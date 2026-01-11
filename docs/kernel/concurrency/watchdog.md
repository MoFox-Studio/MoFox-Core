# Watchdog 全局任务监控器文档

## 概述

Watchdog 是 MoFox 框架中的全局异步任务监控器，采用单例模式设计，用于监控和管理 asyncio 异步任务的完整生命周期。

**模块路径**: `src/kernel/concurrency/watchdog.py`

## 主要功能

### 1. 任务注册与追踪
- 注册需要监控的异步任务
- 为每个任务分配唯一ID
- 跟踪任务的运行状态和元数据
- 记录任务的开始时间、结束时间和运行时长

### 2. 超时检测
- 配置任务超时时间（全局默认或单个任务）
- 自动检测运行超时的任务
- 触发超时回调并自动取消超时任务
- 统计超时任务数量

### 3. 资源泄露检测
- 监控长时间运行的任务
- 自动清理已完成的任务记录（60秒后）
- 防止内存泄露
- 跟踪当前活跃任务数量

### 4. 任务统计与报告
- 统计任务执行情况（完成、失败、超时、取消）
- 生成详细的监控报告
- 实时查看运行中的任务
- 提供 `print_status()` 方法输出格式化报告

### 5. 异常任务处理
- 捕获并记录任务异常
- 触发错误回调函数
- 提供手动取消任务功能
- 区分不同的任务状态

## 核心组件

### TaskStatus 枚举

任务状态枚举类：

```python
class TaskStatus(Enum):
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 运行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    TIMEOUT = "timeout"        # 超时
    CANCELLED = "cancelled"    # 已取消
```

### TaskInfo 数据类

存储任务信息的数据类：

**属性**:
- `task_id` (str): 任务唯一标识符
- `name` (str): 任务名称
- `task` (asyncio.Task): 异步任务对象
- `status` (TaskStatus): 任务当前状态
- `start_time` (float): 任务开始时间（时间戳）
- `end_time` (Optional[float]): 任务结束时间（时间戳）
- `timeout` (Optional[float]): 超时时间（秒）
- `metadata` (Dict[str, Any]): 任务元数据
- `error` (Optional[Exception]): 任务异常信息

**属性方法**:
- `duration`: 返回任务运行时长（秒）
- `is_timeout`: 判断任务是否超时
- `is_alive`: 判断任务是否仍在运行

### Watchdog 类

全局任务监控器主类（单例模式）。

#### 配置属性

```python
watchdog.check_interval = 1.0        # 检查间隔（秒），默认 1.0
watchdog.default_timeout = 300.0     # 默认超时时间（秒），默认 300.0
watchdog.enable_timeout_check = True # 是否启用超时检查
watchdog.enable_leak_detection = True # 是否启用泄露检测
```

#### 主要方法

##### 生命周期管理

**`async start()`**
- 启动监控器
- 开始监控循环
- 幂等操作，重复调用不会产生副作用

**`async stop()`**
- 停止监控器
- 取消监控循环
- 清理资源

##### 任务管理

**`register_task(task, name=None, timeout=None, metadata=None) -> str`**

注册任务到监控器。

参数:
- `task` (asyncio.Task): 要监控的异步任务
- `name` (str, optional): 任务名称，默认为 "Task-{计数器}"
- `timeout` (float, optional): 超时时间（秒），默认使用 default_timeout
- `metadata` (dict, optional): 任务元数据

返回:
- `str`: 任务ID

**`unregister_task(task_id) -> bool`**

取消注册任务。

参数:
- `task_id` (str): 任务ID

返回:
- `bool`: 是否成功取消注册

**`async cancel_task(task_id, msg="Cancelled by watchdog") -> bool`**

取消指定任务。

参数:
- `task_id` (str): 任务ID
- `msg` (str): 取消原因

返回:
- `bool`: 是否成功取消

##### 查询方法

**`get_task_info(task_id) -> Optional[TaskInfo]`**

获取指定任务的信息。

**`get_all_tasks() -> Dict[str, TaskInfo]`**

获取所有任务信息。

**`get_running_tasks() -> Dict[str, TaskInfo]`**

获取所有运行中的任务。

**`get_stats() -> Dict[str, Any]`**

获取统计信息，包括：
- `total_registered`: 总注册任务数
- `total_completed`: 已完成任务数
- `total_failed`: 失败任务数
- `total_timeout`: 超时任务数
- `total_cancelled`: 取消任务数
- `current_running`: 当前运行任务数
- `current_tracked`: 当前跟踪任务数

