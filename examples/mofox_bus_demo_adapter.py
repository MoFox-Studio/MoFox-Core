"""
示例：演示一个最小可用的 WebSocket 适配器如何使用 BaseAdapter 的自动传输封装：
1) 通过 WS 接入平台；
2) 将平台推送的消息转成 MessageEnvelope 并交给核心；
3) 接收核心回复并通过 WS 再发回平台。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import orjson
import websockets
from mofox_wire import (
    AdapterBase,
    InProcessCoreSink,
    MessageEnvelope,
    MessageRuntime,
    WebSocketAdapterOptions,
)

# ---------------------------------------------------------------------------
# 1. 模拟一个提供 WebSocket 接口的平台
# ---------------------------------------------------------------------------


class FakePlatformServer:
    """
    适配器将通过 WS 连接到这个模拟平台。
    平台会广播消息给所有连接，适配器发送的响应也会被打印出来。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 19898) -> None:
        self._host = host
        self._port = port
        self._connections: set[Any] = set()
        self._server = None

    @property
    def url(self) -> str:
        return f"ws://{self._host}:{self._port}"

    async def start(self) -> None:
        self._server = await websockets.serve(self._handler, self._host, self._port)
        print(f"[Platform] WebSocket server listening on {self.url}")

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handler(self, ws) -> None:
        self._connections.add(ws)
        print("[Platform] adapter connected")
        try:
            async for raw in ws:
                data = orjson.loads(raw)
                if data["type"] == "send":
                    print(f"[Platform] <- Bot: {data['payload']['text']}")
        finally:
            self._connections.discard(ws)
            print("[Platform] adapter disconnected")

    async def simulate_incoming_message(self, text: str) -> None:
        payload = {
            "message_id": str(uuid.uuid4()),
            "channel_id": "room-42",
            "user_id": "demo-user",
            "text": text,
            "timestamp": time.time(),
        }
        message = orjson.dumps({"type": "message", "payload": payload}).decode()
        for ws in list(self._connections):
            await ws.send(message)


# ---------------------------------------------------------------------------
# 2. 适配器实现：仅关注核心转换逻辑，网络层交由 AdapterBase 管理
# ---------------------------------------------------------------------------


class DemoWsAdapter(AdapterBase):   # 继承AdapterBase
    platform = "demo"   # 定义平台名称

    # 实现 from_platform_message 方法，将平台消息转换为 MessageEnvelope
    # 该方法必须被实现以便 AdapterBase 正确处理消息转换
    # 该方法会在adapter接收到平台消息后被调用
    def from_platform_message(self, raw: dict[str, Any]) -> MessageEnvelope:
        return {
            "id": raw["message_id"],
            "direction": "incoming",
            "platform": self.platform,
            "timestamp_ms": int(raw["timestamp"] * 1000),
            "channel": {"channel_id": raw["channel_id"], "channel_type": "room"},
            "sender": {"user_id": raw["user_id"], "role": "user"},
            "conversation_id": raw["channel_id"],
            "content": {"type": "text", "text": raw["text"]},
        } # type: ignore

def incoming_parser(raw: str | bytes) -> Any:
    data = orjson.loads(raw)
    if data.get("type") == "message":
        return data["payload"]
    return data


def outgoing_encoder(envelope: MessageEnvelope) -> str:
    return orjson.dumps(
        {
            "type": "send",
            "payload": {
                "channel_id": envelope["channel"]["channel_id"],
                "text": envelope["content"]["text"],
            },
        }
    ).decode()


# ---------------------------------------------------------------------------
# 3. 核心 Runtime：注册处理器并通过 InProcessCoreSink 接收消息
# ---------------------------------------------------------------------------

runtime = MessageRuntime()


@runtime.route(lambda env: env["direction"] == "incoming")
async def handle_incoming(env: MessageEnvelope) -> MessageEnvelope:
    user_text = env["content"]["text"]
    reply_text = f"核心收到：{user_text}"
    return {
        "id": str(uuid.uuid4()),
        "direction": "outgoing",
        "platform": env["platform"],
        "timestamp_ms": int(time.time() * 1000),
        "channel": env["channel"],
        "sender": {
            "user_id": "bot",
            "role": "assistant",
            "display_name": "DemoBot",
        },
        "conversation_id": env["conversation_id"],
        "content": {"type": "text", "text": reply_text},
    }


adapter: DemoWsAdapter | None = None


async def core_entry(message: MessageEnvelope) -> None:
    response = await runtime.handle_message(message)
    if response and adapter is not None:
        await adapter.send_to_platform(response)


core_sink = InProcessCoreSink(core_entry)


# ---------------------------------------------------------------------------
# 4. 串起来并运行 Demo
# ---------------------------------------------------------------------------

async def main() -> None:
    platform = FakePlatformServer()
    await platform.start()

    global adapter
    adapter = DemoWsAdapter(
        core_sink,
        transport=WebSocketAdapterOptions(
            url=platform.url,
            incoming_parser=incoming_parser,
            outgoing_encoder=outgoing_encoder,
        ),
    )
    await adapter.start()

    await asyncio.sleep(0.1)
    await platform.simulate_incoming_message("你好，MoFox Bus！")
    await platform.simulate_incoming_message("请问你是谁？")

    await asyncio.sleep(0.5)
    await adapter.stop()
    await platform.stop()


if __name__ == "__main__":
    asyncio.run(main())
