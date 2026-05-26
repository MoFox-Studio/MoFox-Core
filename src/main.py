# 再用这个就写一行注释来混提交的我直接全部🌿飞😡
# 🌿🌿need
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

# 插件系统现在使用统一的插件加载器
install(extra_lines=3)

logger = get_logger("main")

# 预定义彩蛋短语，避免在每次初始化时重新创建
EGG_PHRASES: list[tuple[str, int]] = [
    ("我们的代码里真的没有bug，只有'特性'。", 10),
    ("你知道吗,雅诺狐的耳朵其实很好摸", 5),
    ("你群最高技术力————言柒姐姐！", 20),
    ("初墨小姐宇宙第一(不是)", 10),
    ("world.execute(me);", 10),
    ("正在尝试连接到MaiBot的服务器...连接失败...，正在转接到maimaiDX", 10),
    ("你的bug就像星星一样多，而我的代码像太阳一样，一出来就看不见了。", 10),
    ("温馨提示：请不要在代码中留下任何魔法数字，除非你知道它的含义。", 10),
    ("世界上只有10种人：懂二进制的和不懂的。", 10),
    ("喵喵~你的麦麦被猫娘入侵了喵~", 15),
    ("恭喜你触发了稀有彩蛋喵：诺狐嗷呜~ ~", 1),
    ("恭喜你！！！你的开发者模式已成功开启，快来加入我们吧！(๑•̀ㅂ•́)و✧   (小声bb:其实是当黑奴)", 10),
]


