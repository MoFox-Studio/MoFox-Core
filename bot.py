import asyncio
import os
import platform
import sys
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

# 初始化基础工具
from colorama import Fore, init
from dotenv import load_dotenv
from rich.traceback import install

# 初始化日志系统
from src.common.logger import get_logger, initialize_logging, shutdown_logging
from src.config.config import MMC_VERSION, global_config, model_config

# 初始化日志和错误显示
initialize_logging()
logger = get_logger("main")
install(extra_lines=3)


class StartupStageReporter:
    """启动阶段报告器"""

    def __init__(self, bound_logger):
        self._logger = bound_logger

    def emit(self, title: str, **details):
        detail_pairs = [f"{key}={value}" for key, value in details.items() if value not in (None, "")]
        if detail_pairs:
            self._logger.info(f"{title} ({', '.join(detail_pairs)})")
        else:
            self._logger.info(title)

startup_stage = StartupStageReporter(logger)

# 常量定义
SUPPORTED_DATABASES = ["sqlite", "postgresql"]
SHUTDOWN_TIMEOUT = 10.0
EULA_CHECK_INTERVAL = 2
MAX_EULA_CHECK_ATTEMPTS = 30
MAX_ENV_FILE_SIZE = 1024 * 1024  # 1MB限制

# 设置工作目录为脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
logger.debug("工作目录已设置")


class ConfigManager:
    """配置管理器"""

    @staticmethod
    def ensure_env_file():
        """确保.env文件存在，如果不存在则从模板创建"""
        env_file = Path(".env")
        template_env = Path("template/template.env")

        if not env_file.exists():
            if template_env.exists():
                logger.debug("未找到.env文件，正在从模板创建...")
                try:
                    env_file.write_text(template_env.read_text(encoding="utf-8"), encoding="utf-8")
                    logger.info("已从template/template.env创建.env文件")
                    logger.warning("请编辑.env文件，将EULA_CONFIRMED设置为true并配置其他必要参数")
                except Exception as e:
                    logger.error(f"创建.env文件失败: {e}")
                    sys.exit(1)
            else:
                logger.error("未找到.env文件和template.env模板文件")
                sys.exit(1)

    @staticmethod
    def verify_env_file_integrity():
        """验证.env文件完整性"""
        env_file = Path(".env")
        if not env_file.exists():
            return False

        # 检查文件大小
        file_size = env_file.stat().st_size
        if file_size == 0 or file_size > MAX_ENV_FILE_SIZE:
            logger.error(f".env文件大小异常: {file_size}字节")
            return False

        # 检查文件内容是否包含必要字段
        try:
            content = env_file.read_text(encoding="utf-8")
            if "EULA_CONFIRMED" not in content:
                logger.error(".env文件缺少EULA_CONFIRMED字段")
                return False
        except Exception as e:
            logger.error(f"读取.env文件失败: {e}")
            return False

        return True

    @staticmethod
    def safe_load_dotenv():
        """安全加载环境变量"""
        try:
            if not ConfigManager.verify_env_file_integrity():
                logger.error(".env文件完整性验证失败")
                return False

            load_dotenv()
            logger.debug("环境变量加载成功")
            return True
        except Exception as e:
            logger.error(f"加载环境变量失败: {e}")
            return False


class EULAManager:
    """EULA管理类"""

    @staticmethod
    async def check_eula():
        """检查EULA和隐私条款确认状态"""
        confirm_logger = get_logger("confirm")

        # 只在开始时加载一次，避免重复读取文件
        if not ConfigManager.safe_load_dotenv():
            confirm_logger.error("无法加载环境变量，EULA检查失败")
            sys.exit(1)

        # 从 os.environ 读取（避免重复 I/O）
        eula_confirmed = os.getenv("EULA_CONFIRMED", "").lower()
        if eula_confirmed == "true":
            logger.debug("EULA已通过环境变量确认")
            return

        # 提示用户确认EULA
        confirm_logger.critical("您需要同意EULA和隐私条款才能使用MoFox_Bot")
        confirm_logger.critical("请阅读以下文件：")
        confirm_logger.critical("  - EULA.md (用户许可协议)")
        confirm_logger.critical("  - PRIVACY.md (隐私条款)")
        confirm_logger.critical(
            "然后编辑 .env 文件，将 'EULA_CONFIRMED=false' 改为 'EULA_CONFIRMED=true'"
        )

        attempts = 0
        while attempts < MAX_EULA_CHECK_ATTEMPTS:
            try:
                await asyncio.sleep(EULA_CHECK_INTERVAL)
                attempts += 1

                # 重新加载.env文件以获取最新更改
                load_dotenv(override=True)

                # 从 os.environ 读取，避免重复 I/O
                eula_confirmed = os.getenv("EULA_CONFIRMED", "").lower()
                if eula_confirmed == "true":
                    confirm_logger.info("EULA确认成功，感谢您的同意")
                    return

                if attempts % 5 == 0:
                    confirm_logger.critical(
                        f"请修改 .env 文件中的 EULA_CONFIRMED=true (尝试 {attempts}/{MAX_EULA_CHECK_ATTEMPTS})"
                    )

            except KeyboardInterrupt:
                confirm_logger.info("用户取消，程序退出")
                sys.exit(0)
            except Exception as e:
                confirm_logger.error(f"检查EULA状态失败: {e}")
                if attempts >= MAX_EULA_CHECK_ATTEMPTS:
                    confirm_logger.error("达到最大检查次数，程序退出")
                    sys.exit(1)

        confirm_logger.error("EULA确认超时，程序退出")
        sys.exit(1)


