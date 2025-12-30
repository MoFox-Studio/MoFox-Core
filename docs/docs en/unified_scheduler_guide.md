# Unified Scheduler

## Overview

The unified scheduler is a general-purpose task scheduling system designed for MoFox Bot, primarily serving the plugin system. It provides a simple and powerful interface to create and manage various types of scheduled tasks.

### Core Features

- **Per-second check**: scheduler checks all tasks every second in the background, ensuring timely triggering
- **Three trigger types**: supports time-based, event-based, and custom condition triggers
- **Recurring and one-time**: supports both recurring and one-time tasks
- **Task management**: complete API for creating, removing, pausing, resuming, and force-triggering tasks
- **Thread-safe**: uses async locks for concurrent safety
- **Auto cleanup**: one-time tasks are automatically removed after execution
- **Event Manager integration**: direct integration with event_manager for efficient event triggering

### Auto-start

The unified scheduler is integrated into the main system, auto-starts when the bot starts, and auto-cleans when the bot shuts down. **No manual startup or shutdown needed**.

## Quick Start

### Basic usage

Since the scheduler auto-starts, you can use it directly:

```python
from src.schedule.unified_scheduler import unified_scheduler, TriggerType

async def my_callback():
    print("Task executed!")

# Create a task to execute after 5 seconds
schedule_id = await unified_scheduler.create_schedule(
    callback=my_callback,
    trigger_type=TriggerType.TIME,
    trigger_config={"delay_seconds": 5},
    task_name="My first task"
)
```

> **Tip**: For manual control, use `initialize_scheduler()` and `shutdown_scheduler()` functions.

## Trigger Types

### 1. Time-based (TIME)

Time-based triggers support two modes:

#### Delay
```python
# Execute once after 5 seconds
await unified_scheduler.create_schedule(
    callback=my_callback,
    trigger_type=TriggerType.TIME,
    trigger_config={"delay_seconds": 5},
    task_name="Delay task"
)

# Execute every 30 seconds (recurring)
await unified_scheduler.create_schedule(
    callback=my_callback,
    trigger_type=TriggerType.TIME,
    trigger_config={"delay_seconds": 30},
    is_recurring=True,
    task_name="Periodic task"
)
```

#### Trigger at specific time
```python
from datetime import datetime, timedelta

# Execute once at specified time
target_time = datetime.now() + timedelta(hours=1)
await unified_scheduler.create_schedule(
    callback=my_callback,
    trigger_type=TriggerType.TIME,
    trigger_config={"trigger_at": target_time},
    task_name="Scheduled task"
)

# Execute every day at fixed time (recurring)
await unified_scheduler.create_schedule(
    callback=my_callback,
    trigger_type=TriggerType.TIME,
    trigger_config={
        "trigger_at": target_time,
        "interval_seconds": 86400  # 24 hours
    },
    is_recurring=True,
    task_name="Daily task"
)
```

### 2. Event-based (EVENT)

Event-based triggers allow tasks to subscribe to specific events and execute automatically when events occur. **Event system is directly integrated with event_manager**, achieving zero-latency event notifications through efficient callbacks.

#### How it works

1. When creating an EVENT task, scheduler tracks that event
2. When `event_manager.trigger_event()` is called, event_manager **directly calls** scheduler's callback
3. Scheduler finds all tasks subscribed to that event and executes them immediately
4. No Handler middleware layer, higher efficiency

#### Create event listener

```python
from src.schedule.unified_scheduler import unified_scheduler, TriggerType

async def on_user_login(user_id: int, username: str):
    print(f"User logged in: {username} (ID: {user_id})")

# Subscribe to user_login event
schedule_id = await unified_scheduler.create_schedule(
    callback=on_user_login,
    trigger_type=TriggerType.EVENT,
    trigger_config={"event_name": "user_login"},
    is_recurring=True,  # Can be triggered multiple times
    task_name="Login listener"
)
```

#### Trigger event

**Important**: Event must be triggered through `event_manager`:

```python
from src.plugin_system.core.event_manager import event_manager

# Trigger event, all subscribed scheduler tasks will execute
await event_manager.trigger_event(
    "user_login",
    permission_group="SYSTEM",  # or plugin name
    user_id=123,
    username="Alice"
)
```

