"""
Google Gemini 客户端实现

使用 aiohttp 实现的 Gemini API 客户端
"""

from typing import List, Dict, Any, Optional, AsyncIterator, TYPE_CHECKING, Union
import json

from .base_client import BaseLLMClient, ModelInfo, LLMResponse, StreamChunk, ModelCapability
from ..exceptions import (
    LLMError,
    AuthenticationError,
    RateLimitError,
    ModelNotFoundError,
    InvalidRequestError,
    APIConnectionError,
    ContextLengthExceededError
)

try:
    from ...logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# aiohttp 是可选的
try:
    import aiohttp  # type: ignore[import-not-found]
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False
    logger.warning("aiohttp package not available. Install with: pip install aiohttp")

if TYPE_CHECKING:
    from aiohttp import ClientSession  # type: ignore[import-not-found]


class GeminiClient(BaseLLMClient):
    """Google Gemini 客户端
    
    使用 aiohttp 实现的 Gemini API 客户端
    """
    
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs
    ):
        """初始化 Gemini 客户端
        
        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            **kwargs: 其他参数
        """
        if not AIOHTTP_AVAILABLE or aiohttp is None:
            raise ImportError(
                "aiohttp package is required for GeminiClient. "
                "Install with: pip install aiohttp"
            )
        
        super().__init__()
        
        self.api_key = api_key
        self.base_url = base_url or self.DEFAULT_BASE_URL
        assert aiohttp is not None
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        
        self.session: Optional["ClientSession"] = None
        logger.info(f"Gemini client initialized with base_url={self.base_url}")
    
    async def initialize(self) -> bool:
        """初始化客户端
        
        Returns:
            bool: 是否初始化成功
        """
        assert aiohttp is not None
        try:
            # 创建会话
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            assert self.session is not None
            
            # 测试连接 - 列出模型
            url = f"{self.base_url}/models?key={self.api_key}"
            async with self.session.get(url) as response:
                if response.status == 401:
                    raise AuthenticationError("Invalid API key")
                
                response.raise_for_status()
                data = await response.json()
                logger.debug(f"Gemini client initialized, {len(data.get('models', []))} models available")
            
            return True
            
        except aiohttp.ClientError as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    async def close(self):
        """关闭客户端"""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Gemini client closed")
    
    def _handle_error(self, status: int, message: str) -> LLMError:
        """处理错误
        
        Args:
            status: HTTP 状态码
            message: 错误消息
            
        Returns:
            LLMError: 转换后的错误
        """
        if status == 401:
            return AuthenticationError(f"Authentication failed: {message}")
        elif status == 429:
            return RateLimitError(f"Rate limit exceeded: {message}")
        elif status == 404:
            return ModelNotFoundError(f"Model not found: {message}")
        elif status == 400:
            if "context" in message.lower():
                return ContextLengthExceededError(f"Context length exceeded: {message}")
            else:
                return InvalidRequestError(f"Invalid request: {message}")
        elif status >= 500:
            return APIConnectionError(f"Server error: {message}")
        else:
            return LLMError(f"Gemini error: {message}")
    
    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """转换消息格式为 Gemini 格式
        
        Args:
            messages: OpenAI 风格的消息列表
            
        Returns:
            Dict: Gemini 格式的请求体
        """
        contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            # 处理系统消息
            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
                continue
            
            # 转换角色
            gemini_role = "user" if role in ["user", "function"] else "model"
            
            # 处理多模态内容
            if isinstance(content, list):
                parts = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append({"text": item.get("text", "")})
                    elif item.get("type") == "image_url":
                        # Gemini 支持内联数据
                        image_url = item.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:"):
                            # 提取 base64 数据
                            parts.append({"inline_data": self._parse_data_url(image_url)})
                        else:
                            # URL 图片
                            parts.append({"file_data": {"file_uri": image_url}})
                
                contents.append({"role": gemini_role, "parts": parts})
            else:
                # 纯文本
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })
        
        result: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            result["system_instruction"] = system_instruction
        
        return result
    
    def _parse_data_url(self, data_url: str) -> Dict[str, str]:
        """解析 data URL
        
        Args:
            data_url: data:image/jpeg;base64,xxx
            
        Returns:
            Dict: {"mime_type": "image/jpeg", "data": "xxx"}
        """
        if not data_url.startswith("data:"):
            return {}
        
        # 分割 data URL
        header, data = data_url.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        
        return {
            "mime_type": mime_type,
            "data": data
        }
    
    async def generate(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> LLMResponse:
        """生成文本
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            top_p: Top-p 采样
            stop: 停止序列
            **kwargs: 其他参数
            
        Returns:
            LLMResponse: 生成结果
        """
        if not self.session:
            await self.initialize()
        if not self.session:
            raise RuntimeError("Failed to initialize aiohttp session")
        assert aiohttp is not None
        assert self.session is not None
        
        try:
            # 转换消息格式
            request_body = self._convert_messages_to_gemini_format(messages)
            
            # 添加生成配置
            generation_config: Dict[str, Any] = {
                "temperature": temperature,
                "topP": top_p
            }
            
            if max_tokens:
                generation_config["maxOutputTokens"] = max_tokens
            
            if stop:
                generation_config["stopSequences"] = stop
            
            request_body["generationConfig"] = generation_config
            
            # 添加其他参数
            if "safety_settings" in kwargs:
                request_body["safetySettings"] = kwargs["safety_settings"]
            
            logger.debug(f"Generating with model {model}")
            
            # 调用 API
            url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
            
            async with self.session.post(url, json=request_body) as response:
                if response.status != 200:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    raise self._handle_error(response.status, error_msg)
                
                data = await response.json()
            
            # 解析响应
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMError("No candidates in response")
            
            candidate = candidates[0]
            content_parts = candidate.get("content", {}).get("parts", [])
            
            # 提取文本内容
            content = "".join(part.get("text", "") for part in content_parts)
            
            # 提取使用情况
            usage_metadata = data.get("usageMetadata", {})
            usage = {
                "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                "total_tokens": usage_metadata.get("totalTokenCount", 0)
            }
            
            result = LLMResponse(
                content=content,
                model=model,
                finish_reason=candidate.get("finishReason", "STOP"),
                usage=usage,
                raw_response=data
            )
            
            logger.debug(f"Generation completed: {result.usage}")
            return result
            
        except aiohttp.ClientError as e:
            logger.error(f"Generation failed: {e}")
            raise APIConnectionError(f"Connection failed: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            logger.error(f"Generation failed: {e}")
            raise LLMError(f"Gemini error: {e}") from e
    
    async def stream_generate(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """流式生成文本
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            top_p: Top-p 采样
            stop: 停止序列
            **kwargs: 其他参数
            
        Yields:
            StreamChunk: 生成的文本片段
        """
        if not self.session:
            await self.initialize()
        if not self.session:
            raise RuntimeError("Failed to initialize aiohttp session")
        assert aiohttp is not None
        assert self.session is not None
        
        try:
            # 转换消息格式
            request_body = self._convert_messages_to_gemini_format(messages)
            
            # 添加生成配置
            generation_config: Dict[str, Any] = {
                "temperature": temperature,
                "topP": top_p
            }
            
            if max_tokens:
                generation_config["maxOutputTokens"] = max_tokens
            
            if stop:
                generation_config["stopSequences"] = stop
            
            request_body["generationConfig"] = generation_config
            
            # 添加其他参数
            if "safety_settings" in kwargs:
                request_body["safetySettings"] = kwargs["safety_settings"]
            
            logger.debug(f"Streaming generation with model {model}")
            
            # 流式调用 API
            url = f"{self.base_url}/models/{model}:streamGenerateContent?key={self.api_key}"
            
            async with self.session.post(url, json=request_body) as response:
                if response.status != 200:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    raise self._handle_error(response.status, error_msg)
                
                # 逐行读取流式响应
                async for line in response.content:
                    if not line:
                        continue
                    
                    # 解析 JSON
                    try:
                        chunk_data = json.loads(line)
                        candidates = chunk_data.get("candidates", [])
                        
                        if not candidates:
                            continue
                        
                        candidate = candidates[0]
                        content_parts = candidate.get("content", {}).get("parts", [])
                        
                        # 提取文本内容
                        content = "".join(part.get("text", "") for part in content_parts)
                        
                        if content:
                            yield StreamChunk(
                                content=content,
                                model=model,
                                finish_reason=candidate.get("finishReason")
                            )
                    
                    except json.JSONDecodeError:
                        continue
            
            logger.debug("Streaming generation completed")
            
        except aiohttp.ClientError as e:
            logger.error(f"Streaming generation failed: {e}")
            raise APIConnectionError(f"Connection failed: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            logger.error(f"Streaming generation failed: {e}")
            raise LLMError(f"Gemini error: {e}") from e
    
    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto",
        **kwargs
    ) -> LLMResponse:
        """使用工具调用生成
        
        Args:
            messages: 消息列表
            tools: 工具列表
            model: 模型名称
            tool_choice: 工具选择策略
            **kwargs: 其他参数
            
        Returns:
            LLMResponse: 生成结果
        """
        if not self.session:
            await self.initialize()
        if not self.session:
            raise RuntimeError("Failed to initialize aiohttp session")
        assert aiohttp is not None
        assert self.session is not None
        
        try:
            # 转换消息格式
            request_body = self._convert_messages_to_gemini_format(messages)
            
            # 转换工具格式
            gemini_tools = []
            for tool in tools:
                if tool.get("type") == "function":
                    func = tool.get("function", {})
                    gemini_tools.append({
                        "function_declarations": [{
                            "name": func.get("name"),
                            "description": func.get("description"),
                            "parameters": func.get("parameters")
                        }]
                    })
            
            request_body["tools"] = gemini_tools
            
            logger.debug(f"Generating with tools, model {model}")
            
            # 调用 API
            url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
            
            async with self.session.post(url, json=request_body) as response:
                if response.status != 200:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    raise self._handle_error(response.status, error_msg)
                
                data = await response.json()
            
            # 解析响应
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMError("No candidates in response")
            
            candidate = candidates[0]
            content_parts = candidate.get("content", {}).get("parts", [])
            
            # 提取文本和函数调用
            content = ""
            tool_calls = []
            
            for part in content_parts:
                if "text" in part:
                    content += part["text"]
                elif "functionCall" in part:
                    func_call = part["functionCall"]
                    tool_calls.append({
                        "id": f"call_{len(tool_calls)}",
                        "type": "function",
                        "function": {
                            "name": func_call.get("name"),
                            "arguments": json.dumps(func_call.get("args", {}))
                        }
                    })
            
            # 提取使用情况
            usage_metadata = data.get("usageMetadata", {})
            usage = {
                "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                "total_tokens": usage_metadata.get("totalTokenCount", 0)
            }
            
            result = LLMResponse(
                content=content,
                model=model,
                finish_reason=candidate.get("finishReason", "STOP"),
                tool_calls=tool_calls if tool_calls else None,
                usage=usage,
                raw_response=data
            )
            
            logger.debug(f"Tool calling completed: {len(tool_calls)} calls")
            return result
            
        except aiohttp.ClientError as e:
            logger.error(f"Tool calling failed: {e}")
            raise APIConnectionError(f"Connection failed: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            logger.error(f"Tool calling failed: {e}")
            raise LLMError(f"Gemini error: {e}") from e
    
    async def create_embeddings(
        self,
        texts: List[str],
        model: str = "embedding-001",
        **kwargs
    ) -> List[List[float]]:
        """创建文本嵌入
        
        Args:
            texts: 文本列表
            model: 模型名称
            **kwargs: 其他参数
            
        Returns:
            List[List[float]]: 嵌入向量列表
        """
        if not self.session:
            await self.initialize()
        if not self.session:
            raise RuntimeError("Failed to initialize aiohttp session")
        assert aiohttp is not None
        assert self.session is not None
        
        try:
            logger.debug(f"Creating embeddings for {len(texts)} texts")
            
            embeddings = []
            
            # Gemini 嵌入 API 每次处理一个文本
            for text in texts:
                request_body = {
                    "content": {
                        "parts": [{"text": text}]
                    }
                }
                
                url = f"{self.base_url}/models/{model}:embedContent?key={self.api_key}"
                
                async with self.session.post(url, json=request_body) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        error_msg = error_data.get("error", {}).get("message", "Unknown error")
                        raise self._handle_error(response.status, error_msg)
                    
                    data = await response.json()
                    embedding = data.get("embedding", {}).get("values", [])
                    embeddings.append(embedding)
            
            logger.debug(f"Embeddings created: {len(embeddings)} vectors")
            return embeddings
            
        except aiohttp.ClientError as e:
            logger.error(f"Embeddings creation failed: {e}")
            raise APIConnectionError(f"Connection failed: {e}") from e
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            logger.error(f"Embeddings creation failed: {e}")
            raise LLMError(f"Gemini error: {e}") from e
    
    async def get_model_info(self, model: str) -> ModelInfo:
        """获取模型信息
        
        Args:
            model: 模型名称
            
        Returns:
            ModelInfo: 模型信息
        """
        if not self.session:
            await self.initialize()
        if not self.session:
            raise RuntimeError("Failed to initialize aiohttp session")
        assert aiohttp is not None
        assert self.session is not None
        
        try:
            url = f"{self.base_url}/models/{model}?key={self.api_key}"
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    # 返回默认信息
                    return self._get_default_model_info(model)
                
                data = await response.json()
            
            # 解析能力
            capabilities = {ModelCapability.CHAT}
            supported_methods = data.get("supportedGenerationMethods", [])
            
            if "generateContent" in supported_methods:
                capabilities.add(ModelCapability.CHAT)
            
            if "embedContent" in supported_methods:
                capabilities.add(ModelCapability.EMBEDDINGS)
            
            # Gemini Pro Vision 支持视觉
            if "vision" in model.lower():
                capabilities.add(ModelCapability.VISION)
            
            return ModelInfo(
                provider="gemini",
                model=model,
                capabilities=capabilities,
                context_window=data.get("inputTokenLimit", 32768),
                max_output_tokens=data.get("outputTokenLimit", 8192),
                supports_streaming=True,
                metadata=data
            )
            
        except Exception as e:
            logger.error(f"Failed to get model info: {e}")
            return self._get_default_model_info(model)
    
    def _get_default_model_info(self, model: str) -> ModelInfo:
        """获取默认模型信息"""
        capabilities = {ModelCapability.CHAT}
        
        if "vision" in model.lower():
            capabilities.add(ModelCapability.VISION)
        
        if "embedding" in model.lower():
            capabilities = {ModelCapability.EMBEDDINGS}
        
        return ModelInfo(
            provider="gemini",
            model=model,
            capabilities=capabilities,
            context_window=32768,
            max_output_tokens=8192,
            supports_streaming=True
        )