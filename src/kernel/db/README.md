# 数据库内核源代码说明

## 特性

- 🗄️ **专业级 SQLite 支持**：优化的 SQLite 配置，支持文件和内存模式
- 🔄 **事务管理**：自动提交/回滚，异常安全
- 📦 **CRUD 封装**：简洁而强大的增删改查接口
- 🔍 **查询规约**：统一的过滤、排序、分页机制
- 🎯 **仓库模式**：基于 SQLAlchemy 的标准化数据库操作
- 📝 **日志集成**：与 Logger 模块深度集成，自动记录所有数据库操作
- ⚡ **性能优化**：WAL 日志模式、连接池、内存映射 I/O、自动真空

## 目录结构

```
db/
├── core/                    # 数据库引擎核心
│   ├── dialect_adapter.py  # SQLite 适配器与配置
│   ├── engine.py           # 引擎管理与创建
│   ├── session.py          # 事务会话管理
│   ├── exceptions.py       # 数据库异常定义
│   └── __init__.py
├── api/                     # 对外 CRUD/查询接口
│   ├── crud.py             # CRUD 仓库实现
│   ├── query.py            # 查询规约
│   └── __init__.py
└── README.md
```

## 核心能力

- **SQLite 引擎**：文件和内存数据库支持，自动目录创建
- **性能配置**：WAL 模式、智能缓存、内存映射 I/O、增量真空
- **事务作用域**：自动提交/回滚、异常安全
- **CRUD 操作**：增、删、改、查、批量操作、计数、存在性检查
- **查询功能**：过滤、排序、分页、统一接口

## 快速使用示例

### 基础 SQLite 设置

```python
from kernel.db.core import create_sqlite_engine, SessionManager, EngineConfig
from kernel.db.api import SQLAlchemyCRUDRepository, QuerySpec

# 方式 1：使用便捷函数（推荐）
engine = create_sqlite_engine("data/app.db")

# 方式 2：使用 EngineManager 和 EngineConfig
from kernel.db.core import EngineManager, EngineConfig

config = EngineConfig(
    database="data/app.db",
    enable_wal=True,
    enable_foreign_keys=True,
    pool_size=10
)
manager = EngineManager()
engine = manager.create(config)

# 创建会话管理和仓库
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

# 使用事务作用域进行 CRUD 操作
with repo.session_scope() as session:
    # 添加对象
    obj = repo.add(session, MyModel(name="demo"), flush=True)
    
    # 列表查询
    query_spec = QuerySpec(
        filters=[MyModel.status == "active"],
        order_by=[MyModel.created_at.desc()],
        limit=10,
        offset=0
    )
    rows = repo.list(session, MyModel, query_spec)
    
    # 计数
    count = repo.count(session, MyModel, query_spec)
    
    # 按 ID 获取
    item = repo.get(session, MyModel, 1)
    
    # 更新字段
    repo.update_fields(session, obj, {"status": "inactive"})
    
    # 删除
    repo.delete(session, obj)
    
    # 事务自动提交
```

### 内存数据库（测试）

```python
from kernel.db.core import create_sqlite_engine
from kernel.db.core import SessionManager
from kernel.db.api import SQLAlchemyCRUDRepository

# 创建内存数据库
engine = create_sqlite_engine(":memory:")
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

# 使用方式相同...
with repo.session_scope() as session:
    obj = repo.add(session, MyModel(name="test"))
```

### 高级配置

```python
from kernel.db.core import create_sqlite_engine

engine = create_sqlite_engine(
    database="data/prod.db",
    pool_size=20,              # 连接池大小
    pool_timeout=60,           # 超时时间（秒）
    enable_wal=True,           # 启用 WAL 日志模式
    enable_foreign_keys=True,  # 启用外键约束
    journal_mode="WAL",        # 日志模式
    synchronous="NORMAL",      # 同步模式（NORMAL/FULL/OFF）
    timeout=20,                # SQLite 锁超时（秒）
    echo=False                 # SQL 日志输出
)
```

## EngineConfig 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `database` | str | 必需 | 数据库文件路径或 `:memory:` |
| `echo` | bool | False | 启用 SQL 语句日志 |
| `pool_size` | int | 10 | 连接池大小 |
| `pool_timeout` | int | 30 | 连接获取超时（秒） |
| `enable_wal` | bool | True | 启用 WAL 日志模式 |
| `enable_foreign_keys` | bool | True | 启用外键约束 |
| `journal_mode` | str | WAL | 日志模式（WAL/DELETE/TRUNCATE） |
| `synchronous` | str | NORMAL | 同步级别（OFF/NORMAL/FULL） |
| `timeout` | int | 20 | 数据库锁超时（秒） |
| `connect_args` | dict | {} | 额外的连接参数 |

## SQLAlchemy ORM 定义示例

```python
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)
```

## CRUD 操作详解

### 添加单个对象

```python
with repo.session_scope() as session:
    user = User(name="Alice", email="alice@example.com")
    repo.add(session, user, flush=True)
    # 事务提交时完整保存
```

