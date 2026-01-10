"""
Kokoro Flow Chatter - 提示词构建器

使用项目统一的 Prompt 管理系统构建提示词
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.chat.utils.prompt import global_prompt_manager
from src.common.logger import get_logger
from src.config.config import global_config

from ..models import EventType, MentalLogEntry
from ..session import KokoroSession

# 导入模板注册（确保模板被注册到 global_prompt_manager）
from . import prompts as _  # noqa: F401
from .prompts import PROMPT_NAMES

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream

logger = get_logger("kfc_prompt_builder")


class PromptBuilder:
    """
    提示词构建器

    使用统一的 Prompt 管理系统构建提示词：
    1. 构建活动流（从 mental_log 生成线性叙事）
    2. 构建当前情况描述
    3. 使用 global_prompt_manager 格式化最终提示词
    """

    def __init__(self):
        self._context_builder = None

    async def build_planner_prompt(
        self,
        session: KokoroSession,
        user_name: str,
        situation_type: str = "new_message",
        chat_stream: Optional["ChatStream"] = None,
        available_actions: dict | None = None,
        extra_context: dict | None = None,
    ) -> str:
        """
        构建规划器提示词（用于生成行动计划）

        Args:
            session: 会话对象
            user_name: 用户名称
            situation_type: 情况类型 (new_message/reply_in_time/reply_late/timeout/proactive)
            chat_stream: 聊天流对象
            available_actions: 可用动作字典
            extra_context: 额外上下文（如 trigger_reason）

        Returns:
            完整的规划器提示词
        """
        extra_context = extra_context or {}

        # 获取 user_id（从 session 中）
        user_id = session.user_id if session else None

        # 1. 构建人设块
        persona_block = self._build_persona_block()

        # 1.5. 构建安全互动准则块
        safety_guidelines_block = self._build_safety_guidelines_block()

        # 1.6. 构建自定义决策提示词块
        custom_decision_block = self._build_custom_decision_block()

        # 2. Planner（分离模式）不做重型上下文构建：记忆检索/工具信息/表达习惯检索等会显著拖慢处理
        #    这些信息留给 Replyer（生成最终回复文本）阶段再获取。
        relation_block = ""
        memory_block = ""
        tool_info = ""
        expression_habits = ""
        schedule_block = ""

        # Planner 阶段也获取日程信息，因为它对决策很重要（比如深夜不该建议去逛街）
        if chat_stream:
            try:
                if self._context_builder is None:
                    from ..context_builder import KFCContextBuilder
                    self._context_builder = KFCContextBuilder
                builder = self._context_builder(chat_stream)
                schedule_block = await builder._build_schedule_block()
            except Exception as e:
                logger.debug(f"Planner 获取日程信息失败: {e}")

        # 3. 构建活动流
        activity_stream = await self._build_activity_stream(session, user_name)

        # 4. 构建当前情况
        current_situation = await self._build_current_situation(
            session, user_name, situation_type, extra_context
        )

        # 5. 构建聊天历史总览
        chat_history_block = await self._build_chat_history_block(chat_stream)

        # 6. 构建可用动作
        actions_block = self._build_actions_block(available_actions)

        # 7. 获取规划器输出格式
        output_format = await self._get_planner_output_format()

        # 8. 使用统一的 prompt 管理系统格式化
        prompt = await global_prompt_manager.format_prompt(
            PROMPT_NAMES["main"],
            user_name=user_name,
            persona_block=persona_block,
            safety_guidelines_block=safety_guidelines_block,
            custom_decision_block=custom_decision_block,
            relation_block=relation_block,
            memory_block=memory_block or "（暂无相关记忆）",
            tool_info=tool_info or "（暂无工具信息）",
            expression_habits=expression_habits or "（根据自然对话风格回复即可）",
            activity_stream=activity_stream or "（这是你们第一次聊天）",
            current_situation=current_situation,
            schedule_block=schedule_block,
            chat_history_block=chat_history_block,
            available_actions=actions_block,
            output_format=output_format,
        )

        return prompt

    async def build_replyer_prompt(
        self,
        session: KokoroSession,
        user_name: str,
        thought: str,
        situation_type: str = "new_message",
        chat_stream: Optional["ChatStream"] = None,
        extra_context: dict | None = None,
    ) -> str:
        """
        构建回复器提示词（用于生成自然的回复文本）

        Args:
            session: 会话对象
            user_name: 用户名称
            thought: 规划器生成的想法
            situation_type: 情况类型
            chat_stream: 聊天流对象
            extra_context: 额外上下文

        Returns:
            完整的回复器提示词
        """
        extra_context = extra_context or {}

        # 获取 user_id
        user_id = session.user_id if session else None

        # 1. 构建人设块
        persona_block = self._build_persona_block()

        # 1.5. 构建安全互动准则块
        safety_guidelines_block = self._build_safety_guidelines_block()

        # 2. 使用 context_builder 获取关系、记忆、表达习惯等
        context_data = await self._build_context_data(user_name, chat_stream, user_id)
        relation_block = context_data.get("relation_info", f"你与 {user_name} 还不太熟悉，这是早期的交流阶段。")
        memory_block = context_data.get("memory_block", "")
        tool_info = context_data.get("tool_info", "")
        expression_habits = self._build_combined_expression_block(context_data.get("expression_habits", ""))
        schedule_block = context_data.get("schedule", "")

        # 3. 构建活动流
        activity_stream = await self._build_activity_stream(session, user_name)

        # 4. 构建当前情况（回复器专用，简化版，不包含决策语言）
        current_situation = await self._build_replyer_situation(
            session, user_name, situation_type, extra_context
        )

        # 5. 构建聊天历史总览
        chat_history_block = await self._build_chat_history_block(chat_stream)

        # 6. 构建回复情景上下文
        reply_context = await self._build_reply_context(
            session, user_name, situation_type, extra_context
        )

        # 7. 使用回复器专用模板
        prompt = await global_prompt_manager.format_prompt(
            PROMPT_NAMES["replyer"],
            user_name=user_name,
            persona_block=persona_block,
            safety_guidelines_block=safety_guidelines_block,
            relation_block=relation_block,
            memory_block=memory_block or "（暂无相关记忆）",
            tool_info=tool_info or "（暂无工具信息）",
            activity_stream=activity_stream or "（这是你们第一次聊天）",
            current_situation=current_situation,
            schedule_block=schedule_block,
            chat_history_block=chat_history_block,
            expression_habits=expression_habits or "（根据自然对话风格回复即可）",
            thought=thought,
            reply_context=reply_context,
        )

        return prompt

    def _build_persona_block(self) -> str:
        """构建人设块"""
        if global_config is None:
            return "你是一个温暖、真诚的人。"

        personality = global_config.personality
        parts = []

        if personality.personality_core:
            parts.append(personality.personality_core)

        if personality.personality_side:
            parts.append(personality.personality_side)

        if personality.identity:
            parts.append(personality.identity)

        background_story = getattr(personality, "background_story", "")
        if background_story:
            parts.append(f"## 背景故事（请理解并作为行动依据，但不要在对话中直接复述）\n{background_story}")

        return "\n\n".join(parts) if parts else "你是一个温暖、真诚的人。"

    def _build_safety_guidelines_block(self) -> str:
        """
        构建安全互动准则块

        从配置中读取 safety_guidelines，构建成提示词格式
        """
        if global_config is None:
            return ""

        safety_guidelines = global_config.personality.safety_guidelines
        if not safety_guidelines:
            return ""

        guidelines_text = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(safety_guidelines))
        return f"""在任何情况下，你都必须遵守以下由你的设定者为你定义的原则：
{guidelines_text}
如果遇到违反上述原则的请求，请在保持你核心人设的同时，以合适的方式进行回应。"""

    def _build_custom_decision_block(self) -> str:
        """
        构建自定义决策提示词块

        从配置中读取 custom_decision_prompt，用于指导KFC的决策行为
        类似于AFC的planner_custom_prompt_content
        """
        from ..config import get_config

        kfc_config = get_config()
        custom_prompt = getattr(kfc_config, "custom_decision_prompt", "")

        if not custom_prompt or not custom_prompt.strip():
            return ""

        return custom_prompt.strip()

    def _build_combined_expression_block(self, learned_habits: str) -> str:
        """
        构建合并后的表达习惯块

        合并：
        - 说话风格（来自人设配置 personality.reply_style）
        - 表达习惯（来自学习系统）
        """
        parts = []

        # 1. 添加说话风格（来自配置）
        if global_config and global_config.personality.reply_style:
            parts.append(f"**说话风格**：\n你必须参考你的说话风格：\n{global_config.personality.reply_style}")

        # 2. 添加学习到的表达习惯
        if learned_habits and learned_habits.strip():
            # 如果 learned_habits 已经有标题，直接追加；否则添加标题
            parts.append("你可以参考以下的语言习惯，当情景合适就使用，但不要生硬使用，以合理的方式结合到你的回复中：")
            if learned_habits.startswith("### "):
                # 移除原有标题，统一格式
                lines = learned_habits.split("\n")
                content_lines = [l for l in lines if not l.startswith("### ")]
                parts.append("\n".join(content_lines).strip())
            else:
                parts.append(learned_habits)

        if parts:
            return "\n\n".join(parts)

        return ""

    def _build_last_bot_action_block(self, session: KokoroSession | None) -> str:
        """
        构建“最近一次Bot动作/发言”块（用于插入到当前情况里）

        目的：让模型在决策时能显式参考“我刚刚做过什么/说过什么”，降低长上下文里漏细节的概率。
        """
        if not session or not getattr(session, "mental_log", None):
            return ""

        last_planning_entry: MentalLogEntry | None = None
        for entry in reversed(session.mental_log):
            if entry.event_type == EventType.BOT_PLANNING:
                last_planning_entry = entry
                break

        if not last_planning_entry:
            return ""

        actions_desc = self._format_actions(last_planning_entry.actions)

        last_message = ""
        for action in last_planning_entry.actions:
            if action.get("type") == "kfc_reply":
                content = (action.get("content") or "").strip()
                if content:
                    last_message = content

        if last_message and len(last_message) > 80:
            last_message = last_message[:80] + "..."

        lines = [f"你最近一次执行的动作是：{actions_desc}"]
        if last_message:
            lines.append(f"你上一次发出的消息是：「{last_message}」")

        return "\n".join(lines) + "\n\n"

    async def _build_context_data(
        self,
        user_name: str,
        chat_stream: Optional["ChatStream"],
        user_id: str | None = None,
        session: KokoroSession | None = None,
        situation_type: str = "new_message",
    ) -> dict[str, str]:
        """
        使用 KFCContextBuilder 构建完整的上下文数据

        包括：关系信息、记忆、表达习惯等
        """
        if not chat_stream:
            return {
                "relation_info": f"你与 {user_name} 还不太熟悉，这是早期的交流阶段。",
                "memory_block": "",
                "tool_info": "",
                "expression_habits": "",
            }

        try:
            # 延迟导入上下文构建器
            if self._context_builder is None:
                from ..context_builder import KFCContextBuilder
                self._context_builder = KFCContextBuilder

            builder = self._context_builder(chat_stream)

            # 获取用于记忆检索的查询文本
            target_message = await self._get_memory_search_query(
                chat_stream=chat_stream,
                session=session,
                situation_type=situation_type,
                user_name=user_name,
            )

            context_data = await builder.build_all_context(
                sender_name=user_name,
                target_message=target_message,
                context=chat_stream.context,
                user_id=user_id,
            )

            return context_data

        except Exception as e:
            logger.warning(f"构建上下文数据失败: {e}")
            return {
                "relation_info": f"你与 {user_name} 还不太熟悉，这是早期的交流阶段。",
                "memory_block": "",
                "tool_info": "",
                "expression_habits": "",
            }

    async def _get_memory_search_query(
        self,
        chat_stream: Optional["ChatStream"],
        session: KokoroSession | None,
        situation_type: str,
        user_name: str,
    ) -> str:
        """
        根据场景类型获取合适的记忆搜索查询文本

        策略：
        1. 优先使用未读消息（new_message/reply_in_time/reply_late）
        2. 如果没有未读消息（timeout/proactive），使用最近的历史消息
        3. 如果历史消息也为空，从 session 的 mental_log 中提取
        4. 最后回退到用户名作为查询

        Args:
            chat_stream: 聊天流对象
            session: KokoroSession 会话对象
            situation_type: 情况类型
            user_name: 用户名称

        Returns:
            用于记忆搜索的查询文本
        """
        target_message = ""

        # 策略1: 优先从未读消息获取（适用于 new_message/reply_in_time/reply_late）
        if chat_stream and chat_stream.context:
            unread = chat_stream.context.get_unread_messages()
            if unread:
                target_message = unread[-1].processed_plain_text or unread[-1].display_message or ""
                if target_message:
                    logger.debug(f"[记忆搜索] 使用未读消息作为查询: {target_message[:50]}...")
                    return target_message

        # 策略2: 从最近的历史消息获取（适用于 timeout/proactive）
        if chat_stream and chat_stream.context:
            history_messages = chat_stream.context.history_messages
            if history_messages:
                # 获取最近的几条非通知消息，组合成查询
                recent_texts = []
                for msg in reversed(history_messages[-5:]):
                    content = getattr(msg, "processed_plain_text", "") or getattr(msg, "display_message", "")
                    if content and not getattr(msg, "is_notify", False):
                        recent_texts.append(content)
                        if len(recent_texts) >= 3:
                            break

                if recent_texts:
                    target_message = " ".join(reversed(recent_texts))
                    logger.debug(f"[记忆搜索] 使用历史消息作为查询 (situation={situation_type}): {target_message[:80]}...")
                    return target_message

        # 策略3: 从 session 的 mental_log 中提取（超时/主动思考场景的最后手段）
        if session and situation_type in ("timeout", "proactive"):
            entries = session.get_recent_entries(limit=10)
            recent_texts = []

            for entry in reversed(entries):
                # 从用户消息中提取
                if entry.event_type == EventType.USER_MESSAGE and entry.content:
                    recent_texts.append(entry.content)
                # 从 bot 的预期反应中提取（可能包含相关话题）
                elif entry.event_type == EventType.BOT_PLANNING and entry.expected_reaction:
                    recent_texts.append(entry.expected_reaction)

                if len(recent_texts) >= 3:
                    break

            if recent_texts:
                target_message = " ".join(reversed(recent_texts))
                logger.debug(f"[记忆搜索] 使用 mental_log 作为查询 (situation={situation_type}): {target_message[:80]}...")
                return target_message

        # 策略4: 最后回退 - 使用用户名 + 场景描述
        if situation_type == "timeout":
            target_message = f"与 {user_name} 的对话 等待回复"
        elif situation_type == "proactive":
            target_message = f"与 {user_name} 的对话 主动发起聊天"
        else:
            target_message = f"与 {user_name} 的对话"

        logger.debug(f"[记忆搜索] 使用回退查询 (situation={situation_type}): {target_message}")
        return target_message

    def _get_latest_user_message(self, session: KokoroSession | None) -> str:
        """
        获取最新的用户消息内容

        Args:
            session: KokoroSession 会话对象

        Returns:
            最新用户消息的内容，如果没有则返回提示文本
        """
        if not session:
            return "（未知消息）"

        # 从 mental_log 中获取最新的用户消息
        entries = session.get_recent_entries(limit=10)
        for entry in reversed(entries):
            if entry.event_type == EventType.USER_MESSAGE and entry.content:
                return entry.content

        return "（消息内容不可用）"

    async def _build_chat_history_block(
        self,
        chat_stream: Optional["ChatStream"],
    ) -> str:
        """
        构建聊天历史总览块

        从 chat_stream 获取历史消息，格式化为可读的聊天记录
        类似于 AFC 的已读历史板块
        """
        if not chat_stream:
            return "（暂无聊天记录）"

        try:
            from src.chat.utils.chat_message_builder import (
                build_readable_messages_with_id,
                get_raw_msg_before_timestamp_with_chat,
            )
            from src.common.data_models.database_data_model import DatabaseMessages

            stream_context = chat_stream.context

            # 获取已读消息
            history_messages = stream_context.history_messages if stream_context else []

            if not history_messages:
                # 如果内存中没有历史消息，从数据库加载
                fallback_messages_dicts = await get_raw_msg_before_timestamp_with_chat(
                    chat_id=chat_stream.stream_id,
                    timestamp=time.time(),
                    limit=30,  # 限制数量，私聊不需要太多
                )
                history_messages = [
                    DatabaseMessages.from_dict(msg_dict) for msg_dict in fallback_messages_dicts
                ]

            if not history_messages:
                return "（暂无聊天记录）"

            # 过滤非文本消息（如戳一戳、禁言等系统通知）
            text_messages = self._filter_text_messages(history_messages)

            if not text_messages:
                return "（暂无聊天记录）"

            # 构建可读消息
            chat_content, _ = await build_readable_messages_with_id(
                messages=[msg.flatten() for msg in text_messages[-30:]],  # 最多30条
                timestamp_mode="normal_no_YMD",
                truncate=False,
                show_actions=False,
            )

            return chat_content if chat_content else "（暂无聊天记录）"

        except Exception as e:
            logger.warning(f"构建聊天历史块失败: {e}")
            return "（获取聊天记录失败）"

    def _filter_text_messages(self, messages: list) -> list:
        """
        过滤非文本消息

        移除系统通知消息（如戳一戳、禁言等），只保留正常的文本聊天消息

        Args:
            messages: 消息列表（DatabaseMessages 对象）

        Returns:
            过滤后的消息列表
        """
        filtered = []
        for msg in messages:
            # 跳过系统通知消息（戳一戳、禁言等）
            if getattr(msg, "is_notify", False):
                continue

            # 跳过没有实际文本内容的消息
            content = getattr(msg, "processed_plain_text", "") or getattr(msg, "display_message", "")
            if not content or not content.strip() or content == "":
                continue

            filtered.append(msg)

        return filtered

    async def _build_activity_stream(
        self,
        session: KokoroSession,
        user_name: str,
    ) -> str:
        """
        构建活动流

        将 mental_log 中的事件按时间顺序转换为线性叙事
        支持线性叙事或结构化表格两种格式（可通过配置切换）
        """
        from ..config import get_config

        kfc_config = get_config()
        prompt_cfg = getattr(kfc_config, "prompt", None)
        max_entries = getattr(prompt_cfg, "max_activity_entries", 30) if prompt_cfg else 30
        max_entry_length = getattr(prompt_cfg, "max_entry_length", 500) if prompt_cfg else 500
        stream_format = (
            getattr(prompt_cfg, "activity_stream_format", "narrative") if prompt_cfg else "narrative"
        )

        entries = session.get_recent_entries(limit=max_entries)
        if not entries:
            return ""

        stream_format = (stream_format or "narrative").strip().lower()
        if stream_format == "table":
            return self._build_activity_stream_table(entries, user_name, max_entry_length)
        if stream_format == "both":
            table = self._build_activity_stream_table(entries, user_name, max_entry_length)
            narrative = await self._build_activity_stream_narrative(entries, user_name)
            return "\n\n".join([p for p in (table, narrative) if p])

        return await self._build_activity_stream_narrative(entries, user_name)

    async def _build_activity_stream_narrative(
        self,
        entries: list[MentalLogEntry],
        user_name: str,
    ) -> str:
        """构建线性叙事活动流（旧格式）"""
        parts: list[str] = []
        for entry in entries:
            part = await self._format_entry(entry, user_name)
            if part:
                parts.append(part)

        return "\n\n".join(parts)

    def _build_activity_stream_table(
        self,
        entries: list[MentalLogEntry],
        user_name: str,
        max_cell_length: int = 500,
    ) -> str:
        """
        构建结构化表格活动流（更高信息密度）

        统一列：序号 / 时间 / 事件类型 / 内容 / 想法 / 行动 / 结果
        """

        def truncate(text: str, limit: int) -> str:
            if not text:
                return ""
            if limit <= 0:
                return text
            text = text.strip()
            return text if len(text) <= limit else (text[: max(0, limit - 1)] + "…")

        def md_cell(value: str) -> str:
            value = (value or "").replace("\r\n", "\n").replace("\n", "<br>")
            value = value.replace("|", "\\|")
            return truncate(value, max_cell_length)

        event_type_alias = {
            EventType.USER_MESSAGE: "用户消息",
            EventType.BOT_PLANNING: "你的决策",
            EventType.WAITING_UPDATE: "等待中",
            EventType.PROACTIVE_TRIGGER: "主动触发",
        }

        header = ["#", "时间", "类型", "内容", "想法", "行动", "结果"]
        lines = [
            "|" + "|".join(header) + "|",
            "|" + "|".join(["---"] * len(header)) + "|",
        ]

        for idx, entry in enumerate(entries, 1):
            time_str = entry.get_time_str()
            type_str = event_type_alias.get(entry.event_type, str(entry.event_type))

            content = ""
            thought = ""
            action = ""
            result = ""

            if entry.event_type == EventType.USER_MESSAGE:
                content = entry.content
                reply_status = entry.metadata.get("reply_status")
                if reply_status in ("in_time", "late"):
                    elapsed_min = entry.metadata.get("elapsed_seconds", 0) / 60
                    max_wait_min = entry.metadata.get("max_wait_seconds", 0) / 60
                    status_cn = "及时" if reply_status == "in_time" else "迟到"
                    result = f"回复{status_cn}（等{elapsed_min:.1f}/{max_wait_min:.1f}分钟）"

            elif entry.event_type == EventType.BOT_PLANNING:
                thought = entry.thought or "（无）"
                action = self._format_actions(entry.actions)
                if entry.max_wait_seconds > 0:
                    wait_min = entry.max_wait_seconds / 60
                    expected = entry.expected_reaction or "（无）"
                    result = f"等待≤{wait_min:.1f}分钟；期待={expected}"
                else:
                    result = "不等待"

            elif entry.event_type == EventType.WAITING_UPDATE:
                thought = entry.waiting_thought or "还在等…"
                elapsed_min = entry.elapsed_seconds / 60
                mood = (entry.mood or "").strip()
                result = f"已等{elapsed_min:.1f}分钟" + (f"；心情={mood}" if mood else "")

            elif entry.event_type == EventType.PROACTIVE_TRIGGER:
                silence = entry.metadata.get("silence_duration", "一段时间")
                result = f"沉默{silence}"

            row = [
                str(idx),
                md_cell(time_str),
                md_cell(type_str),
                md_cell(content),
                md_cell(thought),
                md_cell(action),
                md_cell(result),
            ]
            lines.append("|" + "|".join(row) + "|")

        return "（结构化活动流表；按时间顺序）\n" + "\n".join(lines)

    async def _format_entry(self, entry: MentalLogEntry, user_name: str) -> str:
        """格式化单个活动日志条目"""

        if entry.event_type == EventType.USER_MESSAGE:
            # 用户消息
            result = await global_prompt_manager.format_prompt(
                PROMPT_NAMES["entry_user_message"],
                time=entry.get_time_str(),
                user_name=entry.user_name or user_name,
                content=entry.content,
            )

            # 如果有回复状态元数据，添加说明
            reply_status = entry.metadata.get("reply_status")
            if reply_status == "in_time":
                elapsed = entry.metadata.get("elapsed_seconds", 0) / 60
                max_wait = entry.metadata.get("max_wait_seconds", 0) / 60
                result += await global_prompt_manager.format_prompt(
                    PROMPT_NAMES["entry_reply_in_time"],
                    elapsed_minutes=elapsed,
                    max_wait_minutes=max_wait,
                )
            elif reply_status == "late":
                elapsed = entry.metadata.get("elapsed_seconds", 0) / 60
                max_wait = entry.metadata.get("max_wait_seconds", 0) / 60
                result += await global_prompt_manager.format_prompt(
                    PROMPT_NAMES["entry_reply_late"],
                    elapsed_minutes=elapsed,
                    max_wait_minutes=max_wait,
                )

            return result

        elif entry.event_type == EventType.BOT_PLANNING:
            # Bot 规划
            actions_desc = self._format_actions(entry.actions)

            if entry.max_wait_seconds > 0:
                return await global_prompt_manager.format_prompt(
                    PROMPT_NAMES["entry_bot_planning"],
                    thought=entry.thought or "（没有特别的想法）",
                    actions_description=actions_desc,
                    expected_reaction=entry.expected_reaction or "随便怎么回应都行",
                    max_wait_minutes=entry.max_wait_seconds / 60,
                )
            else:
                return await global_prompt_manager.format_prompt(
                    PROMPT_NAMES["entry_bot_planning_no_wait"],
                    thought=entry.thought or "（没有特别的想法）",
                    actions_description=actions_desc,
                )

        elif entry.event_type == EventType.WAITING_UPDATE:
            # 等待中心理变化
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["entry_waiting_update"],
                elapsed_minutes=entry.elapsed_seconds / 60,
                waiting_thought=entry.waiting_thought or "还在等...",
            )

        elif entry.event_type == EventType.PROACTIVE_TRIGGER:
            # 主动思考触发
            silence = entry.metadata.get("silence_duration", "一段时间")
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["entry_proactive_trigger"],
                silence_duration=silence,
            )

        return ""

    def _format_actions(self, actions: list[dict]) -> str:
        """格式化动作列表为可读描述"""
        if not actions:
            return "（无动作）"

        descriptions = []
        for action in actions:
            action_type = action.get("type", "unknown")

            if action_type == "kfc_reply":
                content = action.get("content", "")
                if len(content) > 50:
                    content = content[:50] + "..."
                descriptions.append(f"发送消息：「{content}」")
            elif action_type == "poke_user":
                descriptions.append("戳了戳对方")
            elif action_type == "do_nothing":
                descriptions.append("什么都不做")
            elif action_type == "send_emoji":
                emoji = action.get("emoji", "")
                descriptions.append(f"发送表情：{emoji}")
            else:
                descriptions.append(f"执行动作：{action_type}")

        return "、".join(descriptions)

    async def _build_current_situation(
        self,
        session: KokoroSession,
        user_name: str,
        situation_type: str,
        extra_context: dict,
    ) -> str:
        """构建当前情况描述"""
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        last_action_block = self._build_last_bot_action_block(session)

        # 如果之前没有设置等待时间（max_wait_seconds == 0），视为 new_message
        if situation_type in ("reply_in_time", "reply_late"):
            max_wait = session.waiting_config.max_wait_seconds
            if max_wait <= 0:
                situation_type = "new_message"

        if situation_type == "new_message":
            # 获取最新消息内容
            latest_message = self._get_latest_user_message(session)
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["situation_new_message"],
                current_time=current_time,
                last_action_block=last_action_block,
                user_name=user_name,
                latest_message=latest_message,
            )

        elif situation_type == "reply_in_time":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            latest_message = self._get_latest_user_message(session)
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["situation_reply_in_time"],
                current_time=current_time,
                last_action_block=last_action_block,
                user_name=user_name,
                elapsed_minutes=elapsed / 60,
                max_wait_minutes=max_wait / 60,
                latest_message=latest_message,
            )

        elif situation_type == "reply_late":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            latest_message = self._get_latest_user_message(session)
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["situation_reply_late"],
                current_time=current_time,
                last_action_block=last_action_block,
                user_name=user_name,
                elapsed_minutes=elapsed / 60,
                max_wait_minutes=max_wait / 60,
                latest_message=latest_message,
            )

        elif situation_type == "timeout":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            expected = session.waiting_config.expected_reaction

            # 构建连续超时上下文
            timeout_context_parts = []

            # 添加真正追问次数警告（只有真正发了消息才算追问）
            followup_count = extra_context.get("followup_count", 0)
            if followup_count >= 2:
                timeout_context_parts.append(
                    f"⚠️ **强烈建议**: 你已经连续追问了 {followup_count} 次，对方仍未回复。"
                    "**极度推荐选择 `do_nothing` 或主动结束话题**。"
                    "对方可能在忙或需要空间，不是所有人都能一直在线。给彼此一些空间会更好。"
                )
            elif followup_count == 1:
                timeout_context_parts.append(
                    "📝 温馨提醒：这是你第2次等待回复（已追问1次）。"
                    "可以再试着追问一次，但如果对方还是没回复，**强烈建议**之后选择 `do_nothing` 或结束话题。"
                )
            elif followup_count == 0:
                timeout_context_parts.append(
                    "💭 追问提示：如果对方一段时间未回复，可以适当追问一次。"
                    "但要记住对方可能在忙，建议最多追问2次左右，之后给对方一些空间。"
                )

            # 添加距离用户上次回复的时间
            time_since_user_reply_str = extra_context.get("time_since_user_reply_str")
            if time_since_user_reply_str:
                timeout_context_parts.append(f"距离 {user_name} 上一次回复你已经过去了 {time_since_user_reply_str}。")

            timeout_context = "\n".join(timeout_context_parts)
            if timeout_context:
                timeout_context = "\n" + timeout_context + "\n"

            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["situation_timeout"],
                current_time=current_time,
                last_action_block=last_action_block,
                user_name=user_name,
                elapsed_minutes=elapsed / 60,
                max_wait_minutes=max_wait / 60,
                expected_reaction=expected or "对方能回复点什么",
                timeout_context=timeout_context,
            )

        elif situation_type == "proactive":
            silence = extra_context.get("silence_duration", "一段时间")
            trigger_reason = extra_context.get("trigger_reason", "")
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["situation_proactive"],
                current_time=current_time,
                last_action_block=last_action_block,
                user_name=user_name,
                silence_duration=silence,
                trigger_reason=trigger_reason,
            )

        # 默认使用 new_message
        return await global_prompt_manager.format_prompt(
            PROMPT_NAMES["situation_new_message"],
            current_time=current_time,
            user_name=user_name,
            last_action_block=last_action_block,
        )

    def _build_actions_block(self, available_actions: dict | None) -> str:
        """
        构建可用动作块

        参考 AFC planner 的格式，为每个动作展示：
        - 动作名和描述
        - 使用场景
        - JSON 示例（含参数）
        """
        if not available_actions:
            return self._get_default_actions_block()

        action_blocks = []
        for action_name, action_info in available_actions.items():
            block = self._format_single_action(action_name, action_info)
            if block:
                action_blocks.append(block)

        return "\n".join(action_blocks) if action_blocks else self._get_default_actions_block()

    def _format_single_action(self, action_name: str, action_info) -> str:
        """
        格式化单个动作为详细说明块

        Args:
            action_name: 动作名称
            action_info: ActionInfo 对象

        Returns:
            格式化后的动作说明
        """
        # 获取动作描述
        description = getattr(action_info, "description", "") or f"执行 {action_name}"

        # 获取使用场景
        action_require = getattr(action_info, "action_require", []) or []
        require_text = "\n".join(f"  - {req}" for req in action_require) if action_require else "  - 根据情况使用"

        # 获取参数定义
        action_parameters = getattr(action_info, "action_parameters", {}) or {}

        # 构建 action_data JSON 示例
        if action_parameters:
            param_lines = []
            for param_name, param_desc in action_parameters.items():
                param_lines.append(f'        "{param_name}": "<{param_desc}>"')
            "{\n" + ",\n".join(param_lines) + "\n      }"
        else:
            pass

        # 构建完整的动作块
        return f"""### {action_name}
