"""
日志广播系统
用于实时推送日志到多个订阅者(如WebSocket客户端)
"""

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from typing import Any

import orjson


class LogBroadcaster:
    """日志广播器,用于实时推送日志到订阅者"""

    def __init__(self, max_buffer_size: int = 1000):
        """
        初始化日志广播器

        Args:
            max_buffer_size: 缓冲区最大大小,超过后会丢弃旧日志
        """
        self.subscribers: set[Callable[[dict[str, Any]], None]] = set()
        self.buffer: deque[dict[str, Any]] = deque(maxlen=max_buffer_size)
        self._lock = asyncio.Lock()

    async def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """
        订阅日志推送

        Args:
            callback: 接收日志的回调函数,参数为日志字典
        """
        async with self._lock:
            self.subscribers.add(callback)

    async def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """
        取消订阅

        Args:
            callback: 要移除的回调函数
        """
        async with self._lock:
            self.subscribers.discard(callback)

    async def broadcast(self, log_record: dict[str, Any]) -> None:
        """
        广播日志到所有订阅者

        Args:
            log_record: 日志记录字典
        """
        # 添加到缓冲区
        async with self._lock:
            self.buffer.append(log_record)
            # 创建订阅者列表的副本,避免在迭代时修改
            subscribers = list(self.subscribers)

        # 异步发送到所有订阅者
        tasks = []
        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(asyncio.create_task(callback(log_record)))
                else:
                    # 同步回调在线程池中执行
                    tasks.append(asyncio.to_thread(callback, log_record))
            except Exception:
                # 忽略单个订阅者的错误
                pass

        # 等待所有发送完成(但不阻塞太久)
        if tasks:
            await asyncio.wait(tasks, timeout=1.0)

    def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        获取最近的日志记录

        Args:
            limit: 返回的最大日志数量

        Returns:
            日志记录列表
        """
        return list(self.buffer)[-limit:]

    def clear_buffer(self) -> None:
        """清空日志缓冲区"""
        self.buffer.clear()

    async def shutdown(self) -> None:
        """
        优雅地关闭日志广播器
        清空缓冲区并取消所有待发送的日志
        """
        async with self._lock:
            # 清空缓冲区
            self.clear_buffer()
            # 清空订阅者列表
            self.subscribers.clear()


class BroadcastLogHandler(logging.Handler):
    """
    日志处理器,将日志推送到广播器
    """

    def __init__(self, broadcaster: LogBroadcaster):
        """
        初始化处理器

        Args:
            broadcaster: 日志广播器实例
        """
        super().__init__()
        self.broadcaster = broadcaster
        self.loop: asyncio.AbstractEventLoop | None = None

    def _get_logger_metadata(self, logger_name: str) -> dict[str, str | None]:
        """
        获取logger的元数据（别名和颜色）

        Args:
            logger_name: logger名称

        Returns:
            包含alias和color的字典
        """
        try:
            # 导入logger元数据获取函数
            from src.common.logger import get_logger_meta

            return get_logger_meta(logger_name)
        except Exception:
            # 如果获取失败,返回空元数据
            return {"alias": None, "color": None}

    def emit(self, record: logging.LogRecord) -> None:
        """
        处理日志记录

        Args:
            record: 日志记录
        """
        try:
            # 获取logger元数据（别名和颜色）
            logger_meta = self._get_logger_metadata(record.name)

            # 转换日志记录为字典
            log_dict = {
                "timestamp": self.format_time(record),
                "level": record.levelname,  # 保持大写，与前端筛选器一致
                "logger_name": record.name,  # 原始logger名称
                "event": record.getMessage(),
            }

            # 添加别名和颜色（如果存在）
            if logger_meta["alias"]:
                log_dict["alias"] = logger_meta["alias"]
            if logger_meta["color"]:
                log_dict["color"] = logger_meta["color"]

            # 添加额外字段
            if hasattr(record, "__dict__"):
                for key, value in record.__dict__.items():
                    if key not in (
                        "name",
                        "msg",
                        "args",
                        "created",
                        "filename",
                        "funcName",
                        "levelname",
                        "levelno",
                        "lineno",
                        "module",
                        "msecs",
                        "pathname",
                        "process",
                        "processName",
                        "relativeCreated",
                        "thread",
                        "threadName",
                        "exc_info",
                        "exc_text",
                        "stack_info",
                    ):
                        try:
                            # 尝试序列化以确保可以转为JSON
                            orjson.dumps(value)
                            log_dict[key] = value
                        except (TypeError, ValueError):
                            log_dict[key] = str(value)

            # 获取或创建事件循环
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # 没有运行的事件循环，创建新任务
                if self.loop is None:
                    try:
                        self.loop = asyncio.new_event_loop()
                    except Exception:
                        return
                loop = self.loop

            # 在事件循环中异步广播
            # 使用try/except捕获submit时的异常，避免关闭期间的错误
            try:
                future = asyncio.run_coroutine_threadsafe(self.broadcaster.broadcast(log_dict), loop)
                # 不要阻塞地等待，但设置一个超时以确保Future不会永久挂起
                # 这避免了"was never awaited"警告
                future.set_exception_handler = lambda ctx: None  # pyright: ignore[reportAttributeAccessIssue] # 忽略任何Future相关的异常
            except RuntimeError:
                # 事件循环已关闭，忽略此错误
                pass

        except Exception:
            # 忽略广播错误，避免影响日志系统
            pass

    def format_time(self, record: logging.LogRecord) -> str:
        """
        格式化时间戳

        Args:
            record: 日志记录

        Returns:
            格式化的时间字符串
        """
        from datetime import datetime

        dt = datetime.fromtimestamp(record.created)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


# 全局广播器实例
_global_broadcaster: LogBroadcaster | None = None


def get_log_broadcaster() -> LogBroadcaster:
    """
    获取全局日志广播器实例

    Returns:
        日志广播器实例
    """
    global _global_broadcaster
    if _global_broadcaster is None:
        _global_broadcaster = LogBroadcaster()
    return _global_broadcaster


def setup_log_broadcasting() -> LogBroadcaster:
    """
    设置日志广播系统,将日志处理器添加到根日志记录器

    Returns:
        日志广播器实例
    """
    broadcaster = get_log_broadcaster()

    # 创建并添加广播处理器到根日志记录器
    handler = BroadcastLogHandler(broadcaster)
    handler.setLevel(logging.DEBUG)

    # 添加到根日志记录器
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    return broadcaster
