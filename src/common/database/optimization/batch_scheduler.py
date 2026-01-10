"""增强的数据库批量调度器

在原有批处理功能基础上，增加：
- 自适应批次大小：根据数据库负载动态调整
- 优先级队列：支持紧急操作优先执行
- 性能监控：详细的执行统计和分析
- 智能合并：更高效的操作合并策略
- 自动重试：处理数据库锁和事务错误
"""

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.database.core.session import get_db_session_direct
from src.common.logger import get_logger
from src.common.memory_utils import estimate_size_smart

logger = get_logger("batch_scheduler")


async def _execute_with_retry(
    operation_func: Callable,
    max_retries: int = 3,
    retry_delay: float = 0.1,
    operation_name: str = "数据库操作",
) -> Any:
    """带重试的数据库操作执行器
    
    Args:
        operation_func: 要执行的操作函数（async，返回结果）
        max_retries: 最大重试次数
        retry_delay: 基础重试延迟（秒）
        operation_name: 操作名称（用于日志）
    
    Returns:
        操作结果
    """
    for attempt in range(max_retries):
        try:
            return await operation_func()
        except Exception as e:
            error_str = str(e)
            is_retryable = (
                "database is locked" in error_str 
                or "locked" in error_str.lower()
                or "invalid transaction" in error_str
                or "rolled back" in error_str
            )
            
            if is_retryable and attempt < max_retries - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.warning(
                    f"{operation_name}遇到可重试错误，重试 {attempt + 1}/{max_retries}，"
                    f"等待 {wait_time:.2f}s: {error_str[:100]}"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"{operation_name}失败（尝试 {attempt + 1}/{max_retries}）: {e}")
                raise


