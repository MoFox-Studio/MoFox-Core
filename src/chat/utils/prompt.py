"""
统一提示词系统 - 合并模板管理和智能构建功能
将原有的Prompt类和SmartPrompt功能整合为一个真正的Prompt类
"""

import asyncio
import contextvars
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from rich.traceback import install

from src.chat.message_receive.chat_stream import get_chat_manager
from src.chat.utils.chat_message_builder import build_readable_messages
from src.chat.utils.prompt_component_manager import prompt_component_manager
from src.chat.utils.prompt_params import PromptParameters
from src.common.logger import get_logger
from src.config.config import global_config
from src.person_info.person_info import get_person_info_manager

install(extra_lines=3)
logger = get_logger("unified_prompt")


class PromptContext:
    """提示词上下文管理器.

    该类用于创建临时的、隔离的提示词作用域，尤其适用于异步环境中的并发消息处理。
    它使用`contextvars`来确保每个协程（例如，处理单个消息的协程）都拥有自己独立的
    提示词注册表，从而避免上下文混淆。
    """

    def __init__(self):
        """初始化上下文管理器."""
        # _context_prompts: 存储按上下文ID组织的提示词字典。
        # 格式: {"context_id_1": {"prompt_name_1": Prompt_obj_1}}
        self._context_prompts: dict[str, dict[str, "Prompt"]] = {}

        # _current_context_var: 使用contextvars来存储当前协程的上下文ID。
        # 这确保了在并发执行的异步任务中，每个任务都能访问到正确的上下文ID。
        self._current_context_var = contextvars.ContextVar(
            "current_context", default=None
        )

        # _context_lock: 一个异步锁，用于保护对共享资源_context_prompts的并发访问。
        self._context_lock = asyncio.Lock()

    @property
    def _current_context(self) -> str | None:
        """获取当前协程的上下文ID."""
        return self._current_context_var.get()

    @_current_context.setter
    def _current_context(self, value: str | None):
        """设置当前协程的上下文ID."""
        self._current_context_var.set(value)  # type: ignore

    @asynccontextmanager
    async def async_scope(self, context_id: str | None = None):
        """创建一个异步的临时提示模板作用域.

        在此作用域内注册或获取的提示词将是临时的，并且只对当前协程可见。
        这对于处理单个消息时需要临时修改或添加提示词的场景非常有用。

        Args:
            context_id (str | None): 上下文ID，通常是消息ID。如果为None，则不创建新的作用域。
        """
        if context_id is not None:
            # 尝试获取锁以安全地初始化上下文
            try:
                await asyncio.wait_for(self._context_lock.acquire(), timeout=5.0)
                try:
                    # 如果是新的上下文ID，为其创建一个空的提示词字典
                    if context_id not in self._context_prompts:
                        self._context_prompts[context_id] = {}
                finally:
                    # 确保锁总是被释放
                    self._context_lock.release()
            except asyncio.TimeoutError:
                # 如果获取锁超时，记录警告并放弃创建此作用域
                logger.warning(f"获取上下文锁超时，context_id: {context_id}")
                context_id = None

            # 设置当前协程的上下文ID
            previous_context = self._current_context
            token = self._current_context_var.set(context_id) if context_id else None  # type: ignore
        else:
            # 如果没有提供context_id，则不改变当前上下文
            previous_context = self._current_context
            token = None

        try:
            # 进入作用域
            yield self
        finally:
            # 退出作用域时，恢复之前的上下文
            if context_id is not None and token is not None:
                try:
                    self._current_context_var.reset(token)
                except Exception as e:
                    # 如果重置失败，尝试手动恢复，作为最后的保障
                    logger.warning(f"恢复上下文时出错: {e}")
                    try:
                        self._current_context = previous_context
                    except Exception:
                        ...

    async def get_prompt_async(self, name: str) -> Optional["Prompt"]:
        """异步、安全地获取当前作用域中的提示模板."""
        async with self._context_lock:
            current_context = self._current_context
            logger.debug(f"获取提示词: {name} 当前上下文: {current_context}")
            # 检查当前上下文是否存在，并且提示词是否已在该上下文中注册
            if (
                current_context
                and current_context in self._context_prompts
                and name in self._context_prompts[current_context]
            ):
                return self._context_prompts[current_context][name]
            return None

    async def register_async(
        self, prompt: "Prompt", context_id: str | None = None
    ) -> None:
        """异步、安全地将提示模板注册到指定的作用域.

        如果未指定context_id，则注册到当前协程的上下文中。
        """
        async with self._context_lock:
            # 确定目标上下文ID
            if target_context := context_id or self._current_context:
                if prompt.name:
                    # 使用setdefault确保目标上下文的字典存在，然后注册prompt
                    self._context_prompts.setdefault(target_context, {})[
                        prompt.name
                    ] = prompt


