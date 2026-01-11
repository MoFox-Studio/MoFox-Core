# Config 快速参考

Config 模块常用功能速查表。

## 快速导入

```python
from kernel.config import (
    Config,
    ConfigManager,
    ConfigLoader,
    ConfigFormat,
    ConfigSource,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ConfigLoadError,
    get_manager,
    get_config,
    load_config,
    register_config
)
```

---

## 创建配置

### 直接创建

```python
config = Config(
    host="localhost",
    port=8000,
    debug=True
)
```

### 从文件加载

```python
# JSON
config = Config.from_file("config.json")

# YAML
config = Config.from_file("config.yaml")

# ENV
config = Config.from_file(".env")

# Python
config = Config.from_file("settings.py")
```

### 从环境变量

```python
# 所有环境变量
config = Config.from_env()

# 特定前缀
config = Config.from_env(prefix="APP_")
```

### 从字典

```python
config = Config.from_dict({
    "database": {
        "host": "localhost",
        "port": 5432
    }
})
```

---

## 基本操作

### 获取配置

```python
# 简单获取
value = config.get("key")

# 带默认值
value = config.get("key", "default")

# 嵌套获取
host = config.get("database.host")
user = config.get("db.credentials.username")

# 索引访问
value = config["key"]

# 检查存在
if "key" in config:
    value = config.get("key")
```

### 设置配置

```python
# 简单设置
config.set("key", "value")

# 嵌套设置
config.set("database.host", "localhost")
config.set("db.credentials.username", "admin")

# 索引赋值
config["key"] = "value"
```

### 删除配置

```python
# 删除键
config.delete("key")

# del 操作
del config["key"]
```

### 清空配置

```python
config.clear()
```

---

## 高级操作

### 获取所有配置

```python
# 所有配置字典
all_config = config.all()

# 所有键
keys = config.keys()

# 所有值
values = config.values()

# 所有键值对
items = config.items()

# 配置数量
count = len(config)
```

### 更新和合并

```python
# 更新配置
config.update({"new_key": "value"})
config.update(other_config)

# 合并配置（不覆盖）
config.merge(defaults)

# 合并配置（覆盖）
config.merge(overrides, overwrite=True)
```

### 保存配置

```python
# 保存为 JSON
config.save("config.json")

# 保存为 YAML
config.save("config.yaml")

# 保存为 ENV
config.save("config.env")
```

### 重新加载

```python
config.reload()
```

---

## 配置验证

### 添加验证器

```python
# 简单验证
config.add_validator("port", lambda x: 1 <= x <= 65535)

# 类型验证
config.add_validator("debug", lambda x: isinstance(x, bool))

# 复杂验证
config.add_validator(
    "email",
    lambda x: "@" in x and "." in x
)
```

### 必需键

```python
config.add_required_key("database.host")
config.add_required_key("api.key")
```

### 执行验证

```python
try:
    config.validate()
    print("配置有效")
except ConfigValidationError as e:
    print(f"配置无效: {e}")
```

---

## 配置元数据

```python
metadata = config.get_metadata()

print(metadata.source)        # 配置来源
print(metadata.format)        # 配置格式
print(metadata.file_path)     # 文件路径
print(metadata.encoding)      # 文件编码
print(metadata.loaded_at)     # 加载时间
print(metadata.modified_keys) # 已修改的键
```

---

## ConfigManager

### 创建管理器

```python
manager = ConfigManager()
```

### 加载配置

```python
# 从文件
manager.load_from_file("dev", "config.dev.json")
manager.load_from_file("prod", "config.prod.json", set_default=True)

# 从环境变量
manager.load_from_env("env", prefix="APP_")

# 从字典
manager.load_from_dict("test", {"debug": True})
```

### 注册配置

```python
custom_config = Config(host="localhost")
manager.register("custom", custom_config, set_default=True)
```

### 获取配置

```python
# 默认配置
config = manager.get()

# 指定配置
dev_config = manager.get("dev")
```

### 管理配置

```python
# 检查存在
if manager.has("prod"):
    prod_config = manager.get("prod")

# 移除配置
manager.remove("temp")

# 列出所有配置
configs = manager.list_configs()

# 设置默认配置
manager.set_default("prod")

# 获取默认配置
default = manager.get_default()

# 清空所有配置
manager.clear()
```

---

## 全局配置

### 加载配置

```python
# 从文件
load_config("app", "config.json", set_default=True)

# 从字典
load_config("test", {"debug": True})
```

### 注册配置

```python
config = Config(host="localhost")
register_config("custom", config, set_default=True)
```

### 获取配置

```python
# 默认配置
config = get_config()

# 指定配置
app_config = get_config("app")
```

### 获取管理器

```python
manager = get_manager()
```

---

## ConfigLoader

### 加载文件

```python
# 自动检测格式
data = ConfigLoader.load_from_file("config.json")

# 指定格式
data = ConfigLoader.load_json("config.json")
data = ConfigLoader.load_yaml("config.yaml")
data = ConfigLoader.load_env(".env")
data = ConfigLoader.load_python("settings.py")
```

### 保存文件

```python
data = {"key": "value"}
ConfigLoader.save_to_file(data, "config.json")
```

### 检测格式

```python
format = ConfigLoader.detect_format("config.json")
print(format)  # ConfigFormat.JSON
```

---

## 常用模式

### 多环境配置

