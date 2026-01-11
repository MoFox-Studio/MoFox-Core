# TaskManager 使用指南

## 概述

`TaskManager` 是一个功能完善的异步任务管理器，与 `Watchdog` 配合使用，提供任务的创建、执行、监控和生命周期管理。

## 主要特性

1. **任务调度与执行**
   - 异步任务提交和执行
   - 优先级队列管理
   - 并发控制

2. **依赖管理**
   - 任务间依赖关系
   - 依赖失败传播
   - 自动依赖检查

3. **容错机制**
   - 自动重试
   - 可配置重试次数和延迟
   - 错误回调

4. **监控集成**
   - 与 Watchdog 深度集成
   - 超时检测
   - 任务状态追踪

5. **生命周期管理**
   - 任务状态机
   - 优雅关闭
   - 资源清理

## 快速开始

### 1. 基本使用

```python
import asyncio
from kernel.concurrency.task_manager import TaskManager

async def main():
    # 创建任务管理器
    manager = TaskManager(max_concurrent_tasks=10)
    await manager.start()
    
    # 定义任务
    async def my_task(x, y):
        await asyncio.sleep(1)
        return x + y
    
    # 提交任务
    task_id = manager.submit_task(my_task, 10, 20, name="Addition")
    
    # 等待任务完成
    result = await manager.wait_for_task(task_id)
    print(f"Result: {result}")  # Output: Result: 30
    
    # 停止管理器
    await manager.stop()

asyncio.run(main())
```

### 2. 使用全局实例

```python
from kernel.concurrency.task_manager import get_task_manager

async def main():
    # 获取全局实例
    manager = get_task_manager(max_concurrent_tasks=10)
    await manager.start()
    
    # 使用管理器...
    
    await manager.stop()
```

    > 统计说明：`total_completed` 采用动态统计（基于任务终态），避免在重试或多次回调场景下出现重复计数；统计值不会超过提交总数。
## 高级功能

### 1. 任务优先级

```python
from kernel.concurrency.task_manager import TaskConfig, TaskPriority

async def critical_task():
    ```

    ## 全局实例与测试隔离

    - 包级全局实例通过 `kernel.concurrency.task_manager.get_task_manager()` 提供；在测试环境中如需重置，可将包内 `_task_manager_instance` 置为 `None` 后重新获取实例：

    ```python
    import kernel.concurrency.task_manager as tm
    tm._task_manager_instance = None
    manager = tm.get_task_manager()
    # 关键任务逻辑
    return "critical result"

async def normal_task():
    # 普通任务逻辑
    return "normal result"

# 提交高优先级任务
config = TaskConfig(priority=TaskPriority.CRITICAL)
task_id = manager.submit_task(critical_task, name="CriticalTask", config=config)

# 提交普通优先级任务
task_id = manager.submit_task(normal_task, name="NormalTask")
```

### 2. 任务依赖

```python
async def task_a():
    await asyncio.sleep(1)
    return "A done"

async def task_b():
    await asyncio.sleep(1)
    return "B done"

async def task_c():
    await asyncio.sleep(1)
    return "C done (depends on A and B)"

# 提交任务 A 和 B
task_a_id = manager.submit_task(task_a, name="Task-A")
task_b_id = manager.submit_task(task_b, name="Task-B")

# 提交任务 C，依赖 A 和 B
config = TaskConfig(dependencies=[task_a_id, task_b_id])
task_c_id = manager.submit_task(task_c, name="Task-C", config=config)

# Task-C 会在 Task-A 和 Task-B 都完成后才执行
```

### 3. 任务重试

```python
async def unreliable_task():
    # 模拟可能失败的任务
    if random.random() < 0.7:
        raise Exception("Task failed")
    return "Success"

# 配置重试
config = TaskConfig(
    max_retries=3,        # 最多重试 3 次
    retry_delay=2.0       # 重试间隔 2 秒
)

task_id = manager.submit_task(unreliable_task, name="UnreliableTask", config=config)
```

### 4. 超时控制

```python
async def long_task():
    await asyncio.sleep(10)
    return "Done"

# 设置超时
config = TaskConfig(
    timeout=5.0,           # 5 秒超时
    enable_watchdog=True   # 启用 Watchdog 监控
)

task_id = manager.submit_task(long_task, name="LongTask", config=config)

# 任务会在 5 秒后被 Watchdog 取消
```

