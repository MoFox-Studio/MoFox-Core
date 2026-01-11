# TaskManager 模块重构说明

## 概述

TaskManager 已从单个 `task_manager.py` 文件拆分为一个组织良好的 `task_manager` 包，以便更好地维护和扩展。

## 新的目录结构

```
src/kernel/concurrency/
├── task_manager/                   # TaskManager 包
│   ├── __init__.py                # 包初始化（导出公共接口）
│   ├── models.py                  # 数据模型（TaskPriority, TaskState, TaskConfig, ManagedTask）
│   ├── manager.py                 # 主管理器类（TaskManager, get_task_manager）
│   ├── scheduler.py               # 任务调度器（按优先级调度任务）
│   ├── executor.py                # 任务执行器（执行单个任务）
│   ├── dependency.py              # 依赖管理器（处理任务依赖关系）
│   └── callbacks.py               # 回调管理器（管理完成/失败回调）
├── task_manager.py                # 向后兼容层（导入并重导出）
├── task_manager_old.py.bak        # 原始文件备份
└── watchdog.py                    # 任务监控器
```

## 模块职责

### models.py
- **TaskPriority**: 任务优先级枚举（LOW, NORMAL, HIGH, CRITICAL）
- **TaskState**: 任务状态枚举（QUEUED, WAITING, RUNNING, COMPLETED, FAILED, CANCELLED, RETRYING）
- **TaskConfig**: 任务配置数据类（优先级、超时、重试、依赖等）
- **ManagedTask**: 被管理的任务数据类（包含任务的所有运行时信息）

### manager.py
- **TaskManager**: 主任务管理类
  - 任务提交和调度
  - 与 Watchdog 集成
  - 全局实例管理
  - 统计信息收集
  - 状态查询和打印
- **get_task_manager()**: 获取全局 TaskManager 实例

### scheduler.py
- **TaskScheduler**: 任务调度器
  - 维护按优先级分类的队列
  - 按优先级获取下一个任务
  - 检查队列状态

### executor.py
- **TaskExecutor**: 任务执行器
  - 执行单个任务
  - 管理信号量（并发控制）
  - 与 Watchdog 集成
  - 处理任务生命周期（成功、失败、取消）

### dependency.py
- **DependencyManager**: 依赖管理器
  - 检查任务依赖
  - 通知依赖任务
  - 处理依赖关系图

### callbacks.py
- **CallbackManager**: 回调管理器
  - 管理任务完成回调
  - 管理任务失败回调
  - 安全执行异步/同步回调

## 向后兼容性

原始的 `task_manager.py` 文件现已成为一个兼容层，它从新的包结构中导入所有内容。这意味着：

### 旧的导入方式仍然有效：
```python
from kernel.concurrency.task_manager import TaskManager, get_task_manager
from kernel.concurrency.task_manager import TaskConfig, TaskPriority, TaskState, ManagedTask
```

### 新的导入方式（推荐）：
```python
from kernel.concurrency.task_manager import TaskManager, get_task_manager
```

两种方式都会正确导入，因为 `task_manager.py` 会自动重导出所有内容。

## 使用示例

### 基本用法
```python
import asyncio
from kernel.concurrency.task_manager import get_task_manager, TaskPriority

async def main():
    # 获取 TaskManager 实例
    manager = get_task_manager(max_concurrent_tasks=10)
    
    # 启动管理器
    await manager.start()
    
    # 定义任务
    async def task_func(x):
        await asyncio.sleep(1)
        return x * 2
    
    # 提交任务
    task_id = manager.submit_task(
        task_func,
        5,
        name="calculate",
        priority=TaskPriority.HIGH
    )
    
    # 等待任务完成
    result = await manager.wait_for_task(task_id)
    print(f"Result: {result}")
    
    # 停止管理器
    await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## 维护优势

1. **模块化**: 每个模块有单一职责
   - `models.py`: 数据定义
   - `scheduler.py`: 调度逻辑
   - `executor.py`: 执行逻辑
   - `dependency.py`: 依赖逻辑
   - `callbacks.py`: 回调逻辑
   - `manager.py`: 主协调

2. **易于测试**: 可以独立测试每个组件

3. **易于扩展**: 新增功能可以添加新模块或扩展现有模块

4. **易于维护**: 代码行数减少，逻辑清晰

5. **向后兼容**: 现有代码无需修改即可工作

## 迁移指南

如果需要更新代码以使用新的包结构（虽然不是必需的）：

### 可选的新导入方式：
```python
# 从包导入（内部实现）
from kernel.concurrency.task_manager.models import TaskPriority, TaskState
from kernel.concurrency.task_manager.manager import TaskManager, get_task_manager
```

### 保持原有方式（推荐兼容性）：
```python
# 从兼容层导入（与旧代码一致）
from kernel.concurrency.task_manager import TaskManager, get_task_manager
```

## 测试

现有的所有测试应该继续工作，因为导入路径没有改变。如果遇到问题，请检查：

1. 确保导入语句正确
2. 检查 `__init__.py` 文件中的导出
3. 验证模块间的依赖关系
