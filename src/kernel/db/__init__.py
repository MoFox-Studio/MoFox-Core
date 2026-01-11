"""SQLite 数据库模块：完整、强大的 SQLite ORM 和 CRUD 接口
SQLite Database Module: Comprehensive and powerful SQLite ORM and CRUD interface.

核心功能 Core Features:
- ✅ SQLite 引擎管理：支持文件和内存数据库 (SQLite engine management)
- ✅ 事务和会话管理：自动提交/回滚 (Transaction and session management)
- ✅ 完整 CRUD API：8 个数据库操作方法 (Complete CRUD API with 8 operations)
- ✅ 灵活查询规约：过滤、排序、分页 (Flexible query spec with filtering, sorting, pagination)
- ✅ SQLAlchemy 2.x 整合：现代 ORM 框架 (SQLAlchemy 2.x integration)
- ✅ 性能优化：WAL、缓存、内存映射 I/O (Performance optimizations)

使用示例 Quick Start Example:
    from kernel.db import EngineManager, create_sqlite_engine, SQLAlchemyCRUDRepository
    from kernel.db import SessionManager, QuerySpec
    
    # 创建引擎
    engine = create_sqlite_engine(
        database="path/to/app.db",
        enable_wal=True,
        pool_size=10
    )
    
    # 初始化管理器
    manager = EngineManager()
    manager.register_engine("default", engine)
    session_manager = SessionManager(engine)
    
    # 使用 CRUD 仓库
    repo = SQLAlchemyCRUDRepository(session_manager)
    
    with session_manager.session_scope() as session:
        # 添加数据
        repo.add(session, user_obj)
        
        # 查询数据
        spec = QuerySpec(
            filters=[User.status == "active"],
            order_by=[User.created_at.desc()],
            limit=10
        )
        users = repo.list(session, User, spec)
        
        # 更新数据
        repo.update_fields(session, user_obj, {"name": "New Name"})
        
        # 删除数据
        repo.delete(session, user_obj)

导入说明 Import Reference:

1. 核心引擎模块 Core Engine Module:
   - EngineManager: 多引擎管理器
   - EngineConfig: 引擎配置类
   - create_sqlite_engine: SQLite 引擎工厂函数
   - SQLiteAdapter: SQLite 方言适配器

2. 会话模块 Session Module:
   - SessionManager: 事务和会话管理

3. CRUD API 模块 CRUD API Module:
   - CRUDRepository: CRUD 基础接口
   - SQLAlchemyCRUDRepository: SQLAlchemy CRUD 实现

4. 查询模块 Query Module:
   - QuerySpec: 查询规约数据类
   - apply_query_spec: 查询规约应用函数

5. 异常模块 Exceptions Module:
   - DatabaseError: 基础数据库错误
   - EngineAlreadyExistsError: 引擎已存在错误
   - EngineNotInitializedError: 引擎未初始化错误
   - SessionError: 会话错误
"""

from __future__ import annotations

# 核心引擎和会话管理 Core Engine and Session Management
from .core import (
    EngineManager,
    EngineConfig,
    SQLiteAdapter,
    SessionManager,
    create_sqlite_engine,
    DatabaseError,
    EngineAlreadyExistsError,
    EngineNotInitializedError,
    SessionError,
)

# CRUD 和查询接口 CRUD and Query Interface
from .api import (
    CRUDRepository,
    SQLAlchemyCRUDRepository,
    QuerySpec,
    apply_query_spec,
)

__all__ = [
    # 核心引擎管理 / Core engine management
    "EngineManager",
    "EngineConfig",
    "SQLiteAdapter",
    "SessionManager",
    "create_sqlite_engine",
    
    # CRUD 仓库 / CRUD repository
    "CRUDRepository",
    "SQLAlchemyCRUDRepository",
    
    # 查询规约 / Query specification
    "QuerySpec",
    "apply_query_spec",
    
    # 异常类 / Exception classes
    "DatabaseError",
    "EngineAlreadyExistsError",
    "EngineNotInitializedError",
    "SessionError",
]
