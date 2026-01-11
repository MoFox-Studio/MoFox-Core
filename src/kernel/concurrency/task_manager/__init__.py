"""
TaskManager 任务管理器模块

负责管理和调度异步任务，提供：
- 任务创建与执行
- 任务优先级管理
- 任务依赖关系处理
- 任务队列管理
- 任务重试机制
- 与 Watchdog 集成的任务监控
- 并发控制
"""

from typing import Optional
from .manager import TaskManager
from .models import TaskPriority, TaskState, TaskConfig, ManagedTask

__all__ = [
    'TaskManager',
    'get_task_manager',
    'TaskPriority',
    'TaskState',
    'TaskConfig',
    'ManagedTask',
]

# 在包层面维护全局实例，便于测试重置
_task_manager_instance: Optional[TaskManager] = None


def get_task_manager(
    max_concurrent_tasks: int = 10,
    enable_watchdog: bool = True
) -> TaskManager:
    """
    获取全局 TaskManager 实例（包级实例）
    与测试中的 reset_instances 保持一致，避免跨模块全局不一致。
    """
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskManager(
            max_concurrent_tasks=max_concurrent_tasks,
            enable_watchdog=enable_watchdog
        )
    return _task_manager_instance