class MainSystem:
    """主系统类，负责协调所有组件"""

    def __init__(self) -> None:
        self.individuality: Individuality = get_individuality()

        # CoreSinkManager 和 MessageHandler 将在 initialize() 中创建
        self.core_sink_manager: CoreSinkManager | None = None
        self.message_handler = None

        # 使用服务器
        self.server: Server = get_global_server()

        # 设置信号处理器用于优雅退出
        self._shutting_down = False
        self._cleanup_started = False
        self._setup_signal_handlers()

        # 存储清理任务的引用
        self._cleanup_tasks: list[asyncio.Task] = []

    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""

        def signal_handler(signum, frame):
            if self._shutting_down:
                logger.warning("系统已经在关闭过程中，忽略重复信号")
                return

            self._shutting_down = True
            logger.info("收到退出信号，正在优雅关闭系统...")

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，创建任务并设置回调
                    async def cleanup_and_exit():
                        await self._async_cleanup()
                        # 给日志系统一点时间刷新
                        await asyncio.sleep(0.1)
                        sys.exit(0)

                    task = asyncio.create_task(cleanup_and_exit())
                    # 存储清理任务引用
                    self._cleanup_tasks.append(task)
                    # 添加任务完成回调，确保程序退出
                    task.add_done_callback(lambda t: sys.exit(0) if not t.cancelled() else None)
                else:
                    # 如果事件循环未运行，使用同步清理
                    self._cleanup()
                    sys.exit(0)
            except Exception as e:
                logger.error(f"信号处理失败: {e}")
                sys.exit(1)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def _async_cleanup(self) -> None:
        """异步清理资源"""
        if self._cleanup_started:
            return

        self._cleanup_started = True
        self._shutting_down = True
        logger.info("开始系统清理流程...")

        # 停止内存监控线程（无需 await，同步操作）
        try:
            stop_background_monitor(timeout=3.0)
        except Exception as e:
            logger.error(f"停止内存监控时出错: {e}")

        cleanup_tasks = []

        # 停止日程管理器（优先级最高，防止在关闭数据库前任务还在访问）
        try:
            from src.schedule.schedule_manager import schedule_manager

            cleanup_tasks.append(("日程管理器", schedule_manager.shutdown()))
        except Exception as e:
            logger.error(f"准备停止日程管理器时出错: {e}")

        # 停止消息批处理器
        try:
            from src.chat.message_receive.storage import get_message_storage_batcher, get_message_update_batcher

            storage_batcher = get_message_storage_batcher()
            cleanup_tasks.append(("消息存储批处理器", storage_batcher.stop()))

            update_batcher = get_message_update_batcher()
            cleanup_tasks.append(("消息更新批处理器", update_batcher.stop()))
        except Exception as e:
            logger.error(f"准备停止消息批处理器时出错: {e}")

        # 停止消息管理器
        try:
            from src.chat.message_manager import message_manager

            cleanup_tasks.append(("消息管理器", message_manager.stop()))
        except Exception as e:
            logger.error(f"准备停止消息管理器时出错: {e}")

        # 停止消息重组器
        try:
            from src.utils.message_chunker import reassembler

            cleanup_tasks.append(("消息重组器", reassembler.stop_cleanup_task()))
        except Exception as e:
            logger.error(f"准备停止消息重组器时出错: {e}")

        # 停止增强记忆系统
        # 停止三层记忆系统
        try:
            from src.memory_graph.manager_singleton import get_unified_memory_manager, shutdown_unified_memory_manager

            if get_unified_memory_manager():
                cleanup_tasks.append(("三层记忆系统", shutdown_unified_memory_manager()))
                logger.info("准备停止三层记忆系统...")
        except Exception as e:
            logger.error(f"准备停止三层记忆系统时出错: {e}")

        # 停止统一调度器
        try:
            from src.plugin_system.apis.unified_scheduler import shutdown_scheduler

            cleanup_tasks.append(("统一调度器", shutdown_scheduler()))
        except Exception as e:
            logger.error(f"准备停止统一调度器时出错: {e}")

        # 触发停止事件
        try:
            from src.plugin_system.core.event_manager import event_manager

            cleanup_tasks.append(
                ("插件系统停止事件", event_manager.trigger_event(EventType.ON_STOP, permission_group="SYSTEM"))
            )
        except Exception as e:
            logger.error(f"准备触发停止事件时出错: {e}")

        # 停止表情管理器
        try:
            cleanup_tasks.append(
                ("表情管理器", asyncio.get_event_loop().run_in_executor(None, get_emoji_manager().shutdown))
            )
        except Exception as e:
            logger.error(f"准备停止表情管理器时出错: {e}")

        # 停止服务器
        try:
            if self.server:
                cleanup_tasks.append(("服务器", self.server.shutdown()))
        except Exception as e:
            logger.error(f"准备停止服务器时出错: {e}")

        # 停止所有适配器
        try:
            from src.plugin_system.core.adapter_manager import get_adapter_manager

            adapter_manager = get_adapter_manager()
            cleanup_tasks.append(("适配器管理器", adapter_manager.stop_all_adapters()))
        except Exception as e:
            logger.error(f"准备停止适配器管理器时出错: {e}")

        # 停止 CoreSinkManager
        try:
            cleanup_tasks.append(("CoreSinkManager", shutdown_core_sink_manager()))
        except Exception as e:
            logger.error(f"准备停止 CoreSinkManager 时出错: {e}")

        # 停止 MessageHandler
        try:
            cleanup_tasks.append(("MessageHandler", shutdown_message_handler()))
        except Exception as e:
            logger.error(f"准备停止 MessageHandler 时出错: {e}")

        # 并行执行所有清理任务
        if cleanup_tasks:
            logger.debug(f"开始并行执行 {len(cleanup_tasks)} 个清理任务...")
            tasks = [task for _, task in cleanup_tasks]
            task_names = [name for name, _ in cleanup_tasks]

            # 使用asyncio.gather并行执行，使用更长的超时或者更智能的取消策略
            try:
                # 给清理任务更多时间（60秒）以确保优雅关闭完成
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=60.0,  # 增加到60秒超时以允许优雅关闭
                )

                # 记录结果
                for i, (name, result) in enumerate(zip(task_names, results)):
                    if isinstance(result, Exception):
                        logger.error(f"停止 {name} 时出错: {result}")
                    else:
                        logger.info(f"🛑 {name} 已停止")

            except asyncio.TimeoutError:
                logger.error("清理任务超时，开始强制取消...")
                # 取消所有仍在运行的任务
                for task in tasks:
                    if isinstance(task, asyncio.Task) and not task.done():
                        task.cancel()
                # 等待所有任务完成（已取消）
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.error("所有清理任务已被强制取消")
            except Exception as e:
                logger.error(f"执行清理任务时发生错误: {e}")
        else:
            logger.warning("没有需要清理的任务")

        # 停止日志广播器（在所有其他清理后停止，避免关闭期间的日志问题）
        try:
            from src.common.log_broadcaster import get_log_broadcaster

            log_broadcaster = get_log_broadcaster()
            await log_broadcaster.shutdown()
            logger.info("🛑 日志广播器已停止")
        except Exception as e:
            logger.error(f"停止日志广播器时出错: {e}")

        # 停止数据库服务 (在所有其他任务完成后最后停止)
        try:
            from src.common.database.core import close_engine as stop_database

            logger.info("正在停止数据库服务...")
            await asyncio.wait_for(stop_database(), timeout=15.0)
            logger.info("🛑 数据库服务已停止")

            # 输出数据库性能统计和慢查询报告
            try:
                from src.common.database.utils.monitoring import get_slow_query_report, print_stats
                from src.common.database.utils.slow_query_analyzer import SlowQueryAnalyzer

                logger.info("")  # 空行
                print_stats()  # 打印数据库性能统计

                # 如果有慢查询，尝试生成报告
                slow_report = get_slow_query_report()
                if slow_report.get("total", 0) > 0:
                    logger.info("")  # 空行
                    logger.info("正在生成慢查询详细报告...")
                    try:
                        # 生成文本报告
                        text_report = SlowQueryAnalyzer.generate_text_report()
                        logger.info("")  # 空行
                        logger.info(text_report)

                        # 尝试生成HTML报告
                        html_file = "logs/slow_query_report.html"
                        SlowQueryAnalyzer.generate_html_report(html_file)
                        logger.info(f"💡 HTML慢查询报告已生成: {html_file}")
                    except Exception as e:
                        logger.warning(f"生成慢查询报告失败: {e}")
            except Exception as e:
                logger.warning(f"无法输出数据库统计信息: {e}")

        except asyncio.TimeoutError:
            logger.error("停止数据库服务超时")
        except Exception as e:
            logger.error(f"停止数据库服务时出错: {e}")

    def _cleanup(self) -> None:
        """同步清理资源（向后兼容）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，创建异步清理任务
                task = asyncio.create_task(self._async_cleanup())
                self._cleanup_tasks.append(task)
            else:
                # 如果循环未运行，直接运行异步清理
                loop.run_until_complete(self._async_cleanup())
        except Exception as e:
            logger.error(f"同步清理资源时出错: {e}")

    async def initialize(self) -> None:
        """初始化系统组件"""
        # 检查必要的配置
        if not global_config or not global_config.bot or not global_config.bot.nickname:
            logger.error("缺少必要的bot配置")
            raise ValueError("Bot配置不完整")

        logger.debug(f"正在唤醒{global_config.bot.nickname}......")

        # 配置数据库慢查询监控
        try:
            from src.common.database.utils.monitoring import set_slow_query_config

            if global_config.database:
                db_config = global_config.database
                if db_config.enable_slow_query_logging:
                    set_slow_query_config(
                        threshold=db_config.slow_query_threshold,
                        buffer_size=db_config.slow_query_buffer_size,
                    )
                    logger.info(
                        f"✅ 数据库慢查询监控已启用 "
                        f"(阈值: {db_config.slow_query_threshold}s, "
                        f"缓冲: {db_config.slow_query_buffer_size})"
                    )
        except Exception as e:
            logger.warning(f"配置数据库监控时出错: {e}")

        # 初始化 CoreSinkManager（包含 MessageRuntime）
        logger.debug("正在初始化 CoreSinkManager...")
        self.core_sink_manager = await initialize_core_sink_manager()

        # 获取 MessageHandler 并向 MessageRuntime 注册处理器
        self.message_handler = get_message_handler()
        self.message_handler.set_core_sink_manager(self.core_sink_manager)

        # 向 MessageRuntime 注册消息处理器和钩子
        self.message_handler.register_handlers(self.core_sink_manager.runtime)
        logger.debug("CoreSinkManager 和 MessageHandler 初始化完成（使用 MessageRuntime 路由）")

        # 初始化组件
        await self._init_components()

        # 随机选择彩蛋
        egg_texts, weights = zip(*EGG_PHRASES)
        selected_egg = choices(egg_texts, weights=weights, k=1)[0]

        logger.debug(
            "全部系统初始化完成，%s 已唤醒（彩蛋：%s）",
            global_config.bot.nickname if global_config and global_config.bot else "Bot",
            selected_egg,
        )

    async def _init_components(self) -> None:
        """初始化其他组件"""
        init_start_time = time.time()

        # 并行初始化基础组件
        base_init_tasks = [
            async_task_manager.add_task(OnlineTimeRecordTask()),
            async_task_manager.add_task(StatisticOutputTask()),
            #async_task_manager.add_task(TelemetryHeartBeatTask()),
        ]

        await asyncio.gather(*base_init_tasks, return_exceptions=True)
        logger.debug("基础定时任务初始化成功")

        # 注册默认事件
        event_manager.init_default_events()

        # 初始化权限管理器
        try:
            from src.plugin_system.apis.permission_api import permission_api
            from src.plugin_system.core.permission_manager import PermissionManager

            permission_manager = PermissionManager()
            await permission_manager.initialize()
            permission_api.set_permission_manager(permission_manager)
            logger.debug("权限管理器初始化成功")
        except Exception as e:
            logger.error(f"权限管理器初始化失败: {e}")

        # 注册API路由
        try:
            from src.api.memory_visualizer_router import router as visualizer_router
            from src.api.message_router import router as message_router
            from src.api.statistic_router import router as llm_statistic_router

            self.server.register_router(message_router, prefix="/api")
            self.server.register_router(llm_statistic_router, prefix="/api")
            self.server.register_router(visualizer_router, prefix="/visualizer")
            logger.debug("API路由注册成功")
        except Exception as e:
            logger.error(f"注册API路由失败: {e}")
        # 初始化统一调度器
        try:
            from src.plugin_system.apis.unified_scheduler import initialize_scheduler

            await initialize_scheduler()
        except Exception as e:
            logger.error(f"统一调度器初始化失败: {e}")

        # 设置核心消息接收器到插件管理器
        # 使用 CoreSinkManager 的 InProcessCoreSink
        if self.core_sink_manager:
            plugin_manager.set_core_sink(self.core_sink_manager.get_in_process_sink())
        else:
            logger.error("CoreSinkManager 未初始化，无法设置核心消息接收器")

        # 加载所有插件
        plugin_manager.load_all_plugins()

        # 处理所有缓存的事件订阅（插件加载完成后）
        event_manager.process_all_pending_subscriptions()

        # 初始化表情管理器
        get_emoji_manager().initialize()
        logger.debug("表情包管理器初始化成功")

        # 启动情绪管理器
        await mood_manager.start()
        logger.debug("情绪管理器初始化成功")

        # 初始化日志广播系统
        try:
            from src.common.log_broadcaster import setup_log_broadcasting
            setup_log_broadcasting()
            logger.debug("日志广播系统初始化成功")
        except Exception as e:
            logger.error(f"日志广播系统初始化失败: {e}")

        # 启动聊天管理器的自动保存任务
        from src.chat.message_receive.chat_stream import get_chat_manager
        task = asyncio.create_task(get_chat_manager()._auto_save_task())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        # 初始化记忆图系统
        try:
            from src.memory_graph.manager_singleton import initialize_memory_manager
            await self._safe_init("记忆图系统", initialize_memory_manager)()
        except Exception as e:
            logger.error(f"记忆图系统初始化失败: {e}")

        # 三层记忆系统已由 initialize_memory_manager 内部初始化

        # 初始化LPMM知识库
        try:
            from src.chat.knowledge.knowledge_lib import initialize_lpmm_knowledge

            initialize_lpmm_knowledge()
            logger.debug("LPMM知识库初始化成功")
        except Exception as e:
            logger.error(f"LPMM知识库初始化失败: {e}")

        # 消息接收器已在 initialize() 中通过 CoreSinkManager 创建
        logger.debug("核心消息接收器已就绪（通过 CoreSinkManager）")

        # 启动消息重组器
        try:
            from src.utils.message_chunker import reassembler

            await reassembler.start_cleanup_task()
            logger.debug("消息重组器已启动")
        except Exception as e:
            logger.error(f"启动消息重组器失败: {e}")

        # 启动消息存储批处理器
        try:
            from src.chat.message_receive.storage import get_message_storage_batcher, get_message_update_batcher

            storage_batcher = get_message_storage_batcher()
            await storage_batcher.start()
            logger.debug("消息存储批处理器已启动")

            update_batcher = get_message_update_batcher()
            await update_batcher.start()
            logger.debug("消息更新批处理器已启动")
        except Exception as e:
            logger.error(f"启动消息批处理器失败: {e}")

        # 启动消息管理器
        try:
            from src.chat.message_manager import message_manager

            await message_manager.start()
            logger.debug("消息管理器已启动")
        except Exception as e:
            logger.error(f"启动消息管理器失败: {e}")

        # 初始化个体特征
        await self._safe_init("个体特征", self.individuality.initialize)()

        # 初始化计划相关组件
        await self._init_planning_components()

        # 触发启动事件
        try:
            await event_manager.trigger_event(EventType.ON_START, permission_group="SYSTEM")
            init_time = int(1000 * (time.time() - init_start_time))
            logger.debug(f"初始化完成，神经元放电{init_time}次")
        except Exception as e:
            logger.error(f"启动事件触发失败: {e}")

        # 启动所有适配器
        try:
            from src.plugin_system.core.adapter_manager import get_adapter_manager

            adapter_manager = get_adapter_manager()
            await adapter_manager.start_all_adapters()
            logger.debug("所有适配器已启动")
        except Exception as e:
            logger.error(f"启动适配器失败: {e}")

        # 启动内存监控
        try:
            if MEM_MONITOR_ENABLED:
                started = start_background_monitor(interval_sec=600)
                if started:
                    logger.debug("[DEV] 内存监控已启动 (间隔=600s ≈ 10min)")
        except Exception as e:
            logger.error(f"启动内存监控失败: {e}")

        # ✅ 启动缓存清理后台任务（修复缓存泄漏）
        try:
            from src.common.cache_manager import tool_cache

            async def cache_cleanup_loop():
                """缓存清理循环（每10分钟清理一次过期条目）"""
                while True:
                    try:
                        await asyncio.sleep(600)  # 10分钟
                        await tool_cache.clean_expired()
                        logger.debug("🧹 缓存清理任务已执行")
                    except Exception as e:
                        logger.error(f"缓存清理失败: {e}")

            # 创建后台任务
            cleanup_task = asyncio.create_task(cache_cleanup_loop())
            _background_tasks.add(cleanup_task)
            cleanup_task.add_done_callback(_background_tasks.discard)
            logger.info("✅ 缓存清理后台任务已启动（间隔: 10分钟）")
        except Exception as e:
            logger.error(f"启动缓存清理任务失败: {e}")

    async def _init_planning_components(self) -> None:
        """初始化计划相关组件"""
        # 初始化月度计划管理器
        if global_config and global_config.planning_system and global_config.planning_system.monthly_plan_enable:
            try:
                await monthly_plan_manager.start_monthly_plan_generation()
                logger.debug("月度计划管理器初始化成功")
            except Exception as e:
                logger.error(f"月度计划管理器初始化失败: {e}")

        # 初始化日程管理器
        if global_config and global_config.planning_system and global_config.planning_system.schedule_enable:
            try:
                await schedule_manager.load_or_generate_today_schedule()
                await schedule_manager.start_daily_schedule_generation()
                logger.debug("日程表管理器初始化成功")
            except Exception as e:
                logger.error(f"日程表管理器初始化失败: {e}")

    def _safe_init(self, component_name: str, init_func) -> "Callable[[], Coroutine[Any, Any, bool]]":
        """安全初始化组件，捕获异常"""

        async def wrapper():
            try:
                result = init_func()
                if asyncio.iscoroutine(result):
                    await result
                logger.debug(f"{component_name}初始化成功")
                return True
            except Exception as e:
                logger.error(f"{component_name}初始化失败: {e}")
                return False

        return wrapper

    async def schedule_tasks(self) -> None:
        """调度定时任务"""
        try:
            while not self._shutting_down:
                try:
                    tasks = [
                        get_emoji_manager().start_periodic_check_register(),
                        self.server.run(),
                    ]

                    # 使用 return_exceptions=True 防止单个任务失败导致整个程序崩溃
                    await asyncio.gather(*tasks, return_exceptions=True)

                except (ConnectionResetError, OSError) as e:
                    if self._shutting_down:
                        break
                    logger.warning(f"网络连接发生错误，尝试重新启动任务: {e}")
                    await asyncio.sleep(1)
                except asyncio.InvalidStateError as e:
                    if self._shutting_down:
                        break
                    logger.error(f"异步任务状态无效，重新初始化: {e}")
                    await asyncio.sleep(2)
                except Exception as e:
                    if self._shutting_down:
                        break
                    logger.error(f"调度任务发生未预期异常: {e}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("调度任务被取消，正在退出...")
        except Exception as e:
            logger.error(f"调度任务发生致命异常: {e}")
            logger.error(traceback.format_exc())
            raise

    async def shutdown(self) -> None:
        """关闭系统组件"""
        if self._cleanup_started:
            return

        logger.info("正在关闭MainSystem...")
        await self._async_cleanup()
        logger.info("MainSystem关闭完成")


async def main() -> None:
    """主函数"""
    system = MainSystem()
    try:
        await system.initialize()
        await system.schedule_tasks()
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
    except Exception as e:
        logger.error(f"主函数执行失败: {e}")
        logger.error(traceback.format_exc())
    finally:
        await system.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
