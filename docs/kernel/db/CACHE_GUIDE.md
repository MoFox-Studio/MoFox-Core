# SQLite 数据库缓存指南

## 概述

本指南介绍如何在 SQLite 数据库系统中实现和使用缓存策略，提高应用性能。缓存主要针对频繁访问的数据，如用户信息、配置、LLM 响应等。

---

## 为什么需要缓存？

| 场景 | 问题 | 缓存方案 |
|------|------|--------|
| 频繁查询相同数据 | 数据库 I/O 压力大 | 内存缓存热点数据 |
| LLM API 调用 | 成本高、延迟长 | 缓存 LLM 响应结果 |
| 配置数据 | 改动不频繁 | 启动时加载到内存 |
| 用户会话 | 频繁校验 | 快速内存访问 |

---

## 缓存策略

### 策略 1：查询结果缓存

```python
from functools import lru_cache

class UserRepository:
    def __init__(self, repo):
        self.repo = repo
        self._cache = {}
    
    def get_user(self, session, user_id):
        # 检查缓存
        cache_key = f"user:{user_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 查询数据库
        user = self.repo.get(session, User, user_id)
        
        # 存储到缓存
        if user:
            self._cache[cache_key] = user
        
        return user
    
    def invalidate_cache(self, user_id):
        """清除用户缓存"""
        cache_key = f"user:{user_id}"
        if cache_key in self._cache:
            del self._cache[cache_key]
```

### 策略 2：LRU 缓存

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_user_by_email(email):
    """使用 LRU 缓存最近查询的 128 个用户"""
    with repo.session_scope() as session:
        spec = QuerySpec(filters=[User.email == email])
        users = repo.list(session, User, spec)
        return users[0] if users else None

# 清除缓存
get_user_by_email.cache_clear()

# 缓存信息
print(get_user_by_email.cache_info())
# CacheInfo(hits=10, misses=5, maxsize=128, currsize=5)
```

### 策略 3：TTL 缓存

```python
import time
from typing import Optional, Any

