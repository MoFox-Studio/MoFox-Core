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

