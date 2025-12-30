# Chat Stream API

Manage chat streams across different platforms.

## Import
```python
from src.plugin_system import chat_api
```

## Functions
- `get_all_streams(platform="qq")` - Get all chat streams
- `get_group_streams(platform="qq")` - Get group streams only
- `get_private_streams(platform="qq")` - Get private streams only
- `get_stream_by_group_id(group_id)` - Get stream by group ID
- `get_stream_by_user_id(user_id)` - Get stream by user ID
- `get_stream_type(chat_stream)` - Get stream type (group/private/unknown)
- `get_stream_info(chat_stream)` - Get detailed stream info
- `get_streams_summary()` - Get summary statistics

## Usage
```python
# Get all streams
all_streams = chat_api.get_all_streams()

# Get specific stream
stream = chat_api.get_stream_by_group_id("123456")

# Get stream type
stream_type = chat_api.get_stream_type(stream)

# Get summary
summary = chat_api.get_streams_summary()
# Returns: {total_streams, group_streams, private_streams, qq_streams}
```
