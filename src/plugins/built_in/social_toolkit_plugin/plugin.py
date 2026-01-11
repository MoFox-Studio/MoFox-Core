import asyncio
import datetime
import re
from typing import ClassVar

from dateutil.parser import parse as parse_datetime

from src.chat.message_receive.chat_stream import ChatStream
from src.common.data_models.database_data_model import DatabaseMessages
from src.common.logger import get_logger
from src.manager.async_task_manager import AsyncTask, async_task_manager
from src.person_info.person_info import get_person_info_manager
from src.plugin_system import (
    ActionActivationType,
    BaseAction,
    BasePlugin,
    ComponentInfo,
    ConfigField,
    register_plugin,
)
from src.plugin_system.apis import generator_api, llm_api, send_api
from src.plugin_system.base.component_types import ChatType

from .qq_emoji_list import qq_face

logger = get_logger("set_emoji_like_plugin")

# ============================ AsyncTask ============================


class ReminderTask(AsyncTask):
    def __init__(
        self,
        delay: float,
        stream_id: str,
        group_id: str | None,
        is_group: bool,
        target_user_id: str,
        target_user_name: str,
        event_details: str,
        creator_name: str,
        chat_stream: ChatStream,
    ):
        super().__init__(task_name=f"ReminderTask_{target_user_id}_{datetime.datetime.now().timestamp()}")
        self.delay = delay
        self.stream_id = stream_id
        self.group_id = group_id
        self.is_group = is_group
        self.target_user_id = target_user_id
        self.target_user_name = target_user_name
        self.event_details = event_details
        self.creator_name = creator_name
        self.chat_stream = chat_stream

    async def run(self):
        try:
            if self.delay > 0:
                logger.info(f"等待 {self.delay:.2f} 秒后执行提醒...")
                await asyncio.sleep(self.delay)

            logger.info(f"执行提醒任务: 给 {self.target_user_name} 发送关于 '{self.event_details}' 的提醒")

            extra_info = f"现在是提醒时间，请你以一种符合你人设的、俏皮的方式提醒 {self.target_user_name}。\n提醒内容: {self.event_details}\n设置提醒的人: {self.creator_name}"
            last_message = self.chat_stream.context.get_last_message()
            reply_message_dict = last_message.flatten() if last_message else None
            success, reply_set, _ = await generator_api.generate_reply(
                chat_stream=self.chat_stream,
                extra_info=extra_info,
                reply_message=reply_message_dict,
                request_type="plugin.reminder.remind_message",
            )

            if success and reply_set:
                for i, (_, text) in enumerate(reply_set):
                    if self.is_group:
                        message_payload = []
                        if i == 0:
                            message_payload.append({"type": "at", "data": {"qq": self.target_user_id}})
                        message_payload.append({"type": "text", "data": {"text": f" {text}"}})
                        await send_api.adapter_command_to_stream(
                            action="send_group_msg",
                            params={"group_id": self.group_id, "message": message_payload},
                            stream_id=self.stream_id,
                        )
                    else:
                        await send_api.text_to_stream(text=text, stream_id=self.stream_id)
            else:
                # Fallback message
                reminder_text = f"叮咚！这是 {self.creator_name} 让我准时提醒你的事情：\n\n{self.event_details}"
                if self.is_group:
                    message_payload = [
                        {"type": "at", "data": {"qq": self.target_user_id}},
                        {"type": "text", "data": {"text": f" {reminder_text}"}},
                    ]
                    await send_api.adapter_command_to_stream(
                        action="send_group_msg",
                        params={"group_id": self.group_id, "message": message_payload},
                        stream_id=self.stream_id,
                    )
                else:
                    await send_api.text_to_stream(text=reminder_text, stream_id=self.stream_id)

            logger.info(f"提醒任务 {self.task_name} 成功完成。")

        except Exception as e:
            logger.error(f"执行提醒任务 {self.task_name} 时出错: {e}")


# =============================== Actions ===============================


def get_emoji_id(emoji_input: str) -> str | None:
    """根据输入获取表情ID"""
    # 如果输入本身就是数字ID，直接返回
    if emoji_input.isdigit() or (isinstance(emoji_input, str) and emoji_input.startswith("😊")):
        if emoji_input in qq_face:
            return emoji_input

    # 尝试从 "[表情：xxx]" 格式中提取
    match = re.search(r"\[表情：(.+?)\]", emoji_input)
    if match:
        emoji_name = match.group(1).strip()
    else:
        emoji_name = emoji_input.strip()

    # 遍历查找
    for key, value in qq_face.items():
        # value 的格式是 "[表情：xxx]"
        if f"[表情：{emoji_name}]" == value:
            return key

    return None


