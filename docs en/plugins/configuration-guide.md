# Configuration System Complete Guide (English Summarized)

For complete details, see the original `docs/plugins/configuration-guide.md`.

## Quick Overview

Configure plugins using two files:
- `_manifest.json` - Static metadata
- `config.toml` - Runtime configuration (auto-generated from code)

## Define Configuration in Code

```python
from src.plugin_system import BasePlugin, ConfigField

@register_plugin
class MyPlugin(BasePlugin):
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=False, description="Is plugin enabled")
        },
        "features": {
            "feature_name": ConfigField(type=str, default="default", description="Feature name")
        }
    }
```

## Access Configuration

```python
# In your component
value = self.get_config("section.key", default_value)
```

## Key Features

- **Auto-generation**: Config file automatically generated from `config_schema`
- **Version management**: Auto-migrate config when schema changes
- **Type validation**: Ensures config values match specified types
- **Default values**: Fallback to defaults when config missing

## Best Practices

✅ Define config in code via `config_schema`
✅ Never manually edit `config.toml`
✅ Use semantic keys like "section.field"
✅ Always provide default values
❌ Don't create config files manually
