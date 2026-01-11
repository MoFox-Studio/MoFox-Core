"""
TaskManager 数据模型

定义任务、配置等数据结构
"""

import time
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class TaskState(Enum):
    """任务状态"""
    QUEUED = "queued"  # 已排队
    WAITING = "waiting"  # 等待依赖
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消
    RETRYING = "retrying"  # 重试中


@dataclass
class TaskConfig:
    """任务配置"""
    priority: TaskPriority = TaskPriority.NORMAL
    timeout: Optional[float] = None  # 超时时间（秒）
    max_retries: int = 0  # 最大重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务ID列表
    metadata: Dict[str, Any] = field(default_factory=dict)  # 任务元数据
    cancel_on_dependency_failure: bool = True  # 依赖失败时是否取消
    enable_watchdog: bool = True  # 是否启用 Watchdog 监控


@dataclass
class ManagedTask:
    """被管理的任务"""
    task_id: str
    name: str
    coro: Callable[..., Coroutine]  # 协程工厂函数
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    config: TaskConfig = field(default_factory=TaskConfig)
    
    # 运行时信息
    state: TaskState = TaskState.QUEUED
    task: Optional[asyncio.Task] = None
    watchdog_id: Optional[str] = None
    result: Any = None
    error: Optional[BaseException] = None
    retry_count: int = 0
    create_time: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # 依赖关系
    dependents: Set[str] = field(default_factory=set)  # 依赖于本任务的任务ID
    
    @property
    def duration(self) -> Optional[float]:
        """任务运行时长"""
        if self.start_time is None:
            return None
        end = self.end_time or time.time()
        return end - self.start_time
    
    @property
    def is_terminal_state(self) -> bool:
        """是否处于终态"""
        return self.state in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED
        )
    
    @property
    def can_retry(self) -> bool:
        """是否可以重试"""
        return self.retry_count < self.config.max_retries
