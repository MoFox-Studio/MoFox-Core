# API Reference Documentation

## Send API

Send various types of messages to chat streams.

### Functions

```python
from src.plugin_system.apis import send_api

# Send text message
await send_api.text_to_stream(text, stream_id, typing=False, reply_to="", storage_message=True)

# Send emoji
await send_api.emoji_to_stream(emoji_base64, stream_id, storage_message=True)

# Send image
await send_api.image_to_stream(image_base64, stream_id, storage_message=True)

# Send command
await send_api.command_to_stream(command, stream_id, storage_message=True, display_message="")

# Send custom message
await send_api.custom_to_stream(message_type, content, stream_id, display_message="", typing=False, reply_to="")
```

### Message Types

- `"text"` - Text message
- `"emoji"` - Emoji message
- `"image"` - Image message
- `"command"` - Command message
- `"video"` - Video message
- `"audio"` - Audio message

## Message API

Query and process messages.

### Main Functions

```python
from src.plugin_system.apis import message_api

# Get messages by time range
message_api.get_messages_by_time(start_time, end_time, limit=0, limit_mode="latest", filter_mai=False)

# Get messages in chat by time
message_api.get_messages_by_time_in_chat(chat_id, start_time, end_time, limit=0, filter_mai=False)

# Get recent messages
message_api.get_recent_messages(chat_id, hours=24.0, limit=100, filter_mai=False)

# Count new messages
message_api.count_new_messages(chat_id, start_time=0.0, end_time=None)

# Format messages to readable string
message_api.build_readable_messages_to_str(messages, replace_bot_name=True, merge_messages=False)

# Filter bot messages
message_api.filter_mai_messages(messages)
```

## Chat API

Manage chat streams.

### Main Functions

```python
from src.plugin_system.apis import chat_api

# Get all streams
chat_api.get_all_streams(platform="qq")

# Get group streams
chat_api.get_group_streams(platform="qq")

# Get private streams
chat_api.get_private_streams(platform="qq")

# Get stream by group ID
chat_api.get_stream_by_group_id(group_id, platform="qq")

# Get stream by user ID
chat_api.get_stream_by_user_id(user_id, platform="qq")

# Get stream type
chat_api.get_stream_type(chat_stream)

# Get stream info
chat_api.get_stream_info(chat_stream)

# Get streams summary
chat_api.get_streams_summary()
```

## LLM API

Large language model interaction.

### Main Functions

```python
from src.plugin_system.apis import llm_api

# Generate response
await llm_api.generate_response(prompt, model_name=None, temperature=0.7, max_tokens=2000)

# Call LLM with messages
await llm_api.call_llm(messages, model_name=None, temperature=0.7, max_tokens=2000)

# Generate embedding
await llm_api.generate_embedding(text)
```

## Config API

Read configuration values.

### Main Functions

```python
from src.plugin_system.apis import config_api

# Get plugin configuration
config_api.get_plugin_config(plugin_name, section, key, default=None)

# Get global configuration
config_api.get_global_config(section, key, default=None)

# Get all configuration
config_api.get_all_config()
```

## Database API

Database operations (for components).

### Usage in Components

```python
# Use from component
value = self.get_config("key", default)  # Configuration
await self.database_query(...)  # Database operations
```

## Person API

Person/relationship information.

### Main Functions

```python
from src.plugin_system.apis import person_api

# Get person info
person_api.get_person_info(person_id, platform="qq")

# Get relationship info
person_api.get_relationship(user_id, target_id, platform="qq")

# Update relationship
person_api.update_relationship(user_id, target_id, intimacy_value, platform="qq")
```

## Emoji API

Emoji package management.

### Main Functions

```python
from src.plugin_system.apis import emoji_api

# Get emoji by emotion
await emoji_api.get_by_emotion(emotion)

# Get emoji by keyword
await emoji_api.get_by_keyword(keyword)

# Get random emoji
await emoji_api.get_random()
```

## Generator API

Reply generation interface.

### Main Functions

```python
from src.plugin_system.apis import generator_api

# Generate styled reply
await generator_api.generate_styled_reply(content, style="normal")

# Generate summary
await generator_api.generate_summary(content, length="short")
```

## Plugin Manage API

Plugin management.

### Main Functions

```python
from src.plugin_system.apis import plugin_manage_api

# Get loaded plugins
plugin_manage_api.get_loaded_plugins()

# Enable plugin
plugin_manage_api.enable_plugin(plugin_name)

# Disable plugin
plugin_manage_api.disable_plugin(plugin_name)

# Get plugin info
plugin_manage_api.get_plugin_info(plugin_name)
```

## Component Manage API

Component management.

### Main Functions

```python
from src.plugin_system.apis import component_manage_api

# Get components by type
component_manage_api.get_components_by_type(component_type)

# Get component info
component_manage_api.get_component_info(component_name)

# Find components
component_manage_api.find_components(query)
```

## Logging API

Logging functionality.

### Usage

```python
from src.plugin_system import get_logger

logger = get_logger("module_name")
logger.info("Information message")
logger.debug("Debug message")
logger.warning("Warning message")
logger.error("Error message")
```

## Tool API

Tool management.

### Main Functions

```python
from src.plugin_system.apis import tool_api

# Get available tools
tool_api.get_available_tools()

# Get tool by name
tool_api.get_tool(tool_name)

# Call tool
await tool_api.call_tool(tool_name, function_args)
```

---

For detailed parameter and return value documentation, see the original Chinese documentation files in `docs/plugins/api/`.
