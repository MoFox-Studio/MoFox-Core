import datetime
import time
from typing import Any

import orjson

from src.common.database.api.crud import CRUDBase
from src.common.database.core.models import PersonInfo
from src.common.database.utils.decorators import cached
from src.common.logger import get_logger
from src.person_info.manager.constants import JSON_SERIALIZED_FIELDS, get_person_id, person_info_default
from src.person_info.manager.naming_service import PersonNamingService
from src.person_info.manager.repository import PersonInfoRepository

logger = get_logger("person_info.service")


class PersonInfoService:
    """Facade that orchestrates repository + naming service."""

    def __init__(self, repository: PersonInfoRepository | None = None, naming_service: PersonNamingService | None = None):
        self.repository = repository or PersonInfoRepository()
        self.naming_service = naming_service or PersonNamingService(self.repository)
        self.crud = CRUDBase(PersonInfo)

    @cached(ttl=300, key_prefix="person_known", use_kwargs=False)
    async def is_person_known(self, platform: str, user_id: int):
        person_id = get_person_id(platform, user_id)
        try:
            record = await self.crud.get_by(person_id=person_id)
            return record is not None
        except Exception as exc:  # noqa: BLE001
            logger.error(f"检查用户 {person_id} 是否已知时出错: {exc}")
            return False

    @cached(ttl=600, key_prefix="person_name_to_id", use_kwargs=False)
    async def get_person_id_by_person_name(self, person_name: str) -> str:
        if not person_name:
            return ""

        try:
            records = await self.crud.get_multi(person_name=person_name, limit=1)
            if records:
                return records[0].person_id
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.error(f"根据用户名 {person_name} 获取用户ID时出错: {exc}")
            return ""

    @cached(ttl=600, key_prefix="person_info_by_user_id", use_kwargs=False)
    async def get_person_info_by_user_id(self, platform: str, user_id: str) -> dict | None:
        if not platform or not user_id:
            return None

        person_id = get_person_id(platform, user_id)
        record = await self.crud.get_by(person_id=person_id)
        if not record:
            return None
        return {c.name: getattr(record, c.name) for c in record.__table__.columns}

    @cached(ttl=600, key_prefix="person_info_by_person_id", use_kwargs=False)
    async def get_person_info_by_person_id(self, person_id: str) -> dict | None:
        if not person_id:
            return None

        record = await self.crud.get_by(person_id=person_id)
        if not record:
            return None
        return {c.name: getattr(record, c.name) for c in record.__table__.columns}

    async def get_person_id_by_name_robust(self, name: str) -> str | None:
        if not name:
            return None

        records = await self.crud.get_multi(person_name=name, limit=1)
        if records:
            return records[0].person_id

        records = await self.crud.get_multi(nickname=name, limit=1)
        if records:
            return records[0].person_id

        return None

    @cached(ttl=600, key_prefix="person_info_by_name_robust", use_kwargs=False)
    async def get_person_info_by_name_robust(self, name: str) -> dict | None:
        person_id = await self.get_person_id_by_name_robust(name)
        if person_id:
            return await self.get_person_info_by_person_id(person_id)
        return None

    async def sync_user_info(self, platform: str, user_id: str, nickname: str | None, cardname: str | None) -> str:
        if not platform or not user_id:
            raise ValueError("platform 和 user_id 不能为空")

        person_id = get_person_id(platform, user_id)
        record = await self.crud.get_by(person_id=person_id)
        effective_name = cardname or nickname or "未知用户"

        if record:
            updates: dict[str, Any] = {}
            if nickname and record.nickname != nickname:
                updates["nickname"] = nickname
            if updates:
                await self.crud.update(record.id, updates)
                logger.debug(f"用户 {person_id} 信息已更新: {updates}")
        else:
            logger.info(f"新用户 {platform}:{user_id}，将创建记录。")
            unique_person_name = await self.naming_service.generate_unique_person_name(effective_name)
            new_person_data = {
                "person_id": person_id,
                "platform": platform,
                "user_id": str(user_id),
                "nickname": nickname,
                "person_name": unique_person_name,
                "name_reason": "首次遇见时自动设置",
                "know_since": int(time.time()),
                "last_know": int(time.time()),
            }
            await self.repository.safe_create_person_info(person_id, new_person_data)

        return person_id

    async def first_knowing_some_one(self, platform: str, user_id: str, user_nickname: str, user_cardname: str):
        person_id = get_person_id(platform, user_id)
        unique_nickname = await self.naming_service.generate_unique_person_name(user_nickname)
        data = {
            "platform": platform,
            "user_id": user_id,
            "nickname": user_nickname,
            "konw_time": int(time.time()),
            "person_name": unique_nickname,
        }
        await self.repository.safe_create_person_info(person_id=person_id, data=data)
        await self.repository.update_field(person_id=person_id, field_name="nickname", value=user_nickname, data=data)

    async def get_or_create_person(
        self,
        platform: str,
        user_id: int,
        nickname: str,
        user_cardname: str,
        user_avatar: str | None = None,
    ) -> str:
        person_id = get_person_id(platform, user_id)

        async def _db_get_or_create_async(p_id: str, init_data: dict):
            record = await self.crud.get_by(person_id=p_id)
            if record:
                return record, False
            try:
                new_person = await self.crud.create(init_data)
                return new_person, True
            except Exception as exc:  # noqa: BLE001
                if "UNIQUE constraint failed" in str(exc):
                    logger.debug(f"检测到并发创建用户 {p_id}，获取现有记录")
                    record = await self.crud.get_by(person_id=p_id)
                    if record:
                        return record, False
                raise exc

        unique_nickname = await self.naming_service.generate_unique_person_name(nickname)
        initial_data = {
            "person_id": person_id,
            "platform": platform,
            "user_id": str(user_id),
            "nickname": nickname,
            "person_name": unique_nickname,
            "name_reason": "从群昵称获取",
            "know_times": 0,
            "know_since": int(datetime.datetime.now().timestamp()),
            "last_know": int(datetime.datetime.now().timestamp()),
            "impression": None,
            "points": [],
            "forgotten_points": [],
        }

        for key in JSON_SERIALIZED_FIELDS:
            if key in initial_data:
                if isinstance(initial_data[key], list | dict):
                    initial_data[key] = orjson.dumps(initial_data[key]).decode("utf-8")
                elif initial_data[key] is None:
                    initial_data[key] = orjson.dumps([]).decode("utf-8")

        model_fields = [column.name for column in PersonInfo.__table__.columns]
        filtered_initial_data = {k: v for k, v in initial_data.items() if v is not None and k in model_fields}

        _record, was_created = await _db_get_or_create_async(person_id, filtered_initial_data)

        if was_created:
            logger.info(f"用户 {platform}:{user_id} (person_id: {person_id}) 不存在，将创建新记录。")
            logger.info(f"已为 {person_id} 创建新记录，初始数据: {filtered_initial_data}")
        else:
            logger.debug(f"用户 {platform}:{user_id} (person_id: {person_id}) 已存在，返回现有记录。")

        return person_id

    @cached(ttl=600, key_prefix="person_info_by_name", use_kwargs=False)
    async def get_person_info_by_name(self, person_name: str) -> dict | None:
        if not person_name:
            logger.debug("get_person_info_by_name 获取失败：person_name 不能为空")
            return None

        records = await self.crud.get_multi(person_name=person_name, limit=1)
        if records:
            record = records[0]
            found_person_id = record.person_id
        else:
            logger.debug(f"数据库中未找到名为 '{person_name}' 的用户")
            return None

        if found_person_id:
            required_fields = [
                "person_id",
                "platform",
                "user_id",
                "nickname",
                "user_cardname",
                "user_avatar",
                "person_name",
                "name_reason",
            ]
            model_fields = [column.name for column in PersonInfo.__table__.columns]
            valid_fields_to_get = [f for f in required_fields if f in model_fields or f in person_info_default]
            person_data = await self.repository.get_values(found_person_id, valid_fields_to_get)
            if person_data:
                return {key: person_data.get(key) for key in required_fields}
            logger.warning(f"找到了 person_id '{found_person_id}' 但 get_values 返回空")
            return None

        logger.error(f"逻辑错误：未能为 '{person_name}' 确定 person_id")
        return None


__all__ = ["PersonInfoService"]