**`print_status()`**

打印格式化的监控器状态报告。

##### 回调管理

**`add_timeout_callback(callback)`**

添加超时回调函数。

回调签名: `def callback(task_id: str, task_info: TaskInfo) -> None`

**`add_error_callback(callback)`**

添加错误回调函数。

回调签名: `def callback(task_id: str, task_info: TaskInfo) -> None`

**`add_complete_callback(callback)`**

添加完成回调函数。

回调签名: `def callback(task_id: str, task_info: TaskInfo) -> None`

### 全局函数

**`get_watchdog() -> Watchdog`**

获取全局 Watchdog 单例实例。

**`async watch_task(coro, name=None, timeout=None, metadata=None, auto_start=True) -> tuple[asyncio.Task, str]`**

便捷函数：创建并注册监控任务。

参数:
- `coro`: 协程对象
- `name` (str, optional): 任务名称
- `timeout` (float, optional): 超时时间
- `metadata` (dict, optional): 任务元数据
- `auto_start` (bool): 是否自动启动 watchdog，默认 True

返回:
- `tuple[asyncio.Task, str]`: (任务对象, 任务ID) 元组

## 使用示例

### 基本使用

```python
import asyncio
from mofox.kernel.concurrency.watchdog import get_watchdog, watch_task

async def my_task():
    """一个示例异步任务"""
    await asyncio.sleep(2)
    return "完成"

async def main():
    # 获取监控器实例
    watchdog = get_watchdog()
    
    # 启动监控器
    await watchdog.start()
    
    # 方式1: 使用便捷函数（推荐）
    task, task_id = await watch_task(
        my_task(),
        name="我的任务",
        timeout=5.0
    )
    
    # 等待任务完成
    result = await task
    print(f"任务结果: {result}")
    
    # 查看统计信息
    watchdog.print_status()
    
    # 停止监控器
    await watchdog.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 手动注册任务

```python
async def manual_registration():
    watchdog = get_watchdog()
    await watchdog.start()
    
    # 创建任务
    task = asyncio.create_task(my_long_task())
    
    # 手动注册到监控器
    task_id = watchdog.register_task(
        task,
        name="长时任务",
        timeout=60.0,
        metadata={"priority": "high", "user_id": 123}
    )
    
    print(f"任务已注册，ID: {task_id}")
    
    # 等待任务完成
    await task
    
    await watchdog.stop()
```

### 使用回调函数

```python
def on_timeout(task_id: str, task_info: TaskInfo):
    """超时回调"""
    print(f"⚠️  任务 '{task_info.name}' (ID: {task_id}) 超时了！")
    print(f"   运行时长: {task_info.duration:.2f}s")
    print(f"   超时设置: {task_info.timeout}s")

def on_error(task_id: str, task_info: TaskInfo):
    """错误回调"""
    print(f"❌ 任务 '{task_info.name}' (ID: {task_id}) 出错了！")
    print(f"   错误信息: {task_info.error}")

def on_complete(task_id: str, task_info: TaskInfo):
    """完成回调"""
    print(f"✅ 任务 '{task_info.name}' (ID: {task_id}) 完成了！")
    print(f"   运行时长: {task_info.duration:.2f}s")

async def with_callbacks():
    watchdog = get_watchdog()
    
    # 注册回调函数
    watchdog.add_timeout_callback(on_timeout)
    watchdog.add_error_callback(on_error)
    watchdog.add_complete_callback(on_complete)
    
    await watchdog.start()
    
    # 创建会超时的任务
    task, task_id = await watch_task(
        asyncio.sleep(10),
        name="测试超时",
        timeout=2.0  # 2秒超时
    )
    
    try:
        await task
    except asyncio.CancelledError:
        print("任务被取消")
    
    await watchdog.stop()
```

### 查询任务状态

```python
async def query_tasks():
    watchdog = get_watchdog()
    await watchdog.start()
    
    # 创建多个任务
    task1, id1 = await watch_task(asyncio.sleep(5), name="任务1")
    task2, id2 = await watch_task(asyncio.sleep(3), name="任务2")
    task3, id3 = await watch_task(asyncio.sleep(7), name="任务3")
    
    # 等待一秒
    await asyncio.sleep(1)
    
    # 查询特定任务
    task_info = watchdog.get_task_info(id1)
    print(f"任务1状态: {task_info.status.value}")
    print(f"任务1运行时长: {task_info.duration:.2f}s")
    
    # 查询所有运行中的任务
    running = watchdog.get_running_tasks()
    print(f"\n当前运行中的任务数: {len(running)}")
    for tid, info in running.items():
        print(f"  - {info.name}: {info.duration:.2f}s")
    
    # 获取统计数据
    stats = watchdog.get_stats()
    print(f"\n统计信息:")
    print(f"  总注册: {stats['total_registered']}")
    print(f"  当前运行: {stats['current_running']}")
    
    # 等待所有任务完成
    await asyncio.gather(task1, task2, task3)
    
    await watchdog.stop()
