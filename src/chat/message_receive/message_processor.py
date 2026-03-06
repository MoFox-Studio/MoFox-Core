"""消息处理工具模块
将原 MessageRecv 的消息处理逻辑提取为独立函数，
基于 mofox-wire 的 TypedDict 形式构建消息数据，然后转换为 DatabaseMessages
"""
import base64
import re
import time
from typing import Any

import orjson
from mofox_wire import MessageEnvelope
from mofox_wire.types import GroupInfoPayload, MessageInfoPayload, SegPayload, UserInfoPayload

from src.chat.utils.self_voice_cache import consume_self_voice_text
from src.chat.utils.utils_image import get_image_manager
from src.chat.utils.utils_video import get_video_analyzer, is_video_analysis_available
from src.chat.utils.utils_voice import get_voice_text
from src.common.data_models.database_data_model import DatabaseMessages
from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("message_processor")

# 预编译正则表达式
_AT_PATTERN = re.compile(r"^([^:]+):(.+)$")

# 常量定义：段类型集合
RECURSIVE_SEGMENT_TYPES = frozenset(["seglist"])
MEDIA_SEGMENT_TYPES = frozenset(["image", "emoji", "voice", "video"])
METADATA_SEGMENT_TYPES = frozenset(["mention_bot", "priority_info"])
SPECIAL_SEGMENT_TYPES = frozenset(["at", "reply", "file"])


