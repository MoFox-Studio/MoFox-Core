"""
Kokoro Flow Chatter - 主动思考器

独立组件，负责：
1. 等待期间的连续思考（更新心理状态）
2. 等待超时决策（继续等 or 做点什么）
3. 长期沉默后主动发起对话

通过 UnifiedScheduler 定期触发，与 Chatter 解耦

支持两种工作模式（与 Chatter 保持一致）：
- unified: 单次 LLM 调用完成思考和回复
- split: Planner + Replyer 两次 LLM 调用
"""

import asyncio
import random
import time
from datetime import datetime
from typing import TYPE_CHECKING

from src.chat.planner_actions.action_manager import ChatterActionManager
from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.apis.unified_scheduler import TriggerType, unified_scheduler

from .config import KFCMode, apply_wait_duration_rules, get_config
from .models import EventType, SessionStatus
from .session import KokoroSession, get_session_manager

if TYPE_CHECKING:
    pass

logger = get_logger("kfc_proactive_thinker")


class ProactiveThinker:
    """
    主动思考器

    独立于 Chatter，负责处理：
    1. 等待期间的连续思考
    2. 等待超时
    3. 长期沉默后主动发起

    核心逻辑：
    - 定期检查所有 WAITING 状态的 Session
    - 触发连续思考或超时决策
    - 定期检查长期沉默的 Session，考虑主动发起

    支持两种工作模式（与 Chatter 保持一致）：
    - unified: 单次 LLM 调用
    - split: Planner + Replyer 两次调用
    """

    # 连续思考触发点（等待进度百分比）
    THINKING_TRIGGERS = [0.3, 0.6, 0.85]

    # 任务名称
    TASK_WAITING_CHECK = "kfc_waiting_check"
    TASK_PROACTIVE_CHECK = "kfc_proactive_check"

    def __init__(self):
        self.session_manager = get_session_manager()

        # 配置
        self._load_config()

        # 调度任务 ID
        self._waiting_schedule_id: str | None = None
        self._proactive_schedule_id: str | None = None
        self._running = False

        # 统计
        self._stats = {
            "waiting_checks": 0,
            "continuous_thinking_triggered": 0,
            "timeout_decisions": 0,
            "proactive_triggered": 0,
        }

    def _load_config(self) -> None:
        """加载配置 - 使用统一的配置系统"""
        config = get_config()
        proactive_cfg = config.proactive
        self._waiting_cfg = config.waiting

        # 工作模式
        self._mode = config.mode

        # 等待检查间隔（秒）
        self.waiting_check_interval = 15.0
        # 主动思考检查间隔（秒）
        self.proactive_check_interval = 300.0

        # 从配置读取主动思考相关设置
        self.proactive_enabled = proactive_cfg.enabled
        self.silence_threshold = proactive_cfg.silence_threshold_seconds
        self.min_proactive_interval = proactive_cfg.min_interval_between_proactive
        self.quiet_hours_start = proactive_cfg.quiet_hours_start
        self.quiet_hours_end = proactive_cfg.quiet_hours_end
        self.trigger_probability = proactive_cfg.trigger_probability
        self.min_affinity_for_proactive = proactive_cfg.min_affinity_for_proactive

    async def start(self) -> None:
        """启动主动思考器"""
        if self._running:
            logger.info("已在运行中")
            return

        self._running = True

        # 注册等待检查任务（始终启用，用于处理等待中的 Session）
        self._waiting_schedule_id = await unified_scheduler.create_schedule(
            callback=self._check_waiting_sessions,
            trigger_type=TriggerType.TIME,
            trigger_config={"delay_seconds": self.waiting_check_interval},
            is_recurring=True,
            task_name=self.TASK_WAITING_CHECK,
            force_overwrite=True,
            timeout=60.0,
        )

        # 注册主动思考检查任务（仅在启用时注册）
        if self.proactive_enabled:
            self._proactive_schedule_id = await unified_scheduler.create_schedule(
                callback=self._check_proactive_sessions,
                trigger_type=TriggerType.TIME,
                trigger_config={"delay_seconds": self.proactive_check_interval},
                is_recurring=True,
                task_name=self.TASK_PROACTIVE_CHECK,
                force_overwrite=True,
                timeout=120.0,
            )
            logger.info("[ProactiveThinker] 已启动（主动思考已启用）")
        else:
            logger.info("[ProactiveThinker] 已启动（主动思考已禁用）")

    async def stop(self) -> None:
        """停止主动思考器"""
        if not self._running:
            return

        self._running = False

        if self._waiting_schedule_id:
            await unified_scheduler.remove_schedule(self._waiting_schedule_id)
        if self._proactive_schedule_id:
            await unified_scheduler.remove_schedule(self._proactive_schedule_id)

        logger.info("[ProactiveThinker] 已停止")

    # ========================
    # 等待检查
    # ========================

    async def _check_waiting_sessions(self) -> None:
        """检查所有等待中的 Session"""
        self._stats["waiting_checks"] += 1

        sessions = await self.session_manager.get_waiting_sessions()
        if not sessions:
            return

        # 并行处理
        tasks = [
            asyncio.create_task(self._process_waiting_session(s))
            for s in sessions
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_waiting_session(self, session: KokoroSession) -> None:
        """处理单个等待中的 Session"""
        try:
            if session.status != SessionStatus.WAITING:
                return

            if not session.waiting_config.is_active():
                return

            # 防止与 Chatter 并发处理：如果 Session 刚刚被更新（5秒内），跳过
            # 这样可以避免 Chatter 正在处理时，ProactiveThinker 也开始处理
            time_since_last_activity = time.time() - session.last_activity_at
            if time_since_last_activity < 5:
                logger.debug(
                    f"[ProactiveThinker] Session {session.user_id} 刚有活动 "
                    f"({time_since_last_activity:.1f}s ago)，跳过处理"
                )
                return

            # 检查是否超时
            if session.waiting_config.is_timeout():
                await self._handle_timeout(session)
                return

            # 检查是否需要触发连续思考
            progress = session.waiting_config.get_progress()
            if self._should_trigger_thinking(session, progress):
                await self._handle_continuous_thinking(session, progress)

        except Exception as e:
            logger.error(f"[ProactiveThinker] 处理等待 Session 失败 {session.user_id}: {e}")

    def _should_trigger_thinking(self, session: KokoroSession, progress: float) -> bool:
        """判断是否应触发连续思考"""
        # 计算应该触发的次数
        expected_count = sum(1 for t in self.THINKING_TRIGGERS if progress >= t)

        if session.waiting_config.thinking_count >= expected_count:
            return False

        # 确保两次思考之间有间隔
        if session.waiting_config.last_thinking_at > 0:
            elapsed = time.time() - session.waiting_config.last_thinking_at
            if elapsed < 30:  # 至少 30 秒间隔
                return False

        return True

    async def _handle_continuous_thinking(
        self,
        session: KokoroSession,
        progress: float,
    ) -> None:
        """处理连续思考"""
        self._stats["continuous_thinking_triggered"] += 1

        # 获取用户名
        user_name = await self._get_user_name(session.user_id, session.stream_id)

        # 调用 LLM 生成等待中的想法
        thought = await self._generate_waiting_thought(session, user_name, progress)

        # 记录到 mental_log
        session.add_waiting_update(
            waiting_thought=thought,
            mood="",  # 心情已融入 thought 中
        )

        # 更新思考计数
        session.waiting_config.thinking_count += 1
        session.waiting_config.last_thinking_at = time.time()

        # 保存
        await self.session_manager.save_session(session.user_id)

        logger.debug(
            f"[ProactiveThinker] 连续思考: user={session.user_id}, "
            f"progress={progress:.1%}, thought={thought[:30]}..."
        )

    async def _generate_waiting_thought(
        self,
        session: KokoroSession,
        user_name: str,
        progress: float,
    ) -> str:
        """调用 LLM 生成等待中的想法"""
        try:
            from src.chat.utils.prompt import global_prompt_manager
            from src.plugin_system.apis import llm_api

            from .prompt.builder import get_prompt_builder
            from .prompt.prompts import PROMPT_NAMES

            # 使用 PromptBuilder 构建人设块
            prompt_builder = get_prompt_builder()
            persona_block = prompt_builder._build_persona_block()

            # 获取关系信息
            relation_block = f"你与 {user_name} 还不太熟悉。"
            try:
                from src.person_info.relationship_manager import relationship_manager

                person_info_manager = await self._get_person_info_manager()
                if person_info_manager:
                    platform = global_config.bot.platform if global_config else "qq"
                    person_id = person_info_manager.get_person_id(platform, session.user_id)
                    relationship = await relationship_manager.get_relationship(person_id)
                    if relationship:
                        relation_block = f"你与 {user_name} 的亲密度是 {relationship.intimacy}。{relationship.description or ''}"
            except Exception as e:
                logger.debug(f"获取关系信息失败: {e}")

            # 获取上次发送的消息
            last_bot_message = "（未知）"
            for entry in reversed(session.mental_log):
                if entry.event_type == EventType.BOT_PLANNING and entry.actions:
                    for action in entry.actions:
                        if action.get("type") == "kfc_reply":
                            content = action.get("content", "")
                            if content:
                                last_bot_message = content[:100] + ("..." if len(content) > 100 else "")
                                break
                    if last_bot_message != "（未知）":
                        break

            # 构建提示词
            elapsed_minutes = session.waiting_config.get_elapsed_minutes()
            max_wait_minutes = session.waiting_config.max_wait_seconds / 60
            expected_reaction = session.waiting_config.expected_reaction or "对方能回复点什么"

            prompt = await global_prompt_manager.format_prompt(
                PROMPT_NAMES["waiting_thought"],
                persona_block=persona_block,
                user_name=user_name,
                relation_block=relation_block,
                last_bot_message=last_bot_message,
                expected_reaction=expected_reaction,
                elapsed_minutes=elapsed_minutes,
                max_wait_minutes=max_wait_minutes,
                progress_percent=int(progress * 100),
            )

            # 调用情绪模型
            models = llm_api.get_available_models()
            emotion_config = models.get("emotion") or models.get("replyer")

            if not emotion_config:
                logger.warning("[ProactiveThinker] 未找到 emotion/replyer 模型配置，使用默认想法")
                return self._get_fallback_thought(elapsed_minutes, progress)

            success, raw_response, _, model_name = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=emotion_config,
                request_type="kokoro_flow_chatter.waiting_thought",
            )

            if not success or not raw_response:
                logger.warning(f"[ProactiveThinker] LLM 调用失败: {raw_response}")
                return self._get_fallback_thought(elapsed_minutes, progress)

            # 使用统一的文本清理函数
            from .replyer import _clean_reply_text
            thought = _clean_reply_text(raw_response)

            logger.debug(f"[ProactiveThinker] LLM 生成等待想法 (model={model_name}): {thought[:50]}...")
            return thought

        except Exception as e:
            logger.error(f"[ProactiveThinker] 生成等待想法失败: {e}")
            import traceback
            traceback.print_exc()
            return self._get_fallback_thought(
                session.waiting_config.get_elapsed_minutes(),
                progress
            )

    def _get_fallback_thought(self, elapsed_minutes: float, progress: float) -> str:
        """获取备用的等待想法（当 LLM 调用失败时使用）"""
        if progress < 0.4:
            thoughts = [
                f"已经等了 {elapsed_minutes:.0f} 分钟了，对方可能在忙吧...",
                "不知道对方在做什么呢",
                "再等等看吧",
            ]
        elif progress < 0.7:
            thoughts = [
                f"等了 {elapsed_minutes:.0f} 分钟了，有点担心...",
                "对方是不是忘记回复了？",
                "嗯...还是没有消息",
            ]
        else:
            thoughts = [
                f"已经等了 {elapsed_minutes:.0f} 分钟了，感觉有点焦虑",
                "要不要主动说点什么呢...",
                "快到时间了，对方还是没回",
            ]
        return random.choice(thoughts)

    async def _get_person_info_manager(self):
        """获取 person_info_manager"""
        try:
            from src.person_info.person_info import get_person_info_manager
            return get_person_info_manager()
        except Exception:
            return None

    async def _handle_timeout(self, session: KokoroSession) -> None:
        """处理等待超时 - 支持双模式"""
        self._stats["timeout_decisions"] += 1

        # 再次检查 Session 状态，防止在等待过程中被 Chatter 处理
        if session.status != SessionStatus.WAITING:
            logger.debug(f"[ProactiveThinker] Session {session.user_id} 已不在等待状态，跳过超时处理")
            return

        # 再次检查最近活动时间
        time_since_last_activity = time.time() - session.last_activity_at
        if time_since_last_activity < 5:
            logger.debug(
                f"[ProactiveThinker] Session {session.user_id} 刚有活动，跳过超时处理"
            )
            return

        # 增加连续超时计数
        session.consecutive_timeout_count += 1

        logger.info(
            f"[ProactiveThinker] 等待超时: user={session.user_id}, "
            f"consecutive_timeout={session.consecutive_timeout_count}"
        )

        try:
            # 获取用户名
            user_name = await self._get_user_name(session.user_id, session.stream_id)

            # 获取聊天流
            chat_stream = await self._get_chat_stream(session.stream_id)

            # 加载动作
            action_manager = ChatterActionManager()
            await action_manager.load_actions(session.stream_id)

            # 通过 ActionModifier 过滤动作
            from src.chat.planner_actions.action_modifier import ActionModifier
            action_modifier = ActionModifier(action_manager, session.stream_id)
            await action_modifier.modify_actions(chatter_name="KokoroFlowChatter")

            # 计算用户最后回复距今的时间
            time_since_user_reply = None
            if session.last_user_message_at:
                time_since_user_reply = time.time() - session.last_user_message_at

            # 构建超时上下文信息
            extra_context = {
                "consecutive_timeout_count": session.consecutive_timeout_count,
                "followup_count": session.waiting_config.followup_count,  # 真正发消息的追问次数
                "time_since_user_reply": time_since_user_reply,
                "time_since_user_reply_str": self._format_duration(time_since_user_reply) if time_since_user_reply else "未知",
            }

            # 根据模式选择生成方式
            if self._mode == KFCMode.UNIFIED:
                # 统一模式：单次 LLM 调用
                from .unified import generate_unified_response
                plan_response = await generate_unified_response(
                    session=session,
                    user_name=user_name,
                    situation_type="timeout",
                    chat_stream=chat_stream,
                    available_actions=action_manager.get_using_actions(),
                )
            else:
                # 分离模式：Planner + Replyer
                from .planner import generate_plan
                plan_response = await generate_plan(
                    session=session,
                    user_name=user_name,
                    situation_type="timeout",
                    chat_stream=chat_stream,
                    available_actions=action_manager.get_using_actions(),
                    extra_context=extra_context,
            )

                # 分离模式下需要注入上下文信息
                for action in plan_response.actions:
                    if action.type == "kfc_reply":
                        if "content" in action.params and action.params.get("content"):
                            logger.warning(
                                "[KFC ProactiveThinker] Split模式下Planner输出了kfc_reply.content，已忽略（由Replyer生成）"
                            )
                        action.params.pop("content", None)
                        action.params["user_id"] = session.user_id
                        action.params["user_name"] = user_name
                        action.params["thought"] = plan_response.thought
                        action.params["situation_type"] = "timeout"
                    action.params["extra_context"] = extra_context

            raw_wait = plan_response.max_wait_seconds
            adjusted_wait = apply_wait_duration_rules(
                raw_wait,
                session.consecutive_timeout_count,
            )
            timeout_limit = max(0, getattr(self._waiting_cfg, "max_consecutive_timeouts", 0))
            if (
                timeout_limit
                and session.consecutive_timeout_count >= timeout_limit
                and raw_wait > 0
                and adjusted_wait == 0
            ):
                logger.info(
                    "[ProactiveThinker] 连续等待 %s 次未获回复，停止继续等待",
                    session.consecutive_timeout_count,
                )
            elif adjusted_wait != raw_wait:
                logger.debug(
                    "[ProactiveThinker] 调整超时等待: raw=%ss adjusted=%ss",
                    raw_wait,
                    adjusted_wait,
                )
            plan_response.max_wait_seconds = adjusted_wait

            # ★ 在执行动作前最后一次检查状态，防止与 Chatter 并发
            if session.status != SessionStatus.WAITING:
                logger.info(
                    f"[ProactiveThinker] Session {session.user_id} 已被 Chatter 处理，取消执行动作"
                )
                return

            # 执行动作（回复生成在 Action.execute() 中完成）
            for action in plan_response.actions:
                result = await action_manager.execute_action(
                    action_name=action.type,
                    chat_id=session.stream_id,
                    target_message=None,
                    reasoning=plan_response.thought,
                    action_data=action.params,
                    thinking_id=None,
                    log_prefix="[KFC ProactiveThinker]",
                )
                if result.get("success") and action.type in ("kfc_reply", "respond"):
                    reply_text = (result.get("reply_text") or "").strip()
                    action.params["content"] = reply_text

            # 🎯 只有真正发送了消息才增加追问计数（do_nothing 不算追问）
            has_reply_action = any(
                a.type in ("kfc_reply", "respond", "poke_user", "send_emoji")
                for a in plan_response.actions
            )
            if has_reply_action:
                session.waiting_config.followup_count += 1
                logger.debug(f"[ProactiveThinker] 超时追问计数+1: user={session.user_id}, followup_count={session.waiting_config.followup_count}")

            # 记录到 mental_log
            session.add_bot_planning(
                thought=plan_response.thought,
                actions=[a.to_dict() for a in plan_response.actions],
                expected_reaction=plan_response.expected_reaction,
                max_wait_seconds=plan_response.max_wait_seconds,
            )

            # 更新状态
            if plan_response.max_wait_seconds > 0:
                # 继续等待
                session.start_waiting(
                    expected_reaction=plan_response.expected_reaction,
                    max_wait_seconds=plan_response.max_wait_seconds,
                )
            else:
                # 不再等待
                session.end_waiting()

            # 保存
            await self.session_manager.save_session(session.user_id)

            logger.info(
                f"[ProactiveThinker] 超时决策完成: user={session.user_id}, "
                f"actions={[a.type for a in plan_response.actions]}, "
                f"continue_wait={plan_response.max_wait_seconds > 0}, "
                f"consecutive_timeout={session.consecutive_timeout_count}"
            )

        except Exception as e:
            logger.error(f"[ProactiveThinker] 处理超时失败: {e}")
            # 出错时结束等待
            session.end_waiting()
            await self.session_manager.save_session(session.user_id)

    # ========================
    # 主动思考（长期沉默）
    # ========================

    async def _check_proactive_sessions(self) -> None:
        """检查是否有需要主动发起对话的 Session"""
        # 检查是否在勿扰时段
        if self._is_quiet_hours():
            return

        sessions = await self.session_manager.get_all_sessions()
        current_time = time.time()

        for session in sessions:
            try:
                trigger_reason = self._should_trigger_proactive(session, current_time)
                if trigger_reason:
                    await self._handle_proactive(session, trigger_reason)
            except Exception as e:
                logger.error(f"[ProactiveThinker] 检查主动思考失败 {session.user_id}: {e}")

    def _is_quiet_hours(self) -> bool:
        """检查是否在勿扰时段"""
        try:
            now = datetime.now()
            current_minutes = now.hour * 60 + now.minute

            start_parts = self.quiet_hours_start.split(":")
            start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])

            end_parts = self.quiet_hours_end.split(":")
            end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])

            if start_minutes <= end_minutes:
                return start_minutes <= current_minutes < end_minutes
            else:
                return current_minutes >= start_minutes or current_minutes < end_minutes
        except:
            return False

    def _should_trigger_proactive(
        self,
        session: KokoroSession,
        current_time: float,
    ) -> str | None:
        """判断是否应触发主动思考"""
        # 只检查 IDLE 状态的 Session
        if session.status != SessionStatus.IDLE:
            return None

        # 检查沉默时长
        silence_duration = current_time - session.last_activity_at
        if silence_duration < self.silence_threshold:
            return None

        # 检查距离上次主动思考的间隔
        if session.last_proactive_at:
            time_since_last = current_time - session.last_proactive_at
            if time_since_last < self.min_proactive_interval:
                return None

        # 概率触发（避免每次检查都触发）
        if random.random() > self.trigger_probability:
            return None

        silence_hours = silence_duration / 3600
        return f"沉默了 {silence_hours:.1f} 小时"

    async def _handle_proactive(
        self,
        session: KokoroSession,
        trigger_reason: str,
    ) -> None:
        """处理主动思考 - 支持双模式"""
        self._stats["proactive_triggered"] += 1

        # 再次检查最近活动时间，防止与 Chatter 并发
        time_since_last_activity = time.time() - session.last_activity_at
        if time_since_last_activity < 5:
            logger.debug(
                f"[ProactiveThinker] Session {session.user_id} 刚有活动，跳过主动思考"
            )
            return

        logger.info(f"主动思考触发: user={session.user_id}, reason={trigger_reason}")

        try:
            # 获取用户名
            user_name = await self._get_user_name(session.user_id, session.stream_id)

            # 获取聊天流
            chat_stream = await self._get_chat_stream(session.stream_id)

            # 加载动作
            action_manager = ChatterActionManager()
            await action_manager.load_actions(session.stream_id)

            # 通过 ActionModifier 过滤动作
            from src.chat.planner_actions.action_modifier import ActionModifier
            action_modifier = ActionModifier(action_manager, session.stream_id)
            await action_modifier.modify_actions(chatter_name="KokoroFlowChatter")

            # 计算沉默时长
            silence_seconds = time.time() - session.last_activity_at
            if silence_seconds < 3600:
                silence_duration = f"{silence_seconds / 60:.0f} 分钟"
            else:
                silence_duration = f"{silence_seconds / 3600:.1f} 小时"

            extra_context = {
                "trigger_reason": trigger_reason,
                "silence_duration": silence_duration,
            }

            # 根据模式选择生成方式
            if self._mode == KFCMode.UNIFIED:
                # 统一模式：单次 LLM 调用
                from .unified import generate_unified_response
                plan_response = await generate_unified_response(
                    session=session,
                    user_name=user_name,
                    situation_type="proactive",
                    chat_stream=chat_stream,
                    available_actions=action_manager.get_using_actions(),
                    extra_context=extra_context,
                )
            else:
                # 分离模式：Planner + Replyer
                from .planner import generate_plan
                plan_response = await generate_plan(
                    session=session,
                    user_name=user_name,
                    situation_type="proactive",
                    chat_stream=chat_stream,
                    available_actions=action_manager.get_using_actions(),
                    extra_context=extra_context,
                )

            # 检查是否决定不打扰
            is_do_nothing = (
                len(plan_response.actions) == 0 or
                (len(plan_response.actions) == 1 and plan_response.actions[0].type == "do_nothing")
            )

            if is_do_nothing:
                logger.info(f"决定不打扰: user={session.user_id}")
                session.last_proactive_at = time.time()
                await self.session_manager.save_session(session.user_id)
                return

            # 分离模式下需要注入上下文信息
            if self._mode == KFCMode.SPLIT:
                for action in plan_response.actions:
                    if action.type == "kfc_reply":
                        if "content" in action.params and action.params.get("content"):
                            logger.warning(
                                "[KFC ProactiveThinker] Split模式下Planner输出了kfc_reply.content，已忽略（由Replyer生成）"
                            )
                        action.params.pop("content", None)
                        action.params["user_id"] = session.user_id
                        action.params["user_name"] = user_name
                        action.params["thought"] = plan_response.thought
                        action.params["situation_type"] = "proactive"
                        action.params["extra_context"] = extra_context

            raw_wait = plan_response.max_wait_seconds
            adjusted_wait = apply_wait_duration_rules(
                raw_wait,
                session.consecutive_timeout_count,
            )
            timeout_limit = max(0, getattr(self._waiting_cfg, "max_consecutive_timeouts", 0))
            if (
                timeout_limit
                and session.consecutive_timeout_count >= timeout_limit
                and raw_wait > 0
                and adjusted_wait == 0
            ):
                logger.info(
                    "[ProactiveThinker] 连续等待 %s 次未获回复，主动无需再等",
                    session.consecutive_timeout_count,
                )
            elif adjusted_wait != raw_wait:
                logger.debug(
                    "[ProactiveThinker] 调整主动等待: raw=%ss adjusted=%ss",
                    raw_wait,
                    adjusted_wait,
                )
            plan_response.max_wait_seconds = adjusted_wait

            # 执行动作（回复生成在 Action.execute() 中完成）
            for action in plan_response.actions:
                result = await action_manager.execute_action(
                    action_name=action.type,
                    chat_id=session.stream_id,
                    target_message=None,
                    reasoning=plan_response.thought,
                    action_data=action.params,
                    thinking_id=None,
                    log_prefix="[KFC ProactiveThinker]",
                )
                if result.get("success") and action.type in ("kfc_reply", "respond"):
                    reply_text = (result.get("reply_text") or "").strip()
                    action.params["content"] = reply_text

            # 记录到 mental_log
            session.add_bot_planning(
                thought=plan_response.thought,
                actions=[a.to_dict() for a in plan_response.actions],
                expected_reaction=plan_response.expected_reaction,
                max_wait_seconds=plan_response.max_wait_seconds,
            )

            # 更新状态
            session.last_proactive_at = time.time()
            if plan_response.max_wait_seconds > 0:
                session.start_waiting(
                    expected_reaction=plan_response.expected_reaction,
                    max_wait_seconds=plan_response.max_wait_seconds,
                )

            # 保存
            await self.session_manager.save_session(session.user_id)

            logger.info(
                f"[ProactiveThinker] 主动发起完成: user={session.user_id}, "
                f"actions={[a.type for a in plan_response.actions]}"
            )

        except Exception as e:
            logger.error(f"[ProactiveThinker] 主动思考失败: {e}")

    async def _get_chat_stream(self, stream_id: str):
        """获取聊天流"""
        try:
            from src.chat.message_receive.chat_stream import get_chat_manager

            chat_manager = get_chat_manager()
            if chat_manager:
                return await chat_manager.get_stream(stream_id)
        except Exception as e:
            logger.warning(f"[ProactiveThinker] 获取 chat_stream 失败: {e}")
        return None

    async def _get_user_name(self, user_id: str, stream_id: str) -> str:
        """获取用户名称（优先从 person_info 获取）"""
        try:
            from src.person_info.person_info import get_person_info_manager

            person_info_manager = get_person_info_manager()
            platform = global_config.bot.platform if global_config else "qq"

            person_id = person_info_manager.get_person_id(platform, user_id)
            person_name = await person_info_manager.get_value(person_id, "person_name")

            if person_name:
                return person_name
        except Exception as e:
            logger.debug(f"[ProactiveThinker] 获取用户名失败: {e}")

        # 回退到 user_id
        return user_id

    def _format_duration(self, seconds: float | None) -> str:
        """格式化时间间隔为人类可读的字符串"""
        if seconds is None or seconds < 0:
            return "未知"

        if seconds < 60:
            return f"{int(seconds)} 秒"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.0f} 分钟"
        elif seconds < 86400:
            hours = seconds / 3600
            return f"{hours:.1f} 小时"
        else:
            days = seconds / 86400
            return f"{days:.1f} 天"

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            "is_running": self._running,
        }


# 全局单例
_proactive_thinker: ProactiveThinker | None = None


def get_proactive_thinker() -> ProactiveThinker:
    """获取全局主动思考器"""
    global _proactive_thinker
    if _proactive_thinker is None:
        _proactive_thinker = ProactiveThinker()
    return _proactive_thinker


async def start_proactive_thinker() -> ProactiveThinker:
    """启动主动思考器"""
    thinker = get_proactive_thinker()
    await thinker.start()
    return thinker


async def stop_proactive_thinker() -> None:
    """停止主动思考器"""
    global _proactive_thinker
    if _proactive_thinker:
        await _proactive_thinker.stop()
