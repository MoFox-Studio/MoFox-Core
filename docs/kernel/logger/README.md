# MoFox Logger 日志系统文档

## 概述

MoFox Logger 是 MoFox 框架的统一日志系统，位于 kernel 层，提供与具体业务无关的日志记录能力。该系统设计遵循企业级标准，支持多种输出格式、元数据追踪、自动清理等高级功能。

### 核心特性

- **多种输出格式**：纯文本、JSON、彩色控制台、结构化键值对
- **灵活的处理器**：控制台、文件、错误文件、时间轮转、异步处理
- **元数据追踪**：支持请求ID、会话ID、用户ID和自定义字段
- **自动清理**：日志压缩、过期删除、大小限制
- **线程安全**：支持多线程并发日志记录
- **环境配置**：开发、生产、测试环境预设
- **单例模式**：全局统一的日志管理器

### 架构位置

```
src/
└── kernel/              # 内核层
    └── logger/          # 日志系统 ← 当前模块
        ├── __init__.py      # 导出接口
        ├── core.py          # 日志核心
        ├── config.py        # 配置管理
        ├── handlers.py      # 处理器
        ├── renderers.py     # 格式化器
        ├── metadata.py      # 元数据管理
        └── cleanup.py       # 清理功能
```

## 快速开始

### 基础使用

```python
from kernel.logger import setup_logger, get_logger

# 1. 设置日志系统（应用启动时）
setup_logger()

# 2. 获取日志器
logger = get_logger(__name__)

# 3. 记录日志
logger.info("应用启动成功")
logger.debug("调试信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

### 自定义配置

```python
from kernel.logger import setup_logger, get_logger, LoggerConfig

# 创建自定义配置
config = LoggerConfig(
    name="mofox",
    level="DEBUG",
    console_enabled=True,
    console_colors=True,
    file_enabled=True,
    file_path="logs/app.log",
    file_format="json",
    error_file_enabled=True
)

# 应用配置
setup_logger(config)
```

### 使用元数据

```python
from kernel.logger import get_logger, with_metadata

logger = get_logger(__name__)

# 使用上下文管理器添加元数据
with with_metadata(user_id="user123", session_id="sess456"):
    logger.info("用户执行操作")  # 日志会自动包含 user_id 和 session_id
```

## 文档目录

### 核心文档

- [配置指南](./CONFIGURATION_GUIDE.md) - 详细的配置选项和参数说明
- [API 参考](./API_REFERENCE.md) - 完整的 API 文档
- [最佳实践](./BEST_PRACTICES.md) - 使用建议和模式
- [故障排查](./TROUBLESHOOTING.md) - 常见问题和解决方案

### 进阶主题

- [元数据系统](./METADATA.md) - 元数据追踪详解
- [日志格式](./FORMATS.md) - 各种输出格式说明
- [日志清理](./CLEANUP.md) - 自动清理和维护
- [性能优化](./PERFORMANCE.md) - 性能调优建议

## 主要组件

### 1. LoggerManager（日志管理器）

全局单例，管理所有日志器和处理器。

```python
from kernel.logger import setup_logger, get_logger, shutdown

# 初始化
setup_logger(config)

# 获取日志器
logger = get_logger("module_name")

# 关闭（应用退出时）
shutdown()
```

### 2. LoggerConfig（配置类）

定义日志系统的配置参数。

```python
from kernel.logger import LoggerConfig

config = LoggerConfig(
    level="INFO",
    console_enabled=True,
    file_enabled=True,
    file_path="logs/app.log"
)
```

### 3. Handlers（处理器）

将日志输出到不同目标。

```python
from kernel.logger.handlers import (
    ConsoleHandler,      # 控制台输出
    FileHandler,         # 文件输出
    ErrorFileHandler,    # 仅错误文件
    TimedFileHandler,    # 时间轮转
    AsyncHandler         # 异步处理
)
```

### 4. Renderers（格式化器）

定义日志的输出格式。

```python
from kernel.logger.renderers import (
    PlainRenderer,       # 纯文本
    JSONRenderer,        # JSON格式
    ColoredRenderer,     # 彩色文本
    StructuredRenderer   # 结构化键值对
)
```

### 5. LogMetadata（元数据管理）

管理日志的上下文信息。

```python
from kernel.logger import LogMetadata, with_metadata

