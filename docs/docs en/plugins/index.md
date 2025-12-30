# MoFox_Bot Plugin Development Documentation

> Welcome to the MoFox_Bot plugin system development documentation! This is the best starting point for your plugin development journey.

## Getting Started for Beginners

- [📖 Quick Start Guide](quick-start.md) - Quickly create your first plugin
- [🔧 Troubleshooting Guide](troubleshooting-guide.md) - Quickly solve common problems ⭐ **NEW**

## Component Feature Details

- [🧱 Action Component Details](action-components.md) - Master the most core Action component
- [💻 Command Component Details](PLUS_COMMAND_GUIDE.md) - Learn direct command response components
- [🔧 Tool Component Details](tool_guide.md) - Understand how to extend information acquisition capabilities
- [⚙️ Configuration File System Guide](configuration-guide.md) - Learn how to use auto-generated plugin configuration files
- [📄 Manifest System Guide](manifest-guide.md) - Understand plugin metadata management and configuration architecture

### Command vs Action Selection Guide

1. **When to Use Command**

- ✅ When users need to explicitly call specific functions
- ✅ When precise parameter control is needed
- ✅ Management and configuration operations
- ✅ Query and information display
- ✅ System maintenance commands

2. **When to Use Action**

- ✅ Enhance AI character's intelligent behavior
- ✅ Auto-trigger based on context
- ✅ Emotion and expression display
- ✅ Intelligent suggestions and help
- ✅ Randomized interactions


## API Browser

### Message Sending and Processing APIs
- [📤 Send API](api/send-api.md) - Various message type sending interfaces
- [Message API](api/message-api.md) - Message retrieval, message construction, message query interfaces
- [Chat Stream API](api/chat-api.md) - Chat stream management and query interfaces

### AI and Generation APIs  
- [LLM API](api/llm-api.md) - Large language model interaction interface, can use built-in LLM for content generation
- [✨ Reply Generator API](api/generator-api.md) - Intelligent reply generation interface, can use built-in stylized generator

### Emoji API
- [😊 Emoji API](api/emoji-api.md) - Emoji selection and management interface

### Relationship System APIs
- [Person Information API](api/person-api.md) - User information, interface for handling people and relationships that AI knows

### Data and Configuration APIs
- [🗄️ Database API](api/database-api.md) - Database operation interface
- [⚙️ Config API](api/config-api.md) - Configuration reading and user information interface

### Plugin and Component Management APIs
- [🔌 Plugin API](api/plugin-manage-api.md) - Plugin loading and management interface
- [🧩 Component API](api/component-manage-api.md) - Component registration and management interface

### Logging API
- [📜 Logging API](api/logging-api.md) - Logger instance retrieval interface
### Tool API
- [🔧 Tool API](api/tool-api.md) - Tool retrieval interface



## Support

> If you find errors in the documentation or need additions, please:

1. Check the latest documentation version
2. Look at related example code
3. Refer to similar plugins
4. Submit issues to the documentation repository

## A Convenient Design

We defined an `__all__` variable in `__init__.py` that includes all classes and functions that need to be exported.
This way, when importing elsewhere, you can directly use `from src.plugin_system import *` to import all plugin-related classes and functions.
Or you can directly use `from src.plugin_system import BasePlugin, register_plugin, ComponentInfo` and similar ways to import only the parts you need.
