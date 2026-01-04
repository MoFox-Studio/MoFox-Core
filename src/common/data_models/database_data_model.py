import json
from dataclasses import dataclass, field
from typing import Any

from . import BaseDataModel


@dataclass(slots=True)
class DatabaseUserInfo(BaseDataModel):
    """
    用户信息数据模型，用于存储用户的基本信息。
    该类通过 dataclass 实现，继承自 BaseDataModel。
    使用 __slots__ 优化内存占用和属性访问性能。
    """
    platform: str = field(default_factory=str)  # 用户所属平台（如微信、QQ 等）
    user_id: str = field(default_factory=str)  # 用户唯一标识 ID
    user_nickname: str = field(default_factory=str)  # 用户昵称
    user_cardname: str | None = None  # 用户备注名或群名片，可为空
    role: str | None = None  # 群成员角色 (owner/admin/member)，可为空

    @classmethod
    def from_dict(cls, data: dict) -> "DatabaseUserInfo":
        """从字典创建实例"""
        return cls(
            platform=data.get("platform", ""),
            user_id=data.get("user_id", ""),
            user_nickname=data.get("user_nickname", ""),
            user_cardname=data.get("user_cardname"),
            role=data.get("role"),
        )

    def to_dict(self) -> dict:
        """将实例转换为字典"""
        return {
            "platform": self.platform,
            "user_id": self.user_id,
            "user_nickname": self.user_nickname,
            "user_cardname": self.user_cardname,
            "role": self.role,
        }


@dataclass(slots=True)
class DatabaseGroupInfo(BaseDataModel):
    """
    群组信息数据模型，用于存储群组的基本信息。
    使用 __slots__ 优化内存占用和属性访问性能。
    """
    group_id: str = field(default_factory=str)  # 群组唯一标识 ID
    group_name: str = field(default_factory=str)  # 群组名称
    platform: str | None = None  # 群组所在平台，可为空

    @classmethod
    def from_dict(cls, data: dict) -> "DatabaseGroupInfo":
        """从字典创建实例"""
        return cls(
            group_id=data.get("group_id", ""),
            group_name=data.get("group_name", ""),
            platform=data.get("platform"),
        )

    def to_dict(self) -> dict:
        """将实例转换为字典"""
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "group_platform": self.platform,
        }


@dataclass(slots=True)
class DatabaseChatInfo(BaseDataModel):
    """
    聊天会话信息数据模型，用于描述一个聊天对话的上下文信息。
    包括会话 ID、平台、创建时间、最后活跃时间以及关联的用户和群组信息。
    使用 __slots__ 优化内存占用和属性访问性能。
    """
    stream_id: str = field(default_factory=str)  # 会话流 ID，唯一标识一个聊天对话
    platform: str = field(default_factory=str)  # 所属平台（如微信、QQ 等）
    create_time: float = field(default_factory=float)  # 会话创建时间戳
    last_active_time: float = field(default_factory=float)  # 最后一次活跃时间戳
    user_info: DatabaseUserInfo = field(default_factory=DatabaseUserInfo)  # 关联的用户信息
    group_info: DatabaseGroupInfo | None = None  # 关联的群组信息，可为空（私聊场景）


