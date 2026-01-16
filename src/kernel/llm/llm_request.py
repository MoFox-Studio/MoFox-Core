"""
LLM 请求核心逻辑

提供统一的 LLM 交互接口，协调 client 和 payload
"""

from typing import List, Dict, Any, Optional, Union, AsyncIterator
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from .client_registry import create_client, ClientRegistry
from .model_client.base_client import BaseLLMClient, LLMResponse, StreamChunk
from .exceptions import (
    ModelNotFoundError,
    InvalidRequestError,
    ValidationError
)

try:
    from ..logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """LLM 请求配置"""
    
    # 基础配置
    model: str
    messages: List[Dict[str, Any]]
    provider: Optional[str] = None
    
    # 生成参数
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[Union[str, List[str]]] = None
    
    # 工具调用
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    
    # 高级选项
    stream: bool = False
    response_format: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    user: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "model": self.model,
            "messages": self.messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": self.stream
        }
        
        # 可选参数
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        
        if self.stop is not None:
            data["stop"] = self.stop
        
        if self.tools is not None:
            data["tools"] = self.tools
        
        if self.tool_choice is not None:
            data["tool_choice"] = self.tool_choice
        
        if self.response_format is not None:
            data["response_format"] = self.response_format
        
        if self.seed is not None:
            data["seed"] = self.seed
        
        if self.user is not None:
            data["user"] = self.user
        
        return data
    
    def validate(self) -> bool:
        """验证请求参数
        
        Returns:
            bool: 是否有效
            
        Raises:
            ValidationError: 参数无效
        """
        if not self.model:
            raise ValidationError("Model is required")
        
        if not self.messages:
            raise ValidationError("Messages cannot be empty")
        
        if self.temperature < 0 or self.temperature > 2:
            raise ValidationError("Temperature must be between 0 and 2")
        
        if self.top_p < 0 or self.top_p > 1:
            raise ValidationError("Top_p must be between 0 and 1")
        
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValidationError("Max_tokens must be positive")
        
        return True