### 批量添加对象

```python
with repo.session_scope() as session:
    users = [
        User(name="Bob", email="bob@example.com"),
        User(name="Charlie", email="charlie@example.com"),
    ]
    repo.add_many(session, users, flush=True)
```

### 查询操作

```python
from kernel.db.api import QuerySpec

with repo.session_scope() as session:
    # 基础查询
    all_users = repo.list(session, User)
    
    # 带过滤的查询
    active_users = repo.list(
        session, 
        User, 
        QuerySpec(filters=[User.status == "active"])
    )
    
    # 复杂查询
    spec = QuerySpec(
        filters=[
            User.status == "active",
            User.is_deleted == False
        ],
        order_by=[User.created_at.desc()],
        limit=20,
        offset=0
    )
    results = repo.list(session, User, spec)
```

### 更新操作

```python
with repo.session_scope() as session:
    user = repo.get(session, User, 1)
    repo.update_fields(session, user, {
        "name": "Alice Updated",
        "status": "inactive"
    })
```

### 删除操作

```python
with repo.session_scope() as session:
    # 删除单个对象
    user = repo.get(session, User, 1)
    repo.delete(session, user)
    
    # 删除符合条件的多个对象
    spec = QuerySpec(filters=[User.is_deleted == True])
    repo.delete_many(session, User, spec)
```

### 计数和存在性检查

```python
with repo.session_scope() as session:
    # 统计所有用户
    total = repo.count(session, User)
    
    # 统计活跃用户
    active_count = repo.count(
        session, 
        User, 
        QuerySpec(filters=[User.status == "active"])
    )
    
    # 检查是否存在
    exists = repo.exists(
        session, 
        User, 
        QuerySpec(filters=[User.email == "alice@example.com"])
    )
```

## 错误处理

```python
from kernel.db.core import (
    EngineAlreadyExistsError,
    EngineNotInitializedError,
    SessionError
)

try:
    with repo.session_scope() as session:
        obj = repo.add(session, MyModel())
except SessionError as e:
    logger.error(f"会话错误: {e}")
except Exception as e:
    # 事务会自动回滚
    logger.error(f"操作失败: {e}")
```

## 性能优化配置

### WAL 模式优势
- **并发性**：允许读操作同时进行的写操作
- **性能**：减少磁盘 I/O，提高写入吞吐量
- **可靠性**：改进数据安全性

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
    timeout=30,
    echo=False
)
```

## 日志集成

数据库模块已与 Logger 模块深度集成，所有数据库操作都会自动记录。

### 自动记录的操作

**会话管理**
- ✅ 会话创建：记录会话ID
- ✅ 事务提交：记录执行时长、状态
- ✅ 事务回滚：记录错误信息、堆栈跟踪
- ✅ 会话关闭：记录会话生命周期

**CRUD 操作**
- ✅ 添加记录：记录模型名称、是否 flush
- ✅ 查询记录：记录模型名称、查询条件、结果数量
- ✅ 更新记录：记录更新的字段、字段数量
- ✅ 删除记录：记录删除的模型

### 日志元数据

每条数据库操作日志都包含：

```python
{
    "session_id": "session_123456",
    "operation": "add",
    "model": "User",
    "duration": 0.123,
    "status": "committed",
    "level": "INFO",
    "timestamp": "2026-01-06T10:30:45"
}
```

### 使用日志集成

#### 方式 1：使用 Logger-Storage 集成（推荐）

```python
from kernel.logger.storage_integration import LoggerWithStorage

# 初始化日志系统
logger_system = LoggerWithStorage(app_name="myapp")

# 使用数据库
from kernel.db.core import create_sqlite_engine, SessionManager
from kernel.db.api import SQLAlchemyCRUDRepository

engine = create_sqlite_engine("data/app.db")
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

with repo.session_scope() as session:
    # 所有操作自动记录日志
    user = repo.add(session, User(name="Alice"), flush=True)
    users = repo.list(session, User)

# 查询数据库操作日志
db_logs = logger_system.log_store.get_logs(
    filter_func=lambda log: 'session_id' in log
)

# 分析慢查询
slow_queries = [
    log for log in db_logs
    if log.get('duration', 0) > 1.0  # 超过1秒
]
```

#### 方式 2：仅使用标准 Logger

```python
from kernel.logger import setup_logger

# 初始化标准 Logger（控制台 + 文件）
setup_logger()

# 使用数据库（自动记录到日志）
with repo.session_scope() as session:
    user = repo.add(session, User(name="Bob"), flush=True)
```

## 相关文档

- [性能优化指南](../../docs/kernel/db/OPTIMIZATION_GUIDE.md)
- [快速参考](../../docs/kernel/db/QUICK_REFERENCE.md)
- [API 参考](../../docs/kernel/db/API_REFERENCE.md)
- [数据库配置指南](../../docs/kernel/db/DATABASE_GUIDE.md)