### 5. 任务回调

```python
def on_task_complete(task):
    print(f"Task {task.name} completed: {task.result}")

def on_task_failed(task):
    print(f"Task {task.name} failed: {task.error}")

# 注册回调
manager.add_complete_callback(on_task_complete)
manager.add_failed_callback(on_task_failed)

# 提交任务
task_id = manager.submit_task(my_task, name="MyTask")
```

### 6. 任务取消

```python
# 提交长时间运行的任务
async def long_running():
    try:
        await asyncio.sleep(100)
    except asyncio.CancelledError:
        print("Task was cancelled")
        raise

task_id = manager.submit_task(long_running, name="LongTask")

# 等待一段时间后取消
await asyncio.sleep(1)
success = await manager.cancel_task(task_id)
```

## 任务状态

任务在生命周期中会经历以下状态：

- `QUEUED`: 已排队，等待执行
- `WAITING`: 等待依赖任务完成
- `RUNNING`: 正在运行
- `COMPLETED`: 成功完成
- `FAILED`: 执行失败
- `CANCELLED`: 已取消
- `RETRYING`: 重试中

## 监控和统计

### 获取任务信息

```python
# 获取单个任务信息
task_info = manager.get_task_info(task_id)
print(f"Status: {task_info.state}")
print(f"Duration: {task_info.duration}s")

# 获取所有任务
all_tasks = manager.get_all_tasks()

# 按状态获取任务
from kernel.concurrency.task_manager import TaskState
running_tasks = manager.get_tasks_by_state(TaskState.RUNNING)
```

### 获取统计信息

```python
stats = manager.get_stats()
print(f"Total submitted: {stats['total_submitted']}")
print(f"Completed: {stats['total_completed']}")
print(f"Failed: {stats['total_failed']}")
print(f"Current running: {stats['current_running']}")
```

### 打印状态报告

```python
manager.print_status()
```

输出示例：
```
============================================================
TaskManager 状态报告
============================================================
运行状态: 运行中
最大并发数: 10

统计信息:
  总提交任务: 25
  已完成: 20
  失败: 2
  取消: 1
  重试次数: 3
  当前运行: 2
  队列中: 0
  等待依赖: 0

运行中的任务:
  - DataProcessing (ID: task_23_1234567890)
    优先级: HIGH, 运行时长: 3.45s
  - ModelTraining (ID: task_24_1234567891)
    优先级: NORMAL, 运行时长: 2.12s
============================================================
```

## 与 Watchdog 集成

`TaskManager` 自动与 `Watchdog` 集成，提供额外的监控能力：

```python
# TaskManager 会自动启动 Watchdog
manager = TaskManager(enable_watchdog=True)
await manager.start()

# 配置 Watchdog 行为
manager._watchdog.check_interval = 1.0  # 检查间隔

# 添加 Watchdog 回调
def on_timeout(task_id, task_info):
    print(f"Task {task_info.name} timed out!")

manager._watchdog.add_timeout_callback(on_timeout)

# 查看 Watchdog 状态
manager._watchdog.print_status()
```

## 最佳实践

1. **合理设置并发数**
   ```python
   # 根据系统资源和任务特性设置
   manager = TaskManager(max_concurrent_tasks=10)
   ```

2. **使用任务优先级**
   ```python
   # 关键任务使用高优先级
   config = TaskConfig(priority=TaskPriority.CRITICAL)
   ```

3. **设置超时**
   ```python
   # 防止任务无限期运行
   config = TaskConfig(timeout=30.0)
   ```

4. **处理依赖关系**
   ```python
   # 明确任务依赖关系
   config = TaskConfig(
       dependencies=[task1_id, task2_id],
       cancel_on_dependency_failure=True
   )
   ```

5. **配置重试策略**
   ```python
   # 对不稳定任务配置重试
   config = TaskConfig(max_retries=3, retry_delay=2.0)
   ```

6. **优雅关闭**
   ```python
   # 等待任务完成后关闭
   await manager.stop(cancel_running_tasks=False)
   
   # 或强制取消所有任务
   await manager.stop(cancel_running_tasks=True)
   ```

## 完整示例

