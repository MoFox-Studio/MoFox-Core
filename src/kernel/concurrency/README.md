# MoFox Concurrency 并发模块

MoFox 的异步任务管理和监控系统，提供强大的任务调度、依赖管理、超时监控和日志集成功能。

## 特性

- 🎯 **任务管理**：统一的异步任务调度和执行
- 🔄 **优先级队列**：支持任务优先级排序
- 📊 **依赖管理**：任务间依赖关系处理
- ⏱️ **超时监控**：Watchdog 全局任务监控
- 🔁 **重试机制**：自动重试失败的任务
- 🎛️ **并发控制**：限制最大并发任务数
- 📝 **日志集成**：与 Logger 模块深度集成，自动记录任务生命周期
- 📈 **统计报告**：任务执行统计和性能分析

## 模块结构

```
kernel/concurrency/
├── task_manager.py              # TaskManager 向后兼容层
├── watchdog.py                  # Watchdog 全局任务监控器
└── task_manager/
    ├── __init__.py
    ├── models.py                # 任务模型和配置
    ├── manager.py               # TaskManager 核心实现
    ├── scheduler.py             # 任务调度器
    ├── executor.py              # 任务执行器
    ├── dependency.py            # 依赖管理器
    └── callbacks.py             # 回调管理器
```

## 快速开始

### 1. 基本任务提交

```python
from kernel.concurrency import get_task_manager

# 获取任务管理器实例（单例）
tm = get_task_manager()

# 启动任务管理器
await tm.start()

# 定义异步任务
async def my_task(name: str):
    await asyncio.sleep(1)
    return f"Hello, {name}!"

# 提交任务
task_id = tm.submit_task(my_task, "Alice")

# 等待任务完成
result = await tm.wait_for_task(task_id)
print(result)  # "Hello, Alice!"

# 停止任务管理器
await tm.stop()
```

### 2. 带配置的任务

```python
from kernel.concurrency import TaskConfig, TaskPriority

# 创建任务配置
config = TaskConfig(
    priority=TaskPriority.HIGH,      # 高优先级
    timeout=10.0,                     # 10秒超时
    max_retries=3,                    # 最多重试3次
    retry_delay=1.0                   # 重试延迟1秒
)

# 提交任务
task_id = tm.submit_task(
    my_task,
    "Bob",
    name="重要任务",
    config=config
)
```

### 3. 任务依赖关系

```python
# 任务A：数据准备
task_a = tm.submit_task(prepare_data, name="准备数据")

# 任务B：依赖任务A
config_b = TaskConfig(dependencies=[task_a])
task_b = tm.submit_task(
    process_data,
    name="处理数据",
    config=config_b
)

# 任务C：依赖任务B
config_c = TaskConfig(dependencies=[task_b])
task_c = tm.submit_task(
    save_results,
    name="保存结果",
    config=config_c
)

# 等待最终任务完成
await tm.wait_for_task(task_c)
```

### 4. 使用 Watchdog 监控

```python
from kernel.concurrency import get_watchdog

# 获取 Watchdog 实例（单例）
watchdog = get_watchdog()

# 启动 Watchdog
await watchdog.start()

# 创建并注册任务到 Watchdog
async def long_running_task():
    await asyncio.sleep(100)

task = asyncio.create_task(long_running_task())
watchdog_id = watchdog.register_task(
    task,
    name="长时间任务",
    timeout=30.0  # 30秒超时
)

# Watchdog 会自动监控并在超时时触发回调

# 停止 Watchdog
await watchdog.stop()
```

## 日志集成

并发模块已与 Logger 模块深度集成，所有任务生命周期事件都会自动记录：

### 自动记录的事件

- ✅ 任务提交：记录任务ID、优先级、配置
- ✅ 任务开始：记录开始时间、任务元数据
- ✅ 任务完成：记录执行时长、结果类型
- ✅ 任务失败：记录错误类型、错误信息、堆栈跟踪
- ✅ 任务重试：记录重试次数、延迟时间
- ✅ 任务超时：记录超时时间、实际运行时长
- ✅ 任务取消：记录取消原因

### 日志元数据

每条任务相关的日志都包含以下元数据：

