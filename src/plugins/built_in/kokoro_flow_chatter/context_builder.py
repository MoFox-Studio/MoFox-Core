"""
Kokoro Flow Chatter 上下文构建器

为 KFC 提供完整的情境感知能力。
包含：
- 关系信息 (relation_info)
- 记忆块 (memory_block)
- 工具调用 (tool_info)
- 表达习惯 (expression_habits)
- 日程信息 (schedule)
- 时间信息 (time)
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.person_info.person_info import get_person_info_manager

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream
    from src.common.data_models.message_manager_data_model import StreamContext

logger = get_logger("kfc_context_builder")


def _get_config():
    """获取全局配置（带类型断言）"""
    assert global_config is not None, "global_config 未初始化"
    return global_config


class KFCContextBuilder:
    """
    KFC V2 上下文构建器

    为提示词提供完整的情境感知数据。
    """

    def __init__(self, chat_stream: "ChatStream"):
        self.chat_stream = chat_stream
        self.chat_id = chat_stream.stream_id
        self.platform = chat_stream.platform
        self.is_group_chat = bool(chat_stream.group_info)

    async def build_all_context(
        self,
        sender_name: str,
        target_message: str,
        context: Optional["StreamContext"] = None,
        user_id: str | None = None,
        enable_tool: bool = True,
        fast_mode: bool = False,
    ) -> dict[str, str]:
        """
        并行构建所有上下文模块

        Args:
            sender_name: 发送者名称
            target_message: 目标消息内容
            context: 聊天流上下文（可选）
            user_id: 用户ID（可选，用于精确查找关系信息）
            enable_tool: 是否启用工具调用

        Returns:
            dict: 包含所有上下文块的字典
        """
        logger.debug(f"[KFC上下文] 开始构建上下文: sender={sender_name}, target={target_message[:50] if target_message else '(空)'}...")

        chat_history = await self._get_chat_history_text(context)

        tasks = {
            "relation_info": self._build_relation_info(sender_name, target_message, user_id),
            "memory_block": self._build_memory_block(chat_history, target_message, context, fast_mode=fast_mode),
            "tool_info": self._build_tool_info(chat_history, sender_name, target_message, enable_tool),
            "expression_habits": self._build_expression_habits(chat_history, target_message),
            "schedule": self._build_schedule_block(),
            "time": self._build_time_block(),
        }

        results = {}
        timing_logs = []

        # 任务名称中英文映射
        task_name_mapping = {
            "relation_info": "感受关系",
            "memory_block": "回忆",
            "tool_info": "使用工具",
            "expression_habits": "选取表达方式",
            "schedule": "日程",
            "time": "时间",
        }

        try:
            task_results = await asyncio.gather(
                *[self._wrap_task_with_timing(name, coro) for name, coro in tasks.items()],
                return_exceptions=True
            )

            for result in task_results:
                if isinstance(result, tuple) and len(result) == 3:
                    name, value, duration = result
                    results[name] = value
                    chinese_name = task_name_mapping.get(name, name)
                    timing_logs.append(f"{chinese_name}: {duration:.1f}s")
                    if duration > 8:
                        logger.warning(f"KFC 上下文构建耗时过长: {chinese_name} 耗时: {duration:.1f}s")
                elif isinstance(result, Exception):
                    logger.warning(f"上下文构建任务异常: {result}")
        except Exception as e:
            logger.error(f"并行构建上下文失败: {e}")

        # 输出耗时日志
        if timing_logs:
            logger.info(f"在回复前的步骤耗时: {'; '.join(timing_logs)}")

        return results

    async def _wrap_task_with_timing(self, name: str, coro) -> tuple[str, str, float]:
        """包装任务以返回名称、结果和耗时"""
        start_time = time.time()
        try:
            result = await coro
            duration = time.time() - start_time
            return (name, result or "", duration)
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"构建 {name} 失败: {e}")
            return (name, "", duration)

    async def _get_chat_history_text(
        self,
        context: Optional["StreamContext"] = None,
        limit: int = 20,
    ) -> str:
        """获取聊天历史文本"""
        if context is None:
            return ""

        try:
            from src.chat.utils.chat_message_builder import build_readable_messages

            messages = context.get_messages(limit=limit, include_unread=True)
            if not messages:
                return ""

            msg_dicts = [msg.flatten() for msg in messages]

            return await build_readable_messages(
                msg_dicts,
                replace_bot_name=True,
                timestamp_mode="relative",
                truncate=True,
            )
        except Exception as e:
            logger.error(f"获取聊天历史失败: {e}")
            return ""

    async def _build_relation_info(self, sender_name: str, target_message: str, user_id: str | None = None) -> str:
        """构建关系信息块"""
        config = _get_config()

        if sender_name == f"{config.bot.nickname}(你)":
            return "你将要回复的是你自己发送的消息。"

        person_info_manager = get_person_info_manager()

        # 优先使用 user_id + platform 获取 person_id
        person_id = None
        if user_id and self.platform:
            person_id = person_info_manager.get_person_id(self.platform, user_id)
            logger.debug(f"通过 platform={self.platform}, user_id={user_id} 获取 person_id={person_id}")

        # 如果没有找到，尝试通过 person_name 查找
        if not person_id:
            person_id = await person_info_manager.get_person_id_by_person_name(sender_name)

        if not person_id:
            logger.debug(f"未找到用户 {sender_name} 的 person_id")
            return f"你与{sender_name}还没有建立深厚的关系，这是早期的互动阶段。"

        try:
            from src.person_info.relationship_fetcher import relationship_fetcher_manager

            relationship_fetcher = relationship_fetcher_manager.get_fetcher(self.chat_id)

            user_relation_info = await relationship_fetcher.build_relation_info(person_id, points_num=5)
            stream_impression = await relationship_fetcher.build_chat_stream_impression(self.chat_id)

            parts = []
            if user_relation_info:
                parts.append(f"### 你与 {sender_name} 的关系\n{user_relation_info}")
            if stream_impression:
                scene_type = "这个群" if self.is_group_chat else "你们的私聊"
                parts.append(f"### 你对{scene_type}的印象\n{stream_impression}")

            if parts:
                return "\n\n".join(parts)
            else:
                return f"你与{sender_name}还没有建立深厚的关系，这是早期的互动阶段。"

        except Exception as e:
            logger.error(f"获取关系信息失败: {e}")
            return f"你与{sender_name}是普通朋友关系。"

    async def _build_memory_block(
        self,
        chat_history: str,
        target_message: str,
        context: Optional["StreamContext"] = None,
        fast_mode: bool = False,
    ) -> str:
        """构建记忆块（使用三层记忆系统）"""
        config = _get_config()

        if not (config.memory and config.memory.enable):
            logger.debug("[KFC记忆] 记忆系统未启用")
            return ""

        try:
            from src.memory_graph.manager_singleton import (
                ensure_unified_memory_manager_initialized,
            )
            from src.memory_graph.utils.three_tier_formatter import memory_formatter

            unified_manager = await ensure_unified_memory_manager_initialized()
            if not unified_manager:
                logger.warning("[KFC记忆] 管理器初始化失败或未启用，跳过记忆检索")
                return ""

            # 构建查询文本（使用最近多条消息的组合块）
            query_text = self._build_memory_query_text(target_message, context)
            logger.debug(f"[KFC记忆] 开始检索，查询文本: {query_text[:100]}...")

            search_result = await unified_manager.search_memories(
                query_text=query_text,
                use_judge=False if fast_mode else config.memory.use_judge,
                recent_chat_history=chat_history,
            )

            if not search_result:
                logger.debug("[KFC记忆] 未找到相关记忆")
                return ""

            perceptual_blocks = search_result.get("perceptual_blocks", [])
            short_term_memories = search_result.get("short_term_memories", [])
            long_term_memories = search_result.get("long_term_memories", [])

            formatted_memories = await memory_formatter.format_all_tiers(
                perceptual_blocks=perceptual_blocks,
                short_term_memories=short_term_memories,
                long_term_memories=long_term_memories
            )

            total_count = len(perceptual_blocks) + len(short_term_memories) + len(long_term_memories)
            if total_count > 0 and formatted_memories.strip():
                logger.info(
                    f"[KFC记忆] 检索到 {total_count} 条记忆 "
                    f"(感知:{len(perceptual_blocks)}, 短期:{len(short_term_memories)}, 长期:{len(long_term_memories)})"
                )
                # 添加记忆块标题，感知记忆的来源说明已在 three_tier_formatter 中添加
                return f"### 🧠 相关记忆\n\n{formatted_memories}"

            logger.debug("[KFC记忆] 记忆为空")
            return ""

        except Exception as e:
            logger.error(f"[KFC记忆] 检索失败: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def _build_memory_query_text(
        self,
        fallback_text: str,
        context: Optional["StreamContext"] = None,
        block_size: int = 5,
    ) -> str:
        """
        将最近若干条消息拼接为一个查询块，用于生成语义向量。

        Args:
            fallback_text: 如果无法拼接消息块时使用的后备文本
            context: 聊天流上下文
            block_size: 组合的消息数量

        Returns:
            str: 用于检索的查询文本
        """
        if not context:
            return fallback_text

        try:
            messages = context.get_messages(limit=block_size, include_unread=True)
            if not messages:
                return fallback_text

            lines = []
            for msg in messages:
                sender = ""
                if msg.user_info:
                    sender = msg.user_info.user_nickname or msg.user_info.user_cardname or ""
                content = msg.processed_plain_text or msg.display_message or ""
                if sender and content:
                    lines.append(f"{sender}: {content}")
                elif content:
                    lines.append(content)

            return "\n".join(lines) if lines else fallback_text
        except Exception:
            return fallback_text

    async def _build_tool_info(
        self,
        chat_history: str,
        sender_name: str,
        target_message: str,
        enable_tool: bool = True,
    ) -> str:
        """构建工具信息块

        Args:
            chat_history: 聊天历史记录
            sender_name: 发送者名称
            target_message: 目标消息内容
            enable_tool: 是否启用工具调用

        Returns:
            str: 工具信息字符串
        """
        if not enable_tool:
            return ""

        try:
            from src.plugin_system.core.tool_use import ToolExecutor

            tool_executor = ToolExecutor(chat_id=self.chat_id)

            info_parts = []

            # ========== 1. 主动召回联网搜索缓存 ==========
            try:
                from src.common.cache_manager import tool_cache

                # 使用聊天历史作为语义查询
                query_text = chat_history if chat_history else target_message
                recalled_caches = await tool_cache.recall_relevant_cache(
                    query_text=query_text,
                    tool_name="web_search",  # 只召回联网搜索的缓存
                    top_k=2,
                    similarity_threshold=0.65,  # 相似度阈值
                )

                if recalled_caches:
                    recall_parts = ["### 🔍 相关的历史搜索结果"]
                    for item in recalled_caches:
                        original_query = item.get("query", "")
                        content = item.get("content", "")
                        similarity = item.get("similarity", 0)
                        if content:
                            # 截断过长的内容
                            if len(content) > 500:
                                content = content[:500] + "..."
                            recall_parts.append(f"**搜索「{original_query}」** (相关度:{similarity:.0%})\n{content}")

                    info_parts.append("\n\n".join(recall_parts))
                    logger.info(f"[缓存召回] 召回了 {len(recalled_caches)} 条相关搜索缓存")
            except Exception as e:
                logger.debug(f"[缓存召回] 召回失败（非关键）: {e}")

            # ========== 2. 获取工具调用历史 ==========
            tool_history_str = tool_executor.history_manager.format_for_prompt(
                max_records=3, include_results=True
            )
            if tool_history_str:
                info_parts.append(tool_history_str)

            # ========== 3. 执行工具调用 ==========
            tool_results, _, _ = await tool_executor.execute_from_chat_message(
                sender=sender_name,
                target_message=target_message,
                chat_history=chat_history,
                return_details=False,
            )

            # 显示当前工具调用的结果（简要信息）
            if tool_results:
                current_results_parts = ["### 🔧 刚获取的工具信息"]
                for tool_result in tool_results:
                    tool_name = tool_result.get("tool_name", "unknown")
                    content = tool_result.get("content", "")
                    # 不进行截断，让工具自己处理结果长度
                    current_results_parts.append(f"- **{tool_name}**: {content}")

                info_parts.append("\n".join(current_results_parts))
                logger.info(f"[工具调用] 获取到 {len(tool_results)} 个工具结果")

            # 如果没有任何信息，返回空字符串
            if not info_parts:
                logger.debug("[工具调用] 未获取到任何工具结果或历史记录")
                return ""

            return "\n\n".join(info_parts)

        except Exception as e:
            logger.error(f"[工具调用] 工具信息获取失败: {e}")
            return ""

    async def _build_expression_habits(self, chat_history: str, target_message: str) -> str:
        """构建表达习惯块"""
        config = _get_config()

        use_expression, _, _ = config.expression.get_expression_config_for_chat(self.chat_id)
        if not use_expression:
            return ""

        try:
            from src.chat.express.expression_selector import expression_selector

            style_habits = []
            grammar_habits = []

            selected_expressions = await expression_selector.select_suitable_expressions(
                chat_id=self.chat_id,
                chat_history=chat_history,
                target_message=target_message,
                max_num=8,
                min_num=2
            )

            if selected_expressions:
                for expr in selected_expressions:
                    if isinstance(expr, dict) and "situation" in expr and "style" in expr:
                        expr_type = expr.get("type", "style")
                        habit_str = f"当{expr['situation']}时，使用 {expr['style']}"
                        if expr_type == "grammar":
                            grammar_habits.append(habit_str)
                        else:
                            style_habits.append(habit_str)

            parts = []
            if style_habits:
                parts.append("**语言风格习惯**：\n" + "\n".join(f"- {h}" for h in style_habits))
            if grammar_habits:
                parts.append("**句法习惯**：\n" + "\n".join(f"- {h}" for h in grammar_habits))

            if parts:
                return "### 💬 你的表达习惯\n\n" + "\n\n".join(parts)

            return ""

        except Exception as e:
            logger.error(f"构建表达习惯失败: {e}")
            return ""

    async def _build_schedule_block(self) -> str:
        """构建日程信息块"""
        config = _get_config()

        if not config.planning_system.schedule_enable:
            return ""

        try:
            from src.schedule.schedule_manager import schedule_manager

            activity_info = schedule_manager.get_current_activity()
            if not activity_info:
                return ""

            activity = activity_info.get("activity")
            time_range = activity_info.get("time_range")
            now = datetime.now()

            if time_range:
                try:
                    start_str, end_str = time_range.split("-")
                    start_time = datetime.strptime(start_str.strip(), "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day
                    )
                    end_time = datetime.strptime(end_str.strip(), "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day
                    )

                    if end_time < start_time:
                        end_time += timedelta(days=1)
                    if now < start_time:
                        now += timedelta(days=1)

                    duration_minutes = (now - start_time).total_seconds() / 60
                    remaining_minutes = (end_time - now).total_seconds() / 60

                    return (
                        f"你当前正在「{activity}」，"
                        f"从{start_time.strftime('%H:%M')}开始，预计{end_time.strftime('%H:%M')}结束，"
                        f"已进行{duration_minutes:.0f}分钟，还剩约{remaining_minutes:.0f}分钟。"
                    )
                except (ValueError, AttributeError):
                    pass

            return f"你当前正在「{activity}」"

        except Exception as e:
            logger.error(f"构建日程块失败: {e}")
            return ""

    async def _build_time_block(self) -> str:
        """构建时间信息块"""
        now = datetime.now()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekdays[now.weekday()]
        return f"{now.strftime('%Y年%m月%d日')} {weekday} {now.strftime('%H:%M:%S')}"


async def build_kfc_context(
    chat_stream: "ChatStream",
    sender_name: str,
    target_message: str,
    context: Optional["StreamContext"] = None,
    user_id: str | None = None,
) -> dict[str, str]:
    """
    便捷函数：构建KFC所需的所有上下文
    """
    builder = KFCContextBuilder(chat_stream)
    return await builder.build_all_context(sender_name, target_message, context, user_id)


__all__ = [
    "KFCContextBuilder",
    "build_kfc_context",
]
