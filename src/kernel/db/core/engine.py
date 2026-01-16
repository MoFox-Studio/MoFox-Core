"""SQLite 引擎注册表与创建助手
SQLite engine registry and creation helpers."""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from sqlalchemy.engine import Engine

from .dialect_adapter import EngineConfig, SQLiteAdapter
from .exceptions import EngineAlreadyExistsError, EngineNotInitializedError


class EngineManager:
    """按名称管理 SQLite 数据库引擎
    Manages SQLite database engines keyed by name."""

    def __init__(self) -> None:
        self._adapter = SQLiteAdapter()
        self._engines: Dict[str, Engine] = {}
        self._default_name = "default"

    def create(self, config: EngineConfig, name: Optional[str] = None) -> Engine:
        """创建并存储 SQLite 引擎
        Create and store a SQLite engine."""

        engine_name = name or self._default_name
        if engine_name in self._engines:
            raise EngineAlreadyExistsError(f"Engine '{engine_name}' already exists")

        engine = self._adapter.create_engine(config)
        self._engines[engine_name] = engine
        return engine

    def get(self, name: Optional[str] = None) -> Engine:
        """按名称检索已注册的引擎
        Retrieve a registered engine by name."""

        engine_name = name or self._default_name
        try:
            return self._engines[engine_name]
        except KeyError as exc:
            raise EngineNotInitializedError(f"Engine '{engine_name}' is not initialized") from exc

    def dispose(self, name: Optional[str] = None) -> None:
        """释放并移除已注册的引擎
        Dispose and remove a registered engine."""

        engine_name = name or self._default_name
        engine = self._engines.pop(engine_name, None)
        if engine:
            engine.dispose()

    def dispose_all(self) -> None:
        """释放所有已注册的引擎
        Dispose all registered engines."""
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()

    def list_engines(self) -> Mapping[str, Engine]:
        """返回已注册引擎的浅拷贝
        Return a shallow copy of registered engines."""

        return dict(self._engines)


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
    """便捷助手：创建和注册 SQLite 引擎
    Convenience helper to create and register a SQLite engine.
    
    参数 Args:
        database: 数据库文件路径或 ":memory:" / Database file path or ":memory:"
        name: 引擎注册名称 / Engine registration name
        echo: 是否启用 SQL 日志 / Enable SQL logging
        pool_size: 连接池大小 / Connection pool size
        pool_timeout: 连接池超时（秒） / Connection pool timeout (seconds)
        enable_wal: 启用 WAL 日志模式 / Enable WAL journal mode
        enable_foreign_keys: 启用外键约束 / Enable foreign key constraints
        journal_mode: 日志模式 / Journal mode (WAL, DELETE, etc.)
        synchronous: 同步模式 / Synchronous mode (NORMAL, FULL, OFF)
        timeout: SQLite 锁超时（秒） / SQLite lock timeout (seconds)
        connect_args: 额外的连接参数 / Additional connection arguments
    """

    manager = EngineManager()
    config = EngineConfig(
        database=database,
        echo=echo,
        pool_size=pool_size,
        pool_timeout=pool_timeout,
        enable_wal=enable_wal,
        enable_foreign_keys=enable_foreign_keys,
        journal_mode=journal_mode,
        synchronous=synchronous,
        timeout=timeout,
        connect_args=connect_args or {},
    )
    return manager.create(config, name=name)


__all__ = [
    "EngineManager",
    "EngineConfig",
    "create_sqlite_engine",
]