**描述**: {description}

**使用场景**:
{require_text}

**示例**:
```json
{{
  "type": "{action_name}",
  {'"content": "<你要说的内容>"' if action_name == "kfc_reply" else self._build_params_example(action_parameters)}
}}
```
"""

    def _build_params_example(self, action_parameters: dict) -> str:
        """构建参数示例字符串"""
        if not action_parameters:
            return '"_comment": "此动作无需额外参数"'

        parts = []
        for param_name, param_desc in action_parameters.items():
            parts.append(f'"{param_name}": "<{param_desc}>"')

        return ",\n  ".join(parts)

    def _get_default_actions_block(self) -> str:
        """获取默认的动作列表"""
        return """### kfc_reply
**描述**: 发送回复消息

**使用场景**:
  - 需要回复对方消息时使用

**示例**:
```json
{
  "type": "kfc_reply",
  "content": "你要说的话"
}
```


### do_nothing
**描述**: 什么都不做

**使用场景**:
  - 当前不需要回应时使用

**示例**:
```json
{
  "type": "do_nothing"
}
```"""

    async def _get_output_format(self) -> str:
        """获取输出格式模板"""
        try:
            prompt = await global_prompt_manager.get_prompt_async(
                PROMPT_NAMES["output_format"]
            )
            return prompt.template
        except KeyError:
            # 如果模板未注册，返回默认格式
            return """请用 JSON 格式回复：
{
    "thought": "你的想法",
    "actions": [{"type": "kfc_reply", "content": "你的回复"}],
    "expected_reaction": "期待的反应",
    "max_wait_seconds": 0
}"""

    async def _get_planner_output_format(self) -> str:
        """获取规划器输出格式模板"""
        try:
            prompt = await global_prompt_manager.get_prompt_async(
                PROMPT_NAMES["planner_output_format"]
            )
            return prompt.template
        except KeyError:
            # 如果模板未注册，返回默认格式
            return """请用 JSON 格式回复：
{
    "thought": "你的想法",
    "actions": [{"type": "kfc_reply"}],
    "expected_reaction": "期待的反应",
    "max_wait_seconds": 0
}