class Priority(IntEnum):
    """操作优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class BatchOperation:
    """批量操作"""

    operation_type: str  # 'select', 'insert', 'update', 'delete'
    model_class: type
    conditions: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] | None = None
    callback: Callable | None = None
    future: asyncio.Future | None = None
    timestamp: float = field(default_factory=time.time)
    priority: Priority = Priority.NORMAL
    timeout: float | None = None  # 超时时间（秒）


@dataclass
class BatchStats:
    """批处理统计"""

    total_operations: int = 0
    batched_operations: int = 0
    cache_hits: int = 0
    total_execution_time: float = 0.0
    avg_batch_size: float = 0.0
    avg_wait_time: float = 0.0
    timeout_count: int = 0
    error_count: int = 0

    # 自适应统计
    last_batch_duration: float = 0.0
    last_batch_size: int = 0
    congestion_score: float = 0.0  # 拥塞评分 (0-1)

    # 🔧 新增：缓存统计
    cache_size: int = 0  # 缓存条目数
    cache_memory_mb: float = 0.0  # 缓存内存占用（MB）


class AdaptiveBatchScheduler:
    """自适应批量调度器

    特性：
    - 动态批次大小：根据负载自动调整
    - 优先级队列：高优先级操作优先执行
    - 智能等待：根据队列情况动态调整等待时间
    - 超时处理：防止操作长时间阻塞
    """

    def __init__(
        self,
        min_batch_size: int = 10,
        max_batch_size: int = 100,
        base_wait_time: float = 0.05,  # 50ms
        max_wait_time: float = 0.2,  # 200ms
        max_queue_size: int = 1000,
        cache_ttl: float = 30.0,
    ):
        """初始化调度器

        Args:
            min_batch_size: 最小批次大小
            max_batch_size: 最大批次大小
            base_wait_time: 基础等待时间（秒）
            max_wait_time: 最大等待时间（秒）
            max_queue_size: 最大队列大小
            cache_ttl: 缓存TTL（秒）
        """
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.current_batch_size = min_batch_size
        self.base_wait_time = base_wait_time
        self.max_wait_time = max_wait_time
        self.current_wait_time = base_wait_time
        self.max_queue_size = max_queue_size
        self.cache_ttl = cache_ttl

        # 操作队列，按优先级分类
        self.operation_queues: dict[Priority, deque[BatchOperation]] = {
            priority: deque() for priority in Priority
        }

        # 调度控制
        self._scheduler_task: asyncio.Task | None = None
        self._is_running = False
        self._lock = asyncio.Lock()

        # 统计信息
        self.stats = BatchStats()

        # 🔧 改进的结果缓存（带大小限制和内存统计）
        self._result_cache: dict[str, tuple[Any, float]] = {}
        self._cache_max_size = 1000  # 最大缓存条目数
        self._cache_memory_estimate = 0  # 缓存内存估算（字节）
        self._cache_size_map: dict[str, int] = {}  # 每个缓存条目的大小

        logger.info(
            f"自适应批量调度器初始化: "
            f"批次大小{min_batch_size}-{max_batch_size}, "
            f"等待时间{base_wait_time*1000:.0f}-{max_wait_time*1000:.0f}ms"
        )

    async def start(self) -> None:
        """启动调度器"""
        if self._is_running:
            logger.warning("调度器已在运行")
            return

        self._is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("批量调度器已启动")

    async def stop(self) -> None:
        """停止调度器"""
        if not self._is_running:
            return

        self._is_running = False

        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # 处理剩余操作
        await self._flush_all_queues()
        logger.info("批量调度器已停止")

    async def add_operation(
        self,
        operation: BatchOperation,
    ) -> asyncio.Future:
        """添加操作到队列

        Args:
            operation: 批量操作

        Returns:
            Future对象，可用于获取结果
        """
        # 检查缓存
        if operation.operation_type == "select":
            cache_key = self._generate_cache_key(operation)
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                future = asyncio.get_event_loop().create_future()
                future.set_result(cached_result)
                return future

        # 创建future
        future = asyncio.get_event_loop().create_future()
        operation.future = future

        should_execute_immediately = False
        total_queued = 0

        async with self._lock:
            # 检查队列是否已满
            total_queued = sum(len(q) for q in self.operation_queues.values())
            if total_queued >= self.max_queue_size:
                should_execute_immediately = True
            else:
                # 添加到优先级队列
                self.operation_queues[operation.priority].append(operation)
                self.stats.total_operations += 1

        # 🔧 修复：在锁外执行操作，避免死锁
        if should_execute_immediately:
            logger.warning(f"队列已满({total_queued})，直接执行操作")
            await self._execute_operations([operation])

        return future

    async def _scheduler_loop(self) -> None:
        """调度器主循环"""
        while self._is_running:
            try:
                await asyncio.sleep(self.current_wait_time)
                await self._flush_all_queues()
                await self._adjust_parameters()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器循环异常: {e}")

    async def _flush_all_queues(self) -> None:
        """刷新所有队列"""
        async with self._lock:
            # 收集操作（按优先级）
            operations = []
            for priority in sorted(Priority, reverse=True):
                queue = self.operation_queues[priority]
                count = min(len(queue), self.current_batch_size - len(operations))
                if queue and count > 0:
                    # 使用 list.extend 代替循环 append
                    operations.extend(queue.popleft() for _ in range(count))

            if not operations:
                return

        # 执行批量操作
        await self._execute_operations(operations)

    async def _execute_operations(
        self,
        operations: list[BatchOperation],
    ) -> None:
        """执行批量操作"""
        if not operations:
            return

        start_time = time.time()
        batch_size = len(operations)

        try:
            # 检查超时
            valid_operations = []
            for op in operations:
                if op.timeout and (time.time() - op.timestamp) > op.timeout:
                    # 超时，设置异常
                    if op.future and not op.future.done():
                        op.future.set_exception(TimeoutError("操作超时"))
                    self.stats.timeout_count += 1
                else:
                    valid_operations.append(op)

            if not valid_operations:
                return

            # 按操作类型分组
            op_groups = defaultdict(list)
            for op in valid_operations:
                key = f"{op.operation_type}_{op.model_class.__name__}"
                op_groups[key].append(op)

            # 执行各组操作
            for ops in op_groups.values():
                await self._execute_group(ops)

            # 更新统计
            duration = time.time() - start_time
            self.stats.batched_operations += batch_size
            self.stats.total_execution_time += duration
            self.stats.last_batch_duration = duration
            self.stats.last_batch_size = batch_size

            if self.stats.batched_operations > 0:
                self.stats.avg_batch_size = (
                    self.stats.batched_operations /
                    (self.stats.total_execution_time / duration)
                )

            logger.debug(
                f"批量执行完成: {batch_size}个操作, 耗时{duration*1000:.2f}ms"
            )

        except Exception as e:
            logger.error(f"批量操作执行失败: {e}")
            self.stats.error_count += 1

            # 设置所有future的异常
            for op in operations:
                if op.future and not op.future.done():
                    op.future.set_exception(e)

    async def _execute_group(self, operations: list[BatchOperation]) -> None:
        """执行同类操作组"""
        if not operations:
            return

        op_type = operations[0].operation_type

        try:
            if op_type == "select":
                await self._execute_select_batch(operations)
            elif op_type == "insert":
                await self._execute_insert_batch(operations)
            elif op_type == "update":
                await self._execute_update_batch(operations)
            elif op_type == "delete":
                await self._execute_delete_batch(operations)
            else:
                raise ValueError(f"未知操作类型: {op_type}")

        except Exception as e:
            logger.error(f"执行{op_type}操作组失败: {e}")
            for op in operations:
                if op.future and not op.future.done():
                    op.future.set_exception(e)

    async def _execute_select_batch(
        self,
        operations: list[BatchOperation],
    ) -> None:
        """批量执行查询操作"""
        async with get_db_session_direct() as session:
            for op in operations:
                try:
                    # 构建查询
                    stmt = select(op.model_class)
                    for key, value in op.conditions.items():
                        attr = getattr(op.model_class, key)
                        if isinstance(value, list | tuple | set):
                            stmt = stmt.where(attr.in_(value))
                        else:
                            stmt = stmt.where(attr == value)

                    # 执行查询
                    result = await session.execute(stmt)
                    data = result.scalars().all()

                    # 设置结果
                    if op.future and not op.future.done():
                        op.future.set_result(data)

                    # 缓存结果
                    cache_key = self._generate_cache_key(op)
                    self._set_cache(cache_key, data)

                    # 执行回调
                    if op.callback:
                        try:
                            op.callback(data)
                        except Exception as e:
                            logger.warning(f"回调执行失败: {e}")

                except Exception as e:
                    logger.error(f"查询失败: {e}")
                    if op.future and not op.future.done():
                        op.future.set_exception(e)

    async def _execute_insert_batch(
        self,
        operations: list[BatchOperation],
    ) -> None:
        """批量执行插入操作"""
        async with get_db_session_direct() as session:
            try:
                # 收集数据，并过滤掉 id=None 的情况（让数据库自动生成）
                all_data = []
                for op in operations:
                    if op.data:
                        # 过滤掉 id 为 None 的键，让数据库自动生成主键
                        filtered_data = {k: v for k, v in op.data.items() if not (k == "id" and v is None)}
                        all_data.append(filtered_data)

                if not all_data:
                    return

                # 批量插入
                stmt = insert(operations[0].model_class).values(all_data)
                await session.execute(stmt)
                # 注意：commit 由 get_db_session_direct 上下文管理器自动处理

                # 设置结果
                for op in operations:
                    if op.future and not op.future.done():
                        op.future.set_result(True)

                    if op.callback:
                        try:
                            op.callback(True)
                        except Exception as e:
                            logger.warning(f"回调执行失败: {e}")

            except Exception as e:
                logger.error(f"批量插入失败: {e}")
                # 注意：rollback 由 get_db_session_direct 上下文管理器自动处理
                for op in operations:
                    if op.future and not op.future.done():
                        op.future.set_exception(e)
                raise  # 重新抛出异常以触发 rollback

    async def _execute_update_batch(
        self,
        operations: list[BatchOperation],
    ) -> None:
        """批量执行更新操作"""
        async with get_db_session_direct() as session:
            results = []
            try:
                # 🔧 收集所有操作后一次性commit，而不是循环中多次commit
                for op in operations:
                    # 构建更新语句
                    stmt = update(op.model_class)
                    for key, value in op.conditions.items():
                        attr = getattr(op.model_class, key)
                        stmt = stmt.where(attr == value)

                    if op.data:
                        stmt = stmt.values(**op.data)

                    # 执行更新（但不commit）
                    result = await session.execute(stmt)
                    results.append((op, result.rowcount))  # type: ignore

                # 注意：commit 由 get_db_session_direct 上下文管理器自动处理

                # 设置所有操作的结果
                for op, rowcount in results:
                    if op.future and not op.future.done():
                        op.future.set_result(rowcount)

                    if op.callback:
                        try:
                            op.callback(rowcount)
                        except Exception as e:
                            logger.warning(f"回调执行失败: {e}")

            except Exception as e:
                logger.error(f"批量更新失败: {e}")
                # 注意：rollback 由 get_db_session_direct 上下文管理器自动处理
                # 所有操作都失败
                for op in operations:
                    if op.future and not op.future.done():
                        op.future.set_exception(e)
                raise  # 重新抛出异常以触发 rollback

    async def _execute_delete_batch(
        self,
        operations: list[BatchOperation],
    ) -> None:
        """批量执行删除操作"""
        async with get_db_session_direct() as session:
            results = []
            try:
                # 🔧 收集所有操作后一次性commit，而不是循环中多次commit
                for op in operations:
                    # 构建删除语句
                    stmt = delete(op.model_class)
                    for key, value in op.conditions.items():
                        attr = getattr(op.model_class, key)
                        stmt = stmt.where(attr == value)

                    # 执行删除（但不commit）
                    result = await session.execute(stmt)
                    results.append((op, result.rowcount))  # type: ignore

                # 注意：commit 由 get_db_session_direct 上下文管理器自动处理

                # 设置所有操作的结果
                for op, rowcount in results:
                    if op.future and not op.future.done():
                        op.future.set_result(rowcount)

                    if op.callback:
                        try:
                            op.callback(rowcount)
                        except Exception as e:
                            logger.warning(f"回调执行失败: {e}")

            except Exception as e:
                logger.error(f"批量删除失败: {e}")
                # 注意：rollback 由 get_db_session_direct 上下文管理器自动处理
                # 所有操作都失败
                for op in operations:
                    if op.future and not op.future.done():
                        op.future.set_exception(e)
                raise  # 重新抛出异常以触发 rollback

    async def _adjust_parameters(self) -> None:
        """根据性能自适应调整参数"""
        # 计算拥塞评分
        total_queued = sum(len(q) for q in self.operation_queues.values())
        self.stats.congestion_score = min(1.0, total_queued / self.max_queue_size)

        # 根据拥塞情况调整批次大小
        if self.stats.congestion_score > 0.7:
            # 高拥塞，增加批次大小
            self.current_batch_size = min(
                self.max_batch_size,
                int(self.current_batch_size * 1.2),
            )
        elif self.stats.congestion_score < 0.3:
            # 低拥塞，减小批次大小
            self.current_batch_size = max(
                self.min_batch_size,
                int(self.current_batch_size * 0.9),
            )

        # 根据批次执行时间调整等待时间
        if self.stats.last_batch_duration > 0:
            if self.stats.last_batch_duration > self.current_wait_time * 2:
                # 执行时间过长，增加等待时间
                self.current_wait_time = min(
                    self.max_wait_time,
                    self.current_wait_time * 1.1,
                )
            elif self.stats.last_batch_duration < self.current_wait_time * 0.5:
                # 执行很快，减少等待时间
                self.current_wait_time = max(
                    self.base_wait_time,
                    self.current_wait_time * 0.9,
                )

    def _generate_cache_key(self, operation: BatchOperation) -> str:
        """生成缓存键"""
        key_parts = [
            operation.operation_type,
            operation.model_class.__name__,
            str(sorted(operation.conditions.items())),
        ]
        return "|".join(key_parts)

    def _get_from_cache(self, cache_key: str) -> Any | None:
        """从缓存获取结果"""
        if cache_key in self._result_cache:
            result, timestamp = self._result_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                self.stats.cache_hits += 1
                return result
            else:
                del self._result_cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, result: Any) -> None:
        """设置缓存（改进版，带大小限制和内存统计）"""

        # 🔧 检查缓存大小限制
        if len(self._result_cache) >= self._cache_max_size:
            # 首先清理过期条目
            current_time = time.time()
            expired_keys = [
                k for k, (_, ts) in self._result_cache.items()
                if current_time - ts >= self.cache_ttl
            ]

            for k in expired_keys:
                # 更新内存统计
                if k in self._cache_size_map:
                    self._cache_memory_estimate -= self._cache_size_map[k]
                    del self._cache_size_map[k]
                del self._result_cache[k]

            # 如果还是太大，清理最老的条目（LRU）
            if len(self._result_cache) >= self._cache_max_size:
                oldest_key = min(
                    self._result_cache.keys(),
                    key=lambda k: self._result_cache[k][1]
                )
                # 更新内存统计
                if oldest_key in self._cache_size_map:
                    self._cache_memory_estimate -= self._cache_size_map[oldest_key]
                    del self._cache_size_map[oldest_key]
                del self._result_cache[oldest_key]
                logger.debug(f"缓存已满，淘汰最老条目: {oldest_key}")

        # 🔧 使用准确的内存估算方法
        try:
            total_size = estimate_size_smart(cache_key) + estimate_size_smart(result)
            self._cache_size_map[cache_key] = total_size
            self._cache_memory_estimate += total_size
        except Exception as e:
            logger.debug(f"估算缓存大小失败: {e}")
            # 使用默认值
            self._cache_size_map[cache_key] = 1024
            self._cache_memory_estimate += 1024

        self._result_cache[cache_key] = (result, time.time())

    async def get_stats(self) -> BatchStats:
        """获取统计信息（改进版，包含缓存统计）"""
        async with self._lock:
            return BatchStats(
                total_operations=self.stats.total_operations,
                batched_operations=self.stats.batched_operations,
                cache_hits=self.stats.cache_hits,
                total_execution_time=self.stats.total_execution_time,
                avg_batch_size=self.stats.avg_batch_size,
                timeout_count=self.stats.timeout_count,
                error_count=self.stats.error_count,
                last_batch_duration=self.stats.last_batch_duration,
                last_batch_size=self.stats.last_batch_size,
                congestion_score=self.stats.congestion_score,
                # 🔧 新增：缓存统计
                cache_size=len(self._result_cache),
                cache_memory_mb=self._cache_memory_estimate / (1024 * 1024),
            )


# 全局调度器实例
_global_scheduler: AdaptiveBatchScheduler | None = None
_scheduler_lock = asyncio.Lock()


async def get_batch_scheduler() -> AdaptiveBatchScheduler:
    """获取全局批量调度器（单例）"""
    global _global_scheduler

    if _global_scheduler is None:
        async with _scheduler_lock:
            if _global_scheduler is None:
                _global_scheduler = AdaptiveBatchScheduler()
                await _global_scheduler.start()

    return _global_scheduler


async def close_batch_scheduler() -> None:
    """关闭全局批量调度器"""
    global _global_scheduler

    if _global_scheduler is not None:
        await _global_scheduler.stop()
        _global_scheduler = None
        logger.info("全局批量调度器已关闭")
