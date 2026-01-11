"""
任务调度器

负责按优先级调度任务
"""

import asyncio
import logging
from typing import Dict, Optional

from .models import TaskPriority, ManagedTask

logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self):
        """初始化调度器"""
        self._priority_queues: Dict[TaskPriority, asyncio.Queue] = {
            priority: asyncio.Queue() for priority in TaskPriority
        }
        self._tasks: Dict[str, ManagedTask] = {}
    
    def set_tasks_dict(self, tasks: Dict[str, ManagedTask]):
        """设置任务字典引用"""
        self._tasks = tasks
    
    def enqueue_task(self, managed_task: ManagedTask) -> None:
        """将任务加入优先级队列"""
        priority = managed_task.config.priority
        try:
            self._priority_queues[priority].put_nowait(managed_task.task_id)
        except asyncio.QueueFull:
            logger.warning(f"优先级队列已满: {priority}")
    
    async def get_next_task(self, timeout: float = 0.1) -> Optional[str]:
        """
        按优先级获取下一个任务
        
        Args:
            timeout: 获取超时时间
        
        Returns:
            任务ID
        """
        # 按优先级从高到低处理任务
        for priority in sorted(TaskPriority, key=lambda p: p.value, reverse=True):
            queue = self._priority_queues[priority]
            
            if not queue.empty():
                try:
                    task_id = await asyncio.wait_for(
                        queue.get(),
                        timeout=timeout
                    )
                    return task_id
                except asyncio.TimeoutError:
                    continue
        
        return None
    
    def is_queue_empty(self) -> bool:
        """检查所有队列是否为空"""
        return all(queue.empty() for queue in self._priority_queues.values())
