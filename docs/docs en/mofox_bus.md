# MoFox Bus Message Library

MoFox Bus is MoFox Bot's in-house messaging layer that replaces the third-party `maim_message`. It abstracts communication between the core and platform adapters into extensible, hot-pluggable components. The library is fully async and built for throughput, covering message modeling, serialization, transport, runtime routing, and adapter utilities.

> It is now a standalone pip package. Install with `pip install -e ./packages/mofox-wire` from the project root.

---

## 1. Design Goals

- **Unified message model**: Consistent envelope/content so core logic ignores platform differences.
- **Zero-copy dict structures**: TypedDict + dataclass for JSON-friendly models.
- **High-performance transport**: Batch send/recv + orjson + WS/HTTP wrappers.
- **Adapter-friendly**: BaseAdapter, Sink, Router, and batching utilities.
- **Progressive extensibility**: Add gRPC/MQ later by dropping implementations under `transport/`.

---

## 2. Package Layout (`packages/mofox-wire/src/mofox_wire/`)

| Module | Responsibility |
| --- | --- |
| `types.py` | TypedDict models (MessageEnvelope, Content, Sender/ChannelInfo, etc.). |
| `message_models.py` | Dataclass `Seg` / `MessageBase`, compatible with legacy segments. |
| `codec.py` | High-performance JSON encode/decode, batch APIs, schema upgrade hook. |
| `runtime.py` | Routing/hooks/batch scheduler powering the core chain. |
| `adapter_utils.py` | BaseAdapter, CoreMessageSink, BatchDispatcher, and helpers. |
| `api.py` | WebSocket `MessageServer`/`MessageClient`, token support, FastAPI reuse. |
| `router.py` | Manage multi-platform clients, auto-reconnect, dynamic routing. |
| `transport/` | Lightweight HTTP/WS servers/clients, reusable elsewhere. |
| `__init__.py` | Re-export common symbols for consumers. |

---

## 3. Message Model

### 3.1 Envelope TypedDict (`types.py`)

- `MessageEnvelope`: Aligns with original maim_message; core fields `message_info` + `message_segment` (SegPayload), `direction`, `schema_version`. Keeps raw fields; adds `channel`, `sender`, `content`; marks v0 fields optional.
- `SegPayload` / `MessageInfoPayload` / `UserInfoPayload` / `GroupInfoPayload` / `FormatInfoPayload` / `TemplateInfoPayload`: TypedDict counterparts to maim_message dataclasses for direct JSON serialization.
- `Content` / `SenderInfo` / `ChannelInfo`: In-flight iteration; compatible with v0 content model.

### 3.2 Dataclass segments (`message_models.py`)

- `Seg`: One content segment; supports nested `seglist`.
- `UserInfo` / `GroupInfo` / `FormatInfo` / `TemplateInfo`: Preserve legacy fields and add commonly used ones like `user_avatar`.
- `BaseMessageInfo` + `MessageBase`: Let adapters keep the original MessageBase API while the core passes dataclasses in memory.

> **TypedDict vs dataclass?** TypedDict is better for transport/DI; dataclass MessageBase keeps segment behavior for adapter-side processing.
---

## 4. Serialization & Versions (`codec.py`)

- `dumps_message` / `loads_message`: Single `MessageEnvelope`, auto-filling `schema_version` (default 1).
- `dumps_messages` / `loads_messages`: Batch payload `{schema_version, items: [...]}` to cut HTTP/WS round trips.
- `_upgrade_schema_if_needed` hook reserved for v2/v3 compatibility.

Default uses `orjson`; falls back to stdlib `json` when missing.

---

## 5. Runtime Scheduling (`runtime.py`)

- `MessageRuntime`:
  - `add_route(predicate, handler)` and `@runtime.route(...)` decorator to register handlers.
  - `register_before_hook` / `register_after_hook` / `register_error_hook` for pre/post/trace handling.
  - `set_batch_handler` to process a batch at once (batch IO optimization).
- `MessageProcessingError` wraps handler exceptions for easier logging.

Runtime uses `RLock` to protect routes for concurrent access; `_maybe_await` handles sync/async handlers transparently.

---

## 6. Transport Layer (`transport/`)

### 6.1 HTTP
- `HttpMessageServer`: `aiohttp.web` listening on `POST /messages`; can return response batches.
- `HttpMessageClient`: Manages `aiohttp.ClientSession`; `send_messages(messages, expect_reply=True)` waits for replies when needed.

### 6.2 WebSocket
- `WsMessageServer`: Built on `aiohttp`, maintains connections, supports `broadcast`.
# MoFox Bus Message Library

