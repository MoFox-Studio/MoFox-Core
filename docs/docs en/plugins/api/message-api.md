# Message Processing API

Query and manage messages.

## Import
```python
from src.plugin_system.apis import message_api
```

## Main Functions

### Query Messages
- `get_messages_by_time(start_time, end_time, limit=0)` - Get messages in time range
- `get_messages_by_time_in_chat(chat_id, start_time, end_time)` - Get messages in specific chat
- `get_recent_messages(chat_id, hours=24.0, limit=100)` - Get recent messages
- `get_messages_before_time(timestamp, limit=0)` - Get messages before specific time

### Count Messages
- `count_new_messages(chat_id, start_time, end_time)` - Count new messages
- `count_new_messages_for_users(chat_id, start_time, end_time, person_ids)` - Count for specific users

### Format Messages
- `build_readable_messages_to_str(messages, replace_bot_name=True)` - Format as string
- `build_readable_messages_with_details(messages)` - Format with details

### Utility
- `get_person_ids_from_messages(messages)` - Extract user IDs from messages
- `filter_mai_messages(messages)` - Remove bot messages

## Usage Example

```python
from src.plugin_system.apis import message_api

# Get recent messages
messages = message_api.get_recent_messages("chat_id_123", hours=24, limit=50)

# Format as readable string
readable = message_api.build_readable_messages_to_str(messages, replace_bot_name=True)

# Count new messages
count = message_api.count_new_messages("chat_id_123", start_time=time1, end_time=time2)
```

## Parameters

- `chat_id` (str) - Chat identifier
- `start_time` (float) - Unix timestamp
- `end_time` (float) - Unix timestamp
- `limit` (int) - Max number of results
- `filter_mai` (bool) - Whether to exclude bot messages
