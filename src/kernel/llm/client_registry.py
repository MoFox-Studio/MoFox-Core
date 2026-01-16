"""
LLM Client 注册管理器

管理和注册不同的 LLM 客户端实现
"""

from typing import Dict, Type, Optional, Any, List
from kernel.logger import get_logger
from .model_client.base_client import BaseLLMClient


class ClientRegistry:
    """LLM客户端注册管理器
    
    提供客户端的注册、获取、管理功能
    """
    
    def __init__(self):
        """初始化注册器"""
        self._clients: Dict[str, Type[BaseLLMClient]] = {}
        self._instances: Dict[str, BaseLLMClient] = {}
        self.logger = get_logger(__name__)
    
    def register(
        self,
        name: str,
        client_class: Type[BaseLLMClient],
        override: bool = False
    ) -> None:
        """注册LLM客户端类
        
        Args:
            name: 客户端名称（如 'openai', 'gemini', 'bedrock'）
            client_class: 客户端类（必须继承BaseLLMClient）
            override: 是否覆盖已存在的注册
            
        Raises:
            TypeError: 如果client_class不是BaseLLMClient的子类
            ValueError: 如果名称已存在且override=False
        """
        # 验证类型
        if not issubclass(client_class, BaseLLMClient):
            self.logger.error(
                f"注册失败: {client_class.__name__} 不是 BaseLLMClient 的子类"
            )
            raise TypeError(
                f"client_class must be a subclass of BaseLLMClient, "
                f"got {client_class.__name__}"
            )
        
        # 检查是否已存在
        if name in self._clients and not override:
            self.logger.warning(f"客户端 '{name}' 已注册，使用 override=True 覆盖")
            raise ValueError(
                f"Client '{name}' is already registered. "
                f"Use override=True to replace it."
            )
        
        # 注册
        self._clients[name] = client_class
        self.logger.info(f"注册LLM客户端: {name} -> {client_class.__name__}")
    
    def unregister(self, name: str) -> None:
        """注销客户端
        
        Args:
            name: 客户端名称
            
        Raises:
            KeyError: 如果客户端不存在
        """
        if name not in self._clients:
            raise KeyError(f"Client '{name}' is not registered")
        
        # 如果有实例，先关闭
        if name in self._instances:
            import asyncio
            try:
                asyncio.create_task(self._instances[name].close())
            except:
                pass
            del self._instances[name]
        
        del self._clients[name]
        self.logger.info(f"注销LLM客户端: {name}")
    
    def get_client_class(self, name: str) -> Type[BaseLLMClient]:
        """获取客户端类
        
        Args:
            name: 客户端名称
            
        Returns:
            Type[BaseLLMClient]: 客户端类
            
        Raises:
            KeyError: 如果客户端未注册
        """
        if name not in self._clients:
            available = ', '.join(self.list_clients())
            self.logger.error(
                f"客户端 '{name}' 未注册，可用客户端: {available}"
            )
            raise KeyError(
                f"Client '{name}' is not registered. "
                f"Available clients: {available}"
            )
        
        return self._clients[name]
    
    def create_client(
        self,
        name: str,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        cache: bool = True
    ) -> BaseLLMClient:
        """创建客户端实例
        
        Args:
            name: 客户端名称
            api_key: API密钥
            config: 客户端配置
            cache: 是否缓存实例（相同配置复用实例）
            
        Returns:
            BaseLLMClient: 客户端实例
            
        Raises:
            KeyError: 如果客户端未注册
        """
        # 如果启用缓存且实例已存在
        if cache and name in self._instances:
            self.logger.debug(f"复用缓存的客户端实例: {name}")
            return self._instances[name]
        
        # 获取客户端类
        client_class = self.get_client_class(name)
        
        # 创建实例
        self.logger.info(f"创建LLM客户端实例: {name}")
        instance = client_class(api_key=api_key, config=config)
        
        # 缓存实例
        if cache:
            self._instances[name] = instance
        
        return instance
    
    async def create_client_async(
        self,
        name: str,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        cache: bool = True
    ) -> BaseLLMClient:
        """异步创建并初始化客户端实例
        
        Args:
            name: 客户端名称
            api_key: API密钥
            config: 客户端配置
            cache: 是否缓存实例
            
        Returns:
            BaseLLMClient: 已初始化的客户端实例
            
        Raises:
            KeyError: 如果客户端未注册
            ConnectionError: 如果初始化失败
        """
        # 创建实例
        client = self.create_client(name, api_key, config, cache)
        
        # 如果未初始化，则初始化
        if not client._initialized:
            self.logger.info(f"初始化LLM客户端: {name}")
            await client.initialize()
            client._initialized = True
        
        return client
    
    def is_registered(self, name: str) -> bool:
        """检查客户端是否已注册
        
        Args:
            name: 客户端名称
            
        Returns:
            bool: 是否已注册
        """
        return name in self._clients
    
    def list_clients(self) -> List[str]:
        """列出所有已注册的客户端名称
        
        Returns:
            List[str]: 客户端名称列表
        """
        return list(self._clients.keys())
    
    def get_client_info(self, name: str) -> Dict[str, Any]:
        """获取客户端信息
        
        Args:
            name: 客户端名称
            
        Returns:
            Dict[str, Any]: 客户端信息
            
        Raises:
            KeyError: 如果客户端未注册
        """
        client_class = self.get_client_class(name)
        
        return {
            'name': name,
            'class': client_class.__name__,
            'module': client_class.__module__,
            'has_instance': name in self._instances,
            'doc': client_class.__doc__
        }
    
    async def close_all(self) -> None:
        """关闭所有缓存的客户端实例"""
        self.logger.info(f"关闭所有LLM客户端实例，共 {len(self._instances)} 个")
        
        for name, client in self._instances.items():
            try:
                await client.close()
                self.logger.debug(f"关闭客户端实例: {name}")
            except Exception as e:
                self.logger.error(f"关闭客户端 '{name}' 失败: {e}")
        
        self._instances.clear()
    
    def clear_cache(self, name: Optional[str] = None) -> None:
        """清除缓存的客户端实例
        
        Args:
            name: 客户端名称，如果为None则清除所有
        """
        if name:
            if name in self._instances:
                del self._instances[name]
                self.logger.debug(f"清除客户端缓存: {name}")
        else:
            self._instances.clear()
            self.logger.debug("清除所有客户端缓存")
    
    def __repr__(self) -> str:
        return (
            f"ClientRegistry("
            f"registered={len(self._clients)}, "
            f"instances={len(self._instances)})"
        )


