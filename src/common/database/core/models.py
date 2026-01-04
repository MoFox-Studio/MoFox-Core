"""SQLAlchemy数据库模型定义

本文件只包含纯模型定义，使用SQLAlchemy 2.0的Mapped类型注解风格。
引擎和会话管理已移至core/engine.py和core/session.py。

支持的数据库类型：
- SQLite: 使用 Text 类型
- PostgreSQL: 使用 Text 类型（PostgreSQL 的 Text 类型性能与 VARCHAR 相当）

所有模型使用统一的类型注解风格：
    field_name: Mapped[PyType] = mapped_column(Type, ...)

这样IDE/Pylance能正确推断实例属性类型。
"""

import datetime
import time

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column

# 创建基类
Base = declarative_base()


# 数据库兼容的字段类型辅助函数
def get_string_field(max_length=255, **kwargs):
    """
    根据数据库类型返回合适的字符串字段类型

    对于需要索引的字段：
    - PostgreSQL: 可以使用 Text，但为了兼容性使用 VARCHAR
    - SQLite: 可以使用 Text，无长度限制

    Args:
        max_length: 最大长度
        **kwargs: 传递给 String/Text 的额外参数

    Returns:
        SQLAlchemy 类型
    """
    from src.config.config import global_config

    assert global_config is not None
    db_type = global_config.database.database_type

    # PostgreSQL 可以使用 Text，但为了跨数据库迁移兼容性，使用 VARCHAR
    if db_type == "postgresql":
        return String(max_length, **kwargs)
    # SQLite 使用 Text（无长度限制）
    else:
        return Text(**kwargs)


class ChatStreams(Base):
    """聊天流模型"""

    __tablename__ = "chat_streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[str] = mapped_column(get_string_field(64), nullable=False, unique=True, index=True)
    create_time: Mapped[float] = mapped_column(Float, nullable=False)
    group_platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_id: Mapped[str | None] = mapped_column(get_string_field(100), nullable=True, index=True)
    group_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_active_time: Mapped[float] = mapped_column(Float, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    user_platform: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    user_nickname: Mapped[str] = mapped_column(Text, nullable=False)
    user_cardname: Mapped[str | None] = mapped_column(Text, nullable=True)
    energy_value: Mapped[float | None] = mapped_column(Float, nullable=True, default=5.0)
    sleep_pressure: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    focus_energy: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.5)
    # 动态兴趣度系统字段
    base_interest_energy: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.5)
    message_interest_total: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    message_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    action_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    reply_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    last_interaction_time: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    consecutive_no_reply: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    # 消息打断系统字段
    interruption_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    # 聊天流印象字段
    stream_impression_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 对聊天流的主观印象描述
    stream_chat_style: Mapped[str | None] = mapped_column(Text, nullable=True)  # 聊天流的总体风格
    stream_topic_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)  # 话题关键词，逗号分隔
    stream_interest_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.5)  # 对聊天流的兴趣程度(0-1)

    __table_args__ = (
        Index("idx_chatstreams_stream_id", "stream_id"),
        Index("idx_chatstreams_user_id", "user_id"),
        Index("idx_chatstreams_group_id", "group_id"),
    )


class LLMUsage(Base):
    """LLM使用记录模型"""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    model_assign_name: Mapped[str] = mapped_column(get_string_field(100), index=True)
    model_api_provider: Mapped[str] = mapped_column(get_string_field(100), index=True)
    user_id: Mapped[str] = mapped_column(get_string_field(50), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(get_string_field(50), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    time_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True, default=datetime.datetime.now)

    __table_args__ = (
        Index("idx_llmusage_model_name", "model_name"),
        Index("idx_llmusage_model_assign_name", "model_assign_name"),
        Index("idx_llmusage_model_api_provider", "model_api_provider"),
        Index("idx_llmusage_time_cost", "time_cost"),
        Index("idx_llmusage_user_id", "user_id"),
        Index("idx_llmusage_request_type", "request_type"),
        Index("idx_llmusage_timestamp", "timestamp"),
    )


class Emoji(Base):
    """表情包模型"""

    __tablename__ = "emoji"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_path: Mapped[str] = mapped_column(get_string_field(500), nullable=False, unique=True, index=True)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    emoji_hash: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emotion: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_time: Mapped[float] = mapped_column(Float, nullable=False)
    register_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_time: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("idx_emoji_full_path", "full_path"),
        Index("idx_emoji_hash", "emoji_hash"),
    )


