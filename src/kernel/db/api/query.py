"""轻量级查询规约，针对 SQLAlchemy 优化
Query specification optimized for SQLAlchemy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union

from sqlalchemy import Select


@dataclass
class QuerySpec:
	"""SQLAlchemy 查询描述
	Query description for SQLAlchemy.
	
	字段说明 Field descriptions:
	- filters: SQLAlchemy 过滤表达式列表 / List of SQLAlchemy filter expressions
	- order_by: SQLAlchemy 排序表达式列表 / List of SQLAlchemy order expressions
	- limit: 结果限制数 / Maximum number of results
	- offset: 跳过的行数 / Number of rows to skip
	- projection: 投影字段（预留） / Projection fields (reserved)
	"""

	filters: Union[List[object], dict] = field(default_factory=list)
	order_by: Union[List[object], List[tuple]] = field(default_factory=list)
	limit: Optional[int] = None
	offset: Optional[int] = None
	projection: Optional[dict] = None


def apply_query_spec(statement: Select, spec: QuerySpec) -> Select:
	"""将查询规约应用到 SQLAlchemy select 语句
	Apply query spec to a SQLAlchemy select statement.
	
	参数 Args:
		statement: SQLAlchemy select 语句 / SQLAlchemy select statement
		spec: 查询规约 / Query specification
	
	返回 Returns:
		应用了规约的 select 语句 / Modified select statement
	"""

	if spec.filters:
		if isinstance(spec.filters, list):
			statement = statement.filter(*spec.filters)
	if spec.order_by:
		if isinstance(spec.order_by, list):
			statement = statement.order_by(*spec.order_by)
	if spec.limit is not None:
		statement = statement.limit(spec.limit)
	if spec.offset is not None:
		statement = statement.offset(spec.offset)
	return statement


__all__ = ["QuerySpec", "apply_query_spec"]
