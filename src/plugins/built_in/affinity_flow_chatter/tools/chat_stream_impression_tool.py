"""
聊天流印象更新工具

采用两阶段设计：
1. 工具调用模型(tool_use)负责判断是否需要更新，传入基本信息
2. 关系追踪模型(relationship_tracker)负责：
   - 读取最近聊天记录
   - 生成高质量的、有人设特色的印象内容
   - 判断常见话题是否真的是"常见"
"""

import asyncio
from typing import Any, ClassVar

from src.chat.utils.chat_message_builder import build_readable_messages
from src.common.database.api.crud import CRUDBase
from src.common.database.core.models import ChatStreams
from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.plugin_system import BaseTool, ToolParamType

logger = get_logger("chat_stream_impression_tool")


class ChatStreamImpressionTool(BaseTool):
    """聊天流印象更新工具

    两阶段设计：
    - 第一阶段：tool_use模型判断是否更新，传入简要信息
    - 第二阶段：relationship_tracker模型读取聊天记录，生成印象
    """

    name = "update_chat_stream_impression"
    description = """记录对当前聊天环境的整体印象。

使用场景：
• 更新印象：对这个聊天流有了新的感受
• 感受变化：兴趣程度明显变化时更新

后台异步执行，不影响回复。"""
    parameters: ClassVar = [
        (
            "impression_hint",
            ToolParamType.STRING,
            "你观察到的关于这个聊天环境的要点（可选）",
            False,
            None,
        ),
        (
            "interest_score",
            ToolParamType.FLOAT,
            "你对这个聊天环境的兴趣程度，0.0-1.0（可选）",
            False,
            None,
        ),
    ]
    available_for_llm = True
    history_ttl = 0

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行聊天流印象更新（异步后台执行，不阻塞回复）

        Args:
            function_args: 工具参数

        Returns:
            dict: 执行结果
        """
        try:
            # 优先从 function_args 获取 stream_id
            stream_id = function_args.get("stream_id")
            stream_name = "未知聊天流"

            # 如果没有，从 chat_stream 对象获取
            if not stream_id and self.chat_stream:
                try:
                    stream_id = self.chat_stream.stream_id
                    stream_name = getattr(self.chat_stream, "group_name", None) or "私聊"
                    logger.debug(f"从 chat_stream 获取到 stream_id: {stream_id}")
                except AttributeError:
                    logger.warning("chat_stream 对象没有 stream_id 属性")

            # 如果还是没有，返回错误
            if not stream_id:
                logger.error("无法获取 stream_id：function_args 和 chat_stream 都没有提供")
                return {"type": "error", "id": "chat_stream_impression", "content": "错误：无法获取当前聊天流ID"}

            # 从LLM传入的参数
            impression_hint = function_args.get("impression_hint", "")
            new_score = function_args.get("interest_score")

            # 如果LLM没有传入任何有效参数，返回提示
            if not impression_hint and new_score is None:
                return {
                    "type": "info",
                    "id": stream_id,
                    "content": "提示：需要提供至少一项更新内容（印象描述或兴趣分数）",
                }

            # 🎯 异步后台执行，不阻塞回复
            asyncio.create_task(self._background_update(
                stream_id=stream_id,
                stream_name=stream_name,
                impression_hint=impression_hint,
                interest_score=new_score,
            ))

            # 立即返回，让回复继续
            return {
                "type": "chat_stream_impression_update",
                "id": stream_id,
                "content": f"正在后台更新对 {stream_name} 的印象..."
            }

        except Exception as e:
            logger.error(f"聊天流印象更新失败: {e}")
            return {
                "type": "error",
                "id": function_args.get("stream_id", "unknown"),
                "content": f"聊天流印象更新失败: {e!s}",
            }

    async def _background_update(
        self,
        stream_id: str,
        stream_name: str,
        impression_hint: str,
        interest_score: float | None,
    ):
        """后台执行聊天流印象更新"""
        try:
            # 从数据库获取现有聊天流印象
            existing_impression = await self._get_stream_impression(stream_id)

            # 获取最近的聊天记录
            chat_history_text = await self._get_recent_chat_history(max_messages=50)

            # 🎯 核心：使用relationship_tracker模型生成印象
            if impression_hint and impression_hint.strip():
                impression_result = await self._generate_stream_impression(
                    stream_name=stream_name,
                    impression_hint=impression_hint,
                    existing_impression=existing_impression,
                    chat_history=chat_history_text,
                )
                final_impression_text = impression_result.get("impression", existing_impression.get("stream_impression_text", ""))
                final_chat_style = impression_result.get("chat_style", existing_impression.get("stream_chat_style", ""))
                final_topic_keywords = impression_result.get("topic_keywords", existing_impression.get("stream_topic_keywords", ""))
            else:
                final_impression_text = existing_impression.get("stream_impression_text", "")
                final_chat_style = existing_impression.get("stream_chat_style", "")
                final_topic_keywords = existing_impression.get("stream_topic_keywords", "")

            # 处理兴趣分数
            if interest_score is not None:
                final_score = max(0.0, min(1.0, float(interest_score)))
            else:
                final_score = existing_impression.get("stream_interest_score", 0.5)

            # 构建最终印象
            final_impression = {
                "stream_impression_text": final_impression_text,
                "stream_chat_style": final_chat_style,
                "stream_topic_keywords": final_topic_keywords,
                "stream_interest_score": final_score,
            }

            # 更新数据库
            await self._update_stream_impression_in_db(stream_id, final_impression)

        except Exception as e:
            logger.error(f"[后台] 聊天流印象更新失败: {e}")

    async def _get_recent_chat_history(self, max_messages: int = 50) -> str:
        """获取最近的聊天记录"""
        try:
            if not self.chat_stream:
                logger.warning("chat_stream 未初始化，无法获取聊天记录")
                return ""

            context = getattr(self.chat_stream, "context", None)
            if not context:
                logger.warning("chat_stream.context 不存在，无法获取聊天记录")
                return ""

            messages = context.get_messages(limit=max_messages, include_unread=True)
            if not messages:
                return ""

            messages_dict = []
            for msg in messages:
                try:
                    if hasattr(msg, "to_dict"):
                        messages_dict.append(msg.to_dict())
                    elif hasattr(msg, "__dict__"):
                        msg_dict = {
                            "time": getattr(msg, "time", 0),
                            "processed_plain_text": getattr(msg, "processed_plain_text", ""),
                            "display_message": getattr(msg, "display_message", ""),
                        }
                        user_info = getattr(msg, "user_info", None)
                        if user_info:
                            msg_dict["user_info"] = {
                                "user_id": getattr(user_info, "user_id", ""),
                                "user_nickname": getattr(user_info, "user_nickname", ""),
                            }
                        chat_info = getattr(msg, "chat_info", None)
                        if chat_info:
                            msg_dict["chat_info"] = {
                                "platform": getattr(chat_info, "platform", ""),
                            }
                        messages_dict.append(msg_dict)
                except Exception as e:
                    logger.warning(f"转换消息失败: {e}")
                    continue

            if not messages_dict:
                return ""

            readable_messages = await build_readable_messages(
                messages=messages_dict,
                replace_bot_name=True,
                timestamp_mode="normal_no_YMD",
                truncate=True
            )

            return readable_messages or ""

        except Exception as e:
            logger.error(f"获取聊天记录失败: {e}")
            return ""

    async def _generate_stream_impression(
        self,
        stream_name: str,
        impression_hint: str,
        existing_impression: dict[str, Any],
        chat_history: str,
    ) -> dict[str, Any]:
        """使用relationship_tracker模型生成聊天流印象"""
        try:
            import orjson
            from json_repair import repair_json
            from src.llm_models.utils_model import LLMRequest

            # 获取人设信息
            bot_name = global_config.bot.nickname if global_config and global_config.bot else "Bot"
            personality_core = global_config.personality.personality_core if global_config and global_config.personality else ""
            personality_side = global_config.personality.personality_side if global_config and global_config.personality else ""
            identity = global_config.personality.identity if global_config and global_config.personality else ""

            # 构建提示词
            existing_text = existing_impression.get("stream_impression_text", "")
            existing_style = existing_impression.get("stream_chat_style", "")
            existing_topics = existing_impression.get("stream_topic_keywords", "")
            is_first_impression = not existing_text or len(existing_text) < 20

            prompt = f"""你是{bot_name}，现在要记录你对聊天环境"{stream_name}"的印象。

