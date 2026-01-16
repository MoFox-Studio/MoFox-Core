# Logger 配置指南

本文档详细说明 MoFox Logger 的所有配置选项和使用方法。

## 目录

- [配置类 LoggerConfig](#配置类-loggerconfig)
- [配置参数详解](#配置参数详解)
- [预设配置](#预设配置)
- [配置管理器](#配置管理器)
- [运行时配置](#运行时配置)
- [配置示例](#配置示例)

## 配置类 LoggerConfig

`LoggerConfig` 是日志系统的配置类，使用 dataclass 实现。

```python
from kernel.logger import LoggerConfig

config = LoggerConfig(
    name="mofox",
    level="INFO",
    console_enabled=True,
    # ... 其他配置
)
```

## 配置参数详解

### 基本配置

#### name
- **类型**: `str`
- **默认值**: `"mofox"`
- **说明**: 日志器名称，用于标识日志来源

```python
config = LoggerConfig(name="my_application")
```

#### level
- **类型**: `str`
- **默认值**: `"INFO"`
- **可选值**: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
- **说明**: 全局日志级别，低于此级别的日志不会被记录

```python
# 开发环境
config = LoggerConfig(level="DEBUG")

# 生产环境
config = LoggerConfig(level="INFO")
```

### 控制台配置

#### console_enabled
- **类型**: `bool`
- **默认值**: `True`
- **说明**: 是否启用控制台输出

```python
# 生产环境通常禁用控制台
config = LoggerConfig(console_enabled=False)
```

#### console_level
- **类型**: `str`
- **默认值**: `"INFO"`
- **可选值**: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
- **说明**: 控制台输出的日志级别

```python
# 控制台只显示警告及以上级别
config = LoggerConfig(
    level="DEBUG",           # 全局DEBUG
    console_level="WARNING"  # 控制台WARNING
)
```

#### console_colors
- **类型**: `bool`
- **默认值**: `True`
- **说明**: 是否使用彩色输出

```python
# 禁用彩色（适用于不支持ANSI的环境）
config = LoggerConfig(console_colors=False)
```

### 文件配置

#### file_enabled
- **类型**: `bool`
- **默认值**: `True`
- **说明**: 是否启用文件输出

```python
# 仅控制台输出
config = LoggerConfig(file_enabled=False)
```

#### file_level
- **类型**: `str`
- **默认值**: `"DEBUG"`
- **说明**: 文件输出的日志级别

```python
# 文件记录所有级别
config = LoggerConfig(file_level="DEBUG")
```

#### file_path
- **类型**: `str`
- **默认值**: `"logs/mofox.log"`
- **说明**: 日志文件路径，支持相对路径和绝对路径

```python
# 自定义路径
config = LoggerConfig(file_path="logs/app.log")

# 绝对路径
config = LoggerConfig(file_path="/var/log/mofox/app.log")
```

#### file_max_bytes
- **类型**: `int`
- **默认值**: `10 * 1024 * 1024` (10MB)
- **说明**: 单个日志文件的最大大小（字节）

```python
# 50MB
config = LoggerConfig(file_max_bytes=50 * 1024 * 1024)
```

#### file_backup_count
- **类型**: `int`
- **默认值**: `5`
- **说明**: 保留的备份文件数量

```python
# 保留10个备份文件
config = LoggerConfig(file_backup_count=10)
```

#### file_format
- **类型**: `str`
- **默认值**: `"plain"`
- **可选值**: `"plain"`, `"json"`
- **说明**: 文件输出格式

```python
# JSON格式（便于日志分析）
config = LoggerConfig(file_format="json")
```

### 错误文件配置

#### error_file_enabled
- **类型**: `bool`
- **默认值**: `True`
- **说明**: 是否启用单独的错误日志文件

```python
# 禁用错误文件
config = LoggerConfig(error_file_enabled=False)
```

#### error_file_path
- **类型**: `str`
- **默认值**: `"logs/error.log"`
- **说明**: 错误日志文件路径

```python
config = LoggerConfig(error_file_path="logs/errors.log")
```

#### error_file_max_bytes
- **类型**: `int`
- **默认值**: `10 * 1024 * 1024` (10MB)
- **说明**: 错误日志文件最大大小

#### error_file_backup_count
- **类型**: `int`
- **默认值**: `5`
- **说明**: 错误日志备份数量

### 时间轮转配置

#### timed_file_enabled
- **类型**: `bool`
- **默认值**: `False`
- **说明**: 是否启用按时间轮转的日志文件

```python
# 启用时间轮转
config = LoggerConfig(timed_file_enabled=True)
```

#### timed_file_path
- **类型**: `str`
- **默认值**: `"logs/mofox_timed.log"`
- **说明**: 时间轮转日志文件路径

#### timed_file_when
- **类型**: `str`
- **默认值**: `"midnight"`
- **可选值**: 
  - `"S"`: 每秒
  - `"M"`: 每分钟
  - `"H"`: 每小时
  - `"D"`: 每天
  - `"midnight"`: 每天午夜
  - `"W0"` - `"W6"`: 每周的某一天（0=Monday）
- **说明**: 轮转时间单位

```python
# 每小时轮转
config = LoggerConfig(
    timed_file_enabled=True,
    timed_file_when="H"
)

# 每天午夜轮转
config = LoggerConfig(
    timed_file_enabled=True,
    timed_file_when="midnight"
)
```

#### timed_file_interval
- **类型**: `int`
- **默认值**: `1`
- **说明**: 轮转间隔

```python
# 每3小时轮转
config = LoggerConfig(
    timed_file_enabled=True,
    timed_file_when="H",
    timed_file_interval=3
)
```

#### timed_file_backup_count
- **类型**: `int`
- **默认值**: `30`
- **说明**: 时间轮转备份数量

### 元数据配置

#### include_metadata
- **类型**: `bool`
- **默认值**: `True`
- **说明**: 是否在日志中包含元数据（请求ID、用户ID等）

```python
# 禁用元数据（节省空间）
config = LoggerConfig(include_metadata=False)
```

### 异步配置

#### async_logging
- **类型**: `bool`
- **默认值**: `False`
- **说明**: 是否使用异步日志（提高性能）

```python
# 高性能场景
config = LoggerConfig(async_logging=True)
```

#### async_queue_size
- **类型**: `int`
- **默认值**: `1000`
- **说明**: 异步日志队列大小

```python
# 更大的队列
config = LoggerConfig(
    async_logging=True,
    async_queue_size=5000
)
```

### 第三方库日志配置

#### third_party_levels
- **类型**: `Dict[str, str]`
- **默认值**: 
  ```python
  {
      "urllib3": "WARNING",
      "httpx": "WARNING",
      "httpcore": "WARNING",
      "asyncio": "WARNING",
  }
  ```
- **说明**: 第三方库的日志级别

```python
config = LoggerConfig(
    third_party_levels={
        "urllib3": "ERROR",
        "sqlalchemy": "INFO",
        "httpx": "DEBUG"
    }
)
```

## 预设配置

### create_default_config()

默认配置，适合一般场景。

```python
from kernel.logger import create_default_config, setup_logger

config = create_default_config()
setup_logger(config)
```

### create_development_config()

开发环境配置。

```python
from kernel.logger import create_development_config, setup_logger

config = create_development_config()
setup_logger(config)
```

**特点**:
- DEBUG 级别
- 彩色控制台输出
- 详细日志
- 文件和控制台都启用

### create_production_config()

生产环境配置。

```python
from kernel.logger import create_production_config, setup_logger

config = create_production_config()
setup_logger(config)
```

**特点**:
- INFO 级别
- JSON 格式
- 异步日志
- 禁用控制台
- 启用时间轮转

### create_testing_config()

测试环境配置。

```python
from kernel.logger import create_testing_config, setup_logger

config = create_testing_config()
setup_logger(config)
```

**特点**:
- WARNING 级别
- 最小化输出
- 禁用文件输出

## 配置管理器

### ConfigManager

单例配置管理器，用于全局配置管理。

```python
from kernel.logger.config import ConfigManager

manager = ConfigManager()

# 设置配置
manager.set_config(config)

# 获取配置
current_config = manager.get_config()

# 更新配置项
manager.update_config(level="DEBUG", console_colors=False)

# 重置配置
manager.reset_config()
```

## 运行时配置

### 动态修改日志级别

```python
from kernel.logger import set_level

# 修改全局级别
set_level("DEBUG")

# 修改特定日志器级别
set_level("WARNING", logger_name="my_module")
```

### 从环境变量读取配置

```python
import os
from kernel.logger import LoggerConfig, setup_logger

config = LoggerConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    file_path=os.getenv("LOG_FILE", "logs/app.log"),
    console_enabled=os.getenv("LOG_CONSOLE", "true").lower() == "true"
)

setup_logger(config)
```

### 从配置文件读取

```python
import json
from kernel.logger import LoggerConfig, setup_logger

# 读取JSON配置
with open("config/logger.json") as f:
    config_dict = json.load(f)

config = LoggerConfig.from_dict(config_dict)
setup_logger(config)
```

配置文件示例 (logger.json):
```json
{
  "name": "mofox",
  "level": "INFO",
  "console_enabled": true,
  "console_colors": true,
  "file_enabled": true,
  "file_path": "logs/app.log",
  "file_format": "json",
  "async_logging": true
}
```

## 配置示例

### 开发环境完整配置

```python
from kernel.logger import LoggerConfig, setup_logger

config = LoggerConfig(
    name="mofox_dev",
    level="DEBUG",
    
    # 控制台
    console_enabled=True,
    console_level="DEBUG",
    console_colors=True,
    
    # 文件
    file_enabled=True,
    file_level="DEBUG",
    file_path="logs/dev.log",
    file_max_bytes=10 * 1024 * 1024,
    file_backup_count=3,
    file_format="plain",
    
    # 错误文件
    error_file_enabled=True,
    error_file_path="logs/error.log",
    
    # 元数据
    include_metadata=True,
    
    # 第三方库
    third_party_levels={
        "urllib3": "WARNING",
        "httpx": "INFO"
    }
)

setup_logger(config)
```

### 生产环境完整配置

```python
from kernel.logger import LoggerConfig, setup_logger

config = LoggerConfig(
    name="mofox_prod",
    level="INFO",
    
    # 控制台（禁用）
    console_enabled=False,
    
    # 文件
    file_enabled=True,
    file_level="INFO",
    file_path="/var/log/mofox/app.log",
    file_max_bytes=50 * 1024 * 1024,
    file_backup_count=10,
    file_format="json",
    
    # 错误文件
    error_file_enabled=True,
    error_file_path="/var/log/mofox/error.log",
    error_file_max_bytes=50 * 1024 * 1024,
    error_file_backup_count=10,
    
    # 时间轮转
    timed_file_enabled=True,
    timed_file_path="/var/log/mofox/timed.log",
    timed_file_when="midnight",
    timed_file_backup_count=30,
    
    # 元数据
    include_metadata=True,
    
    # 异步
    async_logging=True,
    async_queue_size=5000,
    
    # 第三方库
    third_party_levels={
        "urllib3": "ERROR",
        "httpx": "WARNING",
        "sqlalchemy": "WARNING"
    }
)

setup_logger(config)
```

### 微服务配置

```python
from kernel.logger import LoggerConfig, setup_logger

config = LoggerConfig(
    name="microservice",
    level="INFO",
    
    # JSON格式便于日志收集
    file_format="json",
    
    # 异步提高性能
    async_logging=True,
    
    # 包含元数据用于追踪
    include_metadata=True,
    
    # 时间轮转便于管理
    timed_file_enabled=True,
    timed_file_when="H",
    timed_file_interval=1
)

setup_logger(config)
```

### Docker 环境配置

```python
from kernel.logger import LoggerConfig, setup_logger

config = LoggerConfig(
    name="docker_app",
    level="INFO",
    
    # 主要输出到stdout（容器日志）
    console_enabled=True,
    console_colors=False,  # 容器环境禁用颜色
    
    # 文件作为备份
    file_enabled=True,
    file_path="/app/logs/app.log",
    
    # JSON格式便于日志收集系统
    file_format="json"
)

setup_logger(config)
```

### 测试配置

```python
from kernel.logger import LoggerConfig, setup_logger

config = LoggerConfig(
    name="test",
    level="WARNING",  # 测试时减少日志
    
    console_enabled=True,
    console_colors=False,
    
    # 禁用文件输出
    file_enabled=False,
    error_file_enabled=False,
    
    # 禁用元数据
    include_metadata=False
)

setup_logger(config)
```

## 配置验证

### 验证配置有效性

```python
def validate_config(config: LoggerConfig) -> bool:
    """验证配置是否有效"""
    
    # 检查日志级别
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.level not in valid_levels:
        return False
    
    # 检查文件路径
    if config.file_enabled:
        from pathlib import Path
        log_path = Path(config.file_path)
        if not log_path.parent.exists():
            log_path.parent.mkdir(parents=True)
    
    return True

# 使用
if validate_config(config):
    setup_logger(config)
else:
    print("配置无效")
```

## 配置导出和导入

### 导出配置

```python
import json
from kernel.logger.config import ConfigManager

manager = ConfigManager()
config = manager.get_config()

# 导出为字典
config_dict = config.to_dict()

# 保存为JSON
with open("logger_config.json", "w") as f:
    json.dump(config_dict, f, indent=2)
```

### 导入配置

```python
import json
from kernel.logger import LoggerConfig, setup_logger

# 从JSON加载
with open("logger_config.json") as f:
    config_dict = json.load(f)

config = LoggerConfig.from_dict(config_dict)
setup_logger(config)
```

## 最佳配置建议

1. **开发环境**: 使用 DEBUG 级别，彩色控制台，详细输出
2. **生产环境**: 使用 INFO 级别，JSON 格式，异步日志
3. **高性能场景**: 启用异步日志，增大队列大小
4. **存储受限**: 减小文件大小，减少备份数量，启用压缩
5. **日志分析**: 使用 JSON 格式，包含元数据
6. **问题追踪**: 单独的错误文件，保留更多备份

## 相关文档

- [API 参考](./API_REFERENCE.md)
- [最佳实践](./BEST_PRACTICES.md)
- [故障排查](./TROUBLESHOOTING.md)
