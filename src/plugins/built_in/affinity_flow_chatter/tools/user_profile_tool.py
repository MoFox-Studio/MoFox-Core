"""
用户画像更新工具

采用两阶段设计：
1. 工具调用模型(tool_use)负责判断是否需要更新，传入基本信息
2. 关系追踪模型(relationship_tracker)负责：
   - 读取最近聊天记录
   - 生成高质量的、有人设特色的印象内容
   - 决定好感度变化（联动更新）
"""

import time
from typing import Any

from sqlalchemy import select

from src.chat.utils.chat_message_builder import build_readable_messages
from src.common.database.compatibility import get_db_session
from src.common.database.core.models import UserRelationships
from src.common.logger import get_logger
from src.config.config import global_config, model_config  # type: ignore[attr-defined]
from src.plugin_system import BaseTool, ToolParamType

# 默认好感度分数，用于配置未初始化时的回退
DEFAULT_RELATIONSHIP_SCORE = 0.3

logger = get_logger("user_profile_tool")


def _get_base_relationship_score() -> float:
    """安全获取基础好感度分数"""
    if global_config and global_config.affinity_flow:
        return global_config.affinity_flow.base_relationship_score
    return DEFAULT_RELATIONSHIP_SCORE


class UserProfileTool(BaseTool):
    """用户画像更新工具

    两阶段设计：
    - 第一阶段：tool_use模型判断是否更新，传入简要信息
    - 第二阶段：relationship_tracker模型读取聊天记录，生成印象并决定好感度变化
    """

    name = "update_user_profile"
    description = """记录对某个人的印象或别名。

使用场景：
• 记录别名：大家稳定用来称呼这个人的名字或外号（如昵称、绰号、简称）
• 更新印象：相处后对这个人有了新的感受或认知

别名判断原则：
• ✓ 稳定称呼：多人多次使用、或用户自我介绍的名字
• ✗ 排除：临时玩笑、亲昵称呼（老公、老婆、宝贝）、敬语（大人、长官）、一次性角色扮演

后台异步执行，不影响回复。"""
    parameters = [
        ("target_user_id", ToolParamType.STRING, "目标用户的ID（必须）", True, None),
        ("target_user_name", ToolParamType.STRING, "目标用户的名字/昵称（必须）", True, None),
        ("alias_operation", ToolParamType.STRING, "别名操作：add=新增 / remove=删除 / replace=全部替换（可选）", False, None),
        ("alias_value", ToolParamType.STRING, "别名内容，多个用、分隔", False, None),
        ("impression_hint", ToolParamType.STRING, "你观察到的关于TA的要点（可选）", False, None),
    ]
    available_for_llm = True
    history_ttl = 0

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行用户画像更新（异步后台执行，不阻塞回复）

        Args:
            function_args: 工具参数

        Returns:
            dict: 执行结果
        """
        import asyncio

        try:
            # 提取参数
            target_user_id = function_args.get("target_user_id")
            target_user_name = function_args.get("target_user_name", target_user_id)
            if not target_user_id:
                return {
                    "type": "error",
                    "id": "user_profile_update",
                    "content": "错误：必须提供目标用户ID"
                }

            # 从LLM传入的参数
            alias_operation = function_args.get("alias_operation", "")
            alias_value = function_args.get("alias_value", "")
            impression_hint = function_args.get("impression_hint", "")

            # 如果LLM没有传入任何有效参数，返回提示
            if not any([alias_value, impression_hint]):
                return {
                    "type": "info",
                    "id": target_user_id,
                    "content": "提示：需要提供至少一项更新内容（别名或印象描述）"
                }

            # 🎯 异步后台执行，不阻塞回复
            asyncio.create_task(self._background_update(
                target_user_id=target_user_id,
                target_user_name=str(target_user_name) if target_user_name else str(target_user_id),
                alias_operation=alias_operation,
                alias_value=alias_value,
                impression_hint=impression_hint,
            ))

            # 立即返回，让回复继续
            return {
                "type": "user_profile_update",
                "id": target_user_id,
                "content": f"正在后台更新对 {target_user_name} 的印象..."
            }

        except Exception as e:
            logger.error(f"用户画像更新失败: {e}")
            return {
                "type": "error",
                "id": function_args.get("target_user_id", "unknown"),
                "content": f"用户画像更新失败: {e!s}"
            }

    async def _background_update(
        self,
        target_user_id: str,
        target_user_name: str,
        alias_operation: str,
        alias_value: str,
        impression_hint: str,
    ):
        """后台执行用户画像更新"""
        try:
            # 从数据库获取现有用户画像
            existing_profile = await self._get_user_profile(target_user_id)

            # 🎯 处理别名操作
            final_aliases = self._process_list_operation(
                existing_value=existing_profile.get("user_aliases", ""),
                operation=alias_operation,
                new_value=alias_value,
            )

            # 获取最近的聊天记录
            chat_history_text = await self._get_recent_chat_history(target_user_id)

            # 🎯 核心：使用relationship_tracker模型生成印象并决定好感度变化
            final_impression = existing_profile.get("relationship_text", "")
            affection_change = 0.0  # 好感度变化量

            # 只有在LLM明确提供impression_hint时才更新印象（更严格）
            if impression_hint and impression_hint.strip():
                impression_result = await self._generate_impression_with_affection(
                    target_user_name=target_user_name,
                    impression_hint=impression_hint,
                    existing_impression=str(existing_profile.get("relationship_text", "")),
                    chat_history=chat_history_text,
                    current_score=float(existing_profile.get("relationship_score", _get_base_relationship_score())),
                )
                final_impression = impression_result.get("impression", final_impression)
                affection_change = impression_result.get("affection_change", 0.0)

            # 计算新的好感度
            old_score = float(existing_profile.get("relationship_score", _get_base_relationship_score()))
            new_score = old_score + affection_change
            new_score = max(0.0, min(1.0, new_score))  # 确保在0-1范围内

            # 构建最终画像（只包含核心字段）
            final_profile = {
                "user_aliases": final_aliases,
                "relationship_text": final_impression,
                "relationship_score": new_score,
            }

            # 更新数据库
            await self._update_user_profile_in_db(target_user_id, final_profile)

        except Exception as e:
            logger.error(f"[后台] 用户画像更新失败: {e}")

    def _process_list_operation(self, existing_value: str, operation: str, new_value: str) -> str:
        """处理列表类型的操作（别名）

        Args:
            existing_value: 现有值（用、分隔）
            operation: 操作类型 add/remove/replace
            new_value: 新值（用、分隔）

        Returns:
            str: 处理后的值
        """
        if not new_value:
            return existing_value

        # 解析现有值和新值
        existing_set = set(filter(None, [x.strip() for x in (existing_value or "").split("、")]))
        new_set = set(filter(None, [x.strip() for x in new_value.split("、")]))

        operation = (operation or "add").lower().strip()

        if operation == "replace":
            # 全部替换
            result_set = new_set
            logger.debug(f"别名替换: {existing_set} -> {new_set}")
        elif operation == "remove":
            # 删除指定项
            result_set = existing_set - new_set
            logger.debug(f"别名删除: {new_set} 从 {existing_set}")
        else:  # add 或默认
            # 新增（合并）
            result_set = existing_set | new_set
            logger.debug(f"别名新增: {new_set} 到 {existing_set}")

        return "、".join(sorted(result_set))

    async def _get_recent_chat_history(self, target_user_id: str, max_messages: int = 50) -> str:
        """获取最近的聊天记录

        Args:
            target_user_id: 目标用户ID
            max_messages: 最大消息数量
            
        Returns:
            str: 格式化的聊天记录文本
        """
        try:
            # 从 chat_stream 获取上下文
            if not self.chat_stream:
                logger.warning("chat_stream 未初始化，无法获取聊天记录")
                return ""

            context = getattr(self.chat_stream, "context", None)
            if not context:
                logger.warning("chat_stream.context 不存在，无法获取聊天记录")
                return ""

            # 获取最近的消息 - 使用正确的方法名 get_messages
            messages = context.get_messages(limit=max_messages, include_unread=True)
            if not messages:
                return ""

            # 将 DatabaseMessages 对象转换为字典列表
            messages_dict = []
            for msg in messages:
                try:
                    if hasattr(msg, "to_dict"):
                        messages_dict.append(msg.to_dict())
                    elif hasattr(msg, "__dict__"):
                        # 手动构建字典
                        msg_dict = {
                            "time": getattr(msg, "time", 0),
                            "processed_plain_text": getattr(msg, "processed_plain_text", ""),
                            "display_message": getattr(msg, "display_message", ""),
                        }
                        # 处理 user_info
                        user_info = getattr(msg, "user_info", None)
                        if user_info:
                            msg_dict["user_info"] = {
                                "user_id": getattr(user_info, "user_id", ""),
                                "user_nickname": getattr(user_info, "user_nickname", ""),
                            }
                        # 处理 chat_info
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

            # 构建可读的消息文本
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

    async def _generate_impression_with_affection(
        self,
        target_user_name: str,
        impression_hint: str,
        existing_impression: str,
        chat_history: str,
        current_score: float,
    ) -> dict[str, Any]:
        """使用relationship_tracker模型生成印象并决定好感度变化

        Args:
            target_user_name: 目标用户的名字
            impression_hint: 工具调用模型传入的简要观察
            existing_impression: 现有的印象描述
            chat_history: 最近的聊天记录
            current_score: 当前好感度分数

        Returns:
            dict: {"impression": str, "affection_change": float}
        """
        try:
            import orjson
            from json_repair import repair_json

            from src.llm_models.utils_model import LLMRequest

            # 获取人设信息（添加空值保护）
            bot_name = global_config.bot.nickname if global_config and global_config.bot else "Bot"
            personality_core = global_config.personality.personality_core if global_config and global_config.personality else ""
            personality_side = global_config.personality.personality_side if global_config and global_config.personality else ""
            identity = global_config.personality.identity if global_config and global_config.personality else ""

            # 构建提示词
            # 根据是否有旧印象决定任务类型
            is_first_impression = not existing_impression or len(existing_impression) < 20

            prompt = f"""你是{bot_name}，现在要记录你对"{target_user_name}"的印象。

