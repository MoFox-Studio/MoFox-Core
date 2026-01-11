# Logger 与 Storage 模块集成指南

本文档说明如何将日志系统（Logger 模块）与存储系统（Storage 模块）集成，实现日志的持久化存储和后续查询。

---

## 概述

Logger 模块和 Storage 模块现已完全集成：

- **Logger 模块**: 提供日志记录功能，支持多种输出格式和元数据
- **Storage 模块**: 提供 JSON 文件存储功能，支持日志专用的 LogStore
- **LogStoreHandler**: 新增的处理器类，直接连接两个模块

### 集成优势

✨ **持久化存储**: 日志不仅输出到控制台，还存储到 JSON 文件  
🔍 **查询分析**: 支持按时间范围、日志级别、日志器等条件查询  
📊 **统计分析**: 支持日志统计、错误追踪、性能监控  
🔄 **自动管理**: 自动轮转、压缩、清理旧日志  
🔒 **元数据保存**: 自动保存 request_id、user_id 等上下文信息  

---

## 基础使用

### 方式 1: 最简单的方式（推荐）

```python
from kernel.logger.storage_integration import LoggerWithStorage

# 创建集成的日志系统
logger_system = LoggerWithStorage(
    app_name="myapp",
    log_dir="logs",
    console_output=True,      # 同时输出到控制台
    json_storage=True         # 同时存储到 JSON
)

# 获取日志器并使用
logger = logger_system.get_logger("app.main")
logger.info("应用启动")
logger.warning("发生警告")
logger.error("发生错误")

# 查询日志统计
stats = logger_system.get_logs(days=1)
print(f"日志统计: {stats}")

# 获取错误日志
error_logs = logger_system.get_error_logs(days=1)
```

### 方式 2: 手动集成（更灵活）

```python
import logging
from kernel.logger import LoggerConfig, setup_logger, LogStoreHandler
from kernel.storage import LogStore

# 1. 创建存储器
log_store = LogStore(
    directory="logs",
    prefix="myapp",
    max_entries_per_file=1000,
    auto_rotate=True
)

# 2. 配置和初始化 Logger
config = LoggerConfig(
    level="DEBUG",
    console_enabled=True,
    console_colors=True,
)
setup_logger(config)

# 3. 添加存储处理器
root_logger = logging.getLogger()
storage_handler = LogStoreHandler(
    log_store=log_store,
    level=logging.DEBUG,
    include_metadata=True,
    include_exc_info=True
)
root_logger.addHandler(storage_handler)

# 4. 使用日志器
logger = logging.getLogger("app.main")
logger.info("应用启动")
```

### 方式 3: 只存储到 JSON（不输出到控制台）

```python
from kernel.logger import LoggerConfig, setup_logger, LogStoreHandler
from kernel.storage import LogStore

# 禁用控制台输出
config = LoggerConfig(
    level="DEBUG",
    console_enabled=False,  # 关闭控制台
)
setup_logger(config)

# 只添加存储处理器
log_store = LogStore(directory="logs", prefix="silent_app")
storage_handler = LogStoreHandler(log_store=log_store)
logging.getLogger().addHandler(storage_handler)

# 使用
logger = logging.getLogger("app")
logger.info("静默记录到文件")
```

---

## 带元数据的日志记录

Logger 的元数据功能与 Storage 完全兼容：

```python
from kernel.logger import get_logger, MetadataContext

logger = logging.getLogger("app.handlers")

# 方式 1: 使用上下文管理器
with MetadataContext(user_id="user_123", request_id="req_456"):
    logger.info("用户登录")
    logger.info("处理请求")

# 记录的日志会自动包含：
# {
#   "level": "INFO",
#   "message": "用户登录",
#   "user_id": "user_123",
#   "request_id": "req_456",
#   ...
# }

# 方式 2: 手动设置
LogMetadata.set_user_id("user_789")
LogMetadata.set_request_id("req_789")
logger.info("用户执行操作")
```

---

## 日志查询

### 获取日志统计

