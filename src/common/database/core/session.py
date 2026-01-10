"""数据库会话管理

单一职责：提供数据库会话工厂和上下文管理器

支持的数据库类型：
- SQLite: 设置 PRAGMA 参数优化并发
- PostgreSQL: 可选设置 schema 搜索路径
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.common.logger import get_logger

from .engine import get_engine

logger = get_logger("database.session")

# 全局会话工厂
_session_factory: async_sessionmaker | None = None
_factory_lock: asyncio.Lock | None = None


async def get_session_factory() -> async_sessionmaker:
    """获取会话工厂（单例模式）

    Returns:
        async_sessionmaker: SQLAlchemy异步会话工厂
    """
    global _session_factory, _factory_lock

    # 快速路径
    if _session_factory is not None:
        return _session_factory

    # 延迟创建锁
    if _factory_lock is None:
        _factory_lock = asyncio.Lock()

    async with _factory_lock:
        # 双重检查
        if _session_factory is not None:
            return _session_factory

        engine = await get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,  # 避免在commit后访问属性时重新查询
        )

        logger.debug("会话工厂已创建")
        return _session_factory


async def _apply_session_settings(session: AsyncSession, db_type: str) -> None:
    """应用数据库特定的会话设置

    Args:
        session: 数据库会话
        db_type: 数据库类型
    """
    try:
        if db_type == "sqlite":
            # SQLite 特定的 PRAGMA 设置
            # 设置 busy_timeout 与引擎配置一致（120秒）
            await session.execute(text("PRAGMA busy_timeout = 120000"))
            await session.execute(text("PRAGMA foreign_keys = ON"))
        elif db_type == "postgresql":
            # PostgreSQL 特定设置（如果需要）
            # 可以设置 schema 搜索路径等
            from src.config.config import global_config

            assert global_config is not None
            schema = global_config.database.postgresql_schema
            if schema and schema != "public":
                await session.execute(text(f"SET search_path TO {schema}"))
    except Exception:
        # 复用连接时设置可能已存在，忽略错误
        pass


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话上下文管理器

    这是数据库操作的主要入口点，直接从会话工厂获取独立会话。

    支持的数据库：
    - SQLite: 自动设置 busy_timeout 和外键约束
    - PostgreSQL: 支持自定义 schema

    使用示例:
        async with get_db_session() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()

    Yields:
        AsyncSession: SQLAlchemy异步会话对象
    """
    async with get_db_session_direct() as session:
        yield session


@asynccontextmanager
async def get_db_session_direct() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（直接模式，不使用连接池）

    用于特殊场景，如需要完全独立的连接时。
    一般情况下应使用 get_db_session()。

    事务管理说明：
    - 正常退出时自动提交事务
    - 发生异常时自动回滚事务
    - 如果用户代码已手动调用 commit/rollback，再次调用是安全的
    - 适用于所有数据库类型（SQLite, PostgreSQL）

    Yields:
        AsyncSession: SQLAlchemy异步会话对象
    """
    session_factory = await get_session_factory()

    async with session_factory() as session:
        try:
            # 应用数据库特定设置
            from src.config.config import global_config

            assert global_config is not None
            await _apply_session_settings(session, global_config.database.database_type)

            yield session

            # 正常退出时提交事务
            # 这对所有数据库都很重要，因为 SQLAlchemy 默认不是 autocommit 模式
            # 检查事务是否活动，避免在已回滚的事务上提交
            if session.is_active:
                await session.commit()
        except BaseException:
            # 检查是否需要回滚（事务是否活动）
            # 使用 BaseException 以捕获 asyncio.CancelledError，确保超时取消时也能回滚
            if session.is_active:
                await session.rollback()
            raise
        finally:
            await session.close()


async def reset_session_factory():
    """重置会话工厂（用于测试）"""
    global _session_factory
    _session_factory = None
