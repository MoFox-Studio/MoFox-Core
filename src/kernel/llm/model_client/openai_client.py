"""
OpenAI 客户端实现

支持 OpenAI API 和兼容 API（如 Azure OpenAI, DeepSeek 等）
"""

from typing import List, Dict, Any, Optional, AsyncIterator, Union

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

# OpenAI 库是可选的
try:
    from openai import AsyncOpenAI, OpenAIError, AuthenticationError as OpenAIAuthError
    from openai import RateLimitError as OpenAIRateLimitError
    from openai import APIConnectionError as OpenAIConnectionError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    # 为静态分析与类型检查提供占位符，避免未绑定名称的错误
    AsyncOpenAI = None  # type: ignore
    OpenAIError = Exception  # type: ignore
    OpenAIAuthError = Exception  # type: ignore
    OpenAIRateLimitError = Exception  # type: ignore
    OpenAIConnectionError = Exception  # type: ignore
    logger.warning("openai package not available. Install with: pip install openai")


class OpenAIClient(BaseLLMClient):
    """OpenAI 客户端
    
    支持 OpenAI API 和兼容的 API 接口
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs
    ):
        """初始化 OpenAI 客户端
        
        Args:
            api_key: API 密钥
            base_url: API 基础 URL（用于兼容 API）
            organization: 组织 ID
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            **kwargs: 其他参数
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package is required for OpenAIClient. "
                "Install with: pip install openai"
            )
        
        super().__init__()
        
        self.api_key = api_key
        self.base_url = base_url
        self.organization = organization
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 创建客户端
        client_kwargs = {
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": max_retries
        }
        
        if base_url:
            client_kwargs["base_url"] = base_url
        
        if organization:
            client_kwargs["organization"] = organization
        
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package is required for OpenAIClient. Install with: pip install openai"
            )
        # 仅在 OpenAI 可用时创建客户端，避免静态分析误报
        from typing import cast, Any
        self.client = cast(Any, AsyncOpenAI)(**client_kwargs)
        logger.info(f"OpenAI client initialized with base_url={base_url}")
    
    async def initialize(self) -> bool:
        """初始化客户端
        
        Returns:
            bool: 是否初始化成功
        """
        try:
            # 测试连接
            models = await self.client.models.list()
            logger.debug(f"OpenAI client initialized, {len(models.data)} models available")
            return True
            
        except OpenAIAuthError as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"OpenAI authentication failed: {e}") from e
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    async def close(self):
        """关闭客户端"""
        await self.client.close()
        logger.info("OpenAI client closed")
    
    def _handle_error(self, error: Exception) -> LLMError:
        """处理错误
        
        Args:
            error: 原始错误
            
        Returns:
            LLMError: 转换后的错误
        """
        if isinstance(error, OpenAIAuthError):
            return AuthenticationError(f"OpenAI authentication failed: {error}")
        elif isinstance(error, OpenAIRateLimitError):
            return RateLimitError(f"Rate limit exceeded: {error}")
        elif isinstance(error, OpenAIConnectionError):
            return APIConnectionError(f"Connection failed: {error}")
        elif "context_length_exceeded" in str(error):
            return ContextLengthExceededError(f"Context length exceeded: {error}")
        elif "model_not_found" in str(error):
            return ModelNotFoundError(f"Model not found: {error}")
        elif "invalid" in str(error).lower():
            return InvalidRequestError(f"Invalid request: {error}")
        else:
            return LLMError(f"OpenAI error: {error}")
    
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
            frequency_penalty: 频率惩罚
            presence_penalty: 存在惩罚
            stop: 停止序列
            **kwargs: 其他参数
            
        Returns:
            LLMResponse: 生成结果
        """
        try:
            # 准备参数
            # 从 kwargs 中提取可选的扩展采样参数，提供默认值
            frequency_penalty: float = kwargs.pop("frequency_penalty", 0.0)
            presence_penalty: float = kwargs.pop("presence_penalty", 0.0)

            params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty
            }
            
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            
            if stop:
                params["stop"] = stop
            
            # 添加其他参数
            params.update(kwargs)
            
            logger.debug(f"Generating with model {model}")
            
            # 调用 API
            response = await self.client.chat.completions.create(**params)
            
            # 转换响应
            choice = response.choices[0]
            result = LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                finish_reason=choice.finish_reason,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                raw_response=response.model_dump()
            )
            
            logger.debug(f"Generation completed: {result.usage}")
            return result
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise self._handle_error(e)
    
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
            frequency_penalty: 频率惩罚
            presence_penalty: 存在惩罚
            stop: 停止序列
            **kwargs: 其他参数
            
        Yields:
            StreamChunk: 生成的文本片段
        """
        try:
            # 准备参数
            # 从 kwargs 中提取可选的扩展采样参数，提供默认值
            frequency_penalty: float = kwargs.pop("frequency_penalty", 0.0)
            presence_penalty: float = kwargs.pop("presence_penalty", 0.0)

            params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
                "stream": True
            }
            
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            
            if stop:
                params["stop"] = stop
            
            # 添加其他参数
            params.update(kwargs)
            
            logger.debug(f"Streaming generation with model {model}")
            
            # 流式调用
            stream = await self.client.chat.completions.create(**params)
            
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    
                    # 提取内容
                    content = delta.content or ""
                    
                    # 提取工具调用
                    tool_calls = None
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        tool_calls = [tc.model_dump() for tc in delta.tool_calls]
                    
                    yield StreamChunk(
                        content=content,
                        model=chunk.model,
                        finish_reason=chunk.choices[0].finish_reason,
                        tool_calls=tool_calls
                    )
            
            logger.debug("Streaming generation completed")
            
        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            raise self._handle_error(e)
    
    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
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
        try:
            # 准备参数
            # OpenAI 默认为自动选择工具；与基类签名兼容
            resolved_tool_choice = "auto" if tool_choice is None else tool_choice

            params = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": resolved_tool_choice
            }
            
            # 添加其他参数
            params.update(kwargs)
            
            logger.debug(f"Generating with tools, model {model}")
            
            # 调用 API
            response = await self.client.chat.completions.create(**params)
            
            # 转换响应
            choice = response.choices[0]
            
            # 提取工具调用
            tool_calls = None
            if choice.message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in choice.message.tool_calls
                ]
            
            result = LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                finish_reason=choice.finish_reason,
                tool_calls=tool_calls,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                raw_response=response.model_dump()
            )
            
            logger.debug(f"Tool calling completed: {len(tool_calls or [])} calls")
            return result
            
        except Exception as e:
            logger.error(f"Tool calling failed: {e}")
            raise self._handle_error(e)
    
    async def create_embeddings(
        self,
        texts: List[str],
        model: str = "text-embedding-ada-002",
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
        try:
            logger.debug(f"Creating embeddings for {len(texts)} texts")
            
            # 调用 API
            response = await self.client.embeddings.create(
                model=model,
                input=texts,
                **kwargs
            )
            
            # 提取嵌入向量
            embeddings = [data.embedding for data in response.data]
            
            logger.debug(f"Embeddings created: {len(embeddings)} vectors")
            return embeddings
            
        except Exception as e:
            logger.error(f"Embeddings creation failed: {e}")
            raise self._handle_error(e)
    
    async def get_model_info(self, model: str) -> ModelInfo:
        """获取模型信息
        
        Args:
            model: 模型名称
            
        Returns:
            ModelInfo: 模型信息
        """
        try:
            # 调用 API
            model_data = await self.client.models.retrieve(model)
            
            # 推断能力
            capabilities = {ModelCapability.CHAT}
            if "gpt-4" in model or "gpt-3.5" in model:
                capabilities.add(ModelCapability.FUNCTION_CALLING)
            
            if "vision" in model:
                capabilities.add(ModelCapability.VISION)
            
            return ModelInfo(
                provider="openai",
                model=model_data.id,
                capabilities=capabilities,
                context_window=self._get_context_window(model),
                max_output_tokens=self._get_max_output_tokens(model),
                supports_streaming=True,
                metadata=model_data.model_dump()
            )
            
        except Exception as e:
            logger.error(f"Failed to get model info: {e}")
            # 返回默认信息
            return ModelInfo(
                provider="openai",
                model=model,
                capabilities={ModelCapability.CHAT},
                context_window=4096,
                max_output_tokens=2048,
                supports_streaming=True
            )
    
    def _get_context_window(self, model: str) -> int:
        """获取上下文窗口大小"""
        context_windows = {
            "gpt-4-turbo": 128000,
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-3.5-turbo": 16384,
            "gpt-3.5-turbo-16k": 16384
        }
        
        for key, value in context_windows.items():
            if key in model:
                return value
        
        return 4096  # 默认值
    
    def _get_max_output_tokens(self, model: str) -> int:
        """获取最大输出 token 数"""
        # 通常是上下文窗口的一部分
        return self._get_context_window(model) // 2