```python
from kernel.logger.storage_integration import LoggerWithStorage

logger_system = LoggerWithStorage(app_name="myapp")

# 获取最近 1 天的日志统计
stats = logger_system.get_logs(days=1)

# 结果格式:
# {
#   'total': 100,
#   'by_level': {
#       'DEBUG': 20,
#       'INFO': 60,
#       'WARNING': 15,
#       'ERROR': 5
#   },
#   'by_logger': {
#       'app.main': 30,
#       'app.db': 40,
#       'app.api': 30
#   }
# }
```

### 获取特定日志

```python
from datetime import datetime, timedelta

# 直接访问存储
log_store = logger_system.log_store

# 获取最近 7 天的所有日志
week_ago = datetime.now() - timedelta(days=7)
logs = log_store.get_logs(start_date=week_ago)

# 按日志级别过滤
error_logs = log_store.get_logs(
    filter_func=lambda log: log.get('level') == 'ERROR'
)

# 按日志器过滤
app_logs = log_store.get_logs(
    filter_func=lambda log: log.get('logger').startswith('app.')
)

# 按时间范围过滤
start = datetime(2026, 1, 1)
end = datetime(2026, 1, 31)
jan_logs = log_store.get_logs(start_date=start, end_date=end)
```

### 获取错误日志

```python
# 简便方法
error_logs = logger_system.get_error_logs(days=1)

# 每条错误日志包含：
for log in error_logs:
    print(f"错误: {log['message']}")
    print(f"日志器: {log['logger']}")
    print(f"文件: {log['module']}.{log['function']}:{log['line']}")
    
    if 'exception' in log:
        print(f"异常类型: {log['exception']['type']}")
        print(f"异常消息: {log['exception']['message']}")
        print(f"堆栈跟踪:\n{log['exception']['traceback']}")
```

---

## 使用场景

### 场景 1: 应用性能监控

```python
import time
from kernel.logger import get_logger

logger = get_logger("app.performance")
log_store = ...  # 获取 log_store 实例

# 监控每个操作的耗时
operations = [
    ("用户认证", auth_operation),
    ("数据库查询", db_query),
    ("API调用", api_call),
]

for op_name, operation in operations:
    start = time.time()
    operation()
    elapsed = time.time() - start
    
    logger.info(f"操作完成: {op_name}", extra={'duration': elapsed})

# 后续分析
logs = log_store.get_logs(filter_func=lambda log: "操作完成" in log['message'])
total_time = sum(log.get('duration', 0) for log in logs)
```

### 场景 2: 用户活动审计

```python
from kernel.logger import MetadataContext, get_logger

logger = get_logger("app.audit")
log_store = ...

# 记录用户活动
with MetadataContext(user_id="user_123", session_id="sess_456"):
    logger.info("用户登录")
    logger.info("用户访问 /api/profile")
    logger.info("用户修改配置")
    logger.info("用户登出")

# 后续查询
user_logs = log_store.get_logs(
    filter_func=lambda log: log.get('user_id') == 'user_123'
)

# 审计轨迹
for log in user_logs:
    print(f"{log['timestamp']}: {log['message']}")
```

### 场景 3: 错误追踪和分析

```python
from kernel.logger import get_logger

logger = get_logger("app.errors")
log_store = ...

try:
    # 可能出错的代码
    result = risky_operation()
except Exception:
    # 记录完整的错误信息
    logger.exception("操作失败")

# 分析错误
error_logs = log_store.get_logs(
    filter_func=lambda log: 'exception' in log
)

# 错误统计
error_types = {}
for log in error_logs:
    exc_type = log['exception']['type']
    error_types[exc_type] = error_types.get(exc_type, 0) + 1

print("错误类型统计:")
for exc_type, count in error_types.items():
    print(f"  {exc_type}: {count} 次")
```

### 场景 4: 调试和诊断

