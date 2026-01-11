"""数据库优化模块：本地缓存管理
Database optimization module: Local cache management."""

from .backends import CacheBackend, CacheEntry, LocalCache
from .cache_manager import (
    CacheManager,
    create_local_cache_manager,
)

__all__ = [
    # 缓存后端 Cache backends
    "CacheBackend",
    "LocalCache",
    "CacheEntry",
    # 缓存管理器 Cache manager
    "CacheManager",
    "create_local_cache_manager",
]