# ===== Action组件 =====


class PokeAction(BaseAction):
    """发送戳一戳动作"""

    # === 基本信息（必须填写）===
    action_name = "poke_user"
    action_description = "戳一戳其他用户。这是一个需要谨慎使用的互动方式，默认只戳一次。群聊中应当克制使用，私聊中可以适当主动。"
    activation_type = ActionActivationType.ALWAYS
    parallel_action = True

    # === 功能描述（必须填写）===
    action_parameters: ClassVar[dict] = {
        "user_name": "需要戳一戳的用户的名字 (可选)",
        "user_id": "需要戳一戳的用户的ID (可选，优先级更高)",
        "times": "需要戳一戳的次数 (默认为 1，最多3次)",
    }
    action_require: ClassVar[list] = [
        "用户明确要求戳某人时必须使用",
        "私聊场景：可以在适当的互动时机主动使用（如回应戳一戳、俏皮互动等）",
        "群聊场景：应当非常克制，仅在用户明确要求或有充分理由时才使用",
    ]
    llm_judge_prompt = """
    判定是否需要使用戳一戳动作的条件：
    
    **必须遵守的严格规则：**
    1. **用户明确要求**: 当用户明确说"戳XX"、"戳一下XX"等直接指令时，必须使用。
    
    2. **群聊场景（非常克制）**:
       - 群聊中应当非常谨慎，避免在公共场合频繁打扰他人
       - 仅在以下情况考虑使用：用户明确要求、需要紧急提醒某人、或有特别充分的互动理由
       - 如果最近已经在群里戳过任何人，必须回答"否"
       - 群聊中不要随意主动使用，除非有明确必要性
    
    3. **私聊场景（可以主动）**:
       - 私聊中可以更加主动和俏皮
       - 在以下情况可以使用：回应对方的戳一戳、轻松愉快的互动氛围、想要增添趣味时
       - 但如果最近已经戳过对方，应避免频繁使用
    
    4. **频率限制（重要）**:
       - 如果最近已经戳过同一个人，必须回答"否"
       - 默认只戳一次，不要多次戳别人（除非用户明确要求多次）
       - 注意对方的情绪反应，如果对方看起来不高兴或不想被打扰，必须回答"否"
    
    5. **禁止情况**:
       - 对方情绪低落、生气、不耐烦时，严禁使用
       - 严肃的对话场景中，严禁使用
       - 刚刚戳过的情况下，严禁再次使用
    
    **判断逻辑**:
    - 首先判断是群聊还是私聊
    - 群聊：除非用户明确要求或有特殊必要性，否则回答"否"
    - 私聊：可以在合适的互动氛围中主动使用，但要注意频率
    - 检查是否最近已经戳过，如果是则回答"否"
    - 评估对方情绪和对话氛围是否适合
    
    请严格根据上述规则，仅回答"是"或"否"。
    """
    associated_types: ClassVar[list[str]] = ["text"]

    async def execute(self) -> tuple[bool, str]:
        """执行戳一戳的动作"""
        user_id = self.action_data.get("user_id")
        user_name = self.action_data.get("user_name")

        try:
            times = int(self.action_data.get("times", 1))
            if times > 3:
                times = 3
        except (ValueError, TypeError):
            times = 1

        # 优先使用 user_id
        if not user_id:
            if not user_name:
                logger.warning("戳一戳动作缺少 'user_id' 或 'user_name' 参数。")
                return False, "缺少用户标识参数"

            # 备用方案：通过 user_name 查找
            user_info = await get_person_info_manager().get_person_info_by_name(user_name)
            if not user_info or not user_info.get("user_id"):
                logger.info(f"找不到名为 '{user_name}' 的用户。")
                return False, f"找不到名为 '{user_name}' 的用户"
            user_id = user_info.get("user_id")

        display_name = user_name or user_id

        # 构建戳一戳的参数
        poke_args = {"qq_id": str(user_id)}

        for i in range(times):
            logger.info(f"正在向 {display_name} ({user_id}) 发送第 {i + 1}/{times} 次戳一戳...")
            await self.send_command(
                "SEND_POKE", args=poke_args, storage_message=False
            )
            # 添加一个延迟，避免因发送过快导致后续戳一戳失败
            await asyncio.sleep(1.5)

        success_message = f"已向 {display_name} 发送 {times} 次戳一戳。"
        await self.store_action_info(
            action_build_into_prompt=True, action_prompt_display=success_message, action_done=True
        )
        return True, success_message


