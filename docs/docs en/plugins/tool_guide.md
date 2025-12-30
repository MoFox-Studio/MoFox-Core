# Tool Component Guide (Summarized English)

For full details, see `docs/plugins/tool_guide.md`.

## What is Tool

Tools expand MoFox_Bot's information acquisition capabilities. Use Tools to provide external data/services to the LLM.

## Basic Structure

```python
from src.plugin_system import BaseTool, ToolParamType

class MyTool(BaseTool):
    name = "my_tool"
    description = "Tool description for LLM"
    available_for_llm = True
    
    parameters = [
        ("param1", ToolParamType.STRING, "Parameter description", True, None),
        ("param2", ToolParamType.INTEGER, "Optional parameter", False, ["10", "20"])
    ]
    
    async def execute(self, function_args: dict):
        result = f"Processed: {function_args.get('param1')}"
        return {"name": self.name, "content": result}
```

## Caching System

Enable automatic result caching:

```python
class CachedTool(BaseTool):
    enable_cache = True
    cache_ttl = 3600  # 1 hour
    semantic_cache_query_key = "query"  # Use this parameter for semantic matching
```

## Tool vs Action vs Command

| | Tool | Action | Command |
|---|---|---|---|
| Purpose | Info acquisition | Behavior extension | User commands |
| Trigger | LLM decides | MoFox_Bot decides | User input |
| Usage | Provide data | Perform actions | Execute commands |

## Best Practices

✅ One tool = one function
✅ Clear parameter descriptions
✅ Handle errors gracefully
✅ Use caching for API calls
✅ Return structured data
❌ Don't make blocking calls
❌ Don't return raw errors
