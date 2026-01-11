# Logger API 参考文档

完整的 MoFox Logger API 文档。

## 目录

- [核心函数](#核心函数)
- [配置类](#配置类)
- [日志器管理](#日志器管理)
- [元数据管理](#元数据管理)
- [处理器](#处理器)
- [格式化器](#格式化器)
- [清理功能](#清理功能)

## 核心函数

### setup_logger(config)

设置日志系统。

**参数:**
- `config` (LoggerConfig, optional): 日志配置对象，默认为 None（使用默认配置）

**返回:** None

**示例:**
```python
from kernel.logger import setup_logger, LoggerConfig

# 使用默认配置
setup_logger()

# 使用自定义配置
config = LoggerConfig(level="DEBUG")
setup_logger(config)
```

---

### get_logger(name)

获取日志器实例。

**参数:**
- `name` (str, optional): 日志器名称，默认为 None（返回根日志器）

**返回:** `logging.Logger` - 日志器对象

**示例:**
```python
from kernel.logger import get_logger

# 使用模块名
logger = get_logger(__name__)

# 使用自定义名称
logger = get_logger("my_module")

# 获取根日志器
root_logger = get_logger()
```

---

### set_level(level, logger_name)

设置日志级别。

**参数:**
- `level` (str): 日志级别（"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"）
- `logger_name` (str, optional): 日志器名称，默认为 None（设置根日志器）

**返回:** None

**示例:**
```python
from kernel.logger import set_level

# 设置全局级别
set_level("DEBUG")

# 设置特定日志器级别
set_level("WARNING", "my_module")
```

---

### shutdown()

关闭日志系统。

**参数:** 无

**返回:** None

**示例:**
```python
from kernel.logger import shutdown

# 应用退出时调用
shutdown()
```

---

### with_metadata(**kwargs)

创建元数据上下文管理器。

**参数:**
- `**kwargs`: 元数据键值对

**返回:** `MetadataContext` - 上下文管理器

**示例:**
```python
from kernel.logger import get_logger, with_metadata

logger = get_logger(__name__)

with with_metadata(user_id="123", session_id="abc"):
    logger.info("操作")  # 日志包含元数据
```

---

## 便捷日志函数

### debug(message, logger_name, **kwargs)

记录 DEBUG 级别日志。

**参数:**
- `message` (str): 日志消息
- `logger_name` (str, optional): 日志器名称
- `**kwargs`: 额外参数

```python
from kernel.logger import debug

debug("调试信息")
debug("变量值", logger_name="my_module")
```

### info(message, logger_name, **kwargs)

记录 INFO 级别日志。

```python
from kernel.logger import info

info("应用启动")
```

### warning(message, logger_name, **kwargs)

记录 WARNING 级别日志。

```python
from kernel.logger import warning

warning("内存使用率高")
```

### error(message, logger_name, **kwargs)

记录 ERROR 级别日志。

```python
from kernel.logger import error

error("数据库连接失败")
```

### critical(message, logger_name, **kwargs)

记录 CRITICAL 级别日志。

```python
from kernel.logger import critical

critical("系统崩溃")
```

### exception(message, logger_name, **kwargs)

记录异常日志（自动包含堆栈信息）。

```python
from kernel.logger import exception

try:
    # 代码
except Exception:
    exception("操作失败")
```

---

## 配置类

### LoggerConfig

日志配置类。

**属性:**

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| name | str | "mofox" | 日志器名称 |
| level | str | "INFO" | 日志级别 |
| console_enabled | bool | True | 启用控制台 |
| console_level | str | "INFO" | 控制台级别 |
| console_colors | bool | True | 彩色输出 |
| file_enabled | bool | True | 启用文件 |
| file_level | str | "DEBUG" | 文件级别 |
| file_path | str | "logs/mofox.log" | 文件路径 |
| file_max_bytes | int | 10MB | 文件大小 |
| file_backup_count | int | 5 | 备份数量 |
| file_format | str | "plain" | 文件格式 |
| error_file_enabled | bool | True | 启用错误文件 |
| include_metadata | bool | True | 包含元数据 |
| async_logging | bool | False | 异步日志 |

**方法:**

#### to_dict()

转换为字典。

**返回:** `Dict[str, Any]`

```python
config = LoggerConfig()
config_dict = config.to_dict()
```

#### from_dict(data)

从字典创建配置。

**参数:**
- `data` (dict): 配置字典

**返回:** `LoggerConfig`

```python
config = LoggerConfig.from_dict({"level": "DEBUG"})
```

#### get_level_value(level_str)

获取日志级别数值。

**参数:**
- `level_str` (str): 级别字符串

**返回:** `int`

```python
config = LoggerConfig()
level = config.get_level_value("INFO")  # 20
```

---

### 预设配置函数

#### create_default_config()

创建默认配置。

**返回:** `LoggerConfig`

```python
from kernel.logger import create_default_config

config = create_default_config()
```

#### create_development_config()

创建开发环境配置。

**返回:** `LoggerConfig`

```python
from kernel.logger import create_development_config

config = create_development_config()
```

#### create_production_config()

创建生产环境配置。

**返回:** `LoggerConfig`

```python
from kernel.logger import create_production_config

config = create_production_config()
```

#### create_testing_config()

创建测试环境配置。

**返回:** `LoggerConfig`

```python
from kernel.logger import create_testing_config

config = create_testing_config()
```

---

## 日志器管理

### LoggerManager

日志管理器（单例）。

**方法:**

#### setup(config)

设置日志系统。

**参数:**
- `config` (LoggerConfig, optional): 配置对象

**返回:** None

```python
from kernel.logger.core import LoggerManager

manager = LoggerManager()
manager.setup(config)
```

#### get_logger(name)

获取日志器。

**参数:**
- `name` (str, optional): 日志器名称

**返回:** `logging.Logger`

```python
logger = manager.get_logger("my_module")
```

#### set_level(level, logger_name)

设置日志级别。

**参数:**
- `level` (str): 日志级别
- `logger_name` (str, optional): 日志器名称

**返回:** None

```python
manager.set_level("DEBUG")
```

#### shutdown()

关闭日志系统。

**返回:** None

```python
manager.shutdown()
```

#### get_config()

获取当前配置。

**返回:** `LoggerConfig`

```python
config = manager.get_config()
```

---

## 元数据管理

### LogMetadata

元数据管理类（静态方法）。

**方法:**

#### set_request_id(request_id)

设置请求ID。

**参数:**
- `request_id` (str, optional): 请求ID，None 时自动生成

**返回:** `str` - 请求ID

```python
from kernel.logger import LogMetadata

request_id = LogMetadata.set_request_id()
# 或指定ID
LogMetadata.set_request_id("req_123")
```

#### get_request_id()

获取请求ID。

**返回:** `str | None`

```python
request_id = LogMetadata.get_request_id()
```

#### set_session_id(session_id)

设置会话ID。

**参数:**
- `session_id` (str): 会话ID

**返回:** None

```python
LogMetadata.set_session_id("sess_456")
```

#### get_session_id()

获取会话ID。

**返回:** `str | None`

```python
session_id = LogMetadata.get_session_id()
```

#### set_user_id(user_id)

设置用户ID。

**参数:**
- `user_id` (str): 用户ID

**返回:** None

```python
LogMetadata.set_user_id("user_789")
```

#### get_user_id()

获取用户ID。

**返回:** `str | None`

```python
user_id = LogMetadata.get_user_id()
```

#### set_custom(key, value)

设置自定义元数据。

**参数:**
- `key` (str): 键
- `value` (Any): 值

**返回:** None

```python
LogMetadata.set_custom("ip_address", "192.168.1.1")
```

#### get_custom(key, default)

获取自定义元数据。

**参数:**
- `key` (str): 键
- `default` (Any, optional): 默认值

**返回:** `Any`

```python
ip = LogMetadata.get_custom("ip_address", "unknown")
```

#### get_all_custom()

获取所有自定义元数据。

**返回:** `Dict[str, Any]`

```python
custom = LogMetadata.get_all_custom()
```

#### clear()

清除所有元数据。

**返回:** None

```python
LogMetadata.clear()
```

#### get_all()

获取所有元数据。

**返回:** `Dict[str, Any]`

```python
all_metadata = LogMetadata.get_all()
```

---

### MetadataContext

元数据上下文管理器。

**构造函数:**

```python
from kernel.logger import MetadataContext

context = MetadataContext(
    request_id="req_123",
    user_id="user_456",
    custom_field="value"
)
```

**使用:**

```python
with MetadataContext(user_id="123"):
    # 代码
    pass
```

---

## 处理器

### ConsoleHandler

控制台日志处理器。

**构造函数:**

```python
from kernel.logger.handlers import ConsoleHandler

handler = ConsoleHandler(
    level=logging.INFO,
    use_colors=True,
    include_metadata=True,
    stream=None  # 默认 sys.stderr
)
```

---

### FileHandler

文件日志处理器（大小轮转）。

**构造函数:**

```python
from kernel.logger.handlers import FileHandler

handler = FileHandler(
    filename="logs/app.log",
    level=logging.DEBUG,
    max_bytes=10*1024*1024,  # 10MB
    backup_count=5,
    encoding='utf-8',
    use_json=False,
    include_metadata=True
)
```

---

### TimedFileHandler

时间轮转文件处理器。

**构造函数:**

```python
from kernel.logger.handlers import TimedFileHandler

handler = TimedFileHandler(
    filename="logs/app.log",
    level=logging.DEBUG,
    when='midnight',  # 轮转时间
    interval=1,
    backup_count=30,
    encoding='utf-8',
    use_json=False,
    include_metadata=True
)
```

---

### ErrorFileHandler

错误日志处理器。

**构造函数:**

```python
from kernel.logger.handlers import ErrorFileHandler

handler = ErrorFileHandler(
    filename="logs/error.log",
    max_bytes=10*1024*1024,
    backup_count=5,
    encoding='utf-8',
    use_json=False,
    include_metadata=True
)
```

---

### AsyncHandler

异步日志处理器。

**构造函数:**

```python
from kernel.logger.handlers import AsyncHandler, FileHandler

# 包装其他处理器
file_handler = FileHandler("logs/app.log")
async_handler = AsyncHandler(
    handler=file_handler,
    queue_size=1000
)
```

**方法:**

#### close()

关闭处理器。

```python
async_handler.close()
```

---

## 格式化器

### PlainRenderer

纯文本渲染器。

**构造函数:**

```python
from kernel.logger.renderers import PlainRenderer

renderer = PlainRenderer(include_metadata=True)
```

**方法:**

#### format(record)

格式化日志记录。

**参数:**
- `record` (LogRecord): 日志记录

**返回:** `str`

---

### JSONRenderer

JSON 格式渲染器。

**构造函数:**

```python
from kernel.logger.renderers import JSONRenderer

renderer = JSONRenderer(
    include_metadata=True,
    indent=None  # 紧凑格式
)
```

---

### ColoredRenderer

彩色渲染器。

**构造函数:**

```python
from kernel.logger.renderers import ColoredRenderer

renderer = ColoredRenderer(
    include_metadata=True,
    use_colors=True
)
```

---

### StructuredRenderer

结构化键值对渲染器。

**构造函数:**

```python
from kernel.logger.renderers import StructuredRenderer

renderer = StructuredRenderer(include_metadata=True)
```

---

## 清理功能

### LogCleaner

日志清理器。

**构造函数:**

```python
from kernel.logger import LogCleaner

cleaner = LogCleaner(log_directory="logs")
```

**方法:**

#### get_log_files(pattern)

获取日志文件列表。

**参数:**
- `pattern` (str): 匹配模式，默认 "*.log*"

**返回:** `List[Path]`

```python
files = cleaner.get_log_files("*.log")
```

#### delete_old_logs(max_age_days, pattern)

删除过期日志。

**参数:**
- `max_age_days` (int): 最大保留天数
- `pattern` (str): 文件模式

**返回:** `int` - 删除的文件数

```python
deleted = cleaner.delete_old_logs(max_age_days=30)
```

#### compress_logs(pattern, keep_original)

压缩日志文件。

**参数:**
- `pattern` (str): 文件模式
- `keep_original` (bool): 是否保留原文件

**返回:** `int` - 压缩的文件数

```python
compressed = cleaner.compress_logs(keep_original=False)
```

#### cleanup_by_size(max_size_mb)

按大小清理日志。

**参数:**
- `max_size_mb` (int): 最大目录大小（MB）

**返回:** `int` - 删除的文件数

```python
deleted = cleaner.cleanup_by_size(max_size_mb=100)
```

#### archive_logs(archive_path, max_age_days)

归档日志文件。

**参数:**
- `archive_path` (str, optional): 归档文件路径
- `max_age_days` (int): 归档多少天前的日志

**返回:** `Path | None` - 归档文件路径

```python
archive = cleaner.archive_logs(max_age_days=7)
```

#### get_statistics()

获取日志统计信息。

**返回:** `dict`

```python
stats = cleaner.get_statistics()
print(f"总文件数: {stats['total_files']}")
print(f"总大小: {stats['total_size_mb']} MB")
```

---

### AutoCleaner

自动日志清理器。

**构造函数:**

```python
from kernel.logger import AutoCleaner

cleaner = AutoCleaner(
    log_directory="logs",
    max_age_days=30,
    max_size_mb=100,
    compress_after_days=7
)
```

**方法:**

#### run()

执行自动清理。

**返回:** `dict` - 清理结果

```python
results = cleaner.run()
print(f"删除: {results['deleted_old']}")
print(f"压缩: {results['compressed']}")
```

---

### 清理便捷函数

#### create_cleaner(log_directory)

创建日志清理器。

**参数:**
- `log_directory` (str): 日志目录

**返回:** `LogCleaner`

```python
from kernel.logger import create_cleaner

cleaner = create_cleaner("logs")
```

#### create_auto_cleaner(log_directory, max_age_days, max_size_mb, compress_after_days)

创建自动清理器。

**参数:**
- `log_directory` (str): 日志目录
- `max_age_days` (int): 最大保留天数
- `max_size_mb` (int): 最大目录大小
- `compress_after_days` (int): 多少天后压缩

**返回:** `AutoCleaner`

```python
from kernel.logger import create_auto_cleaner

cleaner = create_auto_cleaner(
    log_directory="logs",
    max_age_days=30,
    max_size_mb=100,
    compress_after_days=7
)
```

---

## 异常类

目前日志系统使用 Python 标准异常，未定义自定义异常。

---

## 类型定义

### LogRecord

Python 标准 `logging.LogRecord` 对象。

**重要属性:**
- `name`: 日志器名称
- `levelname`: 级别名称
- `levelno`: 级别数值
- `pathname`: 文件路径
- `filename`: 文件名
- `module`: 模块名
- `lineno`: 行号
- `funcName`: 函数名
- `created`: 创建时间（时间戳）
- `msecs`: 毫秒
- `msg`: 消息模板
- `args`: 消息参数
- `exc_info`: 异常信息

---

## 使用示例

### 完整示例

```python
from kernel.logger import (
    setup_logger,
    get_logger,
    LoggerConfig,
    with_metadata,
    LogMetadata,
    create_auto_cleaner
)

# 1. 设置日志系统
config = LoggerConfig(
    level="DEBUG",
    console_colors=True,
    file_enabled=True
)
setup_logger(config)

# 2. 获取日志器
logger = get_logger(__name__)

# 3. 记录基本日志
logger.info("应用启动")

# 4. 使用元数据
with with_metadata(user_id="123", action="login"):
    logger.info("用户登录")

# 5. 手动设置元数据
LogMetadata.set_request_id("req_456")
logger.debug("处理请求")

# 6. 异常日志
try:
    1 / 0
except Exception:
    logger.exception("计算错误")

# 7. 清理日志
cleaner = create_auto_cleaner(max_age_days=30)
cleaner.run()
```

---

## 相关文档

- [配置指南](./CONFIGURATION_GUIDE.md)
- [最佳实践](./BEST_PRACTICES.md)
- [故障排查](./TROUBLESHOOTING.md)
