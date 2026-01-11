# 数据库模块 - API 参考（Database Module - API Reference）

## 目录（Table of Contents）

- [核心模块](#核心模块)
- [EngineConfig](#engineconfig)
- [EngineManager](#enginemanager)
- [SessionManager](#sessionmanager)
- [SQLAlchemyCRUDRepository](#sqlalchemycrudrepository)
- [QuerySpec](#queryspec)
- [异常类](#异常类)

---

## 核心模块

### 导入

```python
# 核心引擎和会话
from kernel.db.core import (
    EngineConfig,
    EngineManager,
    SessionManager,
    create_sqlite_engine
)

# CRUD 和查询
from kernel.db.api import (
    SQLAlchemyCRUDRepository,
    QuerySpec
)

# 异常处理
from kernel.db.core import (
    DatabaseError,
    EngineAlreadyExistsError,
    EngineNotInitializedError,
    SessionError
)
```

---

## EngineConfig

SQLite 引擎配置类。

### 类定义

```python
@dataclass
class EngineConfig:
    """SQLite 引擎配置"""
    database: str
    echo: bool = False
    pool_size: int = 10
    pool_timeout: int = 30
    connect_args: Dict[str, Any] = field(default_factory=dict)
    create_if_missing: bool = True
    enable_wal: bool = True
    enable_foreign_keys: bool = True
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    timeout: int = 20
```

### 属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `database` | str | 必需 | 数据库文件路径或 `:memory:` |
| `echo` | bool | False | 启用 SQL 语句日志输出 |
| `pool_size` | int | 10 | 连接池大小 |
| `pool_timeout` | int | 30 | 获取连接的超时时间（秒） |
| `connect_args` | Dict | {} | 额外的连接参数 |
| `create_if_missing` | bool | True | 数据库文件不存在时自动创建 |
| `enable_wal` | bool | True | 启用 WAL 日志模式（推荐） |
| `enable_foreign_keys` | bool | True | 启用外键约束 |
| `journal_mode` | str | WAL | 日志模式（WAL/DELETE） |
| `synchronous` | str | NORMAL | 同步级别（OFF/NORMAL/FULL） |
| `timeout` | int | 20 | 数据库锁定超时（秒） |

### 属性方法

```python
@property
def is_memory(self) -> bool:
    """检查是否为内存数据库"""
```

### 示例

```python
# 文件数据库
config = EngineConfig(
    database="data/app.db",
    pool_size=20,
    enable_wal=True
)

# 内存数据库
config = EngineConfig(
    database=":memory:",
    pool_size=1
)

# 自定义配置
config = EngineConfig(
    database="data/prod.db",
    echo=False,
    pool_size=30,
    pool_timeout=60,
    enable_wal=True,
    enable_foreign_keys=True,
    journal_mode="WAL",
    synchronous="NORMAL",
    timeout=30
)
```

---

## EngineManager

数据库引擎管理器，负责创建和管理引擎实例。

### 类定义

```python
class EngineManager:
    """SQLite 数据库引擎管理器"""
    
    def __init__(self) -> None:
        """初始化引擎管理器"""
    
    def create(self, config: EngineConfig, name: Optional[str] = None) -> Engine:
        """创建并注册引擎"""
    
    def get(self, name: Optional[str] = None) -> Engine:
        """按名称获取已注册的引擎"""
    
    def dispose(self, name: Optional[str] = None) -> None:
        """释放指定的引擎"""
    
    def dispose_all(self) -> None:
        """释放所有引擎"""
    
    def list_engines(self) -> Mapping[str, Engine]:
        """列出所有已注册的引擎"""
```

### 方法详解

#### `__init__()`

初始化引擎管理器。

```python
manager = EngineManager()
```

#### `create(config, name="default")`

创建并注册一个新的引擎。

**参数：**
- `config` (EngineConfig): 引擎配置
- `name` (str, optional): 引擎注册名称，默认为 "default"

**返回：**
- (Engine): SQLAlchemy 引擎实例

**异常：**
- `EngineAlreadyExistsError`: 同名引擎已存在

```python
manager = EngineManager()
config = EngineConfig(database="data/app.db")
engine = manager.create(config, name="main")
```

#### `get(name="default")`

获取已注册的引擎。

**参数：**
- `name` (str, optional): 引擎注册名称

**返回：**
- (Engine): SQLAlchemy 引擎实例

**异常：**
- `EngineNotInitializedError`: 引擎未初始化

```python
engine = manager.get("main")
```

#### `dispose(name="default")`

释放指定的引擎及其连接池。

**参数：**
- `name` (str, optional): 引擎注册名称

```python
manager.dispose("main")
```

#### `dispose_all()`

释放所有已注册的引擎。

```python
manager.dispose_all()
```

#### `list_engines()`

获取所有已注册引擎的字典。

**返回：**
- (Mapping[str, Engine]): 引擎字典

```python
engines = manager.list_engines()
for name, engine in engines.items():
    print(f"{name}: {engine}")
```

### 示例

```python
# 创建和管理多个引擎
manager = EngineManager()

# 创建主数据库
config1 = EngineConfig(database="data/main.db")
main_engine = manager.create(config1, name="main")

# 创建测试数据库
config2 = EngineConfig(database=":memory:")
test_engine = manager.create(config2, name="test")

# 获取引擎
engine = manager.get("main")

# 清理资源
manager.dispose("test")
manager.dispose_all()
```

---

## SessionManager

数据库会话管理器，负责事务管理和资源释放。

### 类定义

```python
class SessionManager:
    """数据库会话和事务管理器"""
    
    def __init__(self, engine: Engine) -> None:
        """初始化会话管理器"""
    
    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """获取事务作用域上下文"""
```

### 方法详解

#### `__init__(engine)`

初始化会话管理器。

**参数：**
- `engine` (Engine): SQLAlchemy 引擎实例

```python
from kernel.db.core import SessionManager

session_mgr = SessionManager(engine)
```

#### `session_scope()`

获取事务作用域上下文管理器。自动处理事务的提交和回滚。

**返回：**
- Iterator[Session]: SQLAlchemy 会话对象

**行为：**
- 如果代码块成功执行，自动提交事务
- 如果发生异常，自动回滚事务
- 退出时自动关闭会话

```python
with session_mgr.session_scope() as session:
    obj = session.add(MyModel())
    # 成功时自动提交，异常时自动回滚
```

### 示例

```python
session_mgr = SessionManager(engine)

# 单个操作
with session_mgr.session_scope() as session:
    obj = session.add(MyModel(name="test"))

# 多个操作
with session_mgr.session_scope() as session:
    obj1 = session.add(Model1())
    obj2 = session.add(Model2())
    # 都提交或都回滚

# 异常处理
try:
    with session_mgr.session_scope() as session:
        obj = session.add(MyModel())
except Exception as e:
    logger.error(f"事务失败: {e}")
```

---

## SQLAlchemyCRUDRepository

CRUD 仓库实现，提供数据库操作的统一接口。

### 类定义

```python
class SQLAlchemyCRUDRepository(CRUDRepository[ModelT]):
    """SQLAlchemy CRUD 仓库实现"""
    
    def __init__(self, session_manager: SessionManager) -> None:
        """初始化 CRUD 仓库"""
    
    def add(self, session: Session, obj: ModelT, *, flush: bool = False) -> ModelT:
        """添加单个对象"""
    
    def add_many(self, session: Session, objs: Sequence[ModelT], *, flush: bool = False) -> Sequence[ModelT]:
        """添加多个对象"""
    
    def get(self, session: Session, model: Type[ModelT], obj_id: Any) -> Optional[ModelT]:
        """按 ID 获取单个对象"""
    
    def list(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> Sequence[ModelT]:
        """列表查询"""
    
    def delete(self, session: Session, obj: ModelT) -> None:
        """删除单个对象"""
    
    def delete_many(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> int:
        """删除多个对象"""
    
    def update_fields(self, session: Session, obj: ModelT, fields: dict[str, Any]) -> ModelT:
        """更新对象字段"""
    
    def count(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> int:
        """统计对象数量"""
    
    def exists(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> bool:
        """检查对象是否存在"""
    
    def session_scope(self):
        """获取会话作用域"""
```

### 方法详解

#### `add(session, obj, *, flush=False)`

添加单个对象到数据库。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `obj` (ModelT): 要添加的模型实例
- `flush` (bool): 是否立即刷新到数据库

**返回：**
- (ModelT): 添加的对象

```python
with repo.session_scope() as session:
    user = repo.add(session, User(name="Alice"), flush=True)
```

#### `add_many(session, objs, *, flush=False)`

批量添加多个对象。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `objs` (Sequence[ModelT]): 对象列表
- `flush` (bool): 是否立即刷新到数据库

**返回：**
- (Sequence[ModelT]): 添加的对象列表

```python
with repo.session_scope() as session:
    users = [User(name=f"user{i}") for i in range(100)]
    repo.add_many(session, users, flush=True)
```

#### `get(session, model, obj_id)`

按主键 ID 获取单个对象。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `model` (Type[ModelT]): 模型类
- `obj_id` (Any): 对象的主键值

**返回：**
- (Optional[ModelT]): 找到则返回对象，否则返回 None

```python
with repo.session_scope() as session:
    user = repo.get(session, User, 1)
```

#### `list(session, model, query_spec=None)`

列表查询对象。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `model` (Type[ModelT]): 模型类
- `query_spec` (QuerySpec, optional): 查询规约

**返回：**
- (Sequence[ModelT]): 对象列表

```python
with repo.session_scope() as session:
    # 基础列表
    users = repo.list(session, User)
    
    # 带查询规约
    spec = QuerySpec(
        filters=[User.status == "active"],
        order_by=[User.created_at.desc()],
        limit=10
    )
    active_users = repo.list(session, User, spec)
```

#### `delete(session, obj)`

删除单个对象。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `obj` (ModelT): 要删除的对象

```python
with repo.session_scope() as session:
    user = repo.get(session, User, 1)
    repo.delete(session, user)
```

#### `delete_many(session, model, query_spec=None)`

批量删除多个对象。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `model` (Type[ModelT]): 模型类
- `query_spec` (QuerySpec, optional): 查询规约

**返回：**
- (int): 删除的对象数量

```python
with repo.session_scope() as session:
    spec = QuerySpec(filters=[User.is_deleted == True])
    count = repo.delete_many(session, User, spec)
```

#### `update_fields(session, obj, fields)`

更新对象的多个字段。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `obj` (ModelT): 要更新的对象
- `fields` (dict): 字段字典 {字段名: 新值}

**返回：**
- (ModelT): 更新后的对象

```python
with repo.session_scope() as session:
    user = repo.get(session, User, 1)
    repo.update_fields(session, user, {
        "name": "Bob",
        "status": "inactive"
    })
```

#### `count(session, model, query_spec=None)`

统计对象数量。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `model` (Type[ModelT]): 模型类
- `query_spec` (QuerySpec, optional): 查询规约

**返回：**
- (int): 对象数量

```python
with repo.session_scope() as session:
    total = repo.count(session, User)
    active_count = repo.count(
        session,
        User,
        QuerySpec(filters=[User.status == "active"])
    )
```

#### `exists(session, model, query_spec=None)`

检查对象是否存在。

**参数：**
- `session` (Session): SQLAlchemy 会话对象
- `model` (Type[ModelT]): 模型类
- `query_spec` (QuerySpec, optional): 查询规约

**返回：**
- (bool): 存在则为 True

```python
with repo.session_scope() as session:
    exists = repo.exists(
        session,
        User,
        QuerySpec(filters=[User.email == "alice@example.com"])
    )
```

#### `session_scope()`

获取会话作用域上下文。

**返回：**
- 事务上下文管理器

```python
with repo.session_scope() as session:
    obj = repo.add(session, MyModel())
```

---

## QuerySpec

查询规约类，用于统一的查询接口。

### 类定义

```python
@dataclass
class QuerySpec:
    """SQLAlchemy 查询规约"""
    filters: Union[List[object], dict] = field(default_factory=list)
    order_by: Union[List[object], List[tuple]] = field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None
    projection: Optional[dict] = None
```

### 属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `filters` | List or Dict | [] | 过滤条件列表 |
| `order_by` | List | [] | 排序条件列表 |
| `limit` | int | None | 结果数量限制 |
| `offset` | int | None | 结果偏移量 |
| `projection` | dict | None | 字段投影（预留） |

### 示例

```python
from kernel.db.api import QuerySpec

# 基础查询
spec = QuerySpec()

# 带过滤
spec = QuerySpec(
    filters=[User.status == "active"]
)

# 复杂查询
spec = QuerySpec(
    filters=[
        User.status == "active",
        User.age >= 18,
        User.is_deleted == False
    ],
    order_by=[User.created_at.desc()],
    limit=20,
    offset=0
)

# 分页
page = 1
page_size = 20
spec = QuerySpec(
    limit=page_size,
    offset=(page - 1) * page_size
)
```

---

## 异常类

### DatabaseError

基础数据库异常。

```python
from kernel.db.core import DatabaseError

try:
    # 数据库操作
    pass
except DatabaseError as e:
    logger.error(f"数据库错误: {e}")
```

### EngineAlreadyExistsError

引擎已存在异常。

```python
from kernel.db.core import EngineAlreadyExistsError

try:
    engine = manager.create(config, name="main")
    engine = manager.create(config, name="main")  # 抛出异常
except EngineAlreadyExistsError as e:
    logger.error(f"引擎已存在: {e}")
```

### EngineNotInitializedError

引擎未初始化异常。

```python
from kernel.db.core import EngineNotInitializedError

try:
    engine = manager.get("non_existent")  # 抛出异常
except EngineNotInitializedError as e:
    logger.error(f"引擎未初始化: {e}")
```

### SessionError

会话异常。

```python
from kernel.db.core import SessionError

try:
    with repo.session_scope() as session:
        obj = repo.add(session, MyModel())
except SessionError as e:
    logger.error(f"会话错误: {e}")
```

---

## 便捷函数

### create_sqlite_engine

创建 SQLite 引擎的便捷函数。

```python
def create_sqlite_engine(
    database: str,
    name: str = "default",
    echo: bool = False,
    pool_size: int = 10,
    pool_timeout: int = 30,
    enable_wal: bool = True,
    enable_foreign_keys: bool = True,
    journal_mode: str = "WAL",
    synchronous: str = "NORMAL",
    timeout: int = 20,
    connect_args: Optional[Dict[str, object]] = None,
) -> Engine:
    """创建并注册 SQLite 引擎"""
```

**参数：**
- `database` (str): 数据库文件路径或 `:memory:`
- `name` (str): 引擎注册名称，默认为 "default"
- `echo` (bool): 启用 SQL 日志
- `pool_size` (int): 连接池大小
- `pool_timeout` (int): 连接超时
- `enable_wal` (bool): 启用 WAL 模式
- `enable_foreign_keys` (bool): 启用外键约束
- `journal_mode` (str): 日志模式
- `synchronous` (str): 同步级别
- `timeout` (int): 锁定超时
- `connect_args` (dict): 额外连接参数

**返回：**
- (Engine): SQLAlchemy 引擎实例

```python
from kernel.db.core import create_sqlite_engine

# 快速创建
engine = create_sqlite_engine("data/app.db")

# 完整配置
engine = create_sqlite_engine(
    database="data/prod.db",
    pool_size=20,
    enable_wal=True,
    timeout=30
)
```

---

## 完整工作流示例

```python
from kernel.db.core import create_sqlite_engine, SessionManager
from kernel.db.api import SQLAlchemyCRUDRepository, QuerySpec
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

# 1. 定义模型
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True)

# 2. 创建引擎
engine = create_sqlite_engine("data/app.db")

# 3. 创建会话管理器和仓库
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

# 4. 使用仓库
with repo.session_scope() as session:
    # 添加
    user = repo.add(session, User(name="Alice", email="alice@example.com"))
    
    # 查询
    all_users = repo.list(session, User)
    
    # 统计
    total = repo.count(session, User)
    
    # 更新
    repo.update_fields(session, user, {"name": "Bob"})
    
    # 删除
    repo.delete(session, user)
```

---

**版本** | v2.0.0 | **更新** | 2026年1月8日
