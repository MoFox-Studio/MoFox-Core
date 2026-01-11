# Config 模块文档

MoFox Config 模块提供灵活的配置管理功能，支持多种配置源和格式。

## 📚 文档导航

- [API 参考](API_REFERENCE.md) - 完整的 API 文档
- [最佳实践](BEST_PRACTICES.md) - 使用建议和最佳实践
- [快速参考](QUICK_REFERENCE.md) - 常用功能速查

## 🎯 核心特性

### 多种配置源
- **文件** - JSON、YAML、ENV、Python
- **环境变量** - 支持前缀过滤
- **字典** - 直接从字典创建
- **合并** - 多个配置源合并

### 灵活的配置格式
```python
# JSON
{"database": {"host": "localhost", "port": 5432}}

# YAML
database:
  host: localhost
  port: 5432

# ENV
DATABASE_HOST=localhost
DATABASE_PORT=5432

# Python
DATABASE_HOST = "localhost"
DATABASE_PORT = 5432
```

### 强大的功能
- ✅ 嵌套配置（点号分隔访问）
- ✅ 配置验证
- ✅ 自动类型推断
- ✅ 配置热重载
- ✅ 多配置管理
- ✅ 日志集成
- ✅ 元数据追踪

## 🚀 快速开始

### 安装依赖

```bash
# 基础使用无需额外依赖

# YAML 支持（可选）
pip install pyyaml
```

### 基础使用

```python
from kernel.config import Config

# 创建配置
config = Config(
    database_host="localhost",
    database_port=5432,
    debug=True
)

# 获取配置
host = config.get("database_host")
port = config.get("database_port", 3306)  # 带默认值

# 设置配置
config.set("database_host", "127.0.0.1")

# 检查配置
if "debug" in config:
    print("Debug mode enabled")
```

### 从文件加载

```python
from kernel.config import Config

# 从 JSON 加载
config = Config.from_file("config.json")

# 从 YAML 加载
config = Config.from_file("config.yaml")

# 从 ENV 加载
config = Config.from_file(".env")

# 从 Python 文件加载
config = Config.from_file("settings.py")
```

### 从环境变量加载

```python
from kernel.config import Config

# 加载所有环境变量
config = Config.from_env()

# 只加载特定前缀的环境变量
config = Config.from_env(prefix="MOFOX_")

# 示例：MOFOX_DATABASE_HOST=localhost
host = config.get("DATABASE_HOST")
```

### 嵌套配置访问

```python
from kernel.config import Config

config = Config(
    database={
        "host": "localhost",
        "port": 5432,
        "credentials": {
            "username": "admin",
            "password": "secret"
        }
    }
)

# 使用点号访问嵌套配置
host = config.get("database.host")
username = config.get("database.credentials.username")

# 设置嵌套配置
config.set("database.port", 3306)
config.set("database.credentials.password", "new_secret")
```

### 配置管理器

```python
from kernel.config import ConfigManager

# 创建管理器
manager = ConfigManager()

# 加载多个配置
manager.load_from_file("dev", "config.dev.json")
manager.load_from_file("prod", "config.prod.json")
manager.load_from_env("env", prefix="APP_")

# 获取配置
dev_config = manager.get("dev")
prod_config = manager.get("prod")

# 设置默认配置
manager.set_default("dev")
default_config = manager.get()  # 返回 dev 配置
```

### 使用全局管理器

```python
from kernel.config import load_config, get_config

# 加载配置
load_config("app", "config.json", set_default=True)

# 在其他地方获取配置
config = get_config()  # 获取默认配置
config = get_config("app")  # 获取指定配置

# 使用配置
db_host = config.get("database.host")
```

## 📝 配置文件格式

### JSON 格式

```json
{
  "app": {
    "name": "MoFox",
    "version": "1.0.0",
    "debug": true
  },
  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "mofox_db"
  },
  "logging": {
    "level": "INFO",
    "file": "app.log"
  }
}
```

### YAML 格式