**Workflow**:
1. Call `event_manager.trigger_event("user_login", ...)`
2. Event manager detects scheduler callback is registered
3. Event manager **directly calls** scheduler's `_handle_event_trigger()` method
4. Scheduler finds all tasks subscribed to "user_login"
5. Immediately executes their callbacks, passing event parameters

**Parameters**:
- First param: event name (required)
- `permission_group`: for permission validation (optional, use "SYSTEM" for system events)
- Other params: passed as `**kwargs` to all subscribed callback functions

#### Automatic event management

- **Auto-track**: Scheduler auto-tracks events when EVENT tasks are created
- **Direct notify**: Event manager directly notifies scheduler when triggering, no middleware
- **Auto-cleanup**: Auto stops tracking when last task for an event is removed
- **Zero-latency**: Direct callback mechanism, nearly no delay from trigger to execution

### 3. Custom condition (CUSTOM)

Custom triggers allow you to provide a condition function, scheduler executes it every second, and triggers the task when it returns `True`.

```python
# Define condition function
def check_condition():
    # Can be any custom logic
    return some_variable > threshold

async def on_condition_met():
    print("Condition satisfied!")

# Create custom condition task
await unified_scheduler.create_schedule(
    callback=on_condition_met,
    trigger_type=TriggerType.CUSTOM,
    trigger_config={"condition_func": check_condition},
    task_name="Custom condition task"
)
```

⚠️ **Note**: Condition function executes every second, avoid expensive operations.

## Task Management API

### Remove task
```python
success = await unified_scheduler.remove_schedule(schedule_id)
```

### Pause task
```python
# Pause task (keep but don't trigger)
success = await unified_scheduler.pause_schedule(schedule_id)
```

### Resume task
```python
# Resume paused task
success = await unified_scheduler.resume_schedule(schedule_id)
```

### Force trigger task
```python
# Execute immediately (without waiting for condition)
success = await unified_scheduler.trigger_schedule(schedule_id)
```

### Get task info
```python
# Get detailed info of a single task
task_info = await unified_scheduler.get_task_info(schedule_id)
print(task_info)
# {
#     "schedule_id": "...",
#     "task_name": "...",
#     "trigger_type": "time",
#     "is_recurring": False,
#     "is_active": True,
#     "created_at": "2025-10-27T10:00:00",
#     "last_triggered_at": None,
#     "trigger_count": 0,
#     "trigger_config": {...}
# }
```

### List all tasks
```python
# List all tasks
all_tasks = await unified_scheduler.list_tasks()

# List tasks of specific type
time_tasks = await unified_scheduler.list_tasks(trigger_type=TriggerType.TIME)
```

### Get statistics
```python
stats = unified_scheduler.get_statistics()
print(stats)
# {
#     "is_running": True,
#     "total_tasks": 10,
#     "active_tasks": 8,
#     "paused_tasks": 2,
#     "recurring_tasks": 5,
#     "one_time_tasks": 5,
#     "tasks_by_type": {
#         "time": 6,
#         "event": 3,
#         "custom": 1
#     },
#     "registered_events": ["user_login", "message_received"]
# }
```

## Callbacks

### Sync and async callbacks
Scheduler supports both sync and async callbacks:

```python
# Async callback
async def async_callback():
    await some_async_operation()

# Sync callback
def sync_callback():
    print("Sync execution")

# Both can be used
await unified_scheduler.create_schedule(
    callback=async_callback,  # or sync_callback
    trigger_type=TriggerType.TIME,
    trigger_config={"delay_seconds": 5}
)
```

### Callback with parameters
```python
async def callback_with_params(user_id: int, message: str):
    print(f"User {user_id}: {message}")

# Pass params with callback_args and callback_kwargs
await unified_scheduler.create_schedule(
    callback=callback_with_params,
    trigger_type=TriggerType.TIME,
    trigger_config={"delay_seconds": 5},
    callback_args=(123,),
    callback_kwargs={"message": "Hello"}
)
```

## Using in Plugins

Typical pattern for using scheduler in plugins:

