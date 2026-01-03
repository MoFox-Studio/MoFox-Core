import time
import traceback
from typing import Any

import orjson
from json_repair import repair_json

from src.chat.utils.prompt import Prompt, global_prompt_manager
from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest
from src.person_info.person_info import get_person_info_manager

logger = get_logger("relationship_fetcher")


def init_real_time_info_prompts():
    """初始化实时信息提取相关的提示词"""
    relationship_prompt = """
<聊天记录>
{chat_observe_info}
</聊天记录>

{name_block}
现在，你想要回复{person_name}的消息，消息内容是：{target_message}。请根据聊天记录和你要回复的消息，从你对{person_name}的了解中提取有关的信息：
1.你需要提供你想要提取的信息具体是哪方面的信息，例如：年龄，性别，你们之间的交流方式，最近发生的事等等。
2.请注意，请不要重复调取相同的信息，已经调取的信息如下：
{info_cache_block}
3.如果当前聊天记录中没有需要查询的信息，或者现有信息已经足够回复，请返回{{"none": "不需要查询"}}

请以json格式输出，例如：

{{
    "info_type": "信息类型",
}}

请严格按照json输出格式，不要输出多余内容：
"""
    Prompt(relationship_prompt, "real_time_info_identify_prompt")

    fetch_info_prompt = """

{name_block}
以下是你在之前与{person_name}的交流中，产生的对{person_name}的了解：
{person_impression_block}
{points_text_block}

请从中提取用户"{person_name}"的有关"{info_type}"信息
请以json格式输出，例如：

{{
    {info_json_str}
}}

请严格按照json输出格式，不要输出多余内容：
"""
    Prompt(fetch_info_prompt, "real_time_fetch_person_info_prompt")