```python
import os

# 加载基础配置
config = Config.from_file("config/base.json")

# 加载环境配置
env = os.getenv("APP_ENV", "dev")
env_config = Config.from_file(f"config/{env}.json")
config.merge(env_config, overwrite=True)

# 环境变量优先
env_vars = Config.from_env(prefix="APP_")
config.merge(env_vars, overwrite=True)
```

### 配置分层

```python
# 默认配置
config = Config(timeout=30, retry=3)

# 用户配置
config.merge(Config.from_file("user_config.json"), overwrite=True)

# 环境变量（最高优先级）
config.merge(Config.from_env(prefix="APP_"), overwrite=True)
```

### 配置验证

```python
config = Config.from_file("config.json")

# 添加验证
config.add_validator("port", lambda x: 1 <= x <= 65535)
config.add_required_key("database.host")

# 验证
config.validate()
```

### 安全配置

```python
import os

# 基础配置（不含敏感信息）
config = Config.from_file("config.json")

# 从环境变量加载敏感信息
config.set("database.password", os.getenv("DB_PASSWORD"))
config.set("api.key", os.getenv("API_KEY"))
```

### 配置管理器模式

```python
from kernel.config import ConfigManager
import os

manager = ConfigManager()

# 加载不同环境配置
manager.load_from_file("base", "config/base.json")
manager.load_from_file("dev", "config/dev.json")
manager.load_from_file("prod", "config/prod.json")

# 根据环境选择
env = os.getenv("APP_ENV", "dev")
manager.set_default(env)

# 获取配置
config = manager.get()
```

---

## 异常处理

```python
from kernel.config import (
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ConfigLoadError
)

try:
    # 加载配置
    config = Config.from_file("config.json")
    
    # 验证配置
    config.validate()
    
    # 获取配置
    value = config.get("key")
    
except ConfigLoadError as e:
    print(f"加载失败: {e}")
    
except ConfigValidationError as e:
    print(f"验证失败: {e}")
    
except ConfigNotFoundError as e:
    print(f"配置不存在: {e}")
    
except ConfigError as e:
    print(f"配置错误: {e}")
```

---

## 完整示例

### 应用配置

```python
from kernel.config import Config
import os

def load_app_config() -> Config:
    """加载应用配置"""
    
    # 1. 基础配置（默认值）
    config = Config(
        app_name="MyApp",
        debug=False,
        host="0.0.0.0",
        port=8000
    )
    
    # 2. 文件配置
    config.merge(Config.from_file("config.json"), overwrite=True)
    
    # 3. 环境特定配置
    env = os.getenv("APP_ENV", "dev")
    env_config_path = f"config/{env}.json"
    if os.path.exists(env_config_path):
        config.merge(Config.from_file(env_config_path), overwrite=True)
    
    # 4. 环境变量（最高优先级）
    config.merge(Config.from_env(prefix="APP_"), overwrite=True)
    
    # 5. 验证
    config.add_validator("port", lambda x: 1 <= x <= 65535)
    config.add_required_key("app_name")
    config.validate()
    
    return config

# 使用
config = load_app_config()
app_name = config.get("app_name")
port = config.get("port")

print(f"Starting {app_name} on port {port}")
```

### 数据库配置

```python
from kernel.config import Config
import os

def get_db_config() -> dict:
    """获取数据库配置"""
    
    config = Config.from_file("config/database.json")
    
    # 从环境变量覆盖敏感信息
    password = os.getenv("DB_PASSWORD")
    if password:
        config.set("password", password)
    
    return {
        "host": config.get("host"),
        "port": config.get("port"),
        "database": config.get("database"),
        "user": config.get("user"),
        "password": config.get("password")
    }

# 使用
db_params = get_db_config()
# 连接数据库...
```

### 多配置管理

```python
from kernel.config import ConfigManager
import os

# 创建管理器
manager = ConfigManager()

# 加载所有配置
manager.load_from_file("app", "config/app.json")
manager.load_from_file("database", "config/database.json")
manager.load_from_file("cache", "config/cache.json")

# 设置默认
env = os.getenv("APP_ENV", "dev")
manager.load_from_file("env", f"config/{env}.json", set_default=True)

# 使用配置
app_config = manager.get("app")
db_config = manager.get("database")
default_config = manager.get()  # 环境配置
```

---

## 性能提示

### 缓存频繁访问的配置

```python
from functools import lru_cache

class CachedConfig:
    def __init__(self, config: Config):
        self._config = config
    
    @lru_cache(maxsize=128)
    def get(self, key: str):
        return self._config.get(key)
```

### 延迟加载

```python
class LazyConfig:
    def __init__(self, file_path: str):
        self._file_path = file_path
        self._config = None
    
    @property
    def config(self):
        if self._config is None:
            self._config = Config.from_file(self._file_path)
        return self._config
```

---

## 调试技巧

### 打印配置

```python
print(config)  # Config(keys=5, source=FILE)
print(config.all())  # 所有配置字典
```

### 查看元数据

```python
metadata = config.get_metadata()
print(f"Source: {metadata.source}")
print(f"Format: {metadata.format}")
print(f"File: {metadata.file_path}")
print(f"Modified keys: {metadata.modified_keys}")
```

### 验证配置

```python
# 检查键存在
assert config.has("database.host")

# 检查值
assert config.get("port") == 8000

# 验证类型
assert isinstance(config.get("debug"), bool)
```

---

## 相关文档

- [完整文档](README.md)
- [API 参考](API_REFERENCE.md)
- [最佳实践](BEST_PRACTICES.md)

---

**提示**: 将此页面添加到书签以便快速查找常用操作！
