"""缓存后端抽象接口
Cache backend abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheBackend(ABC):
    """缓存后端抽象基类
    Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """从缓存中获取值
        Get value from cache by key.
        
        参数 Args:
            key: 缓存键 / Cache key
            
        返回 Returns:
            缓存的值，如果不存在则返回 None / Cached value or None if not found
        """
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值
        Set value in cache.
        
        参数 Args:
            key: 缓存键 / Cache key
            value: 要缓存的值 / Value to cache
            ttl: 过期时间（秒），None 表示永不过期 / Time to live in seconds, None means no expiration
            
        返回 Returns:
            是否设置成功 / True if successful
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存键
        Delete cache key.
        
        参数 Args:
            key: 缓存键 / Cache key
            
        返回 Returns:
            是否删除成功 / True if successful
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查键是否存在
        Check if key exists.
        
        参数 Args:
            key: 缓存键 / Cache key
            
        返回 Returns:
            键是否存在 / True if key exists
        """
        pass

    @abstractmethod
    def clear(self) -> bool:
        """清空所有缓存
        Clear all cache entries.
        
        返回 Returns:
            是否清空成功 / True if successful
        """
        pass

    @abstractmethod
    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """批量获取多个键的值
        Get multiple values by keys.
        
        参数 Args:
            keys: 缓存键列表 / List of cache keys
            
        返回 Returns:
            键值对字典 / Dictionary of key-value pairs
        """
        pass

    @abstractmethod
    def set_many(self, mapping: dict[str, Any], ttl: Optional[int] = None) -> bool:
        """批量设置多个键值对
        Set multiple key-value pairs.
        
        参数 Args:
            mapping: 键值对字典 / Dictionary of key-value pairs
            ttl: 过期时间（秒）/ Time to live in seconds
            
        返回 Returns:
            是否设置成功 / True if successful
        """
        pass

    @abstractmethod
    def delete_many(self, keys: list[str]) -> int:
        """批量删除多个键
        Delete multiple keys.
        
        参数 Args:
            keys: 缓存键列表 / List of cache keys
            
        返回 Returns:
            删除的键数量 / Number of keys deleted
        """
        pass

    @abstractmethod
    def increment(self, key: str, delta: int = 1) -> int:
        """递增计数器
        Increment counter.
        
        参数 Args:
            key: 缓存键 / Cache key
            delta: 递增值 / Increment delta
            
        返回 Returns:
            递增后的值 / Value after increment
        """
        pass

    @abstractmethod
    def decrement(self, key: str, delta: int = 1) -> int:
        """递减计数器
        Decrement counter.
        
        参数 Args:
            key: 缓存键 / Cache key
            delta: 递减值 / Decrement delta
            
        返回 Returns:
            递减后的值 / Value after decrement
        """
        pass


__all__ = ["CacheBackend"]