```yaml
app:
  name: MoFox
  version: 1.0.0
  debug: true

database:
  host: localhost
  port: 5432
  name: mofox_db

logging:
  level: INFO
  file: app.log
```

### ENV 格式

```bash
# .env 文件
APP_NAME=MoFox
APP_VERSION=1.0.0
APP_DEBUG=true

DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=mofox_db

LOGGING_LEVEL=INFO
LOGGING_FILE=app.log
```

### Python 格式

```python
# settings.py
APP_NAME = "MoFox"
APP_VERSION = "1.0.0"
APP_DEBUG = True

DATABASE_HOST = "localhost"
DATABASE_PORT = 5432
DATABASE_NAME = "mofox_db"

LOGGING_LEVEL = "INFO"
LOGGING_FILE = "app.log"
```

## 🔧 高级功能

### 配置验证

```python
from kernel.config import Config, ConfigValidationError

config = Config()

# 添加验证器
config.add_validator(
    "port",
    lambda x: isinstance(x, int) and 1 <= x <= 65535
)

# 添加必需键
config.add_required_key("database.host")
config.add_required_key("database.port")

# 验证配置
try:
    config.validate()
    print("配置有效")
except ConfigValidationError as e:
    print(f"配置无效: {e}")
```

### 配置合并

```python
from kernel.config import Config

# 基础配置
base_config = Config.from_file("config.base.json")

# 环境特定配置
dev_config = Config.from_file("config.dev.json")

# 合并配置
base_config.merge(dev_config, overwrite=True)

# 或者合并字典
base_config.merge({
    "custom_setting": "value",
    "override_setting": "new_value"
})
```

### 配置保存

```python
from kernel.config import Config

config = Config(
    app_name="MoFox",
    database_host="localhost",
    debug=True
)

# 保存为 JSON
config.save("config.json")

# 保存为 YAML
config.save("config.yaml")

# 保存为 ENV
config.save("config.env")
```

### 配置热重载

```python
from kernel.config import Config

# 从文件加载
config = Config.from_file("config.json")

# 使用配置...

# 文件修改后重新加载
config.reload()  # 自动从原文件重新加载
```

### 配置元数据

```python
from kernel.config import Config

config = Config.from_file("config.json")

# 获取元数据
metadata = config.get_metadata()

print(f"配置来源: {metadata.source}")
print(f"文件路径: {metadata.file_path}")
print(f"加载时间: {metadata.loaded_at}")
print(f"已修改的键: {metadata.modified_keys}")
```

## 🎨 使用场景

### 应用配置

```python
from kernel.config import Config

# 加载应用配置
app_config = Config.from_file("app_config.json")

# 获取应用设置
app_name = app_config.get("name", "MyApp")
debug_mode = app_config.get("debug", False)
port = app_config.get("server.port", 8000)

print(f"Starting {app_name} on port {port}")
if debug_mode:
    print("Debug mode enabled")
```

### 数据库配置

```python
from kernel.config import Config

# 数据库配置
db_config = Config.from_file("database.yaml")

# 获取连接参数
connection_params = {
    "host": db_config.get("host"),
    "port": db_config.get("port"),
    "database": db_config.get("name"),
    "user": db_config.get("credentials.username"),
    "password": db_config.get("credentials.password")
}

# 使用配置连接数据库
# connect_to_database(**connection_params)
```

### 多环境配置

```python
from kernel.config import ConfigManager
import os

# 创建管理器
manager = ConfigManager()

# 加载不同环境的配置
manager.load_from_file("base", "config.base.json")
manager.load_from_file("dev", "config.dev.json")
manager.load_from_file("staging", "config.staging.json")
manager.load_from_file("prod", "config.prod.json")

# 根据环境选择配置
env = os.getenv("APP_ENV", "dev")
manager.set_default(env)

# 获取当前环境的配置
config = manager.get()
print(f"Running in {env} environment")
```

### 配置分层

