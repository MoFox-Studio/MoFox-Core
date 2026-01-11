"""兼容层适配器

提供向后兼容的API，将旧的数据库API调用转换为新架构的调用
保持原有函数签名和行为不变
"""

from typing import Any

from src.common.database.api import (
    CRUDBase,
    QueryBuilder,
)
from src.common.database.api import (
    store_action_info as new_store_action_info,
)
from src.common.database.api.crud import _model_to_dict as _crud_model_to_dict
from src.common.database.core.models import (
    ActionRecords,
    AntiInjectionStats,
    BanUser,
    BotPersonalityInterests,
    CacheEntries,
    ChatStreams,
    Emoji,
    Expression,
    GraphEdges,
    GraphNodes,
    ImageDescriptions,
    Images,
    LLMUsage,
    MaiZoneScheduleStatus,
    Memory,
    Messages,
    MonthlyPlan,
    OnlineTime,
    PermissionNodes,
    PersonInfo,
    Schedule,
    ThinkingLog,
    UserPermissions,
    UserRelationships,
    Videos,
)
from src.common.logger import get_logger

logger = get_logger("database.compatibility")

# 模型映射表，用于通过名称获取模型类
MODEL_MAPPING = {
    "Messages": Messages,
    "ActionRecords": ActionRecords,
    "PersonInfo": PersonInfo,
    "ChatStreams": ChatStreams,
    "LLMUsage": LLMUsage,
    "Emoji": Emoji,
    "Images": Images,
    "ImageDescriptions": ImageDescriptions,
    "Videos": Videos,
    "OnlineTime": OnlineTime,
    "Memory": Memory,
    "Expression": Expression,
    "ThinkingLog": ThinkingLog,
    "GraphNodes": GraphNodes,
    "GraphEdges": GraphEdges,
    "Schedule": Schedule,
    "MaiZoneScheduleStatus": MaiZoneScheduleStatus,
    "BotPersonalityInterests": BotPersonalityInterests,
    "BanUser": BanUser,
    "AntiInjectionStats": AntiInjectionStats,
    "MonthlyPlan": MonthlyPlan,
    "CacheEntries": CacheEntries,
    "UserRelationships": UserRelationships,
    "PermissionNodes": PermissionNodes,
    "UserPermissions": UserPermissions,
}

# 为每个模型创建CRUD实例
_crud_instances = {name: CRUDBase(model) for name, model in MODEL_MAPPING.items()}


async def build_filters(model_class, filters: dict[str, Any]):
    """构建查询过滤条件（兼容MongoDB风格操作符）

    Args:
        model_class: SQLAlchemy模型类
        filters: 过滤条件字典

    Returns:
        条件列表
    """
    conditions = []

    for field_name, value in filters.items():
        if not hasattr(model_class, field_name):
            logger.warning(f"模型 {model_class.__name__} 中不存在字段 '{field_name}'")
            continue

        field = getattr(model_class, field_name)

        if isinstance(value, dict):
            # 处理 MongoDB 风格的操作符
            for op, op_value in value.items():
                if op == "$gt":
                    conditions.append(field > op_value)
                elif op == "$lt":
                    conditions.append(field < op_value)
                elif op == "$gte":
                    conditions.append(field >= op_value)
                elif op == "$lte":
                    conditions.append(field <= op_value)
                elif op == "$ne":
                    conditions.append(field != op_value)
                elif op == "$in":
                    conditions.append(field.in_(op_value))
                elif op == "$nin":
                    conditions.append(~field.in_(op_value))
                else:
                    logger.warning(f"未知操作符 '{op}' (字段: '{field_name}')")
        else:
            # 直接相等比较
            conditions.append(field == value)

    return conditions


def _model_to_dict(instance) -> dict[str, Any] | None:
    """将数据库模型实例转换为字典（兼容旧API

    Args:
        instance: 数据库模型实例

    Returns:
        字典表示
    """
    if instance is None:
        return None
    return _crud_model_to_dict(instance)




