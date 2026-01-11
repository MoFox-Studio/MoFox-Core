# 数据库内核模块（Database Kernel Module）

## 概述（Overview）

MoFox 数据库内核是一个专业级 SQLite 数据库系统，提供完整的 CRUD 操作、事务管理、查询规约和性能优化。该模块采用 SQLAlchemy ORM 和标准仓库模式，确保代码质量和可维护性。

The MoFox Database Kernel is a professional-grade SQLite database system providing comprehensive CRUD operations, transaction management, query specification, and performance optimization. Using SQLAlchemy ORM and standard repository pattern for quality and maintainability.

---

## 核心特性（Key Features）

| 特性 | 说明 |
|------|------|
| **专业级 SQLite** | 优化的 SQLite 配置，支持文件和内存数据库 |
| **统一接口** | 通过 Repository 模式提供强大的 CRUD 操作 |
| **引擎管理** | EngineManager 中央管理数据库引擎 |
| **事务管理** | SessionManager 自动处理事务、提交和回滚 |
| **查询规约** | QuerySpec 支持过滤、排序、分页 |
| **性能优化** | WAL 模式、连接池、内存映射 I/O、自动真空 |
| **日志集成** | 与 Logger 模块深度集成，记录所有操作 |
| **并发支持** | WAL 日志模式支持读写并发 |
| **完整文档** | 中英文双语文档和代码示例 |

---

## 目录结构（Directory Structure）

```
src/kernel/db/
├── core/                          # 核心引擎与会话管理
│   ├── __init__.py
│   ├── dialect_adapter.py         # SQLite 方言适配器
│   ├── engine.py                  # 引擎管理器与创建函数
│   ├── session.py                 # 会话和事务管理
│   └── exceptions.py              # 自定义异常
├── api/                           # 对外 CRUD 接口
│   ├── __init__.py
│   ├── crud.py                    # CRUD 仓库实现
│   └── query.py                   # 查询规约（QuerySpec）
└── README.md                      # 本文件
```

---

## 快速开始（Quick Start）

### 1. 基础设置 - 文件数据库

```python
from kernel.db.core import create_sqlite_engine, SessionManager
from kernel.db.api import SQLAlchemyCRUDRepository, QuerySpec

# 创建 SQLite 引擎（文件数据库）
engine = create_sqlite_engine("data/app.db")

# 创建会话管理器和仓库
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

# 使用事务进行操作
with repo.session_scope() as session:
    # 添加对象
    user = repo.add(session, User(name="Alice"), flush=True)
    
    # 列表查询
    users = repo.list(session, User, QuerySpec(limit=10))
    
    # 自动提交事务
```

### 2. 内存数据库 - 快速测试

```python
# 创建内存数据库
engine = create_sqlite_engine(":memory:")
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

# 使用方式相同
with repo.session_scope() as session:
    obj = repo.add(session, MyModel())
```

### 3. 高级配置 - 生产环境

```python
from kernel.db.core import EngineManager, EngineConfig

config = EngineConfig(
    database="data/prod.db",
    pool_size=20,
    pool_timeout=60,
    enable_wal=True,              # 启用 WAL 日志模式
    enable_foreign_keys=True,      # 启用外键约束
    journal_mode="WAL",
    synchronous="NORMAL",
    timeout=30
)

manager = EngineManager()
engine = manager.create(config)
```

---

## 核心组件说明（Core Components）

### EngineConfig - 引擎配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `database` | str | 必需 | 数据库文件路径或 `:memory:` |
| `echo` | bool | False | 启用 SQL 语句日志 |
| `pool_size` | int | 10 | 连接池大小 |
| `pool_timeout` | int | 30 | 连接获取超时（秒） |
| `enable_wal` | bool | True | 启用 WAL 日志模式（推荐） |
| `enable_foreign_keys` | bool | True | 启用外键约束 |
| `journal_mode` | str | WAL | 日志模式（WAL/DELETE） |
| `synchronous` | str | NORMAL | 同步级别（OFF/NORMAL/FULL） |
| `timeout` | int | 20 | 数据库锁超时（秒） |

### EngineManager - 引擎管理

```python
from kernel.db.core import EngineManager, EngineConfig

manager = EngineManager()

# 创建引擎
config = EngineConfig(database="data/app.db")
engine = manager.create(config)

# 获取引擎
engine = manager.get()

# 列出所有引擎
engines = manager.list_engines()

# 释放引擎
manager.dispose()
manager.dispose_all()  # 释放所有引擎
```

### SessionManager - 事务管理

```python
from kernel.db.core import SessionManager

session_mgr = SessionManager(engine)

# 获取事务作用域
with session_mgr.session_scope() as session:
    # 操作数据库
    obj = session.add(MyModel())
    # 异常时自动回滚
    # 退出时自动提交
```

### SQLAlchemyCRUDRepository - CRUD 仓库