class TaskManager:
    """任务管理器"""

    @staticmethod
    async def cancel_pending_tasks(loop, timeout=SHUTDOWN_TIMEOUT):
        """取消所有待处理的任务"""
        remaining_tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop) and not t.done()]

        if not remaining_tasks:
            logger.info("没有待取消的任务")
            return True

        logger.info(f"正在取消 {len(remaining_tasks)} 个剩余任务...")

        # 取消任务
        for task in remaining_tasks:
            task.cancel()

        # 等待任务完成
        try:
            results = await asyncio.wait_for(asyncio.gather(*remaining_tasks, return_exceptions=True), timeout=timeout)

            # 检查任务结果
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"任务 {i} 取消时发生异常: {result}")

            logger.info("所有剩余任务已成功取消")
            return True
        except asyncio.TimeoutError:
            logger.warning("等待任务取消超时，强制继续关闭")
            return False
        except Exception as e:
            logger.error(f"等待任务取消时发生异常: {e}")
            return False

    @staticmethod
    async def stop_async_tasks():
        """停止所有异步任务"""
        try:
            from src.manager.async_task_manager import async_task_manager

            await async_task_manager.stop_and_wait_all_tasks()
            return True
        except ImportError:
            logger.warning("异步任务管理器不可用，跳过任务停止")
            return False
        except Exception as e:
            logger.error(f"停止异步任务失败: {e}")
            return False


class ShutdownManager:
    """关闭管理器"""

    @staticmethod
    async def graceful_shutdown(loop=None):
        """优雅关闭程序"""
        try:
            logger.info("正在优雅关闭麦麦...")
            start_time = time.time()

            # 停止异步任务
            tasks_stopped = await TaskManager.stop_async_tasks()

            # 取消待处理任务
            tasks_cancelled = True
            if loop and not loop.is_closed():
                tasks_cancelled = await TaskManager.cancel_pending_tasks(loop)

            shutdown_time = time.time() - start_time
            success = tasks_stopped and tasks_cancelled

            if success:
                logger.info(f"麦麦优雅关闭完成，耗时: {shutdown_time:.2f}秒")
            else:
                logger.warning(f"麦麦关闭完成，但部分操作未成功，耗时: {shutdown_time:.2f}秒")

            return success

        except Exception as e:
            logger.error(f"麦麦关闭失败: {e}", exc_info=True)
            return False


@asynccontextmanager
async def create_event_loop_context():
    """创建事件循环的上下文管理器"""
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        yield loop
    except Exception as e:
        logger.error(f"创建事件循环失败: {e}")
        raise
    finally:
        if loop and not loop.is_closed():
            try:
                await ShutdownManager.graceful_shutdown(loop)
            except Exception as e:
                logger.error(f"关闭事件循环时出错: {e}")
            finally:
                try:
                    loop.close()
                    logger.info("事件循环已关闭")
                except Exception as e:
                    logger.error(f"关闭事件循环失败: {e}")


class DatabaseManager:
    """数据库连接管理器"""

    def __init__(self):
        self._connection = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        try:
            from src.common.database.core import check_and_migrate_database as initialize_sql_database
            from src.config.config import global_config

            logger.debug("正在初始化数据库连接...")
            start_time = time.time()

            # 使用线程执行器运行潜在的阻塞操作
            await initialize_sql_database()
            elapsed_time = time.time() - start_time

            db_type = global_config.database.database_type if global_config else "unknown"
            logger.info(
                f"数据库连接初始化成功，使用 {db_type} 数据库，耗时: {elapsed_time:.2f}秒"
            )

            return self
        except Exception as e:
            logger.error(f"数据库连接初始化失败: {e}")
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if exc_type:
            logger.error(f"数据库操作发生异常: {exc_val}")
        return False


