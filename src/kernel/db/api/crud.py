"""基于 SQLAlchemy 构建的完整 CRUD 和数据库操作接口
Comprehensive CRUD and database operations interface built on SQLAlchemy."""

from __future__ import annotations

from typing import Any, Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..core.session import SessionManager
from .query import QuerySpec, apply_query_spec
from kernel.logger import get_logger

logger = get_logger(__name__)

ModelT = TypeVar("ModelT")


class CRUDRepository(Generic[ModelT]):
	"""SQLAlchemy CRUD 仓库接口
	SQLAlchemy CRUD repository interface."""

	def add(self, session: Any, obj: ModelT, *, flush: bool = False) -> ModelT:
		"""添加对象到数据库
		Add an object to the database."""
		raise NotImplementedError

	def get(self, session: Any, model: Type[ModelT], obj_id: Any) -> Optional[ModelT]:
		"""按 ID 获取单个对象
		Get a single object by ID."""
		raise NotImplementedError

	def list(self, session: Any, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> Sequence[ModelT]:
		"""列表查询，支持过滤、排序、分页
		List query with filtering, sorting, and pagination support."""
		raise NotImplementedError

	def delete(self, session: Any, obj: ModelT) -> None:
		"""删除对象
		Delete an object."""
		raise NotImplementedError

	def update_fields(self, session: Any, obj: ModelT, fields: dict[str, Any]) -> ModelT:
		"""更新对象字段
		Update object fields."""
		raise NotImplementedError


class SQLAlchemyCRUDRepository(CRUDRepository[ModelT]):
	"""SQLAlchemy CRUD 仓库实现，支持完整的数据库操作
	SQLAlchemy CRUD repository implementation with comprehensive database operations."""

	def __init__(self, session_manager: SessionManager) -> None:
		self._session_manager = session_manager

	def add(self, session: Session, obj: ModelT, *, flush: bool = False) -> ModelT:
		"""添加单个对象
		Add a single object."""
		model_name = type(obj).__name__
		
		session.add(obj)
		if flush:
			session.flush()
		
		logger.debug(
			f"数据库添加操作: {model_name}",
			extra={
				'operation': 'add',
				'model': model_name,
				'flushed': flush
			}
		)
		return obj

	def add_many(self, session: Session, objs: Sequence[ModelT], *, flush: bool = False) -> Sequence[ModelT]:
		"""批量添加对象
		Add multiple objects in batch."""
		if not objs:
			return []
		
		model_name = type(objs[0]).__name__
		session.add_all(objs)
		
		if flush:
			session.flush()
		
		logger.info(
			f"数据库批量添加: {model_name}",
			extra={
				'operation': 'add_many',
				'model': model_name,
				'count': len(objs),
				'flushed': flush
			}
		)
		return objs

	def get(self, session: Session, model: Type[ModelT], obj_id: Any) -> Optional[ModelT]:
		"""按 ID 获取单个对象
		Get a single object by ID."""
		result = session.get(model, obj_id)
		
		logger.debug(
			f"数据库查询操作: {model.__name__}",
			extra={
				'operation': 'get',
				'model': model.__name__,
				'id': obj_id,
				'found': result is not None
			}
		)
		return result

	def list(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> Sequence[ModelT]:
		"""列表查询
		List query with optional query spec."""
		stmt = select(model)
		if query_spec:
			stmt = apply_query_spec(stmt, query_spec)
		results = list(session.execute(stmt).scalars().all())
		
		logger.debug(
			f"数据库列表查询: {model.__name__}",
			extra={
				'operation': 'list',
				'model': model.__name__,
				'has_query_spec': query_spec is not None,
				'result_count': len(results),
				'limit': query_spec.limit if query_spec else None,
				'offset': query_spec.offset if query_spec else None
			}
		)
		return results

	def delete(self, session: Session, obj: ModelT) -> None:
		"""删除单个对象
		Delete a single object."""
		model_name = type(obj).__name__
		
		session.delete(obj)
		
		logger.info(
			f"数据库删除操作: {model_name}",
			extra={
				'operation': 'delete',
				'model': model_name
			}
		)

	def delete_many(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> int:
		"""批量删除对象
		Delete multiple objects."""
		stmt = select(model)
		if query_spec:
			stmt = apply_query_spec(stmt, query_spec)
		
		# 获取要删除的对象数量
		count_stmt = select(func.count()).select_from(model)
		if query_spec and query_spec.filters:
			if isinstance(query_spec.filters, list):
				count_stmt = count_stmt.filter(*query_spec.filters)
		count = session.execute(count_stmt).scalar() or 0
		
		# 删除对象
		delete_stmt = select(model)
		if query_spec:
			delete_stmt = apply_query_spec(delete_stmt, query_spec)
		
		for obj in session.execute(delete_stmt).scalars().all():
			session.delete(obj)
		
		logger.info(
			f"数据库批量删除: {model.__name__}",
			extra={
				'operation': 'delete_many',
				'model': model.__name__,
				'deleted_count': count
			}
		)
		return count

	def update_fields(self, session: Session, obj: ModelT, fields: dict[str, Any]) -> ModelT:
		"""更新对象字段
		Update object fields."""
		model_name = type(obj).__name__
		
		for key, value in fields.items():
			setattr(obj, key, value)
		session.flush()
		
		logger.info(
			f"数据库更新操作: {model_name}",
			extra={
				'operation': 'update',
				'model': model_name,
				'fields_updated': list(fields.keys()),
				'field_count': len(fields)
			}
		)
		return obj

	def count(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> int:
		"""计算符合条件的记录数
		Count records matching the query spec."""
		stmt = select(func.count()).select_from(model)
		if query_spec and query_spec.filters:
			if isinstance(query_spec.filters, list):
				stmt = stmt.filter(*query_spec.filters)
		
		count = session.execute(stmt).scalar() or 0
		
		logger.debug(
			f"数据库计数操作: {model.__name__}",
			extra={
				'operation': 'count',
				'model': model.__name__,
				'count': count
			}
		)
		return count

	def exists(self, session: Session, model: Type[ModelT], query_spec: Optional[QuerySpec] = None) -> bool:
		"""检查是否存在符合条件的记录
		Check if any record exists matching the query spec."""
		stmt = select(model)
		if query_spec:
			stmt = apply_query_spec(stmt, query_spec)
		
		result = session.execute(stmt.limit(1)).first()
		exists = result is not None
		
		logger.debug(
			f"数据库存在性检查: {model.__name__}",
			extra={
				'operation': 'exists',
				'model': model.__name__,
				'exists': exists
			}
		)
		return exists

	def session_scope(self):
		"""暴露底层的 session 作用域助手
		Expose the underlying session scope helper."""
		return self._session_manager.session_scope()


__all__ = ["CRUDRepository", "SQLAlchemyCRUDRepository"]