class TTLCache:
    """支持过期时间的缓存"""
    
    def __init__(self):
        self._cache = {}
        self._expiry = {}
    
    def set(self, key: str, value: Any, ttl: int):
        """设置缓存，TTL 秒后过期"""
        self._cache[key] = value
        self._expiry[key] = time.time() + ttl
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存，如果已过期则删除"""
        if key not in self._cache:
            return None
        
        if time.time() > self._expiry[key]:
            # 已过期，删除
            del self._cache[key]
            del self._expiry[key]
            return None
        
        return self._cache[key]

# 使用
cache = TTLCache()
cache.set("config:app", {"version": "2.0.0"}, ttl=3600)
config = cache.get("config:app")
```

### 策略 4：分层缓存

```python
class HierarchicalCache:
    """多层缓存（L1 快速内存 + L2 持久存储）"""
    
    def __init__(self, l1_size=100, l2_size=1000):
        self.l1_cache = {}  # 快速访问
        self.l2_cache = {}  # 备份存储
        self.l1_size = l1_size
        self.l2_size = l2_size
    
    def get(self, key):
        # 优先查询 L1
        if key in self.l1_cache:
            return self.l1_cache[key]
        
        # 查询 L2
        if key in self.l2_cache:
            value = self.l2_cache[key]
            # 晋升到 L1
            self._promote_to_l1(key, value)
            return value
        
        return None
    
    def set(self, key, value):
        if len(self.l1_cache) < self.l1_size:
            self.l1_cache[key] = value
        elif len(self.l2_cache) < self.l2_size:
            self.l2_cache[key] = value
    
    def _promote_to_l1(self, key, value):
        """将数据从 L2 晋升到 L1"""
        self.l1_cache[key] = value
        del self.l2_cache[key]
```

---

## 实践案例

### 案例 1：用户信息缓存

```python
class CachedUserRepository:
    def __init__(self, repo):
        self.repo = repo
        self.cache = {}  # {user_id: user_object}
        self.cache_ttl = {}  # {user_id: expiry_time}
    
    def get_user(self, session, user_id, cache_ttl=3600):
        """获取用户，优先使用缓存"""
        import time
        
        # 检查缓存有效性
        if user_id in self.cache:
            if time.time() < self.cache_ttl.get(user_id, 0):
                return self.cache[user_id]  # 缓存命中
            else:
                del self.cache[user_id]  # 缓存过期
        
        # 从数据库查询
        user = self.repo.get(session, User, user_id)
        
        # 存储到缓存
        if user:
            self.cache[user_id] = user
            self.cache_ttl[user_id] = time.time() + cache_ttl
        
        return user
    
    def update_user(self, session, user_id, updates):
        """更新用户并清除缓存"""
        user = self.repo.get(session, User, user_id)
        if user:
            self.repo.update_fields(session, user, updates)
            
            # 清除缓存以保持一致性
            if user_id in self.cache:
                del self.cache[user_id]
            
            return user
        return None
    
    def clear_cache(self):
        """清除所有缓存"""
        self.cache.clear()
        self.cache_ttl.clear()

# 使用
cached_repo = CachedUserRepository(repo)

with repo.session_scope() as session:
    # 首次查询 - 从数据库
    user = cached_repo.get_user(session, 1)
    
    # 第二次查询 - 从缓存
    user = cached_repo.get_user(session, 1)
    
    # 更新 - 清除缓存
    cached_repo.update_user(session, 1, {"name": "Bob"})
```

### 案例 2：配置缓存

```python
class ConfigCache:
    """应用配置缓存"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.config = {}
        self._initialized = True
    
    def load_config(self, session, repo):
        """从数据库加载配置"""
        configs = repo.list(session, Config)
        for cfg in configs:
            self.config[cfg.key] = cfg.value
    
    def get(self, key, default=None):
        """获取配置值"""
        return self.config.get(key, default)
    
    def reload(self, session, repo):
        """重新加载配置"""
        self.config.clear()
        self.load_config(session, repo)

# 使用
config_cache = ConfigCache()

with repo.session_scope() as session:
    # 启动时加载
    config_cache.load_config(session, repo)
    
    # 在应用中使用
    max_connections = config_cache.get("max_connections", 10)
    debug_mode = config_cache.get("debug_mode", False)
```

### 案例 3：缓存失效策略

```python
from enum import Enum
from typing import Callable, Dict, Any

class CacheInvalidationStrategy(Enum):
    """缓存失效策略"""
    IMMEDIATE = "immediate"  # 立即失效
    LAZY = "lazy"  # 延迟失效
    TTL = "ttl"  # 基于时间失效

class SmartCache:
    """智能缓存，支持多种失效策略"""
    
    def __init__(self, strategy=CacheInvalidationStrategy.TTL):
        self.cache = {}
        self.strategy = strategy
        self.dependencies = {}  # 缓存依赖关系
    
    def set(self, key, value, depends_on=None, ttl=3600):
        """设置缓存及其依赖"""
        self.cache[key] = {
            'value': value,
            'ttl': ttl,
            'created_at': time.time(),
            'depends_on': depends_on or []
        }
        
        # 记录依赖关系
        if depends_on:
            for dep in depends_on:
                if dep not in self.dependencies:
                    self.dependencies[dep] = []
                self.dependencies[dep].append(key)
    
    def invalidate(self, key):
        """手动失效缓存及其依赖"""
        if self.strategy == CacheInvalidationStrategy.IMMEDIATE:
            self._do_invalidate(key)
    
    def _do_invalidate(self, key):
        """实际失效操作"""
        if key in self.cache:
            del self.cache[key]
        
        # 级联失效依赖的缓存
        if key in self.dependencies:
            for dependent_key in self.dependencies[key]:
                self._do_invalidate(dependent_key)

# 使用
cache = SmartCache()