```

### 手动取消任务

```python
async def cancel_example():
    watchdog = get_watchdog()
    await watchdog.start()
    
    # 创建长时间运行的任务
    task, task_id = await watch_task(
        asyncio.sleep(100),
        name="长时任务",
        timeout=None  # 不设置超时
    )
    
    # 等待2秒后手动取消
    await asyncio.sleep(2)
    
    success = await watchdog.cancel_task(task_id, "用户手动取消")
    if success:
        print("任务已取消")
    
    try:
        await task
    except asyncio.CancelledError:
        print("任务被取消捕获")
    
    await watchdog.stop()
```

### 配置监控器

```python
async def configure_watchdog():
    watchdog = get_watchdog()
    
    # 自定义配置
    watchdog.check_interval = 0.5       # 每0.5秒检查一次
    watchdog.default_timeout = 60.0     # 默认60秒超时
    watchdog.enable_timeout_check = True
    watchdog.enable_leak_detection = True
    
    await watchdog.start()
    
    # ... 使用监控器 ...
    
    await watchdog.stop()
```

### 在应用中集成

```python
class Application:
    """应用主类"""
    
    def __init__(self):
        self.watchdog = get_watchdog()
    
    async def startup(self):
        """应用启动"""
        # 启动监控器
        await self.watchdog.start()
        print("监控器已启动")
        
        # 注册回调
        self.watchdog.add_error_callback(self.on_task_error)
        self.watchdog.add_timeout_callback(self.on_task_timeout)
    
    async def shutdown(self):
        """应用关闭"""
        # 停止监控器
        await self.watchdog.stop()
        print("监控器已停止")
    
    def on_task_error(self, task_id: str, task_info: TaskInfo):
        """处理任务错误"""
        # 记录日志、发送告警等
        print(f"任务错误: {task_info.name} - {task_info.error}")
    
    def on_task_timeout(self, task_id: str, task_info: TaskInfo):
        """处理任务超时"""
        # 记录日志、发送告警等
        print(f"任务超时: {task_info.name}")
    
    async def run_background_task(self, coro, name: str):
        """运行后台任务"""
        task, task_id = await watch_task(
            coro,
            name=name,
            timeout=300.0
        )
        return task, task_id

# 使用示例
async def main():
    app = Application()
    await app.startup()
    
    # 运行一些后台任务
    task, task_id = await app.run_background_task(
        some_background_work(),
        name="后台工作"
    )
    
    # ... 应用运行 ...
    
    await app.shutdown()
```

## 工作原理

### 监控循环

Watchdog 启动后会运行一个持续的监控循环：

1. 每隔 `check_interval` 秒执行一次检查
2. 遍历所有注册的任务
3. 检查是否有任务超时
4. 处理超时任务（触发回调、取消任务）
5. 清理已完成的任务（60秒后自动清理）

### 任务生命周期

```
注册 → 运行中 → [完成/失败/超时/取消] → 清理
  ↓       ↓              ↓                  ↓
记录    监控          触发回调          从监控器移除
```

### 回调触发时机

- **超时回调**: 任务运行时间超过 `timeout` 设置时
- **错误回调**: 任务抛出异常时
- **完成回调**: 任务正常完成时

### 自动清理机制

已完成的任务会在 60 秒后自动从监控器中移除，防止内存占用持续增长。

## 注意事项

### 1. 单例模式
Watchdog 使用单例模式，整个应用共享一个实例。多次调用 `get_watchdog()` 或 `Watchdog.get_instance()` 返回同一个对象。

### 2. 启动监控器
必须先调用 `start()` 启动监控器才能开始监控。建议在应用启动时启动，结束时调用 `stop()`。

### 3. 回调异常处理
回调函数中的异常会被捕获并打印，不会影响监控器的正常运行。但建议在回调中添加适当的异常处理。

### 4. 线程安全
Watchdog 设计为在单个 asyncio 事件循环中使用，**不保证多线程安全**。

### 5. 性能考虑
- 默认检查间隔为 1 秒，可根据实际需求调整
- 注册大量任务时，检查循环会遍历所有任务
- 考虑只注册关键任务到监控器

### 6. 超时设置
- 超时时间为 0 或负数视为无超时限制
- `timeout=None` 使用默认超时时间
- 可为单个任务单独设置超时时间

### 7. 任务清理
- 已完成的任务保留 60 秒后自动清理
- 可通过 `unregister_task()` 手动清理
- 清理后任务信息将无法查询

## 最佳实践

### 1. 应用生命周期管理

```python
# 在应用启动时
async def startup():
    watchdog = get_watchdog()
    watchdog.check_interval = 1.0
    watchdog.default_timeout = 300.0
    await watchdog.start()

