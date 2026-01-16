"""SQLite 方言适配器：为本地开发和生产提供完整的 SQL 数据库支持
SQLite dialect adapter providing comprehensive SQL database support for local and production use."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from .exceptions import UnsupportedDialectError


@dataclass
class EngineConfig:
    """SQLite 引擎配置，支持文件和内存数据库
    SQLite engine configuration supporting both file-based and in-memory databases."""

    database: str
    dialect: str = "sqlite"
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

    @property
    def is_memory(self) -> bool:
        return self.database in {":memory:", "memory"}


class SQLiteAdapter:
    """SQLite 适配器：专业级 SQLite 支持，包含性能和功能优化
    Professional-grade SQLite adapter with performance and feature optimizations."""

    name = "sqlite"

    def create_engine(self, config: EngineConfig) -> Engine:
        """创建 SQLAlchemy SQLite 引擎，配置优化
        Create an optimized SQLAlchemy SQLite engine."""

        if not config.is_memory and config.create_if_missing:
            db_path = Path(config.database)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        url = self._build_url(config)
        
        # SQLite 优化配置
        # SQLite optimization configuration
        connect_args = {
            "check_same_thread": False,
            "timeout": config.timeout,
        }
        connect_args.update(config.connect_args)

        # 内存数据库使用 StaticPool，文件数据库使用 QueuePool
        # Use StaticPool for memory, QueuePool for file-based
        if config.is_memory:
            pool_class = StaticPool
            pool_size = 1
        else:
            from sqlalchemy.pool import QueuePool
            pool_class = QueuePool
            pool_size = config.pool_size

        engine = create_engine(
            url,
            echo=config.echo,
            poolclass=pool_class,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=0,
            pool_timeout=config.pool_timeout,
            connect_args=connect_args,
            future=True,
        )

        # 配置 SQLite 特定的性能选项
        # Configure SQLite-specific performance options
        self._configure_sqlite_pragmas(engine, config)

        return engine

    @staticmethod
    def _configure_sqlite_pragmas(engine: Engine, config: EngineConfig) -> None:
        """为 SQLite 配置性能和功能 pragma
        Configure SQLite pragmas for performance and features."""

        @event.listens_for(engine, "connect")
        def configure_pragmas(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            
            # 启用外键约束
            # Enable foreign key constraints
            if config.enable_foreign_keys:
                cursor.execute("PRAGMA foreign_keys = ON")
            
            # 设置日志模式（WAL 提高并发性能）
            # Set journal mode (WAL improves concurrent performance)
            cursor.execute(f"PRAGMA journal_mode = {config.journal_mode}")
            
            # 设置同步模式（NORMAL 平衡性能和安全）
            # Set synchronous mode (NORMAL balances performance and safety)
            cursor.execute(f"PRAGMA synchronous = {config.synchronous}")
            
            # 缓存大小（负数表示 KB）
            # Cache size (negative number means KB)
            cursor.execute("PRAGMA cache_size = -64000")
            
            # 内存映射 I/O（提高读取性能）
            # Memory-mapped I/O for better read performance
            cursor.execute("PRAGMA mmap_size = 30000000000")
            
            # 临时存储在内存中（加快临时操作）
            # Temp storage in memory (speeds up temporary operations)
            cursor.execute("PRAGMA temp_store = MEMORY")
            
            # 自动真空（防止数据库碎片化）
            # Auto-vacuum to prevent database fragmentation
            cursor.execute("PRAGMA auto_vacuum = INCREMENTAL")
            
            cursor.close()

    def _build_url(self, config: EngineConfig) -> str:
        """构建 SQLite 连接 URL
        Build SQLite connection URL."""
        if config.is_memory:
            return "sqlite://"
        absolute_path = Path(config.database).expanduser().resolve()
        return f"sqlite:///{absolute_path}"



__all__ = ["EngineConfig", "SQLiteAdapter"]

