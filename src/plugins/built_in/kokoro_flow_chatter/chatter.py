"""
Kokoro Flow Chatter - Chatter 主类

支持两种工作模式：
1. unified（统一模式）: 单次 LLM 调用完成思考 + 回复生成
2. split（分离模式）: Planner + Replyer 两次 LLM 调用

核心设计：
- Chatter 只负责 "收到消息 → 规划执行" 的流程
- 无论 Session 之前是什么状态，流程都一样
- 区别只体现在提示词中

不负责：
- 等待超时处理（由 ProactiveThinker 负责）
- 连续思考（由 ProactiveThinker 负责）
- 主动发起对话（由 ProactiveThinker 负责）
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any, ClassVar

from src.chat.planner_actions.action_manager import ChatterActionManager
from src.common.data_models.message_manager_data_model import StreamContext
from src.common.logger import get_logger
from src.plugin_system.base.base_chatter import BaseChatter
from src.plugin_system.base.component_types import ChatType

from .config import KFCMode, apply_wait_duration_rules, get_config
from .models import SessionStatus
from .session import get_session_manager

if TYPE_CHECKING:
    pass

logger = get_logger("kfc_chatter")

# 全局用户锁，用于串行化同一用户的消息处理，避免并发冲突
_user_locks: dict[str, asyncio.Lock] = {}
_user_locks_mutex = asyncio.Lock()
_user_lock_access_times: dict[str, float] = {}  # 🔧 跟踪每个锁的最后访问时间
MAX_USER_LOCKS = 1000  # 🔧 最多保存 1000 个用户锁

async def get_user_lock(user_id: str) -> asyncio.Lock:
    async with _user_locks_mutex:
        # 🔧 LRU 清理：如果超过限制，删除最久未使用的锁
        if len(_user_locks) >= MAX_USER_LOCKS and user_id not in _user_locks:
            # 找到最旧的锁
            oldest_user = min(_user_lock_access_times.items(), key=lambda x: x[1])[0]
            del _user_locks[oldest_user]
            del _user_lock_access_times[oldest_user]
            logger.debug(f"🧹 清理久未使用的用户锁: {oldest_user}")

        if user_id not in _user_locks:
            _user_locks[user_id] = asyncio.Lock()

        # 更新访问时间
        _user_lock_access_times[user_id] = time.time()
        return _user_locks[user_id]


class KokoroFlowChatter(BaseChatter):
    """
    Kokoro Flow Chatter - 私聊特化的心流聊天器

    支持两种工作模式（通过配置切换）：
    - unified: 单次 LLM 调用完成思考和回复
    - split: Planner + Replyer 两次 LLM 调用

    核心设计：
    - Chatter 只负责 "收到消息 → 规划执行" 的流程
    - 无论 Session 之前是什么状态，流程都一样
    - 区别只体现在提示词中

    不负责：
    - 等待超时处理（由 ProactiveThinker 负责）
    - 连续思考（由 ProactiveThinker 负责）
    - 主动发起对话（由 ProactiveThinker 负责）
    """

    chatter_name: str = "KokoroFlowChatter"
    chatter_description: str = "心流聊天器 - 私聊特化的深度情感交互处理器"
    chat_types: ClassVar[list[ChatType]] = [ChatType.PRIVATE]

    def __init__(
        self,
        stream_id: str,
        action_manager: "ChatterActionManager",
        plugin_config: dict | None = None,
    ):
        super().__init__(stream_id, action_manager, plugin_config)

        # 核心组件
        self.session_manager = get_session_manager()

        # 加载配置
        self._config = get_config()
        self._mode = self._config.mode

        # 并发控制
        # self._lock = asyncio.Lock() # 不再使用实例锁，改用全局用户锁
        self._processing = False

        # 统计
        self._stats: dict[str, Any] = {
            "messages_processed": 0,
            "successful_responses": 0,
            "failed_responses": 0,
        }

        # 输出初始化信息
        mode_str = "统一模式" if self._mode == KFCMode.UNIFIED else "分离模式"
        logger.info(f"初始化完成 (模式: {mode_str}): stream_id={stream_id}")

        # [Hack] 抑制 sqlalchemy.pool 在任务取消时产生的 "Exception closing connection" 噪音日志
        import logging
        logging.getLogger("sqlalchemy.pool").setLevel(logging.CRITICAL)

    async def execute(self, context: StreamContext) -> dict:
        """
        执行聊天处理

        流程：
        1. 获取 Session
        2. 获取未读消息
        3. 记录用户消息到 mental_log
        4. 确定 situation_type（根据之前的等待状态）
        5. 根据模式调用对应的生成器
        6. 执行动作
        7. 更新 Session（记录 Bot 规划，设置等待状态）
        8. 保存 Session
        """
        # 0. 预检查：获取 user_id 用于锁定 Session
        # 注意：这里只是 peek，真正的获取在锁内进行
        peek_messages = context.get_unread_messages()
        if not peek_messages:
            return self._build_result(success=True, message="no_unread_messages")

        target_message = peek_messages[-1]
        if not target_message.user_info:
             return self._build_result(success=False, message="no_user_info")

        user_id = str(target_message.user_info.user_id)

        # 使用全局用户锁来确保同一用户的处理是串行的
        # 注意：不能使用 SessionManager._get_lock，因为 get_session 内部也会请求该锁，导致死锁
        user_lock = await get_user_lock(user_id)

        async with user_lock:
            self._processing = True
            # 更新上下文状态，以便 MessageManager 能正确检测到正在处理中（用于系统打断）
            if hasattr(context, "is_chatter_processing"):
                context.is_chatter_processing = True

            last_result = self._build_result(success=True, message="no_processed")

            try:
                # 循环处理所有积压的消息，直到没有未读消息为止
                # 这解决了“吞消息”问题：即使 stream_loop 没有及时重新触发，execute 也会处理完所有消息
                while True:
                    # 1. 获取未读消息 (在锁内重新获取，确保状态最新)
                    unread_messages = context.get_unread_messages()
                    if not unread_messages:
                        break

                    # 2. 取最后一条消息作为主消息
                    target_message = unread_messages[-1]
                    # user_id 已经在上面获取了
                    user_name = target_message.user_info.user_nickname or user_id

                    # 3. 获取或创建 Session
                    session = await self.session_manager.get_session(user_id, self.stream_id)

                    # 3.5 **立即**更新活动时间，阻止 ProactiveThinker 并发处理
                    session.last_activity_at = time.time()

                    # 4. 确定 situation_type（根据之前的等待状态）
                    situation_type = self._determine_situation_type(session)

                    # 5. **立即**结束等待状态，防止 ProactiveThinker 并发处理
                    if session.status == SessionStatus.WAITING:
                        session.end_waiting()
                        await self.session_manager.save_session(user_id)

                    # 6. 记录用户消息到 mental_log
                    messages_added_count = 0
                    for msg in unread_messages:
                        msg_content = msg.processed_plain_text or msg.display_message or ""
                        msg_user_name = msg.user_info.user_nickname if msg.user_info else user_name
                        msg_user_id = str(msg.user_info.user_id) if msg.user_info else user_id

                        session.add_user_message(
                            content=msg_content,
                            user_name=msg_user_name,
                            user_id=msg_user_id,
                            timestamp=msg.time,
                        )
                        messages_added_count += 1

                    # 7. 加载可用动作（通过 ActionModifier 过滤）
                    from src.chat.planner_actions.action_modifier import ActionModifier

                    # 检查是否处于极速模式
                    is_fast_mode = self._config.fast_mode_enabled

                    if is_fast_mode:
                        logger.info(f"[KFC] {self.stream_id} 处于极速模式，跳过动作筛选和记忆判官")
                        # 极速模式下，直接加载动作，不进行 modify_actions (跳过 LLM 判定)
                        await self.action_manager.load_actions(self.stream_id)
                        available_actions = self.action_manager.get_using_actions()
                    else:
                        action_modifier = ActionModifier(self.action_manager, self.stream_id)
                        await action_modifier.modify_actions(chatter_name="KokoroFlowChatter")
                        available_actions = self.action_manager.get_using_actions()

                    # 8. 获取聊天流
                    chat_stream = await self._get_chat_stream()

                    # 9. 根据模式调用对应的生成器
                    if is_fast_mode:
                        # 极速模式强制使用统一模式（单次调用）
                        plan_response = await self._execute_unified_mode(
                            session=session,
                            user_name=user_name,
                            situation_type=situation_type,
                            chat_stream=chat_stream,
                            available_actions=available_actions,
                            fast_mode=True,
                        )
                    elif self._mode == KFCMode.UNIFIED:
                        plan_response = await self._execute_unified_mode(
                            session=session,
                            user_name=user_name,
                            situation_type=situation_type,
                            chat_stream=chat_stream,
                            available_actions=available_actions,
                        )
                    else:
                        plan_response = await self._execute_split_mode(
                            session=session,
                            user_name=user_name,
                            user_id=user_id,
                            situation_type=situation_type,
                            chat_stream=chat_stream,
                            available_actions=available_actions,
                        )

                    # 10. 执行动作
                    raw_wait = plan_response.max_wait_seconds
                    adjusted_wait = apply_wait_duration_rules(
                        raw_wait,
                        session.consecutive_timeout_count,
                    )
                    timeout_limit = max(0, self._config.waiting.max_consecutive_timeouts)
                    if (
                        timeout_limit
                        and session.consecutive_timeout_count >= timeout_limit
                        and raw_wait > 0
                        and adjusted_wait == 0
                    ):
                        logger.info(
                            "[KFC] 连续等待 %s 次未收到回复，暂停继续等待",
                            session.consecutive_timeout_count,
                        )
                    elif adjusted_wait != raw_wait:
                        logger.debug(
                            "[KFC] 调整等待时长: raw=%ss adjusted=%ss",
                            raw_wait,
                            adjusted_wait,
                        )
                    plan_response.max_wait_seconds = adjusted_wait

                    exec_results = []
                    has_reply = False

                    for idx, action in enumerate(plan_response.actions, 1):
                        logger.debug(f"[KFC] 执行第 {idx}/{len(plan_response.actions)} 个动作: {action.type}")
                        action_data = action.params.copy()

                        try:
                            result = await self.action_manager.execute_action(
                                action_name=action.type,
                                chat_id=self.stream_id,
                                target_message=target_message,
                                reasoning=plan_response.thought,
                                action_data=action_data,
                                thinking_id=None,
                                log_prefix="[KFC]",
                            )
                            logger.debug(f"[KFC] 动作 {action.type} 执行结果: success={result.get('success')}, reply_text={result.get('reply_text', '')[:50]}")
                            exec_results.append(result)
                            if result.get("success") and action.type in ("kfc_reply", "respond"):
                                has_reply = True
                                reply_text = (result.get("reply_text") or "").strip()
                                # 始终更新内容以反映实际发送情况（包括因打断导致的部分发送或未发送）
                                action.params["content"] = reply_text

                        except BaseException as e:
                            # 检查是否是打断异常 (KFCInterruptionError 现在继承自 BaseException 以穿透 action_manager)
                            from .actions.reply import KFCInterruptionError

                            # 显式检查类型
                            if isinstance(e, KFCInterruptionError):
                                logger.info(f"[KFC] 检测到打断: {e}")

                                # 记录已发送的部分
                                if action.type == "kfc_reply":
                                    action.params["content"] = e.partial_reply
                                    if e.partial_reply:
                                        has_reply = True

                                # 记录这次规划（包含已执行的部分）
                                session.add_bot_planning(
                                    thought=plan_response.thought + " (发送过程中被新消息打断)",
                                    actions=[a.to_dict() for a in plan_response.actions[:idx]], # 只记录到当前执行的动作
                                    expected_reaction=plan_response.expected_reaction,
                                    max_wait_seconds=0, # 打断后立即处理新消息，不等待
                                )

                                # 13. 标记消息为已读
                                for msg in unread_messages:
                                    context.mark_message_as_read(str(msg.message_id))

                                # 提前保存 Session 并退出
                                await self.session_manager.save_session(user_id)

                                current_mode_str = "unified" if self._mode == KFCMode.UNIFIED else "split"
                                return self._build_result(
                                    success=True,
                                    message="interrupted",
                                    has_reply=has_reply,
                                    thought=plan_response.thought,
                                    situation_type=situation_type,
                                    mode=current_mode_str,
                                )

                            elif isinstance(e, asyncio.CancelledError):
                                # 任务被取消（LLM思考阶段被取消）
                                logger.info("[KFC] 任务被取消 (Thinking Phase Interruption)")

                                # 关键修复：如果在思考阶段被打断，必须回滚 mental_log 中新添加的消息
                                # 因为这些消息仍然是 UNREAD 状态，下一次 execute 会再次读取它们。
                                # 如果不回滚，mental_log 中会出现重复的消息记录。
                                if "messages_added_count" in locals() and messages_added_count > 0:
                                    if session and hasattr(session, "mental_log"):
                                        if len(session.mental_log) >= messages_added_count:
                                            session.mental_log = session.mental_log[:-messages_added_count]
                                            logger.info(f"[KFC] 因打断回滚了 {messages_added_count} 条消息记录，等待下一次合并处理")

                                # 保存回滚后的 Session (保持状态一致性)
                                if "user_id" in locals() and user_id:
                                    await self.session_manager.save_session(user_id)
                                raise e

                            else:
                                # 其他异常正常抛出
                                raise e

                    # 11. 记录 Bot 规划到 mental_log
                    session.add_bot_planning(
                        thought=plan_response.thought,
                        actions=[a.to_dict() for a in plan_response.actions],
                        expected_reaction=plan_response.expected_reaction,
                        max_wait_seconds=plan_response.max_wait_seconds,
                    )

                    # 12. 更新 Session 状态
                    if plan_response.max_wait_seconds > 0:
                        session.start_waiting(
                            expected_reaction=plan_response.expected_reaction,
                            max_wait_seconds=plan_response.max_wait_seconds,
                        )
                    else:
                        session.end_waiting()

                    # 13. 标记消息为已读
                    for msg in unread_messages:
                        context.mark_message_as_read(str(msg.message_id))

                    # 14. 保存 Session
                    await self.session_manager.save_session(user_id)

                    # 15. 更新统计
                    self._stats["messages_processed"] += len(unread_messages)
                    if has_reply:
                        self._stats["successful_responses"] += 1

                    # 输出完成信息
                    mode_str = "unified" if self._mode == KFCMode.UNIFIED else "split"
                    logger.info(
                        f"处理完成 ({mode_str}): "
                        f"user={user_name}, situation={situation_type}, "
                        f"actions={[a.type for a in plan_response.actions]}, "
                        f"wait={plan_response.max_wait_seconds}s"
                    )

                    last_result = self._build_result(
                        success=True,
                        message="processed",
                        has_reply=has_reply,
                        thought=plan_response.thought,
                        situation_type=situation_type,
                        mode=mode_str,
                    )

                return last_result

            except Exception as e:
                self._stats["failed_responses"] += 1
                logger.error(f"[KFC] 处理失败: {e}")
                import traceback
                traceback.print_exc()
                return self._build_result(success=False, message=str(e), error=True)

            finally:
                self._processing = False
                if hasattr(context, "is_chatter_processing"):
                    context.is_chatter_processing = False

    async def _execute_unified_mode(
        self,
        session,
        user_name: str,
        situation_type: str,
        chat_stream,
        available_actions,
        fast_mode: bool = False,
    ):
        """
        统一模式：单次 LLM 调用完成思考 + 回复生成

        LLM 输出的 JSON 中 kfc_reply 动作已包含 content 字段，
        无需再调用 Replyer 生成回复。
        """
        from .unified import generate_unified_response

        plan_response = await generate_unified_response(
            session=session,
            user_name=user_name,
            situation_type=situation_type,
            chat_stream=chat_stream,
            available_actions=available_actions,
            fast_mode=fast_mode,
        )

        # 统一模式下 content 已经在 actions 中，无需注入
        return plan_response

    async def _execute_split_mode(
        self,
        session,
        user_name: str,
        user_id: str,
        situation_type: str,
        chat_stream,
        available_actions,
    ):
        """
        分离模式：Planner + Replyer 两次 LLM 调用

        1. Planner 生成行动计划（JSON，kfc_reply 不含 content）
        2. 为 kfc_reply 动作注入上下文，由 Action.execute() 调用 Replyer 生成回复
        """
        from .planner import generate_plan

        plan_response = await generate_plan(
            session=session,
            user_name=user_name,
            situation_type=situation_type,
            chat_stream=chat_stream,
            available_actions=available_actions,
        )

        # 为 kfc_reply 动作注入回复生成所需的上下文
        for action in plan_response.actions:
            if action.type == "kfc_reply":
                # 分离模式下 Planner 不应直接生成回复内容；即使模型输出了 content，也应忽略
                if "content" in action.params and action.params.get("content"):
                    logger.warning(
                        "[KFC] Split模式下Planner输出了kfc_reply.content，已忽略（由Replyer生成）"
                    )
                action.params.pop("content", None)
                action.params["user_id"] = user_id
                action.params["user_name"] = user_name
                action.params["thought"] = plan_response.thought
                action.params["situation_type"] = situation_type

        return plan_response

    def _determine_situation_type(self, session) -> str:
        """
        确定当前情况类型

        根据 Session 之前的状态决定提示词的 situation_type
        """
        if session.status == SessionStatus.WAITING:
            # 之前在等待
            # 如果 max_wait_seconds <= 0，说明不是有效的等待状态，视为新消息
            if session.waiting_config.max_wait_seconds <= 0:
                return "new_message"

            if session.waiting_config.is_timeout():
                # 超时了才收到回复
                return "reply_late"
            else:
                # 在预期内收到回复
                return "reply_in_time"
        else:
            # 之前是 IDLE
            return "new_message"

    async def _get_chat_stream(self):
        """获取聊天流对象"""
        try:
            from src.chat.message_receive.chat_stream import get_chat_manager

            chat_manager = get_chat_manager()
            if chat_manager:
                return await chat_manager.get_stream(self.stream_id)
        except Exception as e:
            logger.warning(f"[KFC] 获取 chat_stream 失败: {e}")
        return None

    def _build_result(
        self,
        success: bool,
        message: str = "",
        error: bool = False,
        **kwargs,
    ) -> dict:
        """构建返回结果"""
        result = {
            "success": success,
            "stream_id": self.stream_id,
            "message": message,
            "error": error,
            "timestamp": time.time(),
        }
        result.update(kwargs)
        return result

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()
        stats["mode"] = self._mode.value
        return stats

    @property
    def is_processing(self) -> bool:
        """是否正在处理"""
        return self._processing

    @property
    def mode(self) -> KFCMode:
        """当前工作模式"""
        return self._mode
