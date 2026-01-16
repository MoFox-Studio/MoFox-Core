# SQLite 数据库配置与优化指南

## 目录

1. [SQLite 简介](#sqlite-简介)
2. [快速开始](#快速开始)
3. [高级配置](#高级配置)
4. [性能优化](#性能优化)
5. [故障排除](#故障排除)
6. [迁移与备份](#迁移与备份)

---

## SQLite 简介

SQLite 是一个轻量级、自包含的 SQL 数据库引擎，完全 ACID 兼容，适合单机应用、本地开发和嵌入式系统。

### 特性

| 特性 | 说明 |
|------|------|
| **零配置** | 无需安装或配置，文件即数据库 |
| **ACID** | 完整的事务支持和数据一致性 |
| **SQL 标准** | 支持大部分 SQL 语句 |
| **小巧** | 核心库仅几百 KB |
| **可靠** | 生产就绪，广泛应用 |
| **WAL 支持** | Write-Ahead Logging 提高并发 |

### 适用场景

```
✅ 本地开发和测试
✅ 桌面应用和移动应用  
✅ 原型和演示
✅ 单机应用
✅ 缓存和临时存储
```

### 不适用场景

```
❌ 多用户网络应用（考虑 MySQL/PostgreSQL）
❌ 海量数据（TB+ 级别）
❌ 高并发写入（>100 QPS）
❌ 分布式系统（需要 MongoDB）
```

---

## 快速开始

### 1. 文件数据库

```python
from kernel.db.core import create_sqlite_engine, SessionManager
from kernel.db.api import SQLAlchemyCRUDRepository

# 创建或连接数据库文件
engine = create_sqlite_engine("data/myapp.db")

# 创建表
from sqlalchemy import Column, Integer, String, create_all

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    email = Column(String(100))

Base.metadata.create_all(engine)

# 使用 CRUD 仓库
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

with repo.session_scope() as session:
    user = repo.add(session, User(name="Alice", email="alice@example.com"), flush=True)
    users = repo.list(session, User)
```

### 2. 内存数据库

```python
# 创建临时内存数据库（测试用）
engine = create_sqlite_engine(":memory:")

session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

with repo.session_scope() as session:
    # 使用完全相同的 API
    obj = repo.add(session, MyModel())
```

### 3. 临时文件数据库

```python
import tempfile

# 创建临时数据库文件
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = f.name

engine = create_sqlite_engine(db_path)
# ...应用逻辑...
```

---

## 高级配置

### 标准配置

```python
from kernel.db.core import EngineConfig, EngineManager

config = EngineConfig(
    database="data/app.db",           # 数据库文件路径
    echo=False,                       # 不输出 SQL 语句
    pool_size=10,                     # 连接池大小
    pool_timeout=30,                  # 连接超时时间
    create_if_missing=True,           # 自动创建数据库文件
)

manager = EngineManager()
engine = manager.create(config)
```

### 开发环境配置

```python
config = EngineConfig(
    database="data/dev.db",
    echo=True,                        # 输出 SQL 调试
    pool_size=5,
    enable_wal=True,
    enable_foreign_keys=True,
)

engine = manager.create(config)
```

### 生产环境配置

```python
config = EngineConfig(
    database="data/prod.db",
    echo=False,
    pool_size=20,                     # 更多连接
    pool_timeout=60,
    enable_wal=True,                  # 启用 WAL 模式
    enable_foreign_keys=True,         # 强制外键约束
    journal_mode="WAL",
    synchronous="NORMAL",             # 平衡安全和性能
    timeout=30,                       # 锁定超时
    create_if_missing=True,
)

engine = manager.create(config)
```

### Pragma 配置详解

| Pragma | 值 | 说明 |
|--------|-----|------|
| `enable_wal` | True | 启用 WAL 日志模式，提高并发性能 |
| `enable_foreign_keys` | True | 启用外键约束检查 |
| `journal_mode` | WAL | 日志模式：WAL（推荐）或 DELETE |
| `synchronous` | NORMAL | 同步级别：OFF（快速）、NORMAL（推荐）、FULL（安全） |
| `timeout` | 30 | 数据库锁定超时（秒），避免长期等待 |

---

## 性能优化

### 1. WAL 模式（推荐）

WAL（Write-Ahead Logging）使用方式：

```python
engine = create_sqlite_engine(
    "data/app.db",
    enable_wal=True,                  # 自动应用所有 WAL 相关配置
)
```

**优势：**
- 读写操作可并发进行
- 写入性能提升 2-5 倍
- 更好的并发应用体验

**权衡：**
- 增加文件数量（`.db-wal`、`.db-shm`）
- 不支持网络文件系统（NFS）

### 2. 连接池优化

```python
config = EngineConfig(
    database="data/app.db",
    pool_size=20,                     # 基础连接数
    pool_timeout=60,                  # 等待连接超时
    pool_recycle=3600,                # 连接回收时间（秒）
)
```

**选择合适的 pool_size：**
- 开发环境：5-10
- 生产环境：10-30
- 高并发：20-50

### 3. Pragma 优化

```python
from kernel.db.core import create_sqlite_engine

engine = create_sqlite_engine(
    "data/app.db",
    enable_wal=True,
    enable_foreign_keys=True,
    journal_mode="WAL",
    synchronous="NORMAL",             # 平衡性能和安全
    timeout=30,
)
```

**关键 Pragma 解释：**

```sql
-- WAL 日志模式（推荐）
PRAGMA journal_mode = WAL;

-- 同步级别（NORMAL 是最佳平衡）
PRAGMA synchronous = NORMAL;

-- 缓存大小（-64000 表示 64MB）
PRAGMA cache_size = -64000;

-- 临时存储在内存（加快临时表）
PRAGMA temp_store = MEMORY;

-- 自动真空（增量模式）
PRAGMA auto_vacuum = INCREMENTAL;

-- 内存映射 I/O（加快读取）
PRAGMA mmap_size = 30000000;

-- 外键约束
PRAGMA foreign_keys = ON;
```

### 4. 索引优化

```python
from sqlalchemy import Index, Column, Integer, String

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(100), unique=True, index=True)  # 唯一索引
    name = Column(String(100), index=True)                # 普通索引
    status = Column(String(20), index=True)
    created_at = Column(DateTime, index=True)

# 复合索引
__table_args__ = (
    Index('idx_user_status_created', 'status', 'created_at'),
)
```

### 5. 批量操作优化

```python
with repo.session_scope() as session:
    # ❌ 低效：逐条插入，频繁提交
    for i in range(1000):
        repo.add(session, User(name=f"user{i}"))
    
    # ✅ 高效：批量插入，一次提交
    users = [User(name=f"user{i}") for i in range(1000)]
    repo.add_many(session, users, flush=True)
```

### 6. 查询优化

```python
from kernel.db.api import QuerySpec

# ❌ 低效：加载所有数据再筛选
with repo.session_scope() as session:
    all_users = repo.list(session, User)
    active = [u for u in all_users if u.status == "active"]

# ✅ 高效：在数据库层筛选
with repo.session_scope() as session:
    spec = QuerySpec(
        filters=[User.status == "active"],
        limit=100
    )
    active = repo.list(session, User, spec)
```

---

## 故障排除

### 问题 1：数据库被锁定

```
sqlite3.OperationalError: database is locked
```

**原因：** 另一个进程正在写入数据库

**解决方案：**
```python
# 增加超时时间
engine = create_sqlite_engine(
    "data/app.db",
    timeout=60  # 等待 60 秒获取锁
)

# 或使用 WAL 模式减少锁时间
engine = create_sqlite_engine(
    "data/app.db",
    enable_wal=True
)
```

### 问题 2：外键约束失败

```
sqlite3.IntegrityError: FOREIGN KEY constraint failed
```

**原因：** 数据库没有启用外键检查

**解决方案：**
```python
engine = create_sqlite_engine(
    "data/app.db",
    enable_foreign_keys=True  # 启用外键约束
)
```

### 问题 3：大文件性能下降

**原因：** 数据库文件过大，需要优化

**解决方案：**
```python
# 启用自动真空防止碎片
engine = create_sqlite_engine(
    "data/app.db",
    enable_wal=True,
    # SQLite 会自动配置以下 pragma
    # PRAGMA auto_vacuum = INCREMENTAL;
    # PRAGMA vacuum_into = 'data/app-optimized.db';
)

# 手动优化（可选）
with engine.connect() as conn:
    conn.execute("VACUUM")  # 重组数据库文件
    conn.commit()
```

### 问题 4：内存使用过高

**原因：** 缓存大小过大或连接数过多

**解决方案：**
```python
config = EngineConfig(
    database="data/app.db",
    pool_size=10,           # 减少连接数
    echo=False,             # 关闭 SQL 日志
)
```

---

## 迁移与备份

### 备份数据库

```python
import shutil
from datetime import datetime

def backup_database(db_path, backup_dir="backups"):
    """创建数据库备份"""
    import os
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/app_{timestamp}.db"
    
    shutil.copy2(db_path, backup_path)
    print(f"备份完成：{backup_path}")
    
    return backup_path

# 使用
backup_database("data/app.db")
```

### 恢复数据库

```python
def restore_database(backup_path, target_path):
    """从备份恢复数据库"""
    import shutil
    
    shutil.copy2(backup_path, target_path)
    print(f"恢复完成：{target_path}")

# 使用
restore_database("backups/app_20240101_120000.db", "data/app.db")
```

### 数据库迁移

使用 SQLAlchemy 的 Alembic 工具：

```bash
# 初始化迁移环境
alembic init alembic

# 创建迁移脚本
alembic revision --autogenerate -m "添加用户表"

# 应用迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

---

## 多环境配置

### 开发环境（dev）

```python
from kernel.db.core import create_sqlite_engine

dev_engine = create_sqlite_engine(
    database="data/dev.db",
    echo=True,                        # 显示 SQL
    pool_size=5,
    enable_wal=True,
)
```

### 测试环境（test）

```python
# 使用内存数据库，每次测试独立
test_engine = create_sqlite_engine(
    database=":memory:",
    echo=False,
    pool_size=1,
)
```

### 生产环境（prod）

```python
prod_engine = create_sqlite_engine(
    database="data/prod.db",
    echo=False,                       # 不显示 SQL
    pool_size=20,
    pool_timeout=60,
    enable_wal=True,
    enable_foreign_keys=True,
    synchronous="NORMAL",
    timeout=30,
)
```

---

## 监控和维护

### 数据库统计

```python
def get_db_stats(engine):
    """获取数据库统计信息"""
    with engine.connect() as conn:
        # 数据库文件大小
        import os
        db_path = engine.url.database
        file_size = os.path.getsize(db_path)
        
        # 表数量
        result = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = result.scalar()
        
        # WAL 模式
        wal_result = conn.execute("PRAGMA journal_mode")
        wal_mode = wal_result.scalar()
        
        return {
            "file_size": file_size,
            "table_count": table_count,
            "wal_mode": wal_mode,
        }

# 使用
stats = get_db_stats(engine)
print(f"数据库大小：{stats['file_size']} 字节")
print(f"表数量：{stats['table_count']}")
print(f"日志模式：{stats['wal_mode']}")
```

### 定期维护

```python
def maintenance_task(engine):
    """定期数据库维护"""
    with engine.connect() as conn:
        # 分析表以优化查询
        conn.execute("ANALYZE")
        
        # 检查完整性
        result = conn.execute("PRAGMA integrity_check")
        check = result.scalar()
        
        print(f"完整性检查：{check}")
        
        conn.commit()

# 定时运行（例如每天一次）
import schedule
schedule.every().day.at("02:00").do(maintenance_task, engine=engine)
```

---

## 最佳实践总结

| 实践 | 说明 |
|------|------|
| **启用 WAL** | 提高并发性能，推荐所有生产环境 |
| **设置合理超时** | 避免无限期锁定 |
| **启用外键** | 保证数据完整性 |
| **定期备份** | 自动化备份关键数据库 |
| **使用索引** | 加速频繁查询字段 |
| **批量操作** | 使用 add_many/delete_many 提高效率 |
| **监控大小** | 定期检查文件大小，必要时优化 |
| **记录日志** | 调试期间启用 SQL 日志 |

---

**最后更新** | 2026 年 1 月 8 日

