"""Action 组件基类

Action 是插件的一种组件类型，用于处理聊天中的动作逻辑。

激活机制：推荐通过重写 go_activate() 方法来自定义激活逻辑。
旧版类属性激活方式 (focus_activation_type 等) 已弃用但仍然兼容。
"""

import asyncio
import random
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from src.chat.message_receive.chat_stream import ChatStream
from src.common.data_models.database_data_model import DatabaseMessages
from src.common.logger import get_logger
from src.plugin_system.apis import database_api, message_api, send_api
from src.plugin_system.base.component_types import ActionActivationType, ActionInfo, ChatMode, ChatType, ComponentType

if TYPE_CHECKING:
    from src.llm_models.utils_model import LLMRequest

logger = get_logger("base_action")


class BaseAction(ABC):
    """Action组件基类

    Action是插件的一种组件类型，用于处理聊天中的动作逻辑

    ==================================================================================
    新的激活机制 (推荐使用)
    ==================================================================================
    推荐通过重写 go_activate() 方法来自定义激活逻辑：

    示例 1 - 关键词激活：
        async def go_activate(self, llm_judge_model=None) -> bool:
            return await self._keyword_match(["你好", "hello"])

    示例 2 - LLM 判断激活：
        async def go_activate(self, llm_judge_model=None) -> bool:
            return await self._llm_judge_activation(
                "当用户询问天气信息时激活",
                llm_judge_model
            )

    示例 3 - 组合多种条件：
        async def go_activate(self, llm_judge_model=None) -> bool:
            # 30% 随机概率，或者匹配关键词
            if await self._random_activation(0.3):
                return True
            return await self._keyword_match(["表情", "emoji"])

    提供的工具函数：
    - _random_activation(probability): 随机激活
    - _keyword_match(keywords, case_sensitive): 关键词匹配（自动获取聊天内容）
    - _llm_judge_activation(judge_prompt, llm_judge_model): LLM 判断（自动获取聊天内容）

    注意：聊天内容会自动从实例属性中获取，无需手动传入。

    ==================================================================================
    旧的激活机制 (已废弃，但仍然兼容)
    ==================================================================================
    子类可以通过类属性定义激活条件（已废弃，但 go_activate() 的默认实现会使用这些）：
    - focus_activation_type: 专注模式激活类型
    - normal_activation_type: 普通模式激活类型
    - activation_keywords: 激活关键词列表
    - keyword_case_sensitive: 关键词是否区分大小写
    - random_activation_probability: 随机激活概率
    - llm_judge_prompt: LLM判断提示词

    ==================================================================================
    其他类属性
    ==================================================================================
    - mode_enable: 启用的聊天模式
    - parallel_action: 是否允许并行执行

    二步Action相关属性：
    - is_two_step_action: 是否为二步Action
    - step_one_description: 第一步的描述
    - sub_actions: 子Action列表
    """

    # 二步Action相关类属性
    is_two_step_action: bool = False
    """是否为二步Action。如果为True，Action将分两步执行：第一步选择操作，第二步执行具体操作"""
    step_one_description: str = ""
    """第一步的描述，用于向LLM展示Action的基本功能"""
    sub_actions: ClassVar[list[tuple[str, str, dict[str, str]]] ] = []
    """子Action列表，格式为[(子Action名, 子Action描述, 子Action参数)]。仅在二步Action中使用"""

    def __init__(
        self,
        action_data: dict,
        reasoning: str,
        cycle_timers: dict,
        thinking_id: str,
        chat_stream: ChatStream,
        log_prefix: str = "",
        plugin_config: dict | None = None,
        action_message: dict | None = None,
        **kwargs,
    ):
        # sourcery skip: hoist-similar-statement-from-if, merge-else-if-into-elif, move-assign-in-block, swap-if-else-branches, swap-nested-ifs
        """初始化Action组件

        Args:
            action_data: 动作数据
            reasoning: 执行该动作的理由
            cycle_timers: 计时器字典
            thinking_id: 思考ID
            chat_stream: 聊天流对象
            log_prefix: 日志前缀
            plugin_config: 插件配置字典
            action_message: 消息数据
            **kwargs: 其他参数
        """
        if plugin_config is None:
            plugin_config = {}
        self.action_data = action_data
        self.reasoning = reasoning
        self.cycle_timers = cycle_timers
        self.thinking_id = thinking_id
        self.log_prefix = log_prefix

        if plugin_config is None:
            plugin_config = getattr(self.__class__, "plugin_config", {})

        self.plugin_config = plugin_config or {}
        """对应的插件配置"""

        # 设置动作基本信息实例属性
        self.action_name: str = getattr(self, "action_name", self.__class__.__name__.lower().replace("action", ""))
        """Action的名字"""
        self.action_description: str = getattr(self, "action_description", self.__doc__ or "Action组件")
        """Action的描述"""
        self.action_parameters: dict = getattr(self.__class__, "action_parameters", {}).copy()
        self.action_require: list[str] = getattr(self.__class__, "action_require", []).copy()

        # 设置激活类型实例属性（从类属性复制，提供默认值）
        self.focus_activation_type = getattr(self.__class__, "focus_activation_type", ActionActivationType.ALWAYS)
        """FOCUS模式下的激活类型"""
        self.normal_activation_type = getattr(self.__class__, "normal_activation_type", ActionActivationType.ALWAYS)
        """NORMAL模式下的激活类型"""
        self.activation_type = getattr(self.__class__, "activation_type", self.focus_activation_type)
        """激活类型"""
        self.random_activation_probability: float = getattr(self.__class__, "random_activation_probability", 0.0)
        """当激活类型为RANDOM时的概率"""
        self.llm_judge_prompt: str = getattr(self.__class__, "llm_judge_prompt", "")
        """协助LLM进行判断的Prompt"""
        self.activation_keywords: list[str] = getattr(self.__class__, "activation_keywords", []).copy()
        """激活类型为KEYWORD时的KEYWORDS列表"""
        self.keyword_case_sensitive: bool = getattr(self.__class__, "keyword_case_sensitive", False)
        self.mode_enable: ChatMode = getattr(self.__class__, "mode_enable", ChatMode.ALL)
        self.parallel_action: bool = getattr(self.__class__, "parallel_action", True)
        self.associated_types: list[str] = getattr(self.__class__, "associated_types", []).copy()
        self.chat_type_allow: ChatType = getattr(self.__class__, "chat_type_allow", ChatType.ALL)

        # 二步Action相关实例属性
        self.is_two_step_action: bool = getattr(self.__class__, "is_two_step_action", False)
        self.step_one_description: str = getattr(self.__class__, "step_one_description", "")
        self.sub_actions: list[tuple[str, str, dict[str, str]]] = getattr(self.__class__, "sub_actions", []).copy()
        self._selected_sub_action: str | None = None
        """当前选择的子Action名称，用于二步Action的状态管理"""

        # =============================================================================
        # 便捷属性 - 直接在初始化时获取常用聊天信息（带类型注解）
        # =============================================================================

        # 获取聊天流对象
        self.chat_stream = chat_stream or kwargs.get("chat_stream")
        self.chat_id = self.chat_stream.stream_id
        self.platform = getattr(self.chat_stream, "platform", None)

        # 初始化基础信息（带类型注解）
        self.action_message = action_message

        self.group_id = None
        self.group_name = None
        self.user_id = None
        self.user_nickname = None
        self.is_group = False
        self.target_id = None
        self.has_action_message = False

        if self.action_message:
            self.has_action_message = True
        else:
            self.action_message = {}

        if self.has_action_message:
            if self.action_name != "no_reply":
                # 统一处理 DatabaseMessages 对象和字典
                if isinstance(self.action_message, DatabaseMessages):
                    self.group_id = str(self.action_message.group_info.group_id if self.action_message.group_info else None)
                    self.group_name = self.action_message.group_info.group_name if self.action_message.group_info else None
                    self.user_id = str(self.action_message.user_info.user_id)
                    self.user_nickname = self.action_message.user_info.user_nickname
                else:
                    self.group_id = str(self.action_message.get("chat_info_group_id", None))
                    self.group_name = self.action_message.get("chat_info_group_name", None)
                    self.user_id = str(self.action_message.get("user_id", None))
                    self.user_nickname = self.action_message.get("user_nickname", None)

                if self.group_id:
                    self.is_group = True
                    self.target_id = self.group_id
                else:
                    self.is_group = False
                    self.target_id = self.user_id
            else:
                if self.chat_stream.group_info:
                    self.group_id = self.chat_stream.group_info.group_id
                    self.group_name = self.chat_stream.group_info.group_name
                    self.is_group = True
                    self.target_id = self.group_id
                else:
                    self.user_id = self.chat_stream.user_info.user_id
                    self.user_nickname = self.chat_stream.user_info.user_nickname
                    self.is_group = False
                    self.target_id = self.user_id

        logger.debug(f"{self.log_prefix} Action组件初始化完成")
        logger.debug(
            f"{self.log_prefix} 聊天信息: 类型={'群聊' if self.is_group else '私聊'}, 平台={self.platform}, 目标={self.target_id}"
        )

        # 验证聊天类型限制
        if not self._validate_chat_type():
            logger.warning(
                f"{self.log_prefix} Action '{self.action_name}' 不支持当前聊天类型: "
                f"{'群聊' if self.is_group else '私聊'}, 允许类型: {self.chat_type_allow.value}"
            )

    def _validate_chat_type(self) -> bool:
        """验证当前聊天类型是否允许执行此Action

        Returns:
            bool: 如果允许执行返回True，否则返回False
        """
        if self.chat_type_allow == ChatType.ALL:
            return True
        elif self.chat_type_allow == ChatType.GROUP and self.is_group:
            return True
        elif self.chat_type_allow == ChatType.PRIVATE and not self.is_group:
            return True
        else:
            return False

    def is_chat_type_allowed(self) -> bool:
        """检查当前聊天类型是否允许执行此Action

        这是一个公开的方法，供外部调用检查聊天类型限制

        Returns:
            bool: 如果允许执行返回True，否则返回False
        """
        return self._validate_chat_type()

    async def wait_for_new_message(self, timeout: int = 1200) -> tuple[bool, str]:
        """等待新消息或超时

        在loop_start_time之后等待新消息，如果没有新消息且没有超时，就一直等待。
        使用message_api检查self.chat_id对应的聊天中是否有新消息。

        Args:
            timeout: 超时时间（秒），默认1200秒

        Returns:
            Tuple[bool, str]: (是否收到新消息, 空字符串)
        """
        try:
            # 获取循环开始时间，如果没有则使用当前时间
            loop_start_time = self.action_data.get("loop_start_time", time.time())
            logger.info(f"{self.log_prefix} 开始等待新消息... (最长等待: {timeout}秒, 从时间点: {loop_start_time})")

            # 确保有有效的chat_id
            if not self.chat_id:
                logger.error(f"{self.log_prefix} 等待新消息失败: 没有有效的chat_id")
                return False, "没有有效的chat_id"

            wait_start_time = asyncio.get_event_loop().time()
            while True:
                # 检查关闭标志
                # shutting_down = self.get_action_context("shutting_down", False)
                # if shutting_down:
                # logger.info(f"{self.log_prefix} 等待新消息时检测到关闭信号，中断等待")
                # return False, ""

                # 检查新消息
                current_time = time.time()
                new_message_count = await message_api.count_new_messages(
                    chat_id=self.chat_id, start_time=loop_start_time, end_time=current_time
                )

                if new_message_count > 0:
                    logger.info(f"{self.log_prefix} 检测到{new_message_count}条新消息，聊天ID: {self.chat_id}")
                    return True, ""

                # 检查超时
                elapsed_time = asyncio.get_event_loop().time() - wait_start_time
                if elapsed_time > timeout:
                    logger.warning(f"{self.log_prefix} 等待新消息超时({timeout}秒)，聊天ID: {self.chat_id}")
                    return False, ""

                # 每30秒记录一次等待状态
                if int(elapsed_time) % 15 == 0 and int(elapsed_time) > 0:
                    logger.debug(f"{self.log_prefix} 已等待{int(elapsed_time)}秒，继续等待新消息...")

                # 短暂休眠
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} 等待新消息被中断 (CancelledError)")
            return False, ""
        except Exception as e:
            logger.error(f"{self.log_prefix} 等待新消息时发生错误: {e}")
            return False, f"等待新消息失败: {e!s}"

    async def send_text(self, content: str, reply_to: str = "", typing: bool = False) -> bool:
        """发送文本消息

        Args:
            content: 文本内容
            reply_to: 回复消息，格式为"发送者:消息内容"

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.text_to_stream(
            text=content,
            stream_id=self.chat_id,
            reply_to=reply_to,
            typing=typing,
        )

    async def send_emoji(self, emoji_base64: str) -> bool:
        """发送表情包

        Args:
            emoji_base64: 表情包的base64编码

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.emoji_to_stream(emoji_base64, self.chat_id)

    async def send_image(self, image_base64: str) -> bool:
        """发送图片

        Args:
            image_base64: 图片的base64编码

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.image_to_stream(image_base64, self.chat_id)

    async def send_custom(self, message_type: str, content: str, typing: bool = False, reply_to: str = "") -> bool:
        """发送自定义类型消息

        Args:
            message_type: 消息类型，如"video"、"file"、"audio"等
            content: 消息内容
            typing: 是否显示正在输入
            reply_to: 回复消息，格式为"发送者:消息内容"

        Returns:
            bool: 是否发送成功
        """
        if not self.chat_id:
            logger.error(f"{self.log_prefix} 缺少聊天ID")
            return False

        return await send_api.custom_to_stream(
            message_type=message_type,
            content=content,
            stream_id=self.chat_id,
            typing=typing,
            reply_to=reply_to,
        )

    async def store_action_info(
        self,
        action_build_into_prompt: bool = False,
        action_prompt_display: str = "",
        action_done: bool = True,
    ) -> None:
        """存储动作信息到数据库

        Args:
            action_build_into_prompt: 是否构建到提示中
            action_prompt_display: 显示的action提示信息
            action_done: action是否完成
        """
        await database_api.store_action_info(
            chat_stream=self.chat_stream,
            action_build_into_prompt=action_build_into_prompt,
            action_prompt_display=action_prompt_display,
            action_done=action_done,
            thinking_id=self.thinking_id,
            action_data=self.action_data,
            action_name=self.action_name,
        )

    async def send_command(
        self, command_name: str, args: dict | None = None, display_message: str = "", storage_message: bool = True
    ) -> bool:
        """发送命令消息

        使用stream API发送命令

        Args:
            command_name: 命令名称
            args: 命令参数
            display_message: 显示消息
            storage_message: 是否存储消息到数据库

        Returns:
            bool: 是否发送成功
        """
        try:
            if not self.chat_id:
                logger.error(f"{self.log_prefix} 缺少聊天ID")
                return False

            # 构造命令数据
            command_data = {"name": command_name, "args": args or {}}

            success = await send_api.command_to_stream(
                command=command_data,
                stream_id=self.chat_id,
                storage_message=storage_message,
                display_message=display_message,
            )

            if success:
                logger.info(f"{self.log_prefix} 成功发送命令: {command_name}")
            else:
                logger.error(f"{self.log_prefix} 发送命令失败: {command_name}")

            return success

        except Exception as e:
            logger.error(f"{self.log_prefix} 发送命令时出错: {e}")
            return False

    async def call_action(self, action_name: str, action_data: dict | None = None) -> tuple[bool, str]:
        """
        在当前Action中调用另一个Action。

        Args:
            action_name (str): 要调用的Action的名称。
            action_data (Optional[dict], optional): 传递给被调用Action的动作数据。如果为None，则使用当前Action的action_data。

        Returns:
            Tuple[bool, str]: 被调用Action的执行结果 (is_success, message)。
        """
        log_prefix = f"{self.log_prefix} [call_action -> {action_name}]"
        logger.info(f"{log_prefix} 尝试调用Action: {action_name}")

        try:
            # 1. 从注册中心获取Action类
            from src.plugin_system.core.component_registry import component_registry

            action_class = component_registry.get_component_class(action_name, ComponentType.ACTION)
            if not action_class:
                logger.error(f"{log_prefix} 未找到Action: {action_name}")
                return False, f"未找到Action: {action_name}"

            # 2. 准备实例化参数
            # 复用当前Action的大部分上下文信息
            called_action_data = action_data if action_data is not None else self.action_data

            component_info = component_registry.get_component_info(action_name, ComponentType.ACTION)
            if not component_info:
                logger.warning(f"{log_prefix} 未找到Action组件信息: {action_name}")
                return False, f"未找到Action组件信息: {action_name}"

            # 确保获取的是Action组件
            if component_info.component_type != ComponentType.ACTION:
                logger.error(
                    f"{log_prefix} 尝试调用的组件 '{action_name}' 不是一个Action，而是一个 '{component_info.component_type.value}'"
                )
                return False, f"组件 '{action_name}' 不是一个有效的Action"

            plugin_config = component_registry.get_plugin_config(component_info.plugin_name)
            # 3. 实例化被调用的Action
            action_params: ClassVar = {
                "action_data": called_action_data,
                "reasoning": f"Called by {self.action_name}",
                "cycle_timers": self.cycle_timers,
                "thinking_id": self.thinking_id,
                "chat_stream": self.chat_stream,
                "log_prefix": log_prefix,
                "plugin_config": plugin_config,
                "action_message": self.action_message,
            }
            action_instance = action_class(**action_params)

            # 4. 执行Action
            logger.debug(f"{log_prefix} 开始执行...")
            execute_result = await action_instance.execute()
            # 确保返回类型符合 (bool, str) 格式
            is_success = execute_result[0] if isinstance(execute_result, tuple) and len(execute_result) > 0 else False
            message = execute_result[1] if isinstance(execute_result, tuple) and len(execute_result) > 1 else ""
            result = (is_success, str(message))
            logger.info(f"{log_prefix} 执行完成，结果: {result}")
            return result

        except Exception as e:
            logger.error(f"{log_prefix} 调用时发生错误: {e}")
            return False, f"调用Action '{action_name}' 时发生错误: {e}"

    @classmethod
    def get_action_info(cls) -> "ActionInfo":
        """从类属性生成ActionInfo

        所有信息都从类属性中读取，确保一致性和完整性。
        Action类必须定义所有必要的类属性。

        Returns:
            ActionInfo: 生成的Action信息对象
        """

        # 从类属性读取名称，如果没有定义则使用类名自动生成
        name = getattr(cls, "action_name", cls.__name__.lower().replace("action", ""))
        if "." in name:
            logger.error(f"Action名称 '{name}' 包含非法字符 '.'，请使用下划线替代")
            raise ValueError(f"Action名称 '{name}' 包含非法字符 '.'，请使用下划线替代")
        # 获取focus_activation_type和normal_activation_type
        focus_activation_type = getattr(cls, "focus_activation_type", ActionActivationType.ALWAYS)
        normal_activation_type = getattr(cls, "normal_activation_type", ActionActivationType.ALWAYS)

        # 处理activation_type：如果插件中声明了就用插件的值，否则默认使用focus_activation_type
        activation_type = getattr(cls, "activation_type", focus_activation_type)

        return ActionInfo(
            name=name,
            component_type=ComponentType.ACTION,
            description=getattr(cls, "action_description", "Action动作"),
            focus_activation_type=focus_activation_type,
            normal_activation_type=normal_activation_type,
            activation_type=activation_type,
            activation_keywords=getattr(cls, "activation_keywords", []).copy(),
            keyword_case_sensitive=getattr(cls, "keyword_case_sensitive", False),
            mode_enable=getattr(cls, "mode_enable", ChatMode.ALL),
            parallel_action=getattr(cls, "parallel_action", True),
            random_activation_probability=getattr(cls, "random_activation_probability", 0.0),
            llm_judge_prompt=getattr(cls, "llm_judge_prompt", ""),
            # 使用正确的字段名
            action_parameters=getattr(cls, "action_parameters", {}).copy(),
            action_require=getattr(cls, "action_require", []).copy(),
            associated_types=getattr(cls, "associated_types", []).copy(),
            chat_type_allow=getattr(cls, "chat_type_allow", ChatType.ALL),
            chatter_allow=getattr(cls, "chatter_allow", []).copy(),
            # 二步Action相关属性
            is_two_step_action=getattr(cls, "is_two_step_action", False),
            step_one_description=getattr(cls, "step_one_description", ""),
            sub_actions=getattr(cls, "sub_actions", []).copy(),
        )

    async def handle_step_one(self) -> tuple[bool, str]:
        """处理二步Action的第一步

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        if not self.is_two_step_action:
            return False, "此Action不是二步Action"

        # 检查action_data中是否包含选择的子Action
        selected_action = self.action_data.get("selected_action")
        if not selected_action:
            # 第一步：展示可用的子Action
            [sub_action[0] for sub_action in self.sub_actions]
            description = self.step_one_description or f"{self.action_name}支持以下操作"

            actions_list = "\n".join([f"- {action}: {desc}" for action, desc, _ in self.sub_actions])
            response = f"{description}\n\n可用操作：\n{actions_list}\n\n请选择要执行的操作。"

            return True, response
        else:
            # 验证选择的子Action是否有效
            valid_actions = [sub_action[0] for sub_action in self.sub_actions]
            if selected_action not in valid_actions:
                return False, f"无效的操作选择: {selected_action}。可用操作: {valid_actions}"

            # 保存选择的子Action
            self._selected_sub_action = selected_action

            # 调用第二步执行
            return await self.execute_step_two(selected_action)

    async def execute_step_two(self, sub_action_name: str) -> tuple[bool, str]:
        """执行二步Action的第二步

        Args:
            sub_action_name: 子Action名称

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        if not self.is_two_step_action:
            return False, "此Action不是二步Action"

        # 子类需要重写此方法来实现具体的第二步逻辑
        return False, f"二步Action必须实现execute_step_two方法来处理操作: {sub_action_name}"

    # =============================================================================
    # 新的激活机制 - go_activate 和工具函数
    # =============================================================================

    def _get_chat_content(self) -> str:
        """获取聊天内容用于激活判断

        从实例属性中获取聊天内容。子类可以重写此方法来自定义获取逻辑。

        Returns:
            str: 聊天内容
        """
        # 尝试从不同的实例属性中获取聊天内容
        # 优先级：_activation_chat_content > action_data['chat_content'] > ""

        # 1. 如果有专门设置的激活用聊天内容（由 ActionModifier 设置）
        if hasattr(self, "_activation_chat_content"):
            return getattr(self, "_activation_chat_content", "")

        # 2. 尝试从 action_data 中获取
        if hasattr(self, "action_data") and isinstance(self.action_data, dict):
            return self.action_data.get("chat_content", "")

        # 3. 默认返回空字符串
        return ""

    async def go_activate(
        self,
        llm_judge_model: "LLMRequest | None" = None,
    ) -> bool:
        """判断此 Action 是否应该被激活

        这是新的激活机制的核心方法。子类可以重写此方法来实现自定义的激活逻辑，
        也可以使用提供的工具函数来简化常见的激活判断。

        默认实现会检查类属性中的激活类型配置，提供向后兼容支持。

        聊天内容会自动从实例属性中获取，不需要手动传入。

        Args:
            llm_judge_model: LLM 判断模型，如果需要使用 LLM 判断

        Returns:
            bool: True 表示应该激活，False 表示不激活

        Example:
            >>> # 简单的关键词激活
            >>> async def go_activate(self, llm_judge_model=None) -> bool:
            >>>     return await self._keyword_match(["你好", "hello"])
            >>>
            >>> # LLM 判断激活
            >>> async def go_activate(self, llm_judge_model=None) -> bool:
            >>>     return await self._llm_judge_activation(
            >>>         "当用户询问天气信息时激活",
            >>>         llm_judge_model
            >>>     )
            >>>
            >>> # 组合多种条件
            >>> async def go_activate(self, llm_judge_model=None) -> bool:
            >>>     # 随机 30% 概率，或者匹配关键词
            >>>     if await self._random_activation(0.3):
            >>>         return True
            >>>     return await self._keyword_match(["天气"])
        """
        # 默认实现：向后兼容旧的激活类型系统
        activation_type = getattr(self, "activation_type", ActionActivationType.ALWAYS)

        if activation_type == ActionActivationType.ALWAYS:
            return True

        elif activation_type == ActionActivationType.NEVER:
            return False

        elif activation_type == ActionActivationType.RANDOM:
            probability = getattr(self, "random_activation_probability", 0.0)
            return await self._random_activation(probability)

        elif activation_type == ActionActivationType.KEYWORD:
            keywords = getattr(self, "activation_keywords", [])
            case_sensitive = getattr(self, "keyword_case_sensitive", False)
            return await self._keyword_match(keywords, case_sensitive)

        elif activation_type == ActionActivationType.LLM_JUDGE:
            prompt = getattr(self, "llm_judge_prompt", "")
            return await self._llm_judge_activation(
                judge_prompt=prompt,
                llm_judge_model=llm_judge_model,
            )

        # 未知类型，默认不激活
        logger.warning(f"{self.log_prefix} 未知的激活类型: {activation_type}")
        return False

    async def _random_activation(self, probability: float) -> bool:
        """随机激活工具函数

        Args:
            probability: 激活概率，范围 0.0 到 1.0

        Returns:
            bool: 是否激活
        """
        result = random.random() < probability
        logger.debug(f"{self.log_prefix} 随机激活判断: 概率={probability}, 结果={'激活' if result else '不激活'}")
        return result

    async def _keyword_match(
        self,
        keywords: list[str],
        case_sensitive: bool = False,
    ) -> bool:
        """关键词匹配工具函数

        聊天内容会自动从实例属性中获取。

        Args:
            keywords: 关键词列表
            case_sensitive: 是否区分大小写

        Returns:
            bool: 是否匹配到关键词
        """
        if not keywords:
            logger.warning(f"{self.log_prefix} 关键词列表为空，默认不激活")
            return False

        # 自动获取聊天内容
        chat_content = self._get_chat_content()

        search_text = chat_content
        if not case_sensitive:
            search_text = search_text.lower()

        matched_keywords  = []
        for keyword in keywords:
            check_keyword = keyword if case_sensitive else keyword.lower()
            if check_keyword in search_text:
                matched_keywords.append(keyword)

        if matched_keywords:
            logger.debug(f"{self.log_prefix} 匹配到关键词: {matched_keywords}")
            return True
        else:
            logger.debug(f"{self.log_prefix} 未匹配到任何关键词: {keywords}")
            return False

    async def _llm_judge_activation(
        self,
        judge_prompt: str = "",
        llm_judge_model: "LLMRequest | None" = None,
        action_description: str = "",
        action_require: list[str] | None = None,
    ) -> bool:
        """LLM 判断激活工具函数

        使用 LLM 来判断是否应该激活此 Action。
        会自动构建完整的判断提示词，只需要提供核心判断逻辑即可。

        聊天内容会自动从实例属性中获取。

        Args:
            judge_prompt: 自定义判断提示词（核心判断逻辑）
            llm_judge_model: LLM 判断模型实例，如果为 None 则会创建默认的小模型
            action_description: Action 描述，如果不提供则使用类属性
            action_require: Action 使用场景，如果不提供则使用类属性

        Returns:
            bool: 是否应该激活

        Example:
            >>> # 最简单的用法
            >>> result = await self._llm_judge_activation(
            >>>     "当用户询问天气信息时激活"
            >>> )
            >>>
            >>> # 提供详细信息
            >>> result = await self._llm_judge_activation(
            >>>     judge_prompt="当用户表达情绪或需要情感支持时激活",
            >>>     action_description="发送安慰表情包",
            >>>     action_require=["用户情绪低落", "需要情感支持"]
            >>> )
        """
        try:
            # 自动获取聊天内容
            chat_content = self._get_chat_content()

            # 如果没有提供 LLM 模型，创建一个默认的
            if llm_judge_model is None:
                from src.config.config import model_config
                from src.llm_models.utils_model import LLMRequest

                llm_judge_model = LLMRequest(
                    model_set=model_config.model_task_config.utils_small,
                    request_type="action.judge",
                )

            # 使用类属性作为默认值
            if not action_description:
                action_description = getattr(self, "action_description", "Action 动作")

            if action_require is None:
                action_require = getattr(self, "action_require", [])

            # 构建完整的判断提示词
            prompt = f"""你需要判断在当前聊天情况下，是否应该激活名为"{self.action_name}"的动作。

