import random
from typing import ClassVar

from src.chat.emoji_system.emoji_history import add_emoji_to_history, get_recent_emojis
from src.chat.emoji_system.emoji_manager import MaiEmoji, get_emoji_manager
from src.chat.utils.utils_image import image_path_to_base64

# 导入依赖的系统组件
from src.common.logger import get_logger
from src.config.config import global_config

# 导入新插件系统
from src.plugin_system import BaseAction, ChatMode

# 导入API模块 - 标准Python包方式
from src.plugin_system.apis import llm_api, message_api

logger = get_logger("emoji")


class EmojiAction(BaseAction):
    """表情动作 - 发送表情包

    注意：此 Action 使用旧的激活类型配置方式（已废弃但仍然兼容）。
    BaseAction.go_activate() 的默认实现会自动处理这些旧配置。

    推荐的新写法（迁移示例）：
    ----------------------------------------
    # 移除下面的 activation_type 相关配置，改为重写 go_activate 方法：

    async def go_activate(self, chat_content: str = "", llm_judge_model=None) -> bool:
        # 根据配置选择激活方式
        if global_config.emoji.emoji_activate_type == "llm":
            return await self._llm_judge_activation(
                chat_content=chat_content,
                judge_prompt=\"""
                判定是否需要使用表情动作的条件：
                1. 用户明确要求使用表情包
                2. 这是一个适合表达情绪的场合
                3. 发表情包能使当前对话更有趣
                4. 不要发送太多表情包
                \""",
                llm_judge_model=llm_judge_model
            )
        else:
            # 使用随机激活
            return await self._random_activation(global_config.emoji.emoji_chance)
    ----------------------------------------
    """

    mode_enable = ChatMode.ALL
    parallel_action = True

    # 动作基本信息
    action_name = "emoji"
    action_description = "作为一条全新的消息，发送一个符合当前情景的表情包来生动地表达情绪。"

    # LLM判断提示词
    llm_judge_prompt = """
    判定是否需要使用表情动作的条件：
    1. 用户明确要求使用表情包。
    2. 当前的对话氛围很适合用表情来活跃气氛。
    3. 发送表情包能让互动变得更有趣、更生动。
    4. 请像正常人一样自然地使用表情包，不要过度依赖，也不要刷屏哦。

    请回答"是"或"否"。
    """

    # 动作参数定义
    action_parameters: ClassVar = {}

    # 动作使用场景
    action_require: ClassVar = [
    "1. 用户明确要求使用表情包。",
    "2. 当前的对话氛围很适合用表情来活跃气氛。",
    "3. 发送表情包能让互动变得更有趣、更生动。",
    "4. 请像正常人一样自然地使用表情包，不要过度依赖，也不要刷屏哦。",
    ]

    # 关联类型
    associated_types: ClassVar[list[str]] = ["emoji"]

    async def go_activate(self, chat_content: str = "", llm_judge_model=None) -> bool:
        """根据配置选择激活方式"""
        assert global_config is not None
        if global_config.emoji.emoji_activate_type == "llm":
            return await self._llm_judge_activation(
                judge_prompt=self.llm_judge_prompt, llm_judge_model=llm_judge_model
            )
        if global_config.emoji.emoji_activate_type == "always":
            return True
        return await self._random_activation(global_config.emoji.emoji_chance)

    async def execute(self) -> tuple[bool, str]:
        """执行表情动作"""
        logger.info(f"{self.log_prefix} 决定发送表情")

        try:
            # 1. 获取发送表情的原因
            reason = self.action_data.get("reason", "表达当前情绪")
            main_reply_content = self.action_data.get("main_reply_content", "")
            logger.info(f"{self.log_prefix} 发送表情原因: {reason}")

            # 2. 获取所有有效的表情包对象
            emoji_manager = get_emoji_manager()
            all_emojis_obj: list[MaiEmoji] = [
                e for e in emoji_manager.emoji_objects if not e.is_deleted and e.description
            ]
            if not all_emojis_obj:
                logger.warning(f"{self.log_prefix} 无法获取任何带有描述的有效表情包")
                return False, "无法获取任何带有描述的有效表情包"

            # 3. 根据历史记录筛选表情
            try:
                recent_emojis_desc = get_recent_emojis(self.chat_id, limit=20)
                if recent_emojis_desc:
                    filtered_emojis = [emoji for emoji in all_emojis_obj if emoji.description not in recent_emojis_desc]
                    if filtered_emojis:
                        all_emojis_obj = filtered_emojis
                        logger.info(f"{self.log_prefix} 根据历史记录过滤后，剩余 {len(all_emojis_obj)} 个表情可用")
                    else:
                        logger.warning(f"{self.log_prefix} 过滤后没有可用的表情包，将使用所有表情包")
            except Exception as e:
                logger.error(f"{self.log_prefix} 获取或处理表情发送历史时出错: {e}")

            # 4. 准备情感数据和后备列表
            emotion_map = {}
            all_emojis_data = []

            for emoji in all_emojis_obj:
                b64 = image_path_to_base64(emoji.full_path)
                if not b64:
                    continue

                desc = emoji.description
                emotions = emoji.emotion
                all_emojis_data.append((b64, desc))

                for emo in emotions:
                    if emo not in emotion_map:
                        emotion_map[emo] = []
                    emotion_map[emo].append((b64, desc))

            if not all_emojis_data:
                logger.warning(f"{self.log_prefix} 无法加载任何有效的表情包数据")
                return False, "无法加载任何有效的表情包数据"

            available_emotions = list(emotion_map.keys())
            emoji_base64, emoji_description = "", ""
            chosen_emotion = "表情包"  # 默认描述，避免变量未定义错误

            # 提取精炼描述和关键词的辅助函数（点睛之笔）
            # 新格式: [精炼描述] Keywords: [关键词] Desc: [详细描述]
            # 我们只需要 Desc: 之前的部分
            def extract_refined_info(full_desc: str) -> str:
                return full_desc.split(" Desc:")[0].strip()

            # 4. 根据配置选择不同的表情选择模式
            assert global_config is not None
            if global_config.emoji.emoji_selection_mode == "emotion":
                # --- 情感标签选择模式 ---
                if not available_emotions:
                    logger.warning(f"{self.log_prefix} 获取到的表情包均无情感标签, 将随机发送")
                    emoji_base64, emoji_description = random.choice(all_emojis_data)
                else:
                    # 获取最近的20条消息内容用于判断
                    recent_messages = await message_api.get_recent_messages(chat_id=self.chat_id, limit=20)
                    messages_text = ""
                    if recent_messages:
                        messages_text = await message_api.build_readable_messages(
                            messages=recent_messages,
                            timestamp_mode="normal_no_YMD",
                            truncate=False,
                            show_actions=False,
                        )

                    # 构建prompt让LLM选择情感
                    prompt_addition = ""
                    if main_reply_content:
                        prompt_addition = f"""
                    这是你刚刚生成、准备发送的消息：
                    "{main_reply_content}"
                    """
                    prompt = f"""
                    你是一个正在进行聊天的网友，你需要根据一个理由、最近的聊天记录以及你自己将要发送的消息，从一个情感标签列表中选择最匹配的一个。
                    {prompt_addition}
                    这是最近的聊天记录：
                    {messages_text}

                    这是理由：“{reason}”
                    这里是可用的情感标签：{available_emotions}
                    请直接返回最匹配的那个情感标签，不要进行任何解释或添加其他多余的文字。
                    """

                    assert global_config is not None
                    logger.debug(f"{self.log_prefix} 生成的LLM Prompt: {prompt}")

                    # 调用LLM
                    models = llm_api.get_available_models()
                    chat_model_config = models.get("utils")
                    if not chat_model_config:
                        logger.error(f"{self.log_prefix} 未找到'utils'模型配置，无法调用LLM")
                        return False, "未找到'utils'模型配置"

                    success, chosen_emotion, _, _ = await llm_api.generate_with_model(
                        prompt, model_config=chat_model_config, request_type="emoji"
                    )

                    if not success:
                        logger.warning(f"{self.log_prefix} LLM调用失败: {chosen_emotion}, 将随机选择一个表情包")
                        emoji_base64, emoji_description = random.choice(all_emojis_data)
                    else:
                        chosen_emotion = chosen_emotion.strip().replace('"', "").replace("'", "")
                        logger.info(f"{self.log_prefix} LLM选择的情感: {chosen_emotion}")

                        # 使用模糊匹配来查找最相关的情感标签
                        matched_key = next((key for key in emotion_map if chosen_emotion in key), None)

                        if matched_key:
                            emoji_base64, emoji_description = random.choice(emotion_map[matched_key])
                            logger.info(
                                f"{self.log_prefix} 找到匹配情感 '{chosen_emotion}' (匹配到: '{matched_key}') 的表情包: {emoji_description}"
                            )
                        else:
                            logger.warning(
                                f"{self.log_prefix} LLM选择的情感 '{chosen_emotion}' 不在可用列表中, 将随机选择一个表情包"
                            )
                            emoji_base64, emoji_description = random.choice(all_emojis_data)

            elif global_config.emoji.emoji_selection_mode == "description":
                # --- 详细描述选择模式 ---
                # 获取最近的5条消息内容用于判断
                recent_messages = await message_api.get_recent_messages(chat_id=self.chat_id, limit=20)
                messages_text = ""
                if recent_messages:
                    messages_text = await message_api.build_readable_messages(
                        messages=recent_messages,
                        timestamp_mode="normal_no_YMD",
                        truncate=False,
                        show_actions=False,
                    )

                # 准备表情描述列表（使用精炼描述）
                emoji_descriptions = [extract_refined_info(desc) for _, desc in all_emojis_data]

                # 构建prompt让LLM选择描述
                prompt_addition = ""
                if main_reply_content:
                    prompt_addition = f"""
                这是你刚刚生成、准备发送的消息：
                "{main_reply_content}"
                """
                prompt = f"""
                你是一个正在进行聊天的网友，你需要根据一个理由、最近的聊天记录以及你自己将要发送的消息，从一个表情包描述列表中选择最匹配的一个。
                {prompt_addition}
                这是最近的聊天记录：
                {messages_text}

                这是理由：“{reason}”
                这里是可用的表情包描述：{emoji_descriptions}
                请直接返回最匹配的那个表情包描述，不要进行任何解释或添加其他多余的文字。
                """
                logger.debug(f"{self.log_prefix} 生成的LLM Prompt: {prompt}")

                # 调用LLM
                models = llm_api.get_available_models()
                chat_model_config = models.get("utils")
                if not chat_model_config:
                    logger.error(f"{self.log_prefix} 未找到'utils'模型配置，无法调用LLM")
                    return False, "未找到'utils'模型配置"

                success, chosen_description, _, _ = await llm_api.generate_with_model(
                    prompt, model_config=chat_model_config, request_type="emoji"
                )

                if not success:
                    logger.warning(f"{self.log_prefix} LLM调用失败: {chosen_description}, 将随机选择一个表情包")
                    emoji_base64, emoji_description = random.choice(all_emojis_data)
                else:
                    chosen_description = chosen_description.strip().replace('"', "").replace("'", "")
                    chosen_emotion = chosen_description  # 在描述模式下，用描述作为情感标签
                    logger.info(f"{self.log_prefix} LLM选择的描述: {chosen_description}")

                    # 使用更鲁棒的子字符串匹配逻辑
                    matched_emoji = None
                    for b64, desc in all_emojis_data:
                        # 检查LLM返回的描述是否是数据库中某个表情完整描述的一部分
                        if chosen_description in desc:
                            matched_emoji = (b64, desc)
                            break

                    if matched_emoji:
                        emoji_base64, emoji_description = matched_emoji
                        logger.info(f"{self.log_prefix} 找到匹配描述的表情包: {emoji_description}")
                    else:
                        logger.warning(f"{self.log_prefix} LLM选择的描述无法匹配任何表情包, 将随机选择")
                        emoji_base64, emoji_description = random.choice(all_emojis_data)
            else:
                assert global_config is not None
                logger.error(f"{self.log_prefix} 无效的表情选择模式: {global_config.emoji.emoji_selection_mode}")
                return False, "无效的表情选择模式"

            # 7. 发送表情包并记录历史
            success = await self.send_emoji(emoji_base64)

            if not success:
                logger.error(f"{self.log_prefix} 表情包发送失败")
                await self.store_action_info(
                    action_build_into_prompt=True, action_prompt_display="发送了一个表情包,但失败了", action_done=False
                )
                return False, "表情包发送失败"

            # 发送成功后，记录到历史
            try:
                add_emoji_to_history(self.chat_id, emoji_description)
            except Exception as e:
                logger.error(f"{self.log_prefix} 添加表情到历史记录时出错: {e}")

            # 提取精炼描述用于显示（点睛之笔）
            refined_description = extract_refined_info(emoji_description)

            await self.store_action_info(
                action_build_into_prompt=True, action_prompt_display=f"发送了一个表情包: {refined_description}", action_done=True
            )

            return True, f"发送表情包: {refined_description}"

        except Exception as e:
            logger.error(f"{self.log_prefix} 表情动作执行失败: {e}")
            return False, f"表情发送失败: {e!s}"
