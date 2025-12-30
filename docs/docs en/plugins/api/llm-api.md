# LLM API - Large Language Model Interaction

```python
from src.plugin_system.apis import llm_api
```

## Functions
- `generate_response(prompt, model=None, temperature=0.7, max_tokens=2000)` - Generate text response
- `call_llm(messages, model=None, temperature=0.7)` - Call LLM with messages
- `generate_embedding(text)` - Generate text embedding
- `get_available_models()` - Get available models
- `set_default_model(model_name)` - Set default model

## Example
```python
response = await llm_api.generate_response(
    prompt="Explain quantum computing",
    temperature=0.7,
    max_tokens=500
)

# With message history
messages = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"},
    {"role": "user", "content": "How are you?"}
]
response = await llm_api.call_llm(messages)
```
