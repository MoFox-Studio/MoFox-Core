# Logger-Storage 集成快速参考

快速查阅 Logger 和 Storage 模块集成的常用模式和代码片段。

---

## 最快开始（30秒）

```python
from kernel.logger.storage_integration import LoggerWithStorage

# 初始化
logger_system = LoggerWithStorage(app_name="myapp")

# 获取日志器
logger = logger_system.get_logger("app.main")

# 记录日志
logger.info("应用启动")
logger.error("发生错误")

# 查询日志
stats = logger_system.get_logs(days=1)
error_logs = logger_system.get_error_logs(days=1)
```

---

## 常用代码片段

### 基础使用

```python
# 创建日志系统
logger_system = LoggerWithStorage(
    app_name="myapp",
    log_dir="logs",
    console_output=True,
    json_storage=True
)

# 获取日志器
logger = logger_system.get_logger("module_name")

# 记录日志
logger.debug("调试")
logger.info("信息")
logger.warning("警告")
logger.error("错误")
logger.critical("严重错误")
logger.exception("异常")
```

### 带元数据的日志

```python
from kernel.logger import MetadataContext

# 方式 1：使用上下文
with MetadataContext(user_id="123", request_id="req_456"):
    logger.info("用户操作")

# 方式 2：手动设置
from kernel.logger import LogMetadata
LogMetadata.set_user_id("456")
LogMetadata.set_request_id("req_789")
logger.info("另一个操作")
```

### 日志查询

```python
# 获取统计信息
stats = logger_system.get_logs(days=1)
# 返回: {
#   'total': 100,
#   'by_level': {'INFO': 60, 'ERROR': 5},
#   'by_logger': {'app.main': 30}
# }

# 获取错误日志
errors = logger_system.get_error_logs(days=7)
for error in errors:
    print(f"{error['timestamp']}: {error['message']}")

# 直接访问存储
log_store = logger_system.log_store
logs = log_store.get_logs()
```

### 日志过滤

```python
from datetime import datetime, timedelta

# 按时间范围
start = datetime.now() - timedelta(days=7)
logs = log_store.get_logs(start_date=start)

# 按日志级别
error_logs = log_store.get_logs(
    filter_func=lambda log: log.get('level') == 'ERROR'
)

# 按日志器
app_logs = log_store.get_logs(
    filter_func=lambda log: log.get('logger') == 'app.main'
)

# 按内容
keyword_logs = log_store.get_logs(
    filter_func=lambda log: 'keyword' in log.get('message', '')
)

# 组合条件
end_date = datetime.now()
start_date = end_date - timedelta(days=1)
user_errors = log_store.get_logs(
    start_date=start_date,
    end_date=end_date,
    filter_func=lambda log: (
        log.get('level') == 'ERROR' and
        log.get('user_id') == 'user_123'
    )
)
```

### 日志维护

```python
# 清理 30 天前的日志
deleted = logger_system.cleanup_old_logs(days=30)

# 定期清理
import schedule

def cleanup_task():
    deleted = logger_system.cleanup_old_logs(days=30)
    print(f"清理了 {deleted} 个日志文件")

schedule.every().day.at("03:00").do(cleanup_task)
```

---

## 配置快速参考

### LoggerWithStorage 参数

```python
LoggerWithStorage(
    app_name="myapp",          # 应用名称（必需）
    log_dir="logs",            # 日志目录（默认: logs）
    console_output=True,       # 是否输出到控制台（默认: True）
    json_storage=True          # 是否存储到 JSON（默认: True）
)
```

### LogStore 参数

```python
LogStore(
    directory="logs",          # 日志目录（必需）
    prefix="app",             # 文件名前缀（默认: log）
    max_entries_per_file=1000,# 文件最大条目数（默认: 1000）
    auto_rotate=True          # 自动轮转（默认: True）
)
```

### LogStoreHandler 参数

```python
LogStoreHandler(
    log_store=log_store,      # LogStore 实例（必需）
    level=logging.DEBUG,      # 日志级别（默认: DEBUG）
    include_metadata=True,    # 包含元数据（默认: True）
    include_exc_info=True     # 包含异常信息（默认: True）
)
```

---

## 常见模式

### 模式 1：应用中央日志系统

```python
# config.py
from kernel.logger.storage_integration import LoggerWithStorage

logger_system = LoggerWithStorage(
    app_name="production_app",
    log_dir="/var/log/myapp",
    console_output=False
)

def get_logger(name):
    return logger_system.get_logger(name)

# main.py
from config import get_logger

logger = get_logger("app.main")
logger.info("应用启动")
```

### 模式 2：按功能模块分离日志

```python
logger_db = logger_system.get_logger("app.database")
logger_api = logger_system.get_logger("app.api")
logger_auth = logger_system.get_logger("app.auth")

# 数据库操作记录到不同日志器
logger_db.debug("连接数据库")
logger_db.info("执行查询")

# API操作记录到不同日志器
logger_api.info("POST /api/users")
logger_api.warning("请求超时")
```

### 模式 3：错误追踪和报警

```python
error_logs = logger_system.get_error_logs(days=1)

# 错误统计
error_count = len(error_logs)
if error_count > 10:
    # 发送报警
    send_alert(f"过去 24 小时发生 {error_count} 个错误")

# 错误分析
from collections import Counter
error_types = Counter(
    log['exception']['type'] 
    for log in error_logs 
    if 'exception' in log
)
print("主要错误类型:", error_types.most_common(5))
```

### 模式 4：审计日志

