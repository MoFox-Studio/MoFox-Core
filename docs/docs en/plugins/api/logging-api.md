# Logging API

Application logging.

```python
from src.plugin_system import get_logger
```

## Usage
```python
logger = get_logger("module_name")

# Log levels
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")

# With context
logger.info("User %s performed action", user_id)

# With exception
try:
    risky_operation()
except Exception as e:
    logger.exception("Operation failed: %s", e)
```

## Best Practices
✅ Use module name as logger name
✅ Use appropriate log levels
✅ Include context in messages
✅ Log exceptions with traceback
❌ Don't log sensitive data
❌ Don't use print() for logs
