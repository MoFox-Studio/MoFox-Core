"""
Kokoro Flow Chatter - 统一模式

统一模式（Unified Mode）：
- 使用模块化的提示词组件构建提示词
- System Prompt + User Prompt 的标准结构
- 一次 LLM 调用完成思考 + 回复生成
- 输出 JSON 格式：thought + actions + max_wait_seconds

与分离模式（Split Mode）的区别：
- 统一模式：一次调用完成所有工作，actions 中直接包含回复内容
- 分离模式：Planner + Replyer 两次调用，先规划再生成回复
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.apis import llm_api
from src.utils.json_parser import extract_and_parse_json

# 统一模式专用的提示词模块
from . import prompt_modules_unified as prompt_modules
from .models import EventType, LLMResponse
from .session import KokoroSession

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream
    from src.common.data_models.message_manager_data_model import StreamContext

logger = get_logger("kfc_unified")


class UnifiedPromptGenerator:
    """
    统一模式提示词生成器

    为统一模式构建提示词：
    - generate_system_prompt: 构建系统提示词
    - generate_responding_prompt: 回应消息场景
    - generate_timeout_prompt: 超时决策场景
    - generate_proactive_prompt: 主动思考场景
    """

    def __init__(self):
        pass

    async def generate_system_prompt(
        self,
        session: KokoroSession,
        available_actions: dict | None = None,
        context_data: dict[str, str] | None = None,
        chat_stream: Optional["ChatStream"] = None,
    ) -> str:
        """
        生成系统提示词

        使用 prompt_modules.build_system_prompt() 构建模块化的提示词
        """
        return prompt_modules.build_system_prompt(
            session=session,
            available_actions=available_actions,
            context_data=context_data,
            chat_stream=chat_stream,
        )

    async def generate_responding_prompt(
        self,
        session: KokoroSession,
        message_content: str,
        sender_name: str,
        sender_id: str,
        message_time: float | None = None,
        available_actions: dict | None = None,
        context: Optional["StreamContext"] = None,
        context_data: dict[str, str] | None = None,
        chat_stream: Optional["ChatStream"] = None,
        all_unread_messages: list | None = None,
    ) -> tuple[str, str]:
        """
        生成回应消息场景的提示词

        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        # 生成系统提示词
        system_prompt = await self.generate_system_prompt(
            session,
            available_actions,
            context_data=context_data,
            chat_stream=chat_stream,
        )

        # 构建叙事历史
        if context:
            narrative_history = prompt_modules.format_history_from_context(
                context, session.mental_log
            )
        else:
            narrative_history = prompt_modules.format_narrative_history(session.mental_log)

        # 格式化收到的消息
        incoming_messages = prompt_modules.format_incoming_messages(
            message_content=message_content,
            sender_name=sender_name,
            sender_id=sender_id,
            message_time=message_time,
            all_unread_messages=all_unread_messages,
        )

        # 使用用户提示词模板
        user_prompt = prompt_modules.RESPONDING_USER_PROMPT_TEMPLATE.format(
            narrative_history=narrative_history,
            incoming_messages=incoming_messages,
        )

        return system_prompt, user_prompt

    async def generate_timeout_prompt(
        self,
        session: KokoroSession,
        available_actions: dict | None = None,
        context_data: dict[str, str] | None = None,
        chat_stream: Optional["ChatStream"] = None,
    ) -> tuple[str, str]:
        """
        生成超时决策场景的提示词

        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        # 生成系统提示词
        system_prompt = await self.generate_system_prompt(
            session,
            available_actions,
            context_data=context_data,
            chat_stream=chat_stream,
        )

        # 构建叙事历史
        narrative_history = prompt_modules.format_narrative_history(session.mental_log)

        # 计算等待时间
        wait_duration = session.waiting_config.get_elapsed_seconds()

        # 生成连续追问警告（使用 followup_count 作为追问计数，只有真正发消息才算）
        followup_count = session.waiting_config.followup_count
        max_followups = 2  # 建议最多追问2次

        if followup_count >= max_followups:
            followup_warning = f"""
⚠️ 你已经追问了 {followup_count} 次，对方都没有回复。
建议这次结束等待（`max_wait_seconds: 0`），给对方一些空间。"""

        elif followup_count == 1:
            followup_warning = """
这是第2次等待了。
- 如果之前问了问题，可以再问一下
- 如果之前只是分享或告别，建议结束等待"""

        elif followup_count == 0:
            followup_warning = """
