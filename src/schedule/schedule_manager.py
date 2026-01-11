import asyncio
from datetime import datetime, time, timedelta
from typing import Any

import orjson
from sqlalchemy import select

from src.common.database.core import get_db_session
from src.common.database.core.models import MonthlyPlan, Schedule
from src.common.logger import get_logger
from src.config.config import global_config
from src.manager.async_task_manager import AsyncTask, async_task_manager

from .database import update_plan_usage
from .llm_generator import ScheduleLLMGenerator
from .plan_manager import PlanManager
from .schemas import ScheduleData

logger = get_logger("schedule_manager")


class ScheduleManager:
    """
    负责管理每日日程的核心类。
    它处理日程的加载、生成、保存以及提供当前活动查询等功能。
    """

    def __init__(self):
        """
        初始化 ScheduleManager。
        """
        self.today_schedule: list[dict[str, Any]] | None = None  # 存储当天的日程数据
        self.llm_generator = ScheduleLLMGenerator()  # 用于生成日程的LLM生成器实例
        self.plan_manager = PlanManager()  # 月度计划管理器实例
        self.daily_task_started = False  # 标记每日自动生成任务是否已启动
        self.schedule_generation_running = False  # 标记当前是否有日程生成任务正在运行，防止重复执行
        self.daily_task_handle: asyncio.Task | None = None  # 存储每日日程生成任务的句柄

    async def initialize(self):
        """
        异步初始化日程管理器。
        如果日程功能已启用，则会加载或生成当天的日程，并启动每日自动生成任务。
        """
        if global_config.planning_system.schedule_enable:
            logger.info("日程表功能已启用，正在初始化管理器...")
            await self.load_or_generate_today_schedule()
            await self.start_daily_schedule_generation()
            logger.info("日程表管理器初始化成功。")

    async def start_daily_schedule_generation(self):
        """
        启动一个后台任务，该任务会在每天零点自动生成第二天的日程。
        """
        if not self.daily_task_started:
            logger.info("正在启动每日日程生成任务...")
            task = DailyScheduleGenerationTask(self)
            await async_task_manager.add_task(task)
            self.daily_task_started = True
            logger.info("每日日程生成任务已成功启动。")
        else:
            logger.info("每日日程生成任务已在运行中。")

    async def shutdown(self):
        """
        优雅地关闭日程管理器。
        确保所有进行中的任务被正常取消，而不是被强制中断。
        """
        if self.daily_task_started:
            logger.info("正在完整地关闭ScheduleManager任务...")
            try:
                # 等待最可能需要的一些无法立即取消的任务
                await asyncio.sleep(0.1)
                logger.info("日程管理器任务已结束。")
            except Exception as e:
                logger.error(f"关闭日程管理器时发生了错误: {e}")

    async def load_or_generate_today_schedule(self):
        """
        加载或生成当天的日程。
        首先尝试从数据库加载，如果失败或不存在，则调用LLM生成新的日程。
        """
        if not global_config.planning_system.schedule_enable:
            logger.info("日程管理功能已禁用，跳过日程加载和生成。")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            # 尝试从数据库加载日程
            schedule_data = await self._load_schedule_from_db(today_str)
            if schedule_data:
                self.today_schedule = schedule_data
                self._log_loaded_schedule(today_str)
                return

            # 如果数据库中没有，则生成新的日程
            logger.info(f"数据库中未找到今天的日程 ({today_str})，将调用 LLM 生成。")
            await self.generate_and_save_schedule()

        except Exception as e:
            # 如果加载过程中出现任何异常，则尝试生成日程作为备用方案
            logger.error(f"加载或生成日程时出错: {e}")
            logger.info("尝试生成日程作为备用方案...")
            await self.generate_and_save_schedule()

    async def _load_schedule_from_db(self, date_str: str) -> list[dict[str, Any]] | None:
        """
        从数据库中加载指定日期的日程。

        Args:
            date_str (str): 日期字符串，格式为 "YYYY-MM-DD"。

        Returns:
            list[dict[str, Any]] | None: 如果找到并验证成功，则返回日程数据，否则返回 None。
        """
        async with get_db_session() as session:
            result = await session.execute(select(Schedule).filter(Schedule.date == date_str))
            schedule_record = result.scalars().first()
            if schedule_record:
                logger.info(f"从数据库加载今天的日程 ({date_str})。")
                schedule_data = orjson.loads(str(schedule_record.schedule_data))
                # 验证数据格式是否符合 Pydantic 模型
                if self._validate_schedule_with_pydantic(schedule_data):
                    return schedule_data
                else:
                    logger.warning("数据库中的日程数据格式无效，将重新生成日程")
        return None

    def _log_loaded_schedule(self, date_str: str):
        """
        记录已成功加载的日程信息。

        Args:
            date_str (str): 日期字符串。
        """
        schedule_str = f"已成功加载今天的日程 ({date_str})：\n"
        if self.today_schedule:
            for item in self.today_schedule:
                schedule_str += f"  - {item.get('time_range', '未知时间')}: {item.get('activity', '未知活动')}\n"
        logger.info(schedule_str)

    async def generate_and_save_schedule(self):
        """
        提交一个按需生成的后台任务来创建和保存日程。
        这种设计可以防止在主流程中长时间等待LLM响应。
        """
        if self.schedule_generation_running:
            logger.info("日程生成任务已在运行中，跳过重复启动")
            return
        logger.info("检测到需要生成日程，已提交后台任务。")
        task = OnDemandScheduleGenerationTask(self)
        await async_task_manager.add_task(task)

    async def _async_generate_and_save_schedule(self):
        """
        实际执行日程生成和保存的异步方法。
        这个方法由后台任务调用。
        """
        self.schedule_generation_running = True
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            current_month_str = datetime.now().strftime("%Y-%m")

            # 如果启用了月度计划，则获取一些计划作为生成日程的参考
            sampled_plans = []
            if global_config.planning_system.monthly_plan_enable:
                await self.plan_manager.ensure_and_generate_plans_if_needed(current_month_str)
                sampled_plans = await self.plan_manager.get_plans_for_schedule(current_month_str, max_count=3)

            # 调用LLM生成日程数据
            schedule_data = await self.llm_generator.generate_schedule_with_llm(sampled_plans)

            if schedule_data:
                # 保存到数据库
                await self._save_schedule_to_db(today_str, schedule_data)
                self.today_schedule = schedule_data
                self._log_generated_schedule(today_str, schedule_data, sampled_plans)

                # 如果参考了月度计划，则更新这些计划的使用情况
                if sampled_plans:
                    used_plan_ids = [plan.id for plan in sampled_plans]
                    logger.info(f"更新使用过的月度计划 {used_plan_ids} 的统计信息。")
                    await update_plan_usage(used_plan_ids, today_str)
        finally:
            self.schedule_generation_running = False
            logger.info("日程生成任务结束")

    @staticmethod
    async def _save_schedule_to_db(date_str: str, schedule_data: list[dict[str, Any]]):
        """
        将日程数据保存到数据库。如果已有记录则更新，否则创建新记录。

        Args:
            date_str (str): 日期字符串。
            schedule_data (list[dict[str, Any]]): 日程数据。
        """
        async with get_db_session() as session:
            schedule_json = orjson.dumps(schedule_data).decode("utf-8")
            # 查找是否已存在当天的日程记录
            result = await session.execute(select(Schedule).filter(Schedule.date == date_str))
            existing_schedule = result.scalars().first()
            if existing_schedule:
                # 更新现有记录
                existing_schedule.schedule_data = schedule_json
                existing_schedule.updated_at = datetime.now()
            else:
                # 创建新记录
                new_schedule = Schedule(date=date_str, schedule_data=schedule_json)
                session.add(new_schedule)
            await session.commit()

    @staticmethod
    def _log_generated_schedule(
        date_str: str, schedule_data: list[dict[str, Any]], sampled_plans: list[MonthlyPlan]
    ):
        """
        记录成功生成并保存的日程信息。

        Args:
            date_str (str): 日期字符串。
            schedule_data (list[dict[str, Any]]): 日程数据。
            sampled_plans (list[MonthlyPlan]]): 用于生成日程的参考月度计划。
        """
        schedule_str = f"成功生成并保存今天的日程 ({date_str})：\n"

        if sampled_plans:
            plan_texts = "\n".join([f"  - {plan.plan_text}" for plan in sampled_plans])
            schedule_str += f"本次日程参考的月度计划:\n{plan_texts}\n"

        schedule_str += "今日日程详情:\n"
        for item in schedule_data:
            schedule_str += f"  - {item.get('time_range', '未知时间')}: {item.get('activity', '未知活动')}\n"
        logger.info(schedule_str)

    def get_current_activity(self) -> dict[str, Any] | None:
        """
        根据当前时间从日程表中获取正在进行的活动。

        Returns:
            dict[str, Any] | None: 如果找到当前活动，则返回包含活动和时间范围的字典，否则返回 None。
        """
        if not global_config.planning_system.schedule_enable or not self.today_schedule:
            return None
        now = datetime.now().time()
        for event in self.today_schedule:
            try:
                time_range = event.get("time_range")
                activity = event.get("activity")
                if not time_range or not activity:
                    continue
                # 解析时间范围
                start_str, end_str = time_range.split("-")
                start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
                end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
                # 判断当前时间是否在时间范围内（支持跨天的时间范围，如 23:00-01:00）
                if (start_time <= now < end_time) or (end_time < start_time and (now >= start_time or now < end_time)):
                    return {"activity": activity, "time_range": time_range}
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f"解析日程事件失败: {event}, 错误: {e}")
        return None

    @staticmethod
    def _validate_schedule_with_pydantic(schedule_data) -> bool:
        """
        使用 Pydantic 模型验证日程数据的格式和内容是否正确。

        Args:
            schedule_data: 待验证的日程数据。

        Returns:
            bool: 如果验证通过则返回 True，否则返回 False。
        """
        try:
            ScheduleData(schedule=schedule_data)
            return True
        except Exception:
            return False


