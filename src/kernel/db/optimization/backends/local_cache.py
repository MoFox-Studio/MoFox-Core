"""本地内存缓存实现
Local in-memory cache implementation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional

from .cache_backend import CacheBackend


@dataclass
class CacheEntry:
    """缓存条目
    Cache entry with value and expiration."""
    
    value: Any
    expires_at: Optional[float] = None  # Unix 时间戳 / Unix timestamp
    
    def is_expired(self) -> bool:
        """检查是否已过期
        Check if entry is expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class LocalCache(CacheBackend):
    """本地内存缓存实现（线程安全）
    Local in-memory cache implementation (thread-safe)."""
    
    def __init__(self, max_size: int = 1000, default_ttl: Optional[int] = 3600):
        """初始化本地缓存
        Initialize local cache.
        
        参数 Args:
            max_size: 最大缓存条目数 / Maximum number of cache entries
            default_ttl: 默认过期时间（秒）/ Default TTL in seconds
        """
        self._cache: dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._access_order: list[str] = []  # LRU 顺序 / LRU order
    
    def get(self, key: str) -> Optional[Any]:
        """从缓存中获取值
        Get value from cache by key."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            if entry.is_expired():
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return None
            
            # 更新 LRU 顺序 / Update LRU order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值
        Set value in cache."""
        with self._lock:
            # 计算过期时间 / Calculate expiration time
            if ttl is None:
                ttl = self._default_ttl
            
            expires_at = None
            if ttl is not None and ttl > 0:
                expires_at = time.time() + ttl
            
            # 如果缓存已满，移除最少使用的条目 / If cache is full, remove LRU entry
            if key not in self._cache and len(self._cache) >= self._max_size:
                if self._access_order:
                    lru_key = self._access_order.pop(0)
                    del self._cache[lru_key]
            
            # 设置缓存条目 / Set cache entry
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            
            # 更新访问顺序 / Update access order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            return True
    
    def delete(self, key: str) -> bool:
        """删除缓存键
        Delete cache key."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在
        Check if key exists."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            
            if entry.is_expired():
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return False
            
            return True
    
    def clear(self) -> bool:
        """清空所有缓存
        Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            return True
    
    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """批量获取多个键的值
        Get multiple values by keys."""
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    def set_many(self, mapping: dict[str, Any], ttl: Optional[int] = None) -> bool:
        """批量设置多个键值对
        Set multiple key-value pairs."""
        for key, value in mapping.items():
            self.set(key, value, ttl)
        return True
    
    def delete_many(self, keys: list[str]) -> int:
        """批量删除多个键
        Delete multiple keys."""
        count = 0
        for key in keys:
            if self.delete(key):
                count += 1
        return count
    
    def increment(self, key: str, delta: int = 1) -> int:
        """递增计数器
        Increment counter."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None or entry.is_expired():
                new_value = delta
            else:
                current_value = entry.value
                if not isinstance(current_value, int):
                    raise ValueError(f"Value for key '{key}' is not an integer")
                new_value = current_value + delta
            
            self.set(key, new_value)
            return new_value
    
    def decrement(self, key: str, delta: int = 1) -> int:
        """递减计数器
        Decrement counter."""
        return self.increment(key, -delta)
    
    def cleanup_expired(self) -> int:
        """清理过期条目
        Clean up expired entries.
        
        返回 Returns:
            清理的条目数 / Number of entries cleaned up
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
            
            return len(expired_keys)
    
    def size(self) -> int:
        """获取当前缓存大小
        Get current cache size."""
        with self._lock:
            return len(self._cache)


__all__ = ["LocalCache", "CacheEntry"]
