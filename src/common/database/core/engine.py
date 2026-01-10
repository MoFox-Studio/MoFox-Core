"""数据库引擎管理

单一职责：创建和管理SQLAlchemy异步引擎

支持的数据库类型：
- SQLite: 轻量级本地数据库，使用 aiosqlite 驱动
- PostgreSQL: 功能丰富的开源数据库，使用 asyncpg 驱动
"""

import asyncio
import os
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool  # 🔧 改用 StaticPool 而不是 NullPool

from src.common.logger import get_logger

from ..utils.exceptions import DatabaseInitializationError
from .dialect_adapter import DialectAdapter

logger = get_logger("database.engine")

# 全局引擎实例
_engine: AsyncEngine | None = None
_engine_lock: asyncio.Lock | None = None


async def get_engine() -> AsyncEngine:
    """获取全局数据库引擎（单例模式）

    Returns:
        AsyncEngine: SQLAlchemy异步引擎

    Raises:
        DatabaseInitializationError: 引擎初始化失败
    """
    global _engine, _engine_lock

    # 快速路径：引擎已初始化
    if _engine is not None:
        return _engine

    # 延迟创建锁（避免在导入时创建）
    if _engine_lock is None:
        _engine_lock = asyncio.Lock()

    assert _engine_lock is not None
    # 使用锁保护初始化过程
    async with _engine_lock:
        # 双重检查锁定模式
        if _engine is not None:
            return _engine

        try:
            from src.config.config import global_config

            assert global_config is not None
            config = global_config.database
            db_type = config.database_type

            # 初始化方言适配器
            DialectAdapter.initialize(db_type)

            logger.info(f"正在初始化 {db_type.upper()} 数据库引擎...")

            # 根据数据库类型构建URL和引擎参数
            if db_type == "postgresql":
                url, engine_kwargs = _build_postgresql_config(config)
            else:
                url, engine_kwargs = _build_sqlite_config(config)

            # 创建异步引擎
            _engine = create_async_engine(url, **engine_kwargs)

            # 数据库特定优化
            if db_type == "sqlite":
                await _enable_sqlite_optimizations(_engine)
            elif db_type == "postgresql":
                await _enable_postgresql_optimizations(_engine)

            logger.info(f"{db_type.upper()} 数据库引擎初始化成功")
            return _engine

        except Exception as e:
            logger.error(f"❌ 数据库引擎初始化失败: {e}")
            raise DatabaseInitializationError(f"引擎初始化失败: {e}") from e


def _build_sqlite_config(config) -> tuple[str, dict]:
    """构建 SQLite 配置

    Args:
        config: 数据库配置对象

    Returns:
        (url, engine_kwargs) 元组

    Note:
        SQLite 使用 StaticPool 而非默认的 QueuePool，原因：
        1. StaticPool 复用单个连接，避免频繁创建/销毁连接的开销
        2. 相比 NullPool（每次新建连接），StaticPool 更高效
        3. 相比 QueuePool（多连接池），StaticPool 避免 SQLite 文件锁冲突
        4. 配合 WAL 模式和 busy_timeout，可以很好地处理并发读写
    """
    if not os.path.isabs(config.sqlite_path):
        ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        db_path = os.path.join(ROOT_PATH, config.sqlite_path)
    else:
        db_path = config.sqlite_path

    # 确保数据库目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    url = f"sqlite+aiosqlite:///{db_path}"

    engine_kwargs = {
        "echo": False,
        "future": True,
        # 🔧 使用 StaticPool 复用单个连接，避免 NullPool 的频繁创建开销
        "poolclass": StaticPool,
        # 启用健康检查，发现连接损坏时自动重连
        "pool_pre_ping": True,
        "connect_args": {
            "check_same_thread": False,
            # 增加 timeout，让 SQLite 在遇到锁时等待更长时间
            "timeout": 120,
        },
    }

    logger.debug(f"SQLite配置: {db_path} (使用 StaticPool)")
    return url, engine_kwargs