# 在应用关闭时
async def shutdown():
    watchdog = get_watchdog()
    await watchdog.stop()
```

### 2. 有选择地注册任务

不是所有任务都需要监控，只监控关键的、长时间运行的、可能超时的任务：

```python
# 需要监控的任务
task, task_id = await watch_task(
    critical_operation(),
    name="关键操作",
    timeout=60.0
)

# 短时间的简单任务不需要监控
simple_result = await simple_operation()
```

### 3. 使用有意义的任务名称

```python
# 好的命名
task, _ = await watch_task(fetch_data(), name="fetch_user_data_123")

# 不好的命名
task, _ = await watch_task(fetch_data(), name="task")
```

### 4. 添加元数据

```python
task, task_id = await watch_task(
    process_request(request_id),
    name="process_request",
    metadata={
        "request_id": request_id,
        "user_id": user_id,
        "priority": "high",
        "timestamp": time.time()
    }
)
```

### 5. 实现告警机制

```python
def on_timeout_alert(task_id: str, task_info: TaskInfo):
    # 发送告警邮件、Slack 通知等
    send_alert(
        level="warning",
        message=f"任务超时: {task_info.name}",
        details=task_info.metadata
    )

watchdog.add_timeout_callback(on_timeout_alert)
```

### 6. 定期检查状态

```python
async def periodic_status_check():
    """定期检查并报告状态"""
    while True:
        await asyncio.sleep(300)  # 每5分钟
        watchdog = get_watchdog()
        stats = watchdog.get_stats()
        
        # 记录统计信息
        logger.info(f"Watchdog stats: {stats}")
        
        # 检查是否有异常情况
        if stats['current_running'] > 100:
            logger.warning("运行中的任务过多")
```

## 常见问题

### Q1: 如何禁用超时检查？

```python
watchdog = get_watchdog()
watchdog.enable_timeout_check = False
```

或为单个任务设置 `timeout=0`:

```python
task, task_id = await watch_task(coro, timeout=0)
```

### Q2: 任务完成后多久会被清理？

默认 60 秒后自动清理。这个时间硬编码在 `_check_tasks` 方法中，如需修改需要修改源码。

### Q3: 如何查看所有历史任务？

Watchdog 只保留最近 60 秒内的已完成任务。如需完整历史记录，建议在 complete 回调中持久化数据。

### Q4: 监控器停止后任务会被取消吗？

不会。监控器停止只是停止监控，已创建的任务会继续运行。

### Q5: 可以在多个事件循环中使用吗？

不建议。Watchdog 设计为单事件循环使用，在多事件循环环境下可能产生不可预期的行为。

## 扩展建议

### 1. 持久化任务历史

```python
def on_task_complete(task_id: str, task_info: TaskInfo):
    # 保存到数据库
    db.save_task_history({
        'task_id': task_id,
        'name': task_info.name,
        'duration': task_info.duration,
        'status': task_info.status.value,
        'timestamp': task_info.end_time
    })

watchdog.add_complete_callback(on_task_complete)
```

### 2. 集成监控系统

```python
def on_task_timeout(task_id: str, task_info: TaskInfo):
    # 发送到 Prometheus、Grafana 等
    metrics.increment('task_timeout_total')
    metrics.gauge('task_duration', task_info.duration)
```

### 3. 实现任务优先级

可以通过 metadata 添加优先级信息，并在超时时根据优先级决定处理策略。

## 相关模块

- [task_manager.py](./task_manager.md) - 任务管理器
- [concurrency/__init__.py](./concurrency_init.md) - 并发模块

## 版本历史

- **1.0.0** (2026-01-01): 初始版本

## 贡献者

MoFox Team

---

*最后更新: 2026年1月1日*