```python
from src.plugin_system.plugin_base import PluginBase
from src.schedule.unified_scheduler import TriggerType, unified_scheduler

class MyPlugin(PluginBase):
    def __init__(self):
        super().__init__(...)
        self.schedule_ids = []  # Save all task IDs
    
    async def on_enable(self):
        """Create tasks when plugin starts"""
        # Create periodic task
        id1 = await unified_scheduler.create_schedule(
            callback=self._my_task,
            trigger_type=TriggerType.TIME,
            trigger_config={"delay_seconds": 60},
            is_recurring=True,
            task_name=f"{self.meta.name}_periodic_task"
        )
        self.schedule_ids.append(id1)
        
        # Create event listener
        id2 = await unified_scheduler.create_schedule(
            callback=self._on_event,
            trigger_type=TriggerType.EVENT,
            trigger_config={"event_name": "my_event"},
            is_recurring=True,
            task_name=f"{self.meta.name}_event_listener"
        )
        self.schedule_ids.append(id2)
    
    async def on_disable(self):
        """Clean up tasks when plugin stops"""
        for schedule_id in self.schedule_ids:
            await unified_scheduler.remove_schedule(schedule_id)
        self.schedule_ids.clear()
    
    async def _my_task(self):
        """Periodic task callback"""
        self.logger.info("Execute periodic task")
    
    async def _on_event(self, **event_params):
        """Event callback"""
        self.logger.info(f"Received event: {event_params}")
```

### Best Practices

1. **Naming convention**: Use plugin name as task name prefix for easy identification
   ```python
   task_name=f"{self.meta.name}_task_description"
   ```

2. **Save IDs**: Keep all created `schedule_id` in plugin for management
   ```python
   self.schedule_ids = []
   self.schedule_ids.append(schedule_id)
   ```

3. **Timely cleanup**: Remove all tasks in `on_disable()` to avoid memory leaks
   ```python
   async def on_disable(self):
       for sid in self.schedule_ids:
           await unified_scheduler.remove_schedule(sid)
       self.schedule_ids.clear()
   ```

4. **Exception handling**: Handle exceptions in callbacks to avoid affecting scheduler
   ```python
   async def my_callback(self):
       try:
           # Task logic
           pass
       except Exception as e:
           self.logger.error(f"Task failed: {e}")
   ```

5. **Performance considerations**: 
   - CUSTOM condition functions execute every second, avoid expensive operations
   - Prefer EVENT type over frequent condition checks
   - Event triggering uses direct callbacks, most efficient

6. **Event naming**: Use clear event names to avoid conflicts
   ```python
   event_name = f"{self.meta.name}_custom_event"
   ```

## Use Case Examples

### Timed reminder
```python
async def send_reminder():
    await send_message("Time to drink water!")

# Remind every hour
await unified_scheduler.create_schedule(
    callback=send_reminder,
    trigger_type=TriggerType.TIME,
    trigger_config={"delay_seconds": 3600},
    is_recurring=True,
    task_name="Water reminder"
)
```

### Listen to message events
```python
from src.plugin_system.core.event_manager import event_manager
from src.schedule.unified_scheduler import unified_scheduler, TriggerType

async def on_new_message(content: str, sender: str):
    # Handle new message
    print(f"Message from {sender}: {content}")

# Subscribe to message event
await unified_scheduler.create_schedule(
    callback=on_new_message,
    trigger_type=TriggerType.EVENT,
    trigger_config={"event_name": "new_message"},
    is_recurring=True,
    task_name="Message handler"
)

# Trigger event elsewhere (via event_manager)
await event_manager.trigger_event(
    "new_message",
    permission_group="SYSTEM",
    content="Hello!",
    sender="User A"
)
```

> **Note**: Events must be triggered via `event_manager.trigger_event()` to trigger scheduler tasks.

### Condition monitoring
```python
import os

def check_file_exists():
    return os.path.exists("/tmp/signal.txt")

async def on_file_created():
    print("Signal file detected!")
    os.remove("/tmp/signal.txt")

# Monitor file creation
await unified_scheduler.create_schedule(
    callback=on_file_created,
    trigger_type=TriggerType.CUSTOM,
    trigger_config={"condition_func": check_file_exists},
    task_name="File monitor"
)
```