# 设置元数据
LogMetadata.set_request_id("req_123")
LogMetadata.set_user_id("user_456")

# 使用上下文
with with_metadata(request_id="req_789"):
    logger.info("操作")
```

### 6. LogCleaner（清理器）

管理日志文件的清理和维护。

```python
from kernel.logger import create_auto_cleaner

cleaner = create_auto_cleaner(
    log_directory="logs",
    max_age_days=30,
    max_size_mb=100
)
cleaner.run()
```

## 配置选项概览

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | str | "mofox" | 日志器名称 |
| `level` | str | "INFO" | 全局日志级别 |
| `console_enabled` | bool | True | 启用控制台输出 |
| `console_colors` | bool | True | 控制台彩色输出 |
| `file_enabled` | bool | True | 启用文件输出 |
| `file_path` | str | "logs/mofox.log" | 日志文件路径 |
| `file_format` | str | "plain" | 文件格式（plain/json） |
| `error_file_enabled` | bool | True | 启用错误文件 |
| `include_metadata` | bool | True | 包含元数据 |
| `async_logging` | bool | False | 异步日志 |

完整配置选项请参考 [配置指南](./CONFIGURATION_GUIDE.md)。

## 使用场景

### 1. Web 应用

```python
from kernel.logger import setup_logger, get_logger, with_metadata
import uuid

# 初始化
setup_logger()
logger = get_logger(__name__)

# 在请求处理中
async def handle_request(request):
    request_id = str(uuid.uuid4())
    
    with with_metadata(
        request_id=request_id,
        user_id=request.user.id,
        ip=request.client.host
    ):
        logger.info(f"处理请求: {request.url}")
        try:
            # 业务逻辑
            result = await process_request(request)
            logger.info("请求处理成功")
            return result
        except Exception as e:
            logger.exception("请求处理失败")
            raise
```

### 2. 后台任务

```python
from kernel.logger import get_logger, LogMetadata

logger = get_logger(__name__)

def background_task(task_id):
    LogMetadata.set_custom("task_id", task_id)
    
    logger.info("任务开始")
    try:
        # 执行任务
        logger.debug("任务进度: 50%")
        # ...
        logger.info("任务完成")
    except Exception as e:
        logger.exception("任务失败")
    finally:
        LogMetadata.clear()
```

### 3. 微服务

```python
from kernel.logger import setup_logger, create_production_config

# 生产环境配置
config = create_production_config()
config.file_format = "json"  # JSON便于日志收集
config.async_logging = True   # 异步提高性能

