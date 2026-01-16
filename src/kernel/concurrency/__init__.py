"""
Concurrency Module

提供异步任务管理和监控功能：
- TaskManager: 任务管理器，负责任务调度、执行和生命周期管理
- Watchdog: 任务监控器，负责任务健康度监控和超时检测
"""

from .task_manager import (
    TaskManager,
    TaskConfig,
    TaskPriority,
    TaskState,
    ManagedTask,
    get_task_manager
)

from .watchdog import (
    Watchdog,
    TaskStatus,
    TaskInfo,
    get_watchdog,
    watch_task
)


__all__ = [
    # TaskManager
    'TaskManager',
    'TaskConfig',
    'TaskPriority',
    'TaskState',
    'ManagedTask',
    'get_task_manager',
    
    # Watchdog
    'Watchdog',
    'TaskStatus',
    'TaskInfo',
    'get_watchdog',
    'watch_task',
]