def _build_postgresql_config(config) -> tuple[str, dict]:
    """构建 PostgreSQL 配置

    Args:
        config: 数据库配置对象

    Returns:
        (url, engine_kwargs) 元组
    """
    encoded_user = quote_plus(config.postgresql_user)
    encoded_password = quote_plus(config.postgresql_password)

    # 构建基本 URL
    url = (
        f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
        f"@{config.postgresql_host}:{config.postgresql_port}/{config.postgresql_database}"
    )

    # SSL 配置
    connect_args = {}
    if config.postgresql_ssl_mode != "disable":
        ssl_config = {"ssl": config.postgresql_ssl_mode}
        if config.postgresql_ssl_ca:
            ssl_config["ssl_ca"] = config.postgresql_ssl_ca
        if config.postgresql_ssl_cert:
            ssl_config["ssl_cert"] = config.postgresql_ssl_cert
        if config.postgresql_ssl_key:
            ssl_config["ssl_key"] = config.postgresql_ssl_key
        connect_args.update(ssl_config)

    # 设置 schema（如果不是 public）
    if config.postgresql_schema and config.postgresql_schema != "public":
        connect_args["server_settings"] = {"search_path": config.postgresql_schema}

    engine_kwargs = {
        "echo": False,
        "future": True,
        "pool_size": config.connection_pool_size,
        "max_overflow": config.connection_pool_size * 2,
        "pool_timeout": config.connection_timeout,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
    }

    if connect_args:
        engine_kwargs["connect_args"] = connect_args

    logger.debug(
        f"PostgreSQL配置: {config.postgresql_user}@{config.postgresql_host}:{config.postgresql_port}/{config.postgresql_database}"
    )
    return url, engine_kwargs


async def close_engine():
    """关闭数据库引擎

    释放所有连接池资源
    """
    global _engine

    if _engine is not None:
        logger.info("正在关闭数据库引擎...")
        await _engine.dispose()
        _engine = None
        logger.info("数据库引擎已关闭")


async def _enable_sqlite_optimizations(engine: AsyncEngine):
    """启用SQLite性能优化

    优化项：
    - WAL模式：提高并发性能
    - NORMAL同步：平衡性能和安全性
    - 启用外键约束
    - 设置busy_timeout：避免锁定错误

    Args:
        engine: SQLAlchemy异步引擎
    """
    try:
        async with engine.begin() as conn:
            # 启用WAL模式
            await conn.execute(text("PRAGMA journal_mode = WAL"))
            # 设置适中的同步级别
            await conn.execute(text("PRAGMA synchronous = NORMAL"))
            # 启用外键约束
            await conn.execute(text("PRAGMA foreign_keys = ON"))
            # 设置busy_timeout（毫秒），遇到锁时等待更长时间，避免 "database is locked" 错误
            # 120秒与连接配置的 timeout 保持一致
            await conn.execute(text("PRAGMA busy_timeout = 120000"))
            # 设置缓存大小（10MB）
            await conn.execute(text("PRAGMA cache_size = -10000"))
            # 临时存储使用内存
            await conn.execute(text("PRAGMA temp_store = MEMORY"))

    except Exception as e:
        logger.warning(f"⚠️ SQLite性能优化失败: {e}，将使用默认配置")


async def _enable_postgresql_optimizations(engine: AsyncEngine) -> None:
    """启用 PostgreSQL 会话级性能优化。

    包含：
    - work_mem：单次排序/哈希可用内存
    - statement_timeout：单条语句超时
    - synchronous_commit：提交同步级别
    - jit：是否启用 JIT
    - idle_in_transaction_session_timeout：事务空闲超时
    - lock_timeout：等待锁超时
    """
    try:
        async with engine.begin() as conn:
            # 排序/哈希内存，注意这是“每个排序操作”的上限，不要乱调太大
            await conn.execute(text("SET work_mem = '64MB'"))

            # 单条语句超时（1 分钟）
            await conn.execute(text("SET statement_timeout = '60000'"))

            # 提交同步级别：'local' 性能好一些，崩溃时可能丢几 ms 的数据
            await conn.execute(text("SET synchronous_commit = 'local'"))

            # 对大量短小查询，通常关掉 JIT 更省 CPU
            await conn.execute(text("SET jit = 'off'"))

            # 事务空闲超时，避免长时间占用锁
            await conn.execute(
                text("SET idle_in_transaction_session_timeout = '60000'")
            )

            # 等锁超过 5s 就报错，避免全部堆死
            await conn.execute(text("SET lock_timeout = '5000'"))

            # 可选：根据你预估的缓存情况设置
            # await conn.execute(text("SET random_page_cost = 1.1"))
            # await conn.execute(text("SET effective_cache_size = '2GB'"))

    except Exception as e:
        logger.warning(
            f"⚠️ PostgreSQL 会话级性能优化失败: {e}，将使用默认配置"
        )


async def get_engine_info() -> dict:
    """获取引擎信息（用于监控和调试）

    Returns:
        dict: 引擎信息字典
    """
    try:
        engine = await get_engine()

        info = {
            "name": engine.name,
            "driver": engine.driver,
            "url": str(engine.url).replace(str(engine.url.password or ""), "***"),
            "pool_size": getattr(engine.pool, "size", lambda: None)(),
            "pool_checked_out": getattr(engine.pool, "checked_out", lambda: 0)(),
            "pool_overflow": getattr(engine.pool, "overflow", lambda: 0)(),
        }

        return info

    except Exception as e:
        logger.error(f"获取引擎信息失败: {e}")
        return {}
