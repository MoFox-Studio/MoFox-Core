import orjson
from json_repair import repair_json

from src.common.database.api.crud import CRUDBase
from src.common.database.core.models import PersonInfo
from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest

logger = get_logger("person_info.naming")


class PersonNamingService:
    """Handle name generation and update flows."""

    def __init__(self, repository):
        assert model_config is not None
        self.repository = repository
        self.qv_name_llm = LLMRequest(model_set=model_config.model_task_config.utils, request_type="relation.qv_name")
        self.crud = CRUDBase(PersonInfo)

    @staticmethod
    def _extract_json_from_text(text: str) -> dict:
        try:
            fixed_json = repair_json(text)
            parsed_json = orjson.loads(fixed_json) if isinstance(fixed_json, str) else fixed_json
            if isinstance(parsed_json, list) and parsed_json:
                parsed_json = parsed_json[0]
            if isinstance(parsed_json, dict):
                return parsed_json
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"JSON提取失败: {exc}")

        logger.warning(f"无法从文本中提取有效的JSON字典: {text}")
        logger.info(f"文本: {text}")
        return {"nickname": "", "reason": ""}

    async def _generate_unique_person_name(self, base_name: str) -> str:
        if not base_name or base_name.isspace():
            base_name = "空格"

        try:
            existing_record = await self.crud.get_by(person_name=base_name)
            if not existing_record:
                return base_name

            counter = 1
            while True:
                new_name = f"{base_name}[{counter}]"
                existing_new_record = await self.crud.get_by(person_name=new_name)
                if not existing_new_record:
                    return new_name
                counter += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(f"生成唯一person_name时出错: {exc}")
            import time

            return f"{base_name}_{int(time.time())}"

    async def generate_unique_person_name(self, base_name: str) -> str:
        """Public wrapper to generate a unique name for reuse by services."""
        return await self._generate_unique_person_name(base_name)

    async def assign_name(
        self,
        person_id: str,
        user_nickname: str,
        user_cardname: str,
        user_avatar: str | None,
        request: str = "",
    ) -> dict | None:
        if not person_id:
            logger.debug("取名失败：person_id不能为空")
            return None

        old_name = await self.repository.get_value(person_id, "person_name")
        old_reason = await self.repository.get_value(person_id, "name_reason")

        max_retries = 8
        current_try = 0
        existing_names_str = ""

        try:
            all_records = await self.crud.get_multi(limit=1000)
            current_name_set = {record.person_name for record in all_records if record.person_name}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"获取现有名称列表失败: {exc}")
            current_name_set = set()

        while current_try < max_retries:
            bot_name = global_config.bot.nickname
            qv_name_prompt = f"你是{bot_name}，一个伪装成人类的AI，你不能让别人发现这一点，"
            qv_name_prompt += f"现在你想给一个用户取一个昵称，用户的qq昵称是{user_nickname}，"
            qv_name_prompt += f"用户的qq群昵称名是{user_cardname}，"
            if user_avatar:
                qv_name_prompt += f"用户的qq头像是{user_avatar}，"
            if old_name:
                qv_name_prompt += f"你之前叫他{old_name}，是因为{old_reason}，"

            qv_name_prompt += f"\n其他取名的要求是：{request}，不要太浮夸，简短，"
            qv_name_prompt += "\n请根据以上用户信息，想想你叫他什么比较好，不要太浮夸，请最好使用用户的qq昵称或群昵称原文，可以稍作修改，优先使用原文。优先使用用户的qq昵称或者群昵称原文。"

            if existing_names_str:
                qv_name_prompt += f"\n请注意，以下名称已被你尝试过或已知存在，请避免：{existing_names_str}。\n"

            if len(current_name_set) < 50 and current_name_set:
                qv_name_prompt += f"已知的其他昵称有: {', '.join(list(current_name_set)[:10])}等。\n"

            qv_name_prompt += "请用json给出你的想法，并给出理由，示例如下："""{
                \"nickname\": \"昵称\",\n                \"reason\": \"理由\"\n            }""""""
            response, _ = await self.qv_name_llm.generate_response_async(qv_name_prompt)
            result = self._extract_json_from_text(response)

            if not result or not result.get("nickname"):
                logger.error("生成的昵称为空或结果格式不正确，重试中...")
                current_try += 1
                continue

            generated_nickname = result["nickname"]
            is_duplicate = False

            if generated_nickname in current_name_set:
                is_duplicate = True
                logger.info(f"尝试给用户{user_nickname} {person_id} 取名，但是 {generated_nickname} 已存在，重试中...")
            else:
                existing_record = await self.crud.get_by(person_name=generated_nickname)
                if existing_record:
                    is_duplicate = True
                    current_name_set.add(generated_nickname)

            if not is_duplicate:
                await self.repository.update_field(person_id, "person_name", generated_nickname)
                await self.repository.update_field(person_id, "name_reason", result.get("reason", "未提供理由"))
                logger.info(
                    f"成功给用户{user_nickname} {person_id} 取名 {generated_nickname}，理由：{result.get('reason', '未提供理由')}"
                )
                return result

            if existing_names_str:
                existing_names_str += "、"
            existing_names_str += generated_nickname
            logger.debug(f"生成的昵称 {generated_nickname} 已存在，重试中...")
            current_try += 1

        unique_nickname = await self._generate_unique_person_name(user_nickname)
        logger.warning(f"在{max_retries}次尝试后未能生成唯一昵称，使用默认昵称 {unique_nickname}")
        await self.repository.update_field(person_id, "person_name", unique_nickname)
        await self.repository.update_field(person_id, "name_reason", "使用用户原始昵称作为默认值")
        return {"nickname": unique_nickname, "reason": "使用用户原始昵称作为默认值"}


__all__ = ["PersonNamingService", "get_person_id"]