## 你是谁
{identity}

## 你的核心人格
{personality_core}

## 你的性格侧面
{personality_side}

## 你之前对{target_user_name}的印象
{existing_impression if existing_impression else "（这是你第一次记录对TA的印象）"}

## 最近的聊天记录
{chat_history if chat_history else "（无聊天记录）"}

## 这次观察到的新要点
{impression_hint if impression_hint else "（无特别观察）"}

## 当前好感度
{current_score:.2f} (范围0-1，0.3=普通认识，0.5=朋友，0.7=好友，0.9=挚友)

---

## 📝 印象写作

用一段短文描绘这个人给你的感觉。

不是记录ta说了什么、做了什么，
而是ta存在本身带来的氛围。
像描述一种天气、一种颜色、一种旋律。

把ta想象成一种事物、一个场景、一种感觉，
然后用文字把它画下来。

示例：
"像午后斜照进来的光，不急不躁，落在哪里都带着暖意。和ta聊天时，时间总是过得很轻。"

**注意**：
- 保持旧印象中已确定的性别（他/她）
- {"写下你对这个人的第一印象" if is_first_impression else "在原有印象基础上融入新的感受"}
- 字数：{"60-120字" if is_first_impression else "80-180字"}

## 好感度变化

当前好感度 {current_score:.2f}，根据阶段选择变化幅度：

