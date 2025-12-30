# Generator API - Reply Generation

```python
from src.plugin_system.apis import generator_api
```

## Functions
- `generate_styled_reply(content, style="normal")` - Generate styled reply
- `generate_summary(content, length="short")` - Generate summary
- `generate_title(content)` - Generate title
- `paraphrase(text)` - Paraphrase text

## Example
```python
# Generate styled reply
reply = await generator_api.generate_styled_reply(
    "User asked about AI",
    style="friendly"
)

# Generate summary
summary = await generator_api.generate_summary(
    long_text,
    length="medium"
)
```
