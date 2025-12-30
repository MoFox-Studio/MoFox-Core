# Event System Guide (Summarized English Version)

For full details, see `docs/plugins/event-system-guide.md`.

## Overview

Event system enables plugins to communicate through publish-subscribe pattern.

## Quick Start

### Create Event Handler

```python
from src.plugin_system import BaseEventHandler, EventType
from src.plugin_system.base.base_event import HandlerResult

class MyEventHandler(BaseEventHandler):
    handler_name = "my_handler"
    init_subscribe = [EventType.ON_MESSAGE]
    
    async def execute(self, params: dict) -> HandlerResult:
        # Handle event
        return HandlerResult(success=True, continue_process=True, message="Done")
```

### Register Handler

```python
@register_plugin
class MyPlugin(BasePlugin):
    def get_plugin_components(self):
        return [(MyEventHandler.get_handler_info(), MyEventHandler)]
```

### Trigger Event

```python
from src.plugin_system.core.event_manager import event_manager

await event_manager.trigger_event(
    EventType.ON_MESSAGE,
    permission_group="SYSTEM",
    message="Hello"
)
```

## Built-in Events

- `ON_START` - System startup
- `ON_STOP` - System shutdown
- `ON_MESSAGE` - New message received
- `POST_LLM` - Before LLM call
- `AFTER_LLM` - After LLM response
- `POST_SEND` - Before sending message
- `AFTER_SEND` - After message sent

## Key Concepts

- **Event** - Something that happens in the system
- **Handler** - Code that responds to events
- **Manager** - Coordinates events and handlers
- **Weight** - Handler execution priority
- **Interception** - Handler can block message flow

## Best Practices

✅ Use built-in events when possible
✅ Set appropriate handler weights
✅ Handle exceptions in execute()
✅ Use meaningful handler names
❌ Don't create infinite event loops
