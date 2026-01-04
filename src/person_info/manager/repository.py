import copy
import time
from collections.abc import Callable
from typing import Any

import orjson

from src.common.database.api.crud import CRUDBase
from src.common.database.core.models import PersonInfo
from src.common.database.optimization.cache_manager import get_cache
from src.common.database.utils.decorators import cached, generate_cache_key
from src.common.logger import get_logger
from src.person_info.manager.constants import JSON_SERIALIZED_FIELDS, person_info_default

logger = get_logger("person_info.repository")


class PersonInfoRepository:
    """Data-access layer for PersonInfo with cache-friendly helpers."""

    def __init__(self):
        self.crud = CRUDBase(PersonInfo)

    async def fetch_by_person_id(self, person_id: str):
        return await self.crud.get_by(person_id=person_id)

    async def fetch_by_person_name(self, person_name: str, limit: int = 1):
        return await self.crud.get_multi(person_name=person_name, limit=limit)

    async def fetch_by_nickname(self, nickname: str, limit: int = 1):
        return await self.crud.get_multi(nickname=nickname, limit=limit)

    async def create_person_info(self, person_id: str, data: dict | None = None):
        if not person_id:
            logger.debug("创建失败，person_id不存在")
            return None

        model_fields = [column.name for column in PersonInfo.__table__.columns]
        final_data = {"person_id": person_id}

        for key, default_value in copy.deepcopy(person_info_default).items():
            if key in model_fields:
                final_data[key] = default_value

        if data:
            for key, value in data.items():
                if key in model_fields:
                    final_data[key] = value

        final_data["person_id"] = person_id

        if final_data.get("user_id") is None:
            logger.warning(f"user_id为None，使用'unknown'作为默认值 person_id={person_id}")
            final_data["user_id"] = "unknown"

        if final_data.get("platform") is None:
            logger.warning(f"platform为None，使用'unknown'作为默认值 person_id={person_id}")
            final_data["platform"] = "unknown"

        for key in JSON_SERIALIZED_FIELDS:
            if key in final_data:
                if isinstance(final_data[key], list | dict):
                    final_data[key] = orjson.dumps(final_data[key]).decode("utf-8")
                elif final_data[key] is None:
                    final_data[key] = orjson.dumps([]).decode("utf-8")

        try:
            return await self.crud.create(final_data)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"创建 PersonInfo 记录 {final_data.get('person_id')} 失败: {exc}")
            return None

    async def safe_create_person_info(self, person_id: str, data: dict | None = None):
        if not person_id:
            logger.debug("创建失败，person_id不存在")
            return False

        model_fields = [column.name for column in PersonInfo.__table__.columns]
        final_data = {"person_id": person_id}

        for key, default_value in copy.deepcopy(person_info_default).items():
            if key in model_fields:
                final_data[key] = default_value

        if data:
            for key, value in data.items():
                if key in model_fields:
                    final_data[key] = value

        final_data["person_id"] = person_id

        if final_data.get("user_id") is None:
            logger.warning(f"user_id为None，使用'unknown'作为默认值 person_id={person_id}")
            final_data["user_id"] = "unknown"

        if final_data.get("platform") is None:
            logger.warning(f"platform为None，使用'unknown'作为默认值 person_id={person_id}")
            final_data["platform"] = "unknown"

        for key in JSON_SERIALIZED_FIELDS:
            if key in final_data:
                if isinstance(final_data[key], list | dict):
                    final_data[key] = orjson.dumps(final_data[key]).decode("utf-8")
                elif final_data[key] is None:
                    final_data[key] = orjson.dumps([]).decode("utf-8")

        try:
            existing = await self.crud.get_by(person_id=final_data["person_id"])
            if existing:
                logger.debug(f"用户 {final_data['person_id']} 已存在，跳过创建")
                return True

            await self.crud.create(final_data)
            return True
        except Exception as exc:  # noqa: BLE001
            if "UNIQUE constraint failed" in str(exc):
                logger.debug(f"检测到并发创建用户 {final_data.get('person_id')}，跳过错误")
                return True

            logger.error(f"创建 PersonInfo 记录 {final_data.get('person_id')} 失败: {exc}")
            return False

    async def update_field(self, person_id: str, field_name: str, value, data: dict | None = None):
        model_fields = [column.name for column in PersonInfo.__table__.columns]
        if field_name not in model_fields:
            logger.debug(f"更新'{field_name}'失败，未在 PersonInfo SQLAlchemy 模型中定义的字段。")
            return False, False

        processed_value = value
        if field_name in JSON_SERIALIZED_FIELDS:
            if isinstance(value, list | dict):
                processed_value = orjson.dumps(value).decode("utf-8")
            elif value is None:
                processed_value = orjson.dumps([]).decode("utf-8")

        start_time = time.time()
        record = await self.crud.get_by(person_id=person_id)
        query_time = time.time()

        if record:
            await self.crud.update(record.id, {field_name: processed_value})
            save_time = time.time()
            total_time = save_time - start_time
            if total_time > 0.5:
                logger.warning(
                    f"数据库更新操作耗时 {total_time:.3f}秒 (查询: {query_time - start_time:.3f}s, 保存: {save_time - query_time:.3f}s) person_id={person_id}, field={field_name}"
                )

            cache = await get_cache()
            await cache.delete(generate_cache_key("person_value", person_id, field_name))
            await cache.delete(generate_cache_key("person_values", person_id))
            await cache.delete(generate_cache_key("person_has_field", person_id, field_name))
            return True, False

        total_time = time.time() - start_time
        if total_time > 0.5:
            logger.warning(f"数据库查询操作耗时 {total_time:.3f}秒 person_id={person_id}, field={field_name}")

        creation_data = data if data is not None else {}
        creation_data[field_name] = value

        if creation_data.get("user_id") is None:
            logger.warning(f"创建用户时user_id为None，使用'unknown'作为默认值 person_id={person_id}")
            creation_data["user_id"] = "unknown"

        if creation_data.get("platform") is None:
            logger.warning(f"创建用户时platform为None，使用'unknown'作为默认值 person_id={person_id}")
            creation_data["platform"] = "unknown"

        await self.safe_create_person_info(person_id, creation_data)
        return False, True

    async def delete_person(self, person_id: str):
        if not person_id:
            logger.debug("删除失败：person_id 不能为空")
            return 0

        try:
            record = await self.crud.get_by(person_id=person_id)
            if record:
                await self.crud.delete(record.id)
                return 1
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.error(f"删除 PersonInfo {person_id} 失败: {exc}")
            return 0

    @cached(ttl=600, key_prefix="person_value")
    async def get_value(self, person_id: str, field_name: str) -> Any:
        if not person_id:
            logger.debug("get_value获取失败：person_id不能为空")
            return None

        model_fields = [column.name for column in PersonInfo.__table__.columns]
        if field_name not in model_fields:
            if field_name in person_info_default:
                logger.debug(f"字段'{field_name}'不在SQLAlchemy模型中，使用默认配置值。")
                return copy.deepcopy(person_info_default[field_name])
            logger.debug(f"get_value查询失败：字段'{field_name}'未在SQLAlchemy模型和默认配置中定义。")
            return None

        record = await self.crud.get_by(person_id=person_id)
        if record:
            try:
                value = getattr(record, field_name)
                if value is not None:
                    if field_name in JSON_SERIALIZED_FIELDS:
                        try:
                            if isinstance(value, str):
                                return orjson.loads(value)
                            return value
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(f"反序列化字段 {field_name} 失败: {exc}, value={value}, 使用默认值")
                            return copy.deepcopy(person_info_default.get(field_name))
                    return value
                return copy.deepcopy(person_info_default.get(field_name))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"访问字段 {field_name} 失败: {exc}, 使用默认值")
                return copy.deepcopy(person_info_default.get(field_name))

        return copy.deepcopy(person_info_default.get(field_name))

    @cached(ttl=600, key_prefix="person_values")
    async def get_values(self, person_id: str, field_names: list) -> dict:
        if not person_id:
            logger.debug("get_values获取失败：person_id不能为空")
            return {}

        result: dict[str, Any] = {}
        record = await self.crud.get_by(person_id=person_id)
        model_fields = [column.name for column in PersonInfo.__table__.columns]

        for field_name in field_names:
            if field_name not in model_fields:
                if field_name in person_info_default:
                    result[field_name] = copy.deepcopy(person_info_default[field_name])
                    logger.debug(f"字段'{field_name}'不在SQLAlchemy模型中，使用默认配置值。")
                else:
                    logger.debug(f"get_values查询失败：字段'{field_name}'未在SQLAlchemy模型和默认配置中定义。")
                    result[field_name] = None
                continue

            if record:
                try:
                    value = getattr(record, field_name)
                    if value is not None:
                        if field_name in JSON_SERIALIZED_FIELDS:
                            try:
                                if isinstance(value, str):
                                    result[field_name] = orjson.loads(value)
                                else:
                                    result[field_name] = value
                            except Exception as exc:  # noqa: BLE001
                                logger.warning(f"反序列化字段 {field_name} 失败: {exc}, value={value}, 使用默认值")
                                result[field_name] = copy.deepcopy(person_info_default.get(field_name))
                        else:
                            result[field_name] = value
                    else:
                        result[field_name] = copy.deepcopy(person_info_default.get(field_name))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"访问字段 {field_name} 失败: {exc}, 使用默认值")
                    result[field_name] = copy.deepcopy(person_info_default.get(field_name))
            else:
                result[field_name] = copy.deepcopy(person_info_default.get(field_name))

        return result

    @cached(ttl=300, key_prefix="person_has_field")
    async def has_field(self, person_id: str, field_name: str):
        model_fields = [column.name for column in PersonInfo.__table__.columns]
        if field_name not in model_fields:
            logger.debug(f"检查字段'{field_name}'失败，未在 PersonInfo SQLAlchemy 模型中定义。")
            return False

        try:
            record = await self.crud.get_by(person_id=person_id)
            return bool(record)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"检查字段 {field_name} for {person_id} 时出错: {exc}")
            return False

    @cached(ttl=300, key_prefix="person_specific_list", use_kwargs=False)
    async def get_specific_value_list(self, field_name: str, predicate: Callable[[Any], bool]) -> dict[str, Any]:
        model_fields = [column.name for column in PersonInfo.__table__.columns]
        if field_name not in model_fields:
            logger.error(f"字段检查失败：'{field_name}'未在 PersonInfo SQLAlchemy 模型中定义")
            return {}

        found_results: dict[str, Any] = {}
        try:
            all_records = await self.crud.get_multi(limit=100000)
            for record in all_records:
                try:
                    value = getattr(record, field_name, None)
                    if value is not None and predicate(value):
                        person_id_value = getattr(record, "person_id", None)
                        if person_id_value:
                            found_results[person_id_value] = value
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"访问记录字段失败: {exc}")
                    continue
        except Exception as exc:  # noqa: BLE001
            logger.error(f"数据库查询失败 (specific_value_list for {field_name}): {exc}")

        return found_results


__all__ = ["PersonInfoRepository"]
