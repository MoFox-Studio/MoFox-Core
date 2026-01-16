# MoFox Logger 日志系统

MoFox 的统一日志系统，提供强大、灵活、易用的日志记录功能。

## 特性

- 🎨 **多种输出格式**：纯文本、JSON、彩色控制台、结构化格式
- 📝 **多种处理器**：控制台、文件、错误文件、时间轮转
- 🏷️ **元数据支持**：请求ID、会话ID、用户ID、自定义字段
- 🧹 **自动清理**：日志压缩、过期删除、大小限制
- ⚡ **异步日志**：避免IO阻塞主线程
- 🔧 **灵活配置**：开发/生产/测试环境预设配置
- 🎯 **单例模式**：全局统一的日志管理
- 💾 **存储集成**：与 Storage 模块无缝集成，日志直接存储为 JSON

## 快速开始

### 💡 新建议：使用 Storage 集成（推荐）

Logger 现已与 Storage 模块深度集成，能够将日志直接存储为 JSON 格式，便于后续查询和分析：

```python
from kernel.logger.storage_integration import LoggerWithStorage

# 一行代码启动 Logger + Storage 集成
logger_system = LoggerWithStorage(app_name="myapp")

# 获取日志器
logger = logger_system.get_logger("app.main")

# 记录日志（自动保存到 JSON）
logger.info("应用启动")
logger.error("发生错误")

# 查询日志
stats = logger_system.get_logs(days=1)
errors = logger_system.get_error_logs(days=1)
```

更多信息请查看：
- 📖 [Logger-Storage 集成指南](../../docs/kernel/logger/LOGGER_STORAGE_INTEGRATION.md)
- 🚀 [快速参考](../../docs/kernel/logger/QUICK_REFERENCE.md)
- 💻 [集成示例代码](./storage_integration.py)

---

### 基本使用

```python
from kernel.logger import setup_logger, get_logger

# 1. 设置日志系统
setup_logger()

# 2. 获取日志器
logger = get_logger(__name__)

# 3. 记录日志
logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

### 自定义配置

```python
from kernel.logger import setup_logger, get_logger, LoggerConfig

# 创建自定义配置
config = LoggerConfig(
    name="my_app",
    level="DEBUG",
    console_enabled=True,
    console_colors=True,
    file_enabled=True,
    file_path="logs/app.log",
    file_format="json",
    error_file_enabled=True,
)

# 使用配置
setup_logger(config)
logger = get_logger("my_app")
logger.info("应用启动")
```

### 使用元数据

```python
from kernel.logger import setup_logger, get_logger, with_metadata, LogMetadata

setup_logger()
logger = get_logger(__name__)

# 方式1: 上下文管理器
with with_metadata(user_id="user123", session_id="sess456"):
    logger.info("用户登录")  # 日志自动包含user_id和session_id

# 方式2: 手动设置
LogMetadata.set_user_id("user789")
LogMetadata.set_session_id("sess101")
LogMetadata.set_custom("ip", "192.168.1.1")
logger.info("用户操作")

# 清除元数据
LogMetadata.clear()
```

## 配置详解

### LoggerConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | "mofox" | 日志器名称 |
| `level` | str | "INFO" | 全局日志级别 |
| `console_enabled` | bool | True | 是否启用控制台输出 |
| `console_level` | str | "INFO" | 控制台日志级别 |
| `console_colors` | bool | True | 是否使用彩色输出 |
| `file_enabled` | bool | True | 是否启用文件输出 |
| `file_level` | str | "DEBUG" | 文件日志级别 |
| `file_path` | str | "logs/mofox.log" | 日志文件路径 |
| `file_max_bytes` | int | 10MB | 单个文件最大大小 |
| `file_backup_count` | int | 5 | 备份文件数量 |
| `file_format` | str | "plain" | 文件格式（plain/json） |
| `error_file_enabled` | bool | True | 是否启用错误文件 |
| `error_file_path` | str | "logs/error.log" | 错误日志文件路径 |
| `include_metadata` | bool | True | 是否包含元数据 |
| `async_logging` | bool | False | 是否使用异步日志 |

### 预设配置

```python
from kernel.logger import (
    create_default_config,
    create_development_config,
    create_production_config,
    create_testing_config,
)