```python
from kernel.config import Config

# 默认配置
default_config = Config(
    timeout=30,
    retry_count=3,
    log_level="INFO"
)

# 用户配置
user_config = Config.from_file("user_config.json")

# 环境变量配置
env_config = Config.from_env(prefix="APP_")

# 合并配置（优先级：env > user > default）
final_config = default_config
final_config.merge(user_config, overwrite=True)
final_config.merge(env_config, overwrite=True)

# 使用最终配置
timeout = final_config.get("timeout")
```

### 动态配置更新

```python
from kernel.config import Config

config = Config.from_file("config.json")

# 运行时更新配置
def update_config(key: str, value: any):
    """更新配置并保存"""
    config.set(key, value)
    config.save("config.json")
    print(f"Config updated: {key} = {value}")

# 使用
update_config("api.rate_limit", 1000)
update_config("features.new_feature", True)
```

## 🔒 安全最佳实践

### 敏感信息处理

```python
from kernel.config import Config
import os

# ❌ 不要在配置文件中存储明文密码
# config.json: {"password": "secret123"}

# ✅ 从环境变量读取敏感信息
config = Config.from_file("config.json")
password = os.getenv("DB_PASSWORD")
config.set("database.password", password)

# ✅ 使用专门的密钥管理服务
# from secret_manager import get_secret
# api_key = get_secret("api_key")
# config.set("api.key", api_key)
```

### 配置文件权限

```bash
# 限制配置文件权限
chmod 600 config.json  # 只有所有者可读写
chmod 400 .env         # 只有所有者可读
```

### 配置验证

```python
from kernel.config import Config, ConfigValidationError

config = Config.from_file("config.json")

# 验证关键配置
def validate_security_config(config: Config):
    """验证安全相关配置"""
    
    # 检查必需的安全配置
    required = ["secret_key", "allowed_hosts", "ssl_enabled"]
    for key in required:
        if not config.has(key):
            raise ConfigValidationError(f"Missing security config: {key}")
    
    # 检查密钥强度
    secret_key = config.get("secret_key")
    if len(secret_key) < 32:
        raise ConfigValidationError("Secret key too short")
    
    # 检查 SSL 配置
    if not config.get("ssl_enabled"):
        print("Warning: SSL is disabled")
    
    return True

# 使用验证
try:
    validate_security_config(config)
    print("Security config validated")
except ConfigValidationError as e:
    print(f"Security validation failed: {e}")
```

## 📊 配置监控

```python
from kernel.config import Config
from kernel.logger import get_logger

logger = get_logger(__name__)

config = Config.from_file("config.json")

# 记录配置加载
metadata = config.get_metadata()
logger.info(f"Config loaded from {metadata.file_path}")
logger.info(f"Config source: {metadata.source}")

# 监控配置修改
def on_config_change(key: str, old_value: any, new_value: any):
    """配置变更回调"""
    logger.info(f"Config changed: {key}")
    logger.debug(f"Old value: {old_value}")
    logger.debug(f"New value: {new_value}")
    
    # 记录到审计日志
    # audit_log.record_change(key, old_value, new_value)

# 修改配置时调用
old_value = config.get("api.rate_limit")
config.set("api.rate_limit", 2000)
on_config_change("api.rate_limit", old_value, 2000)
```

## 🧪 测试支持

```python
from kernel.config import Config
import pytest

# 测试配置
def test_config():
    """测试配置功能"""
    config = Config(
        test_mode=True,
        database_host="localhost",
        database_port=5432
    )
    
    assert config.get("test_mode") is True
    assert config.get("database_host") == "localhost"
    assert config.get("database_port") == 5432

# 使用测试配置
@pytest.fixture
def test_config():
    """提供测试配置"""
    return Config(
        debug=True,
        testing=True,
        database_url="sqlite:///:memory:"
    )

def test_with_config(test_config):
    """使用测试配置的测试"""
    assert test_config.get("testing") is True
```

## 📖 更多资源

- [API 完整参考](API_REFERENCE.md)
- [最佳实践详解](BEST_PRACTICES.md)
- [快速参考](QUICK_REFERENCE.md)

## 🤝 贡献

欢迎贡献代码、报告问题或提出改进建议！

## 📄 许可

本模块遵循 MoFox 项目的许可协议。