这是第一次超时。根据你之前发的消息类型来决定：
- 问题 → 可以追问
- 分享 → 结束等待也行
- 告别 → 不要追问"""

        else:
            followup_warning = ""

        # 获取最后一条 Bot 消息
        last_bot_message = "（没有记录）"
        for entry in reversed(session.mental_log):
            if entry.event_type == EventType.BOT_PLANNING:
                for action in entry.actions:
                    if action.get("type") in ("reply", "kfc_reply"):
                        content = action.get("content", "")
                        if content:
                            last_bot_message = content
                            break
                if last_bot_message != "（没有记录）":
                    break

        # 使用用户提示词模板
        user_prompt = prompt_modules.TIMEOUT_DECISION_USER_PROMPT_TEMPLATE.format(
            narrative_history=narrative_history,
            wait_duration_seconds=wait_duration,
            wait_duration_minutes=wait_duration / 60,
            expected_user_reaction=session.waiting_config.expected_reaction or "不确定",
            followup_warning=followup_warning,
            last_bot_message=last_bot_message,
        )

        return system_prompt, user_prompt

    async def generate_proactive_prompt(
        self,
        session: KokoroSession,
        trigger_context: str,
        available_actions: dict | None = None,
        context_data: dict[str, str] | None = None,
        chat_stream: Optional["ChatStream"] = None,
    ) -> tuple[str, str]:
        """
        生成主动思考场景的提示词

        Returns:
            tuple[str, str]: (系统提示词, 用户提示词)
        """
        # 生成系统提示词
        system_prompt = await self.generate_system_prompt(
            session,
            available_actions,
            context_data=context_data,
            chat_stream=chat_stream,
        )

        # 构建叙事历史
        narrative_history = prompt_modules.format_narrative_history(
            session.mental_log, max_entries=10
        )

        # 计算沉默时长
        silence_seconds = time.time() - session.last_activity_at
        if silence_seconds < 3600:
            silence_duration = f"{silence_seconds / 60:.0f}分钟"
        else:
            silence_duration = f"{silence_seconds / 3600:.1f}小时"

        # 当前时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        # 从 context_data 获取关系信息
        relation_block = ""
        if context_data:
            relation_info = context_data.get("relation_info", "")
            if relation_info:
                relation_block = f"### 你与对方的关系\n{relation_info}"

        if not relation_block:
            # 回退：使用默认关系描述
            relation_block = """### 你与对方的关系