MoFox Bus is MoFox Bot's in-house messaging layer that replaces the third-party `maim_message`. It abstracts communication between the core and platform adapters into extensible, hot-pluggable components. The library is fully async and built for throughput, covering message modeling, serialization, transport, runtime routing, and adapter utilities.

> It is now a standalone pip package. Install with `pip install -e ./packages/mofox-wire` from the project root.

---

## 1. Design Goals

- **Unified message model**: Consistent envelope/content so core logic ignores platform differences.
- **Zero-copy dict structures**: TypedDict + dataclass for JSON-friendly models.
- **High-performance transport**: Batch send/recv + orjson + WS/HTTP wrappers.
- **Adapter-friendly**: BaseAdapter, Sink, Router, and batching utilities.
- **Progressive extensibility**: Add gRPC/MQ later by dropping implementations under `transport/`.

---

## 2. Package Layout (`packages/mofox-wire/src/mofox_wire/`)

| Module | Responsibility |
| --- | --- |
| `types.py` | TypedDict models (MessageEnvelope, Content, Sender/ChannelInfo, etc.). |
| `message_models.py` | Dataclass `Seg` / `MessageBase`, compatible with legacy segments. |
| `codec.py` | High-performance JSON encode/decode, batch APIs, schema upgrade hook. |
| `runtime.py` | Routing/hooks/batch scheduler powering the core chain. |
| `adapter_utils.py` | BaseAdapter, CoreMessageSink, BatchDispatcher, and helpers. |
| `api.py` | WebSocket `MessageServer`/`MessageClient`, token support, FastAPI reuse. |
| `router.py` | Manage multi-platform clients, auto-reconnect, dynamic routing. |
| `transport/` | Lightweight HTTP/WS servers/clients, reusable elsewhere. |
| `__init__.py` | Re-export common symbols for consumers. |

---

## 3. Message Model

### 3.1 Envelope TypedDict (`types.py`)

- `MessageEnvelope`: Aligns with original maim_message; core fields `message_info` + `message_segment` (SegPayload), `direction`, `schema_version`. Keeps raw fields; adds `channel`, `sender`, `content`; marks v0 fields optional.
- `SegPayload` / `MessageInfoPayload` / `UserInfoPayload` / `GroupInfoPayload` / `FormatInfoPayload` / `TemplateInfoPayload`: TypedDict counterparts to maim_message dataclasses for direct JSON serialization.
- `Content` / `SenderInfo` / `ChannelInfo`: In-flight iteration; compatible with v0 content model.

### 3.2 Dataclass segments (`message_models.py`)

- `Seg`: One content segment; supports nested `seglist`.
- `UserInfo` / `GroupInfo` / `FormatInfo` / `TemplateInfo`: Preserve legacy fields and add commonly used ones like `user_avatar`.
- `BaseMessageInfo` + `MessageBase`: Let adapters keep the original MessageBase API while the core passes dataclasses in memory.

> **TypedDict vs dataclass?** TypedDict is better for transport/DI; dataclass MessageBase keeps segment behavior for adapter-side processing.

---

## 4. Serialization & Versions (`codec.py`)

- `dumps_message` / `loads_message`: Single `MessageEnvelope`, auto-filling `schema_version` (default 1).
- `dumps_messages` / `loads_messages`: Batch payload `{schema_version, items: [...]}` to cut HTTP/WS round trips.
- `_upgrade_schema_if_needed` hook reserved for v2/v3 compatibility.

Default uses `orjson`; falls back to stdlib `json` when missing.

---
## 5. Runtime Scheduling (`runtime.py`)

- `MessageRuntime`:
  - `add_route(predicate, handler)` and `@runtime.route(...)` decorator to register handlers.
  - `register_before_hook` / `register_after_hook` / `register_error_hook` for pre/post/trace handling.
  - `set_batch_handler` to process a batch at once (batch IO optimization).
- `MessageProcessingError` wraps handler exceptions for easier logging.

Runtime uses `RLock` to protect routes for concurrent access; `_maybe_await` handles sync/async handlers transparently.

---
## 6. Transport Layer (`transport/`)

### 6.1 HTTP
- `HttpMessageServer`: `aiohttp.web` listening on `POST /messages`; can return response batches.
- `HttpMessageClient`: Manages `aiohttp.ClientSession`; `send_messages(messages, expect_reply=True)` waits for replies when needed.

### 6.2 WebSocket
- `WsMessageServer`: Built on `aiohttp`, maintains connections, supports `broadcast`.
- `WsMessageClient`: Auto-reconnect, background reads; `send_messages`/`send_message` sends batches directly.

