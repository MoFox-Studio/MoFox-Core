"""基于 SQLAlchemy 构建的会话助手
Session helpers built on top of SQLAlchemy."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
import time

from sqlalchemy.orm import Session, sessionmaker

from .exceptions import SessionError
from kernel.logger import get_logger, MetadataContext

logger = get_logger(__name__)


class SessionManager:
    """为给定引擎创建和管理数据库会话
    Creates and manages database sessions for a given engine."""

    def __init__(self, engine) -> None:
        try:
            self._session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
                future=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise SessionError("Failed to initialize session factory") from exc

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """为一系列操作提供事务作用域
        Provide a transactional scope around a series of operations."""

        session: Session = self._session_factory()
        start_time = time.time()
        session_id = f"session_{id(session)}"
        
        with MetadataContext(session_id=session_id):
            logger.debug(
                "数据库会话已创建",
                extra={'session_id': session_id}
            )
            
            try:
                yield session
                session.commit()
                
                duration = time.time() - start_time
                logger.info(
                    "数据库事务已提交",
                    extra={
                        'session_id': session_id,
                        'duration': duration,
                        'status': 'committed'
                    }
                )
            except Exception as e:
                session.rollback()
                duration = time.time() - start_time
                
                logger.error(
                    "数据库事务已回滚",
                    extra={
                        'session_id': session_id,
                        'duration': duration,
                        'status': 'rolled_back',
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    },
                    exc_info=True
                )
                raise
            finally:
                session.close()
                logger.debug(
                    "数据库会话已关闭",
                    extra={'session_id': session_id}
                )
