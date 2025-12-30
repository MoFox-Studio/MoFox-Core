# Tool API

Tool management and calling.

```python
from src.plugin_system.apis import tool_api
```

## Functions
- `get_available_tools()` - Get list of available tools
- `get_tool(tool_name)` - Get tool by name
- `call_tool(tool_name, function_args)` - Execute tool
- `get_tool_definition(tool_name)` - Get tool schema
- `register_tool(tool)` - Register new tool

## Example
```python
# Get available tools
tools = tool_api.get_available_tools()
# Returns: [tool1, tool2, ...]

# Get tool definition (for LLM)
definition = tool_api.get_tool_definition("web_search")

# Call tool
result = await tool_api.call_tool(
    "web_search",
    {"query": "Python programming"}
)
```

## Tool Definition
```python
{
    "name": "web_search",
    "description": "Search the web for information",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
}
```
