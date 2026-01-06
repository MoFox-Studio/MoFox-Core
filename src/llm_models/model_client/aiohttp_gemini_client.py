import asyncio
import io
import time
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp
import orjson

from src.common.logger import get_logger
from src.config.api_ada_configs import APIProvider, ModelInfo

from ..exceptions import (
    NetworkConnectionError,
    ReqAbortException,
    RespNotOkException,
    RespParseException,
)
from ..payload_content.message import Message, RoleType
from ..payload_content.resp_format import RespFormat, RespFormatType
from ..payload_content.tool_option import ToolCall, ToolOption, ToolParam
from .base_client import APIResponse, BaseClient, UsageRecord, client_registry

logger = get_logger("AioHTTP-Gemini客户端")

# 🔍 性能监控：Session 泄漏检测（保留用于诊断）
_session_create_count = 0  # Session 创建总数
_request_count = 0  # 总请求数
_last_monitor_time = time.time()  # 上次监控时间
_request_times = []  # 最近请求耗时（保留最近100条）


# gemini_thinking参数(默认范围) - 旧版 thinking_budget
# 不同模型的思考预算范围配置
THINKING_BUDGET_LIMITS = {
    "gemini-2.5-flash": {"min": 1, "max": 24576, "can_disable": True},
    "gemini-2.5-flash-lite": {"min": 512, "max": 24576, "can_disable": True},
    "gemini-2.5-pro": {"min": 128, "max": 32768, "can_disable": False},
}
# 思维预算特殊值
THINKING_BUDGET_AUTO = -1  # 自动调整思考预算,由模型决定
THINKING_BUDGET_DISABLED = 0  # 禁用思考预算(如果模型允许禁用)

# 新版 thinking_level 参数
# 支持的思考等级
THINKING_LEVEL_LOW = "low"
THINKING_LEVEL_MEDIUM = "medium"
THINKING_LEVEL_HIGH = "high"
VALID_THINKING_LEVELS = [THINKING_LEVEL_LOW, THINKING_LEVEL_MEDIUM, THINKING_LEVEL_HIGH]

gemini_safe_settings = [
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]


def _format_to_mime_type(image_format: str) -> str:
    """
    将图片格式转换为正确的MIME类型

    Args:
        image_format (str): 图片格式 (如 'jpg', 'png' 等)

    Returns:
        str: 对应的MIME类型
    """
    format_mapping = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "heic": "image/heic",
        "heif": "image/heif",
    }

    return format_mapping.get(image_format.lower(), f"image/{image_format.lower()}")


def _convert_messages(messages: list[Message]) -> tuple[list[dict], list[str] | None]:
    """
    转换消息格式 - 将消息转换为Gemini REST API所需的格式
    :param messages: 消息列表
    :return: (contents, system_instructions)
    """

    def _convert_message_item(message: Message) -> dict:
        """转换单个消息格式"""
        # 转换角色名称
        if message.role == RoleType.Assistant:
            role = "model"
        elif message.role == RoleType.User:
            role = "user"
        else:
            raise ValueError(f"不支持的消息角色: {message.role}")

        # 转换内容
        parts = []
        if isinstance(message.content, str):
            parts.append({"text": message.content})
        elif isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, tuple):  # (format, base64_data)
                    parts.append({"inline_data": {"mime_type": _format_to_mime_type(item[0]), "data": item[1]}})
                elif isinstance(item, str):
                    parts.append({"text": item})
        else:
            raise RuntimeError("无法触及的代码：请使用MessageBuilder类构建消息对象")

        return {"role": role, "parts": parts}

    contents = []
    system_instructions = []

    for message in messages:
        if message.role == RoleType.System:
            if isinstance(message.content, str):
                system_instructions.append(message.content)
            else:
                raise ValueError("System消息不支持非文本内容")
        elif message.role == RoleType.Tool:
            # 工具调用结果处理
            if not message.tool_call_id:
                raise ValueError("工具调用消息缺少tool_call_id")
            contents.append({"role": "function", "parts": [{"text": str(message.content)}]})
        else:
            contents.append(_convert_message_item(message))

    return contents, system_instructions if system_instructions else None


