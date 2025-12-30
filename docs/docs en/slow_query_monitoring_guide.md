# Slow Query Monitoring Guide

## Overview

The slow query monitoring system is fully implemented:
- Slow query detection and collection (disabled by default)
- Real-time performance stats
- Text and HTML report generation
- Optimization hints and analysis
- User-controlled enable/disable switch

## Quick Enable

### Option 1: Config (recommended)

Edit `config/bot_config.toml`:

```toml
[database]
enable_slow_query_logging = true
slow_query_threshold = 0.5  # seconds
```

### Option 2: Enable in code

```python
from src.common.database.utils import enable_slow_query_monitoring, disable_slow_query_monitoring, is_slow_query_monitoring_enabled

enable_slow_query_monitoring()

disable_slow_query_monitoring()

if is_slow_query_monitoring_enabled():
    print("Slow query monitoring is on")
```

## Configuration

### bot_config.toml

```toml
[database]
enable_slow_query_logging = false
slow_query_threshold = 0.5
query_timeout = 30
collect_slow_queries = true
slow_query_buffer_size = 100
```

Recommended presets:
- Production: `enable_slow_query_logging = false` (minimal overhead)
- Test: `enable_slow_query_logging = true`, `slow_query_threshold = 0.5`
- Dev: `enable_slow_query_logging = true`, `slow_query_threshold = 0.1` (catch everything)

## How To Use

### 1) Automatic monitoring (recommended)

```python
from src.common.database.utils import measure_time

@measure_time()
async def my_database_query():
    return result

@measure_time(log_slow=1.0)
async def another_query():
    return result
```

### 2) Manual recording

```python
from src.common.database.utils import record_slow_query

record_slow_query(
    operation_name="custom_query",
    execution_time=1.5,
    sql="SELECT * FROM users WHERE id = ?",
    args=(123,)
)
```

### 3) Fetch reports

```python
from src.common.database.utils import get_slow_query_report

report = get_slow_query_report()

print(f"Total slow queries: {report['total']}")
print(f"Threshold: {report['threshold']}")

for op in report['top_operations']:
    print(f"{op['operation']}: {op['count']}")
```

### 4) Analyzer helpers

```python
from src.common.database.utils.slow_query_analyzer import SlowQueryAnalyzer

text_report = SlowQueryAnalyzer.generate_text_report()
print(text_report)

SlowQueryAnalyzer.generate_html_report("reports/slow_query.html")

slowest = SlowQueryAnalyzer.get_slowest_queries(limit=20)
for query in slowest:
    print(f"{query.operation_name}: {query.execution_time:.3f}s")
```

## Sample Output

### Init when enabled

```
Slow query monitoring enabled (threshold: 0.5s, buffer: 100)
```

### Runtime warning

```
get_user_by_id is slow: 0.752s (threshold: 0.500s)
```

### Shutdown report (only when enabled)

```
============================================================
Database Performance Stats
============================================================

Operations:
  get_user_by_id: count=156, avg=0.025s, min=0.001s, max=1.203s, errors=0, slow=3

Cache:
  hits=8923, misses=1237, hit_rate=87.82%

Overall:
  error_rate=0.00%
  slow_queries=3
  slow_threshold=0.500s

Slow Query Report:
  Top 10 by operation:
    1. get_user_by_id: count=3, avg=0.752s, max=1.203s
```

## FAQ

### Check if enabled

```python
from src.common.database.utils import is_slow_query_monitoring_enabled

if is_slow_query_monitoring_enabled():
    print("Enabled")
else:
    print("Disabled")
```

### Temporarily enable/disable

```python
from src.common.database.utils import enable_slow_query_monitoring, disable_slow_query_monitoring

enable_slow_query_monitoring()

# ... run monitored code ...

disable_slow_query_monitoring()
```

### Performance when off

No overhead when disabled.

### Persistence

Data is in-memory (last 100 by default); a report prints on shutdown when enabled.

## Best Practices

### Production

```toml
[database]
enable_slow_query_logging = false
```

Enable temporarily only when debugging performance:

```python
from src.common.database.utils import enable_slow_query_monitoring, disable_slow_query_monitoring

enable_slow_query_monitoring()
# Run the workload
disable_slow_query_monitoring()
```

### Dev/Test

```toml
[database]
enable_slow_query_logging = true
slow_query_threshold = 0.5
```

### Decorator usage

```python
@measure_time()
async def get_user_info(user_id: str):
    return await user_crud.get_by_id(user_id)
```

## Technical Notes

### Core components

| File | Responsibility |
| ---- | -------------- |
| `monitoring.py` | Monitor enable/disable logic |
| `decorators.py` | `@measure_time()` decorator |
| `slow_query_analyzer.py` | Analysis and reports |

### Enable flow

```
enable_slow_query_logging = true
           ↓
main.py: set_slow_query_config()
           ↓
get_monitor().enable()
           ↓
is_enabled() = True
           ↓
record_operation() logs slow queries
           ↓
Warning output
```

### Disable flow

```
enable_slow_query_logging = false
           ↓
is_enabled() = False
           ↓
record_operation() skips logging
           ↓
No overhead
```

## Performance Impact

### Enabled

- CPU: < 0.1% (only on threshold breach)
- Memory: ~50 KB (buffer 100 entries)

### Disabled

- CPU: ~0%
- Memory: 0 KB

Conclusion: safe to keep off in production; turn on when needed.

## Next Steps

1. Auto-enable when performance issues detected
2. Alerts when slow query ratio crosses thresholds
3. Prometheus metrics export
4. Grafana dashboards

---

Updated: 2025-12-17  
Status: Off by default, opt-in by user