async def process_message_from_dict(
    message_dict: MessageEnvelope,
    stream_id: str,
    platform: str,
    skip_media_processing: bool = False
) -> DatabaseMessages:
    """从适配器消息字典处理并生成 DatabaseMessages

    这个函数整合了原 MessageRecv 的所有处理逻辑：
    1. 解析 message_segment 并异步处理内容（图片、语音、视频等）
    2. 提取所有消息元数据
    3. 基于 TypedDict 形式构建数据，然后转换为 DatabaseMessages

    Args:
        message_dict: MessageEnvelope 格式的消息字典
        stream_id: 聊天流ID
        platform: platform 标识
        skip_media_processing: 是否跳过昂贵的媒体处理（如识图、语音转文字）

    Returns:
        DatabaseMessages: 处理完成的数据库消息对象
    """
    # 提取核心数据（使用 TypedDict 类型）
    message_info: MessageInfoPayload = message_dict.get("message_info", {})  # type: ignore
    message_segment: SegPayload | list[SegPayload] = message_dict.get("message_segment", {"type": "text", "data": ""})  # type: ignore

    # 初始化处理状态
    processing_state = {
        "is_emoji": False,
        "has_emoji": False,
        "is_picid": False,
        "has_picid": False,
        "is_voice": False,
        "is_video": False,
        "is_mentioned": None,
        "is_at": False,
        "priority_mode": "interest",
        "priority_info": None,
    }

    # 异步处理消息段，生成纯文本
    processed_plain_text = await _process_message_segments(
        message_segment,
        processing_state,
        message_info,
        skip_media_processing=skip_media_processing
    )

    # 解析 notice 信息
    is_notify = False
    is_public_notice = False
    notice_type = None
    additional_config_dict = message_info.get("additional_config", {})
    if isinstance(additional_config_dict, dict):
        is_notify = additional_config_dict.get("is_notice", False)
        is_public_notice = additional_config_dict.get("is_public_notice", False)
        notice_type = additional_config_dict.get("notice_type")

    # 提取用户信息
    user_info_payload: UserInfoPayload = message_info.get("user_info", {})  # type: ignore
    user_id = str(user_info_payload.get("user_id", ""))
    user_nickname = user_info_payload.get("user_nickname", "")
    user_cardname = user_info_payload.get("user_cardname")
    user_platform = user_info_payload.get("platform", "")
    user_role = user_info_payload.get("role")  # Extract role

    # 提取群组信息
    group_info_payload: GroupInfoPayload | None = message_info.get("group_info")  # type: ignore
    group_id = group_info_payload.get("group_id") if group_info_payload else None
    group_name = group_info_payload.get("group_name") if group_info_payload else None
    group_platform = group_info_payload.get("platform") if group_info_payload else None

    # chat_id 应该直接使用 stream_id（与数据库存储格式一致）
    chat_id = stream_id

    # 准备 additional_config
    additional_config_str = _prepare_additional_config(message_info, is_notify, is_public_notice, notice_type)

    # 提取 reply_to
    reply_to = _extract_reply_from_segment(message_segment)

    # 构造消息数据字典（基于 TypedDict 风格）
    message_time = message_info.get("time", time.time())
    if isinstance(message_time,int):
        message_time = float(message_time / 1000)
    message_id = message_info.get("message_id", "")

    # 处理 is_mentioned
    is_mentioned = None
    mentioned_value = processing_state.get("is_mentioned")
    if isinstance(mentioned_value, bool):
        is_mentioned = mentioned_value
    elif isinstance(mentioned_value, int | float):
        is_mentioned = mentioned_value != 0

    # 使用 TypedDict 风格的数据构建 DatabaseMessages
    db_message = DatabaseMessages(
        message_id=message_id,
        time=float(message_time),
        chat_id=chat_id,
        reply_to=reply_to,
        processed_plain_text=processed_plain_text,
        display_message=processed_plain_text,
        is_mentioned=is_mentioned,
        is_at=bool(processing_state.get("is_at", False)),
        is_emoji=bool(processing_state.get("is_emoji", False)),
        is_picid=bool(processing_state.get("is_picid", False)),
        is_command=False,  # 将在后续处理中设置
        is_notify=bool(is_notify),
        is_public_notice=bool(is_public_notice),
        notice_type=notice_type,
        additional_config=additional_config_str,
        user_id=user_id,
        user_nickname=user_nickname,
        user_cardname=user_cardname,
        user_platform=user_platform,
        user_role=user_role,
        chat_info_stream_id=stream_id,
        chat_info_platform=platform,
        chat_info_create_time=0.0,  # 将由 ChatStream 填充
        chat_info_last_active_time=0.0,  # 将由 ChatStream 填充
        chat_info_user_id=user_id,
        chat_info_user_nickname=user_nickname,
        chat_info_user_cardname=user_cardname,
        chat_info_user_platform=user_platform,
        chat_info_group_id=group_id,
        chat_info_group_name=group_name,
        chat_info_group_platform=group_platform,
    )

    # 设置优先级信息（运行时属性）
    if processing_state.get("priority_mode"):
        setattr(db_message, "priority_mode", processing_state["priority_mode"])
    if processing_state.get("priority_info"):
        setattr(db_message, "priority_info", processing_state["priority_info"])

    # 设置其他运行时属性
    setattr(db_message, "is_voice", bool(processing_state.get("is_voice", False)))
    setattr(db_message, "is_video", bool(processing_state.get("is_video", False)))
    setattr(db_message, "has_emoji", bool(processing_state.get("has_emoji", False)))
    setattr(db_message, "has_picid", bool(processing_state.get("has_picid", False)))

    return db_message


async def _process_message_segments(
    segment: SegPayload | list[SegPayload],
    state: dict,
    message_info: MessageInfoPayload,
    skip_media_processing: bool = False
) -> str:
    """递归处理消息段，转换为文字描述

    Args:
        segment: 要处理的消息段（TypedDict 或列表）
        state: 处理状态字典（用于记录消息类型标记）
        message_info: 消息基础信息（TypedDict 格式）
        skip_media_processing: 是否跳过昂贵的媒体处理

    Returns:
        str: 处理后的文本
    """
    # 如果是列表，遍历处理
    if isinstance(segment, list):
        segments_text = []
        for seg in segment:
            processed = await _process_message_segments(seg, state, message_info, skip_media_processing)
            if processed:
                segments_text.append(processed)
        return " ".join(segments_text)

    # 如果是单个段
    if isinstance(segment, dict):
        seg_type = segment.get("type", "")
        seg_data = segment.get("data")

        # 处理 seglist 类型
        if seg_type == "seglist" and isinstance(seg_data, list):
            segments_text = []
            for sub_seg in seg_data:
                processed = await _process_message_segments(sub_seg, state, message_info, skip_media_processing)
                if processed:
                    segments_text.append(processed)
            return " ".join(segments_text)

        # 处理其他类型
        return await _process_single_segment(segment, state, message_info, skip_media_processing)

    return ""


