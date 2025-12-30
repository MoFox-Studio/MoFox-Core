# Adapter Command API

Adapter-specific command interface.

## Overview

This API provides adapter-specific command handling for different chat platforms (QQ, Telegram, etc.).

## Adapter Interface
```python
from src.plugin_system import BaseAdapter

class MyAdapter(BaseAdapter):
    async def send_message(self, channel_id, message)
    async def get_user_info(self, user_id)
    async def execute_command(self, command, args)
```

## Platform-Specific Commands

### QQ Adapter
- `/group_info` - Get group information
- `/user_info` - Get user information
- `/set_card` - Set card name
- `/send_like` - Send like

### Telegram Adapter
- `/start` - Start bot
- `/help` - Get help
- `/settings` - Configure settings

## Usage in Plugins
```python
# Commands work automatically based on platform
# The plugin system handles platform-specific details
await self.send_text("platform-independent message")
```

## Best Practices
✅ Use cross-platform APIs
✅ Test on multiple adapters
✅ Handle platform differences gracefully
❌ Don't hardcode adapter-specific logic
❌ Don't assume QQ-only features
