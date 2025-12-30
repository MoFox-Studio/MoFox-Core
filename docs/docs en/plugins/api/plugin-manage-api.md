# Plugin Management API

Manage loaded plugins.

```python
from src.plugin_system.apis import plugin_manage_api
```

## Functions
- `get_loaded_plugins()` - Get list of loaded plugins
- `enable_plugin(plugin_name)` - Enable a plugin
- `disable_plugin(plugin_name)` - Disable a plugin
- `get_plugin_info(plugin_name)` - Get plugin details
- `reload_plugin(plugin_name)` - Reload a plugin
- `get_plugin_status(plugin_name)` - Get plugin status

## Example
```python
# Get all loaded plugins
plugins = plugin_manage_api.get_loaded_plugins()

# Get specific plugin info
info = plugin_manage_api.get_plugin_info("my_plugin")
# Returns: {name, version, description, enabled, ...}

# Disable plugin
plugin_manage_api.disable_plugin("my_plugin")

# Enable plugin
plugin_manage_api.enable_plugin("my_plugin")
```