class LLMRequestManager:
    """LLM 请求管理器
    
    提供统一的 LLM 交互接口
    """
    
    def __init__(self, registry: Optional[ClientRegistry] = None):
        """初始化请求管理器
        
        Args:
            registry: 客户端注册表（默认使用全局注册表）
        """
        self.registry = registry
        self._clients: Dict[str, BaseLLMClient] = {}
    
    async def _get_client(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> BaseLLMClient:
        """获取客户端实例
        
        Args:
            provider: 提供商名称
            model: 模型名称
            
        Returns:
            BaseLLMClient: 客户端实例
            
        Raises:
            ModelNotFoundError: 找不到合适的客户端
        """
        # 尝试从缓存获取
        cache_key = f"{provider}:{model}"
        if cache_key in self._clients:
            return self._clients[cache_key]
        
        # 创建新客户端
        try:
            if self.registry:
                client = await self.registry.create_client(provider, model=model)
            else:
                client = await create_client(provider, model=model)
            
            # 缓存客户端
            self._clients[cache_key] = client
            logger.debug(f"Created client for {provider}:{model}")
            
            return client
            
        except Exception as e:
            logger.error(f"Failed to get client: {e}")
            raise ModelNotFoundError(f"Cannot find client for {provider}:{model}") from e
    
    async def generate(
        self,
        request: LLMRequest,
        **kwargs
    ) -> LLMResponse:
        """生成文本
        
        Args:
            request: LLM 请求配置
            **kwargs: 额外参数
            
        Returns:
            LLMResponse: 生成结果
            
        Raises:
            LLMError: 生成失败
        """
        # 验证请求
        request.validate()
        
        # 获取客户端
        client = await self._get_client(request.provider, request.model)
        
        # 合并参数
        params = request.to_dict()
        params.update(kwargs)
        
        # 调用客户端
        try:
            logger.info(f"Generating with model {request.model}")
            response = await client.generate(**params)
            logger.debug(f"Generation completed: {response.usage}")
            
            return response
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
    
    async def stream_generate(
        self,
        request: LLMRequest,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """流式生成文本
        
        Args:
            request: LLM 请求配置
            **kwargs: 额外参数
            
        Yields:
            StreamChunk: 生成的文本片段
            
        Raises:
            LLMError: 生成失败
        """
        # 验证请求
        request.validate()
        
        # 强制启用流式模式
        request.stream = True
        
        # 获取客户端
        client = await self._get_client(request.provider, request.model)
        
        # 合并参数
        params = request.to_dict()
        params.update(kwargs)
        
        # 流式调用
        try:
            logger.info(f"Streaming generation with model {request.model}")
            
            async for chunk in client.stream_generate(**params):
                yield chunk
            
            logger.debug("Streaming generation completed")
            
        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            raise
    
    async def generate_with_tools(
        self,
        request: LLMRequest,
        **kwargs
    ) -> LLMResponse:
        """使用工具调用生成
        
        Args:
            request: LLM 请求配置（必须包含 tools）
            **kwargs: 额外参数
            
        Returns:
            LLMResponse: 生成结果
            
        Raises:
            InvalidRequestError: tools 未设置
            LLMError: 生成失败
        """
        if not request.tools:
            raise InvalidRequestError("Tools must be provided for tool calling")
        
        # 验证请求
        request.validate()
        
        # 获取客户端
        client = await self._get_client(request.provider, request.model)
        
        # 合并参数
        params = request.to_dict()
        params.update(kwargs)
        
        # 调用客户端
        try:
            logger.info(f"Generating with tools, model {request.model}")
            response = await client.generate_with_tools(**params)
            logger.debug("Tool calling completed")
            
            return response
            
        except Exception as e:
            logger.error(f"Tool calling failed: {e}")
            raise
    
    async def create_embeddings(
        self,
        texts: List[str],
        model: str,
        provider: Optional[str] = None,
        **kwargs
    ) -> List[List[float]]:
        """创建文本嵌入
        
        Args:
            texts: 文本列表
            model: 模型名称
            provider: 提供商名称
            **kwargs: 额外参数
            
        Returns:
            List[List[float]]: 嵌入向量列表
            
        Raises:
            LLMError: 创建失败
        """
        if not texts:
            raise InvalidRequestError("Texts cannot be empty")
        
        # 获取客户端
        client = await self._get_client(provider, model)
        
        # 调用客户端
        try:
            logger.info(f"Creating embeddings for {len(texts)} texts")
            embeddings = await client.create_embeddings(texts, model=model, **kwargs)
            logger.debug("Embeddings created")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Embeddings creation failed: {e}")
            raise
    
    async def close(self):
        """关闭所有客户端"""
        for client in self._clients.values():
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Failed to close client: {e}")
        
        self._clients.clear()
        logger.info("All clients closed")
    
    @asynccontextmanager
    async def with_client(self, provider: str, model: Optional[str] = None):
        """客户端上下文管理器
        
        Args:
            provider: 提供商名称
            model: 模型名称
            
        Yields:
            BaseLLMClient: 客户端实例
        """
        client = await self._get_client(provider, model)
        try:
            yield client
        finally:
            pass  # 客户端由管理器统一管理生命周期


# 全局请求管理器实例
_global_manager: Optional[LLMRequestManager] = None


def get_manager() -> LLMRequestManager:
    """获取全局请求管理器
    
    Returns:
        LLMRequestManager: 全局管理器实例
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = LLMRequestManager()
    return _global_manager


# 便捷函数
async def generate(
    model: str,
    messages: List[Dict[str, Any]],
    provider: Optional[str] = None,
    **kwargs
) -> LLMResponse:
    """生成文本（便捷函数）
    
    Args:
        model: 模型名称
        messages: 消息列表
        provider: 提供商名称
        **kwargs: 其他参数
        
    Returns:
        LLMResponse: 生成结果
    """
    request = LLMRequest(
        model=model,
        messages=messages,
        provider=provider,
        **kwargs
    )
    
    manager = get_manager()
    return await manager.generate(request)


async def stream_generate(
    model: str,
    messages: List[Dict[str, Any]],
    provider: Optional[str] = None,
    **kwargs
) -> AsyncIterator[StreamChunk]:
    """流式生成文本（便捷函数）
    
    Args:
        model: 模型名称
        messages: 消息列表
        provider: 提供商名称
        **kwargs: 其他参数
        
    Yields:
        StreamChunk: 生成的文本片段
    """
    request = LLMRequest(
        model=model,
        messages=messages,
        provider=provider,
        stream=True,
        **kwargs
    )
    
    manager = get_manager()
    async for chunk in manager.stream_generate(request):
        yield chunk


async def generate_with_tools(
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    provider: Optional[str] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    **kwargs
) -> LLMResponse:
    """使用工具调用生成（便捷函数）
    
    Args:
        model: 模型名称
        messages: 消息列表
        tools: 工具列表
        provider: 提供商名称
        tool_choice: 工具选择策略
        **kwargs: 其他参数
        
    Returns:
        LLMResponse: 生成结果
    """
    request = LLMRequest(
        model=model,
        messages=messages,
        provider=provider,
        tools=tools,
        tool_choice=tool_choice,
        **kwargs
    )
    
    manager = get_manager()
    return await manager.generate_with_tools(request)


async def create_embeddings(
    texts: List[str],
    model: str,
    provider: Optional[str] = None,
    **kwargs
) -> List[List[float]]:
    """创建文本嵌入（便捷函数）
    
    Args:
        texts: 文本列表
        model: 模型名称
        provider: 提供商名称
        **kwargs: 其他参数
        
    Returns:
        List[List[float]]: 嵌入向量列表
    """
    manager = get_manager()
    return await manager.create_embeddings(texts, model, provider, **kwargs)
