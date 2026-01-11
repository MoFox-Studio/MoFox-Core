"""
TaskManager 任务管理器

负责管理和调度异步任务
"""

import asyncio
import time
from typing import Any, Callable, Coroutine, Dict, Optional
from collections import defaultdict

from .models import TaskState, TaskConfig, ManagedTask
from .scheduler import TaskScheduler
from .executor import TaskExecutor
from .dependency import DependencyManager
from .callbacks import CallbackManager
from ..watchdog import get_watchdog

# 使用 MoFox Logger
from ...logger import get_logger, MetadataContext

logger = get_logger(__name__)


class TaskManager:
    """
    任务管理器
    
    功能：
    1. 任务注册与调度
    2. 优先级队列管理
    3. 依赖关系处理
    4. 并发控制
    5. 重试机制
    6. 与 Watchdog 集成
    7. 任务生命周期管理
    """
    
    def __init__(
        self,
        max_concurrent_tasks: int = 10,
        enable_watchdog: bool = True,
        watchdog_check_interval: float = 1.0
    ):
        """
        初始化任务管理器
        
        Args:
            max_concurrent_tasks: 最大并发任务数
            enable_watchdog: 是否启用 Watchdog 监控
            watchdog_check_interval: Watchdog 检查间隔
        """
        self._tasks: Dict[str, ManagedTask] = {}
        self._task_counter = 0
        self._running = False
        
        # 配置
        self.max_concurrent_tasks = max_concurrent_tasks
        self.enable_watchdog = enable_watchdog
        self.watchdog_check_interval = watchdog_check_interval
        
        # 组件
        self._scheduler = TaskScheduler()
        self._executor = TaskExecutor()
        self._dependency_manager = DependencyManager()
        self._callback_manager = CallbackManager()
        
        # 初始化组件
        self._scheduler.set_tasks_dict(self._tasks)
        self._dependency_manager.set_tasks_dict(self._tasks)
        
        # 调度器任务
        self._scheduler_task: Optional[asyncio.Task] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        
        # 统计数据
        self._stats = defaultdict(int)
        
        # Watchdog 实例
        self._watchdog = get_watchdog() if enable_watchdog else None
        
        # 配置项
        self.auto_cancel_on_timeout = True  # 超时时是否自动取消任务
        
        # 如果启用 Watchdog，注册相应的回调
        if self._watchdog:
            self._watchdog.add_timeout_callback(self._on_watchdog_timeout)
            self._watchdog.add_error_callback(self._on_watchdog_error)
    
    async def start(self):
        """启动任务管理器"""
        if self._running:
            logger.warning("TaskManager 已在运行")
            return
        
        self._running = True
        self._semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        
        # 启动 Watchdog
        if self._watchdog:
            self._watchdog.check_interval = self.watchdog_check_interval
            await self._watchdog.start()
        
        # 启动调度器
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info(
            "TaskManager 已启动",
            extra={
                'max_concurrent_tasks': self.max_concurrent_tasks,
                'watchdog_enabled': self.enable_watchdog,
                'watchdog_interval': self.watchdog_check_interval
            }
        )
    
    async def stop(self, cancel_running_tasks: bool = False):
        """
        停止任务管理器
        
        Args:
            cancel_running_tasks: 是否取消正在运行的任务
        """
        if not self._running:
            return
        
        self._running = False
        
        # 取消调度器
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        # 处理正在运行的任务
        if cancel_running_tasks:
            await self._cancel_all_running_tasks()
        else:
            await self._wait_for_running_tasks()
        
        # 停止 Watchdog
        if self._watchdog:
            await self._watchdog.stop()
        
        logger.info("TaskManager 已停止")
    
    def submit_task(
        self,
        coro: Callable[..., Coroutine],
        *args,
        name: Optional[str] = None,
        config: Optional[TaskConfig] = None,
        **kwargs
    ) -> str:
        """
        提交任务
        
        Args:
            coro: 协程函数
            *args: 位置参数
            name: 任务名称
            config: 任务配置
            **kwargs: 关键字参数
        
        Returns:
            任务ID
        """
        if not self._running:
            raise RuntimeError("TaskManager 未运行，请先调用 start()")
        
        # 生成任务ID
        self._task_counter += 1
        task_id = f"task_{self._task_counter}_{int(time.time() * 1000)}"
        
        # 创建任务配置
        task_config = config or TaskConfig()
        
        # 创建被管理任务
        managed_task = ManagedTask(
            task_id=task_id,
            name=name or f"Task-{self._task_counter}",
            coro=coro,
            args=args,
            kwargs=kwargs,
            config=task_config
        )
        
        self._tasks[task_id] = managed_task
        self._stats['total_submitted'] += 1
        
        # 检查依赖关系
        if task_config.dependencies:
            if self._dependency_manager.check_dependencies(task_id):
                managed_task.state = TaskState.QUEUED
                self._scheduler.enqueue_task(managed_task)
            else:
                managed_task.state = TaskState.WAITING
        else:
            managed_task.state = TaskState.QUEUED
            self._scheduler.enqueue_task(managed_task)
        
        # 使用元数据记录任务提交
        with MetadataContext(task_id=task_id, task_name=managed_task.name):
            logger.info(
                f"任务已提交: {managed_task.name}",
                extra={
                    'task_id': task_id,
                    'priority': task_config.priority.name,
                    'has_dependencies': bool(task_config.dependencies),
                    'state': managed_task.state.name,
                    'timeout': task_config.timeout
                }
            )
        
        return task_id
    
    async def _scheduler_loop(self):
        """调度器循环"""
        while self._running:
            try:
                # 获取下一个任务
                task_id = await self._scheduler.get_next_task(timeout=0.1)
                
                if task_id:
                    await self._execute_task(task_id)
                
                # 检查等待中的任务
                await self._dependency_manager.check_waiting_tasks(
                    self._scheduler.enqueue_task
                )
                
                # 短暂休眠，避免忙等待
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器异常: {e}", exc_info=True)
    
    async def _execute_task(self, task_id: str):
        """执行任务"""
        managed_task = self._tasks.get(task_id)
        if not managed_task:
            return
        
        # 获取信号量（控制并发）
        if not self._semaphore:
            logger.error("信号量未初始化，无法执行任务")
            return
        
        self._stats['total_running'] += 1
        
        try:
            await self._executor.execute_task(
                managed_task,
                self._semaphore,
                self._on_task_success,
                self._on_task_error,
                self._on_task_cancelled,
                self._register_watchdog,
                self._unregister_watchdog_task
            )
        finally:
            self._stats['total_running'] -= 1
    
    def _register_watchdog(self, task, name, timeout, metadata):
        """向 Watchdog 注册任务"""
        if self._watchdog:
            return self._watchdog.register_task(
                task,
                name=name,
                timeout=timeout,
                metadata=metadata
            )
        return None
    
    async def _unregister_watchdog_task(self, managed_task: ManagedTask):
        """从 Watchdog 注销任务"""
        await self._unregister_from_watchdog(managed_task)
    
    def _on_watchdog_timeout(self, watchdog_id: str, task_info: Any):
        """
        Watchdog 超时回调
        
        将 Watchdog 检测到的超时事件转发给对应的 TaskManager 任务，
        可配置是否自动取消超时任务
        """
        # 通过 watchdog_id 查找对应的 ManagedTask
        for task_id, managed_task in self._tasks.items():
            if managed_task.watchdog_id == watchdog_id:
                # 使用元数据记录超时
                with MetadataContext(task_id=task_id, task_name=managed_task.name):
                    logger.warning(
                        f"[Watchdog] 检测到任务超时: {managed_task.name}",
                        extra={
                            'task_id': task_id,
                            'watchdog_id': watchdog_id,
                            'timeout': task_info.timeout,
                            'duration': task_info.duration,
                            'will_cancel': self.auto_cancel_on_timeout
                        }
                    )
                
                # 如果启用了自动取消超时任务，则取消该任务
                if self.auto_cancel_on_timeout and managed_task.task and not managed_task.task.done():
                    logger.info(f"[TaskManager] 自动取消超时任务: {managed_task.name}")
                    managed_task.task.cancel("Task timeout in watchdog")
                    self._stats['total_timeout_cancelled'] += 1
                
                break
    
    def _on_watchdog_error(self, watchdog_id: str, task_info: Any):
        """
        Watchdog 错误回调
        
        仅用于记录 Watchdog 检测到的任务错误。
        实际的错误处理在 _on_task_error 中完成。
        """
        # 通过 watchdog_id 查找对应的 ManagedTask
        for task_id, managed_task in self._tasks.items():
            if managed_task.watchdog_id == watchdog_id:
                # 使用元数据记录错误
                with MetadataContext(task_id=task_id, task_name=managed_task.name):
                    logger.error(
                        f"[Watchdog] 检测到任务错误: {managed_task.name}",
                        extra={
                            'task_id': task_id,
                            'watchdog_id': watchdog_id,
                            'error_type': type(task_info.error).__name__,
                            'error_message': str(task_info.error)
                        }
                    )
                break
    
    async def _on_task_success(self, managed_task: ManagedTask, result: Any):
        """任务成功完成
        保护性统计：避免重复计数同一任务的完成事件
        """
        if managed_task.state != TaskState.COMPLETED:
            managed_task.state = TaskState.COMPLETED
            self._stats['total_completed'] += 1
        managed_task.result = result
        managed_task.end_time = time.time()
        
        # 使用元数据记录任务完成
        with MetadataContext(task_id=managed_task.task_id, task_name=managed_task.name):
            logger.info(
                f"任务完成: {managed_task.name}",
                extra={
                    'task_id': managed_task.task_id,
                    'duration': managed_task.duration,
                    'retry_count': managed_task.retry_count,
                    'result_type': type(result).__name__ if result is not None else None
                }
            )
        
        # 触发回调
        await self._callback_manager.call_complete_callbacks(managed_task)
        
        # 处理依赖此任务的任务
        await self._dependency_manager.notify_dependents(
            managed_task.task_id,
            self._scheduler.enqueue_task
        )
    
    async def _on_task_error(self, managed_task: ManagedTask, error: Exception):
        """任务执行失败"""
        managed_task.error = error
        managed_task.end_time = time.time()
        
        # 检查是否可以重试
        if managed_task.can_retry:
            managed_task.retry_count += 1
            managed_task.state = TaskState.RETRYING
            self._stats['total_retries'] += 1
            
            # 使用元数据记录重试
            with MetadataContext(task_id=managed_task.task_id, task_name=managed_task.name):
                logger.warning(
                    f"任务失败，准备重试: {managed_task.name}",
                    extra={
                        'task_id': managed_task.task_id,
                        'retry_count': managed_task.retry_count,
                        'max_retries': managed_task.config.max_retries,
                        'error_type': type(error).__name__,
                        'error_message': str(error),
                        'retry_delay': managed_task.config.retry_delay
                    }
                )
            
            # 延迟后重新加入队列
            await asyncio.sleep(managed_task.config.retry_delay)
            managed_task.state = TaskState.QUEUED
            managed_task.task = None
            managed_task.start_time = None
            managed_task.end_time = None
            managed_task.error = None
            self._scheduler.enqueue_task(managed_task)
            return
        else:
            managed_task.state = TaskState.FAILED
            self._stats['total_failed'] += 1
            
            # 使用元数据记录失败
            with MetadataContext(task_id=managed_task.task_id, task_name=managed_task.name):
                logger.error(
                    f"任务失败: {managed_task.name}",
                    extra={
                        'task_id': managed_task.task_id,
                        'error_type': type(error).__name__,
                        'error_message': str(error),
                        'duration': managed_task.duration,
                        'retry_count': managed_task.retry_count
                    },
                    exc_info=True
                )
            
            # 触发回调
            await self._callback_manager.call_failed_callbacks(managed_task)
            
            # 处理依赖此任务的任务
            await self._dependency_manager.notify_dependents(
                managed_task.task_id,
                self._scheduler.enqueue_task
            )
    
    async def _on_task_cancelled(self, managed_task: ManagedTask):
        """任务被取消"""
        managed_task.state = TaskState.CANCELLED
        managed_task.end_time = time.time()
        self._stats['total_cancelled'] += 1
        
        logger.info(f"任务已取消: {managed_task.name} (ID: {managed_task.task_id})")
        
        # 处理依赖此任务的任务
        await self._dependency_manager.notify_dependents(
            managed_task.task_id,
            self._scheduler.enqueue_task
        )
    
    async def _unregister_from_watchdog(self, managed_task: ManagedTask):
        """
        从 Watchdog 中注销任务
        
        防止任务完成后仍然被 Watchdog 追踪，导致内存泄漏
        """
        if self._watchdog and managed_task.watchdog_id:
            try:
                self._watchdog.unregister_task(managed_task.watchdog_id)
                logger.debug(
                    f"任务已从 Watchdog 中注销: {managed_task.name} "
                    f"(watchdog_id: {managed_task.watchdog_id})"
                )
            except Exception as e:
                logger.warning(
                    f"从 Watchdog 注销任务失败: {managed_task.name}, "
                    f"错误: {e}"
                )
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功取消
        """
        managed_task = self._tasks.get(task_id)
        if not managed_task:
            return False
        
        if managed_task.state == TaskState.RUNNING and managed_task.task:
            managed_task.task.cancel()
            return True
        elif managed_task.state in (TaskState.QUEUED, TaskState.WAITING):
            managed_task.state = TaskState.CANCELLED
            self._stats['total_cancelled'] += 1
            return True
        
        return False
    
    async def wait_for_task(
        self,
        task_id: str,
        timeout: Optional[float] = None
    ) -> Any:
        """
        等待任务完成
        
        Args:
            task_id: 任务ID
            timeout: 超时时间
        
        Returns:
            任务结果
        
        Raises:
            asyncio.TimeoutError: 超时
            Exception: 任务执行失败
        """
        managed_task = self._tasks.get(task_id)
        if not managed_task:
            raise ValueError(f"任务不存在: {task_id}")
        
        # 等待任务完成（包括重试）
        start_time = time.time()
        while not managed_task.is_terminal_state:
            if timeout and (time.time() - start_time) > timeout:
                raise asyncio.TimeoutError()
            await asyncio.sleep(0.1)
        
        # 返回最终结果
        if managed_task.state == TaskState.COMPLETED:
            return managed_task.result
        elif managed_task.state == TaskState.FAILED:
            if managed_task.error:
                raise managed_task.error
            else:
                raise RuntimeError("Task failed with unknown error")
        else:
            raise asyncio.CancelledError()
    
    async def _cancel_all_running_tasks(self):
        """取消所有运行中的任务"""
        for task_id, managed_task in list(self._tasks.items()):
            if managed_task.state == TaskState.RUNNING:
                await self.cancel_task(task_id)
    
    async def _wait_for_running_tasks(self, timeout: float = 30.0):
        """等待所有运行中的任务完成"""
        start_time = time.time()
        while True:
            running_tasks = [
                t for t in self._tasks.values()
                if t.state == TaskState.RUNNING
            ]
            if not running_tasks:
                break
            
            if time.time() - start_time > timeout:
                logger.warning("等待任务完成超时，将取消剩余任务")
                await self._cancel_all_running_tasks()
                break
            
            await asyncio.sleep(0.5)
    
    def get_task_info(self, task_id: str) -> Optional[ManagedTask]:
        """获取任务信息"""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> Dict[str, ManagedTask]:
        """获取所有任务"""
        return self._tasks.copy()
    
    def get_tasks_by_state(self, state: TaskState) -> Dict[str, ManagedTask]:
        """按状态获取任务"""
        return {
            tid: task for tid, task in self._tasks.items()
            if task.state == state
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        running_count = len(self.get_tasks_by_state(TaskState.RUNNING))
        queued_count = len(self.get_tasks_by_state(TaskState.QUEUED))
        waiting_count = len(self.get_tasks_by_state(TaskState.WAITING))
        # 动态统计已完成任务，避免计数偏差（例如重试导致的重复事件）
        # 避免由于潜在的残留任务造成统计超过提交数
        completed_raw = sum(1 for t in self._tasks.values() if t.state == TaskState.COMPLETED)
        # 使用任务计数器作为提交数的权威来源，避免外部状态影响
        completed_count = min(completed_raw, self._task_counter)
        
        return {
            'total_submitted': self._stats['total_submitted'],
            'total_completed': completed_count,
            'total_failed': self._stats['total_failed'],
            'total_cancelled': self._stats['total_cancelled'],
            'total_retries': self._stats['total_retries'],
            'current_running': running_count,
            'current_queued': queued_count,
            'current_waiting': waiting_count,
            'max_concurrent': self.max_concurrent_tasks
        }
    
    def add_complete_callback(self, callback: Callable[[ManagedTask], None]):
        """添加任务完成回调"""
        self._callback_manager.add_complete_callback(callback)
    
    def add_failed_callback(self, callback: Callable[[ManagedTask], None]):
        """添加任务失败回调"""
        self._callback_manager.add_failed_callback(callback)
    
    def print_status(self):
        """打印管理器状态"""
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("TaskManager 状态报告")
        print("="*60)
        print(f"运行状态: {'运行中' if self._running else '已停止'}")
        print(f"最大并发数: {self.max_concurrent_tasks}")
        print("\n统计信息:")
        print(f"  总提交任务: {stats['total_submitted']}")
        print(f"  已完成: {stats['total_completed']}")
        print(f"  失败: {stats['total_failed']}")
        print(f"  取消: {stats['total_cancelled']}")
        print(f"  重试次数: {stats['total_retries']}")
        print(f"  当前运行: {stats['current_running']}")
        print(f"  队列中: {stats['current_queued']}")
        print(f"  等待依赖: {stats['current_waiting']}")
        
        # 显示运行中的任务
        running_tasks = self.get_tasks_by_state(TaskState.RUNNING)
        if running_tasks:
            print("\n运行中的任务:")
            for task_id, task in running_tasks.items():
                print(f"  - {task.name} (ID: {task_id})")
                print(f"    优先级: {task.config.priority.name}, "
                      f"运行时长: {task.duration:.2f}s")
        
        print("="*60 + "\n")


# 全局实例
_task_manager_instance: Optional[TaskManager] = None


def get_task_manager(
    max_concurrent_tasks: int = 10,
    enable_watchdog: bool = True
) -> TaskManager:
    """
    获取全局 TaskManager 实例
    
    Args:
        max_concurrent_tasks: 最大并发任务数
        enable_watchdog: 是否启用 Watchdog
    
    Returns:
        TaskManager 实例
    """
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskManager(
            max_concurrent_tasks=max_concurrent_tasks,
            enable_watchdog=enable_watchdog
        )
    return _task_manager_instance