class SetEmojiLikeAction(BaseAction):
    """设置消息表情回应"""

    # === 基本信息（必须填写）===
    action_name = "set_emoji_like"
    action_description = "为某条已经存在的消息添加‘贴表情’回应（类似点赞），而不是发送新消息。可以在觉得某条消息非常有趣、值得赞同或者需要特殊情感回应时主动使用。"
    activation_type = ActionActivationType.ALWAYS
    chat_type_allow = ChatType.GROUP
    parallel_action = True

    # === 功能描述（必须填写）===
    action_parameters: ClassVar[dict] = {
        "set": "是否设置回应 (True/False)",
    }
    action_require: ClassVar[list] = [
        "当需要对一个已存在消息进行‘贴表情’回应时使用",
        "这是一个对旧消息的操作，而不是发送新消息",
    ]
    llm_judge_prompt = """
    判定是否需要使用贴表情动作的条件：
    1. 这是一个适合表达强烈情绪的场合，例如非常有趣、赞同、惊讶等。
    2. 不要发送太多表情包，如果最近已经发送过表情包，请回答"否"。
    3. 仅在群聊中使用。

    请回答"是"或"否"。
    """
    associated_types: ClassVar[list[str]] = ["text"]

    # 重新启用完整的表情库
    emoji_options: ClassVar[list] = []
    for name in qq_face.values():
        match = re.search(r"\[表情：(.+?)\]", name)
        if match:
            emoji_options.append(match.group(1))

    async def execute(self) -> tuple[bool, str]:
        """执行设置表情回应的动作"""
        # 检查是否在群聊中，该动作仅在群聊中有效
        if not self.is_group:
            logger.warning("set_emoji_like 动作仅在群聊中有效，当前为私聊场景")
            await self.store_action_info(
                action_prompt_display="贴表情失败: 该功能仅在群聊中可用", action_done=False
            )
            return False, "该功能仅在群聊中可用"

        message_id = None
        set_like = self.action_data.get("set", True)

        if self.has_action_message:
            if isinstance(self.action_message, DatabaseMessages):
                message_id = self.action_message.message_id
                logger.info(f"获取到的消息ID: {message_id}")
            elif isinstance(self.action_message, dict):
                message_id = self.action_message.get("message_id")
                logger.info(f"获取到的消息ID: {message_id}")

        if not message_id:
            logger.error("未提供有效的消息或消息ID")
            await self.store_action_info(action_prompt_display="贴表情失败: 未提供消息ID", action_done=False)
            return False, "未提供消息ID"

        # 校验 message_id 是否为有效数字（过滤 "notice" 等非消息 ID）
        if not str(message_id).isdigit():
            logger.warning(f"消息ID '{message_id}' 无效，无法执行贴表情动作。该动作不支持通知类事件。")
            await self.store_action_info(
                action_prompt_display=f"贴表情失败: 消息ID '{message_id}' 无效", action_done=False
            )
            return False, f"消息ID '{message_id}' 无效"

        available_models = llm_api.get_available_models()
        if "utils_small" not in available_models:
            logger.error("未找到 'utils_small' 模型配置，无法选择表情")
            return False, "表情选择功能配置错误"

        model_to_use = available_models["utils_small"]

        # 统一处理 DatabaseMessages 和字典
        if isinstance(self.action_message, DatabaseMessages):
            context_text = self.action_message.processed_plain_text or ""
        else:
            context_text = self.action_message.get("processed_plain_text", "")

        if not context_text:
            logger.error("无法找到动作选择的原始消息文本")
            return False, "无法找到动作选择的原始消息文本"

        prompt = (
            f"**任务：**\n"
            f"根据以下消息，从“可用表情列表”中选择一个最合适的表情名称来回应。\n\n"
            f"**规则（必须严格遵守）：**\n"
            f"1.  **只能**从下面的“可用表情列表”中选择一个表情名称。\n"
            f"2.  你的回答**必须**只包含你选择的表情名称，**不能**有任何其他文字、标点、解释或空格。\n"
            f"3.  你的回答**不能**包含 `[表情：]` 或 `[]` 等符号。\n\n"
            f"**消息内容：**\n"
            f"'{context_text}'\n\n"
            f"**可用表情列表：**\n"
            f"{', '.join(self.emoji_options)}\n\n"
            f"**示例：**\n"
            f"-   如果认为“赞”最合适，你的回答**必须**是：`赞`\n"
            f"-   如果认为“笑哭”最合适，你的回答**必须**是：`笑哭`\n\n"
            f"**你的回答：**"
        )

        success, response, _, _ = await llm_api.generate_with_model(
            prompt, model_config=model_to_use, request_type="plugin.set_emoji_like.select_emoji"
        )

        if not success or not response:
            logger.error("表情选择模型未能返回有效的表情名称。")
            await self.store_action_info(
                action_prompt_display="贴表情失败:表情选择模型未能返回有效的表情名称。",
                action_done=False,
            )
            return False, "无法选择合适的表情。"

        chosen_emoji_name = response.strip()
        logger.info(f"模型选择的表情是: '{chosen_emoji_name}'")

        emoji_id = get_emoji_id(chosen_emoji_name)

        if not emoji_id:
            logger.error(f"模型选择的表情 '{chosen_emoji_name}' 无法匹配到有效的表情ID。可能是模型违反了规则。")
            await self.store_action_info(
                action_prompt_display=f"贴表情失败: 找不到表情 '{chosen_emoji_name}'",
                action_done=False,
            )
            return False, f"找不到表情: '{chosen_emoji_name}'"

        try:
            success = await self.send_command(
                command_name="SET_EMOJI_LIKE",
                args={"message_id": message_id, "emoji_id": emoji_id, "set": set_like},
                storage_message=False,
            )
            if success:
                display_message = f"贴上了表情: {chosen_emoji_name}"
                logger.info(display_message)
                await self.store_action_info(
                    action_build_into_prompt=True,
                    action_prompt_display=display_message,
                    action_done=True,
                )
                return True, "成功设置表情回应"
            else:
                logger.error("通过适配器设置表情回应失败")
                await self.store_action_info(action_prompt_display="贴表情失败: 适配器返回失败", action_done=False)
                return False, "设置表情回应失败"

        except Exception as e:
            logger.error(f"设置表情回应时发生异常: {e}")
            await self.store_action_info(action_prompt_display=f"贴表情失败: {e}", action_done=False)
            return False, f"设置表情回应失败: {e}"