class OnDemandScheduleGenerationTask(AsyncTask):
    """
    一个按需执行的后台任务，用于生成当天的日程。
    当启动时未找到日程或加载失败时触发。
    """
    def __init__(self, schedule_manager: "ScheduleManager"):
        """
        初始化按需日程生成任务。

        Args:
            schedule_manager (ScheduleManager): ScheduleManager 的实例。
        """
        task_name = f"OnDemandScheduleGenerationTask-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        super().__init__(task_name=task_name)
        self.schedule_manager = schedule_manager

    async def run(self):
        """
        任务的执行体，调用 ScheduleManager 中的核心生成逻辑。
        """
        logger.info(f"后台任务 {self.task_name} 开始执行日程生成。")
        try:
            await self.schedule_manager._async_generate_and_save_schedule()
            logger.info(f"后台任务 {self.task_name} 完成。")
        except asyncio.CancelledError:
            logger.warning(f"后台任务 {self.task_name} 被中止。")
            raise
        except Exception as e:
            logger.error(f"后台任务 {self.task_name} 执行时发生了错误: {e}")
            raise


class DailyScheduleGenerationTask(AsyncTask):
    """
    一个周期性执行的后台任务，用于在每天零点自动生成新一天的日程。
    """
    def __init__(self, schedule_manager: "ScheduleManager"):
        """
        初始化每日日程生成任务。

        Args:
            schedule_manager (ScheduleManager): ScheduleManager 的实例。
        """
        super().__init__(task_name="DailyScheduleGenerationTask")
        self.schedule_manager = schedule_manager

    async def run(self):
        """
        任务的执行体，无限循环直到被取消。
        计算到下一个零点的时间并休眠，然后在零点过后触发日程生成。
        """
        while True:
            try:
                now = datetime.now()
                # 计算下一个零点的时间
                tomorrow = now.date() + timedelta(days=1)
                midnight = datetime.combine(tomorrow, time.min)
                sleep_seconds = (midnight - now).total_seconds()
                logger.info(
                    f"下一次日程生成任务将在 {sleep_seconds:.2f} 秒后运行 (北京时间 {midnight.strftime('%Y-%m-%d %H:%M:%S')})"
                )
                try:
                    await asyncio.sleep(sleep_seconds)
                except asyncio.CancelledError:
                    logger.info("每日日程生成任务被取消。")
                    raise
                # 到达零点，开始生成
                logger.info("到达每日零点，开始生成新的一天日程...")
                try:
                    await self.schedule_manager._async_generate_and_save_schedule()
                except asyncio.CancelledError:
                    logger.warning("日程生成被中止。")
                    raise
            except asyncio.CancelledError:
                logger.info("每日日程生成任务被取消。")
                break
            except Exception as e:
                # 发生未知错误时，记录日志并短暂休眠后重试，避免任务崩溃
                logger.error(f"每日日程生成任务发生未知错误: {e}")
                await asyncio.sleep(300)


# 创建 ScheduleManager 的单例
schedule_manager = ScheduleManager()