def _convert_tool_options(tool_options: list[ToolOption]) -> list[dict]:
    """
    转换工具选项格式 - 将内部 ToolOption 对象列表转换为 Gemini REST API 所需的格式。

    Args:
        tool_options: 要转换的 ToolOption 对象列表。

    Returns:
        一个列表，其中每个字典都代表一个 Gemini API 的工具声明。
    """

    def _convert_tool_param(param: ToolParam) -> dict[str, Any]:
        """转换工具参数"""
        result: dict[str, Any] = {
            "type": param.param_type.value,
            "description": param.description,
        }
        if param.enum_values:
            result["enum"] = param.enum_values
        return result

    def _convert_tool_option_item(tool_option: ToolOption) -> dict[str, Any]:
        """转换单个工具选项"""
        function_declaration: dict[str, Any] = {
            "name": tool_option.name,
            "description": tool_option.description,
        }

        if tool_option.params:
            function_declaration["parameters"] = {
                "type": "object",
                "properties": {param.name: _convert_tool_param(param) for param in tool_option.params},
                "required": [param.name for param in tool_option.params if param.required],
            }

        return {"function_declarations": [function_declaration]}

    return [_convert_tool_option_item(tool_option) for tool_option in tool_options]


def _build_generation_config(
    max_tokens: int,
    temperature: float,
    thinking_budget: int | None = None,
    thinking_level: str | None = None,
    response_format: RespFormat | None = None,
    extra_params: dict | None = None,
) -> dict:
    """
    构建并返回 Gemini API 的 `generationConfig` 字典。

    此函数整合了多个参数，如最大输出 token 数、温度、思考配置(预算或等级)、响应格式和
    其他自定义参数，以创建一个符合 Gemini API 规范的配置对象。

    注意: thinking_budget 和 thinking_level 不能同时使用，否则会返回 400 错误。
    优先使用 thinking_level (新版)，如果未提供则使用 thinking_budget (旧版)。

    Args:
        max_tokens: 生成内容的最大 token 数。
        temperature: 控制生成文本的随机性，值越高越随机。
        thinking_budget: 模型的思考预算(旧版，与 thinking_level 互斥)。
        thinking_level: 模型的思考等级(新版，可选值: "low", "medium", "high")。
        response_format: 指定响应的格式，例如 JSON 对象或遵循特定 schema。
        extra_params: 一个包含其他要合并到配置中的参数的字典。

    Returns:
        一个包含完整 `generationConfig` 的字典。
    """
    config = {
        "maxOutputTokens": max_tokens,
        "temperature": temperature,
        "topK": 1,
        "topP": 1,
    }

    # 处理思考配置 - 新版 thinking_level 优先于旧版 thinking_budget
    if thinking_level is not None:
        # 使用新版 thinkingLevel 参数
        if thinking_level in VALID_THINKING_LEVELS:
            config["thinkingConfig"] = {"thinkingLevel": thinking_level}
        else:
            logger.warning(f"无效的 thinking_level 值 {thinking_level}，有效值为: {VALID_THINKING_LEVELS}")
    elif thinking_budget is not None:
        # 使用旧版 thinkingBudget 参数
        config["thinkingConfig"] = {"includeThoughts": True, "thinkingBudget": thinking_budget}

    # 处理响应格式
    if response_format:
        if response_format.format_type == RespFormatType.JSON_OBJ:
            config["responseMimeType"] = "application/json"
        elif response_format.format_type == RespFormatType.JSON_SCHEMA:
            config["responseMimeType"] = "application/json"
            config["responseSchema"] = response_format.to_dict()

    # 合并额外参数
    if extra_params:
        # 拷贝一份以防修改原始字典
        safe_extra_params = extra_params.copy()
        # 移除已单独处理的参数
        safe_extra_params.pop("thinking_budget", None)
        safe_extra_params.pop("thinking_level", None)
        config.update(safe_extra_params)

    return config