| 阶段 | 范围 | 单次变化 |
|------|------|----------|
| 陌生→初识 | 0-0.3 | ±0.01~0.03 |
| 初识→熟人 | 0.3-0.5 | ±0.01~0.025 |
| 熟人→朋友 | 0.5-0.7 | ±0.01~0.02 |
| 朋友→好友 | 0.7-0.85 | ±0.005~0.015 |
| 好友→挚友 | 0.85+ | ±0.002~0.01 |

**加分情况**：深层情感分享、主动关心帮助、展现真诚信任
**减分情况**：长时间敷衍、明显不耐烦、冲突或伤害性言论
**不变（默认）**：普通日常交流、闲聊、开玩笑

请严格按照以下JSON格式输出：
{{
    "gender": "male/female/unknown",
    "impression": "你对{target_user_name}的印象...",
    "affection_change": 0,
    "change_reason": "无变化/变化原因"
}}"""

            # 使用relationship_tracker模型（添加空值保护）
            if not model_config or not model_config.model_task_config:
                raise ValueError("model_config 未初始化")

            llm = LLMRequest(
                model_set=model_config.model_task_config.relationship_tracker,
                request_type="user_profile.impression_and_affection"
            )

            response, _ = await llm.generate_response_async(
                prompt=prompt,
                temperature=0.7,
                max_tokens=600,
            )

            # 解析响应
            response = response.strip()
            try:
                result = orjson.loads(repair_json(response))
                impression = result.get("impression", "")
                affection_change = float(result.get("affection_change", 0))
                result.get("change_reason", "")
                detected_gender = result.get("gender", "unknown")

                # 🎯 根据当前好感度阶段限制变化范围
                if current_score < 0.3:
                    # 陌生→初识：±0.03
                    max_change = 0.03
                elif current_score < 0.5:
                    # 初识→熟人：±0.025
                    max_change = 0.025
                elif current_score < 0.7:
                    # 熟人→朋友：±0.02
                    max_change = 0.02
                elif current_score < 0.85:
                    # 朋友→好友：±0.015
                    max_change = 0.015
                else:
                    # 好友→挚友：±0.01
                    max_change = 0.01

                affection_change = max(-max_change, min(max_change, affection_change))

                # 如果印象为空或太短，回退到hint
                if not impression or len(impression) < 10:
                    logger.warning("印象生成结果过短，使用原始hint")
                    impression = impression_hint or existing_impression

                logger.debug(f"印象更新: 用户性别判断={detected_gender}, 好感度变化={affection_change:+.3f}")

                return {
                    "impression": impression,
                    "affection_change": affection_change
                }

            except Exception as parse_error:
                logger.warning(f"解析JSON失败: {parse_error}，尝试提取文本")
                # 如果JSON解析失败，尝试直接使用响应作为印象
                return {
                    "impression": response if len(response) > 10 else (impression_hint or existing_impression),
                    "affection_change": 0.0
                }

        except Exception as e:
            logger.error(f"生成印象和好感度失败: {e}")
            # 失败时回退
            return {
                "impression": impression_hint or existing_impression,
                "affection_change": 0.0
            }

    async def _get_user_profile(self, user_id: str) -> dict[str, Any]:
        """从数据库获取用户现有画像

        Args:
            user_id: 用户ID

        Returns:
            dict: 用户画像数据（只包含核心字段）
        """
        try:
            async with get_db_session() as session:
                stmt = select(UserRelationships).where(UserRelationships.user_id == user_id)
                result = await session.execute(stmt)
                profile = result.scalar_one_or_none()

                if profile:
                    # 使用 relationship_text 字段存储印象
                    impression = profile.relationship_text or ""
                    return {
                        "user_name": profile.user_name or user_id,
                        "user_aliases": profile.user_aliases or "",
                        "relationship_text": impression,
                        "relationship_score": float(profile.relationship_score) if profile.relationship_score is not None else _get_base_relationship_score(),
                        "first_met_time": profile.first_met_time,
                    }
                else:
                    # 用户不存在，返回默认值
                    return {
                        "user_name": user_id,
                        "user_aliases": "",
                        "relationship_text": "",
                        "relationship_score": _get_base_relationship_score(),
                        "first_met_time": None,
                    }
        except Exception as e:
            logger.error(f"获取用户画像失败: {e}")
            return {
                "user_name": user_id,
                "user_aliases": "",
                "relationship_text": "",
                "relationship_score": _get_base_relationship_score(),
                "first_met_time": None,
            }



    async def _update_user_profile_in_db(self, user_id: str, profile: dict[str, Any]):
        """更新数据库中的用户画像

        Args:
            user_id: 用户ID
            profile: 画像数据（只包含核心字段：user_aliases, relationship_text, relationship_score）
        """
        try:
            current_time = time.time()

            async with get_db_session() as session:
                stmt = select(UserRelationships).where(UserRelationships.user_id == user_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                # 根据好感度自动计算关系阶段（不再存储到数据库）
                score = profile.get("relationship_score", 0.3)

                if existing:
                    # 更新别名
                    if profile.get("user_aliases"):
                        existing.user_aliases = profile["user_aliases"]

                    # 更新 relationship_text 字段（印象）
                    impression = profile.get("relationship_text", "")
                    if impression:
                        existing.relationship_text = impression

                    existing.relationship_score = score
                    existing.last_impression_update = current_time
                    existing.last_updated = current_time
                    # 如果是首次认识，记录时间
                    if not existing.first_met_time:
                        existing.first_met_time = current_time
                else:
                    # 创建新记录（只写入核心字段）
                    impression = profile.get("relationship_text", "")
                    new_profile = UserRelationships(
                        user_id=user_id,
                        user_name=user_id,
                        user_aliases=profile.get("user_aliases", ""),
                        relationship_text=impression,
                        relationship_score=score,
                        first_met_time=current_time,
                        last_impression_update=current_time,
                        last_updated=current_time
                    )
                    session.add(new_profile)

                await session.commit()

                # 清除缓存，确保下次查询获取最新数据
                try:
                    from src.common.database.optimization.cache_manager import get_cache
                    cache = await get_cache()
                    cache_key = f"user_relationships:filter:[('user_id', '{user_id}')]"
                    await cache.delete(cache_key)
                    logger.debug(f"已清除用户关系缓存: {user_id}")
                except Exception as cache_err:
                    logger.warning(f"清除缓存失败（不影响数据保存）: {cache_err}")

                logger.info(f"用户画像已更新到数据库: {user_id}")

        except Exception as e:
            logger.error(f"更新用户画像到数据库失败: {e}")
            raise

    def _calculate_relationship_stage(self, score: float) -> str:
        """根据好感度分数计算关系阶段

        Args:
            score: 好感度分数(0-1)

        Returns:
            str: 关系阶段
        """
        if score >= 0.9:
            return "bestie"  # 挚友
        elif score >= 0.75:
            return "close_friend"  # 好友
        elif score >= 0.6:
            return "friend"  # 朋友
        elif score >= 0.4:
            return "familiar"  # 熟人
        elif score >= 0.2:
            return "acquaintance"  # 初识
        else:
            return "stranger"  # 陌生人


