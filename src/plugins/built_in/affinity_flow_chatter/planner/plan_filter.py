"""
PlanFilter: 接收 Plan 对象，根据不同模式的逻辑进行筛选，决定最终要执行的动作。
"""

import re
import time
import traceback
from datetime import datetime
from typing import Any

import orjson
from json_repair import repair_json

from src.chat.utils.chat_message_builder import (
    build_readable_messages_with_id,
)
from src.chat.utils.prompt import global_prompt_manager
from src.common.data_models.info_data_model import ActionPlannerInfo, Plan
from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest
from src.mood.mood_manager import mood_manager
from src.plugin_system.base.component_types import ActionInfo, ChatType
from src.schedule.schedule_manager import schedule_manager

logger = get_logger("plan_filter")

SAKURA_PINK = "\033[38;5;175m"
SKY_BLUE = "\033[38;5;117m"
RESET_COLOR = "\033[0m"


class ChatterPlanFilter:
    """
    根据 Plan 中的模式和信息，筛选并决定最终的动作。
    """

    def __init__(self, chat_id: str, available_actions: list[str]):
        """
        初始化动作计划筛选器。

        Args:
            chat_id (str): 当前聊天的唯一标识符。
            available_actions (List[str]): 当前可用的动作列表。
        """
        self.chat_id = chat_id
        self.available_actions = available_actions
        self.planner_llm = LLMRequest(
            model_set=model_config.model_task_config.planner, request_type="planner"
        )
        self.last_obs_time_mark = 0.0

    async def filter(self, plan: Plan) -> Plan:
        """
        执行筛选逻辑，并填充 Plan 对象的 decided_actions 字段。
        """
        try:
            prompt, used_message_id_list = await self._build_prompt(plan)
            plan.llm_prompt = prompt
            if global_config.debug.show_prompt:
                logger.debug(
                    f"规划器原始提示词:{prompt}"
                )  # 叫你不要改你耳朵聋吗😡😡😡😡😡

            llm_content, _ = await self.planner_llm.generate_response_async(
                prompt=prompt
            )

            if llm_content:
                if global_config.debug.show_prompt:
                    logger.debug(f"LLM规划器原始响应:{llm_content}")

                # 尝试修复JSON格式
                repaired_content = repair_json(llm_content)
                parsed_json = orjson.loads(repaired_content)

                # 确保parsed_json是列表格式
                if isinstance(parsed_json, dict):
                    parsed_json = [parsed_json]

                if isinstance(parsed_json, list):
                    final_actions = []

                    for item in parsed_json:
                        if not isinstance(item, dict):
                            continue

                        # 预解析 action_type 来进行判断
                        thinking = item.get("thinking", "未提供思考过程")
                        actions_obj = item.get("actions", [])

                        # 记录决策历史
                        if (
                            hasattr(global_config.chat, "enable_decision_history")
                            and global_config.chat.enable_decision_history
                        ):
                            action_types_to_log = []
                            actions_to_process_for_log = []
                            if isinstance(actions_obj, dict):
                                actions_to_process_for_log.append(actions_obj)
                            elif isinstance(actions_obj, list):
                                actions_to_process_for_log.extend(actions_obj)

                            action_types_to_log = [
                                single_action.get("action_type", "no_action")
                                for single_action in actions_to_process_for_log
                                if isinstance(single_action, dict)
                            ]

                            if thinking != "未提供思考过程" and action_types_to_log:
                                await self._add_decision_to_history(
                                    plan, thinking, ", ".join(action_types_to_log)
                                )

                        # 严格按照新格式处理actions列表
                        if isinstance(actions_obj, list) and actions_obj:
                            if len(actions_obj) == 0:
                                plan.decided_actions = [
                                    ActionPlannerInfo(
                                        action_type="no_action", reasoning="未提供动作"
                                    )
                                ]
                            else:
                                # 处理每个动作
                                for single_action in actions_obj:
                                    if isinstance(single_action, dict):
                                        final_actions.append(
                                            await self._parse_single_action(
                                                single_action,
                                                used_message_id_list,
                                                plan,
                                            )
                                        )

                        if thinking and thinking != "未提供思考过程":
                            logger.info(
                                f"\n{SAKURA_PINK}思考: {thinking}{RESET_COLOR}\n"
                            )

                        plan.decided_actions = final_actions

        except Exception as e:
            logger.error(f"筛选 Plan 时出错: {e}\n{traceback.format_exc()}")
            plan.decided_actions = [
                ActionPlannerInfo(action_type="no_action", reasoning=f"筛选时出错: {e}")
            ]

        # 在返回最终计划前，打印将要执行的动作
        if plan.decided_actions:
            action_types = [action.action_type for action in plan.decided_actions]
            logger.info(
                f"选择动作: [{SKY_BLUE}{', '.join(action_types) if action_types else '无'}{RESET_COLOR}]"
            )

        return plan

    async def _add_decision_to_history(self, plan: Plan, thought: str, action: str):
        """添加决策记录到历史中"""
        try:
            from src.chat.message_receive.chat_stream import get_chat_manager
            from src.common.data_models.message_manager_data_model import DecisionRecord

            chat_manager = get_chat_manager()
            chat_stream = await chat_manager.get_stream(plan.chat_id)
            if not chat_stream:
                return

            if not thought or not action:
                logger.debug("尝试添加空的决策历史，已跳过")
                return

            context = chat_stream.context
            new_record = DecisionRecord(thought=thought, action=action)

            # 添加新记录
            context.decision_history.append(new_record)

            # 获取历史长度限制
            max_history_length = getattr(
                global_config.chat, "decision_history_length", 3
            )

            # 如果历史记录超过长度，则移除最旧的记录
            if len(context.decision_history) > max_history_length:
                context.decision_history.pop(0)

            logger.debug(f"已添加决策历史，当前长度: {len(context.decision_history)}")

        except Exception as e:
            logger.warning(f"记录决策历史失败: {e}")

    async def _build_decision_history_block(self, plan: Plan) -> str:
        """构建决策历史块"""
        if (
            not hasattr(global_config.chat, "enable_decision_history")
            or not global_config.chat.enable_decision_history
        ):
            return ""
        try:
            from src.chat.message_receive.chat_stream import get_chat_manager

            chat_manager = get_chat_manager()
            chat_stream = await chat_manager.get_stream(plan.chat_id)
            if not chat_stream:
                return ""

            context = chat_stream.context
            if not context.decision_history:
                return ""

            history_records = []
            for record in context.decision_history:
                history_records.append(
                    f"- 思考: {record.thought}\n  - 动作: {record.action}"
                )

            history_str = "\n".join(history_records)
            return f"{history_str}"
        except Exception as e:
            logger.warning(f"构建决策历史块失败: {e}")
            return ""

    async def _build_prompt(self, plan: Plan) -> tuple[str, list]:
        """
        根据 Plan 对象构建提示词。
        """
        try:
            time_block = f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            bot_name = global_config.bot.nickname
            bot_nickname = (
                f",也有人叫你{','.join(global_config.bot.alias_names)}"
                if global_config.bot.alias_names
                else ""
            )
            bot_core_personality = global_config.personality.personality_core
            identity_block = (
                f"你的名字是{bot_name}{bot_nickname}，你{bot_core_personality}："
            )

            schedule_block = ""
            if global_config.planning_system.schedule_enable:
                if activity_info := schedule_manager.get_current_activity():
                    activity = activity_info.get("activity", "未知活动")
                    schedule_block = f"你当前正在进行“{activity}”。(此为你的当前状态，仅供参考。除非被直接询问，否则不要在对话中主动提及。)"

            mood_block = ""
            # 需要情绪模块打开才能获得情绪,否则会引发报错
            if global_config.mood.enable_mood:
                chat_mood = mood_manager.get_mood_by_chat_id(plan.chat_id)
                mood_block = f"你现在的心情是：{chat_mood.mood_state}"

            # 构建决策历史
            decision_history_block = await self._build_decision_history_block(plan)

            # 构建已读/未读历史消息
            read_history_block, unread_history_block, message_id_list = (
                await self._build_read_unread_history_blocks(plan)
            )

            actions_before_now_block = ""

            self.last_obs_time_mark = time.time()

            mentioned_bonus = ""
            if global_config.chat.mentioned_bot_inevitable_reply:
                mentioned_bonus = "\n- 有人提到你"
            if global_config.chat.at_bot_inevitable_reply:
                mentioned_bonus = "\n- 有人提到你，或者at你"

            # 移除no_reply/no_action提示词，如果actions是空列表则自动设置为no_action
            no_action_block = ""

            is_group_chat = plan.chat_type == ChatType.GROUP
            chat_context_description = "你现在正在一个群聊中"
            if not is_group_chat and plan.target_info:
                chat_target_name = (
                    plan.target_info.person_name
                    or plan.target_info.user_nickname
                    or "对方"
                )
                chat_context_description = f"你正在和 {chat_target_name} 私聊"

            action_options_block = await self._build_action_options(
                plan.available_actions
            )

            moderation_prompt_block = "请不要输出违法违规内容，不要输出色情，暴力，政治相关内容，如有敏感内容，请规避。"

            custom_prompt_block = ""
            if global_config.custom_prompt.planner_custom_prompt_content:
                custom_prompt_block = (
                    global_config.custom_prompt.planner_custom_prompt_content
                )

            users_in_chat_str = ""  # TODO: Re-implement user list fetching if needed

            planner_prompt_template = await global_prompt_manager.get_prompt_async(
                "planner_prompt"
            )

            # Prepare format parameters
            # Prepare format parameters
            # 根据配置动态生成回复策略和输出格式的提示词部分
            if global_config.chat.enable_multiple_replies:
                reply_strategy_block = """
# 目标
你的任务是根据当前对话，给出一个或多个动作，构成一次完整的响应组合。
- 主要动作：通常是 reply或respond（如需回复）。
- 辅助动作（可选）：如 emoji、poke_user 等，用于增强表达。

# 决策流程
1. 已读仅供参考，不能对已读执行任何动作。
2. 目标消息必须来自未读历史，并使用其前缀 <m...> 作为 target_message_id。
3. 兴趣度优先原则：每条未读消息后都标注了 [兴趣度: X.XXX]，数值越高表示该消息越值得你关注和回复。在选择回复目标时，**应优先选择兴趣度高的消息**（通常 ≥0.5 表示较高兴趣），除非有特殊情况（如被直接@或提问）。
4. 优先级：
   - 直接针对你：@你、回复你、点名提问、引用你的消息。
   - **兴趣度高的消息**：兴趣度 ≥0.5 的消息应优先考虑回复。
   - 与你强相关的话题或你熟悉的问题。
   - 其他与上下文弱相关的内容最后考虑。
{mentioned_bonus}
5. 多目标：若多人同时需要回应，请在 actions 中并行生成多个 reply，每个都指向各自的 target_message_id。
6. 处理无上下文的纯表情包: 对不含任何实质文本、且无紧密上下文互动的纯**表情包**消息（如消息内容仅为“[表情包：xxxxx]”），应默认选择 `no_action`。
7. 处理失败消息: 绝不能回复任何指示媒体内容（图片、表情包等）处理失败的消息。如果消息中出现如“[表情包(描述生成失败)]”或“[图片(描述生成失败)]”等文字，必须将其视为系统错误提示，并立即选择`no_action`。
8. 正确决定回复时机: 在决定reply或respond前，务必评估当前对话氛围和上下文连贯性。避免在不合适的时机（如对方情绪低落、话题不相关等,对方并没有和你对话,贸然插入会很令人讨厌等）进行回复，以免打断对话流或引起误解。如判断当前不适合回复，请选择`no_action`。
9. 认清自己的身份和角色: 在规划回复时，务必确定对方是不是真的在叫自己。聊天时往往有数百甚至数千个用户，请务必认清自己的身份和角色，避免误以为对方在和自己对话而贸然插入回复，导致尴尬局面。
"""
                output_format_block = """
## 输出格式（只输出 JSON，不要多余文本或代码块）
最终输出必须是一个包含 thinking 和 actions 字段的 JSON 对象，其中 actions 必须是一个列表。

示例（单动作）:
```json
{{
    "thinking": "在这里写下你的思绪流...",
    "actions": [
        {{
            "action_type": "reply",
            "reasoning": "选择该动作的详细理由",
            "action_data": {{
                "target_message_id": "m124",
                "content": "回复内容"
            }}
        }}
    ]
}}
```

示例（多重动作，并行）:
```json
{{
    "thinking": "在这里写下你的思绪流...",
    "actions": [
        {{
            "action_type": "reply",
            "reasoning": "理由A - 这个消息较早且需要明确回复对象",
            "action_data": {{
                 "target_message_id": "m124",
                 "content": "对A的回复",
                 "should_quote_reply": false
            }}
        }},
        {{
            "action_type": "reply",
            "reasoning": "理由B",
            "action_data": {{
                "target_message_id": "m125",
                "content": "对B的回复",
                "should_quote_reply": false
            }}
        }}
    ]
}}
```
"""
            else:
                reply_strategy_block = """
# 目标
你的任务是根据当前对话，**选择一个最需要回应的目标**，并给出一个动作，构成一次完整的响应。
- 主要动作：通常是 reply（如需回复）。
- 辅助动作（可选）：如 emoji、poke_user 等，用于增强表达。

# 决策流程
1. 已读仅供参考，不能对已读执行任何动作。
2. 目标消息必须来自未读历史，并使用其前缀 <m...> 作为 target_message_id。
3. **单一目标原则**: 你必须从所有未读消息中，根据**兴趣度**和**优先级**，选择**唯一一个**最值得回应的目标。
4. 兴趣度优先原则：每条未读消息后都标注了 [兴趣度: X.XXX]，数值越高表示该消息越值得你关注和回复。在选择回复目标时，**应优先选择兴趣度高的消息**（通常 ≥0.5 表示较高兴趣），除非有特殊情况（如被直接@或提问）。
5. 优先级：
   - 直接针对你：@你、回复你、点名提问、引用你的消息。
   - **兴趣度高的消息**：兴趣度 ≥0.5 的消息应优先考虑回复。
   - 与你强相关的话题或你熟悉的问题。
   - 其他与上下文弱相关的内容最后考虑。
{mentioned_bonus}
6. 处理无上下文的纯表情包: 对不含任何实质文本、且无紧密上下文互动的纯**表情包**消息（如消息内容仅为“[表情包：xxxxx]”），应默认选择 `no_action`。
7. 处理失败消息: 绝不能回复任何指示媒体内容（图片、表情包等）处理失败的消息。如果消息中出现如“[表情包(描述生成失败)]”或“[图片(描述生成失败)]”等文字，必须将其视为系统错误提示，并立即选择`no_action`。
8. 正确决定回复时机: 在决定reply或respond前，务必评估当前对话氛围和上下文连贯性。避免在不合适的时机（如对方情绪低落、话题不相关等,对方并没有和你对话,贸然插入会很令人讨厌等）进行回复，以免打断对话流或引起误解。如判断当前不适合回复，请选择`no_action`。
9. 认清自己的身份和角色: 在规划回复时，务必确定对方是不是真的在叫自己。聊天时往往有数百甚至数千个用户，请务必认清自己的身份和角色，避免误以为对方在和自己对话而贸然插入回复，导致尴尬局面。
"""
                output_format_block = """
## 输出格式（只输出 JSON，不要多余文本或代码块）
最终输出必须是一个包含 thinking 和 actions 字段的 JSON 对象，其中 actions 必须是一个**只包含单个动作**的列表。

示例:
```json
{{
    "thinking": "在这里写下你的思绪流...",
    "actions": [
        {{
            "action_type": "reply",
            "reasoning": "选择该动作的详细理由",
            "action_data": {{
                "target_message_id": "m124",
                "content": "回复内容"
            }}
        }}
    ]
}}
```
"""

            format_params = {
                "schedule_block": schedule_block,
                "mood_block": mood_block,
                "time_block": time_block,
                "chat_context_description": chat_context_description,
                "decision_history_block": decision_history_block,
                "read_history_block": read_history_block,
                "unread_history_block": unread_history_block,
                "actions_before_now_block": actions_before_now_block,
                "mentioned_bonus": mentioned_bonus,
                "no_action_block": no_action_block,
                "action_options_text": action_options_block,
                "moderation_prompt": moderation_prompt_block,
                "identity_block": identity_block,
                "custom_prompt_block": custom_prompt_block,
                "bot_name": bot_name,
                "users_in_chat": users_in_chat_str,
                "reply_strategy_block": reply_strategy_block,
                "output_format_block": output_format_block,
            }
            prompt = planner_prompt_template.format(**format_params)
            return prompt, message_id_list
        except Exception as e:
            logger.error(f"构建 Planner 提示词时出错: {e}")
            logger.error(traceback.format_exc())
            return "构建 Planner Prompt 时出错", []

    async def _build_read_unread_history_blocks(
        self, plan: Plan
    ) -> tuple[str, str, list]:
        """构建已读/未读历史消息块"""
        try:
            # 从message_manager获取真实的已读/未读消息
            from src.chat.utils.chat_message_builder import (
                get_raw_msg_before_timestamp_with_chat,
            )
            from src.chat.utils.utils import assign_message_ids

            # 获取聊天流的上下文
            from src.plugin_system.apis.chat_api import get_chat_manager

            chat_manager = get_chat_manager()
            chat_stream = await chat_manager.get_stream(plan.chat_id)
            if not chat_stream:
                logger.warning(f"[plan_filter] 聊天流 {plan.chat_id} 不存在")
                return "最近没有聊天内容。", "没有未读消息。", []

            stream_context = chat_stream.context

            # 获取真正的已读和未读消息
            read_messages = (
                stream_context.history_messages
            )  # 已读消息存储在history_messages中
            if not read_messages:
                from src.common.data_models.database_data_model import DatabaseMessages

                # 如果内存中没有已读消息（比如刚启动），则从数据库加载最近的上下文
                fallback_messages_dicts = await get_raw_msg_before_timestamp_with_chat(
                    chat_id=plan.chat_id,
                    timestamp=time.time(),
                    limit=global_config.chat.max_context_size,
                )
                # 将字典转换为DatabaseMessages对象
                read_messages = [
                    DatabaseMessages.from_dict(msg_dict) for msg_dict in fallback_messages_dicts
                ]

            unread_messages = stream_context.get_unread_messages()  # 获取未读消息

            # 构建已读历史消息块
            if read_messages:
                read_content, _ = await build_readable_messages_with_id(
                    messages=[msg.flatten() for msg in read_messages[-80:]],  # 限制数量
                    timestamp_mode="normal_no_YMD",
                    truncate=False,
                    show_actions=False,
                )
                read_history_block = f"{read_content}"
            else:
                read_history_block = "暂无已读历史消息"

            # 构建未读历史消息块（包含兴趣度）
            message_id_list = []
            if unread_messages:
                # 扁平化未读消息用于计算兴趣度和格式化
                flattened_unread = [msg.flatten() for msg in unread_messages]

                # 尝试获取兴趣度评分（返回以真实 message_id 为键的字典）
                interest_scores = await self._get_interest_scores_for_messages(
                    flattened_unread
                )

                # 为未读消息分配短 id（保持与 build_readable_messages_with_id 的一致结构）
                message_id_list = assign_message_ids(flattened_unread)

                unread_lines = []
                for idx, msg in enumerate(flattened_unread):
                    mapped = message_id_list[idx]
                    synthetic_id = mapped.get("id")
                    real_msg_id = msg.get("message_id") or msg.get("id")
                    if not real_msg_id:
                        continue  # 如果消息没有ID，则跳过

                    msg_time = time.strftime(
                        "%H:%M:%S", time.localtime(msg.get("time", time.time()))
                    )
                    # 构建显示名称: GroupCard(Nickname/ID)
                    user_nickname = msg.get("user_nickname", "")
                    user_cardname = msg.get("user_cardname", "")
                    user_id = msg.get("user_id", "")

                    # 尝试获取 role (兼容 flatten 后的 user_role key)
                    user_role = msg.get("user_role")
                    if not user_role:
                        user_info = msg.get("user_info", {})
                        user_role = user_info.get("role") if isinstance(user_info, dict) else msg.get("role")

                    display_name = user_cardname if user_cardname else (user_nickname if user_nickname else "未知用户")

                    aux_info = []
                    if display_name == user_cardname and user_nickname and user_nickname != display_name:
                        if len(user_nickname) < 10:
                            aux_info.append(user_nickname)

                    if user_id and user_id != str(global_config.bot.qq_account):
                        aux_info.append(user_id)

                    # 处理群身份前缀
                    role_prefix = ""
                    if user_role == "owner":
                        role_prefix = "[群主]"
                    elif user_role == "admin":
                        role_prefix = "[管理员]"

                    if aux_info:
                        sender_name = f"{role_prefix}{display_name}({'/'.join(aux_info)})"
                    else:
                        sender_name = f"{role_prefix}{display_name}"

                    msg_content = msg.get("processed_plain_text", "")

                    # 获取兴趣度信息并显示在提示词中
                    interest_score = interest_scores.get(real_msg_id, 0.0)
                    interest_text = (
                        f" [兴趣度: {interest_score:.3f}]" if interest_score > 0 else ""
                    )

                    # 在未读消息中显示兴趣度，让planner优先选择兴趣度高的消息
                    unread_lines.append(
                        f"<{synthetic_id}> {msg_time} {sender_name}: {msg_content}{interest_text}"
                    )

                unread_history_block = "\n".join(unread_lines)
            else:
                unread_history_block = "暂无未读历史消息"

            return read_history_block, unread_history_block, message_id_list

        except Exception as e:
            logger.error(f"构建已读/未读历史消息块时出错: {e}")
            return "构建已读历史消息时出错", "构建未读历史消息时出错", []

    async def _get_interest_scores_for_messages(
        self, messages: list[dict]
    ) -> dict[str, float]:
        """为消息获取兴趣度评分"""
        interest_scores = {}

        try:
            # 直接使用消息中已预计算的兴趣值，无需重新计算
            for msg_dict in messages:
                try:
                    # 直接使用消息中已预计算的兴趣值
                    interest_score = msg_dict.get("interest_value", 0.3)
                    should_reply = msg_dict.get("should_reply", False)

                    # 构建兴趣度字典
                    interest_scores[msg_dict.get("message_id", "")] = interest_score

                    logger.debug(
                        f"使用消息预计算兴趣值: {interest_score:.3f}, should_reply: {should_reply}"
                    )

                except Exception as e:
                    logger.warning(f"获取消息预计算兴趣值失败: {e}")
                    # 使用默认值
                    interest_scores[msg_dict.get("message_id", "")] = 0.3

        except Exception as e:
            logger.warning(f"获取兴趣度评分失败: {e}")

        return interest_scores

    async def _parse_single_action(
        self, action_json: dict, message_id_list: list, plan: Plan
    ) -> ActionPlannerInfo:
        try:
            action: str = action_json.get("action_type", "no_action")
            reasoning: str = action_json.get("reasoning", "")
            action_data: dict = action_json.get("action_data", {})

            # 严格按照标准格式，如果没有action_data则使用空对象
            if not action_data:
                action_data = {}

            target_message_obj = None
            if "target_message_id" in action_data:
                # 处理 target_message_id，支持多种格式
                original_target_id = action_data.get("target_message_id")

                if original_target_id:
                    # 记录原始ID用于调试
                    logger.debug(f"[{action}] 尝试查找目标消息: {original_target_id}")

                    # 使用统一的查找函数
                    target_message_dict = self._find_message_by_id(
                        original_target_id, message_id_list
                    )

                    if not target_message_dict:
                        logger.warning(
                            f"[{action}] 未找到目标消息: {original_target_id}"
                        )
                        # 统一使用最新消息作为兜底
                        target_message_dict = self._get_latest_message(message_id_list)
                        if target_message_dict:
                            logger.info(
                                f"[{action}] 使用最新消息作为目标: {target_message_dict.get('message_id')}"
                            )
                else:
                    # 如果LLM没有指定target_message_id，统一使用最新消息
                    target_message_dict = self._get_latest_message(message_id_list)

                if target_message_dict:
                    target_message_obj = target_message_dict
                    # 更新 action_data 中的 target_message_id 为真实 ID
                    real_message_id = target_message_dict.get(
                        "message_id"
                    ) or target_message_dict.get("id")
                    if real_message_id:
                        action_data["target_message_id"] = real_message_id
                        logger.debug(
                            f"[{action}] 更新目标消息ID: {original_target_id} -> {real_message_id}"
                        )
                else:
                    # 严格按照标准格式，找不到目标消息则记录错误但不降级
                    logger.error(f"[{action}] 最终未找到任何可用的目标消息")

                # 转换为 DatabaseMessages 对象
                from src.common.data_models.database_data_model import DatabaseMessages

                action_message_obj = None
                if target_message_obj:
                    # 确保字典中有 message_id 字段
                    if (
                        "message_id" not in target_message_obj
                        and "id" in target_message_obj
                    ):
                        target_message_obj["message_id"] = target_message_obj["id"]

                    try:
                        # 使用 from_dict 工厂方法创建对象（自动过滤无效参数）
                        action_message_obj = DatabaseMessages.from_dict(target_message_obj)
                        logger.debug(
                            f"[{action}] 成功转换目标消息为 DatabaseMessages 对象: {action_message_obj.message_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[{action}] 无法将目标消息转换为 DatabaseMessages 对象: {e}",
                            exc_info=True,
                        )
                else:
                    # 严格按照标准格式，找不到目标消息则记录错误
                    if action != "no_action":
                        logger.error(
                            f"[{action}] 找不到目标消息，target_message_id: {action_data.get('target_message_id')}"
                        )

                # reply 动作必须有目标消息，如果仍然为 None，则使用最新消息
                if action in ["reply", "proactive_reply"] and action_message_obj is None:
                    logger.warning(f"[{action}] 目标消息为空，强制使用最新消息作为兜底")
                    latest_message_dict = self._get_latest_message(message_id_list)
                    if latest_message_dict:
                        from src.common.data_models.database_data_model import DatabaseMessages
                        try:
                            action_message_obj = DatabaseMessages.from_dict(latest_message_dict)
                            logger.info(f"[{action}] 成功使用最新消息: {action_message_obj.message_id}")
                        except Exception as e:
                            logger.error(f"[{action}] 无法转换最新消息: {e}")

                return ActionPlannerInfo(
                    action_type=action,
                    reasoning=reasoning,
                    action_data=action_data,
                    action_message=action_message_obj,  # 使用转换后的 DatabaseMessages 对象
                    available_actions=plan.available_actions,
                )
            else:
                # 如果LLM没有指定target_message_id，统一使用最新消息
                target_message_dict = self._get_latest_message(message_id_list)
                action_message_obj = None
                if target_message_dict:
                    from src.common.data_models.database_data_model import DatabaseMessages
                    try:
                        action_message_obj = DatabaseMessages.from_dict(target_message_dict)
                    except Exception as e:
                        logger.error(
                            f"[{action}] 无法将默认的最新消息转换为 DatabaseMessages 对象: {e}",
                            exc_info=True,
                        )

                return ActionPlannerInfo(
                    action_type=action,
                    reasoning=reasoning,
                    action_data=action_data,
                    action_message=action_message_obj,
                )
        except Exception as e:
            logger.error(f"解析单个action时出错: {e}")
            return ActionPlannerInfo(
                action_type="no_action",
                reasoning=f"解析action时出错: {e}",
            )

    async def _build_action_options(
        self, current_available_actions: dict[str, ActionInfo]
    ) -> str:
        action_options_block = ""
        for action_name, action_info in current_available_actions.items():
            # 基础动作信息
            action_description = action_info.description
            action_require = "\n".join(f"- {req}" for req in action_info.action_require)

            # 构建参数的JSON示例
            params_json_list = []
            for param_name, param_desc in action_info.action_parameters.items():
                params_json_list.append(f'            "{param_name}": "<{param_desc}>",')

            # 构建完整的action_data JSON示例
            action_data_lines = ["{"]
            if params_json_list:
                action_data_lines.extend(
                    [line.rstrip(",") for line in params_json_list]
                )
            action_data_lines.append("          }")
            action_data_json = "\n".join(action_data_lines)

            # 使用新的action格式，避免双重花括号
            action_options_block += f"""动作: {action_name}
动作描述: {action_description}
动作使用场景:
{action_require}

你应该像这样使用它:
    {{
        "action_type": "{action_name}",
        "reasoning": "<执行该动作的详细原因>",
        "action_data": {action_data_json}
    }}

"""
        return action_options_block

    def _find_message_by_id(
        self, message_id: str, message_id_list: list
    ) -> dict[str, Any] | None:
        """
        增强的消息查找函数，支持多种格式和模糊匹配
        兼容大模型可能返回的各种格式变体
        """
        if not message_id or not message_id_list:
            return None

        # 1. 标准化处理：去除可能的格式干扰
        original_id = str(message_id).strip()
        normalized_id = original_id.strip("<>\"'").strip()

        if not normalized_id:
            return None

        # 2. 构建候选ID集合，兼容各种可能的格式
        candidate_ids = {normalized_id}

        # 处理纯数字格式 (123 -> m123)
        if normalized_id.isdigit():
            candidate_ids.add(f"m{normalized_id}")

        # 处理m前缀格式 (m123 -> 123)
        if normalized_id.startswith("m") and normalized_id[1:].isdigit():
            candidate_ids.add(normalized_id[1:])

        # 处理包含在文本中的ID格式 (如 "消息m123" -> 提取 m123)

        # 尝试提取各种格式的ID
        id_patterns = [
            r"m\d+",  # m123格式
            r"\d+",  # 纯数字格式
            r"buffered-[a-f0-9-]+",  # buffered-xxxx格式
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",  # UUID格式
        ]

        for pattern in id_patterns:
            matches = re.findall(pattern, normalized_id)
            for match in matches:
                candidate_ids.add(match)

        # 3. 尝试精确匹配
        for candidate in candidate_ids:
            for item in message_id_list:
                if isinstance(item, str):
                    if item == candidate:
                        # 字符串类型没有message对象，返回None
                        return None
                    continue

                if not isinstance(item, dict):
                    continue

                # 匹配短ID
                item_id = item.get("id")
                if item_id and item_id == candidate:
                    return item.get("message")

                # 匹配原始消息ID
                message_obj = item.get("message")
                if isinstance(message_obj, dict):
                    orig_mid = message_obj.get("message_id") or message_obj.get("id")
                    if orig_mid and orig_mid == candidate:
                        return message_obj

        # 4. 尝试模糊匹配（数字部分匹配）
        for candidate in candidate_ids:
            # 提取数字部分进行模糊匹配
            number_part = re.sub(r"[^0-9]", "", candidate)
            if number_part:
                for item in message_id_list:
                    if isinstance(item, dict):
                        item_id = item.get("id", "")
                        item_number = re.sub(r"[^0-9]", "", item_id)

                        # 数字部分匹配
                        if item_number == number_part:
                            logger.debug(f"模糊匹配成功: {candidate} -> {item_id}")
                            return item.get("message")

                        # 检查消息对象中的ID
                        message_obj = item.get("message")
                        if isinstance(message_obj, dict):
                            orig_mid = message_obj.get("message_id") or message_obj.get(
                                "id"
                            )
                            orig_number = (
                                re.sub(r"[^0-9]", "", str(orig_mid)) if orig_mid else ""
                            )
                            if orig_number == number_part:
                                logger.debug(
                                    f"模糊匹配成功(消息对象): {candidate} -> {orig_mid}"
                                )
                                return message_obj

        # 5. 兜底策略：返回最新消息
        if message_id_list:
            latest_item = message_id_list[-1]
            if isinstance(latest_item, dict):
                latest_message = latest_item.get("message")
                if isinstance(latest_message, dict):
                    logger.warning(
                        f"未找到精确匹配的消息ID {original_id}，使用最新消息作为兜底"
                    )
                    return latest_message
                elif latest_message is not None:
                    logger.warning(
                        f"未找到精确匹配的消息ID {original_id}，使用最新消息作为兜底"
                    )
                    return latest_message

        logger.warning(f"未找到任何匹配的消息: {original_id} (候选: {candidate_ids})")
        return None

    def _get_latest_message(self, message_id_list: list) -> dict[str, Any] | None:
        if not message_id_list:
            return None
        return message_id_list[-1].get("message")
