# SQLite 性能优化指南

## 目录

1. [WAL 模式优化](#wal-模式优化)
2. [连接池管理](#连接池管理)
3. [查询优化](#查询优化)
4. [索引策略](#索引策略)
5. [事务优化](#事务优化)
6. [缓存策略](#缓存策略)
7. [监控和诊断](#监控和诊断)

---

## WAL 模式优化

### 什么是 WAL？

WAL（Write-Ahead Logging）是 SQLite 的日志记录方式，相比默认模式有更好的并发性能。

### 启用 WAL

```python
from kernel.db.core import create_sqlite_engine

# 自动启用所有 WAL 相关优化
engine = create_sqlite_engine(
    "data/app.db",
    enable_wal=True  # 推荐所有生产环境启用
)
```

### WAL 性能对比

| 指标 | 默认模式 | WAL 模式 | 提升 |
|------|--------|--------|------|
| 顺序写入 | 100 OPS | 500 OPS | 5 倍 |
| 并发读 | 阻塞 | 可读 | ✓ |
| 并发写 | 阻塞 | 阻塞 | 无 |
| 读取延迟 | 低 | 低 | ≈ |
| 磁盘空间 | 小 | 大 | +5% |

### WAL 相关文件

```
data/
├── app.db           # 主数据库文件
├── app.db-wal       # WAL 日志（活跃时存在）
└── app.db-shm       # 共享内存（WAL 使用）
```

**注意：** 不支持网络文件系统（NFS），仅支持本地文件系统。

---

## 连接池管理

### 池大小计算

```python
# 最优池大小 = (并发连接数 * 2) + 5

from kernel.db.core import create_sqlite_engine

# 开发环境（并发 5）
dev_engine = create_sqlite_engine(
    "data/dev.db",
    pool_size=15  # (5 * 2) + 5
)

# 生产环境（并发 20）
prod_engine = create_sqlite_engine(
    "data/prod.db",
    pool_size=45  # (20 * 2) + 5
)

# 高并发（并发 50）
high_concurrency_engine = create_sqlite_engine(
    "data/high_load.db",
    pool_size=105  # (50 * 2) + 5
)
```

### 连接回收

```python
# 长期运行应用应定期回收连接
config = EngineConfig(
    database="data/app.db",
    pool_size=20,
    pool_timeout=30,
    # 连接在 1 小时后回收，防止"僵尸"连接
)

# 手动回收连接
from sqlalchemy import event
from sqlalchemy.pool import QueuePool

@event.listens_for(QueuePool, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()
```

---

## 查询优化

### 1. 投影优化（只查询需要的列）

```python
from kernel.db.api import QuerySpec

# ❌ 低效：查询所有列再筛选
with repo.session_scope() as session:
    users = repo.list(session, User)
    names = [u.name for u in users]  # 浪费内存

# ✅ 高效：只查询需要的列
with repo.session_scope() as session:
    from sqlalchemy import select
    stmt = select(User.id, User.name)
    result = session.execute(stmt).fetchall()
```

### 2. 分页优化

```python
# ❌ 低效：OFFSET 大时扫描所有行
with repo.session_scope() as session:
    spec = QuerySpec(
        limit=20,
        offset=10000  # 需要扫描 10020 行
    )
    users = repo.list(session, User, spec)

# ✅ 高效：使用 WHERE 条件
with repo.session_scope() as session:
    last_id = 10000
    spec = QuerySpec(
        filters=[User.id > last_id],
        limit=20
    )
    users = repo.list(session, User, spec)
```

### 3. JOIN 优化

```python
from sqlalchemy import joinedload

# ❌ 低效：N+1 查询
with repo.session_scope() as session:
    users = repo.list(session, User)
    for user in users:
        posts = user.posts  # 每个用户一次查询

# ✅ 高效：预加载关联
from sqlalchemy import select
stmt = select(User).options(joinedload(User.posts))
users = session.execute(stmt).unique().scalars().all()
```

### 4. 排序优化

```python
# ❌ 低效：在应用中排序（缓存整个结果集）
with repo.session_scope() as session:
    users = repo.list(session, User)
    sorted_users = sorted(users, key=lambda u: u.created_at)

# ✅ 高效：在数据库中排序
with repo.session_scope() as session:
    spec = QuerySpec(
        order_by=[User.created_at.desc()]
    )
    users = repo.list(session, User, spec)
```

---

## 索引策略

### 索引基础

```python
from sqlalchemy import Column, Integer, String, Index

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    
    # 单列索引
    email = Column(String(100), index=True)
    name = Column(String(100), index=True)
    
    # 唯一索引
    username = Column(String(50), unique=True)
    
    # 复合索引
    __table_args__ = (
        Index('idx_status_created', 'status', 'created_at'),
    )
```

### 索引使用场景

| 场景 | 推荐 |
|------|------|
| WHERE 条件 | ✓ |
| JOIN 条件 | ✓ |
| ORDER BY | ✓ |
| GROUP BY | ✓ |
| 高基数列（如 ID） | ✓ |
| 低基数列（如性别） | ✗ |

### 索引性能监控

```python
def analyze_indexes(engine):
    """分析索引使用情况"""
    with engine.connect() as conn:
        # 获取所有索引
        result = conn.execute("""
            SELECT name, tbl_name 
            FROM sqlite_master 
            WHERE type='index'
        """)
        
        for name, table in result:
            print(f"索引：{name} （表：{table}）")
        
        # 强制分析
        conn.execute("ANALYZE")
        conn.commit()

# 使用
analyze_indexes(engine)
```

---

## 事务优化

### 批量操作

```python
# ❌ 低效：多个事务
with repo.session_scope() as session:
    for user_data in large_list:
        repo.add(session, User(**user_data))
        # 每个 add 都涉及事务开销

# ✅ 高效：单个事务中批量插入
with repo.session_scope() as session:
    users = [User(**data) for data in large_list]
    repo.add_many(session, users, flush=True)
```

### 事务隔离级别

```python
from sqlalchemy import event, create_engine

engine = create_sqlite_engine("data/app.db")

# SQLite 支持的隔离级别
# DEFERRED（默认）：延迟锁定
# IMMEDIATE：立即锁定（防止写冲突）
# EXCLUSIVE：独占锁定（防止所有冲突）

@event.listens_for(engine, "connect")
def set_isolation(dbapi_conn, connection_record):
    # 使用 IMMEDIATE 防止写冲突
    dbapi_conn.isolation_level = None  # 禁用自动事务
    cursor = dbapi_conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.close()
```

---

## 缓存策略

### 多层缓存架构

```python
from functools import lru_cache
import time

class MultiLayerCache:
    """L1 快速内存 + L2 持久化"""
    
    def __init__(self):
        self.l1 = {}  # 快速访问，限制大小
        self.l2 = {}  # 备份存储
        self.ttl = {}
        self.l1_size = 100
    
    def get(self, key):
        # L1 缓存
        if key in self.l1:
            if self._is_valid(key):
                return self.l1[key]
        
        # L2 缓存
        if key in self.l2:
            if self._is_valid(key):
                # 晋升到 L1
                self._promote_to_l1(key)
                return self.l2[key]
        
        return None
    
    def set(self, key, value, ttl=3600):
        if len(self.l1) < self.l1_size:
            self.l1[key] = value
        else:
            self.l2[key] = value
        
        self.ttl[key] = time.time() + ttl
    
    def _is_valid(self, key):
        return time.time() < self.ttl.get(key, 0)
    
    def _promote_to_l1(self, key):
        if len(self.l1) >= self.l1_size:
            # 淘汰最旧的
            oldest = min(self.l1.keys(), key=lambda k: self.ttl.get(k, 0))
            self.l2[oldest] = self.l1[oldest]
            del self.l1[oldest]
        
        self.l1[key] = self.l2[key]
        del self.l2[key]
```

### 热点数据预加载

```python
def warm_up_cache(session, repo, cache):
    """启动时预加载热点数据"""
    # 加载活跃用户
    from kernel.db.api import QuerySpec
    
    spec = QuerySpec(
        filters=[User.status == "active"],
        limit=1000
    )
    
    users = repo.list(session, User, spec)
    for user in users:
        cache.set(f"user:{user.id}", user, ttl=3600)
    
    print(f"预加载了 {len(users)} 条热点数据")
```

---

## 监控和诊断

### 性能指标

```python
import sqlite3
import time

def get_performance_metrics(db_path):
    """获取数据库性能指标"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. 数据库大小
    import os
    db_size = os.path.getsize(db_path)
    
    # 2. 表数量
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count = cursor.fetchone()[0]
    
    # 3. 索引数量
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
    index_count = cursor.fetchone()[0]
    
    # 4. WAL 模式
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    
    # 5. 缓存大小
    cursor.execute("PRAGMA cache_size")
    cache_size = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "database_size": db_size,
        "table_count": table_count,
        "index_count": index_count,
        "journal_mode": journal_mode,
        "cache_size": cache_size,
    }

# 使用
metrics = get_performance_metrics("data/app.db")
print(f"数据库大小：{metrics['database_size'] / 1024 / 1024:.2f} MB")
print(f"表数量：{metrics['table_count']}")
print(f"日志模式：{metrics['journal_mode']}")
```

### 查询性能分析

```python
def analyze_query_performance(session, stmt, iterations=10):
    """分析查询性能"""
    import time
    
    times = []
    for _ in range(iterations):
        start = time.time()
        session.execute(stmt).fetchall()
        times.append(time.time() - start)
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print(f"平均: {avg_time*1000:.2f}ms")
    print(f"最小: {min_time*1000:.2f}ms")
    print(f"最大: {max_time*1000:.2f}ms")
    
    return {
        "average": avg_time,
        "min": min_time,
        "max": max_time,
    }

# 使用
from sqlalchemy import select
stmt = select(User).where(User.status == "active")
analyze_query_performance(session, stmt)
```

---

## 优化检查清单

### 基础优化

- [ ] 启用 WAL 模式
- [ ] 设置合理的连接池大小
- [ ] 启用外键约束
- [ ] 配置适当的 synchronous 级别

### 索引优化

- [ ] 为 WHERE 条件列添加索引
- [ ] 为 ORDER BY 列添加索引
- [ ] 考虑复合索引
- [ ] 移除未使用的索引

### 查询优化

- [ ] 使用投影避免查询不需要的列
- [ ] 使用分页限制结果集
- [ ] 使用 JOIN 而不是应用代码循环
- [ ] 分析慢查询

### 缓存优化

- [ ] 缓存频繁查询的数据
- [ ] 设置合理的 TTL
- [ ] 实现缓存预热
- [ ] 监控缓存命中率

### 监控优化

- [ ] 定期检查数据库大小
- [ ] 分析慢查询日志
- [ ] 监控连接池使用情况
- [ ] 跟踪性能指标

---

## 最佳实践总结

| 实践 | 影响 | 难度 |
|------|------|------|
| 启用 WAL | ⭐⭐⭐⭐⭐ | ⭐ |
| 合理设置池大小 | ⭐⭐⭐⭐ | ⭐ |
| 添加索引 | ⭐⭐⭐⭐ | ⭐⭐ |
| 批量操作 | ⭐⭐⭐ | ⭐ |
| 查询优化 | ⭐⭐⭐ | ⭐⭐ |
| 缓存策略 | ⭐⭐⭐⭐ | ⭐⭐⭐ |

---

**最后更新** | 2026 年 1 月 8 日
