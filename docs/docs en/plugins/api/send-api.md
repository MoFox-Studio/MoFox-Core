# Message Sending API

Send various types of messages to chat streams.

## Import

```python
from src.plugin_system.apis import send_api
# or
from src.plugin_system import send_api
```

## Main Functions

### Send Text Message
```python
async def text_to_stream(
    text: str,
    stream_id: str,
    typing: bool = False,
    reply_to: str = "",
    storage_message: bool = True,
) -> bool:
```

### Send Emoji
```python
async def emoji_to_stream(
    emoji_base64: str,
    stream_id: str,
    storage_message: bool = True
) -> bool:
```

### Send Image
```python
async def image_to_stream(
    image_base64: str,
    stream_id: str,
    storage_message: bool = True
) -> bool:
```

### Send Command
```python
async def command_to_stream(
    command: Union[str, dict],
    stream_id: str,
    storage_message: bool = True,
    display_message: str = ""
) -> bool:
```

### Send Custom Message
```python
async def custom_to_stream(
    message_type: str,
    content: str,
    stream_id: str,
    display_message: str = "",
    typing: bool = False,
    reply_to: str = "",
    storage_message: bool = True,
    show_log: bool = True,
) -> bool:
```

## Usage Example

```python
from src.plugin_system.apis import send_api

# Send greeting
await send_api.text_to_stream(
    text="Hello, world!",
    stream_id=chat_stream.stream_id,
    typing=True
)

# Send with reply
await send_api.text_to_stream(
    text="Thanks for asking!",
    stream_id=chat_stream.stream_id,
    reply_to="User:How are you?"
)
```

## Supported Message Types

- `"text"` - Text message
- `"emoji"` - Emoji message
- `"image"` - Image message
- `"command"` - Command message
- `"video"` - Video message
- `"audio"` - Audio message