class AiohttpGeminiStreamParser:
    """
    用于处理和解析来自 Gemini API 的流式（server-sent events）响应的专用解析器。

    该类会累积流式数据块，并从中提取内容、思考过程、工具调用和使用情况统计。
    """

    def __init__(self):
        """初始化解析器，创建用于存储解析数据的缓冲区。"""
        self.content_buffer = io.StringIO()  # 用于累积文本内容
        self.reasoning_buffer = io.StringIO()  # 用于累积思考过程内容
        self.tool_calls_buffer = []  # 用于存储工具调用信息
        self.usage_record = None  # 用于存储最终的使用情况统计

    def parse_chunk(self, chunk_text: str):
        """
        解析单个流式数据块（通常是一行 SSE 数据）。

        Args:
            chunk_text: 从流式响应中接收到的原始文本数据块。
        """
        try:
            if not chunk_text.strip():
                return

            # 移除data:前缀
            if chunk_text.startswith("data: "):
                chunk_text = chunk_text[6:].strip()

            if chunk_text == "[DONE]":
                return

            chunk_data = orjson.loads(chunk_text)

            # 解析候选项
            if chunk_data.get("candidates"):
                candidate = chunk_data["candidates"][0]

                # 解析内容
                if "content" in candidate and "parts" in candidate["content"]:
                    for part in candidate["content"]["parts"]:
                        if "text" in part:
                            self.content_buffer.write(part["text"])

                # 解析工具调用
                if "functionCall" in candidate:
                    func_call = candidate["functionCall"]
                    call_id = f"gemini_call_{len(self.tool_calls_buffer)}"
                    self.tool_calls_buffer.append(
                        {"id": call_id, "name": func_call.get("name", ""), "args": func_call.get("args", {})}
                    )

            # 解析使用统计
            if "usageMetadata" in chunk_data:
                usage = chunk_data["usageMetadata"]
                self.usage_record = (
                    usage.get("promptTokenCount", 0),
                    usage.get("candidatesTokenCount", 0),
                    usage.get("totalTokenCount", 0),
                )

        except orjson.JSONDecodeError as e:
            logger.warning(f"解析流式数据块失败: {e}, 数据: {chunk_text}")
        except Exception as e:
            logger.error(f"处理流式数据块时出错: {e}")

    def get_response(self) -> APIResponse:
        """
        在所有数据块处理完毕后，获取最终的、结构化的 APIResponse 对象。

        此方法会整合所有缓冲区中的数据，并将其封装到一个 APIResponse 对象中。
        调用此方法后，内部缓冲区将被清理。

        Returns:
            一个包含从流中解析出的所有信息的 APIResponse 对象。
        """
        response = APIResponse()

        if self.content_buffer.tell() > 0:
            response.content = self.content_buffer.getvalue()

        if self.reasoning_buffer.tell() > 0:
            response.reasoning_content = self.reasoning_buffer.getvalue()

        if self.tool_calls_buffer:
            response.tool_calls = []
            for call_data in self.tool_calls_buffer:
                response.tool_calls.append(ToolCall(call_data["id"], call_data["name"], call_data["args"]))

        # 清理缓冲区
        self.content_buffer.close()
        self.reasoning_buffer.close()

        return response


async def _default_stream_response_handler(
    response: aiohttp.ClientResponse,
    interrupt_flag: asyncio.Event | None,
) -> tuple[APIResponse, tuple[int, int, int] | None]:
    """
    默认的流式响应处理器。

    此异步函数迭代处理 aiohttp 响应的每一行，使用 AiohttpGeminiStreamParser
    来解析它们，并处理中断信号。

    Args:
        response: aiohttp 的 ClientResponse 对象。
        interrupt_flag: 一个 asyncio.Event，用于发出中断请求的信号。

    Returns:
        一个元组，包含最终的 APIResponse 和使用情况记录。

    Raises:
        ReqAbortException: 如果请求被中断。
        RespParseException: 如果流式响应解析失败。
    """
    parser = AiohttpGeminiStreamParser()

    try:
        async for line in response.content:
            if interrupt_flag and interrupt_flag.is_set():
                raise ReqAbortException("请求被外部信号中断")

            line_text = line.decode("utf-8").strip()
            if line_text:
                parser.parse_chunk(line_text)

        api_response = parser.get_response()
        return api_response, parser.usage_record

    except Exception as e:
        if not isinstance(e, ReqAbortException):
            raise RespParseException(None, f"流式响应解析失败: {e}") from e
        raise


def _default_normal_response_parser(
    response_data: dict,
) -> tuple[APIResponse, tuple[int, int, int] | None]:
    """
    默认的非流式（普通）响应解析器。

    此函数解析一个完整的 JSON 响应体，并从中提取内容、工具调用和使用情况统计。

    Args:
        response_data: 已解析为字典的 JSON 响应数据。

    Returns:
        一个元组，包含最终的 APIResponse 和使用情况记录。

    Raises:
        RespParseException: 如果响应解析失败。
    """
    api_response = APIResponse()

    try:
        # 解析候选项
        if response_data.get("candidates"):
            candidate = response_data["candidates"][0]

            # 解析文本内容
            if "content" in candidate and "parts" in candidate["content"]:
                content_parts = [part["text"] for part in candidate["content"]["parts"] if "text" in part]

                if content_parts:
                    api_response.content = "".join(content_parts)

            # 解析工具调用
            if "functionCall" in candidate:
                func_call = candidate["functionCall"]
                api_response.tool_calls = [
                    ToolCall("gemini_call_0", func_call.get("name", ""), func_call.get("args", {}))
                ]

        # 解析使用统计
        usage_record = None
        if "usageMetadata" in response_data:
            usage = response_data["usageMetadata"]
            usage_record = (
                usage.get("promptTokenCount", 0),
                usage.get("candidatesTokenCount", 0),
                usage.get("totalTokenCount", 0),
            )

        api_response.raw_data = response_data
        return api_response, usage_record

    except Exception as e:
        raise RespParseException(response_data, f"响应解析失败: {e}") from e