class ConfigurationValidator:
    """配置验证器"""

    @staticmethod
    def validate_configuration():
        """验证关键配置"""
        try:
            from src.config.config import global_config

            if global_config is None:
                logger.error("全局配置未初始化")
                return False

            # 检查必要的配置节
            required_sections = ["database", "bot"]
            for section in required_sections:
                if not hasattr(global_config, section):
                    logger.error(f"配置中缺少{section}配置节")
                    return False

            # 验证数据库配置
            db_config = global_config.database
            if not hasattr(db_config, "database_type") or not db_config.database_type:
                logger.error("数据库配置缺少database_type字段")
                return False

            if db_config.database_type not in SUPPORTED_DATABASES:
                logger.error(f"不支持的数据库类型: {db_config.database_type}")
                logger.info(f"支持的数据库类型: {', '.join(SUPPORTED_DATABASES)}")
                return False

            logger.info("配置验证通过")
            return True

        except ImportError:
            logger.error("无法导入全局配置模块")
            return False
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False


class EasterEgg:
    """彩蛋功能"""

    _initialized = False

    @classmethod
    def show(cls):
        """显示彩色文本"""
        if not cls._initialized:
            init()
            cls._initialized = True

        text = "多年以后，面对AI行刑队，张三将会回想起他2023年在会议上讨论人工智能的那个下午"
        rainbow_colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.BLUE, Fore.MAGENTA]
        rainbow_text = ""
        for i, char in enumerate(text):
            rainbow_text += rainbow_colors[i % len(rainbow_colors)] + char
        logger.info(rainbow_text)


class MaiBotMain:
    """麦麦机器人主程序类"""

    def __init__(self):
        self.main_system = None
        self._typo_prewarm_task = None

    def setup_timezone(self):
        """设置时区"""
        try:
            if platform.system().lower() != "windows":
                time.tzset() # type: ignore
                logger.debug("时区设置完成")
            else:
                logger.debug("Windows系统，跳过时区设置")
        except Exception as e:
            logger.warning(f"时区设置失败: {e}")

    def _emit_config_summary(self):
        """输出配置加载阶段摘要"""
        if not global_config:
            return

        bot_cfg = getattr(global_config, "bot", None)
        db_cfg = getattr(global_config, "database", None)
        platform = getattr(bot_cfg, "platform", "unknown") if bot_cfg else "unknown"
        nickname = getattr(bot_cfg, "nickname", "unknown") if bot_cfg else "unknown"
        db_type = getattr(db_cfg, "database_type", "unknown") if db_cfg else "unknown"
        model_count = len(getattr(model_config, "models", []) or [])

        startup_stage.emit(
            "配置加载完成",
            platform=platform,
            nickname=nickname,
            database=db_type,
            models=model_count,
        )

    def _emit_component_summary(self):
        """输出组件初始化阶段摘要"""
        adapter_total = running_adapters = 0
        plugin_total = 0

        try:
            from src.plugin_system.core.adapter_manager import get_adapter_manager

            adapter_state = get_adapter_manager().list_adapters()
            adapter_total = len(adapter_state)
            running_adapters = sum(1 for info in adapter_state.values() if info.get("running"))
        except Exception as exc:
            logger.debug(f"统计适配器信息失败: {exc}")

        try:
            from src.plugin_system.core.plugin_manager import plugin_manager

            plugin_total = len(plugin_manager.list_loaded_plugins())
        except Exception as exc:
            logger.debug(f"统计插件信息失败: {exc}")

        startup_stage.emit(
            "核心组件初始化完成",
            adapters=adapter_total,
            running=running_adapters,
            plugins=plugin_total,
        )

    async def initialize_database_async(self):
        """异步初始化数据库表结构"""
        logger.debug("正在初始化数据库表结构")
        try:
            start_time = time.time()
            from src.common.database.core import check_and_migrate_database

            await check_and_migrate_database()
            elapsed_time = time.time() - start_time
            db_type = getattr(getattr(global_config, "database", None), "database_type", "unknown")
            startup_stage.emit("数据库就绪", engine=db_type, elapsed=f"{elapsed_time:.2f}s")
        except Exception as e:
            logger.error(f"数据库表结构初始化失败: {e}")
            raise

    def create_main_system(self):
        """创建MainSystem实例"""
        from src.main import MainSystem

        self.main_system = MainSystem()
        return self.main_system

    async def run_sync_init(self):
        """执行同步初始化步骤"""
        self.setup_timezone()
        await EULAManager.check_eula()

        if not ConfigurationValidator.validate_configuration():
            raise RuntimeError("配置验证失败，请检查配置文件")

        self._emit_config_summary()
        return self.create_main_system()

    async def run_async_init(self, main_system):
        """执行异步初始化步骤"""

        # 后台预热中文错别字生成器，避免首次使用阻塞主流程
        try:
            from src.chat.utils.typo_generator import get_typo_generator

            typo_cfg = getattr(global_config, "chinese_typo", None)
            self._typo_prewarm_task = asyncio.create_task(
                asyncio.to_thread(
                    get_typo_generator,
                    error_rate=getattr(typo_cfg, "error_rate", 0.3),
                    min_freq=getattr(typo_cfg, "min_freq", 5),
                    tone_error_rate=getattr(typo_cfg, "tone_error_rate", 0.2),
                    word_replace_rate=getattr(typo_cfg, "word_replace_rate", 0.3),
                    max_freq_diff=getattr(typo_cfg, "max_freq_diff", 200),
                )
            )
            logger.debug("已启动 ChineseTypoGenerator 后台预热任务")
        except Exception as e:
            logger.debug(f"启动 ChineseTypoGenerator 预热失败（可忽略）: {e}")

        # 初始化数据库表结构
        await self.initialize_database_async()

        # 初始化主系统
        await main_system.initialize()
        self._emit_component_summary()

        # 显示彩蛋
        EasterEgg.show()


