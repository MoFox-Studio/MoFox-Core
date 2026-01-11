"""
Watchdog 全局任务监控器

负责监控和管理异步任务的生命周期，包括：
- 任务状态跟踪
- 超时检测
- 资源泄露检测
- 任务健康度监控
- 异常任务处理
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set
from collections import defaultdict

# 使用 MoFox Logger
from ..logger import get_logger, MetadataContext

logger = get_logger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    TIMEOUT = "timeout"  # 超时
    CANCELLED = "cancelled"  # 已取消


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    name: str
    task: asyncio.Task
    status: TaskStatus = TaskStatus.PENDING
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    timeout: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[BaseException] = None
    
    @property
    def duration(self) -> float:
        """任务运行时长（秒）"""
        end = self.end_time or time.time()
        return end - self.start_time
    
    @property
    def is_timeout(self) -> bool:
        """是否超时"""
        if self.timeout is None:
            return False
        return self.duration > self.timeout
    
    @property
    def is_alive(self) -> bool:
        """任务是否仍在运行"""
        return not self.task.done()


class Watchdog:
    """
    全局任务监控器（单例模式）
    
    功能：
    1. 任务注册与追踪
    2. 超时监控
    3. 资源泄露检测
    4. 任务统计与报告
    5. 异常任务处理
    """
    
    _instance: Optional['Watchdog'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._tasks: Dict[str, TaskInfo] = {}
        self._task_counter = 0
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 配置
        self.check_interval = 1.0  # 检查间隔（秒）
        self.default_timeout = 300.0  # 默认超时时间（秒）
        self.enable_timeout_check = True  # 是否启用超时检查
        self.enable_leak_detection = True  # 是否启用泄露检测
        
        # 回调函数
        self._on_timeout_callbacks: Set[Callable] = set()
        self._on_error_callbacks: Set[Callable] = set()
        self._on_complete_callbacks: Set[Callable] = set()
        
        # 统计数据
        self._stats = defaultdict(int)
    
    @classmethod
    def get_instance(cls) -> 'Watchdog':
        """获取 Watchdog 单例实例"""
        return cls()
    
    async def start(self):
        """启动监控器"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        print(f"[Watchdog] 监控器已启动，检查间隔: {self.check_interval}s")
    
    async def stop(self):
        """停止监控器"""
        if not self._running:
            return
        
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        print("[Watchdog] 监控器已停止")
    
    def register_task(
        self,
        task: asyncio.Task,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        注册任务到监控器
        
        Args:
            task: 要监控的异步任务
            name: 任务名称
            timeout: 超时时间（秒），None 表示使用默认值
            metadata: 任务元数据
        
        Returns:
            任务ID
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}_{id(task)}"
        
        task_info = TaskInfo(
            task_id=task_id,
            name=name or f"Task-{self._task_counter}",
            task=task,
            status=TaskStatus.RUNNING,
            timeout=timeout or self.default_timeout,
            metadata=metadata or {}
        )
        
        self._tasks[task_id] = task_info
        self._stats['total_registered'] += 1
        
        # 为任务添加完成回调
        task.add_done_callback(lambda t: self._on_task_done(task_id, t))
        
        # 记录任务注册
        with MetadataContext(task_id=task_id, task_name=task_info.name):
            logger.debug(
                f"任务已注册到 Watchdog: {task_info.name}",
                extra={
                    'task_id': task_id,
                    'timeout': task_info.timeout,
                    'metadata': task_info.metadata
                }
            )
        
        return task_id
    
    def unregister_task(self, task_id: str) -> bool:
        """
        取消注册任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功取消注册
        """
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False
    
    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> Dict[str, TaskInfo]:
        """获取所有任务信息"""
        return self._tasks.copy()
    
    def get_running_tasks(self) -> Dict[str, TaskInfo]:
        """获取所有运行中的任务"""
        return {
            tid: info for tid, info in self._tasks.items()
            if info.status == TaskStatus.RUNNING and info.is_alive
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        running_tasks = self.get_running_tasks()
        return {
            'total_registered': self._stats['total_registered'],
            'total_completed': self._stats['total_completed'],
            'total_failed': self._stats['total_failed'],
            'total_timeout': self._stats['total_timeout'],
            'total_cancelled': self._stats['total_cancelled'],
            'current_running': len(running_tasks),
            'current_tracked': len(self._tasks)
        }
    
    async def cancel_task(self, task_id: str, msg: str = "Cancelled by watchdog") -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            msg: 取消原因
        
        Returns:
            是否成功取消
        """
        task_info = self._tasks.get(task_id)
        if not task_info or not task_info.is_alive:
            return False
        
        task_info.task.cancel(msg)
        task_info.status = TaskStatus.CANCELLED
        self._stats['total_cancelled'] += 1
        return True
    
    def add_timeout_callback(self, callback: Callable[[str, TaskInfo], None]):
        """添加超时回调"""
        self._on_timeout_callbacks.add(callback)
    
    def add_error_callback(self, callback: Callable[[str, TaskInfo], None]):
        """添加错误回调"""
        self._on_error_callbacks.add(callback)
    
    def add_complete_callback(self, callback: Callable[[str, TaskInfo], None]):
        """添加完成回调"""
        self._on_complete_callbacks.add(callback)
    
    def _on_task_done(self, task_id: str, task: asyncio.Task):
        """任务完成回调"""
        task_info = self._tasks.get(task_id)
        if not task_info:
            return
        
        task_info.end_time = time.time()
        
        if task.cancelled():
            task_info.status = TaskStatus.CANCELLED
            self._stats['total_cancelled'] += 1
            
            with MetadataContext(task_id=task_id, task_name=task_info.name):
                logger.info(
                    f"[Watchdog] 任务已取消: {task_info.name}",
                    extra={
                        'task_id': task_id,
                        'duration': task_info.duration
                    }
                )
        elif task.exception():
            task_info.status = TaskStatus.FAILED
            task_info.error = task.exception()
            self._stats['total_failed'] += 1
            
            with MetadataContext(task_id=task_id, task_name=task_info.name):
                logger.error(
                    f"[Watchdog] 任务失败: {task_info.name}",
                    extra={
                        'task_id': task_id,
                        'duration': task_info.duration,
                        'error_type': type(task_info.error).__name__,
                        'error_message': str(task_info.error)
                    }
                )
            
            # 触发错误回调
            for callback in self._on_error_callbacks:
                try:
                    callback(task_id, task_info)
                except Exception as e:
                    logger.error(f"[Watchdog] 错误回调执行失败: {e}")
        else:
            task_info.status = TaskStatus.COMPLETED
            self._stats['total_completed'] += 1
            
            with MetadataContext(task_id=task_id, task_name=task_info.name):
                logger.debug(
                    f"[Watchdog] 任务完成: {task_info.name}",
                    extra={
                        'task_id': task_id,
                        'duration': task_info.duration
                    }
                )
            
            # 触发完成回调
            for callback in self._on_complete_callbacks:
                try:
                    callback(task_id, task_info)
                except Exception as e:
                    logger.error(f"[Watchdog] 完成回调执行失败: {e}")
    
    async def _monitor_loop(self):
        """监控循环"""
        logger.info("[Watchdog] 监控循环已启动")
        
        while self._running:
            try:
                await self._check_tasks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("[Watchdog] 监控循环被取消")
                break
            except Exception:
                logger.error("[Watchdog] 监控循环异常", exc_info=True)
    
    async def _check_tasks(self):
        """检查所有任务"""
        current_time = time.time()
        tasks_to_handle = []
        
        for task_id, task_info in list(self._tasks.items()):
            # 检查超时（只处理一次超时事件，避免重复计数）
            if (
                self.enable_timeout_check
                and task_info.is_alive
                and task_info.is_timeout
                and task_info.status != TaskStatus.TIMEOUT
            ):
                tasks_to_handle.append((task_id, task_info, 'timeout'))
            
            # 清理已完成的任务（保留一段时间后清理）
            elif (
                not task_info.is_alive
                and task_info.end_time
                and current_time - task_info.end_time > 60
            ):
                tasks_to_handle.append((task_id, task_info, 'cleanup'))
        
        # 处理需要处理的任务
        for task_id, task_info, action in tasks_to_handle:
            if action == 'timeout':
                await self._handle_timeout(task_id, task_info)
            elif action == 'cleanup':
                self.unregister_task(task_id)
    
    async def _handle_timeout(self, task_id: str, task_info: TaskInfo):
        """处理超时任务"""
        task_info.status = TaskStatus.TIMEOUT
        self._stats['total_timeout'] += 1
        
        # 使用元数据记录超时
        with MetadataContext(task_id=task_id, task_name=task_info.name):
            logger.warning(
                f"[Watchdog] 任务超时: {task_info.name}",
                extra={
                    'task_id': task_id,
                    'duration': task_info.duration,
                    'timeout': task_info.timeout,
                    'metadata': task_info.metadata
                }
            )
        
        # 触发超时回调，让上层决定是否取消任务
        for callback in self._on_timeout_callbacks:
            try:
                callback(task_id, task_info)
            except Exception:
                logger.error("[Watchdog] 超时回调执行失败", exc_info=True)
        
        # 注意：不再自动取消超时任务，而是让 TaskManager 通过回调决定
        # 如果上层没有处理，任务将继续运行并在真正完成时更新状态
    
    def print_status(self):
        """打印监控器状态"""
        stats = self.get_stats()
        running_tasks = self.get_running_tasks()
        
        print("\n" + "="*60)
        print("Watchdog 状态报告")
        print("="*60)
        print(f"运行状态: {'运行中' if self._running else '已停止'}")
        print("\n统计信息:")
        print(f"  总注册任务: {stats['total_registered']}")
        print(f"  已完成: {stats['total_completed']}")
        print(f"  失败: {stats['total_failed']}")
        print(f"  超时: {stats['total_timeout']}")
        print(f"  取消: {stats['total_cancelled']}")
        print(f"  当前运行: {stats['current_running']}")
        print(f"  当前跟踪: {stats['current_tracked']}")
        
        if running_tasks:
            print("\n运行中的任务:")
            for task_id, info in running_tasks.items():
                print(f"  - {info.name} (ID: {task_id})")
                print(f"    状态: {info.status.value}, 运行时长: {info.duration:.2f}s")
                if info.timeout:
                    print(f"    超时设置: {info.timeout}s")
        
        print("="*60 + "\n")


# 全局实例
_watchdog_instance: Optional[Watchdog] = None


def get_watchdog() -> Watchdog:
    """获取全局 Watchdog 实例"""
    global _watchdog_instance
    if _watchdog_instance is None:
        _watchdog_instance = Watchdog.get_instance()
    return _watchdog_instance


async def watch_task(
    coro,
    name: Optional[str] = None,
    timeout: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    auto_start: bool = True
) -> tuple[asyncio.Task, str]:
    """
    便捷函数：创建并注册监控任务
    
    Args:
        coro: 协程对象
        name: 任务名称
        timeout: 超时时间
        metadata: 任务元数据
        auto_start: 是否自动启动 watchdog
    
    Returns:
        (task, task_id) 元组
    """
    watchdog = get_watchdog()
    
    if auto_start and not watchdog._running:
        await watchdog.start()
    
    task = asyncio.create_task(coro)
    task_id = watchdog.register_task(task, name, timeout, metadata)
    
    return task, task_id