# 全局单例注册器
_global_registry: Optional[ClientRegistry] = None


def get_registry() -> ClientRegistry:
    """获取全局客户端注册器（单例模式）
    
    Returns:
        ClientRegistry: 全局注册器实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ClientRegistry()
    return _global_registry


def register_client(
    name: str,
    client_class: Type[BaseLLMClient],
    override: bool = False
) -> None:
    """注册LLM客户端到全局注册器
    
    这是register_client_to_registry的便捷包装函数
    
    Args:
        name: 客户端名称
        client_class: 客户端类
        override: 是否覆盖已存在的注册
        
    Examples:
        >>> from kernel.llm import register_client
        >>> from kernel.llm.model_client import OpenAIClient
        >>> 
        >>> register_client('openai', OpenAIClient)
    """
    registry = get_registry()
    registry.register(name, client_class, override)


def unregister_client(name: str) -> None:
    """从全局注册器注销客户端并清理缓存实例"""
    registry = get_registry()
    registry.unregister(name)


def create_client(
    name: str,
    api_key: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    cache: bool = True
) -> BaseLLMClient:
    """从全局注册器创建客户端实例
    
    Args:
        name: 客户端名称
        api_key: API密钥
        config: 客户端配置
        cache: 是否缓存实例
        
    Returns:
        BaseLLMClient: 客户端实例
        
    Examples:
        >>> client = create_client('openai', api_key='sk-...')
        >>> await client.initialize()
    """
    registry = get_registry()
    return registry.create_client(name, api_key, config, cache)


def get_client(
    name: str,
    api_key: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    cache: bool = True
) -> BaseLLMClient:
    """与 create_client 等价，保持向后兼容接口"""
    return create_client(name, api_key, config, cache)


async def create_client_async(
    name: str,
    api_key: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    cache: bool = True
) -> BaseLLMClient:
    """异步创建并初始化客户端实例
    
    Args:
        name: 客户端名称
        api_key: API密钥
        config: 客户端配置
        cache: 是否缓存实例
        
    Returns:
        BaseLLMClient: 已初始化的客户端实例
        
    Examples:
        >>> client = await create_client_async('openai', api_key='sk-...')
        >>> # 客户端已初始化，可以直接使用
        >>> response = await client.generate(...)
    """
    registry = get_registry()
    return await registry.create_client_async(name, api_key, config, cache)


def list_clients() -> List[str]:
    """列出所有已注册的客户端
    
    Returns:
        List[str]: 客户端名称列表
    """
    registry = get_registry()
    return registry.list_clients()
