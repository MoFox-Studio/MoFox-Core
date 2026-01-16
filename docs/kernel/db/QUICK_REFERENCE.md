# 数据库模块 - 快速参考（Database Module - Quick Reference）

## 🎯 SQLite 核心概念速查表

### SQLite 为什么选择（Why SQLite Only）

```
特点          说明                        优势
───────────────────────────────────────────────────
零配置        无需数据库服务器          快速启动、易于部署
本地存储      直接保存为文件             简单备份、版本管理
WAL 模式      支持并发读写              高效并发处理
ACID 事务     完整事务支持              数据一致性保证
轻量级        库文件 < 1MB              无依赖、易嵌入
性能优化      内存映射、智能缓存        单机最优性能
```

### 应用场景匹配（Use Cases）

```
应用规模        特点                配置建议
──────────────────────────────────────────────
个人项目        数据量小            内存或文件数据库
小型应用        单机部署            文件数据库 + WAL
原型开发        快速迭代            内存数据库
学习测试        无需基础设施        内存数据库
单机应用        完整功能            文件数据库 + 优化
```

---

## 🚀 常见操作速查（Common Operations）

### 1. 创建引擎（Create Engine）

**快速开始（推荐）**
```python
from kernel.db.core import create_sqlite_engine

# 文件数据库
engine = create_sqlite_engine("data/app.db")

# 内存数据库（测试）
engine = create_sqlite_engine(":memory:")
```

**高级配置（生产）**
```python
from kernel.db.core import create_sqlite_engine

engine = create_sqlite_engine(
    database="data/prod.db",
    pool_size=20,              # 连接池大小
    pool_timeout=60,           # 超时时间（秒）
    enable_wal=True,           # WAL 日志模式
    enable_foreign_keys=True,  # 外键约束
    journal_mode="WAL",
    synchronous="NORMAL",
    timeout=30
)
```

### 2. CRUD 基础操作（CRUD Basics）

```python
from kernel.db.api import SQLAlchemyCRUDRepository, QuerySpec

# 初始化仓库
repo = SQLAlchemyCRUDRepository(session_mgr)

# 创建（Create）
with repo.session_scope() as session:
    user = repo.add(session, User(name="Alice"), flush=True)

# 读取（Read）
with repo.session_scope() as session:
    user = repo.get(session, User, 1)
    users = repo.list(session, User)

# 更新（Update）
with repo.session_scope() as session:
    repo.update_fields(session, user, {"name": "Bob"})

# 删除（Delete）
with repo.session_scope() as session:
    repo.delete(session, user)
```

### 3. 批量操作（Batch Operations）

```python
# 批量插入
with repo.session_scope() as session:
    users = [User(name=f"user{i}") for i in range(100)]
    repo.add_many(session, users, flush=True)

# 批量删除
with repo.session_scope() as session:
    spec = QuerySpec(filters=[User.status == "inactive"])
    count = repo.delete_many(session, User, spec)
    print(f"删除了 {count} 条记录")
```

### 4. 查询操作（Query Operations）

**基础列表**
```python
with repo.session_scope() as session:
    all_users = repo.list(session, User)
```

**带过滤**
```python
with repo.session_scope() as session:
    spec = QuerySpec(
        filters=[User.status == "active"]
    )
    active_users = repo.list(session, User, spec)
```

**复杂查询**
```python
with repo.session_scope() as session:
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
    results = repo.list(session, User, spec)
```

**分页**
```python
page_size = 20
page = 1

spec = QuerySpec(
    limit=page_size,
    offset=(page - 1) * page_size
)
items = repo.list(session, User, spec)
total = repo.count(session, User)
pages = (total + page_size - 1) // page_size
```

### 5. 统计操作（Statistics）

```python
with repo.session_scope() as session:
    # 总数
    total = repo.count(session, User)
    
    # 条件计数
    active_count = repo.count(
        session,
        User,
        QuerySpec(filters=[User.status == "active"])
    )
    
    # 存在性检查
    exists = repo.exists(
        session,
        User,
        QuerySpec(filters=[User.email == "alice@example.com"])
    )
```

---

## 📋 QuerySpec 常用过滤表达式（Common Filters）

```python
from kernel.db.api import QuerySpec

# 基本比较
QuerySpec(filters=[User.id == 1])                    # 等于
QuerySpec(filters=[User.id != 1])                    # 不等于
QuerySpec(filters=[User.age > 18])                   # 大于
QuerySpec(filters=[User.age >= 18])                  # 大于等于
QuerySpec(filters=[User.age < 65])                   # 小于
QuerySpec(filters=[User.age <= 65])                  # 小于等于

# 字符串操作
QuerySpec(filters=[User.name.like("A%")])            # 模糊匹配
QuerySpec(filters=[User.name.ilike("a%")])           # 不区分大小写
QuerySpec(filters=[User.email.contains("@example")]) # 包含

# 范围检查
QuerySpec(filters=[User.age.between(18, 65)])        # 范围内

# 多条件（AND）
QuerySpec(filters=[
    User.status == "active",
    User.age >= 18
])

# NULL 检查
QuerySpec(filters=[User.deleted_at == None])         # IS NULL
QuerySpec(filters=[User.deleted_at != None])         # IS NOT NULL

# 排序
QuerySpec(order_by=[User.created_at.desc()])         # 降序
QuerySpec(order_by=[User.created_at.asc()])          # 升序
QuerySpec(order_by=[User.created_at.desc(), User.id.asc()])  # 多字段
```