class PromptManager:
    """统一提示词管理器.

    作为全局单例（global_prompt_manager）存在，负责管理所有全局注册的提示词模板。
    它与PromptContext协作，实现了上下文优先的提示词检索策略，并支持动态的插件内容注入。
    """

    def __init__(self):
        """初始化管理器."""
        self._prompts = {}  # 全局提示词注册表
        self._counter = 0  # 用于为未命名提示词生成唯一名称
        self._context = PromptContext()  # 上下文管理器实例

    @asynccontextmanager
    async def async_message_scope(self, message_id: str | None = None):
        """为单个消息处理流程创建一个异步的临时提示词作用域.

        这是一个便捷的封装，直接使用了PromptContext的async_scope。

        Args:
            message_id (str | None): 消息ID，用作上下文ID。
        """
        async with self._context.async_scope(message_id):
            yield self

    async def get_prompt_async(
        self, name: str, parameters: PromptParameters | None = None
    ) -> "Prompt":
        """异步获取提示模板，并动态地将插件内容注入其中.

        获取提示词的优先级顺序为：
        1. 当前协程的上下文作用域 (通过 `_context.get_prompt_async`)
        2. 全局注册表

        核心功能是动态注入：在获取到原始模板后，它会检查是否有插件注册了
        针对此提示词（`injection_point`）的内容。如果有，它会创建一个新的、
        临时的、包含了注入内容的Prompt实例返回，而不会污染全局注册表。

        Args:
            name (str): 提示词的名称。
            parameters (PromptParameters | None): 用于插件内容注入的参数。

        Returns:
            Prompt: 最终的（可能已被注入内容的）Prompt实例。

        Raises:
            KeyError: 如果找不到指定名称的提示词。
        """
        original_prompt = None
        # 1. 优先从当前上下文获取
        context_prompt = await self._context.get_prompt_async(name)
        if context_prompt is not None:
            logger.debug(f"从上下文中获取提示词: {name} {context_prompt}")
            original_prompt = context_prompt
        # 2. 否则，从全局注册表获取
        elif name in self._prompts:
            original_prompt = self._prompts[name]
        else:
            raise KeyError(f"Prompt '{name}' not found")

        # --- 动态注入插件内容 ---
        if original_prompt.name:
            # 确保我们有有效的parameters实例用于注入逻辑
            params_for_injection = parameters or original_prompt.parameters

            # 应用所有匹配的注入规则，获取修改后的模板
            modified_template = await prompt_component_manager.apply_injections(
                target_prompt_name=original_prompt.name,
                original_template=original_prompt.template,
                params=params_for_injection,
            )

            # 如果模板被修改了，就创建一个新的临时Prompt实例
            if modified_template != original_prompt.template:
                logger.debug(f"为'{name}'应用了Prompt注入规则")
                # 创建一个新的临时Prompt实例，不进行注册
                temp_prompt = Prompt(
                    template=modified_template,
                    name=original_prompt.name,
                    parameters=original_prompt.parameters,
                    should_register=False,  # 确保不重新注册
                )
                return temp_prompt

        # 如果没有注入内容，返回原始的提示词实例
        return original_prompt

    def generate_name(self, template: str) -> str:
        """为未命名的prompt生成一个唯一的名称."""
        self._counter += 1
        return f"prompt_{self._counter}"

    def register(self, prompt: "Prompt") -> None:
        """在全局注册表中注册一个prompt.

        如果prompt没有名称，会自动为其生成一个。
        """
        if not prompt.name:
            prompt.name = self.generate_name(prompt.template)
        self._prompts[prompt.name] = prompt

    def add_prompt(self, name: str, fstr: str) -> "Prompt":
        """通过名称和模板字符串快速添加一个新的全局提示模板."""
        prompt = Prompt(fstr, name=name)
        if prompt.name:
            self._prompts[prompt.name] = prompt
        return prompt

    async def format_prompt(self, name: str, **kwargs) -> str:
        """格式化一个提示模板.

        这是格式化操作的主要入口。它会先通过`get_prompt_async`获取
        最新的、可能已被注入内容的模板，然后再执行格式化。
        """
        # 提取parameters参数，因为它需要被传递给get_prompt_async以进行正确的注入
        parameters = kwargs.get("parameters")
        prompt = await self.get_prompt_async(name, parameters=parameters)
        # 使用所有提供的关键字参数格式化最终的模板
        result = prompt.format(**kwargs)
        return result


# 全局单例
global_prompt_manager = PromptManager()


