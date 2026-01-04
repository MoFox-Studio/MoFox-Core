import pytest

from src.person_info.manager.constants import get_person_id
from src.person_info.manager.service import PersonInfoService


class FakeRecord:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeCRUD:
    def __init__(self, store: dict):
        self.store = store
        self._id_seq = 1

    async def get_by(self, person_id=None, person_name=None, nickname=None):
        if person_id:
            data = self.store.get(person_id)
            return FakeRecord(**data) if data else None
        if person_name:
            for data in self.store.values():
                if data.get("person_name") == person_name:
                    return FakeRecord(**data)
        if nickname:
            for data in self.store.values():
                if data.get("nickname") == nickname:
                    return FakeRecord(**data)
        return None

    async def get_multi(self, person_name=None, nickname=None, limit=1):
        matches = []
        for data in self.store.values():
            if person_name and data.get("person_name") == person_name:
                matches.append(FakeRecord(**data))
            if nickname and data.get("nickname") == nickname:
                matches.append(FakeRecord(**data))
            if len(matches) >= limit:
                break
        return matches

    async def create(self, data: dict):
        if "id" not in data:
            data = {**data, "id": self._id_seq}
            self._id_seq += 1
        self.store[data["person_id"]] = data
        return FakeRecord(**data)

    async def update(self, record_id: int, updates: dict):
        for person_id, record in self.store.items():
            if record.get("id") == record_id:
                self.store[person_id] = {**record, **updates}
                return

    async def delete(self, record_id: int):  # pragma: no cover - not used in current tests
        for person_id, record in list(self.store.items()):
            if record.get("id") == record_id:
                del self.store[person_id]
                return


class FakeRepository:
    def __init__(self, store: dict):
        self.store = store

    async def safe_create_person_info(self, person_id: str, data: dict | None = None):
        self.store[person_id] = {"person_id": person_id, **(data or {})}
        return True

    async def update_field(self, person_id: str, field_name: str, value, data: dict | None = None):
        if person_id not in self.store:
            await self.safe_create_person_info(person_id, data or {})
        self.store[person_id][field_name] = value
        return True

    async def get_value(self, person_id: str, field_name: str):
        return self.store.get(person_id, {}).get(field_name)


class FakeNamingService:
    async def generate_unique_person_name(self, base_name: str) -> str:
        return base_name or "空格"


@pytest.mark.asyncio
async def test_get_person_id_stable_hash():
    pid1 = get_person_id("qq", 123)
    pid2 = get_person_id("qq", "123")
    pid3 = get_person_id("qq-legacy", 123)
    pid4 = get_person_id("legacy", 123)

    assert pid1 == pid2
    assert pid3 == pid4  # dash-prefixed platform trims prefix
    assert pid1 != pid3  # different platform component produces different hash


@pytest.mark.asyncio
async def test_sync_user_info_creates_new_record():
    store: dict = {}
    repo = FakeRepository(store)
    naming = FakeNamingService()
    service = PersonInfoService(repository=repo, naming_service=naming)
    service.crud = FakeCRUD(store)

    person_id = await service.sync_user_info("qq", "123", nickname="Nick", cardname=None)

    assert person_id in store
    created = store[person_id]
    assert created["nickname"] == "Nick"
    assert created["person_name"] == "Nick"
    assert created["platform"] == "qq"
    assert created["user_id"] == "123"


@pytest.mark.asyncio
async def test_sync_user_info_updates_existing_record():
    person_id = get_person_id("qq", "123")
    store: dict = {person_id: {"person_id": person_id, "nickname": "Old", "platform": "qq", "user_id": "123", "id": 1}}
    repo = FakeRepository(store)
    naming = FakeNamingService()
    service = PersonInfoService(repository=repo, naming_service=naming)
    service.crud = FakeCRUD(store)

    await service.sync_user_info("qq", "123", nickname="NewNick", cardname=None)

    assert store[person_id]["nickname"] == "NewNick"