```python
{
    "task_id": "task_123_1234567890",
    "task_name": "我的任务",
    "level": "INFO",
    "message": "任务完成",
    "timestamp": "2026-01-06T10:30:45",
    "duration": 1.23,
    "priority": "NORMAL",
    "retry_count": 0
}
```

### 查询任务日志

```python
from kernel.logger.storage_integration import LoggerWithStorage

# 如果使用了 Logger-Storage 集成
logger_system = LoggerWithStorage(app_name="myapp")

# 查询特定任务的日志
from datetime import datetime, timedelta

logs = logger_system.log_store.get_logs(
    start_date=datetime.now() - timedelta(days=1),
    filter_func=lambda log: log.get('task_id') == task_id
)

for log in logs:
    print(f"{log['timestamp']}: {log['message']}")
```

### 查询失败的任务

```python
# 获取所有任务失败的日志
error_logs = logger_system.get_error_logs(days=7)

# 分析失败原因
from collections import Counter
error_types = Counter(
    log.get('error_type', 'Unknown')
    for log in error_logs
    if 'task_id' in log
)

print("任务失败统计:")
for error_type, count in error_types.most_common():
    print(f"  {error_type}: {count}次")
```

## 配置详解

### TaskManager 参数

```python
from kernel.concurrency import TaskManager

tm = TaskManager(
    max_concurrent_tasks=10,          # 最大并发任务数
    enable_watchdog=True,             # 启用 Watchdog 监控
    watchdog_check_interval=1.0       # Watchdog 检查间隔（秒）
)
```

### TaskConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `priority` | TaskPriority | NORMAL | 任务优先级 |
| `timeout` | float | None | 超时时间（秒） |
| `max_retries` | int | 0 | 最大重试次数 |
| `retry_delay` | float | 1.0 | 重试延迟（秒） |
| `dependencies` | List[str] | [] | 依赖的任务ID列表 |

### TaskPriority 枚举

```python
from kernel.concurrency import TaskPriority

TaskPriority.LOW      # 低优先级
TaskPriority.NORMAL   # 普通优先级（默认）
TaskPriority.HIGH     # 高优先级
TaskPriority.URGENT   # 紧急优先级
```

### TaskState 枚举

```python
from kernel.concurrency import TaskState

TaskState.PENDING     # 待处理
TaskState.QUEUED      # 已入队
TaskState.WAITING     # 等待依赖
TaskState.RUNNING     # 运行中
TaskState.RETRYING    # 重试中
TaskState.COMPLETED   # 已完成
TaskState.FAILED      # 失败
TaskState.CANCELLED   # 已取消
```

## 高级功能

### 1. 回调函数

```python
# 任务完成回调
def on_complete(task):
    print(f"任务完成: {task.name}")

# 任务失败回调
def on_failed(task):
    print(f"任务失败: {task.name}, 错误: {task.error}")

# 添加回调
tm.add_complete_callback(on_complete)
tm.add_failed_callback(on_failed)
```

### 2. 取消任务

```python
# 提交任务
task_id = tm.submit_task(my_task, "Charlie")

# 取消任务
cancelled = await tm.cancel_task(task_id)

if cancelled:
    print("任务已取消")
```

### 3. 获取任务状态

```python
# 获取任务信息
task_info = tm.get_task(task_id)

if task_info:
    print(f"任务状态: {task_info.state.name}")
    print(f"任务名称: {task_info.name}")
    print(f"运行时长: {task_info.duration:.2f}秒")
```

### 4. 统计信息

```python
# 获取 TaskManager 统计
stats = tm.get_stats()
print(f"总提交任务: {stats['total_submitted']}")
print(f"已完成: {stats['total_completed']}")
print(f"失败: {stats['total_failed']}")
print(f"运行中: {stats['total_running']}")

# 获取 Watchdog 统计
watchdog = get_watchdog()
watchdog_stats = watchdog.get_stats()
print(f"监控任务数: {watchdog_stats['current_tracked']}")
print(f"超时任务: {watchdog_stats['total_timeout']}")
```

### 5. 批量任务提交

