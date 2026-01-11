"""缓存管理器：统一的缓存管理接口
Cache Manager: Unified cache management interface."""

from __future__ import annotations

import functools
import hashlib
import json
from typing import Any, Callable, Optional

from .backends import CacheBackend, LocalCache


class CacheManager:
    """缓存管理器：支持多后端缓存策略
    Cache Manager: Supports multi-backend caching strategies."""
    
    def __init__(
        self,
        backend: Optional[CacheBackend] = None,
        default_ttl: int = 3600,
        key_prefix: str = ""
    ):
        """初始化缓存管理器
        Initialize cache manager.
        
        参数 Args:
            backend: 缓存后端实例，默认使用本地缓存 / Cache backend instance, defaults to LocalCache
            default_ttl: 默认过期时间（秒）/ Default TTL in seconds
            key_prefix: 全局键前缀 / Global key prefix
        """
        self._backend = backend or LocalCache(default_ttl=default_ttl)
        self._default_ttl = default_ttl
        self._key_prefix = key_prefix
    
    def _make_key(self, key: str) -> str:
        """生成完整的缓存键
        Generate full cache key."""
        if self._key_prefix:
            return f"{self._key_prefix}:{key}"
        return key
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值
        Get cached value.
        
        参数 Args:
            key: 缓存键 / Cache key
            default: 默认值 / Default value if key not found
            
        返回 Returns:
            缓存的值或默认值 / Cached value or default
        """
        full_key = self._make_key(key)
        value = self._backend.get(full_key)
        return value if value is not None else default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值
        Set cache value.
        
        参数 Args:
            key: 缓存键 / Cache key
            value: 缓存值 / Cache value
            ttl: 过期时间（秒），None 使用默认值 / TTL in seconds, None uses default
            
        返回 Returns:
            是否设置成功 / True if successful
        """
        full_key = self._make_key(key)
        if ttl is None:
            ttl = self._default_ttl
        return self._backend.set(full_key, value, ttl)
    
    def delete(self, key: str) -> bool:
        """删除缓存键
        Delete cache key.
        
        参数 Args:
            key: 缓存键 / Cache key
            
        返回 Returns:
            是否删除成功 / True if successful
        """
        full_key = self._make_key(key)
        return self._backend.delete(full_key)
    
    def exists(self, key: str) -> bool:
        """检查键是否存在
        Check if key exists.
        
        参数 Args:
            key: 缓存键 / Cache key
            
        返回 Returns:
            键是否存在 / True if key exists
        """
        full_key = self._make_key(key)
        return self._backend.exists(full_key)
    
    def clear(self) -> bool:
        """清空所有缓存
        Clear all cache entries.
        
        返回 Returns:
            是否清空成功 / True if successful
        """
        return self._backend.clear()
    
    def get_or_set(
        self,
        key: str,
        default_factory: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """获取缓存值，如果不存在则调用工厂函数设置
        Get cached value or set it using factory function.
        
        参数 Args:
            key: 缓存键 / Cache key
            default_factory: 值工厂函数 / Factory function to generate value
            ttl: 过期时间（秒）/ TTL in seconds
            
        返回 Returns:
            缓存的值 / Cached value
        """
        value = self.get(key)
        if value is None:
            value = default_factory()
            self.set(key, value, ttl)
        return value
    
    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """批量获取多个键的值
        Get multiple values by keys.
        
        参数 Args:
            keys: 缓存键列表 / List of cache keys
            
        返回 Returns:
            键值对字典 / Dictionary of key-value pairs
        """
        full_keys = [self._make_key(key) for key in keys]
        result = self._backend.get_many(full_keys)
        
        # 移除前缀返回原始键 / Remove prefix and return original keys
        if self._key_prefix:
            prefix_len = len(self._key_prefix) + 1
            return {k[prefix_len:]: v for k, v in result.items()}
        return result
    
    def set_many(self, mapping: dict[str, Any], ttl: Optional[int] = None) -> bool:
        """批量设置多个键值对
        Set multiple key-value pairs.
        
        参数 Args:
            mapping: 键值对字典 / Dictionary of key-value pairs
            ttl: 过期时间（秒）/ TTL in seconds
            
        返回 Returns:
            是否设置成功 / True if successful
        """
        full_mapping = {self._make_key(k): v for k, v in mapping.items()}
        if ttl is None:
            ttl = self._default_ttl
        return self._backend.set_many(full_mapping, ttl)
    
    def delete_many(self, keys: list[str]) -> int:
        """批量删除多个键
        Delete multiple keys.
        
        参数 Args:
            keys: 缓存键列表 / List of cache keys
            
        返回 Returns:
            删除的键数量 / Number of keys deleted
        """
        full_keys = [self._make_key(key) for key in keys]
        return self._backend.delete_many(full_keys)
    
    def increment(self, key: str, delta: int = 1) -> int:
        """递增计数器
        Increment counter.
        
        参数 Args:
            key: 缓存键 / Cache key
            delta: 递增值 / Increment delta
            
        返回 Returns:
            递增后的值 / Value after increment
        """
        full_key = self._make_key(key)
        return self._backend.increment(full_key, delta)
    
    def decrement(self, key: str, delta: int = 1) -> int:
        """递减计数器
        Decrement counter.
        
        参数 Args:
            key: 缓存键 / Cache key
            delta: 递减值 / Decrement delta
            
        返回 Returns:
            递减后的值 / Value after decrement
        """
        full_key = self._make_key(key)
        return self._backend.decrement(full_key, delta)
    
    def cached(
        self,
        ttl: Optional[int] = None,
        key_builder: Optional[Callable[..., str]] = None
    ):
        """缓存装饰器：自动缓存函数结果
        Cache decorator: Automatically cache function results.
        
        参数 Args:
            ttl: 过期时间（秒）/ TTL in seconds
            key_builder: 自定义键生成函数 / Custom key builder function
            
        返回 Returns:
            装饰器函数 / Decorator function
            
        示例 Example:
            ```python
            @cache_manager.cached(ttl=300)
            def expensive_function(arg1, arg2):
                # 耗时操作 / Expensive operation
                return result
            ```
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # 生成缓存键 / Generate cache key
                if key_builder:
                    cache_key = key_builder(*args, **kwargs)
                else:
                    cache_key = self._generate_cache_key(func, args, kwargs)
                
                # 尝试从缓存获取 / Try to get from cache
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value
                
                # 调用原函数并缓存结果 / Call original function and cache result
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result
            
            return wrapper
        return decorator
    
    def _generate_cache_key(self, func: Callable, args: tuple, kwargs: dict) -> str:
        """生成函数调用的缓存键
        Generate cache key for function call.
        
        参数 Args:
            func: 函数对象 / Function object
            args: 位置参数 / Positional arguments
            kwargs: 关键字参数 / Keyword arguments
            
        返回 Returns:
            缓存键 / Cache key
        """
        # 构建键组件 / Build key components
        func_name = f"{func.__module__}.{func.__qualname__}"
        
        # 序列化参数 / Serialize arguments
        try:
            args_str = json.dumps(args, sort_keys=True)
            kwargs_str = json.dumps(kwargs, sort_keys=True)
        except (TypeError, ValueError):
            # 如果无法序列化，使用字符串表示 / Use string representation if can't serialize
            args_str = str(args)
            kwargs_str = str(kwargs)
        
        # 生成哈希键 / Generate hash key
        key_data = f"{func_name}:{args_str}:{kwargs_str}"
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        
        return f"func:{func_name}:{key_hash}"
    
    @property
    def backend(self) -> CacheBackend:
        """获取底层缓存后端
        Get underlying cache backend."""
        return self._backend


def create_local_cache_manager(
    max_size: int = 1000,
    default_ttl: int = 3600,
    key_prefix: str = ""
) -> CacheManager:
    """创建本地缓存管理器
    Create local cache manager.
    
    参数 Args:
        max_size: 最大缓存条目数 / Maximum number of cache entries
        default_ttl: 默认过期时间（秒）/ Default TTL in seconds
        key_prefix: 键前缀 / Key prefix
        
    返回 Returns:
        缓存管理器实例 / Cache manager instance
    """
    backend = LocalCache(max_size=max_size, default_ttl=default_ttl)
    return CacheManager(backend=backend, default_ttl=default_ttl, key_prefix=key_prefix)





__all__ = [
    "CacheManager",
    "create_local_cache_manager",
]
