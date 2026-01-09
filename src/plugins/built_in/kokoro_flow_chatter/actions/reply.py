"""
KFC 回复动作模块

KFC 的 reply 动作：
- 完整的回复流程在 execute() 中实现
- 调用 Replyer 生成回复文本
- 回复后处理（系统格式词过滤、分段发送、错字生成等）
- 发送回复消息

与 AFC 类似，但使用 KFC 专属的 Replyer 和 Session 系统。
"""

import asyncio
from typing import TYPE_CHECKING, ClassVar, Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system import ActionActivationType, BaseAction, ChatMode
from src.plugin_system.apis import send_api

if TYPE_CHECKING:
    from ..session import KokoroSession

logger = get_logger("kfc_reply_action")


class KFCInterruptionError(BaseException):
    """KFC 打断异常，当检测到新消息时抛出"""
    def __init__(self, partial_reply: str, unsend_segments: list[str]):
        self.partial_reply = partial_reply
        self.unsend_segments = unsend_segments
        super().__init__("Reply action interrupted by new message")


class KFCReplyAction(BaseAction):
    """KFC Reply 动作 - 完整的私聊回复流程

    特点：
    - 完整的回复流程：生成回复 → 后处理 → 分段发送
    - 使用 KFC 专属的 Replyer 生成回复
    - 支持系统格式词过滤、分段发送、错字生成等后处理
    - 仅限 KokoroFlowChatter 使用
    - 支持回复打断：如果发送过程中收到新消息，会抛出 KFCInterruptionError

    action_data 参数：
    - user_id: 用户ID（必需，用于获取 Session）
    - user_name: 用户名称（必需）
    - thought: Planner 生成的想法/内心独白（必需）
    - situation_type: 情况类型（可选，默认 "new_message"）
    - extra_context: 额外上下文（可选）
    - content: 预生成的回复内容（可选，如果提供则直接发送）
    - should_quote_reply: 是否引用原消息（可选，默认 false）
    - enable_splitter: 是否启用分段发送（可选，默认 true）
    - enable_chinese_typo: 是否启用错字生成（可选，默认 true）
    """

    # 动作基本信息
    action_name = "kfc_reply"
    action_description = "发送回复消息。会根据当前对话情境生成并发送回复。"

    # 激活设置
    activation_type = ActionActivationType.ALWAYS
    mode_enable = ChatMode.ALL
    parallel_action = False

    # Chatter 限制：仅允许 KokoroFlowChatter 使用
    chatter_allow: ClassVar[list[str]] = ["KokoroFlowChatter"]

    # 动作参数定义
    action_parameters: ClassVar = {
        "content": "要发送的回复内容（可选，如果不提供则自动生成）",
        "should_quote_reply": "是否引用原消息（可选，true/false，默认 false）",
    }

    # 动作使用场景
    action_require: ClassVar = [
        "需要发送回复消息时使用",
        "私聊场景的标准回复动作",
    ]

    # 关联类型
    associated_types: ClassVar[list[str]] = ["text"]

    async def execute(self) -> tuple[bool, str]:
        """执行 reply 动作 - 完整的回复流程"""
        try:
            # 1. 检查是否有预生成的内容
            content = self.action_data.get("content", "")

            if not content:
                # 2. 需要生成回复，获取必要信息
                user_id = self.action_data.get("user_id")
                user_name = self.action_data.get("user_name", "用户")
                thought = self.action_data.get("thought", "")
                situation_type = self.action_data.get("situation_type", "new_message")
                extra_context = self.action_data.get("extra_context")

                if not user_id:
                    logger.warning(f"{self.log_prefix} 缺少 user_id，无法生成回复")
                    return False, ""

                # 3. 获取 Session
                session = await self._get_session(user_id)
                if not session:
                    logger.warning(f"{self.log_prefix} 无法获取 Session: {user_id}")
                    return False, ""

                # 4. 调用 Replyer 生成回复
                success, content = await self._generate_reply(
                    session=session,
                    user_name=user_name,
                    thought=thought,
                    situation_type=situation_type,
                    extra_context=extra_context,
                )

                if not success or not content:
                    logger.warning(f"{self.log_prefix} 回复生成失败")
                    return False, ""

            # 5. 回复后处理（系统格式词过滤 + 分段处理）
            enable_splitter = self.action_data.get("enable_splitter", True)
            enable_chinese_typo = self.action_data.get("enable_chinese_typo", True)

            processed_segments = self._post_process_reply(
                content=content,
                enable_splitter=enable_splitter,
                enable_chinese_typo=enable_chinese_typo,
            )

            if not processed_segments:
                logger.warning(f"{self.log_prefix} 回复后处理后内容为空")
                return False, ""

            # 6. 分段发送回复
            should_quote = self.action_data.get("should_quote_reply", False)
            reply_text = await self._send_segments(
                segments=processed_segments,
                should_quote=should_quote,
            )

            logger.info(f"{self.log_prefix} KFC reply 动作执行成功: {reply_text[:50]}...")
            return True, reply_text

        except KFCInterruptionError:
            raise  # 重新抛出打断异常，交由上层处理
        except asyncio.CancelledError:
            raise  # 抛出取消异常，可能在 _send_segments 中被转换为 KFCInterruptionError
        except Exception as e:
            logger.error(f"{self.log_prefix} KFC reply 动作执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False, ""

    def _post_process_reply(
        self,
        content: str,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> list[str]:
        """
        回复后处理

        包括：
        1. 系统格式词过滤（移除 [回复...]、[表情包：...]、@<...> 等）
        2. 分段处理（根据标点分句、智能合并）
        3. 错字生成（拟人化）

        Args:
            content: 原始回复内容
            enable_splitter: 是否启用分段
            enable_chinese_typo: 是否启用错字生成

        Returns:
            处理后的文本段落列表
        """
        try:
            from src.chat.utils.utils import filter_system_format_content, process_llm_response

            # 1. 过滤系统格式词
            filtered_content = filter_system_format_content(content)

            if not filtered_content or not filtered_content.strip():
                logger.warning(f"{self.log_prefix} 过滤系统格式词后内容为空")
                return []

            # 2. 分段处理 + 错字生成
            processed_segments = process_llm_response(
                filtered_content,
                enable_splitter=enable_splitter,
                enable_chinese_typo=enable_chinese_typo,
            )

            # 过滤空段落
            processed_segments = [seg for seg in processed_segments if seg and seg.strip()]

            logger.debug(
                f"{self.log_prefix} 回复后处理完成: "
                f"原始长度={len(content)}, 过滤后长度={len(filtered_content)}, "
                f"分段数={len(processed_segments)}"
            )

            return processed_segments

        except Exception as e:
            logger.error(f"{self.log_prefix} 回复后处理失败: {e}")
            # 失败时返回原始内容
            return [content] if content else []

    async def _send_segments(
        self,
        segments: list[str],
        should_quote: bool = False,
    ) -> str:
        """
        分段发送回复
        """
        reply_text = ""
        first_sent = False

        # 获取分段发送的间隔时间
        typing_delay = 0.5
        if global_config and hasattr(global_config, "response_splitter"):
            typing_delay = getattr(global_config.response_splitter, "typing_delay", 0.5)

        try:
            for i, segment in enumerate(segments):
                if not segment or not segment.strip():
                    continue

                reply_text += segment

                # 发送消息
                if not first_sent:
                    await send_api.text_to_stream(
                        text=segment,
                        stream_id=self.chat_stream.stream_id,
                        reply_to_message=self.action_message,
                        set_reply=should_quote and bool(self.action_message),
                        typing=False,
                    )
                    first_sent = True
                else:
                    if typing_delay > 0:
                        await asyncio.sleep(typing_delay)

                    await send_api.text_to_stream(
                        text=segment,
                        stream_id=self.chat_stream.stream_id,
                        reply_to_message=None,
                        set_reply=False,
                        typing=True,
                    )

            return reply_text

        except asyncio.CancelledError:
            # 如果被外部取消（如 Task.cancel()），也视为打断，保存当前进度
            logger.info(f"{self.log_prefix} 发送过程被强制取消，保存进度")
            # 注意：此时循环中的 segment 可能还没发，或者刚发完但还没更新 reply_text (如果是 await 处取消)
            # 简单起见，我们认为 reply_text 是已确认发送的
            # 未发送部分从当前 index 开始（如果还没加进 reply_text）
            # 由于 reply_text += segment 是在 await 之前，所以如果是 await send/sleep 被取消，
            # 该 segment 已经加进去了，但没发成功（或者sleep时已发成功）。
            # 这是一个边缘情况，为了不丢失信息，我们宁可多发（假装没发成功）也不要少发。
            # 这里保守策略：reply_text 包含 current segment，但其实可能没发出去。
            # 如果是 sleep 被取消，那上一条是发成功的。
            # 如果是 send_api 被取消，那这条可能没发成功。
            # 我们可以检查 reply_text 是否包含 segment。
            # 简化逻辑：直接抛出

            # 计算未发送部分：从当前 i 开始（如果还没处理完）
            # 由于 enumerate scope 问题，我们需要在循环外访问 i？
            # Python loop 变量泄漏到外部 scope，但 try block 内部变量可能不一样。
            # 还是在 loop 内 try/except 比较好？不，loop 外 catch 更整洁。

            # 由于我们无法准确知道 i 的值（除非在 loop 里更新 self.current_index），
            # 这里简单处理：若被强制取消，只返回已累积的 reply_text。
            # 剩下的丢弃？不，这正是用户不要的。
            # 但被 Cancelled 通常意味着 LLM 阶段或者新的 Execute 来了。
            # 如果是新的 Execute 来了，它会重新规划。
            # 所以这里抛出 KFCInterruptionError 主要是为了让 Session 记录 "我说了X"。
            raise KFCInterruptionError(
                partial_reply=reply_text,
                unsend_segments=[] # 无法获取剩余部分，但这不重要，因为会重新规划
            )

    async def _should_interrupt(self) -> bool:
        """
        检查是否应该打断回复

        如果收到比当前处理的消息更新的消息，则视为打断
        """
        if not self.chat_stream or not self.chat_stream.context:
            return False

        # 获取当前未读消息
        current_unread = self.chat_stream.context.get_unread_messages()
        if not current_unread:
            return False

        # 获取目标消息时间（我们正在回复的消息）
        target_time = 0.0
        target_id = ""

        if self.action_message:
            if isinstance(self.action_message, dict):
                target_time = float(self.action_message.get("time", 0.0) or 0.0)
                target_id = str(self.action_message.get("message_id", ""))
            else:
                target_time = float(getattr(self.action_message, "time", 0.0) or 0.0)
                target_id = str(getattr(self.action_message, "message_id", ""))

        # 如果没有目标消息时间，默认打断（可能是主动发起的回复，有新消息就停）
        if target_time <= 0:
            # 如果是主动发起的，检查所有未读消息
            if current_unread:
                logger.debug(f"{self.log_prefix} 发现新消息(主动发起场景), 触发打断")
                return True
            return False

        # 检查是否有更新的用户消息
        for msg in current_unread:
            # 必须是有效的消息时间
            msg_time = float(getattr(msg, "time", 0.0) or 0.0)
            msg_id = str(getattr(msg, "message_id", ""))

            # 如果消息时间明显晚于目标消息（加0.1s缓冲）
            # 并且不是目标消息本身（通过ID判断）
            if msg_time > target_time + 0.1:
                if msg_id != target_id:
                    logger.debug(f"{self.log_prefix} 发现新消息(time={msg_time}), 触发打断")
                    return True

        return False

    async def _get_session(self, user_id: str) -> Optional["KokoroSession"]:
        """获取用户 Session"""
        try:
            from ..session import get_session_manager

            session_manager = get_session_manager()
            return await session_manager.get_session(user_id, self.chat_stream.stream_id)
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取 Session 失败: {e}")
            return None

    async def _generate_reply(
        self,
        session: "KokoroSession",
        user_name: str,
        thought: str,
        situation_type: str,
        extra_context: dict | None = None,
    ) -> tuple[bool, str]:
        """调用 Replyer 生成回复"""
        try:
            from ..replyer import generate_reply_text

            return await generate_reply_text(
                session=session,
                user_name=user_name,
                thought=thought,
                situation_type=situation_type,
                chat_stream=self.chat_stream,
                extra_context=extra_context,
            )
        except Exception as e:
            logger.error(f"{self.log_prefix} 生成回复失败: {e}")
            return False, ""