注意：kfc_reply 动作不需要填写 content 字段，回复内容会单独生成。"""

    async def _build_replyer_situation(
        self,
        session: KokoroSession,
        user_name: str,
        situation_type: str,
        extra_context: dict,
    ) -> str:
        """
        构建回复器专用的当前情况描述

        与 Planner 的 _build_current_situation 不同，这里不包含决策性语言，
        只描述当前的情景背景
        """
        from datetime import datetime
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        last_action_block = self._build_last_bot_action_block(session)

        if situation_type == "new_message":
            return f"现在是 {current_time}。\n\n{last_action_block}{user_name} 刚给你发了消息。"

        elif situation_type == "reply_in_time":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            return (
                f"现在是 {current_time}。\n\n"
                f"{last_action_block}"
                f"你之前发了消息后在等 {user_name} 的回复。"
                f"等了大约 {elapsed / 60:.1f} 分钟（你原本打算最多等 {max_wait / 60:.1f} 分钟）。"
                f"现在 {user_name} 回复了！"
            )

        elif situation_type == "reply_late":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            return (
                f"现在是 {current_time}。\n\n"
                f"{last_action_block}"
                f"你之前发了消息后在等 {user_name} 的回复。"
                f"你原本打算最多等 {max_wait / 60:.1f} 分钟，但实际等了 {elapsed / 60:.1f} 分钟才收到回复。"
                f"虽然有点迟，但 {user_name} 终于回复了。"
            )

        elif situation_type == "timeout":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            return (
                f"现在是 {current_time}。\n\n"
                f"{last_action_block}"
                f"你之前发了消息后一直在等 {user_name} 的回复。"
                f"你原本打算最多等 {max_wait / 60:.1f} 分钟，现在已经等了 {elapsed / 60:.1f} 分钟了，对方还是没回。"
                f"你决定主动说点什么。"
            )

        elif situation_type == "proactive":
            silence = extra_context.get("silence_duration", "一段时间")
            return (
                f"现在是 {current_time}。\n\n"
                f"{last_action_block}"
                f"你和 {user_name} 已经有一段时间没聊天了（沉默了 {silence}）。"
                f"你决定主动找 {user_name} 聊点什么。"
            )

        # 默认
        return f"现在是 {current_time}。\n\n{last_action_block}".rstrip()

    async def _build_reply_context(
        self,
        session: KokoroSession,
        user_name: str,
        situation_type: str,
        extra_context: dict,
    ) -> str:
        """
        构建回复情景上下文

        根据 situation_type 构建不同的情景描述，帮助回复器理解当前要回复的情境
        """
        # 获取最后一条用户消息
        target_message = ""
        entries = session.get_recent_entries(limit=10)
        for entry in reversed(entries):
            if entry.event_type == EventType.USER_MESSAGE:
                target_message = entry.content or ""
                break

        if situation_type == "new_message":
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["replyer_context_normal"],
                user_name=user_name,
                target_message=target_message or "（无消息内容）",
            )

        elif situation_type == "reply_in_time":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["replyer_context_in_time"],
                user_name=user_name,
                target_message=target_message or "（无消息内容）",
                elapsed_minutes=elapsed / 60,
                max_wait_minutes=max_wait / 60,
            )

        elif situation_type == "reply_late":
            elapsed = session.waiting_config.get_elapsed_seconds()
            max_wait = session.waiting_config.max_wait_seconds
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["replyer_context_late"],
                user_name=user_name,
                target_message=target_message or "（无消息内容）",
                elapsed_minutes=elapsed / 60,
                max_wait_minutes=max_wait / 60,
            )

        elif situation_type == "proactive":
            silence = extra_context.get("silence_duration", "一段时间")
            trigger_reason = extra_context.get("trigger_reason", "")
            return await global_prompt_manager.format_prompt(
                PROMPT_NAMES["replyer_context_proactive"],
                user_name=user_name,
                silence_duration=silence,
                trigger_reason=trigger_reason,
            )

        # 默认使用普通情景
        return await global_prompt_manager.format_prompt(
            PROMPT_NAMES["replyer_context_normal"],
            user_name=user_name,
            target_message=target_message or "（无消息内容）",
        )

    async def build_unified_prompt(
        self,
        session: KokoroSession,
        user_name: str,
        situation_type: str = "new_message",
        chat_stream: Optional["ChatStream"] = None,
        available_actions: dict | None = None,
        extra_context: dict | None = None,
    ) -> str:
        """
        构建统一模式提示词（单次 LLM 调用完成思考 + 回复生成）

        与 planner_prompt 的区别：
        - 使用完整的输出格式（要求填写 content 字段）
        - 不使用分离的 replyer 提示词

        Args:
            session: 会话对象
            user_name: 用户名称
            situation_type: 情况类型
            chat_stream: 聊天流对象
            available_actions: 可用动作字典
            extra_context: 额外上下文

        Returns:
            完整的统一模式提示词
        """
        extra_context = extra_context or {}

        # 获取 user_id
        user_id = session.user_id if session else None

        # 1. 构建人设块
        persona_block = self._build_persona_block()

        # 1.5. 构建安全互动准则块
        safety_guidelines_block = self._build_safety_guidelines_block()

        # 2. 使用 context_builder 获取关系、记忆、表达习惯等
        context_data = await self._build_context_data(user_name, chat_stream, user_id)
        relation_block = context_data.get("relation_info", f"你与 {user_name} 还不太熟悉，这是早期的交流阶段。")
        memory_block = context_data.get("memory_block", "")
        tool_info = context_data.get("tool_info", "")
        expression_habits = self._build_combined_expression_block(context_data.get("expression_habits", ""))
        schedule_block = context_data.get("schedule", "")

        # 3. 构建活动流
        activity_stream = await self._build_activity_stream(session, user_name)

        # 4. 构建当前情况
        current_situation = await self._build_current_situation(
            session, user_name, situation_type, extra_context
        )

        # 5. 构建聊天历史总览
        chat_history_block = await self._build_chat_history_block(chat_stream)

        # 6. 构建可用动作（统一模式强调需要填写 content）
        actions_block = self._build_unified_actions_block(available_actions)

        # 7. 获取统一模式输出格式（要求填写 content）
        output_format = await self._get_unified_output_format()

        # 8. 使用统一的 prompt 管理系统格式化
        prompt = await global_prompt_manager.format_prompt(
            PROMPT_NAMES["main"],
            user_name=user_name,
            persona_block=persona_block,
            safety_guidelines_block=safety_guidelines_block,
            relation_block=relation_block,
            memory_block=memory_block or "（暂无相关记忆）",
            tool_info=tool_info or "（暂无工具信息）",
            expression_habits=expression_habits or "（根据自然对话风格回复即可）",
            activity_stream=activity_stream or "（这是你们第一次聊天）",
            current_situation=current_situation,
            schedule_block=schedule_block,
            chat_history_block=chat_history_block,
            available_actions=actions_block,
            output_format=output_format,
        )

        return prompt

    def _build_unified_actions_block(self, available_actions: dict | None) -> str:
        """
        构建统一模式的可用动作块

        与 _build_actions_block 的区别：
        - 强调 kfc_reply 需要填写 content 字段
        """
        if not available_actions:
            return self._get_unified_default_actions_block()

        action_blocks = []
        for action_name, action_info in available_actions.items():
            block = self._format_unified_action(action_name, action_info)
            if block:
                action_blocks.append(block)

        return "\n".join(action_blocks) if action_blocks else self._get_unified_default_actions_block()

    def _format_unified_action(self, action_name: str, action_info) -> str:
        """格式化统一模式的单个动作"""
        description = getattr(action_info, "description", "") or f"执行 {action_name}"
        action_require = getattr(action_info, "action_require", []) or []
        require_text = "\n".join(f"  - {req}" for req in action_require) if action_require else "  - 根据情况使用"

        # 统一模式要求 kfc_reply 必须填写 content
        if action_name == "kfc_reply":
            return f"""### {action_name}