## 你是谁
{identity}

## 你的核心人格
{personality_core}

## 你的性格侧面
{personality_side}

## 你之前对这个聊天环境的印象
{existing_text if existing_text else "（这是你第一次记录对这个聊天环境的印象）"}

## 之前记录的聊天风格
{existing_style if existing_style else "（无）"}

## 之前记录的常见话题
{existing_topics if existing_topics else "（无）"}

## 最近的聊天记录
{chat_history if chat_history else "（无聊天记录）"}

## 这次观察到的新要点
{impression_hint if impression_hint else "（无特别观察）"}

---

## 📝 印象写作

用一段短文描绘这个聊天环境给你的感觉。

不是记录发生了什么事，
而是这个地方本身带来的氛围。
像描述一个场所、一种空气、一种温度。

示例：
"像一个温暖的小角落，大家聊着天南海北，偶尔蹦出几个冷笑话，气氛轻松得让人想赖着不走。"

**注意**：
- {"写下你对这个聊天环境的第一印象" if is_first_impression else "在原有印象基础上融入新的感受"}
- 字数：60-150字

## 聊天风格
用简短的词语描述这个聊天环境的风格，如"活跃热闹,轻松愉快"或"安静佛系,偶尔冒泡"

## 常见话题
**只记录在聊天记录中多次出现的话题**，偶尔提到一次的不算。
如果没有明显的反复话题，保持原有记录或留空。

