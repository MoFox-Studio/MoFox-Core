"""
回调管理器

负责管理任务完成和失败的回调函数
"""

import asyncio
import logging
from typing import Callable, List

from .models import ManagedTask

logger = logging.getLogger(__name__)


class CallbackManager:
    """回调管理器"""
    
    def __init__(self):
        """初始化回调管理器"""
        self._on_task_complete_callbacks: List[Callable] = []
        self._on_task_failed_callbacks: List[Callable] = []
    
    def add_complete_callback(self, callback: Callable[[ManagedTask], None]):
        """添加任务完成回调"""
        self._on_task_complete_callbacks.append(callback)
    
    def add_failed_callback(self, callback: Callable[[ManagedTask], None]):
        """添加任务失败回调"""
        self._on_task_failed_callbacks.append(callback)
    
    async def call_complete_callbacks(self, managed_task: ManagedTask) -> None:
        """执行完成回调"""
        for callback in self._on_task_complete_callbacks:
            try:
                await self._safe_callback(callback, managed_task)
            except Exception as e:
                logger.error(f"完成回调执行失败: {e}")
    
    async def call_failed_callbacks(self, managed_task: ManagedTask) -> None:
        """执行失败回调"""
        for callback in self._on_task_failed_callbacks:
            try:
                await self._safe_callback(callback, managed_task)
            except Exception as e:
                logger.error(f"失败回调执行失败: {e}")
    
    async def _safe_callback(self, callback: Callable, managed_task: ManagedTask) -> None:
        """安全执行回调"""
        if asyncio.iscoroutinefunction(callback):
            await callback(managed_task)
        else:
            callback(managed_task)
