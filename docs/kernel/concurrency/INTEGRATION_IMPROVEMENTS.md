"""
Watchdog 和 TaskManager 集成改进总览

检查日期: 2026年1月3日
改进内容: 优化两个模块间的协作机制
"""

## 问题分析

### 发现的问题

1. **Watchdog 回调未集成**
   - TaskManager 注册任务到 Watchdog，但未响应 Watchdog 的回调
   - Watchdog 的超时检测结果无法被 TaskManager 知晓

2. **任务状态信息不同步**
   - Watchdog 有自己的 TaskStatus（PENDING, RUNNING, COMPLETED, FAILED, TIMEOUT, CANCELLED）
   - TaskManager 有自己的 TaskState（QUEUED, WAITING, RUNNING, COMPLETED, FAILED, CANCELLED, RETRYING）
   - 两个状态系统没有映射关系

3. **异常处理缺乏协调**
   - Watchdog 会检测和记录异常
   - TaskManager 也会处理异常
   - 可能导致异常被重复处理

4. **资源泄漏风险**
   - 任务完成后，TaskManager 没有从 Watchdog 中注销
   - 导致已完成的任务仍被 Watchdog 跟踪，占用内存

5. **超时处理的职责不清**
   - 原来 Watchdog 检测到超时后自动取消任务
   - 没有让上层应用决定是否取消的机制

---

## 改进方案

### 1. 添加 Watchdog 回调集成 ✅

**在 TaskManager.__init__ 中注册回调：**

```python
# 如果启用 Watchdog，注册相应的回调
if self._watchdog:
    self._watchdog.add_timeout_callback(self._on_watchdog_timeout)
    self._watchdog.add_error_callback(self._on_watchdog_error)
```

**新增回调处理方法：**

```python
def _on_watchdog_timeout(self, watchdog_id: str, task_info: Any):
    """Watchdog 超时回调 - 自动取消超时任务（可配置）"""
    # 通过 watchdog_id 找到对应的 ManagedTask
    # 如果 auto_cancel_on_timeout=True，则取消任务

def _on_watchdog_error(self, watchdog_id: str, task_info: Any):
    """Watchdog 错误回调 - 仅记录错误信息"""
    # 实际错误处理在 _on_task_error 中完成
```

**优点：**
- TaskManager 能感知 Watchdog 的超时和错误检测
- 可配置超时时是否自动取消（通过 `auto_cancel_on_timeout` 属性）
- 提供更多的日志和诊断信息

### 2. 改进超时处理流程 ✅

**原流程（有问题）：**
```
Task Running → Watchdog 检测超时 → Watchdog 自动取消 → TaskManager 不知道原因
```

**新流程（改进后）：**
```
Task Running → Watchdog 检测超时 → Watchdog 触发回调 
→ TaskManager 通过回调得知 → TaskManager 决定是否取消
```

**Watchdog 改进：**
- `_handle_timeout` 方法不再自动取消任务
- 仅触发回调，让上层决定

**配置选项：**
```python
task_manager.auto_cancel_on_timeout = True  # 超时时自动取消（默认开启）
```

### 3. 添加资源清理机制 ✅

**新增方法：**
```python
async def _unregister_from_watchdog(self, managed_task: ManagedTask):
    """从 Watchdog 中注销任务，防止内存泄漏"""
```

**在任务完成时调用：**
- 任务成功完成 (`_on_task_success`)
- 任务执行失败 (`_on_task_error`)
- 任务被取消 (`_on_task_cancelled`)

**好处：**
- 已完成的任务及时从 Watchdog 中移除
- 防止内存泄漏
- 减少 Watchdog 的监控负担

### 4. 完善日志记录 ✅

**新增详细日志：**

在 `_on_watchdog_timeout` 中：
```
[Watchdog] 检测到任务超时: Task Name (ID: task_xxx)
超时时间: 30.0s, 实际运行时长: 31.5s
[TaskManager] 自动取消超时任务: Task Name
```

在 `_unregister_from_watchdog` 中：
```
任务已从 Watchdog 中注销: Task Name (watchdog_id: task_xxx_yyy)
```

### 5. 新增配置选项 ✅

```python
# 在 TaskManager.__init__ 中
self.auto_cancel_on_timeout = True  # 超时时是否自动取消任务
```

可通过以下方式配置：
```python
task_manager = TaskManager()
task_manager.auto_cancel_on_timeout = False  # 禁用自动取消
```

---

## 集成点总览

```
┌─────────────────────────────────────┐
│      TaskManager                    │
├─────────────────────────────────────┤
│                                     │
│  submit_task(coro)                  │
│    ↓                                │
│  _execute_task(task_id)             │
│    ├─ create asyncio.Task           │
│    ├─ watchdog.register_task() ◄────┼──┐
│    ├─ await task                    │  │
│    └─ _on_task_success/error        │  │
│         ├─ watchdog.unregister()    │  │
│         └─ update state             │  │
│                                     │  │
└─────────────────────────────────────┘  │
                                         │
┌─────────────────────────────────────┐  │
│      Watchdog                       │  │
├─────────────────────────────────────┤  │
│                                     │  │
│  get_watchdog()                     │◄─┘
│    ↓                                │
│  _monitor_loop()                    │
│    ├─ _check_tasks()                │
│    │   ├─ check timeout             │
│    │   └─ trigger callbacks         │
│    └─ _handle_timeout()             │
│         └─ add_timeout_callback()   │
│              ↓                      │
│         TaskManager._on_watchdog_timeout()
│              ├─ log timeout         │
│              └─ cancel task         │
│                                     │
└─────────────────────────────────────┘
```

---

## 配合效果检查表

- ✅ Watchdog 能监控 TaskManager 提交的任务
- ✅ TaskManager 能响应 Watchdog 的超时/错误回调
- ✅ 超时检测有明确的处理流程
- ✅ 任务完成后及时从 Watchdog 中注销
- ✅ 提供详细的日志记录
- ✅ 支持灵活的超时处理策略
- ✅ 错误处理协调一致
- ✅ 资源清理机制完善

---

## 测试覆盖

创建的集成测试（test_integration.py）包含：

1. **test_basic_integration** - 基本集成功能
2. **test_timeout_detection** - 超时检测和自动取消
3. **test_error_handling** - 错误处理
4. **test_retry_mechanism** - 重试机制
5. **test_watchdog_cleanup** - 资源清理
6. **test_concurrent_tasks** - 并发控制
7. **test_task_dependencies** - 依赖关系
8. **test_priority_queue** - 优先级队列

---

## 后续建议

1. **监控指标导出**
   - 导出 Watchdog 和 TaskManager 的统计数据到监控系统
   - 跟踪超时、错误率等关键指标

2. **性能优化**
   - 考虑 Watchdog 检查间隔的优化
   - 任务状态变化的批量处理

3. **错误恢复**
   - 增加更灵活的失败处理策略
   - 支持自定义的恢复逻辑

4. **文档完善**
   - 添加使用示例
   - 记录最佳实践
