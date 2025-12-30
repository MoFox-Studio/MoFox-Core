# MoFox Bot Message Runtime Architecture (MessageRuntime)

This document describes how MoFox Bot uses `mofox_wire.MessageRuntime` to simplify the message processing pipeline.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CoreSinkManager                                │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                        MessageRuntime                                ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               ││
│  │  │ before_hook  │→ │   Routes     │→ │ after_hook   │               ││
│  │  │ (pre/filter) │  │ (routing)    │  │ (post)       │               ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘               ││
│  │         ↓                 ↓                 ↓                        ││
│  │  ┌──────────────────────────────────────────────────────────────┐   ││
│  │  │                     error_hook (error handling)               │   ││
│  │  └──────────────────────────────────────────────────────────────┘   ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌──────────────────────┐   ┌──────────────────────────────────────┐    │
│  │ InProcessCoreSink    │   │ ProcessCoreSinkServer (subprocess)   │    │
│  │ (same process)       │   │                                      │    │
│  └──────────────────────┘   └──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
              ↑                                    ↑
              │                                    │
    ┌─────────────────────┐            ┌─────────────────────┐
    │  Same-process adp.  │            │ Subprocess adapter   │
    │ (run_in_subprocess  │            │ (run_in_subprocess   │
    │  = False)           │            │  = True)             │
    └─────────────────────┘            └─────────────────────┘
```

## Core Components

### 1. CoreSinkManager (`src/common/core_sink_manager.py`)

Manages the two CoreSink instances and MessageRuntime:

```python
from src.common.core_sink_manager import get_core_sink_manager, get_message_runtime

# Manager
manager = get_core_sink_manager()

# MessageRuntime
runtime = get_message_runtime()

# Send outgoing message to adapters
await manager.send_outgoing(envelope)
```

### 2. MessageRuntime

The routing core from mofox_wire supports:

- **Routing**: `add_route()` or `@on_message` decorator by message type.
- **Hooks**: `before_hook`, `after_hook`, `error_hook`.
- **Middleware**: Onion-style middleware chain.
- **Batch**: `handle_batch()` for batch handling.

### 3. MessageHandler (`src/chat/message_receive/message_handler.py`)

Registers handlers and hooks on MessageRuntime:

```python
class MessageHandler:
    def register_handlers(self, runtime: MessageRuntime) -> None:
        runtime.register_before_hook(self._before_hook)
        runtime.register_after_hook(self._after_hook)
        runtime.register_error_hook(self._error_hook)
        
        runtime.add_route(
            predicate=_is_adapter_response,
            handler=self._handle_adapter_response_route,
            name="adapter_response_handler",
            message_type="adapter_response",
        )
        
        runtime.add_route(
            predicate=lambda _: True,
            handler=self._handle_normal_message,
            name="default_message_handler",
        )
```

## Message Flow

### Incoming

```
Adapter → InProcessCoreSink/ProcessCoreSinkServer → CoreSinkManager._dispatch_to_runtime()
       → MessageRuntime.handle_message()
       → before_hook (preprocess/filter)
       → route match (adapter_response / normal_message)
       → handler execution
       → after_hook (postprocess)
```

### Outgoing

```
Send request → CoreSinkManager.send_outgoing()
           → InProcessCoreSink.push_outgoing()
           → ProcessCoreSinkServer.push_outgoing()
           → Adapter
```

## Hooks

### before_hook
- Normalize IDs to strings.
- Detect echo messages (self messages).
- Raise `UserWarning` to skip processing.

### after_hook
- Cleanup.
- Logging.

### error_hook
- Distinguish flow control (`UserWarning`) vs real errors.
- Centralized exception logging.

## Routing Priority

1. **Routes with explicit `message_type`** (highest).
2. **Event routes** (by `event_type`).
3. **Generic routes** (no `message_type`).

## Extending Processing

### Register custom handlers

```python
from src.common.core_sink_manager import get_message_runtime
from mofox_wire import MessageEnvelope

runtime = get_message_runtime()

@runtime.on_message(message_type="image")
async def handle_image(envelope: MessageEnvelope):
    pass

runtime.add_route(
    predicate=lambda env: env.get("platform") == "qq",
    handler=my_handler,
    name="qq_handler",
)
```

### Register hooks

```python
runtime = get_message_runtime()

async def my_before_hook(envelope: MessageEnvelope) -> None:
    pass

runtime.register_before_hook(my_before_hook)

async def my_error_hook(envelope: MessageEnvelope, exc: BaseException) -> None:
    pass

runtime.register_error_hook(my_error_hook)
```

## Initialization Flow

In `MainSystem.initialize()`:

1. Init `CoreSinkManager` (includes `MessageRuntime`).
2. Get `MessageHandler` and set the manager reference.
3. Call `MessageHandler.register_handlers()` to add routes/hooks to `MessageRuntime`.
4. Init other components.

```python
async def initialize(self) -> None:
    self.core_sink_manager = await initialize_core_sink_manager()
    
    self.message_handler = get_message_handler()
    self.message_handler.set_core_sink_manager(self.core_sink_manager)
    self.message_handler.register_handlers(self.core_sink_manager.runtime)
```

## Benefits

1. **Simplified pipeline**: Declarative routing instead of manual chains.
2. **Better extensibility**: Add handlers via `add_route()` or decorators.
3. **Unified error handling**: Centralized via `error_hook`.
4. **Middleware support**: Onion-model middleware.
5. **Clearer structure**: Logic separated by message type.

## References

- `packages/mofox-wire/src/mofox_wire/runtime.py` — MessageRuntime implementation.
- `src/common/core_sink_manager.py` — CoreSinkManager implementation.
- `src/chat/message_receive/message_handler.py` — MessageHandler implementation.
- `docs/mofox_wire.md` — MoFox Bus message library overview.