@dataclass(init=False)
class DatabaseMessages(BaseDataModel):
    """
    消息数据模型，用于存储每一条消息的完整信息，包括内容、元数据、用户、聊天上下文等。
    使用 init=False 实现自定义初始化逻辑，通过 __init__ 手动设置字段。
    使用 __slots__ 优化内存占用和属性访问性能。
    """

    __slots__ = (
        "actions",
        "additional_config",
        "chat_id",
        "chat_info",
        "display_message",
        "group_info",
        "has_emoji",
        "has_picid",
        "interest_calculated",
        "interest_value",
        "is_at",
        "is_command",
        "is_emoji",
        "is_mentioned",
        "is_notify",
        "is_picid",
        "is_public_notice",
        "is_read",
        "is_video",
        "is_voice",
        "key_words",
        "key_words_lite",
        # 基础消息字段
        "message_id",
        "notice_type",
        "priority_info",
        "priority_mode",
        "processed_plain_text",
        "reply_probability_boost",
        "reply_to",
        "selected_expressions",
        # 运行时扩展字段（固定）
        "semantic_embedding",
        "should_act",
        "should_reply",
        "time",
        # 关联对象
        "user_info",
    )

    def __init__(
        self,
        message_id: str = "",  # 消息唯一 ID
        time: float = 0.0,  # 消息时间戳
        chat_id: str = "",  # 所属聊天会话 ID
        reply_to: str | None = None,  # 回复的目标消息 ID，可为空
        interest_value: float | None = None,  # 消息兴趣度评分，用于优先级判断
        key_words: str | None = None,  # 消息关键词，用于内容分析
        key_words_lite: str | None = None,  # 精简关键词，可能用于快速匹配
        is_mentioned: bool | None = None,  # 是否被提及（@）
        is_at: bool | None = None,  # 是否直接 @ 机器人
        reply_probability_boost: float | None = None,  # 回复概率增强值，影响是否回复
        processed_plain_text: str | None = None,  # 处理后的纯文本内容
        display_message: str | None = None,  # 显示消息内容（可能包含格式）
        priority_mode: str | None = None,  # 优先级模式
        priority_info: str | None = None,  # 优先级附加信息
        additional_config: str | None = None,  # 额外配置字符串
        is_emoji: bool = False,  # 是否为表情消息
        is_picid: bool = False,  # 是否为图片消息（包含图片 ID）
        is_command: bool = False,  # 是否为命令消息（如 /help）
        is_notify: bool = False,  # 是否为 notice 消息（如禁言、戳一戳等系统事件）
        is_public_notice: bool = False,  # 是否为公共 notice（所有聊天可见）
        notice_type: str | None = None,  # notice 类型（由适配器指定，如 "group_ban", "poke" 等）
        selected_expressions: str | None = None,  # 选择的表情或响应模板
        is_read: bool = False,  # 是否已读
        actions: list | None = None,  # 与消息相关的动作列表（如回复、转发等）
        should_reply: bool = False,  # 是否应该自动回复
        should_act: bool = False,  # 是否应该执行动作（如发送消息）
        # 用户信息（用于构建 user_info）
        user_id: str = "",
        user_nickname: str = "",
        user_cardname: str | None = None,
        user_role: str | None = None, # 新增角色字段
        user_platform: str = "",
        # 群组 / 聊天上下文信息（用于构建 group_info / chat_info）
        chat_info_group_id: str | None = None,
        chat_info_group_name: str | None = None,
        chat_info_group_platform: str | None = None,
        chat_info_user_id: str = "",
        chat_info_user_nickname: str = "",
        chat_info_user_cardname: str | None = None,
        chat_info_user_platform: str = "",
        chat_info_stream_id: str = "",
        chat_info_platform: str = "",
        chat_info_create_time: float = 0.0,
        chat_info_last_active_time: float = 0.0,
        # 运行时字段（固定）
        semantic_embedding: Any | None = None,
        interest_calculated: bool = False,
        is_voice: bool = False,  # 是否为语音消息
        is_video: bool = False,  # 是否为视频消息
        has_emoji: bool = False,  # 是否包含表情
        has_picid: bool = False,  # 是否包含图片 ID
    ):
        # 初始化基础字段
        self.message_id = message_id
        self.time = time
        self.chat_id = chat_id
        self.reply_to = reply_to
        self.interest_value = interest_value
        self.key_words = key_words
        self.key_words_lite = key_words_lite
        self.is_mentioned = is_mentioned
        self.is_at = is_at
        self.reply_probability_boost = reply_probability_boost
        self.processed_plain_text = processed_plain_text
        self.display_message = display_message
        self.priority_mode = priority_mode
        self.priority_info = priority_info
        self.additional_config = additional_config
        self.is_emoji = is_emoji
        self.is_picid = is_picid
        self.is_command = is_command
        self.is_notify = is_notify
        self.is_public_notice = is_public_notice
        self.notice_type = notice_type
        self.selected_expressions = selected_expressions
        self.is_read = is_read
        self.actions = actions
        self.should_reply = should_reply
        self.should_act = should_act

        # 构建用户信息对象
        self.user_info = DatabaseUserInfo(
            user_id=user_id,
            user_nickname=user_nickname,
            user_cardname=user_cardname,
            role=user_role,
            platform=user_platform,
        )

        # 构建群组信息对象（仅当群组信息完整时）
        self.group_info = None
        if chat_info_group_id and chat_info_group_name:
            self.group_info = DatabaseGroupInfo(
                group_id=chat_info_group_id,
                group_name=chat_info_group_name,
                platform=chat_info_group_platform,
            )

        # 构建聊天信息对象
        self.chat_info = DatabaseChatInfo(
            stream_id=chat_info_stream_id,
            platform=chat_info_platform,
            create_time=chat_info_create_time,
            last_active_time=chat_info_last_active_time,
            user_info=DatabaseUserInfo(
                user_id=chat_info_user_id,
                user_nickname=chat_info_user_nickname,
                user_cardname=chat_info_user_cardname,
                platform=chat_info_user_platform,
            ),
            group_info=self.group_info,
        )

        # 运行时字段
        self.semantic_embedding = semantic_embedding
        self.interest_calculated = interest_calculated
        self.is_voice = is_voice
        self.is_video = is_video
        self.has_emoji = has_emoji
        self.has_picid = has_picid
        # 注意: id 参数从数据库加载时会传入，但不存储（使用 message_id 作为业务主键）

    def flatten(self) -> dict[str, Any]:
        """
        将消息对象转换为字典格式，便于序列化存储或传输。
        嵌套对象（如 user_info、group_info、chat_info）展开为扁平结构。
        """
        return {
            "message_id": self.message_id,
            "time": self.time,
            "chat_id": self.chat_id,
            "reply_to": self.reply_to,
            "interest_value": self.interest_value,
            "key_words": self.key_words,
            "key_words_lite": self.key_words_lite,
            "is_mentioned": self.is_mentioned,
            "is_at": self.is_at,
            "reply_probability_boost": self.reply_probability_boost,
            "processed_plain_text": self.processed_plain_text,
            "display_message": self.display_message,
            "priority_mode": self.priority_mode,
            "priority_info": self.priority_info,
            "additional_config": self.additional_config,
            "is_emoji": self.is_emoji,
            "is_picid": self.is_picid,
            "is_command": self.is_command,
            "is_notify": self.is_notify,
            "is_public_notice": self.is_public_notice,
            "notice_type": self.notice_type,
            "selected_expressions": self.selected_expressions,
            "is_read": self.is_read,
            "actions": self.actions,
            "should_reply": self.should_reply,
            "should_act": self.should_act,
            # user_info 展开
            "user_id": self.user_info.user_id,
            "user_nickname": self.user_info.user_nickname,
            "user_cardname": self.user_info.user_cardname,
            "user_role": self.user_info.role,
            "user_platform": self.user_info.platform,
            # group_info 展开（可能为 None）
            "chat_info_group_id": self.group_info.group_id if self.group_info else None,
            "chat_info_group_name": self.group_info.group_name if self.group_info else None,
            "chat_info_group_platform": self.group_info.platform if self.group_info else None,
            # chat_info 展开
            "chat_info_stream_id": self.chat_info.stream_id,
            "chat_info_platform": self.chat_info.platform,
            "chat_info_create_time": self.chat_info.create_time,
            "chat_info_last_active_time": self.chat_info.last_active_time,
            "chat_info_user_id": self.chat_info.user_info.user_id,
            "chat_info_user_nickname": self.chat_info.user_info.user_nickname,
            "chat_info_user_cardname": self.chat_info.user_info.user_cardname,
            "chat_info_user_platform": self.chat_info.user_info.platform,
            # 运行时字段
            "semantic_embedding": self.semantic_embedding,
            "interest_calculated": self.interest_calculated,
        }

    def update_message_info(
        self, interest_value: float | None = None, actions: list | None = None, should_reply: bool | None = None
    ):
        """
        更新消息的关键信息字段，支持部分更新。

        Args:
            interest_value: 兴趣度值，用于影响消息优先级
            actions: 要执行的动作列表，替换原有列表
            should_reply: 是否应该回复的标志
        """
        if interest_value is not None:
            self.interest_value = interest_value
        if actions is not None:
            self.actions = actions
        if should_reply is not None:
            self.should_reply = should_reply

    def add_action(self, action: str):
        """
        向消息的动作列表中添加一个动作。

        Args:
            action: 要添加的动作名称（字符串）
        """
        if self.actions is None:
            self.actions = []
        if action not in self.actions:  # 避免重复添加
            self.actions.append(action)

    def get_actions(self) -> list:
        """
        获取消息的动作列表。

        Returns:
            动作列表，如果没有动作则返回空列表。
        """
        return self.actions or []

    def get_message_summary(self) -> dict[str, Any]:
        """
        获取消息的关键摘要信息，用于日志、通知或前端展示。

        Returns:
            包含消息 ID、时间、兴趣度、动作、回复状态、用户昵称和显示内容的摘要字典。
        """
        return {
            "message_id": self.message_id,
            "time": self.time,
            "interest_value": self.interest_value,
            "actions": self.actions,
            "should_reply": self.should_reply,
            "user_nickname": self.user_info.user_nickname,
            "display_message": self.display_message,
        }

    # DatabaseMessages 接受的所有参数名集合（用于 from_dict 过滤）
    _VALID_INIT_PARAMS: frozenset[str] = frozenset({
        "message_id", "time", "chat_id", "reply_to", "interest_value",
        "key_words", "key_words_lite", "is_mentioned", "is_at",
        "reply_probability_boost", "processed_plain_text", "display_message",
        "priority_mode", "priority_info", "additional_config",
        "is_emoji", "is_picid", "is_command", "is_notify", "is_public_notice",
        "notice_type", "selected_expressions", "is_read", "actions",
        "should_reply", "should_act",
        "user_id", "user_nickname", "user_cardname", "user_role", "user_platform",
        "chat_info_group_id", "chat_info_group_name", "chat_info_group_platform",
        "chat_info_user_id", "chat_info_user_nickname", "chat_info_user_cardname",
        "chat_info_user_platform", "chat_info_stream_id", "chat_info_platform",
        "chat_info_create_time", "chat_info_last_active_time",
        "semantic_embedding", "interest_calculated",
        "is_voice", "is_video", "has_emoji", "has_picid",
    })

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatabaseMessages":
        """
        从字典创建 DatabaseMessages 实例，自动过滤掉不支持的参数。

        Args:
            data: 包含消息数据的字典（如从数据库查询返回的结果）

        Returns:
            DatabaseMessages 实例
        """
        # 只保留有效的参数
        filtered_data = {k: v for k, v in data.items() if k in cls._VALID_INIT_PARAMS}
        return cls(**filtered_data)