```python
import asyncio
import random
from kernel.concurrency.task_manager import (
    TaskManager,
    TaskConfig,
    TaskPriority,
    TaskState
)

async def data_fetching(url: str):
    """模拟数据获取"""
    await asyncio.sleep(random.uniform(0.5, 2.0))
    return f"Data from {url}"

async def data_processing(data: str):
    """模拟数据处理"""
    await asyncio.sleep(random.uniform(1.0, 3.0))
    if random.random() < 0.2:
        raise Exception("Processing failed")
    return f"Processed: {data}"

async def data_saving(data: str):
    """模拟数据保存"""
    await asyncio.sleep(0.5)
    return f"Saved: {data}"

async def main():
    # 创建管理器
    manager = TaskManager(max_concurrent_tasks=5, enable_watchdog=True)
    await manager.start()
    
    # 回调函数
    def on_complete(task):
        print(f"✓ {task.name} completed in {task.duration:.2f}s")
    
    def on_failed(task):
        print(f"✗ {task.name} failed: {task.error}")
    
    manager.add_complete_callback(on_complete)
    manager.add_failed_callback(on_failed)
    
    # 提交任务链
    fetch_ids = []
    for i in range(3):
        url = f"https://api.example.com/data/{i}"
        config = TaskConfig(
            priority=TaskPriority.HIGH,
            timeout=5.0
        )
        task_id = manager.submit_task(
            data_fetching,
            url,
            name=f"Fetch-{i}",
            config=config
        )
        fetch_ids.append(task_id)
    
    # 处理任务依赖获取任务
    process_ids = []
    for i, fetch_id in enumerate(fetch_ids):
        config = TaskConfig(
            dependencies=[fetch_id],
            max_retries=2,
            retry_delay=1.0
        )
        # 获取获取任务的结果
        fetch_result = await manager.wait_for_task(fetch_id, timeout=10.0)
        
        task_id = manager.submit_task(
            data_processing,
            fetch_result,
            name=f"Process-{i}",
            config=config
        )
        process_ids.append(task_id)
    
    # 保存任务依赖处理任务
    save_ids = []
    for i, process_id in enumerate(process_ids):
        config = TaskConfig(dependencies=[process_id])
        
        try:
            process_result = await manager.wait_for_task(process_id, timeout=20.0)
            task_id = manager.submit_task(
                data_saving,
                process_result,
                name=f"Save-{i}",
                config=config
            )
            save_ids.append(task_id)
        except Exception as e:
            print(f"Processing failed for {i}: {e}")
    
    # 等待所有保存任务完成
    for save_id in save_ids:
        try:
            await manager.wait_for_task(save_id, timeout=10.0)
        except Exception as e:
            print(f"Save failed: {e}")
    
    # 打印统计
    manager.print_status()
    
    # 停止管理器
    await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## 错误处理

```python
from kernel.concurrency.task_manager import TaskManager

async def main():
    manager = TaskManager()
    await manager.start()
    
    try:
        # 提交任务
        task_id = manager.submit_task(my_task, name="MyTask")
        
        # 等待任务完成
        result = await manager.wait_for_task(task_id, timeout=10.0)
        
    except asyncio.TimeoutError:
        print("Task timed out")
        await manager.cancel_task(task_id)
        
    except Exception as e:
        print(f"Task failed: {e}")
        
    finally:
        await manager.stop()
```

## 配置参考

### TaskConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `priority` | `TaskPriority` | `NORMAL` | 任务优先级 |
| `timeout` | `float` | `None` | 超时时间（秒） |
| `max_retries` | `int` | `0` | 最大重试次数 |
| `retry_delay` | `float` | `1.0` | 重试延迟（秒） |
| `dependencies` | `List[str]` | `[]` | 依赖的任务ID列表 |
| `metadata` | `Dict` | `{}` | 任务元数据 |
| `cancel_on_dependency_failure` | `bool` | `True` | 依赖失败时是否取消 |
| `enable_watchdog` | `bool` | `True` | 是否启用Watchdog监控 |

### TaskManager 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_concurrent_tasks` | `int` | `10` | 最大并发任务数 |
| `enable_watchdog` | `bool` | `True` | 是否启用Watchdog |
| `watchdog_check_interval` | `float` | `1.0` | Watchdog检查间隔（秒） |
