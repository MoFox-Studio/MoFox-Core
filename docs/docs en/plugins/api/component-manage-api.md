# Component Management API

Manage registered components.

```python
from src.plugin_system.apis import component_manage_api
```

## Functions
- `get_components_by_type(component_type)` - Get components by type
- `get_component_info(component_name)` - Get component details
- `find_components(query)` - Search components
- `get_all_components()` - Get all registered components
- `register_component(component_info, component_class)` - Register new component

## Example
```python
from src.plugin_system.base.component_types import ComponentType

# Get all actions
actions = component_manage_api.get_components_by_type(ComponentType.ACTION)

# Get all commands
commands = component_manage_api.get_components_by_type(ComponentType.COMMAND)

# Search components
results = component_manage_api.find_components("greeting")

# Get component info
info = component_manage_api.get_component_info("my_action")
```
