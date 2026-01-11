# Config 模块 API 参考

完整的 Config 模块 API 文档。

## 目录

- [基础类](#基础类)
  - [BaseConfig](#baseconfig)
  - [Config](#config)
  - [ConfigMetadata](#configmetadata)
- [管理类](#管理类)
  - [ConfigManager](#configmanager)
  - [ConfigLoader](#configloader)
- [枚举类](#枚举类)
  - [ConfigFormat](#configformat)
  - [ConfigSource](#configsource)
- [异常类](#异常类)
- [全局函数](#全局函数)

---

## 基础类

### BaseConfig

配置管理的抽象基类。

```python
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Callable

class BaseConfig(ABC):
    """配置管理抽象基类"""
```

#### 抽象方法

##### `get()`
```python
@abstractmethod
def get(self, key: str, default: Optional[Any] = None) -> Any:
    """获取配置值
    
    Args:
        key: 配置键，支持点号分隔的嵌套键
        default: 默认值
        
    Returns:
        配置值，如果不存在返回默认值
    """
```

##### `set()`
```python
@abstractmethod
def set(self, key: str, value: Any) -> None:
    """设置配置值
    
    Args:
        key: 配置键，支持点号分隔的嵌套键
        value: 配置值
    """
```

##### `has()`
```python
@abstractmethod
def has(self, key: str) -> bool:
    """检查配置键是否存在
    
    Args:
        key: 配置键
        
    Returns:
        是否存在
    """
```

##### `delete()`
```python
@abstractmethod
def delete(self, key: str) -> None:
    """删除配置项
    
    Args:
        key: 配置键
        
    Raises:
        ConfigNotFoundError: 配置键不存在
    """
```

##### `all()`
```python
@abstractmethod
def all(self) -> Dict[str, Any]:
    """获取所有配置
    
    Returns:
        所有配置的字典
    """
```

##### `clear()`
```python
@abstractmethod
def clear(self) -> None:
    """清空所有配置"""
```

##### `validate()`
```python
@abstractmethod
def validate(self) -> bool:
    """验证配置
    
    Returns:
        配置是否有效
        
    Raises:
        ConfigValidationError: 验证失败
    """
```

##### `get_metadata()`
```python
@abstractmethod
def get_metadata(self) -> 'ConfigMetadata':
    """获取配置元数据
    
    Returns:
        配置元数据对象
    """
```

---

### Config

配置管理具体实现类。

```python
from typing import Any, Optional, Dict, List, Callable, Union
from pathlib import Path

class Config(BaseConfig):
    """配置管理实现类"""
```

#### 构造方法

```python
def __init__(self, **kwargs):
    """初始化配置
    
    Args:
        **kwargs: 初始配置键值对
        
    Example:
        config = Config(
            host="localhost",
            port=8000,
            debug=True
        )
    """
```

#### 类方法（工厂方法）

##### `from_file()`
```python
@classmethod
def from_file(
    cls,
    file_path: Union[str, Path],
    encoding: str = "utf-8"
) -> 'Config':
    """从文件加载配置
    
    Args:
        file_path: 配置文件路径
        encoding: 文件编码
        
    Returns:
        Config 实例
        
    Raises:
        ConfigLoadError: 加载失败
        
    Example:
        config = Config.from_file("config.json")
        config = Config.from_file("settings.yaml")
    """
```

##### `from_env()`
```python
@classmethod
def from_env(
    cls,
    prefix: Optional[str] = None,
    lowercase: bool = False
) -> 'Config':
    """从环境变量加载配置
    
    Args:
        prefix: 环境变量前缀，只加载匹配前缀的变量
        lowercase: 是否将键转换为小写
        
    Returns:
        Config 实例
        
    Example:
        # 加载所有环境变量
        config = Config.from_env()
        
        # 只加载 APP_ 前缀的变量
        config = Config.from_env(prefix="APP_")
        # APP_DATABASE_HOST -> DATABASE_HOST
    """
```

##### `from_dict()`
```python
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> 'Config':
    """从字典创建配置
    
    Args:
        data: 配置字典
        
    Returns:
        Config 实例
        
    Example:
        config = Config.from_dict({
            "database": {
                "host": "localhost",
                "port": 5432
            }
        })
    """
```

#### 实例方法

##### `get()`
```python
def get(self, key: str, default: Optional[Any] = None) -> Any:
    """获取配置值
    
    Args:
        key: 配置键，支持点号分隔访问嵌套配置
        default: 默认值
        
    Returns:
        配置值
        
    Example:
        host = config.get("database.host")
        port = config.get("database.port", 5432)
        username = config.get("db.credentials.username")
    """
```

##### `set()`
```python
def set(self, key: str, value: Any) -> None:
    """设置配置值
    
    Args:
        key: 配置键，支持点号分隔设置嵌套配置
        value: 配置值
        
    Example:
        config.set("database.host", "localhost")
        config.set("database.credentials.username", "admin")
    """
```

##### `has()`
```python
def has(self, key: str) -> bool:
    """检查配置键是否存在
    
    Args:
        key: 配置键
        
    Returns:
        是否存在
        
    Example:
        if config.has("database.host"):
            host = config.get("database.host")
    """
```

##### `delete()`
```python
def delete(self, key: str) -> None:
    """删除配置项
    
    Args:
        key: 配置键
        
    Raises:
        ConfigNotFoundError: 配置键不存在
        
    Example:
        config.delete("temp_setting")
        config.delete("cache.old_key")
    """
```

##### `all()`
```python
def all(self) -> Dict[str, Any]:
    """获取所有配置
    
    Returns:
        所有配置的字典副本
        
    Example:
        all_config = config.all()
        print(all_config)
    """
```

##### `keys()`
```python
def keys(self) -> List[str]:
    """获取所有配置键
    
    Returns:
        配置键列表
        
    Example:
        for key in config.keys():
            print(f"{key}: {config.get(key)}")
    """
```

##### `values()`
```python
def values(self) -> List[Any]:
    """获取所有配置值
    
    Returns:
        配置值列表
    """
```

##### `items()`
```python
def items(self) -> List[tuple]:
    """获取所有配置键值对
    
    Returns:
        (key, value) 元组列表
        
    Example:
        for key, value in config.items():
            print(f"{key}: {value}")
    """
```

##### `clear()`
```python
def clear(self) -> None:
    """清空所有配置
    
    Example:
        config.clear()
    """
```

##### `update()`
```python
def update(self, other: Union[Dict[str, Any], 'Config']) -> None:
    """更新配置
    
    Args:
        other: 另一个配置对象或字典
        
    Example:
        config.update({"new_key": "value"})
        config.update(other_config)
    """
```

##### `merge()`
```python
def merge(
    self,
    other: Union[Dict[str, Any], 'Config'],
    overwrite: bool = False
) -> None:
    """合并配置
    
    Args:
        other: 另一个配置对象或字典
        overwrite: 是否覆盖现有值
        
    Example:
        # 不覆盖现有值
        config.merge(defaults)
        
        # 覆盖现有值
        config.merge(overrides, overwrite=True)
    """
```

##### `save()`
```python
def save(
    self,
    file_path: Union[str, Path],
    format: Optional[ConfigFormat] = None
) -> None:
    """保存配置到文件
    
    Args:
        file_path: 文件路径
        format: 配置格式，None 则根据文件扩展名自动判断
        
    Raises:
        ConfigLoadError: 保存失败
        
    Example:
        config.save("config.json")
        config.save("config.yaml")
        config.save("config.env")
    """
```

##### `reload()`
```python
def reload(self) -> None:
    """重新加载配置
    
    从原始源重新加载配置。
    
    Raises:
        ConfigLoadError: 无法重新加载或原始源不可用
        
    Example:
        config = Config.from_file("config.json")
        # ... 配置文件被修改 ...
        config.reload()  # 重新加载
    """
```

##### `validate()`
```python
def validate(self) -> bool:
    """验证配置
    
    Returns:
        配置是否有效
        
    Raises:
        ConfigValidationError: 验证失败
        
    Example:
        try:
            config.validate()
            print("配置有效")
        except ConfigValidationError as e:
            print(f"配置无效: {e}")
    """
```

##### `add_validator()`
```python
def add_validator(self, key: str, validator: Callable[[Any], bool]) -> None:
    """添加配置验证器
    
    Args:
        key: 配置键
        validator: 验证函数，接受配置值，返回是否有效
        
    Example:
        config.add_validator(
            "port",
            lambda x: isinstance(x, int) and 1 <= x <= 65535
        )
        
        config.add_validator(
            "email",
            lambda x: "@" in x and "." in x
        )
    """
```

##### `add_required_key()`
```python
def add_required_key(self, key: str) -> None:
    """添加必需的配置键
    
    Args:
        key: 配置键
        
    Example:
        config.add_required_key("database.host")
        config.add_required_key("api.key")
    """
```

##### `get_metadata()`
```python
def get_metadata(self) -> ConfigMetadata:
    """获取配置元数据
    
    Returns:
        配置元数据对象
        
    Example:
        metadata = config.get_metadata()
        print(f"来源: {metadata.source}")
        print(f"格式: {metadata.format}")
        print(f"文件: {metadata.file_path}")
    """
```

#### 特殊方法

##### `__contains__()`
```python
def __contains__(self, key: str) -> bool:
    """支持 in 操作符
    
    Example:
        if "database.host" in config:
            host = config.get("database.host")
    """
```

##### `__getitem__()`
```python
def __getitem__(self, key: str) -> Any:
    """支持索引访问
    
    Example:
        host = config["database.host"]
    """
```

##### `__setitem__()`
```python
def __setitem__(self, key: str, value: Any) -> None:
    """支持索引赋值
    
    Example:
        config["database.host"] = "localhost"
    """
```

##### `__delitem__()`
```python
def __delitem__(self, key: str) -> None:
    """支持 del 操作符
    
    Example:
        del config["temp_key"]
    """
```

##### `__len__()`
```python
def __len__(self) -> int:
    """获取配置项数量
    
    Example:
        count = len(config)
    """
```

##### `__repr__()`
```python
def __repr__(self) -> str:
    """字符串表示
    
    Example:
        print(config)
        # Config(keys=5, source=FILE)
    """
```

---

### ConfigMetadata

配置元数据类。

```python
from dataclasses import dataclass
from typing import Optional, Set
from datetime import datetime
from pathlib import Path

@dataclass
class ConfigMetadata:
    """配置元数据"""
```

#### 属性

```python
source: ConfigSource
"""配置来源"""

format: Optional[ConfigFormat] = None
"""配置格式"""

file_path: Optional[Path] = None
"""文件路径（如果从文件加载）"""

encoding: str = "utf-8"
"""文件编码"""

loaded_at: datetime = field(default_factory=datetime.now)
"""加载时间"""

modified_keys: Set[str] = field(default_factory=set)
"""已修改的配置键"""
```

#### 示例

```python
metadata = config.get_metadata()

print(f"配置来源: {metadata.source}")
print(f"配置格式: {metadata.format}")
print(f"文件路径: {metadata.file_path}")
print(f"加载时间: {metadata.loaded_at}")
print(f"已修改的键: {metadata.modified_keys}")
```

---

## 管理类

### ConfigManager

配置管理器，管理多个配置实例。

```python
class ConfigManager:
    """配置管理器"""
```

#### 构造方法

```python
def __init__(self):
    """初始化配置管理器"""
```

#### 实例方法

##### `load_from_file()`
```python
def load_from_file(
    self,
    name: str,
    file_path: Union[str, Path],
    set_default: bool = False
) -> Config:
    """从文件加载配置
    
    Args:
        name: 配置名称
        file_path: 文件路径
        set_default: 是否设置为默认配置
        
    Returns:
        Config 实例
        
    Example:
        manager = ConfigManager()
        manager.load_from_file("dev", "config.dev.json")
        manager.load_from_file("prod", "config.prod.json", set_default=True)
    """
```

##### `load_from_env()`
```python
def load_from_env(
    self,
    name: str,
    prefix: Optional[str] = None,
    set_default: bool = False
) -> Config:
    """从环境变量加载配置
    
    Args:
        name: 配置名称
        prefix: 环境变量前缀
        set_default: 是否设置为默认配置
        
    Returns:
        Config 实例
        
    Example:
        manager.load_from_env("env", prefix="APP_")
    """
```

##### `load_from_dict()`
```python
def load_from_dict(
    self,
    name: str,
    data: Dict[str, Any],
    set_default: bool = False
) -> Config:
    """从字典加载配置
    
    Args:
        name: 配置名称
        data: 配置字典
        set_default: 是否设置为默认配置
        
    Returns:
        Config 实例
        
    Example:
        manager.load_from_dict("test", {
            "debug": True,
            "testing": True
        })
    """
```

##### `register()`
```python
def register(
    self,
    name: str,
    config: Config,
    set_default: bool = False
) -> None:
    """注册配置
    
    Args:
        name: 配置名称
        config: Config 实例
        set_default: 是否设置为默认配置
        
    Example:
        custom_config = Config(host="localhost")
        manager.register("custom", custom_config)
    """
```

##### `get()`
```python
def get(self, name: Optional[str] = None) -> Config:
    """获取配置
    
    Args:
        name: 配置名称，None 则返回默认配置
        
    Returns:
        Config 实例
        
    Raises:
        ConfigNotFoundError: 配置不存在
        
    Example:
        # 获取默认配置
        config = manager.get()
        
        # 获取指定配置
        dev_config = manager.get("dev")
    """
```

##### `has()`
```python
def has(self, name: str) -> bool:
    """检查配置是否存在
    
    Args:
        name: 配置名称
        
    Returns:
        是否存在
        
    Example:
        if manager.has("prod"):
            prod_config = manager.get("prod")
    """
```

##### `remove()`
```python
def remove(self, name: str) -> None:
    """移除配置
    
    Args:
        name: 配置名称
        
    Raises:
        ConfigNotFoundError: 配置不存在
        
    Example:
        manager.remove("temp")
    """
```

##### `list_configs()`
```python
def list_configs(self) -> List[str]:
    """列出所有配置名称
    
    Returns:
        配置名称列表
        
    Example:
        configs = manager.list_configs()
        print(f"Available configs: {', '.join(configs)}")
    """
```

##### `set_default()`
```python
def set_default(self, name: str) -> None:
    """设置默认配置
    
    Args:
        name: 配置名称
        
    Raises:
        ConfigNotFoundError: 配置不存在
        
    Example:
        manager.set_default("prod")
    """
```

##### `get_default()`
```python
def get_default(self) -> Optional[Config]:
    """获取默认配置
    
    Returns:
        默认配置，如果没有设置则返回 None
        
    Example:
        default = manager.get_default()
        if default:
            print("Default config available")
    """
```

##### `clear()`
```python
def clear(self) -> None:
    """清空所有配置
    
    Example:
        manager.clear()
    """
```

---

### ConfigLoader

配置加载器，支持多种格式。

```python
class ConfigLoader:
    """配置加载器"""
```

#### 静态方法

##### `load_from_file()`
```python
@staticmethod
def load_from_file(
    file_path: Union[str, Path],
    encoding: str = "utf-8"
) -> Dict[str, Any]:
    """从文件加载配置
    
    Args:
        file_path: 文件路径
        encoding: 文件编码
        
    Returns:
        配置字典
        
    Raises:
        ConfigLoadError: 加载失败
        
    Supported Formats:
        - .json - JSON 格式
        - .yaml, .yml - YAML 格式
        - .env - ENV 格式
        - .py - Python 格式
        
    Example:
        data = ConfigLoader.load_from_file("config.json")
    """
```

##### `load_json()`
```python
@staticmethod
def load_json(file_path: Union[str, Path], encoding: str = "utf-8") -> Dict[str, Any]:
    """加载 JSON 配置
    
    Args:
        file_path: JSON 文件路径
        encoding: 文件编码
        
    Returns:
        配置字典
        
    Raises:
        ConfigLoadError: 加载失败
    """
```

##### `load_yaml()`
```python
@staticmethod
def load_yaml(file_path: Union[str, Path], encoding: str = "utf-8") -> Dict[str, Any]:
    """加载 YAML 配置
    
    需要安装 pyyaml: pip install pyyaml
    
    Args:
        file_path: YAML 文件路径
        encoding: 文件编码
        
    Returns:
        配置字典
        
    Raises:
        ConfigLoadError: 加载失败或 pyyaml 未安装
    """
```

##### `load_env()`
```python
@staticmethod
def load_env(file_path: Union[str, Path], encoding: str = "utf-8") -> Dict[str, Any]:
    """加载 ENV 配置
    
    Args:
        file_path: ENV 文件路径
        encoding: 文件编码
        
    Returns:
        配置字典
        
    Example:
        # .env 内容:
        # DATABASE_HOST=localhost
        # DATABASE_PORT=5432
        
        data = ConfigLoader.load_env(".env")
        # {"DATABASE_HOST": "localhost", "DATABASE_PORT": "5432"}
    """
```

##### `load_python()`
```python
@staticmethod
def load_python(file_path: Union[str, Path]) -> Dict[str, Any]:
    """加载 Python 配置
    
    Args:
        file_path: Python 文件路径
        
    Returns:
        配置字典（大写变量）
        
    Example:
        # settings.py 内容:
        # DATABASE_HOST = "localhost"
        # DATABASE_PORT = 5432
        
        data = ConfigLoader.load_python("settings.py")
        # {"DATABASE_HOST": "localhost", "DATABASE_PORT": 5432}
    """
```

##### `save_to_file()`
```python
@staticmethod
def save_to_file(
    data: Dict[str, Any],
    file_path: Union[str, Path],
    format: Optional[ConfigFormat] = None
) -> None:
    """保存配置到文件
    
    Args:
        data: 配置字典
        file_path: 文件路径
        format: 配置格式，None 则根据扩展名判断
        
    Raises:
        ConfigLoadError: 保存失败
    """
```

##### `detect_format()`
```python
@staticmethod
def detect_format(file_path: Union[str, Path]) -> ConfigFormat:
    """检测配置文件格式
    
    Args:
        file_path: 文件路径
        
    Returns:
        配置格式
        
    Raises:
        ConfigLoadError: 无法识别的格式
    """
```

---

## 枚举类

### ConfigFormat

配置格式枚举。

```python
from enum import Enum

class ConfigFormat(Enum):
    """配置格式"""
    JSON = "json"
    YAML = "yaml"
    ENV = "env"
    PYTHON = "python"
```

#### 示例

```python
from kernel.config import ConfigFormat

if metadata.format == ConfigFormat.JSON:
    print("JSON 格式")
elif metadata.format == ConfigFormat.YAML:
    print("YAML 格式")
```

---

### ConfigSource

配置来源枚举。

```python
from enum import Enum

class ConfigSource(Enum):
    """配置来源"""
    FILE = "file"
    ENV = "env"
    DICT = "dict"
    UNKNOWN = "unknown"
```

#### 示例

```python
from kernel.config import ConfigSource

if metadata.source == ConfigSource.FILE:
    print(f"从文件加载: {metadata.file_path}")
elif metadata.source == ConfigSource.ENV:
    print("从环境变量加载")
```

---

## 异常类

### ConfigError

配置基础异常。

```python
class ConfigError(Exception):
    """配置基础异常"""
```

### ConfigNotFoundError

配置不存在异常。

```python
class ConfigNotFoundError(ConfigError):
    """配置不存在异常"""
```

### ConfigValidationError

配置验证失败异常。

```python
class ConfigValidationError(ConfigError):
    """配置验证失败异常"""
```

### ConfigLoadError

配置加载失败异常。

```python
class ConfigLoadError(ConfigError):
    """配置加载失败异常"""
```

#### 示例

```python
from kernel.config import (
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ConfigLoadError
)

try:
    config = Config.from_file("config.json")
except ConfigLoadError as e:
    print(f"加载失败: {e}")

try:
    value = config.get("required_key")
    if not value:
        raise ConfigNotFoundError("required_key not found")
except ConfigNotFoundError as e:
    print(f"配置不存在: {e}")

try:
    config.validate()
except ConfigValidationError as e:
    print(f"验证失败: {e}")
```

---

## 全局函数

### `get_manager()`

获取全局配置管理器实例（单例）。

```python
def get_manager() -> ConfigManager:
    """获取全局配置管理器
    
    Returns:
        ConfigManager 单例实例
        
    Example:
        from kernel.config import get_manager
        
        manager = get_manager()
        manager.load_from_file("app", "config.json")
    """
```

### `get_config()`

从全局管理器获取配置。

```python
def get_config(name: Optional[str] = None) -> Config:
    """获取配置
    
    Args:
        name: 配置名称，None 则返回默认配置
        
    Returns:
        Config 实例
        
    Raises:
        ConfigNotFoundError: 配置不存在
        
    Example:
        from kernel.config import get_config
        
        # 获取默认配置
        config = get_config()
        
        # 获取指定配置
        dev_config = get_config("dev")
    """
```

### `load_config()`

加载配置到全局管理器。

```python
def load_config(
    name: str,
    source: Union[str, Path, Dict[str, Any]],
    set_default: bool = False
) -> Config:
    """加载配置
    
    Args:
        name: 配置名称
        source: 配置源（文件路径或字典）
        set_default: 是否设置为默认配置
        
    Returns:
        Config 实例
        
    Example:
        from kernel.config import load_config
        
        # 从文件加载
        load_config("app", "config.json", set_default=True)
        
        # 从字典加载
        load_config("test", {"debug": True})
    """
```

### `register_config()`

注册配置到全局管理器。

```python
def register_config(
    name: str,
    config: Config,
    set_default: bool = False
) -> None:
    """注册配置
    
    Args:
        name: 配置名称
        config: Config 实例
        set_default: 是否设置为默认配置
        
    Example:
        from kernel.config import Config, register_config
        
        custom_config = Config(host="localhost", port=8000)
        register_config("custom", custom_config, set_default=True)
    """
```

---

## 完整使用示例

### 基础配置管理

```python
from kernel.config import Config

# 创建配置
config = Config(
    app_name="MoFox",
    debug=True,
    database={
        "host": "localhost",
        "port": 5432
    }
)

# 获取配置
app_name = config.get("app_name")
db_host = config.get("database.host")

# 设置配置
config.set("database.port", 3306)

# 检查配置
if "debug" in config:
    print("Debug mode")

# 删除配置
config.delete("debug")
```

### 从文件加载

```python
from kernel.config import Config

# JSON
config = Config.from_file("config.json")

# YAML
config = Config.from_file("config.yaml")

# ENV
config = Config.from_file(".env")

# Python
config = Config.from_file("settings.py")
```

### 配置管理器

```python
from kernel.config import ConfigManager

# 创建管理器
manager = ConfigManager()

# 加载多个配置
manager.load_from_file("dev", "config.dev.json")
manager.load_from_file("prod", "config.prod.json", set_default=True)
manager.load_from_env("env", prefix="APP_")

# 获取配置
dev_config = manager.get("dev")
prod_config = manager.get("prod")
default_config = manager.get()  # 默认配置
```

### 全局配置

```python
from kernel.config import load_config, get_config

# 加载配置
load_config("app", "config.json", set_default=True)

# 在其他模块中获取
config = get_config()
db_host = config.get("database.host")
```

### 配置验证

```python
from kernel.config import Config, ConfigValidationError

config = Config.from_file("config.json")

# 添加验证器
config.add_validator("port", lambda x: 1 <= x <= 65535)
config.add_required_key("database.host")

# 验证
try:
    config.validate()
except ConfigValidationError as e:
    print(f"Validation failed: {e}")
```

### 配置合并

```python
from kernel.config import Config

# 基础配置
base = Config.from_file("config.base.json")

# 环境配置
dev = Config.from_file("config.dev.json")

# 合并
base.merge(dev, overwrite=True)
```

---

更多示例请参考 [README](README.md) 和 [最佳实践](BEST_PRACTICES.md)。