```python
from kernel.logger import get_logger, MetadataContext

logger = get_logger("app.debug")

# 在特定上下文中详细记录
with MetadataContext(request_id="debug_123"):
    logger.debug("开始处理请求")
    logger.debug("验证输入参数")
    logger.debug("查询数据库")
    logger.debug("处理业务逻辑")
    logger.debug("返回结果")

# 获取调试日志
debug_logs = log_store.get_logs(
    filter_func=lambda log: log.get('level') == 'DEBUG'
)

# 追踪执行流程
for log in debug_logs:
    print(f"{log['timestamp']}: {log['message']}")
```

---

## 日志文件结构

日志被存储为 JSON 文件，位置在 `{log_dir}/{app_name}_{YYYYMMDD}.json`：

```json
[
  {
    "level": "INFO",
    "logger": "app.main",
    "message": "应用启动",
    "module": "main",
    "function": "main",
    "line": 42,
    "timestamp": "2026-01-06T10:30:45.123456",
    "request_id": "req_123",
    "user_id": "user_456",
    "metadata": {
      "custom_field": "custom_value"
    }
  },
  {
    "level": "ERROR",
    "logger": "app.handlers",
    "message": "处理请求失败",
    "module": "handlers",
    "function": "handle_request",
    "line": 156,
    "timestamp": "2026-01-06T10:31:12.654321",
    "exception": {
      "type": "ValueError",
      "message": "invalid input",
      "traceback": "Traceback (most recent call last):\n  ..."
    }
  }
]
```

### 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| level | 日志级别 | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| logger | 日志器名称 | app.main, app.handlers |
| message | 日志消息 | 应用启动 |
| module | 模块名 | main, handlers |
| function | 函数名 | main, handle_request |
| line | 代码行号 | 42, 156 |
| timestamp | 时间戳（ISO格式） | 2026-01-06T10:30:45.123456 |
| request_id | 请求ID（如果设置） | req_123 |
| session_id | 会话ID（如果设置） | sess_456 |
| user_id | 用户ID（如果设置） | user_456 |
| metadata | 自定义元数据 | {"custom": "value"} |
| exception | 异常信息（仅错误日志） | {"type": "ValueError", ...} |

---

## 配置选项

### LogStoreHandler 配置

```python
from kernel.logger import LogStoreHandler
from kernel.storage import LogStore

log_store = LogStore(directory="logs", prefix="myapp")

handler = LogStoreHandler(
    log_store=log_store,
    level=logging.DEBUG,              # 日志级别
    include_metadata=True,            # 包含 request_id, user_id 等
    include_exc_info=True             # 包含异常堆栈跟踪
)
```

### LogStore 配置

```python
from kernel.storage import LogStore

log_store = LogStore(
    directory="logs",                 # 日志存储目录
    prefix="myapp",                   # 文件名前缀
    max_entries_per_file=1000,        # 每个文件最大条目数
    auto_rotate=True                  # 自动轮转
)
```

---

## 最佳实践

### 1. 始终使用 MetadataContext

```python
# ✅ 推荐
with MetadataContext(user_id=user.id, request_id=request.id):
    logger.info("用户操作")

# ❌ 不推荐
logger.info(f"用户 {user.id} 的操作")  # 日志内容中包含信息，不可查询
```

### 2. 使用适当的日志级别

```python
logger.debug("变量值: x=10")           # 调试信息
logger.info("用户登录成功")            # 一般信息
logger.warning("连接超时，正在重试")   # 警告信息
logger.error("数据库连接失败")         # 错误信息
logger.critical("系统崩溃")            # 严重错误
```

### 3. 定期清理旧日志

```python
# 定期清理 30 天前的日志
import schedule

def cleanup():
    logger_system.cleanup_old_logs(days=30)

schedule.every().day.at("03:00").do(cleanup)
```

### 4. 分离不同类型的日志

```python
# 应用日志
app_logger = logger_system.get_logger("app")
app_logger.info("应用级别的信息")

# 数据库日志
db_logger = logger_system.get_logger("app.db")
db_logger.debug("SQL 查询")

# API 日志
api_logger = logger_system.get_logger("app.api")
api_logger.info("API 请求")
```

### 5. 对敏感信息进行脱敏

