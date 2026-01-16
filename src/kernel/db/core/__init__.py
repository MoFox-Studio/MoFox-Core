"""Database core exports."""

from .dialect_adapter import (
    EngineConfig,
    SQLiteAdapter,
)
from .engine import (
    EngineManager,
    create_sqlite_engine,
)
from .exceptions import (
    DatabaseError,
    EngineAlreadyExistsError,
    EngineNotInitializedError,
    SessionError,
)
from .session import SessionManager

__all__ = [
    "EngineManager",
    "EngineConfig",
    "SQLiteAdapter",
    "SessionManager",
    "create_sqlite_engine",
    "DatabaseError",
    "EngineAlreadyExistsError",
    "EngineNotInitializedError",
    "SessionError",
]

