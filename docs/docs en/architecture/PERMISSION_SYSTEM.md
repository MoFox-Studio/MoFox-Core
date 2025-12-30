# Permission System Guide

## Overview

The MoFox_Bot permission system provides full permission management with both permission levels and nodes. Core concepts:

- **Master users**: Highest authority, bypass all nodes, configured in the file.
- **Permission nodes**: Fine-grained control units, created and managed by plugins.
- **Permission management**: Unified grant, revoke, and query functions.

## Configuration

Add permission settings to `config/bot_config.toml`:

```toml
[permission] # Permission system config
# Master users (bypass all nodes)
# Format: [[platform, user_id], ...]
master_users = [
    ["qq", "123456789"],  # Master user on QQ
    ["qq", "987654321"],  # Multiple masters supported
]
```

## Using Permissions in Plugins

### 1) Register permission nodes

Register nodes in the plugin `on_load()` method:

```python
from src.plugin_system.apis.permission_api import permission_api

class MyPlugin(BasePlugin):
    def on_load(self):
        # Register permission nodes
        permission_api.register_permission_node(
            "plugin.myplugin.admin",   # Node name
            "Admin permission for my plugin",  # Description
            "myplugin",                # Plugin name
            False                       # Default grant? (False = deny)
        )
        
        permission_api.register_permission_node(
            "plugin.myplugin.user",
            "User permission for my plugin",
            "myplugin",
            True  # Default grant
        )
```

### 2) Use permission decorators

The simplest check uses decorators:

```python
from src.plugin_system.utils.permission_decorators import require_permission, require_master

class MyCommand(BaseCommand):
    @require_permission("plugin.myplugin.admin")
    async def execute(self, message: Message, chat_stream: ChatStream, args: List[str]):
        await send_message(chat_stream, "You have admin permission!")
    
    @require_master("Only Master can run this")
    async def master_only_function(self, message: Message, chat_stream: ChatStream):
        await send_message(chat_stream, "Master-only feature")
```

### 3) Manual permission checks

For more complex logic, check manually:

```python
from src.plugin_system.utils.permission_decorators import PermissionChecker

class MyCommand(BaseCommand):
    async def execute(self, message: Message, chat_stream: ChatStream, args: List[str]):
        # Master check
        if PermissionChecker.is_master(chat_stream):
            await send_message(chat_stream, "Master can do everything")
            return
        
        # Specific permission
        if PermissionChecker.check_permission(chat_stream, "plugin.myplugin.read"):
            await send_message(chat_stream, "You can read data")
        
        # ensure_permission auto-sends insufficient-permission message
        if await PermissionChecker.ensure_permission(chat_stream, "plugin.myplugin.write"):
            await send_message(chat_stream, "You can write data")
```

### 4) Direct permission API usage

```python
from src.plugin_system.apis.permission_api import permission_api

# Check permission
has_permission = permission_api.check_permission("qq", "123456", "plugin.myplugin.admin")

# Check Master
is_master = permission_api.is_master("qq", "123456")

# Grant user
success = permission_api.grant_permission("qq", "123456", "plugin.myplugin.admin")

# Revoke user
success = permission_api.revoke_permission("qq", "123456", "plugin.myplugin.admin")

# Get all permissions for user
permissions = permission_api.get_user_permissions("qq", "123456")

# Get all permission nodes
all_nodes = permission_api.get_all_permission_nodes()

# Get nodes for a plugin
plugin_nodes = permission_api.get_plugin_permission_nodes("myplugin")
```

## Permission Management Commands

Built-in commands require corresponding permissions:

### Admin commands (need `plugin.permission.manage`)

```
# Grant
/permission grant @user plugin.example.admin
/permission grant 123456789 plugin.example.admin

# Revoke
/permission revoke @user plugin.example.admin
/permission revoke 123456789 plugin.example.admin
```

### View commands (need `plugin.permission.view`)

```
# List user permissions
/permission list @user
/permission list 123456789
/permission list  # List your own

# Check a permission
/permission check @user plugin.example.admin
/permission check 123456789 plugin.example.admin

# List permission nodes
/permission nodes  # All nodes
/permission nodes example_plugin  # Nodes for a plugin
```

### Help command

```
/permission help  # Show help
```

## Naming Convention

Suggested format:

```
plugin.<plugin>.<category>.<permission>
```

Examples:
- `plugin.music.play` - play permission for music plugin
- `plugin.music.admin` - admin permission for music plugin
- `plugin.game.user` - user permission for game plugin
- `plugin.game.room.create` - room creation permission for game plugin

## Database Tables

The system auto-creates:

1. **permission_nodes** - Permission node info
2. **user_permissions** - User grants

## Best Practices

1. **Fine-grained nodes**: Separate permissions per feature.
2. **Default grants**: Be careful; sensitive actions should default to deny.
3. **Descriptions**: Give each node a clear description.
4. **Master users**: Assign Master only to real admins.
5. **Checks**: Always check permission before sensitive actions.

## Example Plugin

See `plugins/permission_example.py` for a complete example.

## Troubleshooting

1. **Checks failing**: Ensure nodes are registered.
2. **Master config**: Verify user ID format in config.
3. **Changes not applied**: Restart the bot to reload config.
4. **DB issues**: Check DB connection and schema.