```python
# 批量提交任务
task_ids = []
for i in range(10):
    task_id = tm.submit_task(
        process_item,
        i,
        name=f"任务-{i}"
    )
    task_ids.append(task_id)

# 等待所有任务完成
results = await asyncio.gather(*[
    tm.wait_for_task(tid) for tid in task_ids
])
```

### 6. 超时自动取消

```python
# 启用超时自动取消
tm.auto_cancel_on_timeout = True

# 提交一个会超时的任务
config = TaskConfig(timeout=5.0)
task_id = tm.submit_task(
    slow_task,
    config=config
)

# 如果任务超过5秒，会被自动取消
```

## 完整示例

### 数据处理管道

```python
import asyncio
from kernel.concurrency import get_task_manager, TaskConfig, TaskPriority
from kernel.logger.storage_integration import LoggerWithStorage

async def main():
    # 初始化日志系统
    logger_system = LoggerWithStorage(app_name="data_pipeline")
    
    # 初始化任务管理器
    tm = get_task_manager()
    await tm.start()
    
    try:
        # 阶段1：数据获取（高优先级）
        fetch_config = TaskConfig(
            priority=TaskPriority.HIGH,
            timeout=30.0,
            max_retries=3
        )
        task_fetch = tm.submit_task(
            fetch_data,
            name="获取数据",
            config=fetch_config
        )
        
        # 阶段2：数据处理（依赖阶段1）
        process_config = TaskConfig(
            dependencies=[task_fetch],
            timeout=60.0
        )
        task_process = tm.submit_task(
            process_data,
            name="处理数据",
            config=process_config
        )
        
        # 阶段3：数据保存（依赖阶段2）
        save_config = TaskConfig(
            dependencies=[task_process],
            timeout=20.0,
            max_retries=2
        )
        task_save = tm.submit_task(
            save_data,
            name="保存数据",
            config=save_config
        )
        
        # 等待管道完成
        result = await tm.wait_for_task(task_save, timeout=120.0)
        print(f"管道完成，结果: {result}")
        
        # 查看统计
        stats = tm.get_stats()
        print(f"\n任务统计:")
        print(f"  完成: {stats['total_completed']}")
        print(f"  失败: {stats['total_failed']}")
        print(f"  重试: {stats['total_retries']}")
        
        # 查询日志
        logs = logger_system.get_logs(days=1)
        print(f"\n日志统计: {logs}")
        
    finally:
        # 清理
        await tm.stop()

# 任务函数
async def fetch_data():
    await asyncio.sleep(2)
    return {"data": [1, 2, 3, 4, 5]}

async def process_data():
    await asyncio.sleep(3)
    return {"processed": True}

async def save_data():
    await asyncio.sleep(1)
    return {"saved": True}

if __name__ == "__main__":
    asyncio.run(main())
```

## 最佳实践

### 1. 合理设置超时

```python
# 根据任务类型设置合适的超时时间
quick_config = TaskConfig(timeout=5.0)      # 快速任务
normal_config = TaskConfig(timeout=30.0)    # 普通任务
long_config = TaskConfig(timeout=300.0)     # 长时间任务
```

### 2. 使用优先级

```python
# 紧急任务使用 URGENT 优先级
urgent_config = TaskConfig(priority=TaskPriority.URGENT)

# 后台任务使用 LOW 优先级
background_config = TaskConfig(priority=TaskPriority.LOW)
```

### 3. 合理配置重试

```python
# 网络请求任务：多次重试
network_config = TaskConfig(
    max_retries=5,
    retry_delay=2.0
)

# 数据库操作：少量重试
db_config = TaskConfig(
    max_retries=2,
    retry_delay=0.5
)

# 幂等操作：可以安全重试
# 非幂等操作：不要重试或谨慎重试
```

### 4. 控制并发数

```python
# 根据系统资源调整最大并发数
tm = TaskManager(max_concurrent_tasks=20)  # 高性能服务器
tm = TaskManager(max_concurrent_tasks=5)   # 资源受限环境
```

### 5. 依赖关系设计

```python
# 避免循环依赖
# ❌ 错误：A -> B -> C -> A

# ✅ 正确：A -> B -> C
task_a = tm.submit_task(task_a_func)
task_b = tm.submit_task(task_b_func, config=TaskConfig(dependencies=[task_a]))
task_c = tm.submit_task(task_c_func, config=TaskConfig(dependencies=[task_b]))
```