**描述**: {description}

**使用场景**:
{require_text}

**示例**:
```json
{{
  "type": "{action_name}",
  "content": "你要说的话（必填）"
}}
```
"""
        else:
            action_parameters = getattr(action_info, "action_parameters", {}) or {}
            params_example = self._build_params_example(action_parameters)

            return f"""### {action_name}
**描述**: {description}

**使用场景**:
{require_text}

**示例**:
```json
{{
  "type": "{action_name}",
  {params_example}
}}
```
"""

    def _get_unified_default_actions_block(self) -> str:
        """获取统一模式的默认动作列表"""
        return """### kfc_reply
**描述**: 发送回复消息

**使用场景**:
  - 需要回复对方消息时使用

**示例**:
```json
{
  "type": "kfc_reply",
  "content": "你要说的话（必填）"
}
```


### do_nothing
**描述**: 什么都不做

**使用场景**:
  - 当前不需要回应时使用

**示例**:
```json
{
  "type": "do_nothing"
}
```"""

    async def _get_unified_output_format(self) -> str:
        """获取统一模式的输出格式模板"""
        try:
            prompt = await global_prompt_manager.get_prompt_async(
                PROMPT_NAMES["unified_output_format"]
            )
            return prompt.template
        except KeyError:
            # 如果模板未注册，返回默认格式
            return """请用以下 JSON 格式回复：