动作描述：{action_description}
"""

            if action_require:
                prompt += "\n动作使用场景：\n"
                for req in action_require:
                    prompt += f"- {req}\n"

            if judge_prompt:
                prompt += f"\n额外判定条件：\n{judge_prompt}\n"

            if chat_content:
                prompt += f"\n当前聊天记录：\n{chat_content}\n"

            prompt += """
请根据以上信息判断是否应该激活这个动作。
只需要回答"是"或"否"，不要有其他内容。
"""

            # 调用 LLM 进行判断，设置7秒超时避免长时间等待
            import asyncio
            response = ""  # 初始化response变量
            try:
                response, _ = await asyncio.wait_for(
                    llm_judge_model.generate_response_async(prompt=prompt),
                    timeout=7.0
                )
                response = response.strip().lower()
                should_activate = "是" in response or "yes" in response or "true" in response
            except asyncio.TimeoutError:
                logger.warning(f"{self.log_prefix} LLM 判断激活超时（7秒），默认激活以避免阻塞")
                # 超时时默认激活，交给后续决策系统处理
                should_activate = True

            logger.debug(
                f"{self.log_prefix} LLM 判断结果: 响应='{response}', 结果={'激活' if should_activate else '不激活'}"
            )
            return should_activate

        except Exception as e:
            logger.error(f"{self.log_prefix} LLM 判断激活时出错: {e}")
            # 出错时默认不激活
            return False

    @abstractmethod
    async def execute(self) -> tuple[bool, str]:
        """执行Action的抽象方法，子类必须实现

        对于二步Action，会自动处理第一步逻辑

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        # 如果是二步Action，自动处理第一步
        if self.is_two_step_action:
            return await self.handle_step_one()

        # 普通Action由子类实现
        pass

    async def handle_action(self) -> tuple[bool, str]:
        """兼容旧系统的handle_action接口，委托给execute方法

        为了保持向后兼容性，旧系统的代码可能会调用handle_action方法。
        此方法将调用委托给新的execute方法。

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        return await self.execute()

    def get_config(self, key: str, default=None):
        """获取插件配置值，使用嵌套键访问

        Args:
            key: 配置键名，使用嵌套访问如 "section.subsection.key"
            default: 默认值

        Returns:
            Any: 配置值或默认值
        """
        if not self.plugin_config:
            return default

        # 支持嵌套键访问
        keys = key.split(".")
        current = self.plugin_config

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default

        return current