### 6. 使用元数据追踪

```python
from kernel.logger import MetadataContext

# 在任务中设置元数据
async def my_task(user_id: str):
    from kernel.logger import LogMetadata
    LogMetadata.set_user_id(user_id)
    
    # 任务执行...
    return result
```

### 7. 定期清理日志

```python
# 定期清理旧日志
logger_system.cleanup_old_logs(days=30)

# 或使用定时任务
import schedule

schedule.every().day.at("03:00").do(
    lambda: logger_system.cleanup_old_logs(days=30)
)
```

## 故障排查

### 问题：任务一直处于 WAITING 状态

**原因**：依赖的任务未完成或失败

**解决**：
```python
# 检查依赖任务状态
task = tm.get_task(task_id)
for dep_id in task.config.dependencies:
    dep_task = tm.get_task(dep_id)
    print(f"依赖任务 {dep_id}: {dep_task.state.name}")
```

### 问题：任务超时但未取消

**原因**：`auto_cancel_on_timeout` 设置为 False

**解决**：
```python
# 启用超时自动取消
tm.auto_cancel_on_timeout = True
```

### 问题：日志未记录

**原因**：Logger 未正确初始化

**解决**：
```python
from kernel.logger import setup_logger

# 初始化 Logger
setup_logger()

# 或使用 Storage 集成
from kernel.logger.storage_integration import LoggerWithStorage
logger_system = LoggerWithStorage(app_name="myapp")
```

### 问题：任务执行过慢

**分析**：
```python
# 查看统计信息
stats = tm.get_stats()
print(f"当前运行任务: {stats['total_running']}")
print(f"队列中任务: len of queue")

# 查看 Watchdog 监控
watchdog_stats = watchdog.get_stats()
print(f"监控任务: {watchdog_stats['current_tracked']}")
```

**优化**：
- 增加 `max_concurrent_tasks`
- 检查任务是否有阻塞操作
- 使用异步 I/O 替代同步 I/O

## API 参考

### TaskManager

```python
class TaskManager:
    def __init__(
        self,
        max_concurrent_tasks: int = 10,
        enable_watchdog: bool = True,
        watchdog_check_interval: float = 1.0
    )
    
    async def start() -> None
    async def stop(cancel_running_tasks: bool = False) -> None
    
    def submit_task(
        self,
        coro: Callable,
        *args,
        name: Optional[str] = None,
        config: Optional[TaskConfig] = None,
        **kwargs
    ) -> str
    
    async def cancel_task(task_id: str) -> bool
    async def wait_for_task(task_id: str, timeout: Optional[float] = None) -> Any
    
    def get_task(task_id: str) -> Optional[ManagedTask]
    def get_all_tasks() -> Dict[str, ManagedTask]
    def get_stats() -> Dict[str, Any]
```

### Watchdog

```python
class Watchdog:
    async def start() -> None
    async def stop() -> None
    
    def register_task(
        self,
        task: asyncio.Task,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> str
    
    def unregister_task(task_id: str) -> bool
    def get_task_info(task_id: str) -> Optional[TaskInfo]
    def get_stats() -> Dict[str, Any]
    
    def add_timeout_callback(callback: Callable) -> None
    def add_error_callback(callback: Callable) -> None
    def add_complete_callback(callback: Callable) -> None
```

## 相关文档

- 📖 [Logger 模块文档](../logger/README.md)
- 📖 [Logger-Storage 集成指南](../../docs/kernel/logger/LOGGER_STORAGE_INTEGRATION.md)
- 🚀 [Logger 快速参考](../../docs/kernel/logger/QUICK_REFERENCE.md)
- 📖 [Storage 模块文档](../storage/README.md)
- 📖 [TaskManager 重构总结](../../docs/kernel/concurrency/TASK_MANAGER_REFACTOR_SUMMARY.md)
- 📖 [Watchdog 文档](../../docs/kernel/concurrency/watchdog.md)

## 贡献

欢迎提交 Issue 和 Pull Request！