class Messages(Base):
    """消息模型"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    time: Mapped[float] = mapped_column(Float, nullable=False)
    chat_id: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    reply_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    key_words: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_words_lite: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mentioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # 从 chat_info 扁平化而来的字段
    chat_info_stream_id: Mapped[str] = mapped_column(Text, nullable=False)
    chat_info_platform: Mapped[str] = mapped_column(Text, nullable=False)
    chat_info_user_platform: Mapped[str] = mapped_column(Text, nullable=False)
    chat_info_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    chat_info_user_nickname: Mapped[str] = mapped_column(Text, nullable=False)
    chat_info_user_cardname: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_info_group_platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_info_group_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_info_group_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_info_create_time: Mapped[float] = mapped_column(Float, nullable=False)
    chat_info_last_active_time: Mapped[float] = mapped_column(Float, nullable=False)

    # 从顶层 user_info 扁平化而来的字段
    user_platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(get_string_field(100), nullable=True, index=True)
    user_nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_cardname: Mapped[str | None] = mapped_column(Text, nullable=True)

    processed_plain_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    memorized_times: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_emoji: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_picid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_command: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_public_notice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notice_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 兴趣度系统字段
    actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    should_reply: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    should_act: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)

    __table_args__ = (
        Index("idx_messages_message_id", "message_id"),
        Index("idx_messages_chat_id", "chat_id"),
        Index("idx_messages_time", "time"),
        Index("idx_messages_user_id", "user_id"),
        Index("idx_messages_should_reply", "should_reply"),
        Index("idx_messages_should_act", "should_act"),
    )


class ActionRecords(Base):
    """动作记录模型"""

    __tablename__ = "action_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    time: Mapped[float] = mapped_column(Float, nullable=False)
    action_name: Mapped[str] = mapped_column(Text, nullable=False)
    action_data: Mapped[str] = mapped_column(Text, nullable=False)
    action_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action_build_into_prompt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action_prompt_display: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    chat_info_stream_id: Mapped[str] = mapped_column(Text, nullable=False)
    chat_info_platform: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_actionrecords_action_id", "action_id"),
        Index("idx_actionrecords_chat_id", "chat_id"),
        Index("idx_actionrecords_time", "time"),
    )


class Images(Base):
    """图像信息模型"""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    emoji_hash: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(get_string_field(500), nullable=False, unique=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    vlm_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_images_emoji_hash", "emoji_hash"),
        Index("idx_images_path", "path"),
    )


class ImageDescriptions(Base):
    """图像描述信息模型"""

    __tablename__ = "image_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    image_description_hash: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("idx_imagedesc_hash", "image_description_hash"),)


class Videos(Base):
    """视频信息模型"""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    video_hash: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    vlm_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 视频特有属性
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_videos_video_hash", "video_hash"),
        Index("idx_videos_timestamp", "timestamp"),
    )


class OnlineTime(Base):
    """在线时长记录模型"""

    __tablename__ = "online_time"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False, default=str(datetime.datetime.now))
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    start_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    end_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True)

    __table_args__ = (Index("idx_onlinetime_end_timestamp", "end_timestamp"),)


class PersonInfo(Base):
    """人物信息模型"""

    __tablename__ = "person_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(get_string_field(100), nullable=False, unique=True, index=True)
    person_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str] = mapped_column(get_string_field(50), nullable=False, index=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    impression: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_impression: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[str | None] = mapped_column(Text, nullable=True)
    forgotten_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_list: Mapped[str | None] = mapped_column(Text, nullable=True)
    know_times: Mapped[float | None] = mapped_column(Float, nullable=True)
    know_since: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_know: Mapped[float | None] = mapped_column(Float, nullable=True)
    attitude: Mapped[int | None] = mapped_column(Integer, nullable=True, default=50)

    __table_args__ = (
        Index("idx_personinfo_person_id", "person_id"),
        Index("idx_personinfo_user_id", "user_id"),
    )


class BotPersonalityInterests(Base):
    """机器人人格兴趣标签模型"""

    __tablename__ = "bot_personality_interests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    personality_id: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    personality_description: Mapped[str] = mapped_column(Text, nullable=False)
    interest_tags: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(get_string_field(100), nullable=False, default="text-embedding-ada-002")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now, index=True)

    __table_args__ = (
        Index("idx_botpersonality_personality_id", "personality_id"),
        Index("idx_botpersonality_version", "version"),
        Index("idx_botpersonality_last_updated", "last_updated"),
    )


class Memory(Base):
    """记忆模型"""

    __tablename__ = "memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    chat_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_view_time: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("idx_memory_memory_id", "memory_id"),)


class Expression(Base):
    """表达风格模型"""

    __tablename__ = "expression"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[float] = mapped_column(Float, nullable=False)
    last_active_time: Mapped[float] = mapped_column(Float, nullable=False)
    chat_id: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    create_date: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("idx_expression_chat_id", "chat_id"),)


class ThinkingLog(Base):
    """思考日志模型"""

    __tablename__ = "thinking_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(get_string_field(64), nullable=False, index=True)
    trigger_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_info_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_info_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timing_results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_history_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_history_in_thinking_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_history_after_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartflow_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)

    __table_args__ = (Index("idx_thinkinglog_chat_id", "chat_id"),)


class GraphNodes(Base):
    """记忆图节点模型"""

    __tablename__ = "graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concept: Mapped[str] = mapped_column(get_string_field(255), nullable=False, unique=True, index=True)
    memory_items: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_time: Mapped[float] = mapped_column(Float, nullable=False)
    last_modified: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("idx_graphnodes_concept", "concept"),)


class GraphEdges(Base):
    """记忆图边模型"""

    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(get_string_field(255), nullable=False, index=True)
    target: Mapped[str] = mapped_column(get_string_field(255), nullable=False, index=True)
    strength: Mapped[int] = mapped_column(Integer, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_time: Mapped[float] = mapped_column(Float, nullable=False)
    last_modified: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("idx_graphedges_source", "source"),
        Index("idx_graphedges_target", "target"),
    )


class Schedule(Base):
    """日程模型"""

    __tablename__ = "schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(get_string_field(10), nullable=False, unique=True, index=True)
    schedule_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    __table_args__ = (Index("idx_schedule_date", "date"),)


class MaiZoneScheduleStatus(Base):
    """麦麦空间日程处理状态模型"""

    __tablename__ = "maizone_schedule_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datetime_hour: Mapped[str] = mapped_column(get_string_field(13), nullable=False, unique=True, index=True)
    activity: Mapped[str] = mapped_column(Text, nullable=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    story_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    send_success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    __table_args__ = (
        Index("idx_maizone_datetime_hour", "datetime_hour"),
        Index("idx_maizone_is_processed", "is_processed"),
    )


class BanUser(Base):
    """被禁用用户模型

    使用 SQLAlchemy 2.0 类型标注写法，方便静态类型检查器识别实际字段类型，
    避免在业务代码中对属性赋值时报 `Column[...]` 不可赋值的告警。
    """

    __tablename__ = "ban_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(get_string_field(50), nullable=False)  # 使用有限长度，以便创建索引
    user_id: Mapped[str] = mapped_column(get_string_field(50), nullable=False, index=True)
    violation_num: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)

    __table_args__ = (
        Index("idx_violation_num", "violation_num"),
        Index("idx_banuser_user_id", "user_id"),
        Index("idx_banuser_platform", "platform"),
        Index("idx_banuser_platform_user_id", "platform", "user_id"),
    )


class AntiInjectionStats(Base):
    """反注入系统统计模型"""

    __tablename__ = "anti_injection_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """总处理消息数"""

    detected_injections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """检测到的注入攻击数"""

    blocked_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """被阻止的消息数"""

    shielded_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """被加盾的消息数"""

    processing_time_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    """总处理时间"""

    total_process_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    """累计总处理时间"""

    last_process_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    """最近一次处理时间"""

    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """错误计数"""

    start_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    """统计开始时间"""

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    """记录创建时间"""

    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    """记录更新时间"""

    __table_args__ = (
        Index("idx_anti_injection_stats_created_at", "created_at"),
        Index("idx_anti_injection_stats_updated_at", "updated_at"),
    )


class CacheEntries(Base):
    """工具缓存条目模型"""

    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(get_string_field(500), nullable=False, unique=True, index=True)
    """缓存键，包含工具名、参数和代码哈希"""

    cache_value: Mapped[str] = mapped_column(Text, nullable=False)
    """缓存的数据，JSON格式"""

    expires_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    """过期时间戳"""

    tool_name: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    """工具名称"""

    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: time.time())
    """创建时间戳"""

    last_accessed: Mapped[float] = mapped_column(Float, nullable=False, default=lambda: time.time())
    """最后访问时间戳"""

    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """访问次数"""

    __table_args__ = (
        Index("idx_cache_entries_key", "cache_key"),
        Index("idx_cache_entries_expires_at", "expires_at"),
        Index("idx_cache_entries_tool_name", "tool_name"),
        Index("idx_cache_entries_created_at", "created_at"),
    )


class MonthlyPlan(Base):
    """月度计划模型"""

    __tablename__ = "monthly_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    status: Mapped[str] = mapped_column(get_string_field(20), nullable=False, default="active", index=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (
        Index("idx_monthlyplan_target_month_status", "target_month", "status"),
        Index("idx_monthlyplan_last_used_date", "last_used_date"),
        Index("idx_monthlyplan_usage_count", "usage_count"),
    )


class PermissionNodes(Base):
    """权限节点模型"""

    __tablename__ = "permission_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_name: Mapped[str] = mapped_column(get_string_field(255), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    plugin_name: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    default_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_permission_plugin", "plugin_name"),
        Index("idx_permission_node", "node_name"),
    )


class UserPermissions(Base):
    """用户权限模型"""

    __tablename__ = "user_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(get_string_field(50), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(get_string_field(100), nullable=False, index=True)
    permission_node: Mapped[str] = mapped_column(get_string_field(255), nullable=False, index=True)
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    granted_by: Mapped[str | None] = mapped_column(get_string_field(100), nullable=True)

    __table_args__ = (
        Index("idx_user_platform_id", "platform", "user_id"),
        Index("idx_user_permission", "platform", "user_id", "permission_node"),
        Index("idx_permission_granted", "permission_node", "granted"),
    )


class UserRelationships(Base):
    """用户关系模型 - 存储用户与bot的关系数据

    核心字段：
    - relationship_text: 当前印象描述（用于兼容旧系统，逐步迁移到 impression_text）
    - impression_text: 长期印象（新字段，自然叙事风格）
    - preference_keywords: 用户偏好关键词
    - relationship_score: 好感度分数(0-1)
    - key_facts: 关键信息JSON（生日、职业、理想等）
    - relationship_stage: 关系阶段（stranger/acquaintance/friend/close_friend/bestie）
    """

    __tablename__ = "user_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(get_string_field(100), nullable=False, unique=True, index=True)
    user_name: Mapped[str | None] = mapped_column(get_string_field(100), nullable=True)
    # user_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)  # 用户别名，逗号分隔 (已废弃)

    # 印象相关（新旧兼容）
    relationship_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 旧字段，保持兼容
    impression_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 新字段：长期印象（自然叙事）

    # 用户信息
    preference_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)  # 用户偏好关键词，逗号分隔
    key_facts: Mapped[str | None] = mapped_column(Text, nullable=True)  # 关键信息JSON（生日、职业等）

    # 关系状态
    relationship_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)  # 好感度(0-1)
    relationship_stage: Mapped[str | None] = mapped_column(get_string_field(50), nullable=True, default="stranger")  # 关系阶段

    # 时间记录
    first_met_time: Mapped[float | None] = mapped_column(Float, nullable=True)  # 首次认识时间戳
    last_impression_update: Mapped[float | None] = mapped_column(Float, nullable=True)  # 上次更新印象时间
    last_updated: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_user_relationship_id", "user_id"),
        Index("idx_relationship_score", "relationship_score"),
        Index("idx_relationship_updated", "last_updated"),
        Index("idx_relationship_stage", "relationship_stage"),
    )
