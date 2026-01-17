"""
@desc: 该模块封装了与大语言模型（LLM）交互的所有核心逻辑。
它被设计为一个高度容错和可扩展的系统，包含以下主要组件：

- **模型选择器 (_ModelSelector)**:
  实现了基于负载均衡和失败惩罚的动态模型选择策略，确保在高并发或部分模型失效时系统的稳定性。

- **提示处理器 (_PromptProcessor)**:
  负责对输入模型的提示词进行预处理（如内容混淆、反截断指令注入）和对模型输出进行后处理（如提取思考过程、检查截断）。

- **请求执行器 (_RequestExecutor)**:
  封装了底层的API请求逻辑，包括自动重试、异常分类处理和消息体压缩等功能。

- **请求策略 (_RequestStrategy)**:
  实现了高阶请求策略，如模型间的故障转移（Failover），确保单个模型的失败不会导致整个请求失败。

- **LLMRequest (主接口)**:
  作为模块的统一入口（Facade），为上层业务逻辑提供了简洁的接口来发起文本、图像、语音等不同类型的LLM请求。
"""

import asyncio
import random
import re
import string
import time
from collections import namedtuple
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, ClassVar, Literal

import numpy as np
from rich.traceback import install

from src.common.logger import get_logger
from src.config.api_ada_configs import APIProvider, ModelInfo, TaskConfig
from src.config.config import model_config

from .exceptions import NetworkConnectionError, ReqAbortException, RespNotOkException, RespParseException
from .model_client.base_client import APIResponse, BaseClient, UsageRecord, client_registry
from .payload_content.message import Message, MessageBuilder, RoleType
from .payload_content.system_prompt import SYSTEM_PROMPT
from .payload_content.tool_option import ToolCall, ToolOption, ToolOptionBuilder
from .utils import compress_messages, llm_usage_recorder

install(extra_lines=3)

logger = get_logger("model_utils")

# ==============================================================================
# Standalone Utility Functions
# ==============================================================================


async def _normalize_image_format(image_format: str) -> str:
    """
    标准化图片格式名称，确保与各种API的兼容性

    Args:
        image_format (str): 原始图片格式

    Returns:
        str: 标准化后的图片格式
    """
    format_mapping = {
        "jpg": "jpeg",
        "JPG": "jpeg",
        "JPEG": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "PNG": "png",
        "webp": "webp",
        "WEBP": "webp",
        "gif": "gif",
        "GIF": "gif",
        "heic": "heic",
        "HEIC": "heic",
        "heif": "heif",
        "HEIF": "heif",
    }
    normalized = format_mapping.get(image_format, image_format.lower())
    logger.debug(f"图片格式标准化: {image_format} -> {normalized}")
    return normalized