```python
# ❌ 不要记录敏感信息
logger.info(f"用户密码: {password}")

# ✅ 脱敏处理
logger.info("密码设置成功")
logger.debug(f"密码长度: {len(password)}")  # 记录长度而不是密码本身
```

---

## 与现有代码集成

如果您的项目已有日志系统，可以这样集成：

```python
# 原有的日志配置
import logging
logger = logging.getLogger("myapp")

# 添加存储处理器
from kernel.logger import LogStoreHandler
from kernel.storage import LogStore

log_store = LogStore(directory="logs", prefix="myapp")
handler = LogStoreHandler(log_store=log_store)
logger.addHandler(handler)

# 现在日志既输出到原有的输出，也存储到 JSON
logger.info("这条日志会被存储")
```

---

## 常见问题

### Q1: 如何只存储特定级别的日志？

```python
# 只存储 WARNING 及以上的日志
storage_handler = LogStoreHandler(
    log_store=log_store,
    level=logging.WARNING  # 只有 WARNING, ERROR, CRITICAL 会被存储
)
```

### Q2: 如何在查询时搜索特定内容？

```python
# 搜索包含特定文本的日志
logs = log_store.get_logs(
    filter_func=lambda log: "关键词" in log['message']
)
```

### Q3: 如何导出日志为其他格式？

```python
import json
import csv

logs = log_store.get_logs()

# 导出为 JSON 文件
with open('logs_export.json', 'w') as f:
    json.dump(logs, f, indent=2)

# 导出为 CSV 文件
with open('logs_export.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['timestamp', 'level', 'message', 'logger'])
    writer.writeheader()
    for log in logs:
        writer.writerow({
            'timestamp': log.get('timestamp'),
            'level': log.get('level'),
            'message': log.get('message'),
            'logger': log.get('logger')
        })
```

### Q4: 日志存储对性能有影响吗？

影响很小。Storage 模块的写入操作非常快，而且：
- 使用了原子操作，避免阻塞
- 可以使用 AsyncHandler 进行异步写入
- 日志条目以 JSON 格式存储，便于快速查询

```python
# 使用异步处理器进一步提升性能
from kernel.logger import AsyncHandler

async_handler = AsyncHandler(storage_handler)
logger.addHandler(async_handler)
```

### Q5: 如何备份和恢复日志？

```python
# 日志文件的备份由 LogStore 自动管理
# 默认保留 5 个备份

# 手动压缩（节省空间）
log_store.compress()

# 清理旧日志
deleted = log_store.clear_old_logs(days=30)
print(f"清理了 {deleted} 个旧日志文件")
```

---

## 性能建议

### 日志量很大时的优化

```python
# 1. 关闭不必要的日志级别
config = LoggerConfig(
    level="INFO",  # 仅记录 INFO 及以上
    console_enabled=False,  # 不输出到控制台（提升性能）
)

# 2. 增大日志轮转阈值
log_store = LogStore(
    directory="logs",
    max_entries_per_file=5000  # 从默认的 1000 增大到 5000
)

# 3. 定期清理
import schedule
schedule.every().day.at("03:00").do(
    lambda: log_store.clear_old_logs(days=7)  # 只保留 7 天
)
```

---

## 下一步

- 查看 [Logger 模块文档](./README.md)
- 查看 [Storage 模块文档](../storage/README.md)
- 查看 [集成示例](./storage_integration.py)
- 查看 [最佳实践](./BEST_PRACTICES.md)

---

## 总结

✅ **优势**:
- 日志持久化存储
- 支持复杂查询和分析
- 自动管理和清理
- 元数据自动记录
- 与现有系统兼容

📝 **核心概念**:
- LogStoreHandler: 连接 Logger 和 Storage 的处理器
- LogStore: 日志专用的存储器
- MetadataContext: 上下文信息管理
- 日志查询: 按时间、级别、内容、元数据过滤

🚀 **立即开始**:
```python
from kernel.logger.storage_integration import LoggerWithStorage

logger_system = LoggerWithStorage(app_name="myapp")
logger = logger_system.get_logger(__name__)
logger.info("开始使用集成的日志系统!")
```