---

## 🔄 事务模式（Transaction Patterns）

**基础事务**
```python
with repo.session_scope() as session:
    obj = repo.add(session, MyModel())
    # 自动提交或在异常时回滚
```

**异常处理**
```python
from kernel.db.core import SessionError

try:
    with repo.session_scope() as session:
        obj1 = repo.add(session, Model1())
        obj2 = repo.add(session, Model2())
except SessionError as e:
    logger.error(f"事务失败: {e}")
```

**多对象操作**
```python
with repo.session_scope() as session:
    obj1 = repo.add(session, Model1())
    obj2 = repo.add(session, Model2())
    obj3 = repo.add(session, Model3())
    # 所有操作一起提交或都回滚
```

---

## ⚠️ 常见错误与解决（Common Issues）

### 问题 1：唯一约束冲突
```python
from sqlalchemy.exc import IntegrityError

try:
    with repo.session_scope() as session:
        user = repo.add(session, User(email="duplicate@example.com"))
except IntegrityError as e:
    logger.error(f"邮箱已存在")
```

### 问题 2：操作在会话外
```python
# ❌ 错误
user = repo.get(session, User, 1)  # session 已关闭

# ✓ 正确
with repo.session_scope() as session:
    user = repo.get(session, User, 1)
```

### 问题 3：数据库锁定
```python
# SQLite 在并发时可能锁定
# 解决：增加 timeout 参数
engine = create_sqlite_engine(
    database="data/app.db",
    timeout=30  # 等待 30 秒
)
```

### 问题 4：内存溢出
```python
# ❌ 错误：100万条数据全在内存
all_users = repo.list(session, User)

# ✓ 正确：分页查询
spec = QuerySpec(limit=1000, offset=offset)
users = repo.list(session, User, spec)
```

---

## 📊 性能优化清单（Performance Checklist）

```
引擎配置
□ 启用 WAL 模式（enable_wal=True）
□ 启用外键约束（enable_foreign_keys=True）
□ 设置合适连接池（pool_size=20）
□ 设置适当超时（timeout=30）

查询优化
□ 使用分页（limit + offset）
□ 使用过滤（filters）
□ 使用排序（order_by）
□ 添加数据库索引

操作优化
□ 使用批量操作（add_many, delete_many）
□ 使用事务作用域（session_scope）
□ 避免 N+1 查询
□ 定期运行 VACUUM

监控维护
□ 监控数据库大小
□ 监控慢查询
□ 定期备份
□ 检查日志
```

---

## 🛠️ EngineConfig 参数速查（Config Parameters）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| database | str | 必需 | 数据库文件路径或 `:memory:` |
| echo | bool | False | 启用 SQL 日志 |
| pool_size | int | 10 | 连接池大小 |
| pool_timeout | int | 30 | 获取连接超时（秒） |
| enable_wal | bool | True | 启用 WAL 日志模式 |
| enable_foreign_keys | bool | True | 启用外键约束 |
| journal_mode | str | WAL | 日志模式 |
| synchronous | str | NORMAL | 同步级别 |
| timeout | int | 20 | 数据库锁超时 |

---

## 📚 完整示例（Complete Example）

```python
from kernel.db.core import create_sqlite_engine, SessionManager
from kernel.db.api import SQLAlchemyCRUDRepository, QuerySpec
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

# 定义模型
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

# 初始化
engine = create_sqlite_engine("data/app.db")
session_mgr = SessionManager(engine)
repo = SQLAlchemyCRUDRepository(session_mgr)

# 使用示例
with repo.session_scope() as session:
    # 添加用户
    user = repo.add(session, User(name="Alice", email="alice@example.com"))
    
    # 查询用户
    spec = QuerySpec(
        filters=[User.status == "active"],
        order_by=[User.created_at.desc()],
        limit=10
    )
    users = repo.list(session, User, spec)
    
    # 统计
    total = repo.count(session, User)
    
    # 更新
    repo.update_fields(session, user, {"status": "inactive"})
    
    # 删除
    repo.delete(session, user)
```

---

## 💡 最佳实践速记（Best Practices）

**✅ DO：**
- 使用 `with repo.session_scope()` 管理事务
- 对大数据集使用分页查询
- 为常用条件建立索引
- 使用 QuerySpec 统一查询接口
- 启用 WAL 模式进行并发读取

**❌ DON'T：**
- 不在事务外保持长连接
- 不一次性加载所有数据
- 不跳过连接池配置
- 不忽视外键约束
- 不在没有过滤的情况下删除数据

---

## 🔗 相关文档（See Also）

- [完整文档](README.md) - 详细设计和解释
- [性能优化指南](OPTIMIZATION_GUIDE.md) - 高级优化技巧
- [API 参考](API_REFERENCE.md) - 完整 API 文档

---

**版本** | v2.0.0 | **更新** | 2026年1月8日