# 用户数据依赖于用户 ID
cache.set("user:1:profile", {"name": "Alice"}, depends_on=["user:1"])
cache.set("user:1:posts", [post1, post2], depends_on=["user:1"])

# 当用户数据更新时，级联失效所有依赖
cache.invalidate("user:1")
# user:1:profile 和 user:1:posts 都会被自动失效
```

---

## 缓存性能优化

### 优化 1：缓存大小管理

```python
class LimitedCache:
    """限制缓存大小的缓存"""
    
    def __init__(self, max_size=1000, eviction_strategy="lru"):
        self.cache = {}
        self.max_size = max_size
        self.strategy = eviction_strategy
        self.access_count = {}
    
    def set(self, key, value):
        if len(self.cache) >= self.max_size:
            self._evict_one()
        self.cache[key] = value
        self.access_count[key] = 0
    
    def get(self, key):
        if key in self.cache:
            self.access_count[key] += 1
            return self.cache[key]
        return None
    
    def _evict_one(self):
        """淘汰一个缓存项"""
        if self.strategy == "lru":
            # 淘汰最少使用的
            lru_key = min(self.access_count, key=self.access_count.get)
            del self.cache[lru_key]
            del self.access_count[lru_key]
```

### 优化 2：缓存预热

```python
class WarmableCache:
    """支持预热的缓存"""
    
    def __init__(self, repo):
        self.cache = {}
        self.repo = repo
    
    def warm_up(self, session, query_spec=None):
        """启动时预加载热点数据"""
        print("开始缓存预热...")
        
        if query_spec is None:
            # 加载所有常用数据
            users = self.repo.list(session, User, QuerySpec(limit=1000))
        else:
            users = self.repo.list(session, User, query_spec)
        
        for user in users:
            self.cache[f"user:{user.id}"] = user
        
        print(f"预热完成，缓存了 {len(users)} 条记录")
    
    def get(self, key):
        return self.cache.get(key)

# 启动应用时预热
cache = WarmableCache(repo)

with repo.session_scope() as session:
    # 预加载活跃用户
    hot_spec = QuerySpec(
        filters=[User.status == "active"],
        limit=1000
    )
    cache.warm_up(session, hot_spec)
```

---

## 缓存监控

```python
class CacheStatistics:
    """缓存统计"""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
    
    def record_hit(self):
        self.hits += 1
    
    def record_miss(self):
        self.misses += 1
    
    def record_set(self):
        self.sets += 1
    
    def record_delete(self):
        self.deletes += 1
    
    @property
    def hit_rate(self):
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0
    
    def report(self):
        print(f"缓存统计:")
        print(f"  命中: {self.hits}")
        print(f"  未命中: {self.misses}")
        print(f"  命中率: {self.hit_rate:.2%}")
        print(f"  设置: {self.sets}")
        print(f"  删除: {self.deletes}")

# 使用
stats = CacheStatistics()

def cached_get(key):
    if key in cache:
        stats.record_hit()
        return cache[key]
    else:
        stats.record_miss()
        return None

stats.report()
```

---

## 最佳实践

| 实践 | 说明 |
|------|------|
| **缓存热点数据** | 仅缓存频繁访问的数据，避免缓存冷数据 |
| **设置合理 TTL** | 根据数据更新频率设置过期时间 |
| **缓存失效策略** | 数据更新时立即清除相关缓存 |
| **监控缓存指标** | 跟踪命中率，优化缓存策略 |
| **避免缓存雪崩** | 使用随机 TTL 避免大量缓存同时过期 |
| **线程安全** | 在多线程环境中使用锁保护缓存 |

---

## 总结

缓存是提高应用性能的关键技术。根据不同场景选择合适的缓存策略：

- **查询缓存**：用于数据库查询结果
- **LLM 响应缓存**：减少 API 调用和成本
- **配置缓存**：启动时加载，减少配置查询
- **会话缓存**：用户会话快速访问

合理的缓存策略可以显著改善应用响应时间和系统吞吐量。

---

**最后更新** | 2026 年 1 月 8 日