async def _process_single_segment(
    segment: SegPayload,
    state: dict,
    message_info: MessageInfoPayload,
    skip_media_processing: bool = False
) -> str:
    """处理单个消息段

    Args:
        segment: 消息段（TypedDict 格式）
        state: 处理状态字典
        message_info: 消息基础信息（TypedDict 格式）
        skip_media_processing: 是否跳过昂贵的媒体处理

    Returns:
        str: 处理后的文本
    """
    seg_type = segment.get("type", "")
    seg_data = segment.get("data")

    try:
        if seg_type == "text":
            return str(seg_data) if seg_data else ""

        elif seg_type == "at":
            state["is_at"] = True
            # 处理at消息，格式为"@<昵称:QQ号>"
            if isinstance(seg_data, str):
                match = _AT_PATTERN.match(seg_data)
                if match:
                    nickname, qq_id = match.groups()
                    return f"@<{nickname}:{qq_id}>"
                logger.warning(f"[at处理] 无法解析格式: '{seg_data}'")
                return f"@{seg_data}"
            logger.warning(f"[at处理] 数据类型异常: {type(seg_data)}")
            return f"@{seg_data}" if isinstance(seg_data, str) else "@未知用户"

        elif seg_type == "image":
            # 如果是base64图片数据
            if isinstance(seg_data, str):
                state["has_picid"] = True
                state["is_picid"] = True
                if skip_media_processing:
                    logger.debug("[message_processor] 静默模式，跳过图片识别")
                    return "[图片]"
                image_manager = get_image_manager()
                _, processed_text = await image_manager.process_image(seg_data)
                return processed_text
            return "[发了一张图片，网卡了加载不出来]"

        elif seg_type == "emoji":
            state["has_emoji"] = True
            state["is_emoji"] = True
            if isinstance(seg_data, str):
                if skip_media_processing:
                    logger.debug("[message_processor] 静默模式，跳过表情包识别")
                    return "[表情包]"
                return await get_image_manager().get_emoji_description(seg_data)
            return "[发了一个表情包，网卡了加载不出来]"

        elif seg_type == "voice":
            state["is_voice"] = True
            if skip_media_processing:
                return "[语音]"

            # 检查消息是否由机器人自己发送
            user_info = message_info.get("user_info", {})
            user_id_str = str(user_info.get("user_id", ""))
            if global_config and user_id_str == str(global_config.bot.qq_account):
                logger.info(f"检测到机器人自身发送的语音消息 (User ID: {user_id_str})，尝试从缓存获取文本。")
                if isinstance(seg_data, str):
                    cached_text = consume_self_voice_text(seg_data)
                    if cached_text:
                        logger.info(f"成功从缓存中获取语音文本: '{cached_text[:70]}...'")
                        return f"[语音：{cached_text}]"
                    else:
                        logger.warning("机器人自身语音消息缓存未命中，将回退到标准语音识别。")

            # 标准语音识别流程
            if isinstance(seg_data, str):
                return await get_voice_text(seg_data)
            return "[发了一段语音，网卡了加载不出来]"

        elif seg_type == "mention_bot":
            if isinstance(seg_data, int | float):
                state["is_mentioned"] = float(seg_data)
            return ""

        elif seg_type == "priority_info":
            if isinstance(seg_data, dict):
                # 处理优先级信息
                state["priority_mode"] = "priority"
                state["priority_info"] = seg_data
            return ""

        elif seg_type == "file":
            if isinstance(seg_data, dict):
                file_name = seg_data.get("name", "未知文件")
                file_size = seg_data.get("size", "未知大小")
                return f"[文件：{file_name} ({file_size}字节)]"
            return "[收到一个文件]"

        elif seg_type == "video":
            state["is_video"] = True
            if skip_media_processing:
                return "[视频]"
            logger.info(f"接收到视频消息，数据类型: {type(seg_data)}")

            # 检查视频分析功能是否可用
            if not is_video_analysis_available():
                logger.warning("⚠️ Rust视频处理模块不可用，跳过视频分析")
                return "[视频]"

            if global_config and global_config.video_analysis.enable:
                logger.info("已启用视频识别,开始识别")
                if isinstance(seg_data, dict):
                    try:
                        # 从Adapter接收的视频数据
                        video_base64 = seg_data.get("base64")
                        filename = seg_data.get("filename", "video.mp4")

                        logger.info(f"视频文件名: {filename}")

                        if video_base64:
                            # 解码base64视频数据
                            video_bytes = base64.b64decode(video_base64)
                            logger.info(f"解码后视频大小: {len(video_bytes)} 字节")

                            # 使用video analyzer分析视频
                            video_analyzer = get_video_analyzer()
                            result = await video_analyzer.analyze_video_from_bytes(
                                video_bytes, filename, prompt=global_config.video_analysis.batch_analysis_prompt
                            )

                            logger.info(f"视频分析结果: {result}")

                            # 返回视频分析结果
                            summary = result.get("summary", "")
                            if summary:
                                return f"[视频内容] {summary}"
                            else:
                                return "[已收到视频，但分析失败]"
                        else:
                            logger.warning("视频消息中没有base64数据")
                            return "[收到视频消息，但数据异常]"
                    except Exception as e:
                        logger.error(f"视频处理失败: {e!s}")
                        import traceback
                        logger.error(f"错误详情: {traceback.format_exc()}")
                        return "[收到视频，但处理时出现错误]"
                else:
                    logger.warning(f"视频消息数据不是字典格式: {type(seg_data)}")
                return "[发了一个视频，但格式不支持]"
            else:
                return ""
        elif seg_type == "music":
            # 处理音乐分享卡片
            try:
                if isinstance(seg_data, dict):
                    # 尝试优先获取标题，其次是ID
                    title = seg_data.get("title")
                    music_id = seg_data.get("id")

                    if title:
                        return f"[分享音乐: {title}]"
                    elif music_id:
                        return f"[分享音乐, ID: {music_id}]"
                    else:
                        # 如果没有标准字段，尝试转储数据内容以便调试或作为后备
                        return f"[分享音乐, 数据: {seg_data}]"

                elif isinstance(seg_data, str):
                     return f"[分享音乐, ID: {seg_data}]"
            except Exception:
                pass
            return f"[分享音乐, 原始数据: {seg_data!s}]"

        else:
            logger.warning(f"未知的消息段类型: {seg_type}")
            return f"[{seg_type} 消息]"

    except Exception as e:
        logger.error(f"处理消息段失败: {e!s}, 类型: {seg_type}, 数据: {seg_data}")
        return f"[处理失败的{seg_type}消息]"


def _prepare_additional_config(
    message_info: MessageInfoPayload,
    is_notify: bool,
    is_public_notice: bool,
    notice_type: str | None
) -> str | None:
    """准备 additional_config，包含 format_info 和 notice 信息

    Args:
        message_info: 消息基础信息（TypedDict 格式）
        is_notify: 是否为notice消息
        is_public_notice: 是否为公共notice
        notice_type: notice类型

    Returns:
        str | None: JSON 字符串格式的 additional_config，如果为空则返回 None
    """
    try:
        # 首先获取adapter传递的additional_config
        additional_config_raw = message_info.get("additional_config")
        if isinstance(additional_config_raw, dict):
            additional_config_data = additional_config_raw.copy()
        elif isinstance(additional_config_raw, str):
            try:
                additional_config_data = orjson.loads(additional_config_raw)
            except Exception as e:
                logger.warning(f"无法解析 additional_config JSON: {e}")
                additional_config_data = {}
        else:
            additional_config_data = {}

        # 添加notice相关标志
        if is_notify:
            additional_config_data["is_notice"] = True
            additional_config_data["notice_type"] = notice_type or "unknown"
            additional_config_data["is_public_notice"] = bool(is_public_notice)

        # 添加format_info到additional_config中
        format_info = message_info.get("format_info")
        if format_info:
            try:
                additional_config_data["format_info"] = format_info
                logger.debug(f"[message_processor] 嵌入 format_info 到 additional_config: {format_info}")
            except Exception as e:
                logger.warning(f"将 format_info 转换为字典失败: {e}")

        # 序列化为JSON字符串
        if additional_config_data:
            return orjson.dumps(additional_config_data).decode("utf-8")
    except Exception as e:
        logger.error(f"准备 additional_config 失败: {e}")

    return None


def _extract_reply_from_segment(segment: SegPayload | list[SegPayload]) -> str | None:
    """从消息段中提取reply_to信息

    Args:
        segment: 消息段（TypedDict 格式或列表）

    Returns:
        str | None: 回复的消息ID，如果没有则返回None
    """
    try:
        # 如果是列表，遍历查找
        if isinstance(segment, list):
            for seg in segment:
                reply_id = _extract_reply_from_segment(seg)
                if reply_id:
                    return reply_id
            return None

        # 如果是字典
        if isinstance(segment, dict):
            seg_type = segment.get("type", "")
            seg_data = segment.get("data")

            # 如果是 seglist，递归搜索
            if seg_type == "seglist" and isinstance(seg_data, list):
                for sub_seg in seg_data:
                    reply_id = _extract_reply_from_segment(sub_seg)
                    if reply_id:
                        return reply_id

            # 如果是 reply 段，返回 message_id
            elif seg_type == "reply":
                return str(seg_data) if seg_data else None

    except Exception as e:
        logger.warning(f"提取reply_to信息失败: {e}")

    return None


# =============================================================================
# DatabaseMessages 扩展工具函数
# =============================================================================

def get_message_info_from_db_message(db_message: DatabaseMessages) -> MessageInfoPayload:
    """从 DatabaseMessages 重建 MessageInfoPayload（TypedDict 格式）

    Args:
        db_message: DatabaseMessages 对象

    Returns:
        MessageInfoPayload: 重建的消息信息对象（TypedDict 格式）
    """
    # 构建用户信息
    user_info: UserInfoPayload = {
        "platform": db_message.user_info.platform,
        "user_id": db_message.user_info.user_id,
        "user_nickname": db_message.user_info.user_nickname,
        "user_cardname": db_message.user_info.user_cardname or "",
    }

    # 构建群组信息（如果存在）
    group_info: GroupInfoPayload | None = None
    if db_message.group_info:
        group_info = {
            "platform": db_message.group_info.platform or "",
            "group_id": db_message.group_info.group_id,
            "group_name": db_message.group_info.group_name,
        }

    # 解析 additional_config（从 JSON 字符串到字典）
    additional_config = None
    if db_message.additional_config:
        try:
            additional_config = orjson.loads(db_message.additional_config)
        except Exception:
            # 如果解析失败，保持为字符串
            pass

    # 创建 MessageInfoPayload
    message_info: MessageInfoPayload = {
        "platform": db_message.chat_info.platform,
        "message_id": db_message.message_id,
        "time": db_message.time,
        "user_info": user_info,
    }

    if group_info:
        message_info["group_info"] = group_info

    if additional_config:
        message_info["additional_config"] = additional_config

    return message_info


def set_db_message_runtime_attr(db_message: DatabaseMessages, attr_name: str, value: Any) -> None:
    """安全地为 DatabaseMessages 设置运行时属性

    Args:
        db_message: DatabaseMessages 对象
        attr_name: 属性名
        value: 属性值
    """
    setattr(db_message, attr_name, value)


def get_db_message_runtime_attr(db_message: DatabaseMessages, attr_name: str, default: Any = None) -> Any:
    """安全地获取 DatabaseMessages 的运行时属性

    Args:
        db_message: DatabaseMessages 对象
        attr_name: 属性名
        default: 默认值

    Returns:
        属性值或默认值
    """
    return getattr(db_message, attr_name, default)
