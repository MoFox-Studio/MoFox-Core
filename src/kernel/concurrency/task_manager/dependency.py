"""
任务依赖关系管理

负责处理任务间的依赖关系
"""

import logging
from typing import Dict

from .models import ManagedTask, TaskState

logger = logging.getLogger(__name__)


class DependencyManager:
    """依赖管理器"""
    
    def __init__(self):
        self._tasks: Dict[str, ManagedTask] = {}
    
    def set_tasks_dict(self, tasks: Dict[str, ManagedTask]):
        """设置任务字典引用"""
        self._tasks = tasks
    
    def check_dependencies(self, task_id: str) -> bool:
        """
        检查任务的依赖是否满足
        
        Args:
            task_id: 任务ID
        
        Returns:
            True 如果所有依赖都已完成，False 否则
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        for dep_id in task.config.dependencies:
            dep_task = self._tasks.get(dep_id)
            if not dep_task:
                logger.warning(f"依赖任务不存在: {dep_id}")
                return False
            
            # 记录依赖关系
            dep_task.dependents.add(task_id)
            
            # 检查依赖状态
            if dep_task.state != TaskState.COMPLETED:
                if dep_task.state == TaskState.FAILED:
                    if task.config.cancel_on_dependency_failure:
                        task.state = TaskState.CANCELLED
                        task.error = Exception(f"依赖任务失败: {dep_id}")
                return False
        
        return True
    
    async def notify_dependents(
        self,
        task_id: str,
        enqueue_callback
    ) -> None:
        """
        通知依赖任务
        
        Args:
            task_id: 任务ID
            enqueue_callback: 将任务加入队列的回调函数
        """
        task = self._tasks.get(task_id)
        if not task:
            return
        
        for dependent_id in task.dependents:
            dependent = self._tasks.get(dependent_id)
            if not dependent or dependent.state != TaskState.WAITING:
                continue
            
            # 检查依赖是否满足
            if self.check_dependencies(dependent_id):
                dependent.state = TaskState.QUEUED
                enqueue_callback(dependent)
    
    async def check_waiting_tasks(self, enqueue_callback) -> None:
        """
        检查等待中的任务
        
        Args:
            enqueue_callback: 将任务加入队列的回调函数
        """
        for task_id, task in list(self._tasks.items()):
            if task.state == TaskState.WAITING:
                if self.check_dependencies(task_id):
                    task.state = TaskState.QUEUED
                    enqueue_callback(task)