@dataclass(init=False)
class DatabaseActionRecords(BaseDataModel):
    """
    动作记录数据模型，用于记录系统执行的某个操作或动作的详细信息。
    用于审计、日志或调试。
    使用 __slots__ 优化内存占用和属性访问性能。
    """

    __slots__ = (
        "action_build_into_prompt",
        "action_data",
        "action_done",
        "action_id",
        "action_name",
        "action_prompt_display",
        "chat_id",
        "chat_info_platform",
        "chat_info_stream_id",
        "time",
    )

    def __init__(
        self,
        action_id: str,  # 动作唯一 ID
        time: float,  # 动作执行时间戳
        action_name: str,  # 动作名称（如 send_message、reply_with_image）
        action_data: str,  # 动作的参数数据，以 JSON 字符串形式存储
        action_done: bool,  # 动作是否成功完成
        action_build_into_prompt: bool,  # 是否将动作结果用于构建 prompt
        action_prompt_display: str,  # 动作在 prompt 中的显示文本
        chat_id: str,  # 所属聊天 ID
        chat_info_stream_id: str,  # 所属聊天流 ID
        chat_info_platform: str,  # 所属平台
    ):
        self.action_id = action_id
        self.time = time
        self.action_name = action_name
        # 解析传入的 action_data 字符串为 Python 对象
        if isinstance(action_data, str):
            self.action_data = json.loads(action_data)
        else:
            raise ValueError("action_data must be a JSON string")
        self.action_done = action_done
        self.action_build_into_prompt = action_build_into_prompt
        self.action_prompt_display = action_prompt_display
        self.chat_id = chat_id
        self.chat_info_stream_id = chat_info_stream_id
        self.chat_info_platform = chat_info_platform
