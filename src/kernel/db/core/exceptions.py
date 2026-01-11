"""Database-related exceptions for the kernel layer."""


class DatabaseError(Exception):
    """Base exception for database errors."""


class UnsupportedDialectError(DatabaseError):
    """Raised when a requested database dialect is not registered."""


class EngineAlreadyExistsError(DatabaseError):
    """Raised when attempting to register an engine with a duplicate name."""


class EngineNotInitializedError(DatabaseError):
    """Raised when accessing an engine that has not been initialized."""


class SessionError(DatabaseError):
    """Raised when a database session fails to initialize or execute."""