async def db_query(
    model_class,
    data: dict[str, Any] | None = None,
    query_type: str | None = "get",
    filters: dict[str, Any] | None = None,
    limit: int | None = None,
    order_by: list[str] | None = None,
    single_result: bool | None = False,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    """执行异步数据库查询操作（兼容旧API）

    Args:
        model_class: SQLAlchemy模型类
        data: 用于创建或更新的数据字典
        query_type: 查询类型 ("get", "create", "update", "delete", "count")
        filters: 过滤条件字典
        limit: 限制结果数量
        order_by: 排序字段，前缀'-'表示降序
        single_result: 是否只返回单个结果

    Returns:
        根据查询类型返回相应结果
    """
    try:
        if query_type not in ["get", "create", "update", "delete", "count"]:
            raise ValueError("query_type must be 'get', 'create', 'update', 'delete' or 'count'")

        # 获取CRUD实例
        model_name = model_class.__name__
        crud = _crud_instances.get(model_name)
        if not crud:
            crud = CRUDBase(model_class)

        if query_type == "get":
            # 使用QueryBuilder
            # 🔧 兼容层默认禁用缓存（避免旧代码产生大量缓存）
            query_builder = QueryBuilder(model_class).no_cache()

            # 应用过滤条件
            if filters:
                # 将MongoDB风格过滤器转换为QueryBuilder格式
                for field_name, value in filters.items():
                    if isinstance(value, dict):
                        for op, op_value in value.items():
                            if op == "$gt":
                                query_builder = query_builder.filter(**{f"{field_name}__gt": op_value})
                            elif op == "$lt":
                                query_builder = query_builder.filter(**{f"{field_name}__lt": op_value})
                            elif op == "$gte":
                                query_builder = query_builder.filter(**{f"{field_name}__gte": op_value})
                            elif op == "$lte":
                                query_builder = query_builder.filter(**{f"{field_name}__lte": op_value})
                            elif op == "$ne":
                                query_builder = query_builder.filter(**{f"{field_name}__ne": op_value})
                            elif op == "$in":
                                query_builder = query_builder.filter(**{f"{field_name}__in": op_value})
                            elif op == "$nin":
                                query_builder = query_builder.filter(**{f"{field_name}__nin": op_value})
                    else:
                        query_builder = query_builder.filter(**{field_name: value})

            # 应用排序
            if order_by:
                query_builder = query_builder.order_by(*order_by)

            # 应用限制
            if limit:
                query_builder = query_builder.limit(limit)

            # 执行查询
            if single_result:
                return await query_builder.first(as_dict=True)

            return await query_builder.all(as_dict=True)

        elif query_type == "create":
            if not data:
                logger.error("创建操作需要提供data参数")
                return None

            instance = await crud.create(data)
            return _model_to_dict(instance)

        elif query_type == "update":
            if not filters or not data:
                logger.error("更新操作需要提供filters和data参数")
                return None

            # 先查找记录
            query_builder = QueryBuilder(model_class)
            for field_name, value in filters.items():
                if isinstance(value, dict):
                    # 处理 MongoDB 风格的操作符
                    for op, op_value in value.items():
                        if op == "$gt":
                            query_builder = query_builder.filter(**{f"{field_name}__gt": op_value})
                        elif op == "$lt":
                            query_builder = query_builder.filter(**{f"{field_name}__lt": op_value})
                        elif op == "$gte":
                            query_builder = query_builder.filter(**{f"{field_name}__gte": op_value})
                        elif op == "$lte":
                            query_builder = query_builder.filter(**{f"{field_name}__lte": op_value})
                        elif op == "$ne":
                            query_builder = query_builder.filter(**{f"{field_name}__ne": op_value})
                        elif op == "$in":
                            query_builder = query_builder.filter(**{f"{field_name}__in": op_value})
                        elif op == "$nin":
                            query_builder = query_builder.filter(**{f"{field_name}__nin": op_value})
                else:
                    query_builder = query_builder.filter(**{field_name: value})

            instance = await query_builder.first()
            if not instance:
                logger.warning(f"未找到匹配的记录: {filters}")
                return None

            # 更新记录
            updated = await crud.update(instance.id, data)  # type: ignore
            return _model_to_dict(updated)

        elif query_type == "delete":
            if not filters:
                logger.error("删除操作需要提供filters参数")
                return None

            # 先查找记录
            query_builder = QueryBuilder(model_class)
            for field_name, value in filters.items():
                if isinstance(value, dict):
                    # 处理 MongoDB 风格的操作符
                    for op, op_value in value.items():
                        if op == "$gt":
                            query_builder = query_builder.filter(**{f"{field_name}__gt": op_value})
                        elif op == "$lt":
                            query_builder = query_builder.filter(**{f"{field_name}__lt": op_value})
                        elif op == "$gte":
                            query_builder = query_builder.filter(**{f"{field_name}__gte": op_value})
                        elif op == "$lte":
                            query_builder = query_builder.filter(**{f"{field_name}__lte": op_value})
                        elif op == "$ne":
                            query_builder = query_builder.filter(**{f"{field_name}__ne": op_value})
                        elif op == "$in":
                            query_builder = query_builder.filter(**{f"{field_name}__in": op_value})
                        elif op == "$nin":
                            query_builder = query_builder.filter(**{f"{field_name}__nin": op_value})
                else:
                    query_builder = query_builder.filter(**{field_name: value})

            instance = await query_builder.first()
            if not instance:
                logger.warning(f"未找到匹配的记录: {filters}")
                return None

            # 删除记录
            success = await crud.delete(instance.id)  # type: ignore
            return {"deleted": success}

        elif query_type == "count":
            query_builder = QueryBuilder(model_class)

            # 应用过滤条件
            if filters:
                for field_name, value in filters.items():
                    query_builder = query_builder.filter(**{field_name: value})

            count = await query_builder.count()
            return {"count": count}

    except Exception as e:
        logger.error(f"数据库操作失败: {e}")
        return None if single_result or query_type != "get" else []


async def db_save(
    model_class,
    data: dict[str, Any],
    key_field: str,
    key_value: Any,
) -> dict[str, Any] | None:
    """保存或更新记录（兼容旧API）

    Args:
        model_class: SQLAlchemy模型类
        data: 数据字典
        key_field: 主键字段名
        key_value: 主键值

    Returns:
        保存的记录数据或None
    """
    try:
        model_name = model_class.__name__
        crud = _crud_instances.get(model_name)
        if not crud:
            crud = CRUDBase(model_class)

        # 使用get_or_create (返回tuple[T, bool])
        instance, _created = await crud.get_or_create(
            defaults=data,
            **{key_field: key_value},
        )

        return _model_to_dict(instance)

    except Exception as e:
        logger.error(f"保存数据库记录出错: {e}")
        return None


async def db_get(
    model_class,
    filters: dict[str, Any] | None = None,
    limit: int | None = None,
    order_by: str | None = None,
    single_result: bool | None = False,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    """从数据库获取记录（兼容旧API）

    Args:
        model_class: SQLAlchemy模型类
        filters: 过滤条件
        limit: 结果数量限制
        order_by: 排序字段，前缀'-'表示降序
        single_result: 是否只返回单个结果

    Returns:
        记录数据或None
    """
    order_by_list = [order_by] if order_by else None
    return await db_query(
        model_class=model_class,
        query_type="get",
        filters=filters,
        limit=limit,
        order_by=order_by_list,
        single_result=single_result,
    )


async def store_action_info(
    chat_stream=None,
    action_build_into_prompt: bool = False,
    action_prompt_display: str = "",
    action_done: bool = True,
    thinking_id: str = "",
    action_data: dict | None = None,
    action_name: str = "",
) -> dict[str, Any] | None:
    """存储动作信息到数据库（兼容旧API）

    直接使用新的specialized API
    """
    return await new_store_action_info(
        chat_stream=chat_stream,
        action_build_into_prompt=action_build_into_prompt,
        action_prompt_display=action_prompt_display,
        action_done=action_done,
        thinking_id=thinking_id,
        action_data=action_data,
        action_name=action_name,
    )