```python
from kernel.db.api import SQLAlchemyCRUDRepository, QuerySpec

repo = SQLAlchemyCRUDRepository(session_mgr)

# 基本操作
with repo.session_scope() as session:
    # 添加
    obj = repo.add(session, MyModel(name="demo"))
    
    # 批量添加
    objs = repo.add_many(session, [MyModel(name=f"item{i}") for i in range(10)])
    
    # 查询
    item = repo.get(session, MyModel, 1)
    items = repo.list(session, MyModel)
    
    # 删除
    repo.delete(session, obj)
    count = repo.delete_many(session, MyModel, QuerySpec(filters=[...]))
    
    # 更新
    repo.update_fields(session, obj, {"name": "updated"})
    
    # 统计
    total = repo.count(session, MyModel)
    exists = repo.exists(session, MyModel, QuerySpec(filters=[...]))
```

### QuerySpec - 查询规约

```python
from kernel.db.api import QuerySpec

# 基础查询
spec = QuerySpec(
    filters=[MyModel.status == "active"],
    order_by=[MyModel.created_at.desc()],
    limit=20,
    offset=0
)

results = repo.list(session, MyModel, spec)
```

---

## 常见使用模式（Common Patterns）

### 模式 1：事务操作

```python
from kernel.db.core import SessionError

try:
    with repo.session_scope() as session:
        user1 = repo.add(session, User(name="Alice"))
        user2 = repo.add(session, User(name="Bob"))
        # 所有操作一起提交或一起回滚
except SessionError as e:
    print(f"事务失败: {e}")
```

### 模式 2：复杂查询

```python
from kernel.db.api import QuerySpec

# 多条件过滤
spec = QuerySpec(
    filters=[
        User.status == "active",
        User.age >= 18,
        User.is_deleted == False
    ],
    order_by=[User.created_at.desc()],
    limit=10,
    offset=0
)

active_adult_users = repo.list(session, User, spec)
```

### 模式 3：批量操作

```python
# 批量插入
users = [User(name=f"user{i}", email=f"user{i}@example.com") 
         for i in range(1000)]
repo.add_many(session, users, flush=True)

# 批量删除
spec = QuerySpec(filters=[User.is_deleted == True])
deleted_count = repo.delete_many(session, User, spec)
```

### 模式 4：分页查询

```python
page_size = 20
current_page = 1

spec = QuerySpec(
    limit=page_size,
    offset=(current_page - 1) * page_size
)

items = repo.list(session, User, spec)
total_count = repo.count(session, User)
total_pages = (total_count + page_size - 1) // page_size
```

---

## ORM 模型定义（Model Definition）

```python
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    status = Column(String(20), default="active")
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Post(Base):
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## 错误处理（Error Handling）

```python
from kernel.db.core import (
    DatabaseError,
    EngineAlreadyExistsError,
    EngineNotInitializedError,
    SessionError
)
from sqlalchemy.exc import IntegrityError

try:
    with repo.session_scope() as session:
        user = repo.add(session, User(name="Alice", email="alice@example.com"))
except IntegrityError as e:
    print(f"数据完整性错误（如唯一约束冲突）: {e}")
except SessionError as e:
    print(f"会话错误: {e}")
except EngineNotInitializedError as e:
    print(f"引擎未初始化: {e}")
except Exception as e:
    print(f"未知错误: {e}")
```

---

## 性能优化（Performance Optimization）

### WAL 模式优势

SQLite WAL（Write-Ahead Logging）模式提供：
- **并发读取**：读操作不阻塞写操作
- **高性能**：减少磁盘 I/O，提高吞吐量
- **数据安全**：改进崩溃恢复能力

### 推荐配置（生产环境）

```python
engine = create_sqlite_engine(
    database="data/prod.db",
    pool_size=20,
    pool_timeout=60,
    enable_wal=True,
    enable_foreign_keys=True,
    journal_mode="WAL",
    synchronous="NORMAL",      # FULL 更安全但较慢
    timeout=30
)
```

---

## 日志集成（Logging Integration）

所有数据库操作自动与 Logger 模块集成：

```python
# 调试信息
logger.debug("数据库添加操作: User", extra={
    'operation': 'add',
    'model': 'User'
})

# 信息级别
logger.info("数据库批量添加: User", extra={
    'operation': 'add_many',
    'count': 100
})

# 错误级别
logger.error("数据库事务回滚", extra={
    'session_id': 'session_123456',
    'error_type': 'IntegrityError'
})
```

---

## 常见问题（FAQ）

**Q: 如何从 SQLite 切换到其他数据库？**  
A: 当前版本仅支持 SQLite。如需其他数据库，可联系开发团队。

**Q: 如何处理数据库迁移？**  
A: 使用 SQLAlchemy 的 Alembic 迁移工具。详见 [Alembic 文档](https://alembic.sqlalchemy.org)。

**Q: WAL 模式是否安全？**  
A: 是的，WAL 模式在单机环境中完全安全且性能优于默认模式。

**Q: 如何备份数据库？**  
A: 直接备份 `data/app.db` 文件即可。

---

## 相关文档（Related Documentation）

- [快速参考](QUICK_REFERENCE.md) - 常见操作速查表
- [API 参考](API_REFERENCE.md) - 完整 API 文档
- [性能优化指南](OPTIMIZATION_GUIDE.md) - 优化最佳实践

---

## 版本历史（Version History）

**v2.0.0** - 数据库模块简化版本
- 移除 MySQL、PostgreSQL、Redis、MongoDB 支持
- 专注 SQLite 专业级优化
- 增强 CRUD 仓库功能
- 完整的性能优化配置
- 改进文档和示例

---

**最后更新** | 2026 年 1 月 8 日