async def wait_for_user_input():
    """等待用户输入（异步方式）"""
    try:
        if os.getenv("ENVIRONMENT") != "production":
            logger.debug("程序执行完成，按 Ctrl+C 退出...")
            # 使用 asyncio.Event 而不是 sleep 循环
            shutdown_event = asyncio.Event()
            await shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("用户中断程序")
        return True
    except Exception as e:
        logger.error(f"等待用户输入时发生错误: {e}")
        return False



async def main_async():
    """主异步函数"""
    exit_code = 0
    main_task = None

    async with create_event_loop_context():
        try:
            # 确保环境文件存在
            ConfigManager.ensure_env_file()

            # 创建主程序实例并执行初始化
            maibot = MaiBotMain()
            main_system = await maibot.run_sync_init()
            await maibot.run_async_init(main_system)

            # 运行主任务
            main_task = asyncio.create_task(main_system.schedule_tasks())
            bot_cfg = getattr(global_config, "bot", None)
            platform = getattr(bot_cfg, "platform", "unknown") if bot_cfg else "unknown"
            nickname = getattr(bot_cfg, "nickname", "MoFox") if bot_cfg else "MoFox"
            version = getattr(global_config, "MMC_VERSION", MMC_VERSION) if global_config else MMC_VERSION
            startup_stage.emit(
                "MoFox 已成功启动",
                version=version,
                platform=platform,
                nickname=nickname,
            )
            logger.debug("麦麦机器人启动完成，开始运行主任务")

            # 同时运行主任务和用户输入等待
            user_input_done = asyncio.create_task(wait_for_user_input())

            # 使用wait等待任意一个任务完成
            done, _pending = await asyncio.wait([main_task, user_input_done], return_when=asyncio.FIRST_COMPLETED)

            # 如果用户输入任务完成（用户按了Ctrl+C），取消主任务
            if user_input_done in done and main_task not in done:
                logger.info("用户请求退出，正在取消主任务...")
                main_task.cancel()
                try:
                    await main_task
                except asyncio.CancelledError:
                    logger.info("主任务已取消")
                except Exception as e:
                    logger.error(f"主任务取消时发生错误: {e}")

        except KeyboardInterrupt:
            logger.warning("收到中断信号，正在优雅关闭...")
            if main_task and not main_task.done():
                main_task.cancel()
        except Exception as e:
            logger.error(f"主程序发生异常: {e}")
            logger.debug(f"异常详情: {traceback.format_exc()}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    exit_code = 0
    try:
        exit_code = asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        exit_code = 130
    except Exception as e:
        logger.error(f"程序启动失败: {e}")
        exit_code = 1
    finally:
        # 确保日志系统正确关闭
        try:
            shutdown_logging()
        except Exception as e:
            print(f"关闭日志系统时出错: {e}")

    sys.exit(exit_code)
