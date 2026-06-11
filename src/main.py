# 再用这个就写一行注释来混提交的我直接全部🌿飞😡
# 🌿🌿need
# 待重写
import asyncio
import signal
import sys
import time
import traceback
from collections.abc import Callable, Coroutine
from random import choices
from typing import Any

from rich.traceback import install

from src.chat.emoji_system.emoji_manager import get_emoji_manager
from src.chat.message_receive.message_handler import get_message_handler, shutdown_message_handler
from src.chat.utils.statistic import OnlineTimeRecordTask, StatisticOutputTask
from src.common.core_sink_manager import (
    CoreSinkManager,
    initialize_core_sink_manager,
    shutdown_core_sink_manager,
)
from src.common.logger import get_logger

logger = get_logger("main_system")
from src.common.mem_monitor import (
    MEM_MONITOR_ENABLED,
    start_background_monitor,
    stop_background_monitor,
)

# 全局背景任务集合
_background_tasks = set()
from src.common.server import Server, get_global_server
from src.config.config import global_config
from src.individuality.individuality import Individuality, get_individuality
from src.manager.async_task_manager import async_task_manager
from src.mood.mood_manager import mood_manager
from src.plugin_system.base.component_types import EventType
from src.plugin_system.core.event_manager import event_manager
from src.plugin_system.core.plugin_manager import plugin_manager
from src.schedule.monthly_plan_manager import monthly_plan_manager
from src.schedule.schedule_manager import schedule_manager


class MainSystem:
    """MoFox_Bot 主系统类

    负责核心组件初始化与启动协调。
    替代原有的函数式 main.py，提供面向对象的初始化接口。
    """

    def __init__(self):
        self._initialized = False
        self._running = False
        self._server: Server | None = None

    async def initialize(self):
        """异步初始化核心组件"""
        if self._initialized:
            return

        logger.info("正在初始化主系统...")

        # 1. 触发启动事件 (插件在 PluginManager 构造时已自动加载)
        await event_manager.trigger_event(EventType.ON_START)

        # 2. 初始化 schedule_manager
        await schedule_manager.initialize()

        # 3. 初始化 monthly_plan_manager
        await monthly_plan_manager.initialize()

        # 4. 初始化核心汇管理器
        await initialize_core_sink_manager()

        # 5. 初始化个体性系统
        individuality = get_individuality()
        await individuality.initialize()

        # 6. 启动内存监控（如启用）
        if MEM_MONITOR_ENABLED:
            start_background_monitor()

        logger.info("主系统初始化完成")

        self._initialized = True

    async def schedule_tasks(self):
        """启动调度任务循环"""
        if self._running:
            return
        self._running = True

        logger.info("正在启动调度任务...")

        try:
            await schedule_manager.initialize()
        except asyncio.CancelledError:
            logger.info("调度任务被取消")
        except Exception as e:
            logger.error(f"调度任务崩溃: {e}", exc_info=True)
        finally:
            self._running = False

    async def shutdown(self):
        """优雅关闭"""
        logger.info("正在关闭主系统...")

        self._running = False

        if MEM_MONITOR_ENABLED:
            stop_background_monitor()

        await schedule_manager.shutdown()
        await shutdown_core_sink_manager()

        logger.info("主系统已关闭")


# 向后兼容的单例别名
main_system = MainSystem()