### Daily summary
```python
from datetime import datetime, time, timedelta

async def daily_summary():
    # 生成每日总结
    summary = generate_summary()
    await send_message(summary)

# 每天晚上10点执行
now = datetime.now()
target = datetime.combine(now.date(), time(22, 0))
if target <= now:
    target += timedelta(days=1)

await unified_scheduler.create_schedule(
    callback=daily_summary,
    trigger_type=TriggerType.TIME,
    trigger_config={
        "trigger_at": target,
        "interval_seconds": 86400  # 24小时
    },
    is_recurring=True,
    task_name="每日总结"
)
```

## 示例代码

完整的示例代码可以在以下文件中找到：

- `examples/unified_scheduler_example.py` - 基础使用示例
- `examples/plugin_scheduler_integration.py` - 插件集成示例
- `examples/test_scheduler_direct_integration.py` - Event Manager 直接集成测试

运行示例：
```bash
# 基础示例
python examples/unified_scheduler_example.py

# 直接集成测试
python examples/test_scheduler_direct_integration.py
```

## 注意事项

1. **自动启动**: 调度器在 Bot 启动时自动启动，无需手动调用 `start()`
2. **自动清理**: Bot 关闭时会自动清理调度器，但插件仍需清理自己的任务
3. **任务清理**: 插件或模块不再使用时，**必须**移除创建的任务，避免内存泄漏
4. **异常处理**: 回调函数中的异常会被捕获并记录，但不会中断调度器运行
5. **Performance impact**: 
   - Many CUSTOM tasks affect performance, prefer EVENT type
   - EVENT type uses direct callbacks, almost no overhead
6. **Timezone**: All times use system local time
7. **Event triggering**: Must use `event_manager.trigger_event()` to trigger event tasks, direct scheduler method calls won't trigger event tasks

## API Reference

### UnifiedScheduler

#### Methods

- `start()` - Start scheduler (usually called automatically)
- `stop()` - Stop scheduler (usually called automatically)
- `create_schedule(...)` - Create schedule task
- `remove_schedule(schedule_id)` - Remove task
- `trigger_schedule(schedule_id)` - Force trigger task
- `pause_schedule(schedule_id)` - Pause task
- `resume_schedule(schedule_id)` - Resume task
- `get_task_info(schedule_id)` - Get task info
- `list_tasks(trigger_type=None)` - List tasks
- `get_statistics()` - Get statistics

#### Convenience functions

- `initialize_scheduler()` - Initialize and start scheduler (called at bot startup)
- `shutdown_scheduler()` - Shut down scheduler and clean resources (called at bot shutdown)

### TriggerType

Trigger type enum:

- `TriggerType.TIME` - Time-based trigger
- `TriggerType.EVENT` - Event-based trigger
- `TriggerType.CUSTOM` - Custom condition trigger

## Troubleshooting

### Task not executing

1. Check if scheduler is running: `unified_scheduler.get_statistics()["is_running"]`
2. Check if task is paused: see `task_info["is_active"]`
3. Verify trigger conditions are configured correctly
4. For EVENT type, confirm event is triggered via `event_manager.trigger_event()`
5. Check logs for exceptions

### Event task not triggering

1. Confirm using `event_manager.trigger_event()` not other methods
2. Check event name matches (case-sensitive)
3. Check task's `is_recurring` setting (one-time tasks auto-remove after execution)
4. Use `get_statistics()` to check `registered_events` list

### Performance issues

1. Check count and complexity of CUSTOM tasks
2. Reduce execution time of condition functions
3. Consider using EVENT type instead of frequent condition checks (EVENT uses direct callbacks, almost no overhead)

### Memory leaks

1. Ensure plugin removes all tasks on unload
2. Check if tasks reference resources no longer needed
3. Use `list_tasks()` to check for orphaned tasks
4. Check `registered_events` decreases as tasks are cleaned

## Changelog

### v1.1.0 (2025-10-28)
- Removed SchedulerEventHandler middleware layer
- Performance optimization: Event Manager direct callback, zero-latency event notification
- Architecture simplification: ~180 lines less code, clearer logic
- Auto-integrated into main system, auto-start and shutdown
- Simplified event subscription API

### v1.0.0 (2025-10-27)
- Initial release
- Supports three trigger types (TIME, EVENT, CUSTOM)
- Supports recurring and one-time tasks
- Complete task management API
- Thread-safe async implementation

## License

This module is part of MoFox Bot project, follows project license.
