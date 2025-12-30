# Database Cache Guide

## Overview

The MoFox Bot database system includes a pluggable cache architecture with multiple backends:

- **Memory cache**: Multi-level LRU cache, best for single-instance deployments.
- **Redis cache**: Distributed cache for multi-instance or persistent-cache scenarios.

## Choosing a Cache Backend

Configure in `bot_config.toml`:

```toml
[database]
enable_database_cache = true  # Turn cache on/off
cache_backend = "memory"      # "memory" or "redis"
```

### Backend Comparison

| Feature | Memory cache (memory) | Redis cache (redis) |
| --- | --- | --- |
| Deploy complexity | Low (no extra deps) | Medium (Redis service required) |
| Distributed | ❌ | ✅ |
| Persistence | ❌ | ✅ |
| Performance | Very high (local memory) | High (network overhead) |
| Best for | Single instance | Multi-instance / clusters |

---

## Memory Cache Architecture

### Multi-level cache

- **L1 cache (hot data)**
  - Capacity: 1,000 items (configurable)
  - TTL: 300s (configurable)
  - Use: hottest recently accessed data

- **L2 cache (warm data)**
  - Capacity: 10,000 items (configurable)
  - TTL: 1,800s (configurable)
  - Use: commonly accessed, less hot data

### LRU eviction

Both levels use LRU:
- When full, evict the least recently used item.
- Keep the most-used data cached.

---

## Redis Cache Architecture

### Features

- **Distributed**: Share cache across Bot instances.
- **Persistence**: Redis RDB/AOF supported.
- **TTL management**: Use Redis native expiration.
- **Pattern delete**: Wildcard batch deletes.
- **Atomic ops**: INCR/DECR and more.

### Configuration

```toml
[database]
# Redis cache config (effective when cache_backend = "redis")
redis_host = "localhost"
redis_port = 6379
redis_password = ""
redis_db = 0
redis_key_prefix = "mofox:"
redis_default_ttl = 600
redis_connection_pool_size = 10
```

### Install Redis dependency

```bash
pip install redis
```

---

## Usage

### 1) `@cached` decorator (recommended)

Simplest approach; works with any backend:

```python
from src.common.database.utils.decorators import cached

@cached(ttl=600, key_prefix="person_info")
async def get_person_info(platform: str, person_id: str):
    """Fetch person info with a 10-minute cache"""
    return await _person_info_crud.get_by(
        platform=platform,
        person_id=person_id,
    )
```

#### Parameters

- `ttl`: Expiration in seconds; None means never expire.
- `key_prefix`: Prefix for namespacing cache keys.
- `use_args`: Include positional args in the key (default True).
- `use_kwargs`: Include keyword args in the key (default True).

### 2) Manual cache management

For fine-grained control:

```python
from src.common.database.optimization import get_cache

async def custom_query():
    cache = await get_cache()
    
    # Try cache
    result = await cache.get("my_key")
    if result is not None:
        return result
    
    # Miss: query DB
    result = await execute_database_query()
    
    # Write cache (custom TTL optional)
    await cache.set("my_key", result, ttl=300)
    
    return result
```

### 3) `get_or_load`

Simplified load pattern:

```python
cache = await get_cache()

# If hit, return; if miss, run loader then cache
result = await cache.get_or_load(
    "my_key",
    loader=lambda: fetch_data_from_db(),
    ttl=600
)
```

### 4) Cache invalidation

Expire cache after updates:

```python
from src.common.database.optimization import get_cache
from src.common.database.utils.decorators import generate_cache_key

async def update_person_affinity(platform: str, person_id: str, affinity_delta: float):
    await _person_info_crud.update(person.id, {"affinity": new_affinity})
    
    cache = await get_cache()
    cache_key = generate_cache_key("person_info", platform, person_id)
    await cache.delete(cache_key)
```

---

## Pre-cached queries

### PersonInfo

- **Function**: `get_or_create_person()`
- **TTL**: 10 minutes
- **Key**: `person_info:args:<hash>`
- **Invalidation**: When `update_person_affinity()` updates affinity

### UserRelationships

- **Function**: `get_user_relationship()`
- **TTL**: 5 minutes
- **Key**: `user_relationship:args:<hash>`
- **Invalidation**: When `update_relationship_affinity()` updates relationship

### ChatStreams

- **Function**: `get_or_create_chat_stream()`
- **TTL**: 5 minutes
- **Key**: `chat_stream:args:<hash>`
- **Invalidation**: On stream updates when needed

## Cache stats

### Memory cache stats

```python
cache = await get_cache()
stats = await cache.get_stats()

if cache.backend_type == "memory":
    print(f"L1: {stats['l1'].item_count} items, hit rate {stats['l1'].hit_rate:.2%}")
    print(f"L2: {stats['l2'].item_count} items, hit rate {stats['l2'].hit_rate:.2%}")
```

### Redis cache stats

```python
if cache.backend_type == "redis":
    print(f"Hit rate: {stats['hit_rate']:.2%}")
    print(f"Key count: {stats['key_count']}")
```

### Check current backend

```python
from src.common.database.optimization import get_cache_backend_type

backend = get_cache_backend_type()  # "memory" or "redis"
```

---

## Best practices

### 1) Choose TTL wisely

- **Fast-changing data**: 60–300s (e.g., online status)
- **Moderate change**: 300–600s (e.g., user info, relationships)
- **Stable data**: 600–1800s (e.g., configs, metadata)

### 2) Key design

- Use meaningful prefixes: `person_info:`, `user_rel:`, `chat_stream:`
- Ensure uniqueness: include all query params.
- Avoid collisions: use `generate_cache_key()` helper.

### 3) Invalidate promptly

- **Write-time invalidation**: Delete cache right after updates.
- **Batch invalidation**: Wildcards/prefix deletes for related keys.
- **Lazy invalidation**: Rely on TTL for non-critical data.

### 4) Monitor effectiveness

- Hit rate > 70%: good ✅
- 50–70%: tune TTL or strategy ⚠️
- < 50%: consider not caching ❌

---

## Performance gains

From tests:

- **PersonInfo queries**: >90% fewer DB hits on cache hit.
- **Relationship queries**: >80% fewer connections in hot paths.
- **Chat stream queries**: >75% fewer repeated lookups in active sessions.

## Notes

1. **Consistency**: Invalidate after writes.
2. **Memory usage**: Monitor cache size to avoid excessive RAM.
3. **Serialization**: Cached objects must be serializable.
   - Memory cache: stores Python objects directly.
   - Redis cache: JSON by default; complex objects fall back to Pickle.
4. **Concurrency**: Both backends are coroutine-safe.
5. **No automatic fallback**: Redis failures raise; no auto-fallback to memory.

---

## Troubleshooting

### Cache not working

1. Check `enable_database_cache = true`.
2. Ensure the decorator is imported correctly.
3. Verify TTL settings.
4. Check cache logs.

### Data inconsistency

1. Confirm updates invalidate cache.
2. Ensure consistent key generation.
3. Consider shorter TTL.

### High memory usage (memory cache)

1. Inspect item counts in stats.
2. Adjust L1/L2 sizes.
3. Shorten TTL for faster eviction.

### Redis connection failure

1. Ensure Redis is running.
2. Verify host/port/password.
3. Check firewall/network.
4. Inspect logs for errors.

---

## Further reading

- Cache backend abstraction: `../src/common/database/optimization/cache_backend.py`
- Memory cache implementation: `../src/common/database/optimization/cache_manager.py`
- Redis cache implementation: `../src/common/database/optimization/redis_cache.py`
- Cache decorators: `../src/common/database/utils/decorators.py`
