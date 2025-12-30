# Configuration API

Read plugin and global configuration.

```python
from src.plugin_system.apis import config_api
```

## Functions
- `get_plugin_config(plugin_name, section, key, default=None)` - Get plugin config
- `get_global_config(section, key, default=None)` - Get global config
- `get_all_config()` - Get all configuration

## In Components
```python
# Easiest way in components
value = self.get_config("section.key", default_value)

# Direct API
from src.plugin_system.apis import config_api
value = config_api.get_plugin_config("my_plugin", "section", "key", "default")
```

## Example
```python
# Get feature enabled status
enabled = self.get_config("features.advanced", False)

# Get timeout value
timeout = self.get_config("api.timeout", 30)

# Get list config
servers = self.get_config("servers", [])
```