@client_registry.register_client_class("aiohttp_gemini")
class AiohttpGeminiClient(BaseClient):
    """
    一个使用 aiohttp 库与 Google Gemini API 进行异步通信的客户端。

    该客户端实现了 BaseClient 接口，提供了获取对话响应、处理流式数据、
    管理 API key 和端点等功能。它被设计为无状态的，每次请求都创建一个
    新的 aiohttp.ClientSession，以增强健壮性。
    """

    def __init__(self, api_provider: APIProvider):
        """
        初始化 AiohttpGeminiClient。

        Args:
            api_provider: 包含 API key 和可选的 base_url 的 APIProvider 对象。
        """
        super().__init__(api_provider)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        # 🔧 修复：创建全局复用的 Session，避免每次请求都创建新 Session
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

        # 如果 API provider 中提供了自定义的 base_url，则覆盖默认值
        if api_provider.base_url:
            self.base_url = api_provider.base_url.rstrip("/")

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建全局复用的 Session（线程安全）"""
        if self._session is None or self._session.closed:
            async with self._session_lock:
                if self._session is None or self._session.closed:
                    self._session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=300),
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        },
                    )
                    logger.debug("✅ 创建新的全局 Session（复用模式）")
        return self._session

    async def _close_session(self):
        """关闭 Session"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("🛑 Session 已关闭")

    @staticmethod
    def clamp_thinking_budget(tb: int, model_id: str) -> int:
        """
        按模型限制思考预算范围，仅支持指定的模型（支持带数字后缀的新版本）
        """
        limits = None

        # 优先尝试精确匹配
        if model_id in THINKING_BUDGET_LIMITS:
            limits = THINKING_BUDGET_LIMITS[model_id]
        else:
            # 按 key 长度倒序，保证更长的（更具体的，如 -lite）优先
            sorted_keys = sorted(THINKING_BUDGET_LIMITS.keys(), key=len, reverse=True)
            for key in sorted_keys:
                # 必须满足：完全等于 或者 前缀匹配（带 "-" 边界）
                if model_id == key or model_id.startswith(f"{key}-"):
                    limits = THINKING_BUDGET_LIMITS[key]
                    break

        # 特殊值处理
        if tb == THINKING_BUDGET_AUTO:
            return THINKING_BUDGET_AUTO
        if tb == THINKING_BUDGET_DISABLED:
            if limits and limits.get("can_disable", False):
                return THINKING_BUDGET_DISABLED
            return limits["min"] if limits else THINKING_BUDGET_AUTO

        # 已知模型裁剪到范围
        if limits:
            return max(limits["min"], min(tb, limits["max"]))

        # 未知模型，返回动态模式
        logger.warning(f"模型 {model_id} 未在 THINKING_BUDGET_LIMITS 中定义，将使用动态模式 tb=-1 兼容。")
        return tb

    # 移除全局 session，全部请求都用 with aiohttp.ClientSession() as session:

    async def _make_request(
        self, method: str, endpoint: str, data: dict | None = None, stream: bool = False
    ) -> aiohttp.ClientResponse:
        """
        向 Gemini API 发起一个 HTTP 请求，并增加了重试逻辑。

        此方法封装了 aiohttp 的请求逻辑，包括 URL 构建、认证、超时和错误处理。
        - 对于网络连接相关的 `aiohttp.ClientError`，它会最多重试3次。
        - 对于 HTTP 状态码错误（如 4xx, 5xx），它会立即失败，不会重试。
        为了健壮性，它在每次调用时都会创建一个新的 aiohttp.ClientSession。

        Args:
            method: HTTP 请求方法 (例如, "POST")。
            endpoint: API 的目标端点 (例如, "models/gemini-pro:generateContent")。
            data: 要作为 JSON 发送到请求体的数据。
            stream: 如果为 True，则请求一个流式响应。

        Returns:
            一个 aiohttp.ClientResponse 对象。

        Raises:
            RespNotOkException: 如果 HTTP 响应状态码表示错误。
            NetworkConnectionError: 如果在所有重试尝试后仍然发生 aiohttp 客户端错误。
        """
        api_key = self.api_provider.get_api_key()
        url = f"{self.base_url}/{endpoint}?key={api_key}"

        max_retries = 3
        last_exception = None

        for attempt in range(max_retries):
            try:
                # � 修复：使用全局复用的 Session
                session = await self._get_session()
                
                if method.upper() == "POST":
                    response = await session.post(
                        url, json=data, headers={"Accept": "text/event-stream" if stream else "application/json"}
                    )
                else:
                    response = await session.get(url)

                # 检查HTTP状态码 - 如果是错误，立即失败，不重试
                if response.status >= 400:
                    error_text = await response.text()
                    raise RespNotOkException(response.status, error_text)

                # 成功，返回响应
                return response

            except aiohttp.ClientError as e:
                last_exception = e
                await asyncio.sleep(1)  # 等待1秒后重试

        # 如果所有重试都失败了
        raise NetworkConnectionError() from last_exception

    async def get_response(
        self,
        model_info: ModelInfo,
        message_list: list[Message],
        tool_options: list[ToolOption] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        response_format: RespFormat | None = None,
        stream_response_handler: Callable[
            [aiohttp.ClientResponse, asyncio.Event | None],
            Coroutine[Any, Any, tuple[APIResponse, tuple[int, int, int] | None]],
        ]
        | None = None,
        async_response_parser: Callable[[dict], tuple[APIResponse, tuple[int, int, int] | None]] | None = None,
        interrupt_flag: asyncio.Event | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取一个完整的对话响应，支持流式和非流式模式。

        这是客户端的核心方法，它负责：
        1. 转换输入消息和工具选项。
        2. 构建请求体，包括生成配置。
        3. 根据模型信息决定是使用流式还是非流式端点。
        4. 发起请求并处理中断。
        5. 使用适当的处理器/解析器处理响应。
        6. 格式化最终的 APIResponse 对象，包括使用情况统计。

        Args:
            model_info: 包含模型标识符和配置的模型信息。
            message_list: 对话消息列表。
            tool_options: 可用的工具选项列表。
            max_tokens: 最大生成 token 数。
            temperature: 生成温度。
            response_format: 响应格式。
            stream_response_handler: 用于处理流式响应的可调用对象。
            async_response_parser: 用于解析非流式响应的可调用对象。
            interrupt_flag: 用于中断请求的 asyncio.Event。
            extra_params: 包含额外参数的字典，例如 'thinking_budget'。

        Returns:
            一个包含模型响应的 APIResponse 对象。
        """
        if stream_response_handler is None:
            stream_response_handler = _default_stream_response_handler

        if async_response_parser is None:
            async_response_parser = _default_normal_response_parser

        # 转换消息格式
        contents, system_instructions = _convert_messages(message_list)

        # 处理思考配置 - 优先使用新版 thinking_level，否则使用旧版 thinking_budget
        thinking_level = None
        thinking_budget = None

        if extra_params:
            # 优先检查新版 thinking_level
            if "thinking_level" in extra_params:
                level_value = extra_params.get("thinking_level", "").lower()
                if level_value in VALID_THINKING_LEVELS:
                    thinking_level = level_value
                else:
                    logger.warning(f"无效的 thinking_level 值 {level_value}，有效值为: {VALID_THINKING_LEVELS}")
            # 如果没有 thinking_level，则使用旧版 thinking_budget
            elif "thinking_budget" in extra_params:
                try:
                    tb = int(extra_params["thinking_budget"])
                    thinking_budget = self.clamp_thinking_budget(tb, model_info.model_identifier)
                except (ValueError, TypeError):
                    logger.warning(f"无效的 thinking_budget 值 {extra_params['thinking_budget']}，将使用默认动态模式")
                    thinking_budget = THINKING_BUDGET_AUTO

        # 构建请求体
        request_data = {
            "contents": contents,
            "generationConfig": _build_generation_config(
                max_tokens,
                temperature,
                thinking_budget=thinking_budget,
                thinking_level=thinking_level,
                response_format=response_format,
                extra_params=extra_params
            ),
            "safetySettings": gemini_safe_settings,
        }

        # 添加系统指令
        if system_instructions:
            request_data["systemInstruction"] = {"parts": [{"text": instr} for instr in system_instructions]}

        # 添加工具定义
        if tool_options:
            request_data["tools"] = _convert_tool_options(tool_options)

        try:
            if model_info.force_stream_mode:
                # 流式请求
                endpoint = f"models/{model_info.model_identifier}:streamGenerateContent"
                req_task = asyncio.create_task(self._make_request("POST", endpoint, request_data, stream=True))

                while not req_task.done():
                    if interrupt_flag and interrupt_flag.is_set():
                        req_task.cancel()
                        raise ReqAbortException("请求被外部信号中断")
                    await asyncio.sleep(0.1)

                response = req_task.result()
                api_response, usage_record = await stream_response_handler(response, interrupt_flag)

            else:
                # 普通请求
                endpoint = f"models/{model_info.model_identifier}:generateContent"
                req_task = asyncio.create_task(self._make_request("POST", endpoint, request_data))

                while not req_task.done():
                    if interrupt_flag and interrupt_flag.is_set():
                        req_task.cancel()
                        raise ReqAbortException("请求被外部信号中断")
                    await asyncio.sleep(0.1)

                response = req_task.result()
                response_data = await response.json()
                api_response, usage_record = async_response_parser(response_data)

        except (ReqAbortException, NetworkConnectionError, RespNotOkException, RespParseException):
            # 直接重抛项目定义的异常
            raise
        except Exception as e:
            logger.debug(str(e))
            # 其他异常转换为网络连接错误
            raise NetworkConnectionError() from e

        # 设置使用统计
        if usage_record:
            api_response.usage = UsageRecord(
                model_name=model_info.name,
                provider_name=model_info.api_provider,
                prompt_tokens=usage_record[0],
                completion_tokens=usage_record[1],
                total_tokens=usage_record[2],
            )

        return api_response

    async def get_embedding(
        self,
        model_info: ModelInfo,
        embedding_input: str | list[str],
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        获取文本嵌入 - 此客户端不支持嵌入功能
        """
        raise NotImplementedError("AioHTTP Gemini客户端不支持文本嵌入功能")

    async def get_audio_transcriptions(
        self,
        model_info: ModelInfo,
        audio_base64: str,
        extra_params: dict[str, Any] | None = None,
    ) -> APIResponse:
        """
        使用 Gemini 模型获取音频文件的转录。

        此方法将 base64 编码的音频数据和预设的提示词发送到 Gemini API，
        并返回生成的文本转录。

        Args:
            model_info: 要使用的模型的信息。
            audio_base64: Base64 编码的 WAV 音频数据。
            extra_params: 传递给生成配置的额外参数。

        Returns:
            一个 APIResponse 对象，其 `content` 字段包含音频转录。

        Raises:
            NetworkConnectionError: 如果发生网络问题。
            RespNotOkException: 如果 API 返回错误状态码。
            RespParseException: 如果响应解析失败。
        """
        # 构建包含音频的内容
        contents = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "Generate a transcript of the speech. The language of the transcript should match the language of the speech."
                    },
                    {"inline_data": {"mime_type": "audio/wav", "data": audio_base64}},
                ],
            }
        ]

        request_data = {
            "contents": contents,
            "generationConfig": _build_generation_config(
                2048,
                0.1,
                thinking_budget=THINKING_BUDGET_AUTO,
                thinking_level=None,
                response_format=None,
                extra_params=extra_params
            ),
            "safetySettings": gemini_safe_settings,
        }

        try:
            endpoint = f"models/{model_info.model_identifier}:generateContent"
            response = await self._make_request("POST", endpoint, request_data)
            response_data = await response.json()

            api_response, usage_record = _default_normal_response_parser(response_data)

            if usage_record:
                api_response.usage = UsageRecord(
                    model_name=model_info.name,
                    provider_name=model_info.api_provider,
                    prompt_tokens=usage_record[0],
                    completion_tokens=usage_record[1],
                    total_tokens=usage_record[2],
                )

            return api_response

        except (NetworkConnectionError, RespNotOkException, RespParseException):
            raise
        except Exception as e:
            raise NetworkConnectionError() from e

    def get_support_image_formats(self) -> list[str]:
        """
        获取支持的图片格式
        """
        return ["png", "jpg", "jpeg", "webp", "heic", "heif"]

    # 移除 __aenter__、__aexit__、__del__，不再持有全局 session