请严格按照以下JSON格式输出：
{{
    "impression": "你对这个聊天环境的印象...",
    "chat_style": "聊天风格关键词",
    "topic_keywords": "话题1,话题2（只记录反复出现的话题，可为空）"
}}"""

            # 使用relationship_tracker模型
            if not model_config or not model_config.model_task_config:
                raise ValueError("model_config 未初始化")

            llm = LLMRequest(
                model_set=model_config.model_task_config.relationship_tracker,
                request_type="chat_stream.impression"
            )

            response, _ = await llm.generate_response_async(
                prompt=prompt,
                temperature=0.7,
                max_tokens=500,
            )

            # 解析响应
            response = response.strip()
            try:
                result = orjson.loads(repair_json(response))
                impression = result.get("impression", "")
                chat_style = result.get("chat_style", "")
                topic_keywords = result.get("topic_keywords", "")

                if not impression or len(impression) < 10:
                    logger.warning("印象生成结果过短，使用原始hint")
                    impression = impression_hint or existing_text

                return {
                    "impression": impression,
                    "chat_style": chat_style,
                    "topic_keywords": topic_keywords,
                }

            except Exception as parse_error:
                logger.warning(f"解析JSON失败: {parse_error}")
                return {
                    "impression": impression_hint or existing_text,
                    "chat_style": existing_style,
                    "topic_keywords": existing_topics,
                }

        except Exception as e:
            logger.error(f"生成聊天流印象失败: {e}")
            return {
                "impression": existing_impression.get("stream_impression_text", ""),
                "chat_style": existing_impression.get("stream_chat_style", ""),
                "topic_keywords": existing_impression.get("stream_topic_keywords", ""),
            }

    async def _get_stream_impression(self, stream_id: str) -> dict[str, Any]:
        """从数据库获取聊天流现有印象

        Args:
            stream_id: 聊天流ID

        Returns:
            dict: 聊天流印象数据
        """
        try:
            # 使用CRUD进行查询
            crud = CRUDBase(ChatStreams)
            stream = await crud.get_by(stream_id=stream_id)

            if stream:
                return {
                    "stream_impression_text": stream.stream_impression_text or "",
                    "stream_chat_style": stream.stream_chat_style or "",
                    "stream_topic_keywords": stream.stream_topic_keywords or "",
                    "stream_interest_score": float(stream.stream_interest_score)
                    if stream.stream_interest_score is not None
                    else 0.5,
                    "group_name": stream.group_name or "私聊",
                }
            else:
                # 聊天流不存在，返回默认值
                return {
                    "stream_impression_text": "",
                    "stream_chat_style": "",
                    "stream_topic_keywords": "",
                    "stream_interest_score": 0.5,
                    "group_name": "未知",
                }
        except Exception as e:
            logger.error(f"获取聊天流印象失败: {e}")
            return {
                "stream_impression_text": "",
                "stream_chat_style": "",
                "stream_topic_keywords": "",
                "stream_interest_score": 0.5,
                "group_name": "未知",
            }



    async def _update_stream_impression_in_db(self, stream_id: str, impression: dict[str, Any]):
        """更新数据库中的聊天流印象

        Args:
            stream_id: 聊天流ID
            impression: 印象数据
        """
        try:
            # 使用CRUD进行更新
            crud = CRUDBase(ChatStreams)
            existing = await crud.get_by(stream_id=stream_id)

            if existing:
                # 更新现有记录
                await crud.update(
                    existing.id,
                    {
                        "stream_impression_text": impression.get("stream_impression_text", ""),
                        "stream_chat_style": impression.get("stream_chat_style", ""),
                        "stream_topic_keywords": impression.get("stream_topic_keywords", ""),
                        "stream_interest_score": impression.get("stream_interest_score", 0.5),
                    }
                )

                # 使缓存失效
                from src.common.database.optimization.cache_manager import get_cache
                from src.common.database.utils.decorators import generate_cache_key
                cache = await get_cache()
                await cache.delete(generate_cache_key("stream_impression", stream_id))
                await cache.delete(generate_cache_key("chat_stream", stream_id))

                logger.debug(f"聊天流印象已更新到数据库: {stream_id}")
            else:
                error_msg = f"聊天流 {stream_id} 不存在于数据库中，无法更新印象"
                logger.error(error_msg)
                # 注意：通常聊天流应该在消息处理时就已创建，这里不创建新记录
                raise ValueError(error_msg)

        except Exception as e:
            logger.error(f"更新聊天流印象到数据库失败: {e}")
            raise