- 你们还不太熟悉
- 正在慢慢了解中"""

        # 使用用户提示词模板
        user_prompt = prompt_modules.PROACTIVE_THINKING_USER_PROMPT_TEMPLATE.format(
            narrative_history=narrative_history,
            current_time=current_time,
            silence_duration=silence_duration,
            relation_block=relation_block,
            trigger_context=trigger_context,
        )

        return system_prompt, user_prompt

    def build_messages_for_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        stream_id: str = "",
    ) -> str:
        """
        构建 LLM 请求的完整提示词

        将 system + user 合并为单个提示词字符串
        """
        # 合并提示词
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        # DEBUG日志：打印完整的KFC提示词（只在 DEBUG 级别输出）
        logger.debug(
            f"Final KFC prompt constructed for stream {stream_id}:\n"
            f"--- PROMPT START ---\n"
            f"{full_prompt}\n"
            f"--- PROMPT END ---"
        )

        return full_prompt


# 全局提示词生成器实例
_prompt_generator: UnifiedPromptGenerator | None = None


def get_unified_prompt_generator() -> UnifiedPromptGenerator:
    """获取全局提示词生成器实例"""
    global _prompt_generator
    if _prompt_generator is None:
        _prompt_generator = UnifiedPromptGenerator()
    return _prompt_generator


async def generate_unified_response(
    session: KokoroSession,
    user_name: str,
    situation_type: str = "new_message",
    chat_stream: Optional["ChatStream"] = None,
    available_actions: dict | None = None,
    extra_context: dict | None = None,
) -> LLMResponse:
    """
    统一模式：单次 LLM 调用生成完整响应

    调用方式：
    - 使用 UnifiedPromptGenerator 生成 System + User 提示词
    - 使用 replyer 模型调用 LLM
    - 解析 JSON 响应（thought + actions + max_wait_seconds）

    Args:
        session: 会话对象
        user_name: 用户名称
        situation_type: 情况类型 (new_message/timeout/proactive)
        chat_stream: 聊天流对象
        available_actions: 可用动作字典
        extra_context: 额外上下文

    Returns:
        LLMResponse 对象，包含完整的思考和动作
    """
    try:
        prompt_generator = get_unified_prompt_generator()
        extra_context = extra_context or {}

        # 获取上下文数据（关系、记忆等）
        context_data = await _build_context_data(user_name, chat_stream, session.user_id)

        # 根据情况类型选择提示词生成方法
        if situation_type == "timeout":
            system_prompt, user_prompt = await prompt_generator.generate_timeout_prompt(
                session=session,
                available_actions=available_actions,
                context_data=context_data,
                chat_stream=chat_stream,
            )
        elif situation_type == "proactive":
            trigger_context = extra_context.get("trigger_reason", "")
            system_prompt, user_prompt = await prompt_generator.generate_proactive_prompt(
                session=session,
                trigger_context=trigger_context,
                available_actions=available_actions,
                context_data=context_data,
                chat_stream=chat_stream,
            )
        else:
            # 默认为回应消息场景 (new_message, reply_in_time, reply_late)
            # 获取最后一条用户消息
            message_content, sender_name, sender_id, message_time, all_unread = _get_last_user_message(
                session, user_name, chat_stream
            )

            system_prompt, user_prompt = await prompt_generator.generate_responding_prompt(
                session=session,
                message_content=message_content,
                sender_name=sender_name,
                sender_id=sender_id,
                message_time=message_time,
                available_actions=available_actions,
                context=chat_stream.context if chat_stream else None,
                context_data=context_data,
                chat_stream=chat_stream,
                all_unread_messages=all_unread,
            )

        # 构建完整提示词
        prompt = prompt_generator.build_messages_for_llm(
            system_prompt,
            user_prompt,
            stream_id=chat_stream.stream_id if chat_stream else "",
        )

        # 显示提示词（调试模式 - 只有在配置中开启时才输出）
        if global_config and global_config.debug.show_prompt:
            logger.info(
                f"[KFC] 完整提示词 (stream={chat_stream.stream_id if chat_stream else 'unknown'}):\n"
                f"--- PROMPT START ---\n"
                f"{prompt}\n"
                f"--- PROMPT END ---"
            )

        # 获取 replyer_private 模型配置并调用 LLM（KFC私聊专用）
        models = llm_api.get_available_models()
        replyer_config = models.get("replyer_private")

        if not replyer_config:
            logger.error("[KFC Unified] 未找到 replyer_private 模型配置")
            return LLMResponse.create_error_response("未找到 replyer_private 模型配置")

        # 调用 LLM（使用合并后的提示词）
        success, raw_response, _reasoning, _model_name = await llm_api.generate_with_model(
            prompt=prompt,
            model_config=replyer_config,
            request_type="kokoro_flow_chatter.unified",
        )

        if not success:
            logger.error(f"[KFC Unified] LLM 调用失败: {raw_response}")
            return LLMResponse.create_error_response(raw_response)

        # 输出原始 JSON 响应（DEBUG 级别，用于调试）
        logger.debug(
            f"Raw JSON response from LLM for stream {chat_stream.stream_id if chat_stream else 'unknown'}:\n"
            f"--- JSON START ---\n"
            f"{raw_response}\n"
            f"--- JSON END ---"
        )

        # 解析响应
        return _parse_unified_response(raw_response, chat_stream.stream_id if chat_stream else None)

    except Exception as e:
        logger.error(f"[KFC Unified] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return LLMResponse.create_error_response(str(e))


async def _build_context_data(
    user_name: str,
    chat_stream: Optional["ChatStream"],
    user_id: str | None = None,
) -> dict[str, str]:
    """
    构建上下文数据（关系、记忆、工具、表达习惯等）
    """
    logger.debug(f"[KFC Unified] 开始构建上下文数据: user={user_name}")

    if not chat_stream:
        logger.warning("[KFC Unified] 无 chat_stream，返回默认上下文")
        return {
            "relation_info": f"你与 {user_name} 还不太熟悉，这是早期的交流阶段。",
            "memory_block": "",
            "tool_info": "",
            "expression_habits": "",
            "schedule": "",
        }

    try:
        from .context_builder import KFCContextBuilder

        builder = KFCContextBuilder(chat_stream)

        # 获取最近的消息作为 target_message（用于记忆检索）
        target_message = ""
        if chat_stream.context:
            unread = chat_stream.context.get_unread_messages()
            if unread:
                target_message = unread[-1].processed_plain_text or unread[-1].display_message or ""

        context_data = await builder.build_all_context(
            sender_name=user_name,
            target_message=target_message,
            context=chat_stream.context,
            user_id=user_id,
        )

        # 打印关键信息
        memory_len = len(context_data.get("memory_block", ""))
        tool_len = len(context_data.get("tool_info", ""))
        logger.debug(f"[KFC Unified] 上下文构建完成: memory_block={memory_len}字符, tool_info={tool_len}字符")

        return context_data

    except Exception as e:
        logger.error(f"[KFC Unified] 构建上下文数据失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "relation_info": f"你与 {user_name} 还不太熟悉，这是早期的交流阶段。",
            "memory_block": "",
            "tool_info": "",
            "expression_habits": "",
            "schedule": "",
        }


def _get_last_user_message(
    session: KokoroSession,
    user_name: str,
    chat_stream: Optional["ChatStream"],
) -> tuple[str, str, str, float, list | None]:
    """
    获取最后一条用户消息

    Returns:
        tuple: (消息内容, 发送者名称, 发送者ID, 消息时间, 所有未读消息列表)
    """
    message_content = ""
    sender_name = user_name
    sender_id = session.user_id or ""
    message_time = time.time()
    all_unread = None

    # 从 chat_stream 获取未读消息
    if chat_stream and chat_stream.context:
        unread = chat_stream.context.get_unread_messages()
        if unread:
            all_unread = unread if len(unread) > 1 else None
            last_msg = unread[-1]
            message_content = last_msg.processed_plain_text or last_msg.display_message or ""
            if last_msg.user_info:
                sender_name = last_msg.user_info.user_nickname or user_name
                sender_id = str(last_msg.user_info.user_id)
            message_time = last_msg.time or time.time()

    # 如果没有从 chat_stream 获取到，从 mental_log 获取
    if not message_content:
        for entry in reversed(session.mental_log):
            if entry.event_type == EventType.USER_MESSAGE:
                message_content = entry.content or ""
                sender_name = entry.user_name or user_name
                message_time = entry.timestamp
                break

    return message_content, sender_name, sender_id, message_time, all_unread


def _parse_unified_response(raw_response: str, stream_id: str | None = None) -> LLMResponse:
    """
    解析统一模式的 LLM 响应

    响应格式：
    {
        "thought": "...",
        "expected_user_reaction": "...",
        "max_wait_seconds": 300,
        "actions": [{"type": "reply", "content": "..."}]
    }
    """
    data = extract_and_parse_json(raw_response, strict=False)

    if not data or not isinstance(data, dict):
        logger.warning(f"[KFC Unified] 无法解析 JSON: {raw_response[:200]}...")
        return LLMResponse.create_error_response("无法解析响应格式")

    # 兼容旧版的字段名
    # expected_user_reaction -> expected_reaction
    if "expected_user_reaction" in data and "expected_reaction" not in data:
        data["expected_reaction"] = data["expected_user_reaction"]

    # 兼容旧版的 reply -> kfc_reply
    actions = data.get("actions", [])
    for action in actions:
        if isinstance(action, dict):
            if action.get("type") == "reply":
                action["type"] = "kfc_reply"

    response = LLMResponse.from_dict(data)

    # 美化日志输出：内心思考 + 回复内容
    _log_pretty_response(response, stream_id)

    return response


def _log_pretty_response(response: LLMResponse, stream_id: str | None = None) -> None:
    """简洁输出 LLM 响应日志"""
    if not response.thought and not response.actions:
        logger.warning("[KFC] 响应为空")
        return

    stream_tag = f"({stream_id[:8]}) " if stream_id else ""

    # 收集回复内容和其他动作
    replies = []
    actions = []
    for action in response.actions:
        if action.type == "kfc_reply":
            content = action.params.get("content", "")
            if content:
                replies.append(content)
        elif action.type not in ("do_nothing", "no_action"):
            actions.append(action.type)

    # 逐行输出，简洁明了
    if response.thought:
        logger.info(f"[KFC] {stream_tag}💭 {response.thought}")

    for i, reply in enumerate(replies):
        if len(replies) > 1:
            logger.info(f"[KFC] 💬 [{i+1}] {reply}")
        else:
            logger.info(f"[KFC] 💬 {reply}")

    if actions:
        logger.info(f"[KFC] 🎯 {', '.join(actions)}")

    if response.max_wait_seconds > 0 or response.expected_reaction:
        meta = f"⏱ {response.max_wait_seconds}s" if response.max_wait_seconds > 0 else ""
        if response.expected_reaction:
            meta += f" 预期: {response.expected_reaction}"
        logger.info(f"[KFC] {meta.strip()}")
