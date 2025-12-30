# Emoji API

Emoji package management and selection.

```python
from src.plugin_system.apis import emoji_api
```

## Functions
- `get_by_emotion(emotion)` - Get emoji for emotion
- `get_by_keyword(keyword)` - Get emoji by keyword
- `get_random()` - Get random emoji
- `get_all()` - Get all emojis
- `search(query)` - Search emojis

## Example
```python
# Get emoji for emotion
emoji_data = await emoji_api.get_by_emotion("happy")
# Returns: (emoji_base64, description, matched_emotion)

# Get by keyword
emojis = await emoji_api.get_by_keyword("laugh")

# Get random
emoji_data = await emoji_api.get_random()

# Send emoji
await send_api.emoji_to_stream(emoji_base64, stream_id)
```
