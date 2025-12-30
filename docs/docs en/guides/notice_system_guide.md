# Notice System Usage Guide

## Overview

The Notice system is used to manage and display system notification messages, supporting two scopes:
- **Public Notice**: Visible to all chat streams
- **Stream-level Notice**: Visible only to specific chat streams

## Notice Configuration

### 1. Mark Message as Notice

Set the following fields in the message's `additional_config`:

```python
additional_config = {
    "is_notice": True,  # Mark as notice message
    "notice_type": "group_ban",  # Notice type (optional)
    "is_public_notice": False,  # Whether it's a public notice
}
```

### 2. Notice Scope

Notice scope is completely determined by the `is_public_notice` field:

#### Stream-level Notice (Default)
```python
additional_config = {
    "is_notice": True,
    "is_public_notice": False,  # Or don't set this field
}
```
- Visible only in the chat stream the message belongs to
- Applicable to: group bans, group unbans, pokes and other group events

#### Public Notice
```python
additional_config = {
    "is_notice": True,
    "is_public_notice": True,  # Explicitly set as public
}
```
- Visible in all chat streams
- Applicable to: system announcements, platform maintenance notifications and other global events

### 3. Notice Types

Use the `notice_type` field to categorize notices:

```python
# Common notice types
notice_types = {
    "group_ban": "Group ban",
    "group_lift_ban": "Group unban",
    "group_whole_ban": "Whole group ban",
    "group_whole_lift_ban": "Whole group unban",
    "poke": "Poke",
    "system_announcement": "System announcement",
    "platform_maintenance": "Platform maintenance",
}
```

### 4. Notice Time-to-Live (TTL)

Notice messages automatically expire after a certain time, default is 1 hour (3600 seconds).

Different types of notices can have different TTLs:
- Temporary events (pokes): 5 minutes
- Group management events (ban/unban): 1 hour
- Important announcements: 24 hours

## Usage Examples

### Example 1: Group Ban Notice (Stream-level)

```python
from src.common.data_models.database_data_model import DatabaseMessages

message = DatabaseMessages(
    chat_id="group_123456",
    sender_id="10001",
    raw_message="User 张三 has been banned for 10 minutes by admin",
    additional_config={
        "is_notice": True,
        "is_public_notice": False,  # Only visible in this group
        "notice_type": "group_ban",
        "target_id": "user_12345",
    }
)
```

### Example 2: System Maintenance Announcement (Public)

```python
message = DatabaseMessages(
    chat_id="system",
    sender_id="system",
    raw_message="System will undergo maintenance tonight at 23:00, expected duration 1 hour",
    additional_config={
        "is_notice": True,
        "is_public_notice": True,  # Visible in all chat streams
        "notice_type": "platform_maintenance",
    }
)
```

### Example 3: Send Notice in Plugin

```python
from src.api import send_private_message, send_group_message

# Send group notice
await send_group_message(
    group_id=123456,
    message="Admin has enabled group-wide ban",
    additional_config={
        "is_notice": True,
        "is_public_notice": False,
        "notice_type": "group_whole_ban",
    }
)

# Send public notice
await send_group_message(
    group_id=123456,  # Any valid group number
    message="🔔 Bot will restart in 5 minutes for updates",
    additional_config={
        "is_notice": True,
        "is_public_notice": True,
        "notice_type": "system_announcement",
    }
)
```

## Notice Display in Prompt

When `notice_in_prompt` configuration is enabled, notice messages are automatically added to the AI's prompt:

```
## 📢 Recent System Notifications

[Group Ban] User 张三 has been banned for 10 minutes by admin (5 minutes ago)
[Poke] 李四 poked you (just now)
[System Announcement] Bot will restart in 5 minutes for updates (2 minutes ago)
```

## Configuration Options

Configure notice system in `bot_config.toml`:

```toml
[notice]
# Whether to display notice in prompt
notice_in_prompt = true

# Limit of notice count displayed in prompt
notice_prompt_limit = 5
```

## Important Notes

1. **Scope Control**: 
   - `is_public_notice` field is the only factor that determines notice scope
   - Don't rely on `notice_type` to control scope

2. **Performance Considerations**:
   - Notice messages automatically expire and are cleaned up
   - Store maximum 100 notices per type
   - Auto-cleanup expired messages every 5 minutes

3. **Compatibility**:
   - If `is_public_notice` is not set, defaults to stream-level notice
   - Old code relying on `notice_type` to determine public status has been removed

## Migration Guide

If your code relied on the following notice types automatically becoming public notices:
- `group_whole_ban`
- `group_whole_lift_ban`
- `system_announcement`
- `platform_maintenance`

Please explicitly set in the message's `additional_config`:

```python
# Before (relying on hard-coded logic)
additional_config = {
    "is_notice": True,
    "notice_type": "system_announcement",
    # Would automatically become public notice
}

# After (explicit specification)
additional_config = {
    "is_notice": True,
    "notice_type": "system_announcement",
    "is_public_notice": True,  # Explicitly set
}
```

## API Reference

### GlobalNoticeManager

```python
from src.chat.message_manager.global_notice_manager import global_notice_manager

# Add notice
success = global_notice_manager.add_notice(
    message=db_message,
    scope=NoticeScope.PUBLIC,  # Or NoticeScope.STREAM
    target_stream_id="group_123456",  # Required for STREAM mode
    ttl=3600  # Time-to-live (seconds)
)

# Get accessible notices
notices = global_notice_manager.get_accessible_notices(
    stream_id="group_123456",
    limit=10
)

# Get formatted notice text
text = global_notice_manager.get_notice_text(
    stream_id="group_123456",
    limit=5
)
```

## FAQ

### Q: Notice doesn't show in prompt?
A: Check configuration:
1. `notice.notice_in_prompt = true` in `bot_config.toml`
2. Confirm message has `is_notice = True`
3. Confirm notice hasn't expired

### Q: How to make notice visible in all groups?
A: Set `is_public_notice = True` in `additional_config`

### Q: How to set custom notice type?
A: Set any string as `notice_type` in `additional_config`

### Q: When will notice be cleaned up?
A: 
1. Auto-cleanup after TTL expires
2. Remove oldest when exceeding 100 per type
3. Manual cleanup via API