async def execute_concurrently(
    coro_callable: Callable[..., Coroutine[Any, Any, Any]],
    concurrency_count: int,
    *args,
    **kwargs,
) -> Any:
    """
    执行并发请求并从成功的结果中随机选择一个。

    Args:
        coro_callable (Callable): 要并发执行的协程函数。
        concurrency_count (int): 并发执行的次数。
        *args: 传递给协程函数的位置参数。
        **kwargs: 传递给协程函数的关键字参数。

    Returns:
        Any: 其中一个成功执行的结果。

    Raises:
        RuntimeError: 如果所有并发请求都失败。
    """
    logger.info(f"启用并发请求模式，并发数: {concurrency_count}")
    tasks = [coro_callable(*args, **kwargs) for _ in range(concurrency_count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful_results = [res for res in results if not isinstance(res, Exception)]

    if successful_results:
        selected = random.choice(successful_results)
        logger.info(f"并发请求完成，从{len(successful_results)}个成功结果中选择了一个")
        return selected

    # 如果所有请求都失败了，记录所有异常并抛出第一个
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(f"并发任务 {i + 1}/{concurrency_count} 失败: {res}")

    first_exception = next((res for res in results if isinstance(res, Exception)), None)
    if first_exception:
        raise first_exception
    raise RuntimeError(f"所有 {concurrency_count} 个并发请求都失败了，但没有具体的异常信息")


class RequestType(Enum):
    """请求类型枚举"""

    RESPONSE = "response"
    EMBEDDING = "embedding"
    AUDIO = "audio"


# ==============================================================================
# Helper Classes for LLMRequest Refactoring
# ==============================================================================

# 定义用于跟踪模型使用情况的具名元组
ModelUsageStats = namedtuple(  # noqa: PYI024
    "ModelUsageStats", ["total_tokens", "penalty", "usage_penalty", "avg_latency", "request_count"]
)


class _ModelSelector:
    """负责模型选择、负载均衡和动态故障切换的策略。"""

    def __init__(self, model_list: list[str], model_usage: dict[str, ModelUsageStats]):
        """
        初始化模型选择器。

        Args:
            model_list (List[str]): 可用模型名称列表。
            model_usage (Dict[str, ModelUsageStats]): 模型的初始使用情况。
        """
        self.model_list = model_list
        self.model_usage = model_usage

        # 从配置文件加载倍率参数
        selector_config = model_config.model_selector
        self.CRITICAL_PENALTY_MULTIPLIER = selector_config.critical_penalty_multiplier if selector_config else 5.0
        self.DEFAULT_PENALTY_INCREMENT = selector_config.default_penalty_increment if selector_config else 1.0
        self.LATENCY_WEIGHT = selector_config.latency_weight if selector_config else 200.0
        self.PENALTY_WEIGHT = selector_config.penalty_weight if selector_config else 300.0
        self.USAGE_PENALTY_WEIGHT = selector_config.usage_penalty_weight if selector_config else 1000.0

    async def select_best_available_model(
        self, failed_models_in_this_request: set, request_type: str
    ) -> tuple[ModelInfo, APIProvider, BaseClient] | None:
        """
        从可用模型中选择负载均衡评分最低的模型，并排除当前请求中已失败的模型。

        Args:
            failed_models_in_this_request (set): 当前请求中已失败的模型名称集合。
            request_type (str): 请求类型，用于确定是否强制创建新客户端。

        Returns:
            Optional[Tuple[ModelInfo, APIProvider, BaseClient]]: 选定的模型详细信息，如果无可用模型则返回 None。
        """
        candidate_models_usage = {
            model_name: usage_data
            for model_name, usage_data in self.model_usage.items()
            if model_name not in failed_models_in_this_request
        }

        if not candidate_models_usage:
            logger.warning("没有可用的模型供当前请求选择。")
            return None

        # 核心负载均衡算法：选择一个综合得分最低的模型。
        # 公式: total_tokens + penalty * PENALTY_WEIGHT + usage_penalty * USAGE_PENALTY_WEIGHT + avg_latency * LATENCY_WEIGHT
        # 设计思路:
        # - `total_tokens`: 基础成本，优先使用累计token少的模型，实现长期均衡。
        # - `penalty * PENALTY_WEIGHT`: 失败惩罚项。每次失败会增加penalty，使其在短期内被选中的概率降低。
        # - `usage_penalty * USAGE_PENALTY_WEIGHT`: 短期使用惩罚项。每次被选中后会增加，完成后会减少。高权重确保在多个模型都健康的情况下，请求会均匀分布（轮询）。
        # - `avg_latency * LATENCY_WEIGHT`: 延迟惩罚项。优先选择平均响应时间更快的模型。
        least_used_model_name = min(
            candidate_models_usage,
            key=lambda k: candidate_models_usage[k].total_tokens
            + candidate_models_usage[k].penalty * self.PENALTY_WEIGHT
            + candidate_models_usage[k].usage_penalty * self.USAGE_PENALTY_WEIGHT
            + candidate_models_usage[k].avg_latency * self.LATENCY_WEIGHT,
        )

        assert model_config is not None, "model_config 不能为 None"
        model_info = model_config.get_model_info(least_used_model_name)
        api_provider = model_config.get_provider(model_info.api_provider)
        # 自动事件循环检测：ClientRegistry 会自动检测事件循环变化并处理缓存失效
        # 无需手动指定 force_new，embedding 请求也能享受缓存优势
        client = client_registry.get_client_class_instance(api_provider)

        logger.debug(f"为当前请求选择了最佳可用模型: {model_info.name}")
        # 增加所选模型的请求使用惩罚值，以实现动态负载均衡。
        await self.update_usage_penalty(model_info.name, increase=True)
        return model_info, api_provider, client

    async def update_usage_penalty(self, model_name: str, increase: bool):
        """
        更新模型的使用惩罚值。

        在模型被选中时增加惩罚值，请求完成后减少惩罚值。
        这有助于在短期内将请求分散到不同的模型，实现更动态的负载均衡。

        Args:
            model_name (str): 要更新惩罚值的模型名称。
            increase (bool): True表示增加惩罚值，False表示减少。
        """
        # 获取当前模型的统计数据
        stats = self.model_usage[model_name]
        # 根据操作是增加还是减少来确定调整量
        adjustment = 1 if increase else -1
        # 更新模型的惩罚值
        self.model_usage[model_name] = stats._replace(usage_penalty=stats.usage_penalty + adjustment)

    async def update_failure_penalty(self, model_name: str, e: Exception):
        """
        根据异常类型动态调整模型的失败惩罚值。
        关键错误（如网络连接、服务器错误）会获得更高的惩罚，
        促使负载均衡算法在下次选择时优先规避这些不可靠的模型。
        """
        stats = self.model_usage[model_name]
        penalty_increment = self.DEFAULT_PENALTY_INCREMENT

        # 对严重错误施加更高的惩罚，以便快速将问题模型移出候选池
        if isinstance(e, NetworkConnectionError | ReqAbortException):
            # 网络连接错误或请求被中断，通常是基础设施问题，应重罚
            penalty_increment = self.CRITICAL_PENALTY_MULTIPLIER
            logger.warning(
                f"模型 '{model_name}' 发生严重错误 ({type(e).__name__})，增加高额惩罚值: {penalty_increment}"
            )
        elif isinstance(e, RespNotOkException):
            # 对于HTTP响应错误，重点关注服务器端错误
            if e.status_code >= 500:
                # 5xx 错误表明服务器端出现问题，应重罚
                penalty_increment = self.CRITICAL_PENALTY_MULTIPLIER
                logger.warning(
                    f"模型 '{model_name}' 发生服务器错误 (状态码: {e.status_code})，增加高额惩罚值: {penalty_increment}"
                )
            else:
                # 4xx 客户端错误通常不代表模型本身不可用，给予基础惩罚
                logger.warning(
                    f"模型 '{model_name}' 发生客户端响应错误 (状态码: {e.status_code})，增加基础惩罚值: {penalty_increment}"
                )
        else:
            # 其他未知异常，给予基础惩罚
            import traceback
            logger.warning(
                f"模型 '{model_name}' 发生未知异常: {type(e).__name__}，增加基础惩罚值: {penalty_increment}\n"
                f"异常详情: {e!s}\n"
                f"异常堆栈:\n{traceback.format_exc()}"
            )

        self.model_usage[model_name] = stats._replace(penalty=stats.penalty + penalty_increment)


class _PromptProcessor:
    """封装所有与提示词和响应内容的预处理和后处理逻辑。"""

    def __init__(self):
        """
        初始化提示处理器。
        这里定义了用于内容混淆和反截断的指令文本。
        """
        # 内容混淆过滤指令: 用于在API传输中增加噪音，防止内容被审查或修改
        self.noise_instruction = """**【核心过滤规则】**
在交互过程中,你会在用户的输入内容中看到一些无意义的、由字母和数字组成的随机字符串。这些字符串是API传输过程中的技术伪装信息,【不是】用户真实意图的一部分。

你的任务是【完全并彻底地忽略】这些随机字符串。
**【严禁】** 将这些字符串写入你的回复、对它们进行任何形式的解读、或将它们作为故事的一部分进行模拟。当看到这些字符串时,请将其视为空白或直接跳过,并根据用户其他有意义的输入(如有)或当前故事情节来继续你的叙事。此规则为最高优先级。
"""
        # 反截断指令
        self.end_marker = "###MAI_RESPONSE_END###"
        self.anti_truncation_instruction = f"""
**【输出完成信令】**
这是一个非常重要的指令,请务必遵守。在你的回复内容完全结束后,请务必在最后另起一行,只写 `{self.end_marker}` 作为结束标志。
例如:
<你的回复内容>
{self.end_marker}

这有助于我判断你的输出是否被截断。请不要在 `{self.end_marker}` 前后添加任何其他文字或标点。
"""

    # ==============================================================================
    # 提示词扰动 (Prompt Perturbation) 模块
    #
    # 本模块通过引入一系列轻量级的、保持语义的随机化技术，
    # 旨在增加输入提示词的结构多样性。这有助于：
    # 1. 避免因短时间内发送高度相似的提示词而导致模型产生趋同或重复的回复。
    # 2. 增强模型对不同输入格式的鲁棒性。
    # 3. 在某些情况下，通过引入“噪音”来激发模型更具创造性的响应。
    # ==============================================================================

    # 定义语义等价的文本替换模板。
    # Key 是原始文本，Value 是一个包含多种等价表达的列表。
    SEMANTIC_VARIANTS: ClassVar = {
        "当前时间": ["当前时间", "现在是", "此时此刻", "时间"],
        "最近的系统通知": ["最近的系统通知", "系统通知", "通知消息", "最新通知"],
        "聊天历史": ["聊天历史", "对话记录", "历史消息", "之前的对话"],
        "你的任务是": ["你的任务是", "请", "你需要", "你应当"],
        "请注意": ["请注意", "注意", "请留意", "需要注意"],
    }

    async def _apply_prompt_perturbation(
        self,
        prompt_text: str,
        enable_semantic_variants: bool,
        strength: Literal["light", "medium", "heavy"],
    ) -> str:
        """
        统一的提示词扰动处理函数。

        该方法按顺序应用三种扰动技术：
        1. 语义变体 (Semantic Variants): 将特定短语替换为语义等价的其它表达。
        2. 空白噪声 (Whitespace Noise): 随机调整换行、空格和缩进。
        3. 内容混淆 (Content Confusion): 注入随机的、无意义的字符串。

        Args:
            prompt_text (str): 原始的用户提示词。
            enable_semantic_variants (bool): 是否启用语义变体替换。
            strength (Literal["light", "medium", "heavy"]): 扰动的强度，会影响所有扰动操作的程度。

        Returns:
            str: 经过扰动处理后的提示词。
        """
        try:
            perturbed_text = prompt_text

            # 步骤 1: 应用语义变体
            if enable_semantic_variants:
                perturbed_text = self._apply_semantic_variants(perturbed_text)

            # 步骤 2: 注入空白噪声
            perturbed_text = self._inject_whitespace_noise(perturbed_text, strength)

            # 步骤 3: 注入内容混淆（随机噪声字符串）
            perturbed_text = self._inject_random_noise(perturbed_text, strength)

            # 计算并记录变化率，用于调试和监控
            change_rate = self._calculate_change_rate(prompt_text, perturbed_text)
            if change_rate > 0.001:  # 仅在有实际变化时记录日志
                logger.debug(f"提示词扰动完成，强度: '{strength}'，变化率: {change_rate:.2%}")

            return perturbed_text

        except Exception as e:
            logger.error(f"提示词扰动处理失败: {e}")
            return prompt_text  # 发生异常时返回原始文本，保证流程不中断

    @staticmethod
    def _apply_semantic_variants(text: str) -> str:
        """
        应用语义等价的文本替换。

        遍历 SEMANTIC_VARIANTS 字典，对文本中首次出现的 key 进行随机替换。

        Args:
            text (str): 输入文本。

        Returns:
            str: 替换后的文本。
        """
        try:
            result = text
            for original, variants in _PromptProcessor.SEMANTIC_VARIANTS.items():
                if original in result:
                    # 从变体列表中随机选择一个进行替换
                    replacement = random.choice(variants)
                    # 只替换第一次出现的地方，避免过度修改
                    result = result.replace(original, replacement, 1)
            return result
        except Exception as e:
            logger.error(f"语义变体替换失败: {e}")
            return text

    @staticmethod
    def _inject_whitespace_noise(text: str, strength: str) -> str:
        """
        注入轻量级噪声（空白字符调整）。

        根据指定的强度，调整文本中的换行、行尾空格和列表项缩进。

        Args:
            text (str): 输入文本。
            strength (str): 噪声强度 ('light', 'medium', 'heavy')。

        Returns:
            str: 调整空白字符后的文本。
        """
        try:
            # 噪声强度配置，定义了不同强度下各种操作的参数范围
            noise_config = {
                "light": {"newline_range": (1, 2), "space_range": (0, 2), "indent_adjust": False, "probability": 0.3},
                "medium": {"newline_range": (1, 3), "space_range": (0, 4), "indent_adjust": True, "probability": 0.5},
                "heavy": {"newline_range": (1, 4), "space_range": (0, 6), "indent_adjust": True, "probability": 0.7},
            }
            config = noise_config.get(strength, noise_config["light"])

            lines = text.split("\n")
            result_lines = []
            for line in lines:
                processed_line = line
                # 随机调整行尾空格
                if line.strip() and random.random() < config["probability"]:
                    spaces = " " * random.randint(*config["space_range"])
                    processed_line += spaces

                # 随机调整列表项缩进（仅在中等和重度模式下）
                if config["indent_adjust"]:
                    list_match = re.match(r"^(\s*)([-*•])\s", processed_line)
                    if list_match and random.random() < 0.5:
                        indent, marker = list_match.group(1), list_match.group(2)
                        adjust = random.choice([-2, 0, 2])
                        new_indent = " " * max(0, len(indent) + adjust)
                        processed_line = processed_line.replace(indent + marker, new_indent + marker, 1)

                result_lines.append(processed_line)

            result = "\n".join(result_lines)

            # 调整连续换行的数量
            newline_pattern = r"\n{2,}"
            def replace_newlines(match):
                count = random.randint(*config["newline_range"])
                return "\n" * count
            result = re.sub(newline_pattern, replace_newlines, result)

            return result
        except Exception as e:
            logger.error(f"空白字符噪声注入失败: {e}")
            return text

    @staticmethod
    def _inject_random_noise(text: str, strength: str) -> str:
        """
        在文本中按指定强度注入随机噪音字符串（内容混淆）。

        Args:
            text (str): 输入文本。
            strength (str): 噪音强度 ('light', 'medium', 'heavy')。

        Returns:
            str: 注入随机噪音后的文本。
        """
        try:
            # 不同强度下的噪音注入参数配置
            # probability: 在每个单词后注入噪音的百分比概率
            # length: 注入噪音字符串的随机长度范围
            strength_config = {
                "light": {"probability": 15, "length": (3, 6)},
                "medium": {"probability": 25, "length": (5, 10)},
                "heavy": {"probability": 35, "length": (8, 15)},
            }
            config = strength_config.get(strength, strength_config["light"])

            words = text.split()
            if not words:
                return text

            result = []
            for word in words:
                result.append(word)
                # 根据概率决定是否在此单词后注入噪音
                if random.randint(1, 100) <= config["probability"]:
                    noise_length = random.randint(*config["length"])
                    # 定义噪音字符集
                    chars = string.ascii_letters + string.digits
                    noise = "".join(random.choice(chars) for _ in range(noise_length))
                    result.append(f" {noise} ") # 添加前后空格以分隔

            return "".join(result)
        except Exception as e:
            logger.error(f"随机噪音注入失败: {e}")
            return text

    @staticmethod
    def _calculate_change_rate(original: str, modified: str) -> float:
        """计算文本变化率，用于衡量扰动程度。"""
        if not original or not modified:
            return 0.0
        # 使用 Levenshtein 距离等更复杂的算法可能更精确，但为了性能，这里使用简单的字符差异计算
        diff_chars = sum(1 for a, b in zip(original, modified) if a != b) + abs(len(original) - len(modified))
        max_len = max(len(original), len(modified))
        return diff_chars / max_len if max_len > 0 else 0.0


    async def prepare_prompt(
        self, prompt: str, model_info: ModelInfo,  task_name: str
    ) -> str:
        """
        为请求准备最终的提示词,应用各种扰动和指令。
        """
        final_prompt_parts = []
        user_prompt = prompt

        # 步骤 A: 添加抗审查指令
        if model_info.enable_prompt_perturbation:
            final_prompt_parts.append(self.noise_instruction)

        # 步骤 B: (可选) 应用统一的提示词扰动
        if getattr(model_info, "enable_prompt_perturbation", False):
            logger.info(f"为模型 '{model_info.name}' 启用提示词扰动功能。")
            user_prompt = await self._apply_prompt_perturbation(
                prompt_text=user_prompt,
                enable_semantic_variants=getattr(model_info, "enable_semantic_variants", False),
                strength=getattr(model_info, "perturbation_strength", "light"),
            )

        final_prompt_parts.append(user_prompt)

        # 步骤 C: (可选) 添加反截断指令
        if model_info.anti_truncation:
            final_prompt_parts.append(self.anti_truncation_instruction)
            logger.info(f"模型 '{model_info.name}' (任务: '{task_name}') 已启用反截断功能。")

        return "\n\n".join(final_prompt_parts)

    async def process_response(self, content: str, use_anti_truncation: bool) -> tuple[str, str, bool]:
        """
        处理响应内容，提取思维链并检查截断。

        Returns:
            Tuple[str, str, bool]: (处理后的内容, 思维链内容, 是否被截断)
        """
        content, reasoning = await self._extract_reasoning(content)
        is_truncated = False
        if use_anti_truncation:
            if content.endswith(self.end_marker):
                content = content[: -len(self.end_marker)].strip()
            else:
                is_truncated = True
        return content, reasoning, is_truncated

    @staticmethod
    async def _extract_reasoning(content: str) -> tuple[str, str]:
        """
        从模型返回的完整内容中提取被<think>...</think>标签包裹的思考过程，
        并返回清理后的内容和思考过程。

        Args:
            content (str): 模型返回的原始字符串。

        Returns:
            Tuple[str, str]:
                - 清理后的内容（移除了<think>标签及其内容）。
                - 提取出的思考过程文本（如果没有则为空字符串）。
        """
        # 使用正则表达式精确查找 <think>...</think> 标签及其内容
        think_pattern = re.compile(r"<think>(.*?)</think>\s*", re.DOTALL)
        match = think_pattern.search(content)

        if match:
            # 提取思考过程
            reasoning = match.group(1).strip()
            # 从原始内容中移除匹配到的整个部分（包括标签和后面的空白）
            clean_content = think_pattern.sub("", content, count=1).strip()
        else:
            reasoning = ""
            clean_content = content.strip()

        return clean_content, reasoning


class _RequestExecutor:
    """负责执行实际的API请求，包含重试逻辑和底层异常处理。"""

    def __init__(self, model_selector: _ModelSelector, task_name: str):
        """
        初始化请求执行器。

        Args:
            model_selector (_ModelSelector): 模型选择器实例，用于在请求失败时更新惩罚。
            task_name (str): 当前任务的名称，用于日志记录。
        """
        self.model_selector = model_selector
        self.task_name = task_name

    async def execute_request(
        self,
        api_provider: APIProvider,
        client: BaseClient,
        request_type: RequestType,
        model_info: ModelInfo,
        **kwargs,
    ) -> APIResponse:
        """
        实际执行请求的方法，包含了重试和异常处理逻辑。

        Args:
            api_provider (APIProvider): API提供商配置。
            client (BaseClient): 用于发送请求的客户端实例。
            request_type (RequestType): 请求的类型 (e.g., RESPONSE, EMBEDDING)。
            model_info (ModelInfo): 正在使用的模型的信息。
            **kwargs: 传递给客户端方法的具体参数。

        Returns:
            APIResponse: 来自API的成功响应。

        Raises:
            Exception: 如果重试后请求仍然失败，则抛出最终的异常。
            RuntimeError: 如果达到最大重试次数。
        """
        retry_remain = api_provider.max_retry
        compressed_messages: list[Message] | None = None

        while retry_remain > 0:
            try:
                # 优先使用压缩后的消息列表
                message_list = kwargs.get("message_list")
                current_messages = compressed_messages or message_list

                # 根据请求类型调用不同的客户端方法
                if request_type == RequestType.RESPONSE:
                    assert current_messages is not None, "message_list cannot be None for response requests"

                    # 修复: 防止 'message_list' 在 kwargs 中重复传递
                    request_params = kwargs.copy()
                    request_params.pop("message_list", None)

                    return await client.get_response(
                        model_info=model_info, message_list=current_messages, **request_params
                    )
                elif request_type == RequestType.EMBEDDING:
                    return await client.get_embedding(model_info=model_info, **kwargs)
                elif request_type == RequestType.AUDIO:
                    return await client.get_audio_transcriptions(model_info=model_info, **kwargs)

            except Exception as e:
                logger.debug(f"请求失败: {e!s}")
                # 记录失败并更新模型的惩罚值
                await self.model_selector.update_failure_penalty(model_info.name, e)

                # 处理异常，决定是否重试以及等待多久
                wait_interval, new_compressed_messages = await self._handle_exception(
                    e,
                    model_info,
                    api_provider,
                    retry_remain,
                    (kwargs.get("message_list"), compressed_messages is not None),
                )
                if new_compressed_messages:
                    compressed_messages = new_compressed_messages  # 更新为压缩后的消息

                if wait_interval == -1:
                    raise e  # 如果决定不再重试，则传播异常
                elif wait_interval > 0:
                    await asyncio.sleep(wait_interval)  # 等待指定时间后重试
            finally:
                retry_remain -= 1

        logger.error(f"模型 '{model_info.name}' 请求失败，达到最大重试次数 {api_provider.max_retry} 次")
        raise RuntimeError("请求失败，已达到最大重试次数")

    async def _handle_exception(
        self, e: Exception, model_info: ModelInfo, api_provider: APIProvider, remain_try: int, messages_info
    ) -> tuple[int, list[Message] | None]:
        """
        默认异常处理函数，决定是否重试。

        Returns:
            (等待间隔（-1表示不再重试）, 新的消息列表（适用于压缩消息）)
        """
        model_name = model_info.name
        retry_interval = api_provider.retry_interval

        if isinstance(e, NetworkConnectionError | ReqAbortException):
            return await self._check_retry(remain_try, retry_interval, "连接异常", model_name)
        elif isinstance(e, RespNotOkException):
            return await self._handle_resp_not_ok(e, model_info, api_provider, remain_try, messages_info)
        elif isinstance(e, RespParseException):
            logger.error(f"任务-'{self.task_name}' 模型-'{model_name}': 响应解析错误 - {e.message}")
            return -1, None
        else:
            import traceback
            logger.error(
                f"任务-'{self.task_name}' 模型-'{model_name}': 未知异常 - {e!s}\n"
                f"异常类型: {type(e).__name__}\n"
                f"异常堆栈:\n{traceback.format_exc()}"
            )
            return -1, None

    async def _handle_resp_not_ok(
        self, e: RespNotOkException, model_info: ModelInfo, api_provider: APIProvider, remain_try: int, messages_info
    ) -> tuple[int, list[Message] | None]:
        """
        处理非200的HTTP响应异常。

        根据不同的HTTP状态码决定下一步操作：
        - 4xx 客户端错误：通常不可重试，直接放弃。
        - 413 (Payload Too Large): 尝试压缩消息体后重试一次。
        - 429 (Too Many Requests) / 5xx 服务器错误：可重试。

        Args:
            e (RespNotOkException): 捕获到的响应异常。
            model_info (ModelInfo): 当前模型信息。
            api_provider (APIProvider): API提供商配置。
            remain_try (int): 剩余重试次数。
            messages_info (tuple): 包含消息列表和是否已压缩的标志。

        Returns:
            Tuple[int, Optional[List[Message]]]: (等待间隔, 新的消息列表)。
            等待间隔为-1表示不再重试。新的消息列表用于压缩后重试。
        """
        model_name = model_info.name
        # 处理客户端错误 (400-404)，这些错误通常是请求本身有问题，不应重试
        if e.status_code in [400, 401, 402, 403, 404]:
            logger.warning(
                f"任务-'{self.task_name}' 模型-'{model_name}': 客户端错误 {e.status_code} - {e.message}，不再重试。"
            )
            return -1, None
        # 处理请求体过大的情况
        elif e.status_code == 413:
            messages, is_compressed = messages_info
            # 如果消息存在且尚未被压缩，则尝试压缩后立即重试
            if messages and not is_compressed:
                logger.warning(f"任务-'{self.task_name}' 模型-'{model_name}': 请求体过大，尝试压缩消息后重试。")
                return 0, compress_messages(messages)
            # 如果已经压缩过或没有消息体，则放弃
            logger.warning(f"任务-'{self.task_name}' 模型-'{model_name}': 请求体过大且无法压缩，放弃请求。")
            return -1, None
        # 处理请求频繁或服务器端错误，这些情况适合重试
        elif e.status_code == 429 or e.status_code >= 500:
            reason = "请求过于频繁" if e.status_code == 429 else "服务器错误"
            return await self._check_retry(remain_try, api_provider.retry_interval, reason, model_name)
        # 处理其他未知的HTTP错误
        else:
            logger.warning(f"任务-'{self.task_name}' 模型-'{model_name}': 未知响应错误 {e.status_code} - {e.message}")
            return -1, None

    async def _check_retry(self, remain_try: int, interval: int, reason: str, model_name: str) -> tuple[int, None]:
        """
        辅助函数，根据剩余次数决定是否进行下一次重试。

        Args:
            remain_try (int): 剩余的重试次数。
            interval (int): 重试前的等待间隔（秒）。
            reason (str): 本次失败的原因。
            model_name (str): 失败的模型名称。

        Returns:
            Tuple[int, None]: (等待间隔, None)。如果等待间隔为-1，表示不应再重试。
        """
        # 只有在剩余重试次数大于1时才进行下一次重试（因为当前这次失败已经消耗掉一次）
        if remain_try > 1:
            logger.warning(
                f"任务-'{self.task_name}' 模型-'{model_name}': {reason}，将于{interval}秒后重试 ({remain_try - 1}次剩余)。"
            )
            return interval, None

        # 如果已无剩余重试次数，则记录错误并返回-1表示放弃
        logger.error(f"任务-'{self.task_name}' 模型-'{model_name}': {reason}，已达最大重试次数，放弃。")
        return -1, None


class _RequestStrategy:
    """
    封装高级请求策略，如故障转移。
    此类协调模型选择、提示处理和请求执行，以实现健壮的请求处理，
    即使在单个模型或API端点失败的情况下也能正常工作。
    """

    def __init__(
        self,
        model_selector: _ModelSelector,
        prompt_processor: _PromptProcessor,
        executor: _RequestExecutor,
        model_list: list[str],
        task_name: str,
        *,
        system_prompt: str | None = None,
    ):
        """
        初始化请求策略。

        Args:
            model_selector (_ModelSelector): 模型选择器实例。
            prompt_processor (_PromptProcessor): 提示处理器实例。
            executor (_RequestExecutor): 请求执行器实例。
            model_list (List[str]): 可用模型列表。
            task_name (str): 当前任务的名称。
        """
        self.model_selector = model_selector
        self.prompt_processor = prompt_processor
        self.executor = executor
        self.model_list = model_list
        self.task_name = task_name
        self.system_prompt = system_prompt

    async def execute_with_failover(
        self,
        request_type: RequestType,
        raise_when_empty: bool = True,
        **kwargs,
    ) -> tuple[APIResponse, ModelInfo]:
        """
        执行请求，动态选择最佳可用模型，并在模型失败时进行故障转移。
        """
        failed_models_in_this_request = set()
        max_attempts = len(self.model_list)
        last_exception: Exception | None = None

        for attempt in range(max_attempts):
            selection_result = await self.model_selector.select_best_available_model(
                failed_models_in_this_request, str(request_type.value)
            )
            if selection_result is None:
                logger.error(f"尝试 {attempt + 1}/{max_attempts}: 没有可用的模型了。")
                break

            model_info, api_provider, client = selection_result
            logger.debug(f"尝试 {attempt + 1}/{max_attempts}: 正在使用模型 '{model_info.name}'...")

            try:
                # 准备请求参数
                request_kwargs = kwargs.copy()
                if request_type == RequestType.RESPONSE and "prompt" in request_kwargs:
                    prompt = request_kwargs.pop("prompt")
                    processed_prompt = await self.prompt_processor.prepare_prompt(
                        prompt, model_info, self.task_name
                    )
                    message_list = []
                    if self.system_prompt:
                        system_message = (
                            MessageBuilder()
                            .set_role(RoleType.System)
                            .add_text_content(self.system_prompt)
                            .build()
                        )
                        message_list.append(system_message)

                    user_message = MessageBuilder().add_text_content(processed_prompt).build()
                    message_list.append(user_message)
                    request_kwargs["message_list"] = message_list

                # 合并模型特定的额外参数
                if model_info.extra_params:
                    request_kwargs["extra_params"] = {
                        **model_info.extra_params,
                        **request_kwargs.get("extra_params", {}),
                    }

                response = await self._try_model_request(
                    model_info, api_provider, client, request_type, **request_kwargs
                )

                # 成功，立即返回
                logger.debug(f"模型 '{model_info.name}' 成功生成了回复。")
                await self.model_selector.update_usage_penalty(model_info.name, increase=False)
                return response, model_info

            except Exception as e:
                logger.error(f"模型 '{model_info.name}' 失败，异常: {e}。将其添加到当前请求的失败模型列表中。")
                failed_models_in_this_request.add(model_info.name)
                last_exception = e
                # 使用惩罚值已在 select 时增加，失败后不减少，以降低其后续被选中的概率

        logger.error(f"当前请求已尝试 {max_attempts} 个模型，所有模型均已失败。")
        if raise_when_empty:
            if last_exception:
                raise RuntimeError("所有模型均未能生成响应。") from last_exception
            raise RuntimeError("所有模型均未能生成响应，且无具体异常信息。")

        # 如果不抛出异常，返回一个备用响应
        assert model_config is not None, "model_config 不能为 None"
        fallback_model_info = model_config.get_model_info(self.model_list[0])
        return APIResponse(content="所有模型都请求失败"), fallback_model_info

    async def _try_model_request(
        self, model_info: ModelInfo, api_provider: APIProvider, client: BaseClient, request_type: RequestType, **kwargs
    ) -> APIResponse:
        """
        为单个模型尝试请求，包含空回复/截断的内部重试逻辑。
        如果模型返回空回复或响应被截断，此方法将自动重试请求，直到达到最大重试次数。

        Args:
            model_info (ModelInfo): 要使用的模型信息。
            api_provider (APIProvider): API提供商信息。
            client (BaseClient): API客户端实例。
            request_type (RequestType): 请求类型。
            **kwargs: 传递给执行器的请求参数。

        Returns:
            APIResponse: 成功的API响应。

        Raises:
            RuntimeError: 如果在达到最大重试次数后仍然收到空回复或截断的响应。
        """
        max_empty_retry = api_provider.max_retry

        for i in range(max_empty_retry + 1):
            response = await self.executor.execute_request(api_provider, client, request_type, model_info, **kwargs)

            if request_type != RequestType.RESPONSE:
                return response  # 对于非响应类型，直接返回

            # --- 响应内容处理和空回复/截断检查 ---
            content = response.content or ""
            use_anti_truncation = model_info.anti_truncation
            processed_content, reasoning, is_truncated = await self.prompt_processor.process_response(
                content, use_anti_truncation
            )

            # 更新响应对象
            response.content = processed_content
            response.reasoning_content = response.reasoning_content or reasoning

            is_empty_reply = not response.tool_calls and not (response.content and response.content.strip())

            if not is_empty_reply and not is_truncated:
                return response  # 成功获取有效响应

            if i < max_empty_retry:
                reason = "空回复" if is_empty_reply else "截断"
                logger.warning(
                    f"模型 '{model_info.name}' 检测到{reason}，正在进行内部重试 ({i + 1}/{max_empty_retry})..."
                )
                if api_provider.retry_interval > 0:
                    await asyncio.sleep(api_provider.retry_interval)
            else:
                reason = "空回复" if is_empty_reply else "截断"
                logger.error(f"模型 '{model_info.name}' 经过 {max_empty_retry} 次内部重试后仍然生成{reason}的回复。")
                raise RuntimeError(f"模型 '{model_info.name}' 已达到空回复/截断的最大内部重试次数。")

        raise RuntimeError("内部重试逻辑错误")  # 理论上不应到达这里


# ==============================================================================
# Main Facade Class
# ==============================================================================


class LLMRequest:
    """
    LLM请求协调器。
    封装了模型选择、Prompt处理、请求执行和高级策略（如故障转移、并发）的完整流程。
    为上层业务逻辑提供统一的、简化的接口来与大语言模型交互。
    """

    def __init__(self, model_set: TaskConfig, request_type: str = ""):
        """
        初始化LLM请求协调器。

        Args:
            model_set (TaskConfig): 特定任务的模型配置集合。
            request_type (str, optional): 请求类型或任务名称，用于日志和用量记录。 Defaults to "".
        """
        self.task_name = request_type
        self.model_for_task = model_set
        self.system_prompt = self._resolve_system_prompt(model_set)
        self.model_usage: dict[str, ModelUsageStats] = {
            model: ModelUsageStats(total_tokens=0, penalty=0, usage_penalty=0, avg_latency=0.0, request_count=0)
            for model in self.model_for_task.model_list
        }
        """模型使用量记录"""
        # 🔧 优化：移除全局锁，改用信号量控制并发度（允许多个请求并行）
        # 默认允许50个并发请求，可通过配置调整
        max_concurrent = getattr(model_set, "max_concurrent_requests", 50)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._stats_lock = asyncio.Lock()  # 只保护统计数据的写入

        # 初始化辅助类
        self._model_selector = _ModelSelector(self.model_for_task.model_list, self.model_usage)
        self._prompt_processor = _PromptProcessor()
        self._executor = _RequestExecutor(self._model_selector, self.task_name)
        self._strategy = _RequestStrategy(
            self._model_selector,
            self._prompt_processor,
            self._executor,
            self.model_for_task.model_list,
            self.task_name,
            system_prompt=self.system_prompt,
        )

    def _resolve_system_prompt(self, model_set: TaskConfig) -> str | None:
        """确定是否需要附加统一的system prompt."""
        try:
            if model_config and (model_set is model_config.model_task_config.replyer or model_set is model_config.model_task_config.replyer_private):
                return SYSTEM_PROMPT
        except AttributeError:
            logger.debug("模型配置缺少replyer定义，无法注入系统提示词")
        return None

    async def generate_response_for_image(
        self,
        prompt: str,
        image_base64: str,
        image_format: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, tuple[str, str, list[ToolCall] | None]]:
        """
        为图像生成响应。

        Args:
            prompt (str): 提示词
            image_base64 (str): 图像的Base64编码字符串
            image_format (str): 图像格式（如 'png', 'jpeg' 等）

        Returns:
            (Tuple[str, str, str, Optional[List[ToolCall]]]): 响应内容、推理内容、模型名称、工具调用列表
        """
        start_time = time.time()

        # 图像请求目前不使用复杂的故障转移策略，直接选择模型并执行
        selection_result = await self._model_selector.select_best_available_model(set(), "response")
        if not selection_result:
            raise RuntimeError("无法为图像响应选择可用模型。")
        model_info, api_provider, client = selection_result

        normalized_format = await _normalize_image_format(image_format)
        message = (
            MessageBuilder()
            .add_text_content(prompt)
            .add_image_content(
                image_base64=image_base64,
                image_format=normalized_format,
                support_formats=client.get_support_image_formats(),
            )
            .build()
        )

        response = await self._executor.execute_request(
            api_provider,
            client,
            RequestType.RESPONSE,
            model_info,
            message_list=[message],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        await self._record_usage(model_info, response.usage, time.time() - start_time, "/chat/completions")
        content, reasoning, _ = await self._prompt_processor.process_response(response.content or "", False)
        reasoning = response.reasoning_content or reasoning

        return content, (reasoning, model_info.name, response.tool_calls)

    async def generate_response_for_voice(self, voice_base64: str) -> str | None:
        """
        为语音生成响应（语音转文字）。
        使用故障转移策略来确保即使主模型失败也能获得结果。

        Args:
            voice_base64 (str): 语音的Base64编码字符串。

        Returns:
            Optional[str]: 语音转换后的文本内容，如果所有模型都失败则返回None。
        """
        response, _ = await self._strategy.execute_with_failover(RequestType.AUDIO, audio_base64=voice_base64)
        return response.content or None

    async def generate_response_async(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        raise_when_empty: bool = True,
    ) -> tuple[str, tuple[str, str, list[ToolCall] | None]]:
        """
        异步生成响应，支持并发请求。

        Args:
            prompt (str): 提示词
            temperature (float, optional): 温度参数
            max_tokens (int, optional): 最大token数
            tools: 工具配置
            raise_when_empty (bool): 是否在空回复时抛出异常

        Returns:
            (Tuple[str, str, str, Optional[List[ToolCall]]]): 响应内容、推理内容、模型名称、工具调用列表
        """
        concurrency_count = getattr(self.model_for_task, "concurrency_count", 1)

        if concurrency_count <= 1:
            return await self._execute_single_text_request(prompt, temperature, max_tokens, tools, raise_when_empty)

        try:
            return await execute_concurrently(
                self._execute_single_text_request,
                concurrency_count,
                prompt,
                temperature,
                max_tokens,
                tools,
                raise_when_empty=False,
            )
        except Exception as e:
            logger.error(f"所有 {concurrency_count} 个并发请求都失败了: {e}")
            if raise_when_empty:
                raise e
            return "所有并发请求都失败了", ("", "unknown", None)

    async def _execute_single_text_request(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        raise_when_empty: bool = True,
    ) -> tuple[str, tuple[str, str, list[ToolCall] | None]]:
        """
        执行单次文本生成请求的内部方法。
        这是 `generate_response_async` 的核心实现，处理单个请求的完整生命周期，
        包括工具构建、故障转移执行和用量记录。

        Args:
            prompt (str): 用户的提示。
            temperature (Optional[float]): 生成温度。
            max_tokens (Optional[int]): 最大生成令牌数。
            tools (Optional[List[Dict[str, Any]]]): 可用工具列表。
            raise_when_empty (bool): 如果响应为空是否引发异常。

        Returns:
            Tuple[str, Tuple[str, str, Optional[List[ToolCall]]]]:
                (响应内容, (推理过程, 模型名称, 工具调用))
        """
        # 🔧 优化：使用信号量控制并发，允许多个请求并行执行
        async with self._semaphore:
            start_time = time.time()
            tool_options = await self._build_tool_options(tools)

            response, model_info = await self._strategy.execute_with_failover(
                RequestType.RESPONSE,
                raise_when_empty=raise_when_empty,
                prompt=prompt,  # 传递原始prompt，由strategy处理
                tool_options=tool_options,
                temperature=self.model_for_task.temperature if temperature is None else temperature,
                max_tokens=self.model_for_task.max_tokens if max_tokens is None else max_tokens,
            )

            await self._record_usage(model_info, response.usage, time.time() - start_time, "/chat/completions")
            logger.debug(f"LLM原始响应: {response.content}")

            if not response.content and not response.tool_calls:
                if raise_when_empty:
                    raise RuntimeError("所选模型生成了空回复。")
                response.content = "生成的响应为空"

            return response.content or "", (response.reasoning_content or "", model_info.name, response.tool_calls)

    async def get_embedding(self, embedding_input: str | list[str]) -> tuple[list[float] | list[list[float]], str]:
        """
        获取嵌入向量，支持批量文本

        Args:
            embedding_input (str | list[str]): 需要生成嵌入的文本或文本列表

        Returns:
            (Tuple[Union[List[float], List[List[float]]], str]): 嵌入结果及使用的模型名称
        """
        start_time = time.time()
        response, model_info = await self._strategy.execute_with_failover(
            RequestType.EMBEDDING, embedding_input=embedding_input
        )

        await self._record_usage(model_info, response.usage, time.time() - start_time, "/embeddings")

        if response.embedding is None:
            raise RuntimeError("获取embedding失败")

        embeddings = response.embedding
        is_batch_request = isinstance(embedding_input, list)

        if is_batch_request:
            if not isinstance(embeddings, list):
                raise RuntimeError("获取embedding失败，批量结果格式异常")

            # embeddings 正常应该是 list[vector]；如果 provider 返回了一维列表（单向量），只在这种情况下套一层
            if embeddings and not isinstance(embeddings[0], (list, tuple, np.ndarray)):
                embeddings = [embeddings]  # type: ignore[list-item]

            # 批量请求返回二维列表
            return embeddings, model_info.name  # type: ignore[return-value]

        # 单个请求返回一维列表
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return embeddings[0], model_info.name  # type: ignore[return-value]

        return embeddings, model_info.name  # type: ignore[return-value]

    async def execute_with_messages(
        self,
        message_list: list[Message],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> APIResponse:
        """
        使用自定义消息列表执行请求（支持多模态/多图）。
        """
        start_time = time.time()
        response, model_info = await self._strategy.execute_with_failover(
            RequestType.RESPONSE,
            message_list=message_list,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        await self._record_usage(model_info, response.usage, time.time() - start_time, "/chat/completions")
        return response

    async def _record_usage(self, model_info: ModelInfo, usage: UsageRecord | None, time_cost: float, endpoint: str):
        """
        记录模型使用情况。

        此方法首先在内存中更新模型的累计token使用量，然后创建一个异步任务，
        将详细的用量数据（包括模型信息、token数、耗时等）写入数据库。

        Args:
            model_info (ModelInfo): 使用的模型信息。
            usage (Optional[UsageRecord]): API返回的用量记录。
            time_cost (float): 本次请求的总耗时。
            endpoint (str): 请求的API端点 (e.g., "/chat/completions")。
        """
        if usage:
            # 步骤1: 更新内存中的统计数据，用于负载均衡（需要加锁保护）
            async with self._stats_lock:
                stats = self.model_usage[model_info.name]

                # 计算新的平均延迟
                new_request_count = stats.request_count + 1
                new_avg_latency = (stats.avg_latency * stats.request_count + time_cost) / new_request_count

                self.model_usage[model_info.name] = stats._replace(
                    total_tokens=stats.total_tokens + usage.total_tokens,
                    avg_latency=new_avg_latency,
                    request_count=new_request_count,
                )

            # 步骤2: 创建一个后台任务，将用量数据异步写入数据库（无需等待）
            asyncio.create_task(  # noqa: RUF006
                llm_usage_recorder.record_usage_to_database(
                    model_info=model_info,
                    model_usage=usage,
                    user_id="system",  # 此处可根据业务需求修改
                    time_cost=time_cost,
                    request_type=self.task_name,
                    endpoint=endpoint,
                )
            )

    @staticmethod
    async def _build_tool_options(tools: list[dict[str, Any]] | None) -> list[ToolOption] | None:
        """
        根据输入的字典列表构建并验证 `ToolOption` 对象列表。

        此方法将标准化的工具定义（字典格式）转换为内部使用的 `ToolOption` 对象，
        同时会验证参数格式的正确性。

        Args:
            tools (Optional[List[Dict[str, Any]]]): 工具定义的列表。
                每个工具是一个字典，包含 "name", "description", 和 "parameters"。
                "parameters" 是一个元组列表，每个元组包含 (name, type, desc, required, enum)。

        Returns:
            Optional[List[ToolOption]]: 构建好的 `ToolOption` 对象列表，如果输入为空则返回 None。
        """
        # 如果没有提供工具，直接返回 None
        if not tools:
            return None

        tool_options: list[ToolOption] = []
        # 遍历每个工具定义
        for tool in tools:
            try:
                # 使用建造者模式创建 ToolOption
                builder = ToolOptionBuilder().set_name(tool["name"]).set_description(tool.get("description", ""))

                # 遍历工具的参数
                for param in tool.get("parameters", []):
                    # 严格验证参数格式是否为包含5个元素的元组
                    assert isinstance(param, tuple), "参数必须是元组"
                    assert len(param) == 5, "参数必须包含5个元素"
                    builder.add_param(
                        name=param[0],
                        param_type=param[1],
                        description=param[2],
                        required=param[3],
                        enum_values=param[4],
                    )
                # 将构建好的 ToolOption 添加到列表中
                tool_options.append(builder.build())
            except (KeyError, IndexError, TypeError, AssertionError) as e:
                # 如果构建过程中出现任何错误，记录日志并跳过该工具
                logger.error(f"构建工具 '{tool.get('name', 'N/A')}' 失败: {e}")

        # 如果列表非空则返回列表，否则返回 None
        return tool_options or None