```python
from kernel.logger import MetadataContext

# 记录用户操作
with MetadataContext(user_id=user.id, session_id=session.id):
    logger.info("用户登录")
    logger.info("查看文件")
    logger.info("下载文件")
    logger.info("用户登出")

# 查询用户操作历史
audit_logs = log_store.get_logs(
    filter_func=lambda log: log.get('user_id') == target_user_id
)
for log in audit_logs:
    print(f"{log['timestamp']}: {log['message']}")
```

### 模式 5：性能监控

```python
import time

def timed_operation(name, func):
    start = time.time()
    result = func()
    elapsed = time.time() - start
    
    logger.info(f"{name} 完成", extra={'duration': elapsed})
    if elapsed > 1.0:
        logger.warning(f"{name} 耗时过长: {elapsed:.2f}秒")
    
    return result

# 分析性能
logs = log_store.get_logs(
    filter_func=lambda log: 'duration' in log
)
slow_operations = [log for log in logs if log.get('duration', 0) > 1.0]
```

---

## 日志格式

### 日志条目结构

```python
{
    "level": "INFO",                    # 日志级别
    "logger": "app.main",               # 日志器名称
    "message": "用户操作",              # 日志消息
    "timestamp": "2026-01-06T10:30:45", # 时间戳
    "module": "main",                   # 模块名
    "function": "process_user",         # 函数名
    "line": 42,                         # 代码行号
    "request_id": "req_123",            # 请求ID
    "user_id": "user_456",              # 用户ID
    "session_id": "sess_789",           # 会话ID
    "metadata": {                       # 自定义元数据
        "custom_field": "value"
    },
    "exception": {                      # 异常信息（仅错误）
        "type": "ValueError",
        "message": "invalid input",
        "traceback": "..."
    }
}
```

---

## 故障排查

### 问题：日志没有保存

```python
# 检查 LogStore 是否创建成功
if logger_system.log_store is None:
    print("LogStore 未初始化，检查 json_storage 参数")

# 检查处理器是否添加
handlers = logging.getLogger().handlers
print(f"日志处理器: {handlers}")

# 检查日志级别
print(f"日志级别: {logging.getLogger().level}")
```

### 问题：日志查询返回空

```python
# 确认日志确实已保存
logs_all = log_store.get_logs()
print(f"总日志数: {len(logs_all)}")

# 检查时间范围
from datetime import datetime, timedelta
today = datetime.now().replace(hour=0, minute=0, second=0)
logs_today = log_store.get_logs(start_date=today)
print(f"今天的日志数: {len(logs_today)}")
```

### 问题：性能下降

```python
# 减小日志级别
config = LoggerConfig(level="WARNING")

# 关闭不必要的处理器
# 只保留 LogStoreHandler

# 增大轮转阈值
log_store = LogStore(
    directory="logs",
    max_entries_per_file=5000  # 增大
)
```

---

## 性能指标

| 操作 | 耗时 | 说明 |
|------|------|------|
| 单条日志写入 | < 5ms | 取决于 JSON 大小和磁盘 |
| 日志查询（1天） | < 100ms | 从内存读取 |
| 日志过滤（1000条） | < 50ms | Python 列表推导式 |
| 日志清理（30天） | < 500ms | 删除旧文件 |

### 优化建议

- 使用异步处理器：`AsyncHandler(storage_handler)`
- 关闭不必要的元数据：`include_metadata=False`
- 调整日志级别为 `WARNING`
- 增大日志轮转阈值

---

## 完整示例

```python
#!/usr/bin/env python3
"""完整的 Logger-Storage 集成示例"""

from kernel.logger.storage_integration import LoggerWithStorage
from kernel.logger import MetadataContext
from datetime import datetime, timedelta

# 初始化
logger_system = LoggerWithStorage(
    app_name="demo",
    log_dir="logs/demo",
    console_output=True,
    json_storage=True
)

# 获取日志器
logger = logger_system.get_logger("demo.main")

# 记录各种日志
logger.debug("调试信息")
logger.info("应用启动")

# 模拟用户操作
with MetadataContext(user_id="user_001", request_id="req_001"):
    logger.info("用户登录")
    logger.info("用户请求数据")

# 模拟错误
try:
    x = 1 / 0
except ZeroDivisionError:
    logger.exception("数学错误")

# 查询和分析
stats = logger_system.get_logs(days=1)
print(f"\n日志统计: {stats}")

errors = logger_system.get_error_logs(days=1)
print(f"\n错误数量: {len(errors)}")
for error in errors:
    print(f"  - {error['message']}")

# 清理
deleted = logger_system.cleanup_old_logs(days=30)
print(f"\n清理了 {deleted} 个旧日志文件")
```

---

## 检查清单

集成 Logger 和 Storage 时的检查清单：

- [ ] 创建了 LoggerWithStorage 实例
- [ ] 获取日志器并开始记录
- [ ] 验证日志出现在控制台和 JSON 文件中
- [ ] 测试了日志查询功能
- [ ] 设置了定期清理任务
- [ ] 配置了元数据（user_id, request_id）
- [ ] 测试了错误日志和异常记录
- [ ] 验证了性能可接受
- [ ] 配置了生产环境日志级别
- [ ] 设置了日志轮转和备份策略

---

## 下一步

- 查看完整的 [集成指南](./LOGGER_STORAGE_INTEGRATION.md)
- 查看 [集成示例代码](./storage_integration.py)
- 阅读 [Logger 文档](./README.md)
- 阅读 [Storage 文档](../storage/README.md)
