# Enhanced Command System Usage Guide

> ⚠️ **Important: Plugin commands must use PlusCommand!**
> 
> - ✅ **Recommended**: `PlusCommand` - Standard base class for plugin development
> - ❌ **Forbidden**: `BaseCommand` - Only for framework internal use
> 
> If you directly use `BaseCommand`, you will need to manually handle parameter parsing, regex matching and other complex logic, and the `execute()` method signature is also different.

## Overview

The Enhanced Command System is an extension of the MoFox-Bot plugin system that makes command definition and usage much simpler and more intuitive. You no longer need to write complex regular expressions, just define the command name, aliases and parameter processing logic.

## Core Features

- **No Regular Expressions Needed**: Just define command name and aliases
- **Automatic Parameter Parsing**: Provides `CommandArgs` class for parameter handling
- **Command Alias Support**: One command can have multiple aliases
- **Priority Control**: Support command priority setting
- **Chat Type Restriction**: Can restrict commands to group or private chats
- **Message Interception**: Can choose whether to intercept messages for subsequent processing

## Quick Start

### 1. Create Basic Command

```python
from src.plugin_system import PlusCommand, CommandArgs, ChatType
from typing import Tuple, Optional

class EchoCommand(PlusCommand):
    """Echo command example"""
    
    command_name = "echo"
    command_description = "Echo command"
    command_aliases = ["say", "repeat"]  # Optional: command aliases
    priority = 5  # Optional: priority, higher number has higher priority
    chat_type_allow = ChatType.ALL  # Optional: ALL, GROUP, PRIVATE
    intercept_message = True  # Optional: whether to intercept messages

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        """Execute command"""
        if args.is_empty():
            await self.send_text("❓ Please provide content to echo\\nUsage: /echo <content>")
            return True, "Insufficient parameters", True
        
        content = args.get_raw()
        await self.send_text(f"🔊 {content}")
        
        return True, "Echo command executed successfully", True
```

### 2. Register Command in Plugin

```python
from src.plugin_system import BasePlugin, create_plus_command_adapter, register_plugin

@register_plugin
class MyPlugin(BasePlugin):
    plugin_name = "my_plugin"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"

    def get_plugin_components(self):
        components = []
        
        # Use factory function to create adapter
        echo_adapter = create_plus_command_adapter(EchoCommand)
        components.append((EchoCommand.get_command_info(), echo_adapter))
        
        return components
```

## CommandArgs Class Details

The `CommandArgs` class provides rich parameter processing functionality:

### Basic Methods

```python
# Get raw parameter string
raw_text = args.get_raw()

# Get parsed parameter list (split by space, support quotes)
arg_list = args.get_args()

# Check if there are parameters
if args.is_empty():
    # Handle no parameters

# Get number of parameters
count = args.count()
```

### Get Specific Parameters

```python
# Get first parameter
first_arg = args.get_first("default value")

# Get parameter at specific index
second_arg = args.get_arg(1, "default value")

# Get remaining parameters from specified position
remaining = args.get_remaining(1)  # From 2nd parameter
```

### Flag Parameter Handling

```python
# Check if contains flag
if args.has_flag("--verbose"):
    # Handle verbose mode

# Get flag value
output_file = args.get_flag_value("--output", "default.txt")
name = args.get_flag_value("--name", "Anonymous")
```

## Advanced Examples

### 1. Complex Command with Subcommands

```python
class TestCommand(PlusCommand):
    command_name = "test"
    command_description = "Test command, demonstrates parameter parsing functionality"
    command_aliases = ["t"]

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        if args.is_empty():
            await self.send_text("Usage: /test <subcommand> [parameters]")
            return True, "Show help", True
        
        subcommand = args.get_first().lower()
        
        if subcommand == "args":
            result = f"""
🔍 Parameter Parsing Results:
Raw string: '{args.get_raw()}'
Parsed parameters: {args.get_args()}
Parameter count: {args.count()}
First parameter: '{args.get_first()}'
Remaining parameters: '{args.get_remaining()}'
            """
            await self.send_text(result)
            
        elif subcommand == "flags":
            result = f"""
🏴 Flag Test Results:
Contains --verbose: {args.has_flag('--verbose')}
Contains -v: {args.has_flag('-v')}
Value of --output: '{args.get_flag_value('--output', 'Not set')}'
Value of --name: '{args.get_flag_value('--name', 'Not set')}'
            """
            await self.send_text(result)
            
        else:
            await self.send_text(f"❓ Unknown subcommand: {subcommand}")
        
        return True, "Test command executed successfully", True
```

### 2. Chat Type Restriction Example

```python
class PrivateOnlyCommand(PlusCommand):
    command_name = "private"
    command_description = "Command only available in private chat"
    chat_type_allow = ChatType.PRIVATE

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        await self.send_text("This is a command only available in private chat")
        return True, "Private chat command executed", True

class GroupOnlyCommand(PlusCommand):
    command_name = "group"
    command_description = "Command only available in group chat"
    chat_type_allow = ChatType.GROUP

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        await self.send_text("This is a command only available in group chat")
        return True, "Group chat command executed", True
```

