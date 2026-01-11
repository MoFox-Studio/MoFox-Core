"""
LLM Client 抽象基类

定义所有 LLM 客户端必须实现的接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, AsyncIterator, Union, Set
from dataclasses import dataclass
from enum import Enum


class ModelCapability(Enum):
    """模型能力枚举"""
    TEXT_GENERATION = "text_generation"
    CHAT = "chat"
    VISION = "vision"
    FUNCTION_CALLING = "function_calling"
    STREAMING = "streaming"
    JSON_MODE = "json_mode"
    EMBEDDINGS = "embeddings"


@dataclass
class ModelInfo:
    """模型信息"""
    provider: str  # 提供商：openai, gemini, bedrock等
    model: str  # 模型名称/ID
    capabilities: Set[ModelCapability]  # 支持的能力
    context_window: int  # 上下文窗口大小
    max_output_tokens: Optional[int] = None  # 最大输出token数
    supports_system_message: bool = True  # 是否支持system消息
    supports_streaming: bool = False  # 是否支持流式输出
    metadata: Optional[Dict[str, Any]] = None  # 其他元数据

    def __post_init__(self) -> None:
        # 兼容传入 list 的情况，内部统一为 set 便于包含判断
        if not isinstance(self.capabilities, set):
            self.capabilities = set(self.capabilities)


@dataclass
class LLMResponse:
    """LLM响应数据类"""
    content: str  # 响应内容
    model: str  # 使用的模型
    finish_reason: Optional[str] = None  # 结束原因
    usage: Optional[Dict[str, int]] = None  # token使用情况
    function_call: Optional[Dict[str, Any]] = None  # 函数调用
    tool_calls: Optional[List[Dict[str, Any]]] = None  # 工具调用
    metadata: Optional[Dict[str, Any]] = None  # 其他元数据
    raw_response: Optional[Any] = None  # 原始响应数据


@dataclass
class StreamChunk:
    """流式响应数据块"""
    delta: Optional[str] = None  # 增量内容（可选）
    content: Optional[str] = None  # 完整内容片段（部分模型返回）
    model: Optional[str] = None  # 模型名称
    finish_reason: Optional[str] = None  # 结束原因
    tool_calls: Optional[List[Dict[str, Any]]] = None  # 工具调用增量
    metadata: Optional[Dict[str, Any]] = None  # 元数据


class BaseLLMClient(ABC):
    """LLM客户端抽象基类
    
    所有LLM客户端实现必须继承此类并实现所有抽象方法
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化客户端
        
        Args:
            api_key: API密钥
            config: 客户端配置
        """
        self.api_key = api_key
        self.config = config or {}
        self._initialized = False
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化客户端连接和资源
        
        Raises:
            ConnectionError: 连接失败时抛出
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭客户端，释放资源"""
        pass
    
    @abstractmethod
    async def get_model_info(self, model: str) -> ModelInfo:
        """获取模型信息
        
        Args:
            model: 模型名称
            
        Returns:
            ModelInfo: 模型信息
            
        Raises:
            ValueError: 模型不支持时抛出
        """
        pass
    
    @abstractmethod
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
        """生成文本（非流式）
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            top_p: top_p采样
            stop: 停止词列表
            **kwargs: 其他模型特定参数
            
        Returns:
            LLMResponse: LLM响应
            
        Raises:
            ValueError: 参数错误
            RuntimeError: 生成失败
        """
        pass
    
    @abstractmethod
    def stream_generate(
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
            max_tokens: 最大token数
            top_p: top_p采样
            stop: 停止词列表
            **kwargs: 其他模型特定参数
            
        Yields:
            StreamChunk: 流式响应数据块
            
        Raises:
            ValueError: 参数错误
            RuntimeError: 生成失败
        """
        pass
    
    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """使用工具生成（函数调用）
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            model: 模型名称
            tool_choice: 工具选择策略
            **kwargs: 其他参数
            
        Returns:
            LLMResponse: LLM响应
            
        Raises:
            NotImplementedError: 如果模型不支持工具调用
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support tool calling"
        )
    
    async def create_embeddings(
        self,
        texts: List[str],
        model: str,
        **kwargs
    ) -> List[List[float]]:
        """创建文本嵌入
        
        Args:
            texts: 文本或文本列表
            model: 嵌入模型名称
            **kwargs: 其他参数
            
        Returns:
            List[List[float]]: 嵌入向量列表
            
        Raises:
            NotImplementedError: 如果模型不支持嵌入
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support embeddings"
        )
    
    async def supports_capability(
        self,
        model: str,
        capability: ModelCapability
    ) -> bool:
        """检查模型是否支持某项能力
        
        Args:
            model: 模型名称
            capability: 能力枚举
            
        Returns:
            bool: 是否支持
        """
        try:
            model_info = await self.get_model_info(model)
            return capability in set(model_info.capabilities)
        except ValueError:
            return False
    
    async def health_check(self) -> bool:
        """健康检查
        
        Returns:
            bool: 客户端是否正常工作
        """
        try:
            # 默认实现：尝试简单的生成
            response = await self.generate(
                messages=[{"role": "user", "content": "test"}],
                model=self._get_default_model(),
                max_tokens=5
            )
            return bool(response.content)
        except Exception:
            return False
    
    @abstractmethod
    def _get_default_model(self) -> str:
        """获取默认模型名称"""
        pass
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(config={self.config})"
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