class RemindAction(BaseAction):
    """一个能从对话中智能识别并设置定时提醒的动作。"""

    # === 基本信息 ===
    action_name = "set_reminder"
    action_description = "根据用户的对话内容，智能地设置一个未来的提醒事项。"
    activation_type = ActionActivationType.KEYWORD
    activation_keywords: ClassVar[list[str]] = ["提醒", "叫我", "记得", "别忘了"]
    chat_type_allow = ChatType.ALL
    parallel_action = True

    # === LLM 判断与参数提取 ===
    llm_judge_prompt = ""
    action_parameters: ClassVar[dict] = {}
    action_require: ClassVar[list] = [
        "当用户请求在未来的某个时间点提醒他/她或别人某件事时使用",
        "适用于包含明确时间信息和事件描述的对话",
        "例如：'10分钟后提醒我收快递'、'明天早上九点喊一下李四参加晨会'",
    ]

    async def execute(self) -> tuple[bool, str]:
        """执行设置提醒的动作"""
        user_name = self.action_data.get("user_name")
        remind_time_str = self.action_data.get("remind_time")
        event_details = self.action_data.get("event_details")

        if not all([user_name, remind_time_str, event_details]):
            missing_params = [
                p
                for p, v in {
                    "user_name": user_name,
                    "remind_time": remind_time_str,
                    "event_details": event_details,
                }.items()
                if not v
            ]
            error_msg = f"缺少必要的提醒参数: {', '.join(missing_params)}"
            logger.warning(f"[ReminderPlugin] LLM未能提取完整参数: {error_msg}")
            return False, error_msg

        # 1. 解析时间
        try:
            assert isinstance(remind_time_str, str)
            # 优先尝试直接解析
            try:
                target_time = parse_datetime(remind_time_str, fuzzy=True)
            except Exception as e:
                # 如果直接解析失败，调用 LLM 进行转换
                logger.info(f"[ReminderPlugin] 直接解析时间 '{remind_time_str}' 失败，尝试使用 LLM 进行转换...")

                # 获取所有可用的模型配置
                available_models = llm_api.get_available_models()
                if "utils_small" not in available_models:
                    raise ValueError("未找到 'utils_small' 模型配置，无法解析时间") from e

                # 明确使用 'planner' 模型
                model_to_use = available_models["utils_small"]

                # 在执行时动态获取当前时间
                current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                prompt = (
                    f"请将以下自然语言时间短语转换为一个未来的、标准的 'YYYY-MM-DD HH:MM:SS' 格式。"
                    f"请只输出转换后的时间字符串，不要包含任何其他说明或文字。\n"
                    f"作为参考，当前时间是: {current_time_str}\n"
                    f"需要转换的时间短语是: '{remind_time_str}'\n"
                    f"规则:\n"
                    f"- 如果用户没有明确指出是上午还是下午，请根据当前时间判断。例如，如果当前是上午，用户说‘8点’，则应理解为今天的8点；如果当前是下午，用户说‘8点’，则应理解为今天的20点。\n"
                    f"- 如果转换后的时间早于当前时间，则应理解为第二天的时间。\n"
                    f"示例:\n"
                    f"- 当前时间: 2025-09-16 10:00:00, 用户说: '8点' -> '2025-09-17 08:00:00'\n"
                    f"- 当前时间: 2025-09-16 14:00:00, 用户说: '8点' -> '2025-09-16 20:00:00'\n"
                    f"- 当前时间: 2025-09-16 23:00:00, 用户说: '晚上10点' -> '2025-09-17 22:00:00'"
                )

                success, response, _, _ = await llm_api.generate_with_model(
                    prompt, model_config=model_to_use, request_type="plugin.reminder.time_parser"
                )

                if not success or not response:
                    raise ValueError(f"LLM未能返回有效的时间字符串: {response}") from e

                converted_time_str = response.strip()
                logger.info(f"[ReminderPlugin] LLM 转换结果: '{converted_time_str}'")
                target_time = parse_datetime(converted_time_str, fuzzy=False)

        except Exception as e:
            logger.error(f"[ReminderPlugin] 无法解析或转换时间字符串 '{remind_time_str}': {e}")
            await self.send_text(f"抱歉，我无法理解您说的时间 '{remind_time_str}'，提醒设置失败。")
            return False, f"无法解析时间 '{remind_time_str}'"

        now = datetime.datetime.now()
        if target_time <= now:
            await self.send_text("提醒时间必须是一个未来的时间点哦，提醒设置失败。")
            return False, "提醒时间必须在未来"

        delay_seconds = (target_time - now).total_seconds()

        # 2. 解析用户
        person_manager = get_person_info_manager()
        user_id_to_remind = None
        user_name_to_remind = ""

        assert isinstance(user_name, str)

        if user_name.strip() in ["自己", "我", "me"]:
            user_id_to_remind = self.user_id
            user_name_to_remind = self.user_nickname
        else:
            # 1. 精确匹配
            user_info = await person_manager.get_person_info_by_name(user_name)

            # 2. 包含匹配
            if not user_info:
                # 使用数据库查询获取所有用户进行包含匹配
                from src.common.database.api.crud import CRUDBase
                from src.common.database.core.models import PersonInfo
                crud = CRUDBase(PersonInfo)
                all_records = await crud.get_multi(limit=1000)  # 限制数量避免性能问题
                for record in all_records:
                    if record.person_name and user_name in record.person_name:
                        user_info = await person_manager.get_values(record.person_id, ["user_id", "user_nickname"])
                        break

            # 3. 模糊匹配 (此处简化为字符串相似度)
            if not user_info:
                best_match = None
                highest_similarity = 0
                import difflib

                # 使用数据库查询获取所有用户进行模糊匹配
                crud = CRUDBase(PersonInfo)
                all_records = await crud.get_multi(limit=1000)  # 限制数量避免性能问题
                for record in all_records:
                    if record.person_name:
                        similarity = difflib.SequenceMatcher(None, user_name, record.person_name).ratio()
                        if similarity > highest_similarity:
                            highest_similarity = similarity
                            best_match = record.person_id

                if best_match and highest_similarity > 0.6:  # 相似度阈值
                    user_info = await person_manager.get_values(best_match, ["user_id", "user_nickname"])

            if not user_info or not user_info.get("user_id"):
                logger.warning(f"[ReminderPlugin] 找不到名为 '{user_name}' 的用户")
                await self.send_text(f"抱歉，我的联系人里找不到叫做 '{user_name}' 的人，提醒设置失败。")
                return False, f"用户 '{user_name}' 不存在"
            user_id_to_remind = user_info.get("user_id")
            user_name_to_remind = user_info.get("user_nickname") or user_name

        # 3. 创建并调度异步任务
        try:
            assert user_id_to_remind is not None
            assert event_details is not None

            reminder_task = ReminderTask(
                delay=delay_seconds,
                stream_id=self.chat_stream.stream_id,
                group_id=self.chat_stream.group_info.group_id
                if self.is_group and self.chat_stream.group_info
                else None,
                is_group=self.is_group,
                target_user_id=str(user_id_to_remind),
                target_user_name=str(user_name_to_remind),
                event_details=str(event_details),
                creator_name=str(self.user_nickname),
                chat_stream=self.chat_stream,
            )
            await async_task_manager.add_task(reminder_task)

            # 4. 生成并发送确认消息
            extra_info = f"你已经成功设置了一个提醒，请以一种符合你人设的、俏皮的方式回复用户。\n提醒时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')}\n提醒对象: {user_name_to_remind}\n提醒内容: {event_details}"
            last_message = self.chat_stream.context.get_last_message()
            reply_message_dict = last_message.flatten() if last_message else None
            success, reply_set, _ = await generator_api.generate_reply(
                chat_stream=self.chat_stream,
                extra_info=extra_info,
                reply_message=reply_message_dict,
                request_type="plugin.reminder.confirm_message",
            )
            if success and reply_set:
                for _, text in reply_set:
                    await self.send_text(text)
            else:
                # Fallback message
                fallback_message = f"好的，我记下了。\n将在 {target_time.strftime('%Y-%m-%d %H:%M:%S')} 提醒 {user_name_to_remind}：\n{event_details}"
                await self.send_text(fallback_message)

            return True, "提醒设置成功"
        except Exception as e:
            logger.error(f"[ReminderPlugin] 创建提醒任务时出错: {e}")
            await self.send_text("抱歉，设置提醒时发生了一点内部错误。")
            return False, "设置提醒时发生内部错误"