class RelationshipFetcher:
    def __init__(self, chat_id):
        self.chat_id = chat_id

        # 信息获取缓存：记录正在获取的信息请求
        self.info_fetching_cache: list[dict[str, Any]] = []

        # 信息结果缓存：存储已获取的信息结果，带TTL
        self.info_fetched_cache: dict[str, dict[str, Any]] = {}
        # 结构：{person_id: {info_type: {"info": str, "ttl": int, "start_time": float, "person_name": str, "unknown": bool}}}

        # LLM模型配置
        self.llm_model = LLMRequest(
            model_set=model_config.model_task_config.utils_small, request_type="relation.fetcher"
        )

        # 小模型用于即时信息提取
        self.instant_llm_model = LLMRequest(
            model_set=model_config.model_task_config.utils_small, request_type="relation.fetch"
        )

        self.log_prefix = f"[{self.chat_id}] 实时信息"  # 初始化时使用chat_id，稍后异步更新
        self._log_prefix_initialized = False

    async def _initialize_log_prefix(self):
        """异步初始化log_prefix"""
        if not self._log_prefix_initialized:
            from src.chat.message_receive.chat_stream import get_chat_manager

            name = await get_chat_manager().get_stream_name(self.chat_id)
            self.log_prefix = f"[{name}] 实时信息"
            self._log_prefix_initialized = True

    def _cleanup_expired_cache(self):
        """清理过期的信息缓存"""
        for person_id in list(self.info_fetched_cache.keys()):
            for info_type in list(self.info_fetched_cache[person_id].keys()):
                self.info_fetched_cache[person_id][info_type]["ttl"] -= 1
                if self.info_fetched_cache[person_id][info_type]["ttl"] <= 0:
                    del self.info_fetched_cache[person_id][info_type]
            if not self.info_fetched_cache[person_id]:
                del self.info_fetched_cache[person_id]

    async def build_relation_info(self, person_id, points_num=5):
        """构建详细的人物关系信息

        注意：现在只从 user_relationships 表读取印象和关系数据，
        person_info 表只用于获取基础信息（用户名、平台等）
        """
        # 初始化log_prefix
        await self._initialize_log_prefix()

        # 清理过期的信息缓存
        self._cleanup_expired_cache()

        person_info_manager = get_person_info_manager()

        # 仅从 person_info 获取基础信息（不获取印象相关字段）
        person_name = await person_info_manager.get_value(person_id, "person_name")
        await person_info_manager.get_value(person_id, "platform")

        # 构建详细的关系描述
        relation_parts = []

        # 从 UserRelationships 表获取完整关系信息（这是唯一的印象数据来源）
        try:
            from src.common.database.api.specialized import get_user_relationship

            # 查询用户关系数据
            user_id = str(await person_info_manager.get_value(person_id, "user_id"))

            # 使用优化后的API（带缓存）- 只需要user_id
            relationship = await get_user_relationship(user_id=user_id)

            if relationship:
                # 将SQLAlchemy对象转换为字典（只保留核心字段）
                try:
                    rel_data = {
                        "user_aliases": relationship.__dict__.get("user_aliases"),
                        "impression_text": relationship.__dict__.get("impression_text"),
                        "relationship_text": relationship.__dict__.get("relationship_text"),  # 兼容回退
                        "relationship_score": relationship.__dict__.get("relationship_score"),
                        "first_met_time": relationship.__dict__.get("first_met_time"),
                    }
                except Exception as attr_error:
                    logger.warning(f"访问relationship对象属性失败: {attr_error}")
                    rel_data = {}

                # 1. 用户别名
                if rel_data.get("user_aliases"):
                    aliases_list = [alias.strip() for alias in rel_data["user_aliases"].split(",") if alias.strip()]
                    if aliases_list:
                        aliases_str = "、".join(aliases_list)
                        relation_parts.append(f"{person_name}的别名有：{aliases_str}")

                # 2. 关系阶段和好感度（关系阶段从分数实时计算）
                if rel_data.get("relationship_score") is not None:
                    score = rel_data["relationship_score"]
                    stage = self._get_stage_from_score(score)
                    stage_desc = self._get_stage_description(stage)
                    relation_parts.append(f"你和{person_name}的关系：{stage_desc}（好感度{score:.2f}）")

                # 3. 认识时间
                if rel_data.get("first_met_time"):
                    from datetime import datetime
                    first_met = datetime.fromtimestamp(rel_data["first_met_time"]).strftime("%Y年%m月")
                    relation_parts.append(f"你们从{first_met}开始认识")

                # 4. 印象描述（优先使用 impression_text，兼容回退到 relationship_text）
                impression = rel_data.get("impression_text") or rel_data.get("relationship_text")
                if impression:
                    relation_parts.append(f"\n你对{person_name}的印象：\n{impression}")

                # 注：preference_keywords 和 key_facts 字段已废弃，不再读取显示

        except Exception as e:
            logger.error(f"查询UserRelationships表失败: {e}")

        # 构建最终的关系信息字符串
        if relation_parts:
            relation_info = f"关于{person_name}，你知道以下信息：\n" + "\n".join(
                [f"• {part}" for part in relation_parts]
            )
        else:
            # 只有当所有数据源都没有信息时才返回默认文本
            relation_info = f"你完全不认识{person_name}，这是你们第一次交流。"

        return relation_info

    async def build_chat_stream_impression(self, stream_id: str) -> str:
        """构建聊天流的印象信息

        Args:
            stream_id: 聊天流ID

        Returns:
            str: 格式化后的聊天流印象字符串
        """
        try:
            import time

            from src.common.database.api.crud import CRUDBase
            from src.common.database.api.specialized import get_or_create_chat_stream
            from src.common.database.core.models import ChatStreams

            # 先尝试通过stream_id直接查询现有记录
            crud = CRUDBase(ChatStreams)
            existing_stream = await crud.get_by(stream_id=stream_id)

            platform = "unknown"
            if existing_stream:
                # 从现有记录获取platform
                platform = getattr(existing_stream, "platform", "unknown") or "unknown"
                logger.debug(f"从现有ChatStream获取到platform: {platform}, stream_id: {stream_id}")
            else:
                logger.debug(f"未找到现有ChatStream记录，使用默认platform: unknown, stream_id: {stream_id}")

            current_time = time.time()

            stream, _ = await get_or_create_chat_stream(
                stream_id=stream_id,
                platform=platform,
                defaults={
                    "create_time": current_time,
                    "last_active_time": current_time,
                },
            )

            if not stream:
                return ""

            # 将SQLAlchemy对象转换为字典以保持兼容性
            # 直接使用 __dict__ 访问，避免触发 SQLAlchemy 的描述符和 lazy loading
            # 方案A已经确保所有字段在缓存前都已预加载，所以 __dict__ 中有完整数据
            try:
                stream_data = {
                    "group_name": stream.__dict__.get("group_name"),
                    "stream_impression_text": stream.__dict__.get("stream_impression_text"),
                    "stream_chat_style": stream.__dict__.get("stream_chat_style"),
                    "stream_topic_keywords": stream.__dict__.get("stream_topic_keywords"),
                    "stream_interest_score": stream.__dict__.get("stream_interest_score"),
                }
            except Exception as e:
                logger.warning(f"访问stream对象属性失败: {e}")
                stream_data = {}

            impression_parts = []

            # 1. 聊天环境基本信息
            if stream_data.get("group_name"):
                impression_parts.append(f"这是一个名为「{stream_data['group_name']}」的群聊")
            else:
                impression_parts.append("这是一个私聊对话")

            # 2. 聊天流的主观印象
            if stream_data.get("stream_impression_text"):
                impression_parts.append(f"你对这个聊天环境的印象：{stream_data['stream_impression_text']}")

            # 3. 聊天风格
            if stream_data.get("stream_chat_style"):
                impression_parts.append(f"这里的聊天风格：{stream_data['stream_chat_style']}")

            # 4. 常见话题
            if stream_data.get("stream_topic_keywords"):
                topics_list = [topic.strip() for topic in stream_data["stream_topic_keywords"].split(",") if topic.strip()]
                if topics_list:
                    topics_str = "、".join(topics_list)
                    impression_parts.append(f"这里常讨论的话题：{topics_str}")

            # 5. 兴趣程度
            if stream_data.get("stream_interest_score") is not None:
                interest_desc = self._get_interest_score_description(stream_data["stream_interest_score"])
                impression_parts.append(f"你对这个聊天环境的兴趣程度：{interest_desc}（{stream_data['stream_interest_score']:.2f}）")

            # 构建最终的印象信息字符串
            if impression_parts:
                impression_info = "关于当前的聊天环境：\n" + "\n".join(
                    [f"• {part}" for part in impression_parts]
                )
                return impression_info
            else:
                return ""

        except Exception as e:
            logger.debug(f"查询ChatStreams表失败: {e}")
            return ""

    def _get_interest_score_description(self, score: float) -> str:
        """根据兴趣分数返回描述性文字"""
        if score >= 0.8:
            return "非常感兴趣，很喜欢这里的氛围"
        elif score >= 0.6:
            return "比较感兴趣，愿意积极参与"
        elif score >= 0.4:
            return "一般兴趣，会适度参与"
        elif score >= 0.2:
            return "兴趣不大，较少主动参与"
        else:
            return "不太感兴趣，很少参与"

    def _get_attitude_description(self, attitude: int) -> str:
        """根据态度分数返回描述性文字"""
        if attitude >= 80:
            return "非常喜欢和欣赏"
        elif attitude >= 60:
            return "比较有好感"
        elif attitude >= 40:
            return "中立态度"
        elif attitude >= 20:
            return "有些反感"
        else:
            return "非常厌恶"

    def _get_relationship_score_description(self, score: float) -> str:
        """根据关系分数返回描述性文字"""
        if score >= 0.8:
            return "非常亲密的好友"
        elif score >= 0.6:
            return "关系不错的朋友"
        elif score >= 0.4:
            return "普通熟人"
        elif score >= 0.2:
            return "认识但不熟悉"
        else:
            return "陌生人"

    def _get_stage_from_score(self, score: float) -> str:
        """根据好感度分数返回关系阶段"""
        if score >= 0.9:
            return "bestie"
        elif score >= 0.75:
            return "close_friend"
        elif score >= 0.6:
            return "friend"
        elif score >= 0.4:
            return "familiar"
        elif score >= 0.2:
            return "acquaintance"
        else:
            return "stranger"

    def _get_stage_description(self, stage: str) -> str:
        """根据关系阶段返回描述性文字"""
        stage_map = {
            "stranger": "陌生人",
            "acquaintance": "初识",
            "familiar": "熟人",
            "friend": "朋友",
            "close_friend": "好友",
            "bestie": "挚友",
        }
        return stage_map.get(stage, "未知关系")

    async def _build_fetch_query(self, person_id, target_message, chat_history):
        nickname_str = ",".join(global_config.bot.alias_names)
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"
        person_info_manager = get_person_info_manager()
        person_name: str = await person_info_manager.get_value(person_id, "person_name")  # type: ignore

        info_cache_block = self._build_info_cache_block()

        prompt = (await global_prompt_manager.get_prompt_async("real_time_info_identify_prompt")).format(
            chat_observe_info=chat_history,
            name_block=name_block,
            info_cache_block=info_cache_block,
            person_name=person_name,
            target_message=target_message,
        )

        try:
            logger.debug(f"{self.log_prefix} 信息识别prompt: \n{prompt}\n")
            content, _ = await self.llm_model.generate_response_async(prompt=prompt)

            if content:
                content_json = orjson.loads(repair_json(content))

                # 检查是否返回了不需要查询的标志
                if "none" in content_json:
                    logger.debug(f"{self.log_prefix} LLM判断当前不需要查询任何信息：{content_json.get('none', '')}")
                    return None

                if info_type := content_json.get("info_type"):
                    # 记录信息获取请求
                    self.info_fetching_cache.append(
                        {
                            "person_id": await get_person_info_manager().get_person_id_by_person_name(person_name),
                            "person_name": person_name,
                            "info_type": info_type,
                            "start_time": time.time(),
                            "forget": False,
                        }
                    )

                    # 限制缓存大小
                    if len(self.info_fetching_cache) > 10:
                        self.info_fetching_cache.pop(0)

                    logger.info(f"{self.log_prefix} 识别到需要调取用户 {person_name} 的[{info_type}]信息")
                    return info_type
                else:
                    logger.warning(f"{self.log_prefix} LLM未返回有效的info_type。响应: {content}")

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行信息识别LLM请求时出错: {e}")
            logger.error(traceback.format_exc())

        return None

    def _build_info_cache_block(self) -> str:
        """构建已获取信息的缓存块"""
        info_cache_block = ""
        if self.info_fetching_cache:
            # 对于每个(person_id, info_type)组合，只保留最新的记录
            latest_records = {}
            for info_fetching in self.info_fetching_cache:
                key = (info_fetching["person_id"], info_fetching["info_type"])
                if key not in latest_records or info_fetching["start_time"] > latest_records[key]["start_time"]:
                    latest_records[key] = info_fetching

            # 按时间排序并生成显示文本
            sorted_records = sorted(latest_records.values(), key=lambda x: x["start_time"])
            for info_fetching in sorted_records:
                info_cache_block += (
                    f"你已经调取了[{info_fetching['person_name']}]的[{info_fetching['info_type']}]信息\n"
                )
        return info_cache_block

    async def _extract_single_info(self, person_id: str, info_type: str, person_name: str):
        """提取单个信息类型

        Args:
            person_id: 用户ID
            info_type: 信息类型
            person_name: 用户名
        """
        start_time = time.time()
        person_info_manager = get_person_info_manager()

        # 首先检查 info_list 缓存
        info_list = await person_info_manager.get_value(person_id, "info_list") or []
        cached_info = None

        # 查找对应的 info_type
        for info_item in info_list:
            if info_item.get("info_type") == info_type:
                cached_info = info_item.get("info_content")
                logger.debug(f"{self.log_prefix} 在info_list中找到 {person_name} 的 {info_type} 信息: {cached_info}")
                break

        # 如果缓存中有信息，直接使用
        if cached_info:
            if person_id not in self.info_fetched_cache:
                self.info_fetched_cache[person_id] = {}

            self.info_fetched_cache[person_id][info_type] = {
                "info": cached_info,
                "ttl": 2,
                "start_time": start_time,
                "person_name": person_name,
                "unknown": cached_info == "none",
            }
            logger.info(f"{self.log_prefix} 记得 {person_name} 的 {info_type}: {cached_info}")
            return

        # 如果缓存中没有，尝试从用户档案中提取
        try:
            person_impression = await person_info_manager.get_value(person_id, "impression")
            points = await person_info_manager.get_value(person_id, "points")

            # 构建印象信息块
            if person_impression:
                person_impression_block = (
                    f"<对{person_name}的总体了解>\n{person_impression}\n</对{person_name}的总体了解>"
                )
            else:
                person_impression_block = ""

            # 构建要点信息块
            if points:
                points_text = "\n".join([f"{point[2]}:{point[0]}" for point in points])
                points_text_block = f"<对{person_name}的近期了解>\n{points_text}\n</对{person_name}的近期了解>"
            else:
                points_text_block = ""

            # 如果完全没有用户信息
            if not points_text_block and not person_impression_block:
                if person_id not in self.info_fetched_cache:
                    self.info_fetched_cache[person_id] = {}
                self.info_fetched_cache[person_id][info_type] = {
                    "info": "none",
                    "ttl": 2,
                    "start_time": start_time,
                    "person_name": person_name,
                    "unknown": True,
                }
                logger.info(f"{self.log_prefix} 完全不认识 {person_name}")
                await self._save_info_to_cache(person_id, info_type, "none")
                return

            # 使用LLM提取信息
            nickname_str = ",".join(global_config.bot.alias_names)
            name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"

            prompt = (await global_prompt_manager.get_prompt_async("real_time_fetch_person_info_prompt")).format(
                name_block=name_block,
                info_type=info_type,
                person_impression_block=person_impression_block,
                person_name=person_name,
                info_json_str=f'"{info_type}": "有关{info_type}的信息内容"',
                points_text_block=points_text_block,
            )

            # 使用小模型进行即时提取
            content, _ = await self.instant_llm_model.generate_response_async(prompt=prompt)

            if content:
                content_json = orjson.loads(repair_json(content))
                if info_type in content_json:
                    info_content = content_json[info_type]
                    is_unknown = info_content == "none" or not info_content

                    # 保存到运行时缓存
                    if person_id not in self.info_fetched_cache:
                        self.info_fetched_cache[person_id] = {}
                    self.info_fetched_cache[person_id][info_type] = {
                        "info": "unknown" if is_unknown else info_content,
                        "ttl": 3,
                        "start_time": start_time,
                        "person_name": person_name,
                        "unknown": is_unknown,
                    }

                    # 保存到持久化缓存 (info_list)
                    await self._save_info_to_cache(person_id, info_type, "none" if is_unknown else info_content)

                    if not is_unknown:
                        logger.info(f"{self.log_prefix} 思考得到，{person_name} 的 {info_type}: {info_content}")
                    else:
                        logger.info(f"{self.log_prefix} 思考了也不知道{person_name} 的 {info_type} 信息")
            else:
                logger.warning(f"{self.log_prefix} 小模型返回空结果，获取 {person_name} 的 {info_type} 信息失败。")

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行信息提取时出错: {e}")
            logger.error(traceback.format_exc())

    async def _save_info_to_cache(self, person_id: str, info_type: str, info_content: str):
        # sourcery skip: use-next
        """将提取到的信息保存到 person_info 的 info_list 字段中

        Args:
            person_id: 用户ID
            info_type: 信息类型
            info_content: 信息内容
        """
        try:
            person_info_manager = get_person_info_manager()

            # 获取现有的 info_list
            info_list = await person_info_manager.get_value(person_id, "info_list") or []

            # 查找是否已存在相同 info_type 的记录
            found_index = -1
            for i, info_item in enumerate(info_list):
                if isinstance(info_item, dict) and info_item.get("info_type") == info_type:
                    found_index = i
                    break

            # 创建新的信息记录
            new_info_item = {
                "info_type": info_type,
                "info_content": info_content,
            }

            if found_index >= 0:
                # 更新现有记录
                info_list[found_index] = new_info_item
                logger.info(f"{self.log_prefix} [缓存更新] 更新 {person_id} 的 {info_type} 信息缓存")
            else:
                # 添加新记录
                info_list.append(new_info_item)
                logger.info(f"{self.log_prefix} [缓存保存] 新增 {person_id} 的 {info_type} 信息缓存")

            # 保存更新后的 info_list
            await person_info_manager.update_one_field(person_id, "info_list", info_list)

        except Exception as e:
            logger.error(f"{self.log_prefix} [缓存保存] 保存信息到缓存失败: {e}")
            logger.error(traceback.format_exc())


class RelationshipFetcherManager:
    """关系提取器管理器

    管理不同 chat_id 的 RelationshipFetcher 实例
    """

    def __init__(self):
        self._fetchers: dict[str, RelationshipFetcher] = {}

    def get_fetcher(self, chat_id: str) -> RelationshipFetcher:
        """获取或创建指定 chat_id 的 RelationshipFetcher

        Args:
            chat_id: 聊天ID

        Returns:
            RelationshipFetcher: 关系提取器实例
        """
        if chat_id not in self._fetchers:
            self._fetchers[chat_id] = RelationshipFetcher(chat_id)
        return self._fetchers[chat_id]

    def remove_fetcher(self, chat_id: str):
        """移除指定 chat_id 的 RelationshipFetcher

        Args:
            chat_id: 聊天ID
        """
        if chat_id in self._fetchers:
            del self._fetchers[chat_id]

    def clear_all(self):
        """清空所有 RelationshipFetcher"""
        self._fetchers.clear()

    def get_active_chat_ids(self) -> list[str]:
        """获取所有活跃的 chat_id 列表"""
        return list(self._fetchers.keys())


# 全局管理器实例
relationship_fetcher_manager = RelationshipFetcherManager()


init_real_time_info_prompts()
