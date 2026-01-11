"""
TaskManager 任务管理器 (向后兼容层)

此模块保持向后兼容性。所有实现已经重构到 task_manager 包中。

负责管理和调度异步任务，提供：
- 任务创建与执行
- 任务优先级管理
- 任务依赖关系处理
- 任务队列管理
- 任务重试机制
- 与 Watchdog 集成的任务监控
- 并发控制
"""

# 从新的模块结构中导入所有内容
from .task_manager.models import (
    TaskPriority,
    TaskState,
    TaskConfig,
    ManagedTask,
)
from .task_manager.manager import (
    TaskManager,
    get_task_manager,
    _task_manager_instance,
)

__all__ = [
    'TaskManager',
    'TaskConfig',
    'TaskPriority',
    'TaskState',
    'ManagedTask',
    'get_task_manager',
    '_task_manager_instance',
]