# ===== 插件注册 =====
@register_plugin
class SetEmojiLikePlugin(BasePlugin):
    """一个集合多种实用功能的插件，旨在提升聊天体验和效率。"""

    # 插件基本信息
    plugin_name: str = "social_toolkit_plugin"  # 内部标识符
    enable_plugin: bool = True
    dependencies: ClassVar[list[str]] = []  # 插件依赖列表
    python_dependencies: ClassVar[list[str]] = []  # Python包依赖列表，现在使用内置API
    config_file_name: str = "config.toml"  # 配置文件名

    # 配置节描述
    config_section_descriptions: ClassVar[dict] = {"plugin": "插件基本信息", "components": "插件组件"}

    # 配置Schema定义
    config_schema: ClassVar[dict] = {
        "plugin": {
            "name": ConfigField(type=str, default="set_emoji_like", description="插件名称"),
            "version": ConfigField(type=str, default="1.0.0", description="插件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="1.1", description="配置版本"),
        },
        "components": {
            "action_set_emoji_like": ConfigField(type=bool, default=True, description="是否启用设置表情回应功能"),
            "action_poke_enable": ConfigField(type=bool, default=True, description="是否启用戳一戳功能"),
            "action_set_reminder_enable": ConfigField(type=bool, default=True, description="是否启用定时提醒功能"),
        },
    }

    def get_plugin_components(self) -> list[tuple[ComponentInfo, type]]:
        enable_components = []
        if self.get_config("components.action_set_emoji_like"):
            enable_components.append((SetEmojiLikeAction.get_action_info(), SetEmojiLikeAction))
        if self.get_config("components.action_poke_enable"):
            enable_components.append((PokeAction.get_action_info(), PokeAction))
        if self.get_config("components.action_set_reminder_enable"):
            enable_components.append((RemindAction.get_action_info(), RemindAction))
        return enable_components