class Prompt:
    """统一提示词类 - 融合了模板管理和智能构建功能.

    这是系统的核心类。一个`Prompt`实例不仅是一个简单的字符串模板，更是一个
    能够根据复杂的`PromptParameters`动态、异步地构建自身完整内容的“构建器”。
    它负责调用各种子系统（如记忆、工具、知识库等）来收集上下文信息，
    并将这些信息整合到最终的提示词中。
    """

    # 使用临时标记来处理模板中的转义花括号 `\{` 和 `\}`
    # 这是为了防止它们在 `format` 方法中被错误地解释为占位符
    _TEMP_LEFT_BRACE = "__ESCAPED_LEFT_BRACE__"
    _TEMP_RIGHT_BRACE = "__ESCAPED_RIGHT_BRACE__"

    def __init__(
        self,
        template: str,
        name: str | None = None,
        parameters: PromptParameters | None = None,
        should_register: bool = True,
    ):
        """初始化一个统一提示词实例.

        Args:
            template (str): 提示词模板字符串，例如 "你好, {user_name}!"。
            name (str | None): 提示词的唯一名称，用于注册和检索。
            parameters (PromptParameters | None): 控制智能构建过程的参数对象。
            should_register (bool): 是否应将此实例自动注册到全局管理器。
                在创建临时或动态修改的Prompt时应设为False。
        """
        self.template = template
        self.name = name
        self.parameters = parameters or PromptParameters()
        self.args = self._parse_template_args(template)  # 解析模板中的占位符
        self._formatted_result = ""  # 存储最后一次格式化或构建的结果

        # 预处理模板，将转义的花括号替换为临时标记
        self._processed_template = self._process_escaped_braces(template)

        # 根据`should_register`标志和当前是否处于一个临时上下文中来决定是否进行全局注册
        # 如果在`async_scope`内，则不进行全局注册，由调用者决定是否进行上下文注册
        if should_register and not global_prompt_manager._context._current_context:
            global_prompt_manager.register(self)

    @staticmethod
    def _process_escaped_braces(template) -> str:
        r"""预处理模板，将 `\{` 和 `\}` 替换为临时标记."""
        if isinstance(template, list):
            template = "\n".join(str(item) for item in template)
        elif not isinstance(template, str):
            template = str(template)

        return template.replace("\\{", Prompt._TEMP_LEFT_BRACE).replace(
            "\\}", Prompt._TEMP_RIGHT_BRACE
        )

    @staticmethod
    def _restore_escaped_braces(template: str) -> str:
        """在格式化完成后，将临时标记还原为实际的花括号字符 `{` 和 `}`."""
        return template.replace(Prompt._TEMP_LEFT_BRACE, "{").replace(
            Prompt._TEMP_RIGHT_BRACE, "}"
        )

    def _parse_template_args(self, template: str) -> list[str]:
        """从模板字符串中解析出所有占位符（例如 "{user_name}" -> "user_name"）."""
        template_args = []
        # 在解析前先处理转义花括号，避免将它们误认为占位符
        processed_template = self._process_escaped_braces(template)
        # 使用正则表达式查找所有花括号内的内容
        result = re.findall(r"\{(.*?)\}", processed_template)
        for expr in result:
            # 提取变量名部分，忽略格式说明符（如 {elapsed_minutes:.1f} -> elapsed_minutes）
            arg_name = expr.split(":")[0].split("!")[0].strip()
            # 添加到列表中，并确保唯一性
            if arg_name and arg_name not in template_args:
                template_args.append(arg_name)
        return template_args

    async def build(self) -> str:
        """构建完整的、包含所有智能上下文的提示词.

        这是`Prompt`类最核心的方法。它 orchestrates 了整个构建流程：
        1. 验证传入的`PromptParameters`是否有效。
        2. 调用 `_build_context_data` 异步地、并行地收集所有需要的上下文信息。
        3. 使用收集到的上下文数据格式化主模板。
        4. 返回最终构建完成的提示词文本。

        Returns:
            str: 构建完成的、可以直接发送给LLM的提示词文本。

        Raises:
            ValueError: 如果参数验证失败。
            TimeoutError: 如果构建过程中的任何一步超时。
            RuntimeError: 如果发生其他构建错误。
        """
        # 步骤 0: 参数验证
        errors = self.parameters.validate()
        if errors:
            logger.error(f"参数验证失败: {', '.join(errors)}")
            raise ValueError(f"参数验证失败: {', '.join(errors)}")

        start_time = time.time()
        try:
            # 步骤 1: 构建核心的上下文数据字典
            context_data = await self._build_context_data()

            # 步骤 2: 使用构建好的上下文数据来格式化主模板
            main_formatted_prompt = await self._format_with_context(context_data)

            # 步骤 3: (已废弃) 注入插件内容的逻辑已前置到`PromptManager.get_prompt_async`中
            # 这样做可以更早地组合模板，也使得`Prompt`类的职责更单一。
            result = main_formatted_prompt

            total_time = time.time() - start_time
            logger.debug(
                f"Prompt构建完成，模式: {self.parameters.prompt_mode}, 耗时: {total_time:.2f}s"
            )

            # 缓存结果
            self._formatted_result = result
            return result

        except asyncio.TimeoutError as e:
            logger.error(f"构建Prompt超时: {e}")
            raise TimeoutError(f"构建Prompt超时: {e}") from e
        except Exception as e:
            logger.error(f"构建Prompt失败: {e}")
            raise RuntimeError(f"构建Prompt失败: {e}") from e

    async def _build_context_data(self) -> dict[str, Any]:
        """构建所有智能上下文数据.

        这是性能和复杂性的核心。它根据`PromptParameters`中的开关，
        动态地创建一系列异步构建任务，然后并行执行它们以最大限度地
        减少I/O等待时间。

        关键优化：
        - **并行执行**: 使用`asyncio.gather`（隐式地通过循环`await`）来同时运行多个数据获取任务。
        - **独立超时**: 为每个任务设置独立的、合理的超时时间，防止单个慢任务阻塞整个构建过程。
        - **预构建参数**: 允许外部系统（如消息处理器）预先构建某些耗时的数据（如记忆），
          并将其传入`PromptParameters`，从而完全跳过此处的实时构建。
        - **错误隔离**: 单个任务的失败或超时不会导致整个构建过程失败，而是会使用默认的空值替代，
          保证了系统的健壮性。

        Returns:
            dict[str, Any]: 一个包含所有构建好的上下文数据的字典。
        """
        start_time = time.time()

        # 初始化预构建参数字典
        pre_built_params = {}

        try:
            # --- 步骤 1: 准备构建任务 ---
            tasks = []
            task_names = []

            # --- 步骤 1.1: 优先使用预构建的参数 ---
            # 如果参数对象中已经包含了某些block，说明它们是外部预构建的，
            # 我们将它们存起来，并跳过对应的实时构建任务。
            if self.parameters.expression_habits_block:
                pre_built_params["expression_habits_block"] = (
                    self.parameters.expression_habits_block
                )
            if self.parameters.relation_info_block:
                pre_built_params["relation_info_block"] = (
                    self.parameters.relation_info_block
                )
            if self.parameters.memory_block:
                pre_built_params["memory_block"] = self.parameters.memory_block
                logger.debug("使用预构建的memory_block，跳过实时构建")
            if self.parameters.tool_info_block:
                pre_built_params["tool_info_block"] = self.parameters.tool_info_block
            if self.parameters.knowledge_prompt:
                pre_built_params["knowledge_prompt"] = self.parameters.knowledge_prompt
            if self.parameters.cross_context_block:
                pre_built_params["cross_context_block"] = (
                    self.parameters.cross_context_block
                )
            if self.parameters.notice_block:
                pre_built_params["notice_block"] = self.parameters.notice_block

            # --- 步骤 1.2: 根据参数和预构建情况，决定需要实时运行的任务 ---
            if self.parameters.enable_expression and not pre_built_params.get(
                "expression_habits_block"
            ):
                tasks.append(self._build_expression_habits())
                task_names.append("expression_habits")

            # 记忆块构建已移至 default_generator.py 的 build_memory_block 方法
            # 使用新的记忆图系统，不再在 prompt.py 中构建记忆
            # 如果需要记忆，必须通过 pre_built_params 传入

            if self.parameters.enable_relation and not pre_built_params.get(
                "relation_info_block"
            ):
                tasks.append(self._build_relation_info())
                task_names.append("relation_info")

            if self.parameters.enable_tool and not pre_built_params.get(
                "tool_info_block"
            ):
                tasks.append(self._build_tool_info())
                task_names.append("tool_info")

            if self.parameters.enable_knowledge and not pre_built_params.get(
                "knowledge_prompt"
            ):
                tasks.append(self._build_knowledge_info())
                task_names.append("knowledge_info")

            if self.parameters.enable_cross_context and not pre_built_params.get(
                "cross_context_block"
            ):
                tasks.append(self._build_cross_context())
                task_names.append("cross_context")

            # --- 步骤 2: 并行执行任务，并进行精细化的超时和错误处理 ---

            # 为不同类型的任务设置不同的超时时间，这是一个重要的性能优化。
            # I/O密集型或计算密集型任务（如记忆、工具）可以有更长的超时。
            task_timeouts = {
                "memory_block": 15.0,
                "tool_info": 15.0,
                "relation_info": 10.0,
                "knowledge_info": 10.0,
                "cross_context": 10.0,
                "expression_habits": 10.0,
            }

            # 使用 asyncio.gather 实现并发执行，提供更好的错误处理和性能
            results: list[Any] = [None] * len(tasks)  # 预分配结果列表，保持任务顺序
            tasks_to_run = []  # 存储带超时的任务
            task_info = []  # 存储任务信息，用于结果处理

            # 准备任务并创建带超时的协程
            for i, task in enumerate(tasks):
                task_name = task_names[i] if i < len(task_names) else f"task_{i}"
                task_timeout = task_timeouts.get(
                    task_name, 2.0
                )  # 未指定超时的任务默认为2秒

                # 检查任务是否为协程，非协程任务直接使用默认值
                if asyncio.iscoroutine(task):
                    # 创建带超时的任务
                    timeout_task = asyncio.wait_for(task, timeout=task_timeout)
                    tasks_to_run.append(timeout_task)
                    task_info.append({"index": i, "name": task_name, "timeout": task_timeout})
                else:
                    logger.warning(
                        f"任务{task_name}不是协程对象，类型: {type(task)}，跳过处理"
                    )
                    results[i] = self._get_default_result_for_task(task_name)  # type: ignore

            # 使用 gather 并发执行所有任务，return_exceptions=True 确保单个任务失败不影响其他任务
            if tasks_to_run:
                task_results = await asyncio.gather(*tasks_to_run, return_exceptions=True)

                # 处理任务结果
                for i, result in enumerate(task_results):
                    info = task_info[i]
                    task_index = info["index"]
                    task_name = info["name"]
                    task_timeout = info["timeout"]

                    if isinstance(result, asyncio.TimeoutError):
                        # 处理超时错误
                        logger.warning(
                            f"构建任务{task_name}超时 ({task_timeout}s)，使用默认值"
                        )
                        results[task_index] = self._get_default_result_for_task(task_name)
                    elif isinstance(result, Exception):
                        # 处理其他异常
                        logger.error(f"构建任务{task_name}失败: {result!s}")
                        results[task_index] = self._get_default_result_for_task(task_name)
                    else:
                        # 成功完成
                        results[task_index] = result
                        logger.debug(f"构建任务{task_name}完成 ({task_timeout}s)")

            # --- 步骤 3: 合并所有结果 ---
            context_data = {}
            # 合并实时构建的结果
            for i, result in enumerate(results):
                task_name = task_names[i] if i < len(task_names) else f"task_{i}"
                if isinstance(result, Exception):
                    logger.error(f"构建任务{task_name}失败: {result!s}")
                elif isinstance(result, dict):
                    context_data.update(result)

            # 合并预构建的参数，这会覆盖任何同名的实时构建结果
            context_data.update(
                {key: value for key, value in pre_built_params.items() if value}
            )

        except asyncio.TimeoutError:
            # 这是一个不太可能发生的、总体的构建超时，作为最后的保障
            logger.error("构建超时")
            context_data = {}
            # 即使总体超时，也要确保预构建的参数被包含在内
            for key, value in pre_built_params.items():
                if value:
                    context_data[key] = value

        # --- 步骤 4: 构建特定模式的上下文和补充基础信息 ---
        # 为 s4u 和 normal 模式构建聊天历史上下文
        if self.parameters.prompt_mode in ["s4u", "normal"]:
            await self._build_s4u_chat_context(context_data)

        # 补充所有模式都需要的基础信息
        context_data.update(
            {
                "keywords_reaction_prompt": self.parameters.keywords_reaction_prompt,
                "extra_info_block": self.parameters.extra_info_block,
                "time_block": self.parameters.time_block
                or f"当前时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
                "identity": self.parameters.identity_block,
                "schedule_block": self.parameters.schedule_block,
                "moderation_prompt": self.parameters.moderation_prompt_block,
                "reply_target_block": self.parameters.reply_target_block,
                "mood_state": self.parameters.mood_prompt,
                "action_descriptions": self.parameters.action_descriptions,
                "bot_name": self.parameters.bot_name,
                "bot_nickname": self.parameters.bot_nickname,
            }
        )

        total_time = time.time() - start_time
        logger.debug(f"上下文构建完成，总耗时: {total_time:.2f}s")

        return context_data

    async def _build_s4u_chat_context(self, context_data: dict[str, Any]) -> None:
        """为S4U（Scene for You）模式构建特殊的、包含已读和未读消息的聊天上下文."""
        if not self.parameters.message_list_before_now_long:
            return

        target_user_id = ""
        if self.parameters.target_user_info:
            target_user_id = self.parameters.target_user_info.get("user_id") or ""

        # 调用核心构建逻辑
        read_history_prompt, unread_history_prompt = (
            await self._build_s4u_chat_history_prompts(
                self.parameters.message_list_before_now_long,
                target_user_id,
                self.parameters.sender,
                self.parameters.chat_id,
            )
        )

        # 将构建好的prompt添加到上下文数据中
        context_data["read_history_prompt"] = read_history_prompt
        context_data["unread_history_prompt"] = unread_history_prompt

    async def _build_s4u_chat_history_prompts(
        self,
        message_list_before_now: list[dict[str, Any]],
        target_user_id: str,
        sender: str,
        chat_id: str,
    ) -> tuple[str, str]:
        """构建S4U风格的已读/未读历史消息prompt.

        这是一个代理方法，它动态导入并调用`default_generator`中的实际实现，
        以避免循环依赖问题。
        """
        try:
            # 动态导入以避免循环依赖: prompt -> replyer -> prompt
            from src.plugin_system.apis.generator_api import get_replyer

            # 获取一个临时的生成器实例来访问其方法
            temp_generator = await get_replyer(
                None, chat_id, request_type="prompt_building"
            )
            if temp_generator:
                # 调用实际的构建方法
                return await temp_generator.build_s4u_chat_history_prompts(
                    message_list_before_now, target_user_id, sender, chat_id
                )
            return "", ""
        except Exception as e:
            logger.error(f"构建S4U历史消息prompt失败: {e}")
            return "", ""

    async def _build_expression_habits(self) -> dict[str, Any]:
        """构建表达习惯（如表情、口癖）的上下文块."""
        assert global_config is not None
        # 检查当前聊天是否启用了表达习惯功能
        use_expression, _, _ = global_config.expression.get_expression_config_for_chat(
            self.parameters.chat_id
        )
        if not use_expression:
            return {"expression_habits_block": ""}

        try:
            # 动态导入以减少启动时的加载负担
            from src.chat.express.expression_selector import ExpressionSelector

            # 准备用于分析的近期聊天历史
            chat_history = ""
            if self.parameters.message_list_before_now_long:
                recent_messages = self.parameters.message_list_before_now_long[-10:]
                chat_history = await build_readable_messages(
                    recent_messages,
                    replace_bot_name=True,
                    timestamp_mode="normal",
                    truncate=True,
                )

            # 使用统一的表达方式选择入口（支持classic和exp_model模式）
            expression_selector = ExpressionSelector(self.parameters.chat_id)
            selected_expressions = (
                await expression_selector.select_suitable_expressions(
                    chat_id=self.parameters.chat_id,
                    chat_history=chat_history,
                    target_message=self.parameters.target,
                )
            )

            # 将选择的表达习惯格式化为提示词的一部分
            if selected_expressions:
                formatted_expressions = []
                for expr in selected_expressions:
                    if isinstance(expr, dict):
                        situation = expr.get("situation", "")
                        style = expr.get("style", "")
                        if situation and style:
                            formatted_expressions.append(f"- {situation}：{style}")

                if formatted_expressions:
                    style_habits_str = "\n".join(formatted_expressions)
                    expression_habits_block = f"你可以参考以下的语言习惯，当情景合适就使用，但不要生硬使用，以合理的方式结合到你的回复中：\n{style_habits_str}"
                else:
                    expression_habits_block = ""
            else:
                expression_habits_block = ""

            return {"expression_habits_block": expression_habits_block}

        except Exception as e:
            # 保证即使构建失败，也不会中断整个流程
            logger.error(f"构建表达习惯失败: {e}")
            return {"expression_habits_block": ""}

    async def _build_relation_info(self) -> dict[str, Any]:
        """构建与对话目标相关的关系信息."""
        try:
            # [重构] 直接从 PromptParameters 获取稳定的用户身份信息
            platform = self.parameters.platform
            user_id = self.parameters.user_id

            if not platform or not user_id:
                logger.warning("无法从参数中获取platform或user_id，跳过关系信息构建")
                return {"relation_info_block": ""}

            # 调用新的、基于ID的静态方法
            relation_info = await Prompt.build_relation_info_by_user_id(
                self.parameters.chat_id, platform, user_id
            )
            return {"relation_info_block": relation_info}
        except Exception as e:
            logger.error(f"构建关系信息失败: {e}")
            return {"relation_info_block": ""}

    async def _build_tool_info(self) -> dict[str, Any]:
        """构建工具调用结果的上下文块."""
        assert global_config is not None
        if not global_config.tool.enable_tool:
            return {"tool_info_block": ""}

        try:
            from src.plugin_system.core.tool_use import ToolExecutor

            # 准备用于工具选择的聊天历史
            chat_history = ""
            if self.parameters.message_list_before_now_long:
                recent_messages = self.parameters.message_list_before_now_long[-15:]
                chat_history = await build_readable_messages(
                    recent_messages,
                    replace_bot_name=True,
                    timestamp_mode="normal",
                    truncate=True,
                )

            # 决定是否调用工具并执行
            tool_executor = ToolExecutor(chat_id=self.parameters.chat_id)
            tool_results, _, _ = await tool_executor.execute_from_chat_message(
                sender=self.parameters.sender,
                target_message=self.parameters.target,
                chat_history=chat_history,
                return_details=False,
            )

            # 将工具结果格式化为提示词的一部分
            if tool_results:
                tool_info_parts = ["## 工具信息", "以下是你通过工具获取到的实时信息："]
                for tool_result in tool_results:
                    tool_name = tool_result.get("tool_name", "unknown")
                    content = tool_result.get("content", "")
                    result_type = tool_result.get("type", "tool_result")

                    tool_info_parts.append(f"- 【{tool_name}】{result_type}: {content}")

                tool_info_parts.append(
                    "以上是你获取到的实时信息，请在回复时参考这些信息。"
                )
                tool_info_block = "\n".join(tool_info_parts)
            else:
                tool_info_block = ""

            return {"tool_info_block": tool_info_block}

        except Exception as e:
            logger.error(f"构建工具信息失败: {e}")
            return {"tool_info_block": ""}

    async def _build_knowledge_info(self) -> dict[str, Any]:
        """构建从知识库检索到的相关信息的上下文块."""
        assert global_config is not None
        if not global_config.lpmm_knowledge.enable:
            return {"knowledge_prompt": ""}

        try:
            from src.chat.knowledge.knowledge_lib import qa_manager

            question = self.parameters.target or ""
            if not question or not qa_manager:
                return {"knowledge_prompt": ""}

            # 从知识库检索与当前消息相关的信息
            knowledge_results = await qa_manager.get_knowledge(question=question)

            # 将检索结果格式化为提示词
            if knowledge_results and knowledge_results.get("knowledge_items"):
                knowledge_parts = [
                    "## 知识库信息",
                    "以下是与你当前对话相关的知识信息：",
                ]

                for item in knowledge_results["knowledge_items"]:
                    content = item.get("content", "")
                    source = item.get("source", "")
                    relevance = item.get("relevance", 0.0)
                    if content:
                        # 过滤掉相关性低于阈值的知识
                        try:
                            relevance_float = float(relevance)
                            if (
                                relevance_float
                                < global_config.lpmm_knowledge.qa_paragraph_threshold
                            ):
                                continue
                            relevance_str = f"{relevance_float:.2f}"
                        except (ValueError, TypeError):
                            relevance_str = str(relevance)

                        if source:
                            knowledge_parts.append(
                                f"- [{relevance_str}] {content} (来源: {source})"
                            )
                        else:
                            knowledge_parts.append(f"- [{relevance_str}] {content}")

                # 如果有总结，也一并加入
                if global_config.lpmm_knowledge.enable_summary and knowledge_results.get("summary"):
                    knowledge_parts.append(
                        f"\n知识总结: {knowledge_results['summary']}"
                    )

                knowledge_prompt = "\n".join(knowledge_parts)
            else:
                knowledge_prompt = ""

            return {"knowledge_prompt": knowledge_prompt}

        except Exception as e:
            logger.error(f"构建知识信息失败: {e}")
            return {"knowledge_prompt": ""}

    async def _build_cross_context(self) -> dict[str, Any]:
        """构建跨群聊上下文信息."""
        try:
            # 调用静态方法来执行实际的构建逻辑
            cross_context = await Prompt.build_cross_context(
                self.parameters.chat_id,
                self.parameters.prompt_mode,
                self.parameters.target_user_info,
            )
            return {"cross_context_block": cross_context}
        except Exception as e:
            logger.error(f"构建跨群上下文失败: {e}")
            return {"cross_context_block": ""}

    async def _format_with_context(self, context_data: dict[str, Any]) -> str:
        """根据不同的提示词模式，准备最终的参数并格式化模板."""
        # 根据prompt_mode选择不同的参数准备策略
        if self.parameters.prompt_mode == "s4u":
            params = self._prepare_s4u_params(context_data)
        elif self.parameters.prompt_mode == "normal":
            params = self._prepare_normal_params(context_data)
        else:
            # 默认模式或其他未指定模式
            params = self._prepare_default_params(context_data)

        # 如果prompt有名称，则通过全局管理器格式化（这样可以应用注入逻辑），否则直接格式化
        return (
            await global_prompt_manager.format_prompt(self.name, **params)
            if self.name
            else self.format(**params)
        )

    def _prepare_s4u_params(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """为S4U（Scene for You）模式准备最终用于格式化的参数字典."""
        assert global_config is not None
        return {
            **context_data,
            "expression_habits_block": context_data.get("expression_habits_block", ""),
            "tool_info_block": context_data.get("tool_info_block", ""),
            "knowledge_prompt": context_data.get("knowledge_prompt", ""),
            "memory_block": context_data.get("memory_block", ""),
            "relation_info_block": context_data.get("relation_info_block", ""),
            "extra_info_block": self.parameters.extra_info_block
            or context_data.get("extra_info_block", ""),
            "cross_context_block": context_data.get("cross_context_block", ""),
            "notice_block": self.parameters.notice_block
            or context_data.get("notice_block", ""),
            "identity": self.parameters.identity_block
            or context_data.get("identity", ""),
            "action_descriptions": self.parameters.action_descriptions
            or context_data.get("action_descriptions", ""),
            "schedule_block": self.parameters.schedule_block
            or context_data.get("schedule_block", ""),
            "sender_name": self.parameters.sender or "未知用户",
            "mood_state": self.parameters.mood_prompt
            or context_data.get("mood_state", ""),
            "read_history_prompt": context_data.get("read_history_prompt", ""),
            "unread_history_prompt": context_data.get("unread_history_prompt", ""),
            "time_block": context_data.get("time_block", ""),
            "reply_target_block": context_data.get("reply_target_block", ""),
            "reply_style": global_config.personality.reply_style,
            "keywords_reaction_prompt": self.parameters.keywords_reaction_prompt
            or context_data.get("keywords_reaction_prompt", ""),
            "moderation_prompt": self.parameters.moderation_prompt_block
            or context_data.get("moderation_prompt", ""),
            "safety_guidelines_block": self.parameters.safety_guidelines_block
            or context_data.get("safety_guidelines_block", ""),
            "auth_role_prompt_block": self.parameters.auth_role_prompt_block
            or context_data.get("auth_role_prompt_block", ""),
            "chat_scene": self.parameters.chat_scene
            or "你正在一个QQ群里聊天，你需要理解整个群的聊天动态和话题走向，并做出自然的回应。",
            "group_chat_reminder_block": self.parameters.group_chat_reminder_block
            or context_data.get("group_chat_reminder_block", ""),
        }

    def _prepare_normal_params(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """为Normal模式准备最终用于格式化的参数字典."""
        assert global_config is not None
        return {
            **context_data,
            "expression_habits_block": context_data.get("expression_habits_block", ""),
            "tool_info_block": context_data.get("tool_info_block", ""),
            "knowledge_prompt": context_data.get("knowledge_prompt", ""),
            "memory_block": context_data.get("memory_block", ""),
            "relation_info_block": context_data.get("relation_info_block", ""),
            "extra_info_block": self.parameters.extra_info_block
            or context_data.get("extra_info_block", ""),
            "cross_context_block": context_data.get("cross_context_block", ""),
            "notice_block": self.parameters.notice_block
            or context_data.get("notice_block", ""),
            "identity": self.parameters.identity_block
            or context_data.get("identity", ""),
            "action_descriptions": self.parameters.action_descriptions
            or context_data.get("action_descriptions", ""),
            "schedule_block": self.parameters.schedule_block
            or context_data.get("schedule_block", ""),
            "time_block": context_data.get("time_block", ""),
            "chat_info": context_data.get("chat_info", ""),
            "reply_target_block": context_data.get("reply_target_block", ""),
            "reply_style": global_config.personality.reply_style,
            "mood_state": self.parameters.mood_prompt
            or context_data.get("mood_state", ""),
            "read_history_prompt": context_data.get("read_history_prompt", ""),
            "unread_history_prompt": context_data.get("unread_history_prompt", ""),
            "keywords_reaction_prompt": self.parameters.keywords_reaction_prompt
            or context_data.get("keywords_reaction_prompt", ""),
            "moderation_prompt": self.parameters.moderation_prompt_block
            or context_data.get("moderation_prompt", ""),
            "safety_guidelines_block": self.parameters.safety_guidelines_block
            or context_data.get("safety_guidelines_block", ""),
            "auth_role_prompt_block": self.parameters.auth_role_prompt_block
            or context_data.get("auth_role_prompt_block", ""),
            "chat_scene": self.parameters.chat_scene
            or "你正在一个QQ群里聊天，你需要理解整个群的聊天动态和话题走向，并做出自然的回应。",
            "bot_name": self.parameters.bot_name,
            "bot_nickname": self.parameters.bot_nickname,
            "group_chat_reminder_block": self.parameters.group_chat_reminder_block
            or context_data.get("group_chat_reminder_block", ""),
        }

    def _prepare_default_params(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """为默认模式（或其他未指定模式）准备最终用于格式化的参数字典."""
        assert global_config is not None
        return {
            "expression_habits_block": context_data.get("expression_habits_block", ""),
            "relation_info_block": context_data.get("relation_info_block", ""),
            "chat_target": "",
            "time_block": context_data.get("time_block", ""),
            "chat_info": context_data.get("chat_info", ""),
            "identity": self.parameters.identity_block
            or context_data.get("identity", ""),
            "schedule_block": self.parameters.schedule_block
            or context_data.get("schedule_block", ""),
            "chat_target_2": "",
            "reply_target_block": context_data.get("reply_target_block", ""),
            "raw_reply": self.parameters.target,
            "reason": "",
            "mood_state": self.parameters.mood_prompt
            or context_data.get("mood_state", ""),
            "reply_style": global_config.personality.reply_style,
            "keywords_reaction_prompt": self.parameters.keywords_reaction_prompt
            or context_data.get("keywords_reaction_prompt", ""),
            "moderation_prompt": self.parameters.moderation_prompt_block
            or context_data.get("moderation_prompt", ""),
            "safety_guidelines_block": self.parameters.safety_guidelines_block
            or context_data.get("safety_guidelines_block", ""),
            "auth_role_prompt_block": self.parameters.auth_role_prompt_block
            or context_data.get("auth_role_prompt_block", ""),
            "bot_name": self.parameters.bot_name,
            "bot_nickname": self.parameters.bot_nickname,
        }

    def format(self, *args, **kwargs) -> str:
        """使用给定的参数格式化模板.

        支持标准的`str.format()`语法，包括位置参数和关键字参数。
        同时处理了之前用临时标记替换的转义花括号。

        Args:
            *args: 用于格式化的位置参数。
            **kwargs: 用于格式化的关键字参数。

        Returns:
            str: 格式化后的字符串。

        Raises:
            ValueError: 如果提供的参数与模板中的占位符不匹配。
        """
        try:
            # 优先使用位置参数进行格式化
            if args:
                formatted_args = {}
                for i, arg in enumerate(args):
                    if i < len(self.args):
                        formatted_args[self.args[i]] = arg
                processed_template = self._processed_template.format(**formatted_args)
            else:
                processed_template = self._processed_template

            # 然后使用关键字参数对结果进行再次格式化
            if kwargs:
                # 过滤掉模板中不存在的关键字参数，并转义字符串值中的花括号
                safe_kwargs = {}
                for k, v in kwargs.items():
                    if k in self.args:
                        if isinstance(v, str):
                            # 转义花括号，防止被 format 误认为嵌套占位符
                            safe_kwargs[k] = v.replace("{", "{{").replace("}", "}}")
                        else:
                            safe_kwargs[k] = v
                processed_template = processed_template.format(**safe_kwargs)

            # 最后，将转义花括号的临时标记还原
            result = self._restore_escaped_braces(processed_template)
            return result
        except (IndexError, KeyError) as e:
            # 捕获格式化错误并抛出更具信息量的异常
            raise ValueError(
                f"格式化模板失败: {self.template}, args={args}, kwargs={kwargs} {e!s}"
            ) from e

    def __str__(self) -> str:
        """返回格式化后的结果，如果还未格式化，则返回原始模板."""
        return self._formatted_result if self._formatted_result else self.template

    def __repr__(self) -> str:
        """返回一个清晰的、可用于调试的Prompt对象表示形式."""
        return f"Prompt(template='{self.template}', name='{self.name}')"

    # =============================================================================
    # PromptUtils功能迁移 - 静态工具方法
    #
    # 这些方法原本位于一个单独的`PromptUtils`类中，为了解决循环导入问题，
    # 它们被迁移到`Prompt`类下作为静态方法。
    # 这样，任何需要这些工具函数的地方都可以直接通过`Prompt.method_name`调用，
    # 而无需导入另一个可能导致循环依赖的模块。
    # =============================================================================

    @staticmethod
    def parse_reply_target(target_message: str) -> tuple[str, str]:
        """解析“回复”类型的消息，分离出发送者和消息内容.

        Args:
            target_message: 目标消息字符串，通常格式为 "发送者:消息内容" 或 "发送者：消息内容"。

        Returns:
            tuple[str, str]: 一个包含(发送者名称, 消息内容)的元组。
        """
        sender = ""
        target = ""

        # 添加None检查，增强健壮性
        if target_message is None:
            return sender, target

        # 兼容中文和英文冒号作为分隔符
        if ":" in target_message or "：" in target_message:
            parts = re.split(pattern=r"[:：]", string=target_message, maxsplit=1)
            if len(parts) == 2:
                sender = parts[0].strip()
                target = parts[1].strip()
        return sender, target

    @staticmethod
    async def build_relation_info_by_user_id(chat_id: str, platform: str, user_id: str) -> str:
        """
        [新] 根据用户ID构建关系信息字符串。
        """
        from src.person_info.relationship_fetcher import relationship_fetcher_manager

        person_info_manager = get_person_info_manager()
        person_id = person_info_manager.get_person_id(platform, user_id)

        if not person_id:
            logger.warning(f"构建关系信息时未找到用户 platform={platform}, user_id={user_id}")
            return f"你似乎还不认识这位用户（ID: {user_id}），这是你们的第一次互动。"

        relationship_fetcher = relationship_fetcher_manager.get_fetcher(chat_id)

        # 并行构建用户信息和聊天流印象
        user_relation_info_task = relationship_fetcher.build_relation_info(person_id, points_num=5)
        stream_impression_task = relationship_fetcher.build_chat_stream_impression(chat_id)

        user_relation_info, stream_impression = await asyncio.gather(
            user_relation_info_task, stream_impression_task
        )

        info_parts = []
        if user_relation_info:
            info_parts.append(user_relation_info)
        if stream_impression:
            info_parts.append(stream_impression)

        return "\n\n".join(info_parts) if info_parts else ""

    def _get_default_result_for_task(self, task_name: str) -> dict[str, Any]:
        """为超时或失败的异步构建任务提供一个安全的默认返回值.

        这确保了单个子任务的失败不会导致整个提示词构建过程的崩溃。

        Args:
            task_name: 失败的任务的名称。

        Returns:
            dict: 一个包含空字符串值的字典，其键与任务的预期输出相匹配。
        """
        defaults = {
            "memory_block": {"memory_block": ""},
            "tool_info": {"tool_info_block": ""},
            "relation_info": {"relation_info_block": ""},
            "knowledge_info": {"knowledge_prompt": ""},
            "cross_context": {"cross_context_block": ""},
            "expression_habits": {"expression_habits_block": ""},
        }

        if task_name in defaults:
            logger.info(f"为超时/失败的任务 {task_name} 提供默认值")
            return defaults[task_name]
        else:
            logger.warning(f"未知任务类型 {task_name}，返回空结果")
            return {}

    @staticmethod
    async def build_cross_context(
        chat_id: str, prompt_mode: str, target_user_info: dict[str, Any] | None
    ) -> str:
        """构建跨群聊的上下文信息.

        Args:
            chat_id: 当前聊天的ID。
            prompt_mode: 当前的提示词模式。
            target_user_info: 目标用户的信息字典。

        Returns:
            str: 构建好的跨群聊上下文字符串。
        """
        assert global_config is not None
        if not global_config.cross_context.enable:
            return ""

        # 动态导入以避免循环依赖
        from src.plugin_system.apis import cross_context_api

        chat_stream = await get_chat_manager().get_stream(chat_id)
        if not chat_stream:
            return ""

        # 目前只为s4u模式构建跨群上下文
        if prompt_mode == "s4u":
            return await cross_context_api.build_cross_context_s4u(
                chat_stream, target_user_info
            )

        return ""

    # [废弃] 该函数完全依赖于不稳定的名称解析，应被移除
    # @staticmethod
    # async def parse_reply_target_id(reply_to: str) -> str:
    #     """从回复目标字符串中解析出原始发送者的用户ID."""
    #     if not reply_to:
    #         return ""
    #     sender, _ = Prompt.parse_reply_target(reply_to)
    #     if not sender:
    #         return ""
    #     person_info_manager = get_person_info_manager()
    #     # [脆弱点] 使用了不稳健的按名称查询
    #     person_id = await person_info_manager.get_person_id_by_name_robust(sender)
    #     if person_id:
    #         user_id = await person_info_manager.get_value(person_id, "user_id")
    #         return str(user_id) if user_id else ""
    #     return ""


# 工厂函数
def create_prompt(
    template: str,
    name: str | None = None,
    parameters: PromptParameters | None = None,
    **kwargs,
) -> Prompt:
    """一个用于快速创建`Prompt`实例的工厂函数.

    它会自动处理`PromptParameters`的创建。

    Args:
        template (str): 提示词模板。
        name (str | None): 提示词名称。
        parameters (PromptParameters | None): 预先创建的参数对象。
        **kwargs: 如果未提供`parameters`，这些关键字参数将被用于创建一个新的`PromptParameters`实例。

    Returns:
        Prompt: 新创建的Prompt实例。
    """
    if parameters is None:
        parameters = PromptParameters(**kwargs)
    return Prompt(template, name, parameters)


async def create_prompt_async(
    template: str,
    name: str | None = None,
    parameters: PromptParameters | None = None,
    **kwargs,
) -> Prompt:
    """异步创建`Prompt`实例，并自动处理插件内容的动态注入.

    这是推荐的创建prompt的方式，因为它整合了注入逻辑。

    Args:
        template (str): 基础提示词模板。
        name (str | None): 提示词名称，用于查找要注入的组件。
        parameters (PromptParameters | None): 预先创建的参数对象。
        **kwargs: 如果未提供`parameters`，这些关键字参数将被用于创建一个新的`PromptParameters`实例。

    Returns:
        Prompt: 一个可能包含了注入内容的、新创建的Prompt实例。
    """
    # 确保我们有一个有效的参数实例
    final_params = parameters or PromptParameters(**kwargs)

    # 如果提供了名称，就尝试为它注入插件内容
    if name:
        modified_template = await prompt_component_manager.apply_injections(
            target_prompt_name=name, original_template=template, params=final_params
        )
        if modified_template != template:
            logger.debug(f"为'{name}'应用了Prompt注入规则")
            template = modified_template

    # 使用可能已被修改的模板来创建最终的Prompt实例
    prompt = create_prompt(template, name, final_params)

    # 如果当前处于一个临时上下文中，则将这个新创建的prompt异步注册到该上下文中
    if global_prompt_manager._context._current_context:
        await global_prompt_manager._context.register_async(prompt)

    return prompt
