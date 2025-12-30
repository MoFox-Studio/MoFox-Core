# Slow Query Monitoring Quick Reference

## Enable Fast

### Config (recommended)

```toml
# config/bot_config.toml
[database]
enable_slow_query_logging = true
slow_query_threshold = 0.5  # seconds
```

### In code

```python
from src.common.database.utils import enable_slow_query_monitoring, disable_slow_query_monitoring

enable_slow_query_monitoring()

# ... your code ...

disable_slow_query_monitoring()
```

### Check status

```python
from src.common.database.utils import is_slow_query_monitoring_enabled

if is_slow_query_monitoring_enabled():
    print("Enabled")
else:
    print("Disabled")
```

---

## Key Commands

```python
from src.common.database.utils import (
    enable_slow_query_monitoring,
    disable_slow_query_monitoring,
    is_slow_query_monitoring_enabled,
    get_slow_queries,
    get_slow_query_report,
)

enable_slow_query_monitoring()
disable_slow_query_monitoring()
is_slow_query_monitoring_enabled()

queries = get_slow_queries(limit=20)
report = get_slow_query_report()

from src.common.database.utils.slow_query_analyzer import SlowQueryAnalyzer

SlowQueryAnalyzer.generate_html_report("report.html")
text = SlowQueryAnalyzer.generate_text_report()
```

---

## Suggested Config

```toml
# Production (default)
enable_slow_query_logging = false

# Test
enable_slow_query_logging = true
slow_query_threshold = 0.5

# Dev
enable_slow_query_logging = true
slow_query_threshold = 0.1
```

---

## Example

```python
enable_slow_query_monitoring()

@measure_time()
async def slow_operation():
    return await db.query(...)

report = get_slow_query_report()
print(f"Total slow: {report['total']}")

disable_slow_query_monitoring()
```

---

## Performance

| State | CPU | Memory |
| ----- | --- | ------ |
| Enabled | < 0.1% | ~50 KB |
| Disabled | ~0% | 0 KB |

---

## Core Points

- Off by default, zero cost
- Toggle on/off as needed
- Warns in real time when over threshold
- Detailed report on shutdown when enabled
- No overhead when disabled

---

Enable: enable_slow_query_monitoring()
Disable: disable_slow_query_monitoring()
Report: get_slow_query_report()

More: docs/slow_query_monitoring_guide.md
