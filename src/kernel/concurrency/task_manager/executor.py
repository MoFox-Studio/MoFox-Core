"""
任务执行器

负责执行单个任务及其生命周期管理
"""

import asyncio
import time
import logging
from typing import Callable, Optional

from .models import ManagedTask, TaskState

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器"""
    
    def __init__(self):
        self.auto_cancel_on_timeout = True
    
    async def execute_task(
        self,
        managed_task: ManagedTask,
        semaphore: asyncio.Semaphore,
        on_success: Callable,
        on_error: Callable,
        on_cancelled: Callable,
        register_watchdog: Optional[Callable] = None,
        unregister_watchdog: Optional[Callable] = None
    ) -> None:
        """
        执行任务
        
        Args:
            managed_task: 被管理的任务
            semaphore: 并发信号量
            on_success: 成功回调
            on_error: 错误回调
            on_cancelled: 取消回调
            register_watchdog: Watchdog 注册函数
            unregister_watchdog: Watchdog 注销函数
        """
        await semaphore.acquire()
        
        try:
            managed_task.state = TaskState.RUNNING
            managed_task.start_time = time.time()
            
            # 创建协程
            coro = managed_task.coro(*managed_task.args, **managed_task.kwargs)
            
            # 创建任务
            task = asyncio.create_task(coro)
            managed_task.task = task
            
            # 注册到 Watchdog
            if register_watchdog and managed_task.config.enable_watchdog:
                watchdog_id = register_watchdog(
                    task,
                    name=managed_task.name,
                    timeout=managed_task.config.timeout,
                    metadata=managed_task.config.metadata
                )
                managed_task.watchdog_id = watchdog_id
            
            # 等待任务完成
            try:
                result = await task
                await on_success(managed_task, result)
            except asyncio.CancelledError:
                await on_cancelled(managed_task)
            except Exception as e:
                await on_error(managed_task, e)
            
        finally:
            semaphore.release()
            if unregister_watchdog:
                await unregister_watchdog(managed_task)
