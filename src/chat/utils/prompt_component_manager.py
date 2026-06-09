from __future__ import annotations

import asyncio
import copy
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from src.chat.utils.prompt_params import PromptParameters
from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.plugin_system.base.base_prompt import BasePrompt
    from src.plugin_system.base.component_types import ComponentType, InjectionRule, InjectionType, PromptInfo
    from src.plugin_system.core.component_registry import component_registry

logger = get_logger("prompt_component_manager")


class PromptComponentManager:
    """
    一个统一的、动态的、可观测的提示词组件管理中心。

    该管理器是整个提示词动态注入系统的核心，它负责：
    1.  **规则加载**: 在系统启动时，自动扫描所有已注册的 `BasePrompt` 组件，
        并将其静态定义的 `injection_rules` 加载为默认的动态规则。
    2.  **动态管理**: 提供线程安全的 API，允许在运行时动态地添加、更新或移除注入规则，
        使得提示词的结构可以被实时调整。
    3.  **状态观测**: 提供丰富的查询 API，用于观测系统当前完整的注入状态，
        例如查询所有注入到特定目标的规则、或查询某个组件定义的所有规则。
    4.  **注入应用**: 在构建核心 Prompt 时，根据统一的、按优先级排序的规则集，
        动态地修改和装配提示词模板，实现灵活的提示词组合。
    """

    def __init__(self):
        """初始化管理器实例。"""
        # _dynamic_rules 存储通过 API 在运行时动态添加/修改的规则。
        # 这是实现提示词动态性的核心数据结构。
        # 结构: {
        #   "target_prompt_name": {  // 目标 Prompt 的名称
        #     "prompt_component_name": (InjectionRule, content_provider, source) // 注入组件的规则详情
        #   }
        # }
        self._dynamic_rules: dict[str, dict[str, tuple[InjectionRule, Callable[..., Awaitable[str]], str]]] = {}
        self._lock = asyncio.Lock()  # 使用异步锁确保对 _dynamic_rules 的并发访问安全。
        self._initialized = False  # 标记静态规则是否已加载，防止重复加载。

    # --- 核心生命周期与初始化 ---

    def load_static_rules(self):
        """..."""
        if self._initialized:
            return

        from src.plugin_system.base.base_prompt import BasePrompt  # noqa: F811 - 延迟导入打破循环依赖
        from src.plugin_system.base.component_types import ComponentType, PromptInfo  # noqa: F811
        from src.plugin_system.core.component_registry import component_registry  # noqa: F811

        logger.info("正在加载静态 Prompt 注入规则...")

        # 从组件注册表中获取所有已启用的 Prompt 组件
        enabled_prompts = component_registry.get_enabled_components_by_type(ComponentType.PROMPT)

        for prompt_name, prompt_info in enabled_prompts.items():
            if not isinstance(prompt_info, PromptInfo):
                continue

            component_class = component_registry.get_component_class(prompt_name, ComponentType.PROMPT)
            if not (component_class and issubclass(component_class, BasePrompt)):
                logger.warning(f"无法为 '{prompt_name}' 加载静态规则，因为它不是一个有效的 Prompt 组件。")
                continue

            def create_provider(
                cls: type[BasePrompt],
            ) -> Callable[[PromptParameters, str], Awaitable[str]]:
                """
                为静态组件创建一个内容提供者闭包 (Content Provider Closure)。

                这个闭包捕获了组件的类 `cls`，并返回一个标准的 `content_provider` 异步函数。
                当 `apply_injections` 需要内容时，它会调用这个函数。
                函数内部会实例化组件，并执行其 `execute` 方法来获取注入内容。

                Args:
                    cls (type[BasePrompt]): 需要为其创建提供者的 Prompt 组件类。

                Returns:
                    Callable[[PromptParameters, str], Awaitable[str]]: 一个符合管理器标准的异步内容提供者。
                """

                async def content_provider(params: PromptParameters, target_prompt_name: str) -> str:
                    """实际执行内容生成的异步函数。"""
                    try:
                        # 从注册表获取最新的组件信息，包括插件配置
                        p_info = component_registry.get_component_info(cls.prompt_name, ComponentType.PROMPT)
                        plugin_config = {}
                        if isinstance(p_info, PromptInfo):
                            plugin_config = component_registry.get_plugin_config(p_info.plugin_name)

                        # 实例化组件并执行，传入 target_prompt_name
                        instance = cls(params=params, plugin_config=plugin_config, target_prompt_name=target_prompt_name)
                        result = await instance.execute()
                        return str(result) if result is not None else ""
                    except Exception as e:
                        logger.error(f"执行静态规则提供者 '{cls.prompt_name}' 时出错: {e}")
                        return ""  # 出错时返回空字符串，避免影响主流程

                return content_provider

            # 为该组件的每条静态注入规则创建并注册一个动态规则
            for rule in prompt_info.injection_rules:
                provider = create_provider(component_class)
                target_rules = self._dynamic_rules.setdefault(rule.target_prompt, {})
                target_rules[prompt_name] = (rule, provider, "static_default")

        self._initialized = True
        logger.info(f"静态 Prompt 注入规则加载完成，共处理 {len(enabled_prompts)} 个组件。")

    # --- 运行时规则管理 API ---

    async def add_injection_rule(
        self,
        prompt_name: str,
        rules: list[InjectionRule],
        content_provider: Callable[..., Awaitable[str]],
        source: str = "runtime",
    ) -> bool:
        """
        动态添加或更新注入规则。

        此方法允许在系统运行时，由外部逻辑（如插件、命令）向管理器中添加新的注入行为。
        如果已存在同名组件针对同一目标的规则，此方法会覆盖旧规则。

        Args:
            prompt_name (str): 动态注入组件的唯一名称。
            rules (List[InjectionRule]): 描述注入行为的规则对象列表。
            content_provider (Callable[..., Awaitable[str]]):
                一个异步函数，用于在应用注入时动态生成内容。
                函数签名应为: `async def provider(params: "PromptParameters", target_prompt_name: str) -> str`
            source (str, optional): 规则的来源标识，默认为 "runtime"。

        Returns:
            bool: 如果成功添加或更新，则返回 True。
        """
        # 加锁以保证多协程环境下的数据一致性
        async with self._lock:
            # 遍历所有待添加的规则
            for rule in rules:
                # 使用 setdefault 确保目标 prompt 的规则字典存在
                target_rules = self._dynamic_rules.setdefault(rule.target_prompt, {})
                # 添加或覆盖指定组件的规则、内容提供者和来源
                target_rules[prompt_name] = (rule, content_provider, source)
                logger.info(f"成功添加/更新注入规则: '{prompt_name}' -> '{rule.target_prompt}' (来源: {source})")
        return True

    async def add_rule_for_component(self, prompt_name: str, rule: InjectionRule) -> bool:
        """
        为一个已存在的组件添加单条注入规则，自动复用其内容提供者和来源。

        此方法首先会查找指定 `prompt_name` 的组件当前是否已有注入规则。
        如果存在，则复用其 content_provider 和 source 为新的规则进行注册。
        这对于为一个组件动态添加多个注入目标非常有用，无需重复提供 provider 或 source。

        Args:
            prompt_name (str): 已存在的注入组件的名称。
            rule (InjectionRule): 要为该组件添加的新注入规则。

        Returns:
            bool: 如果成功添加规则，则返回 True；
                  如果未找到该组件的任何现有规则（无法复用），则返回 False。
        """
        async with self._lock:
            # 步骤 1: 遍历所有动态规则，查找指定组件已存在的 provider 和 source
            found_provider: Callable[..., Awaitable[str]] | None = None
            found_source: str | None = None
            for target_rules in self._dynamic_rules.values():
                if prompt_name in target_rules:
                    # 如果找到，记录其 provider 和 source 并跳出循环
                    _, found_provider, found_source = target_rules[prompt_name]
                    break

            # 步骤 2: 如果遍历完仍未找到 provider，说明该组件无任何规则，无法复用
            if not found_provider:
                logger.warning(
                    f"尝试为组件 '{prompt_name}' 添加规则失败: "
                    f"未找到该组件的任何现有规则，无法复用 content_provider 和 source。"
                )
                return False

            # 步骤 3: 使用找到的 provider 和 source 添加新规则
            source_to_use = found_source or "runtime"  # 如果 source 为 None，提供默认值
            target_rules = self._dynamic_rules.setdefault(rule.target_prompt, {})
            target_rules[prompt_name] = (rule, found_provider, source_to_use)
            logger.info(
                f"成功为组件 '{prompt_name}' 添加新注入规则 -> "
                f"'{rule.target_prompt}' (来源: {source_to_use})"
            )
            return True

    async def remove_injection_rule(self, prompt_name: str, target_prompt: str) -> bool:
        """
        移除一条动态注入规则。

        Args:
            prompt_name (str): 要移除的注入组件的名称。
            target_prompt (str): 该组件注入的目标核心提示词名称。

        Returns:
            bool: 如果成功移除，则返回 True；如果规则不存在，则返回 False。
        """
        async with self._lock:
            # 检查目标和组件规则是否存在
            if target_prompt in self._dynamic_rules and prompt_name in self._dynamic_rules[target_prompt]:
                # 存在则删除
                del self._dynamic_rules[target_prompt][prompt_name]
                # 如果删除后，该目标下已无任何规则，则清理掉这个目标键，保持数据结构整洁
                if not self._dynamic_rules[target_prompt]:
                    del self._dynamic_rules[target_prompt]
                logger.info(f"成功移除注入规则: '{prompt_name}' from '{target_prompt}'")
                return True
        # 如果规则不存在，记录警告并返回 False
        logger.warning(f"尝试移除注入规则失败: 未找到 '{prompt_name}' on '{target_prompt}'")
        return False

    async def remove_all_rules_by_component_name(self, prompt_name: str) -> bool:
        """
        按组件名称移除其所有相关的注入规则。

        此方法会遍历管理器中所有的目标提示词，并移除所有与给定的 `prompt_name`
        相关联的注入规则。这对于清理或禁用某个组件的所有注入行为非常有用。

        Args:
            prompt_name (str): 要移除规则的组件的名称。

        Returns:
            bool: 如果至少移除了一条规则，则返回 True；否则返回 False。
        """
        removed = False
        async with self._lock:
            # 创建一个目标列表的副本进行迭代，因为我们可能会在循环中修改字典
            for target_prompt in list(self._dynamic_rules.keys()):
                # 检查当前目标下是否存在该组件的规则
                if prompt_name in self._dynamic_rules[target_prompt]:
                    # 存在则删除
                    del self._dynamic_rules[target_prompt][prompt_name]
                    removed = True
                    logger.info(f"成功移除注入规则: '{prompt_name}' from '{target_prompt}'")
                    # 如果目标下已无任何规则，则清理掉这个键
                    if not self._dynamic_rules[target_prompt]:
                        del self._dynamic_rules[target_prompt]
                        logger.debug(f"目标 '{target_prompt}' 已空，已被移除。")

        if not removed:
            logger.warning(f"尝试移除组件 '{prompt_name}' 的所有规则失败: 未找到任何相关规则。")

        return removed

    # --- 核心注入逻辑 ---
    def _create_content_provider(
        self, component_name: str, component_class: type[BasePrompt]
    ) -> Callable[[PromptParameters, str], Awaitable[str]]:
        """为指定的组件类创建一个标准化的内容提供者闭包。"""

        async def content_provider(params: PromptParameters, target_prompt_name: str) -> str:
            """实际执行内容生成的异步函数。"""
            try:
                # 从注册表获取组件信息，用于后续获取插件配置
                p_info = component_registry.get_component_info(component_name, ComponentType.PROMPT)
                plugin_config = {}
                if isinstance(p_info, PromptInfo):
                    # 获取该组件所属插件的配置
                    plugin_config = component_registry.get_plugin_config(p_info.plugin_name)

                # 实例化组件，并传入所需参数
                instance = component_class(
                    params=params, plugin_config=plugin_config, target_prompt_name=target_prompt_name
                )
                # 执行组件的 execute 方法以生成内容
                result = await instance.execute()
                # 确保返回的是字符串
                return str(result) if result is not None else ""
            except Exception as e:
                # 捕获并记录执行过程中的任何异常，返回空字符串以避免注入失败
                logger.error(f"执行规则提供者 '{component_name}' 时出错: {e}", exc_info=True)
                return ""

        return content_provider

    async def _build_rules_for_target(self, target_prompt_name: str) -> list:
        """在注入时动态构建目标的所有有效规则列表。"""
        all_rules = []

        # 1. 从 component_registry 获取所有静态组件的规则
        static_components = component_registry.get_components_by_type(ComponentType.PROMPT)
        for name, info in static_components.items():
            if not isinstance(info, PromptInfo):
                continue

            # 实时检查组件是否已启用，跳过禁用的组件
            if not component_registry.is_component_available(name, ComponentType.PROMPT):
                continue

            # 获取组件的类定义
            component_class = component_registry.get_component_class(name, ComponentType.PROMPT)
            if not (component_class and issubclass(component_class, BasePrompt)):
                continue

            # 为该组件创建一个内容提供者
            provider = self._create_content_provider(name, component_class)
            # 遍历组件定义的所有注入规则
            for rule in info.injection_rules:
                # 如果规则的目标与当前目标匹配，则添加到列表中
                if rule.target_prompt == target_prompt_name:
                    all_rules.append((rule, provider, "static"))

        # 2. 从 _dynamic_rules 获取所有纯运行时规则
        async with self._lock:
            runtime_rules = self._dynamic_rules.get(target_prompt_name, {})
            for name, (rule, provider, source) in runtime_rules.items():
                # 检查该运行时规则是否关联到一个已注册的静态组件
                static_info = component_registry.get_component_info(name, ComponentType.PROMPT)
                # 如果关联的静态组件存在且被禁用，则跳过此运行时规则
                if static_info and not component_registry.is_component_available(name, ComponentType.PROMPT):
                    logger.debug(f"跳过运行时规则 '{name}'，因为它关联的静态组件当前已禁用。")
                    continue
                # 将有效的运行时规则添加到列表
                all_rules.append((rule, provider, source))

        return all_rules

    async def apply_injections(
        self, target_prompt_name: str, original_template: str, params: PromptParameters
    ) -> str:
        """
        【核心方法】根据目标名称，应用所有匹配的注入规则，返回修改后的模板。

        此方法实现了“意图识别与安全执行”机制，以确保注入操作的鲁棒性：
        1.  **占位符保护**: 首先，扫描模板中的所有 `"{...}"` 占位符，
            并用唯一的、无冲突的临时标记替换它们。这可以防止注入规则意外地修改或删除核心占位符。
        2.  **规则预检与警告**: 在应用规则前，检查所有 `REMOVE` 和 `REPLACE` 类型的规则，
            看它们的 `target_content` 是否可能匹配到被保护的占位符。如果可能，
            会记录一条明确的警告日志，告知开发者该规则有风险，但不会中断流程。
        3.  **安全执行**: 在“净化”过的模板上（即占位符已被替换的模板），
            按优先级顺序安全地应用所有注入规则。
        4.  **占位符恢复**: 所有注入操作完成后，将临时标记恢复为原始的占位符。

        Args:
            target_prompt_name (str): 目标核心提示词的名称。
            original_template (str): 未经修改的原始提示词模板。
            params (PromptParameters): 当前请求的参数，会传递给 `content_provider`。

        Returns:
            str: 应用了所有注入规则后，最终生成的提示词模板字符串。
        """
        # 构建适用于当前目标的所有规则
        rules_for_target = await self._build_rules_for_target(target_prompt_name)
        if not rules_for_target:
            # 如果没有规则，直接返回原始模板
            return original_template

        # --- 占位符保护机制 ---
        # 1. 保护: 找到所有 {placeholder} 并用临时标记替换
        placeholders = re.findall(r"({[^{}]+})", original_template)
        placeholder_map: dict[str, str] = {
            f"__PROMPT_PLACEHOLDER_{i}__": p for i, p in enumerate(placeholders)
        }

        protected_template = original_template
        for marker, placeholder in placeholder_map.items():
            protected_template = protected_template.replace(placeholder, marker)

        # 2. 预检与警告: 检查危险规则
        for rule, _, source in rules_for_target:
            if rule.injection_type in (InjectionType.REMOVE, InjectionType.REPLACE) and rule.target_content:
                try:
                    # 检查规则的 target_content (正则) 是否可能匹配到任何一个占位符
                    for p in placeholders:
                        if re.search(rule.target_content, p):
                            logger.warning(
                                f"注入规则警告 (来源: {source}): "
                                f"规则 `target_content` ('{rule.target_content}') "
                                f"可能会影响核心占位符 '{p}'。为保证系统稳定，该占位符已被保护，不会被此规则修改。"
                            )
                            # 每个规则只警告一次
                            break
                except re.error:
                    # 如果正则表达式本身有误，后续执行时会捕获，此处可忽略
                    pass

        # 3. 安全执行: 按优先级排序并应用规则
        rules_for_target.sort(key=lambda x: x[0].priority)

        modified_template = protected_template
        for rule, provider, source in rules_for_target:
            content = ""
            # REMOVE 类型不需要生成内容
            if rule.injection_type != InjectionType.REMOVE:
                try:
                    # 调用内容提供者生成要注入的文本
                    content = await provider(params, target_prompt_name)
                except Exception as e:
                    logger.error(f"执行规则 '{rule}' (来源: {source}) 的内容提供者时失败: {e}")
                    continue

            # 应用注入规则
            try:
                if rule.injection_type == InjectionType.PREPEND:
                    if content:
                        modified_template = f"{content}\n{modified_template}"
                elif rule.injection_type == InjectionType.APPEND:
                    if content:
                        modified_template = f"{modified_template}\n{content}"
                elif rule.injection_type == InjectionType.REPLACE:
                    if content is not None and rule.target_content:
                        modified_template = re.sub(rule.target_content, str(content), modified_template)
                elif rule.injection_type == InjectionType.INSERT_AFTER:
                    if content and rule.target_content:
                        # 使用 \\g<0> 在匹配项后插入内容
                        replacement = f"\\g<0>\n{content}"
                        modified_template = re.sub(rule.target_content, replacement, modified_template)
                elif rule.injection_type == InjectionType.REMOVE:
                    if rule.target_content:
                        modified_template = re.sub(rule.target_content, "", modified_template)
            except re.error as e:
                logger.error(f"应用规则时发生正则错误: {e} (pattern: '{rule.target_content}')")
            except Exception as e:
                logger.error(f"应用注入规则 '{rule}' (来源: {source}) 失败: {e}")

        # 4. 占位符恢复: 将临时标记替换回原始的占位符
        final_template = modified_template
        for marker, placeholder in placeholder_map.items():
            final_template = final_template.replace(marker, placeholder)

        return final_template

    async def preview_prompt_injections(
        self, target_prompt_name: str, params: PromptParameters
    ) -> str:
        """
        【预览功能】模拟应用所有注入规则，返回最终生成的模板字符串，而不实际修改任何状态。

        这个方法对于调试和测试非常有用，可以查看在特定参数下，
        一个核心提示词经过所有注入规则处理后会变成什么样子。

        Args:
            target_prompt_name (str): 希望预览的目标核心提示词名称。
            params (PromptParameters): 模拟的请求参数。

        Returns:
            str: 模拟生成的最终提示词模板字符串。如果找不到模板，则返回错误信息。
        """
        try:
            # 动态导入以避免循环依赖
            from src.chat.utils.prompt import global_prompt_manager
            # 从全局管理器获取原始的、未经修改的提示词对象
            original_prompt = global_prompt_manager._prompts.get(target_prompt_name)
            if not original_prompt:
                logger.warning(f"无法预览 '{target_prompt_name}'，因为找不到这个核心 Prompt。")
                return f"Error: Prompt '{target_prompt_name}' not found."
            original_template = original_prompt.template
        except KeyError:
            logger.warning(f"无法预览 '{target_prompt_name}'，因为找不到这个核心 Prompt。")
            return f"Error: Prompt '{target_prompt_name}' not found."

        # 直接调用核心注入逻辑来模拟并返回结果
        return await self.apply_injections(target_prompt_name, original_template, params)

    # --- 状态观测与查询 API ---

    def get_core_prompts(self) -> list[str]:
        """获取所有已注册的核心提示词模板名称列表（即所有可注入的目标）。"""
        # 动态导入以避免循环依赖
        from src.chat.utils.prompt import global_prompt_manager
        # 返回所有核心 prompt 的名称列表
        return list(global_prompt_manager._prompts.keys())

    def get_core_prompt_contents(self, prompt_name: str | None = None) -> list[list[str]]:
        """
        获取核心提示词模板的原始内容。

        Args:
            prompt_name (str | None, optional):
                如果指定，则只返回该名称对应的提示词模板。
                如果为 None，则返回所有核心提示词模板。
                默认为 None。

        Returns:
            list[list[str]]: 一个列表，每个子列表包含 [prompt_name, template_content]。
                             如果指定了 prompt_name 但未找到，则返回空列表。
        """
        from src.chat.utils.prompt import global_prompt_manager

        if prompt_name:
            # 如果指定了名称，则查找并返回单个模板
            prompt = global_prompt_manager._prompts.get(prompt_name)
            return [[prompt_name, prompt.template]] if prompt else []

        # 如果未指定名称，则返回所有模板的列表
        return [[name, prompt.template] for name, prompt in global_prompt_manager._prompts.items()]

    async def get_registered_prompt_component_info(self) -> list[PromptInfo]:
        """
        获取所有已注册和动态添加的Prompt组件信息，并反映当前的注入规则状态。
        此方法现在直接从 component_registry 获取静态组件信息，并合并纯运行时的组件信息。
        """
        # 从注册表获取所有已注册的静态 Prompt 组件信息
        all_components = component_registry.get_components_by_type(ComponentType.PROMPT)
        info_list = [info for info in all_components.values() if isinstance(info, PromptInfo)]

        # 检查并合并仅在运行时通过 API 添加的“纯动态”组件
        async with self._lock:
            runtime_component_names = set()
            # 收集所有动态规则中涉及的组件名称
            for rules in self._dynamic_rules.values():
                runtime_component_names.update(rules.keys())

            static_component_names = {info.name for info in info_list}
            # 找出那些只存在于动态规则中，但未在静态组件中注册的名称
            pure_dynamic_names = runtime_component_names - static_component_names

            for name in pure_dynamic_names:
                # 为这些“纯动态”组件创建一个临时的信息对象
                dynamic_info = PromptInfo(
                    name=name,
                    component_type=ComponentType.PROMPT,
                    description="Dynamically added runtime component",
                    plugin_name="runtime",
                    is_built_in=False,
                )
                # 从动态规则中收集并关联其所有注入规则
                for rules_in_target in self._dynamic_rules.values():
                    if name in rules_in_target:
                        rule, _, _ = rules_in_target[name]
                        dynamic_info.injection_rules.append(rule)
                info_list.append(dynamic_info)

        return info_list

    async def get_injection_info(
        self,
        target_prompt: str | None = None,
        detailed: bool = False,
    ) -> dict[str, list[dict]]:
        """
        获取注入信息的映射图，可按目标筛选，并可控制信息的详细程度。
        此方法现在动态构建信息，以反映当前启用的组件和规则。
        """
        info_map = {}
        all_core_prompts = self.get_core_prompts()
        # 确定要处理的目标：如果指定了有效的目标，则只处理它；否则处理所有核心 prompt
        targets_to_process = [target_prompt] if target_prompt and target_prompt in all_core_prompts else all_core_prompts

        for target in targets_to_process:
            # 动态构建该目标的所有有效规则
            rules_for_target = await self._build_rules_for_target(target)
            if not rules_for_target:
                info_map[target] = []
                continue

            info_list = []
            for rule, _, source in rules_for_target:
                # 从规则对象中获取其所属组件的名称
                prompt_name = rule.owner_component
                if detailed:
                    # 如果需要详细信息，则添加更多字段
                    info_list.append(
                        {
                            "name": prompt_name,
                            "priority": rule.priority,
                            "source": source,
                            "injection_type": rule.injection_type.value,
                            "target_content": rule.target_content,
                        }
                    )
                else:
                    # 否则只添加基本信息
                    info_list.append({"name": prompt_name, "priority": rule.priority, "source": source})

            # 按优先级对结果进行排序
            info_list.sort(key=lambda x: x["priority"])
            info_map[target] = info_list
        return info_map

    async def get_injection_rules(
        self,
        target_prompt: str | None = None,
        component_name: str | None = None,
    ) -> dict[str, dict[str, "InjectionRule"]]:
        """
        获取所有（包括静态和运行时）注入规则，可通过目标或组件名称进行筛选。

        - 不提供任何参数时，返回所有规则。
        - 提供 `target_prompt` 时，仅返回注入到该目标的规则。
        - 提供 `component_name` 时，仅返回由该组件定义的所有规则。
        - 同时提供 `target_prompt` 和 `component_name` 时，返回满足两个条件的规则。

        Args:
            target_prompt (str, optional): 按目标核心提示词名称筛选。
            component_name (str, optional): 按注入组件名称筛选。

        Returns:
            dict[str, dict[str, InjectionRule]]: 一个包含所有匹配规则的深拷贝字典。
            结构: { "target_prompt": { "component_name": InjectionRule } }
        """
        all_rules: dict[str, dict[str, InjectionRule]] = {}

        # 1. 收集所有静态组件的规则
        static_components = component_registry.get_components_by_type(ComponentType.PROMPT)
        for name, info in static_components.items():
            if not isinstance(info, PromptInfo):
                continue
            # 如果指定了 component_name 且不匹配，则跳过此组件
            if component_name and name != component_name:
                continue

            for rule in info.injection_rules:
                # 如果指定了 target_prompt 且不匹配，则跳过此规则
                if target_prompt and rule.target_prompt != target_prompt:
                    continue
                target_dict = all_rules.setdefault(rule.target_prompt, {})
                target_dict[name] = rule

        # 2. 收集并合并所有运行时规则
        async with self._lock:
            for target, rules_in_target in self._dynamic_rules.items():
                # 如果指定了 target_prompt 且不匹配，则跳过此目标下的所有规则
                if target_prompt and target != target_prompt:
                    continue

                for name, (rule, _, _) in rules_in_target.items():
                    # 如果指定了 component_name 且不匹配，则跳过此规则
                    if component_name and name != component_name:
                        continue
                    target_dict = all_rules.setdefault(target, {})
                    # 运行时规则会覆盖同名的静态规则
                    target_dict[name] = rule

        # 返回深拷贝以防止外部修改影响内部状态
        return copy.deepcopy(all_rules)


# 创建全局单例 (Singleton)
# 在整个应用程序中，应该只使用这一个 `prompt_component_manager` 实例，
# 以确保所有部分都共享和操作同一份动态规则集。
prompt_component_manager = PromptComponentManager()