```json
{
    "thought": "你脑子里在想什么，越自然越好",
    "actions": [
        {"type": "kfc_reply", "content": "你的回复内容"}
    ],
    "expected_reaction": "你期待对方的反应是什么",
    "max_wait_seconds": "预估的等待时间（秒）"
}
```

### 字段说明
- `thought`：你的内心独白，记录你此刻的想法和感受。要自然，不要技术性语言。
- `actions`：你要执行的动作列表。对于 `kfc_reply` 动作，**必须**填写 `content` 字段，写上你要说的话。
- `expected_reaction`：你期待对方如何回应（用于判断是否需要等待）
- `max_wait_seconds`：预估的等待时间（秒），这很关键，请根据对话节奏来判断：
  - 如果你刚问了一个开放性问题（比如"你觉得呢？"、"后来怎么样了？"），或者对话明显还在兴头上，设置一个等待时间（比如 60-180 秒），给对方思考和打字的时间。
  - 如果对话感觉自然结束了（比如晚安、拜拜），或者你给出了一个总结性的陈述，那就设置为 0，表示你觉得可以告一段落了。
  - 不要总是设为 0，那会显得你很急着结束对话。

### 注意事项
- kfc_reply 的 content 字段是必填的，直接写你要发送的消息内容
- 即使什么都不想做，也放一个 `{"type": "do_nothing"}`
- 可以组合多个动作，比如先发消息再发表情"""


# 全局单例
_prompt_builder: PromptBuilder | None = None


def get_prompt_builder() -> PromptBuilder:
    """获取全局提示词构建器"""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder
