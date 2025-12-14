"""请求事件处理器 - 处理 Napcat OneBot 的 request 事件

支持：
- 好友请求（request_type=friend）
- 群请求（request_type=group，sub_type=invite/add）

职责：
- 仅进行 OneBot → MessageEnvelope 封装，并附加 request 详情到 additional_config
- 审批与通知由插件系统（如 auto_accept_requests）通过 ON_NOTICE_RECEIVED 执行
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import time
from mofox_wire import MessageBuilder

from src.common.logger import get_logger
from ...event_models import ACCEPT_FORMAT

if TYPE_CHECKING:
    from ....plugin import NapcatAdapter


logger = get_logger("napcat_adapter")


class RequestHandler:
    """处理 Napcat 的 request 事件"""

    def __init__(self, adapter: "NapcatAdapter"):
        self.adapter = adapter
        self.plugin_config: dict[str, Any] | None = None

    def set_plugin_config(self, config: dict[str, Any]) -> None:
        """设置插件配置"""
        self.plugin_config = config

    async def handle_request(self, raw: dict[str, Any]) -> dict | None:
        """处理 request 事件并返回 MessageEnvelope

        事件示例（OneBot 11/Napcat）：
        {
            "post_type": "request",
            "request_type": "group" | "friend",
            "sub_type": "invite" | "add",
            "group_id": 111,
            "user_id": 1111,
            "comment": "",
            "flag": "111213",
            "self_id": 123,
            "time": 23123
        }
        """

        request_type = raw.get("request_type")
        sub_type = str(raw.get("sub_type", ""))
        user_id = str(raw.get("user_id", ""))
        group_id = raw.get("group_id")
        flag = raw.get("flag")
        comment = raw.get("comment", "")

        # 使用平台事件时间，如果不可用则回退到当前时间
        raw_time = raw.get("time")
        event_ts_seconds: float | None
        try:
            if raw_time is None:
                event_ts_seconds = None
            else:
                # OneBot 平台一般使用秒时间戳，这里统一转换为 float
                event_ts_seconds = float(raw_time)
        except (TypeError, ValueError):
            event_ts_seconds = None

        if event_ts_seconds is None or event_ts_seconds <= 0:
            # 无效或缺失时回退到当前时间
            event_ts_seconds = time.time()

        timestamp_ms = int(event_ts_seconds * 1000)

        if not request_type:
            logger.warning("缺少 request_type，跳过处理")
            return None

        # 适配器层不再自动同意，由插件 auto_accept_requests 统一处理

        # 构造 MessageEnvelope，作为 Notice 类型进入核心流程
        mb = MessageBuilder()

        (
            mb.direction("incoming")
            .message_id(str(flag or f"request:{timestamp_ms}"))
            .timestamp_ms(timestamp_ms)
            .from_user(user_id=user_id, platform="qq")
        )

        # 群信息（仅群请求）
        if request_type == "group" and group_id:
            mb.from_group(group_id=str(group_id), platform="qq")

        # 片段占位，统一为文本提示
        if request_type == "group":
            text = f"收到群邀请请求，来自 {user_id}，群 {group_id}"
            content_format = ["text", "notify"]
        else:
            text = f"收到好友添加请求，来自 {user_id}"
            content_format = ["text", "notify"]

        mb.format_info(content_format=content_format, accept_format=ACCEPT_FORMAT)
        mb.seg_list([{"type": "text", "data": text}])

        envelope = mb.build()

        # 附加配置，标记为 notice，供 MessageRuntime 的 notice 路由处理
        notice_type = "group_invite" if request_type == "group" else "friend_request"
        envelope.setdefault("message_info", {})
        envelope["message_info"].setdefault("additional_config", {})
        envelope["message_info"]["additional_config"].update(
            {
                "is_notice": True,
                "is_public_notice": False,
                "notice_type": notice_type,
                "request_detail": {
                    "request_type": request_type,
                    "sub_type": sub_type,
                    "user_id": user_id,
                    "group_id": group_id,
                    "flag": flag,
                    "comment": comment,
                },
            }
        )

        return envelope