# 开发环境：DEBUG级别，彩色控制台
dev_config = create_development_config()

# 生产环境：INFO级别，JSON格式，异步日志
prod_config = create_production_config()

# 测试环境：WARNING级别，最小化输出
test_config = create_testing_config()
```

## 高级功能

### 异常日志

```python
logger = get_logger(__name__)

try:
    result = 1 / 0
except Exception:
    # 自动记录异常堆栈信息
    logger.exception("发生异常")
```

### 日志清理

```python
from kernel.logger import create_auto_cleaner

# 创建自动清理器
cleaner = create_auto_cleaner(
    log_directory="logs",
    max_age_days=30,        # 保留30天
    max_size_mb=100,        # 最大100MB
    compress_after_days=7   # 7天后压缩
)

# 执行清理
results = cleaner.run()
print(f"清理了 {results['deleted_old']} 个过期文件")
print(f"压缩了 {results['compressed']} 个文件")
```

### 手动清理操作

```python
from kernel.logger import LogCleaner

cleaner = LogCleaner("logs")

# 删除30天前的日志
cleaner.delete_old_logs(max_age_days=30)

# 压缩日志文件
cleaner.compress_logs()

# 归档日志
cleaner.archive_logs(max_age_days=7)

# 获取统计信息
stats = cleaner.get_statistics()
print(f"总文件数: {stats['total_files']}")
print(f"总大小: {stats['total_size_mb']:.2f} MB")
```

### 异步日志（避免IO阻塞）

```python
config = LoggerConfig(
    async_logging=True,      # 启用异步日志
    async_queue_size=1000    # 队列大小
)
setup_logger(config)
```

### 自定义渲染器

```python
from kernel.logger.renderers import JSONRenderer, ColoredRenderer
from kernel.logger.handlers import FileHandler

# JSON格式的文件处理器
handler = FileHandler(
    filename="logs/json.log",
    use_json=True
)

# 彩色控制台处理器
from kernel.logger.handlers import ConsoleHandler
handler = ConsoleHandler(use_colors=True)
```

## 日志格式示例

### 纯文本格式

```
[2026-01-06 10:30:15.123] [INFO] [my_app] [req=a1b2c3d4, user=user123] 用户登录成功
```

### JSON格式

```json
{
  "timestamp": "2026-01-06T10:30:15.123456",
  "level": "INFO",
  "logger": "my_app",
  "message": "用户登录成功",
  "module": "auth",
  "function": "login",
  "line": 45,
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "user_id": "user123"
}
```

### 彩色控制台

带有颜色编码的输出：
- 🔵 DEBUG - 青色
- 🟢 INFO - 绿色
- 🟡 WARNING - 黄色
- 🔴 ERROR - 红色
- 🟣 CRITICAL - 紫色

## 最佳实践

### 1. 模块级日志器

```python
# 在每个模块顶部
import logging
from kernel.logger import get_logger

logger = get_logger(__name__)  # 使用模块名作为日志器名称

def my_function():
    logger.info("函数执行")
```

### 2. 使用元数据追踪请求

```python
from kernel.logger import with_metadata, LogMetadata

# 在请求开始时设置请求ID
async def handle_request(request):
    request_id = LogMetadata.set_request_id()
    
    with with_metadata(user_id=request.user_id):
        logger.info("处理请求")
        # 所有日志都会包含request_id和user_id
```

### 3. 环境感知配置

```python
import os
from kernel.logger import (
    setup_logger,
    create_development_config,
    create_production_config,
)

# 根据环境变量选择配置
env = os.getenv("ENVIRONMENT", "development")