All reuse the `codec` batch protocol for consistent upstream/downstream format.

---

## 7. Server / Client / Router (`api.py`, `router.py`)

### 7.1 MessageServer
- Can reuse an existing FastAPI app (`app=get_global_server().get_app()`), sharing routes in-process.
- Header token validation (`enable_token` + `add_valid_token`).
- `broadcast_message`, `broadcast_to_platform`, `send_message(message: MessageBase)` for various scenarios.

### 7.2 MessageClient
- WebSocket-only; manages `aiohttp` connections and incoming messages for adapters pushing to the core.

### 7.3 Router
- `RouteConfig` + `TargetConfig` describe platform-to-URL mapping.
- `Router.run()` creates a `MessageClient` per platform and keeps heartbeats; `_monitor_connections` auto-reconnects.
- `register_class_handler` binds class handlers (e.g., Napcat adapter style).

---

## 8. Adapter Utilities (`adapter_utils.py`)

- `BaseAdapter`: Defines inbound `from_platform_message` / outbound `_send_platform_message`; batch entry provided by default.
- `CoreMessageSink` protocol + `InProcessCoreSink`: Push adapter messages to the core coroutine in-process.
- `BatchDispatcher`: Buffered, timed flush pipeline; combine with HTTP/WS clients to boost throughput.

---

## 9. Integration & Config

1. **Config**: Add `[message_bus]` to `config.*.toml` (see `template/bot_config_template.toml`) for host/port/token/wss.
2. **Startup**: `src/common/message/api.py` `get_global_api()` instantiates `MessageServer` and writes the token.
3. **Adapter updates**: Modules using `maim_message` now import from `mofox_wire`; continue using `MessageBase` / `Router` APIs.

---

## 10. Quick Start

```python
from mofox_wire import MessageRuntime, types
from mofox_wire.transport import HttpMessageServer

runtime = MessageRuntime()

@runtime.route(lambda env: (env.get("message_segment") or {}).get("type") == "text")
async def handle_text(env: types.MessageEnvelope):
    print("Received text", env["message_segment"]["data"])

async def http_handler(messages: list[types.MessageEnvelope]):
    await runtime.handle_batch(messages)

server = HttpMessageServer(http_handler)
app = server.make_app()  # hand to aiohttp/uvicorn
```

**Adapter skeleton:**
```python
from mofox_wire import (
    BaseAdapter,
    MessageEnvelope,
    WebSocketAdapterOptions,
)

class MyAdapter(BaseAdapter):
    platform = "custom"

    def __init__(self, core_sink):
        super().__init__(
            core_sink,
            transport=WebSocketAdapterOptions(
                url="ws://127.0.0.1:19898",
                incoming_parser=lambda raw: orjson.loads(raw)["payload"],
            ),
        )

    def from_platform_message(self, raw: dict) -> MessageEnvelope:
        return {
            "id": raw["id"],
            "direction": "incoming",
            "platform": self.platform,
            "timestamp_ms": raw["ts"],
            "channel": {"channel_id": raw["room_id"], "channel_type": "dm"},
            "sender": {"user_id": raw["user_id"], "role": "user"},
            "content": {"type": "text", "text": raw["content"]},
            "conversation_id": raw["room_id"],
        }
```

- With `WebSocketAdapterOptions`, BaseAdapter auto-connects/listens, wraps messages as `{ "type": "message", "payload": ... }` JSON by default, and lets you customize downlink via `outgoing_encoder`.
- With `HttpAdapterOptions`, BaseAdapter auto-starts an aiohttp webhook (`POST /adapter/messages`) and batches incoming JSON to the core.

> See `examples/mofox_wire_demo_adapter.py` for a full WebSocket adapter example: platform WS, adapter auto-starts via WebSocketAdapterOptions, receives/processes/replies; run it to watch logs.

---

## 11. Debugging & Best Practices

- Use `MessageRuntime.register_error_hook` to log `correlation_id` / `id` and locate problematic messages quickly.
- If adapter and core share a process, prefer `InProcessCoreSink` to avoid JSON encode/decode.
- For high-throughput (e.g., HTTP push), batch with `BatchDispatcher` before sending to cut connection overhead.
- Custom transports can follow `transport/http_server.py` / `ws_client.py`; keep the `loads_messages` / `dumps_messages` protocol to interop with the core.

---

MoFox Bus provides an end-to-end unified messaging stack for high-performance, multi-platform AI Bot scenarios. To add new transports or content types, just add the Literal/TypedDict/Transport implementations in the corresponding module. Enjoy!