### 3. Configuration-Driven Command

```python
class ConfigurableCommand(PlusCommand):
    command_name = "config_cmd"
    command_description = "Configurable command"

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
        # Get settings from plugin configuration
        max_length = self.get_config("commands.max_length", 100)
        enabled_features = self.get_config("commands.features", [])
        
        if args.is_empty():
            await self.send_text("Please provide parameters")
            return True, "No parameters", True
            
        content = args.get_raw()
        if len(content) > max_length:
            await self.send_text(f"Content too long, maximum allowed {max_length} characters")
            return True, "Content too long", True
            
        # Decide functionality based on configuration
        if "uppercase" in enabled_features:
            content = content.upper()
            
        await self.send_text(f"Processing result: {content}")
        return True, "Config command executed", True
```

## Supported Command Prefixes

The system supports the following command prefixes (configured in `config/bot_config.toml`):

- `/` - Slash (default)
- `!` - Exclamation mark
- `.` - Period
- `#` - Hash

For example, for the echo command, all of the following calls are valid:
- `/echo Hello`
- `!echo Hello`
- `.echo Hello`
- `#echo Hello`

## Return Value Explanation

The `execute` method must return a triple:

```python
async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
    # ... Your logic ...
    return (success flag, log description, intercept message)
```

### Return Value Details

| Position | Type | Name | Explanation |
|------|------|------|------|
| 1 | `bool` | Success Flag | `True` = command executed successfully<br>`False` = command execution failed |
| 2 | `Optional[str]` | Log Description | Descriptive text for internal logging<br>⚠️ **NOT a message to send to the user!** |
| 3 | `bool` | Intercept Message | `True` = intercept, prevent subsequent processing (recommended)<br>`False` = don't intercept, continue processing |

### Important: Message Sending vs Log Description

⚠️ **Common Error: Returning user message in return value**

```python
# ❌ Wrong approach - Don't do this!
async def execute(self, args: CommandArgs):
    message = "Hello, this is a message to the user"
    return True, message, True  # This message won't be sent to the user!

# ✅ Correct approach - Use self.send_text()
async def execute(self, args: CommandArgs):
    await self.send_text("Hello, this is a message to the user")  # Send to user
    return True, "Executed greeting command", True  # Log description
```

### Complete Example

```python
async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]:
    """Complete example of execute method"""
    
    # 1. Parameter validation
    if args.is_empty():
        await self.send_text("⚠️ Please provide parameters")
        return True, "Missing parameters", True
    
    # 2. Execute logic
    user_input = args.get_raw()
    result = process_input(user_input)
    
    # 3. Send message to user
    await self.send_text(f"✅ Processing result: {result}")
    
    # 4. Return: success, log description, intercept message
    return True, f"Processed user input: {user_input[:20]}", True
```

### Intercept Flag Usage Guide

- **Return `True`** (recommended): Command processing complete, no subsequent processing needed (such as LLM reply)
- **Return `False`**: Allow system to continue processing (such as allowing LLM to also reply)

## Best Practices

### 1. Command Design
- ✅ **Command Naming**: Use short, intuitive command names (such as `time`, `help`, `status`)
- ✅ **Alias Setting**: Provide short aliases for common commands (such as `echo` -> `e`, `say`)
- ✅ **Chat Type**: Choose `ChatType.ALL`/`GROUP`/`PRIVATE` based on command functionality

### 2. Parameter Handling
- ✅ **Always Validate**: Use `args.is_empty()`, `args.count()` to check parameters
- ✅ **Friendly Prompts**: Provide clear usage instructions when parameters are wrong
- ✅ **Default Values**: Provide reasonable defaults for optional parameters

### 3. Message Sending
- ✅ **Use `self.send_text()`**: Send messages to users
- ❌ **Don't return user messages in return value**: Return value is log description
- ✅ **Intercept Messages**: Most cases return `True` as the third parameter

### 4. Error Handling
- ✅ **Try-Catch**: Catch and handle possible exceptions
- ✅ **Clear Feedback**: Tell users what went wrong
- ✅ **Log Recording**: Provide useful debugging information in return value

### 5. Configuration Management
- ✅ **Configurability**: Important settings should be read via `self.get_config()`
- ✅ **Default Values**: Works correctly even if configuration is missing

### 6. Code Quality
- ✅ **Type Annotations**: Use complete type hints
- ✅ **Docstrings**: Add documentation for `execute()` method
- ✅ **Code Comments**: Add necessary comments for complex logic

## Complete Example

See `plugins/echo_example/plugin.py` file for complete plugin example.

## Difference from Traditional BaseCommand

| Feature | PlusCommand | BaseCommand |
|------|-------------|-------------|
| Regular Expression | Auto-generated | Manual writing |
| Parameter Parsing | CommandArgs class | Manual handling |
| Alias Support | Built-in support | Need to handle in regex |
| Code Complexity | Simple | Complex |
| Learning Curve | Gentle | Steep |

The Enhanced Command System makes plugin development much simpler and more efficient, especially suitable for new developers to quickly get started.