setup_logger(config)
```

## 日志级别

日志级别从低到高：

| 级别 | 值 | 使用场景 |
|------|-------|----------|
| DEBUG | 10 | 详细的调试信息 |
| INFO | 20 | 一般信息记录 |
| WARNING | 30 | 警告信息 |
| ERROR | 40 | 错误信息 |
| CRITICAL | 50 | 严重错误 |

```python
logger.debug("变量值: x=%s", x)
logger.info("用户登录成功")
logger.warning("内存使用率超过80%")
logger.error("数据库连接失败")
logger.critical("系统崩溃")
```

## 输出格式示例

### 纯文本格式

```
[2026-01-06 10:30:15.123] [INFO] [my_app] [req=a1b2c3d4] 用户登录成功
```

### JSON 格式

```json
{
  "timestamp": "2026-01-06T10:30:15.123456",
  "level": "INFO",
  "logger": "my_app",
  "message": "用户登录成功",
  "module": "auth",
  "function": "login",
  "line": 45,
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 彩色控制台

带颜色编码的可读输出（终端支持时）。

## 性能考虑

- **同步日志**：简单直接，适合大多数场景
- **异步日志**：高性能，适合高并发场景，但略增复杂度
- **文件轮转**：避免单个文件过大
- **日志级别**：生产环境使用 INFO 或更高级别

```python
# 高性能配置
config = LoggerConfig(
    async_logging=True,           # 异步处理
    file_max_bytes=50*1024*1024,  # 50MB轮转
    file_backup_count=10          # 保留10个备份
)
```

## 与其他 kernel 模块集成

### 与 storage 集成

```python
from kernel.storage import LogStore
from kernel.logger import get_logger

# 日志持久化
logger = get_logger(__name__)
log_store = LogStore("data/persistent_logs")

def log_and_persist(level, message, **kwargs):
    # 记录到日志系统
    getattr(logger, level.lower())(message)
    
    # 持久化到存储
    log_store.add_log({
        "level": level,
        "message": message,
        **kwargs
    })
```

### 与 config 集成

```python
from kernel.config import Config
from kernel.logger import setup_logger, LoggerConfig

# 从配置系统读取日志配置
config = Config()
log_level = config.get("log_level", "INFO")

logger_config = LoggerConfig(level=log_level)
setup_logger(logger_config)
```

### 与 concurrency 集成

```python
from kernel.concurrency import TaskManager
from kernel.logger import get_logger, LogMetadata

logger = get_logger(__name__)

async def async_task(task_id):
    LogMetadata.set_custom("task_id", task_id)
    logger.info("异步任务开始")
    # 任务逻辑
    logger.info("异步任务完成")
```

## 开发与生产环境

### 开发环境

```python
from kernel.logger import create_development_config, setup_logger

config = create_development_config()
# DEBUG级别，彩色控制台，详细输出
setup_logger(config)
```

### 生产环境

```python
from kernel.logger import create_production_config, setup_logger

config = create_production_config()
# INFO级别，JSON格式，异步处理，禁用控制台
setup_logger(config)
```

### 测试环境

```python
from kernel.logger import create_testing_config, setup_logger

config = create_testing_config()
# WARNING级别，最小化输出
setup_logger(config)
```

## 故障排查

### 日志未输出

1. 检查日志级别设置
2. 确认处理器已启用
3. 验证文件路径权限

### 性能问题

1. 启用异步日志
2. 调整日志级别
3. 减少元数据使用

### 文件过大

1. 启用自动轮转
2. 配置自动清理
3. 使用压缩功能

详见 [故障排查指南](./TROUBLESHOOTING.md)。

## 扩展开发

### 自定义渲染器

```python
from kernel.logger.renderers import BaseRenderer

class CustomRenderer(BaseRenderer):
    def format(self, record):
        # 自定义格式化逻辑
        return f"[CUSTOM] {record.getMessage()}"
```

### 自定义处理器

```python
from kernel.logger.handlers import FileHandler

class DatabaseHandler(FileHandler):
    def emit(self, record):
        # 将日志写入数据库
        pass
```

## 最佳实践

1. **在模块级别获取日志器**
   ```python
   logger = get_logger(__name__)
   ```

2. **使用元数据追踪请求**
   ```python
   with with_metadata(request_id=req_id):
       # 操作代码
   ```

3. **合理设置日志级别**
   - 开发：DEBUG
   - 生产：INFO
   - 错误追踪：ERROR

4. **定期清理日志**
   ```python
   cleaner = create_auto_cleaner(max_age_days=30)
   cleaner.run()
   ```

5. **异常使用 exception()**
   ```python
   try:
       # 代码
   except Exception:
       logger.exception("操作失败")  # 自动记录堆栈
   ```

## 贡献指南

欢迎贡献代码和文档改进。请遵循：

1. 保持向后兼容
2. 编写单元测试
3. 更新文档
4. 遵循代码风格

## 许可证

MIT License

## 版本历史

- **1.0.0** (2026-01-06)
  - 初始版本
  - 核心功能实现
  - 完整文档

## 支持

- 问题反馈：GitHub Issues
- 文档：`docs/kernel/logger/`
- 示例代码：`src/kernel/logger/example.py`
