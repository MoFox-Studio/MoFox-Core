# 故障排除指南 (Troubleshooting Guide)

This is the English version of the troubleshooting guide. The comprehensive guide can be found at the original location.

## Quick Reference

For the most common issues encountered during plugin development:

### Plugin Won't Load
- Check that `_manifest.json` exists and is valid JSON
- Ensure plugin directory has `plugin.py` with `@register_plugin` decorator
- Check logs in `logs/app_*.jsonl` for detailed error information

### Command Not Responding
- Use `PlusCommand` instead of `BaseCommand`
- Ensure `execute(self, args: CommandArgs)` method signature is correct
- Check that you're using `await self.send_text()` to send messages
- Don't return user messages in the return value - return (True, "log description", True)

### Action Not Triggering
- Check `action_name` and `action_description` are set
- Verify `go_activate()` or `activation_type` is configured correctly
- Ensure `async def execute(self)` is implemented with return (bool, str)
- Check `associated_types` matches what the plugin can send

### Configuration Issues
- Don't manually create `config.toml` - let the system auto-generate based on `config_schema`
- Use `self.get_config("section.key", default_value)` to read configuration
- For missing config error, check logs - it usually means config fallback is working normally

### Return Value Errors

**Action must return 2 elements:**
```python
return True, "log description"  # Correct
```

**Command must return 3 elements:**
```python
return True, "log description", True  # Correct
```

---

## Common Errors and Solutions

### Error: "ActionInfo.__init__() missing required argument: 'component_type'"

**Solution:** Use `get_action_info()` instead of manually creating ActionInfo:
```python
# ❌ Wrong
action_info = ActionInfo(name="test", description="test")

# ✅ Correct
(TestAction.get_action_info(), TestAction)
```

### Error: "Plugin not loading"

**Checklist:**
1. ✅ `_manifest.json` exists in plugin directory
2. ✅ `plugin.py` exists with `@register_plugin` decorator
3. ✅ `plugin_name` attribute is unique
4. ✅ `get_plugin_components()` returns proper list

### Error: "Command executed but user got no message"

**Solution:** Use `self.send_text()` to send messages, not return value:
```python
# ❌ Wrong
return True, "user message", True

# ✅ Correct
await self.send_text("user message")
return True, "log message", True
```

---

## Best Practices

- ✅ Always use type hints
- ✅ Use `PlusCommand` for all commands
- ✅ Let config system auto-generate `config.toml`
- ✅ Use `await self.send_text()` for messages
- ✅ Return 2 elements for Action, 3 for Command
- ✅ Check logs when things don't work

---

For detailed troubleshooting guide, see the original Chinese documentation at `docs/plugins/troubleshooting-guide.md`.