if env == "production":
    config = create_production_config()
else:
    config = create_development_config()

setup_logger(config)
```

### 4. 定期清理日志

```python
from kernel.logger import create_auto_cleaner
import schedule

# 创建清理器
cleaner = create_auto_cleaner(max_age_days=30)

# 每天凌晨3点清理
schedule.every().day.at("03:00").do(cleaner.run)
```

## 与 Storage 集成

### 简介

Logger 现已支持与 Storage 模块集成，实现以下功能：

- ✅ 日志自动存储为 JSON 格式
- ✅ 自动元数据提取（request_id, session_id, user_id）
- ✅ 完整的异常堆栈跟踪
- ✅ 灵活的日志查询和过滤
- ✅ 自动日志轮转和清理
- ✅ 同时支持控制台和文件存储

### 集成三种方式

**方式 1：最简单（推荐）**
```python
from kernel.logger.storage_integration import LoggerWithStorage
logger_system = LoggerWithStorage(app_name="myapp")
```

**方式 2：手动配置**
```python
from kernel.logger import setup_logger, LogStoreHandler
from kernel.storage import LogStore

log_store = LogStore(directory="logs")
handler = LogStoreHandler(log_store)
setup_logger()  # 然后添加处理器
```

**方式 3：仅控制台（不存储）**
```python
from kernel.logger import setup_logger
setup_logger()  # 保持原有行为
```

### 查看更多

- 📖 [完整集成指南](../../docs/kernel/logger/LOGGER_STORAGE_INTEGRATION.md)
- 🚀 [快速参考和代码片段](../../docs/kernel/logger/QUICK_REFERENCE.md)
- 💻 [集成示例](./storage_integration.py)

## 模块结构

```
kernel/logger/
├── __init__.py                  # 导出接口
├── core.py                      # 日志系统核心
├── config.py                    # 配置管理
├── handlers.py                  # 日志处理器（包含 LogStoreHandler）
├── renderers.py                 # 格式化器
├── metadata.py                  # 元数据管理
├── cleanup.py                   # 清理功能
├── storage_integration.py       # Logger-Storage 集成包装器
└── example.py                   # 使用示例
```

## API 参考

### 核心函数

- `setup_logger(config)` - 设置日志系统
- `get_logger(name)` - 获取日志器
- `set_level(level, logger_name)` - 设置日志级别
- `shutdown()` - 关闭日志系统
- `with_metadata(**kwargs)` - 创建元数据上下文

### 便捷函数

- `debug(message, logger_name, **kwargs)` - 记录DEBUG日志
- `info(message, logger_name, **kwargs)` - 记录INFO日志
- `warning(message, logger_name, **kwargs)` - 记录WARNING日志
- `error(message, logger_name, **kwargs)` - 记录ERROR日志
- `critical(message, logger_name, **kwargs)` - 记录CRITICAL日志
- `exception(message, logger_name, **kwargs)` - 记录异常日志

### Storage 集成 API

**LoggerWithStorage 类**

```python
# 初始化
logger_system = LoggerWithStorage(
    app_name="myapp",           # 应用名称（必需）
    log_dir="logs",             # 日志目录
    console_output=True,        # 是否输出到控制台
    json_storage=True           # 是否存储为 JSON
)

# 获取日志器
logger = logger_system.get_logger("module.name")

# 查询日志
stats = logger_system.get_logs(days=1)          # 获取统计信息
errors = logger_system.get_error_logs(days=7)  # 获取错误日志

# 维护日志
deleted = logger_system.cleanup_old_logs(days=30)  # 清理旧日志
```

**LogStoreHandler 类**

```python
# 创建处理器
handler = LogStoreHandler(
    log_store=log_store,        # LogStore 实例
    level=logging.DEBUG,        # 日志级别
    include_metadata=True,      # 包含元数据
    include_exc_info=True       # 包含异常信息
)

# 添加到日志器
logger.addHandler(handler)
```

