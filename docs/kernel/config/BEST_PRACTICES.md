# Config 模块最佳实践

本文档提供 Config 模块的最佳实践和使用建议。

## 目录

- [配置设计原则](#配置设计原则)
- [配置文件组织](#配置文件组织)
- [配置加载策略](#配置加载策略)
- [配置验证](#配置验证)
- [安全性](#安全性)
- [性能优化](#性能优化)
- [错误处理](#错误处理)
- [测试](#测试)
- [常见模式](#常见模式)

---

## 配置设计原则

### 1. 单一职责

每个配置文件应该有明确的职责。

```python
# ✅ 好的做法：分离配置
# config.database.json
{
    "host": "localhost",
    "port": 5432,
    "name": "mydb"
}

# config.app.json
{
    "name": "MyApp",
    "debug": false,
    "log_level": "INFO"
}

# ❌ 不好的做法：混杂配置
# config.json
{
    "app_name": "MyApp",
    "db_host": "localhost",
    "cache_ttl": 3600,
    "log_file": "app.log",
    ...
}
```

### 2. 环境分离

为不同环境使用不同的配置文件。

```python
from kernel.config import Config
import os

# 配置文件结构
# config/
#   base.json      # 基础配置
#   dev.json       # 开发环境
#   staging.json   # 预发布环境
#   prod.json      # 生产环境

# 加载策略
env = os.getenv("APP_ENV", "dev")

# 加载基础配置
config = Config.from_file("config/base.json")

# 合并环境特定配置
env_config = Config.from_file(f"config/{env}.json")
config.merge(env_config, overwrite=True)

# 环境变量具有最高优先级
env_vars = Config.from_env(prefix="APP_")
config.merge(env_vars, overwrite=True)
```

### 3. 默认值优先

始终提供合理的默认值。

```python
from kernel.config import Config

# ✅ 好的做法
config = Config(
    # 应用配置
    app_name="MyApp",
    app_version="1.0.0",
    debug=False,
    
    # 服务器配置
    host="0.0.0.0",
    port=8000,
    workers=4,
    
    # 超时配置
    request_timeout=30,
    connect_timeout=10,
    read_timeout=30,
)

# 从文件加载并覆盖默认值
config.merge(Config.from_file("config.json"), overwrite=True)

# ❌ 不好的做法：没有默认值
config = Config.from_file("config.json")  # 文件可能不存在或不完整
```

### 4. 类型安全

使用类型提示和验证确保配置的正确性。

```python
from kernel.config import Config, ConfigValidationError
from typing import Any

def create_validated_config() -> Config:
    """创建并验证配置"""
    config = Config.from_file("config.json")
    
    # 添加类型验证
    config.add_validator("port", lambda x: isinstance(x, int) and 1 <= x <= 65535)
    config.add_validator("workers", lambda x: isinstance(x, int) and x > 0)
    config.add_validator("debug", lambda x: isinstance(x, bool))
    config.add_validator("host", lambda x: isinstance(x, str) and len(x) > 0)
    
    # 添加必需键
    config.add_required_key("database.host")
    config.add_required_key("database.port")
    config.add_required_key("secret_key")
    
    # 验证配置
    try:
        config.validate()
    except ConfigValidationError as e:
        # 记录详细的错误信息
        print(f"Configuration validation failed: {e}")
        raise
    
    return config
```

---

## 配置文件组织

### 推荐的目录结构

```
project/
├── config/
│   ├── __init__.py
│   ├── base.json          # 基础配置
│   ├── dev.json           # 开发环境
│   ├── staging.json       # 预发布环境
│   ├── prod.json          # 生产环境
│   ├── local.json         # 本地覆盖（不提交到版本控制）
│   └── secrets/           # 敏感配置（不提交到版本控制）
│       ├── dev.json
│       └── prod.json
├── .env                   # 环境变量
├── .env.example           # 环境变量示例
└── src/
```

### 配置加载顺序

```python
from kernel.config import Config
from pathlib import Path
import os

def load_application_config() -> Config:
    """加载应用配置（推荐模式）"""
    
    # 1. 加载基础配置（最低优先级）
    config = Config.from_file("config/base.json")
    
    # 2. 加载环境特定配置
    env = os.getenv("APP_ENV", "dev")
    env_config_path = Path(f"config/{env}.json")
    if env_config_path.exists():
        config.merge(Config.from_file(env_config_path), overwrite=True)
    
    # 3. 加载敏感配置
    secrets_path = Path(f"config/secrets/{env}.json")
    if secrets_path.exists():
        config.merge(Config.from_file(secrets_path), overwrite=True)
    
    # 4. 加载本地覆盖配置
    local_config_path = Path("config/local.json")
    if local_config_path.exists():
        config.merge(Config.from_file(local_config_path), overwrite=True)
    
    # 5. 加载环境变量（最高优先级）
    env_vars = Config.from_env(prefix="APP_")
    config.merge(env_vars, overwrite=True)
    
    return config
```

### .gitignore 配置

```gitignore
# 本地配置
config/local.json
config/secrets/

# 环境变量
.env
.env.local

# 但保留示例文件
!.env.example
!config/secrets/.gitkeep
```

---

## 配置加载策略

### 延迟加载

只在需要时加载配置，避免不必要的开销。

```python
from kernel.config import Config
from typing import Optional

class DatabaseConnection:
    """数据库连接（延迟加载配置）"""
    
    def __init__(self):
        self._config: Optional[Config] = None
        self._connection = None
    
    @property
    def config(self) -> Config:
        """延迟加载配置"""
        if self._config is None:
            self._config = Config.from_file("config/database.json")
        return self._config
    
    def connect(self):
        """连接数据库"""
        if self._connection is None:
            host = self.config.get("host")
            port = self.config.get("port")
            # 建立连接...
            print(f"Connecting to {host}:{port}")
        return self._connection
```

### 配置缓存

缓存已加载的配置，避免重复加载。

```python
from kernel.config import ConfigManager, Config
from typing import Dict
from pathlib import Path

class CachedConfigLoader:
    """带缓存的配置加载器"""
    
    def __init__(self):
        self._cache: Dict[str, Config] = {}
    
    def load(self, file_path: str) -> Config:
        """加载配置（带缓存）"""
        path = str(Path(file_path).absolute())
        
        if path not in self._cache:
            self._cache[path] = Config.from_file(file_path)
        
        return self._cache[path]
    
    def reload(self, file_path: str) -> Config:
        """强制重新加载配置"""
        path = str(Path(file_path).absolute())
        
        # 清除缓存
        if path in self._cache:
            del self._cache[path]
        
        # 重新加载
        return self.load(file_path)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()

# 使用示例
loader = CachedConfigLoader()
config1 = loader.load("config.json")  # 从文件加载
config2 = loader.load("config.json")  # 从缓存获取
```

### 热重载

监控配置文件变化并自动重新加载。

```python
from kernel.config import Config
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

class ConfigReloader(FileSystemEventHandler):
    """配置文件监控和热重载"""
    
    def __init__(self, config_path: str, on_reload=None):
        self.config_path = Path(config_path)
        self.config = Config.from_file(config_path)
        self.on_reload = on_reload
        self.last_modified = self.config_path.stat().st_mtime
    
    def on_modified(self, event):
        """文件修改时触发"""
        if event.src_path == str(self.config_path):
            # 防止重复触发
            current_mtime = self.config_path.stat().st_mtime
            if current_mtime > self.last_modified:
                self.last_modified = current_mtime
                
                # 重新加载配置
                print(f"Config file changed: {self.config_path}")
                try:
                    self.config.reload()
                    if self.on_reload:
                        self.on_reload(self.config)
                    print("Config reloaded successfully")
                except Exception as e:
                    print(f"Failed to reload config: {e}")

# 使用示例
def on_config_reload(config: Config):
    """配置重载回调"""
    print("Applying new configuration...")
    # 应用新配置...

reloader = ConfigReloader("config.json", on_reload=on_config_reload)

# 启动监控
observer = Observer()
observer.schedule(reloader, path=str(reloader.config_path.parent), recursive=False)
observer.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()
```

---

## 配置验证

### 基础验证

```python
from kernel.config import Config, ConfigValidationError

def validate_basic_config(config: Config):
    """基础配置验证"""
    
    # 必需键
    required_keys = [
        "app.name",
        "app.version",
        "database.host",
        "database.port",
    ]
    
    for key in required_keys:
        config.add_required_key(key)
    
    # 类型和范围验证
    config.add_validator(
        "database.port",
        lambda x: isinstance(x, int) and 1 <= x <= 65535
    )
    
    config.add_validator(
        "app.version",
        lambda x: isinstance(x, str) and len(x) > 0
    )
    
    # 执行验证
    config.validate()
```

### 复杂验证

```python
from kernel.config import Config, ConfigValidationError
import re

def validate_advanced_config(config: Config):
    """高级配置验证"""
    
    # 邮箱格式验证
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    config.add_validator(
        "admin.email",
        lambda x: bool(email_pattern.match(x))
    )
    
    # URL 格式验证
    url_pattern = re.compile(r'^https?://[^\s]+$')
    config.add_validator(
        "api.base_url",
        lambda x: bool(url_pattern.match(x))
    )
    
    # 枚举值验证
    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    config.add_validator(
        "logging.level",
        lambda x: x.upper() in valid_log_levels
    )
    
    # 条件验证
    def validate_ssl_config(config_dict):
        """SSL 配置条件验证"""
        ssl_enabled = config_dict.get("ssl", {}).get("enabled", False)
        if ssl_enabled:
            # 如果启用 SSL，必须提供证书路径
            if not config_dict.get("ssl", {}).get("cert_path"):
                raise ConfigValidationError("SSL enabled but cert_path not provided")
            if not config_dict.get("ssl", {}).get("key_path"):
                raise ConfigValidationError("SSL enabled but key_path not provided")
        return True
    
    # 执行验证
    validate_ssl_config(config.all())
    config.validate()
```

### 自定义验证器

```python
from kernel.config import Config, ConfigValidationError
from typing import Any, Callable
import os

class ConfigValidator:
    """配置验证器工具类"""
    
    @staticmethod
    def range_validator(min_val: int, max_val: int) -> Callable[[Any], bool]:
        """范围验证器"""
        def validator(value):
            return isinstance(value, (int, float)) and min_val <= value <= max_val
        return validator
    
    @staticmethod
    def length_validator(min_len: int, max_len: int) -> Callable[[Any], bool]:
        """长度验证器"""
        def validator(value):
            return isinstance(value, str) and min_len <= len(value) <= max_len
        return validator
    
    @staticmethod
    def file_exists_validator() -> Callable[[Any], bool]:
        """文件存在验证器"""
        def validator(value):
            return isinstance(value, str) and os.path.isfile(value)
        return validator
    
    @staticmethod
    def enum_validator(*allowed_values) -> Callable[[Any], bool]:
        """枚举值验证器"""
        def validator(value):
            return value in allowed_values
        return validator

# 使用示例
config = Config.from_file("config.json")

# 使用自定义验证器
config.add_validator("server.port", ConfigValidator.range_validator(1, 65535))
config.add_validator("api.key", ConfigValidator.length_validator(32, 128))
config.add_validator("log.file", ConfigValidator.file_exists_validator())
config.add_validator("env", ConfigValidator.enum_validator("dev", "staging", "prod"))

config.validate()
```

---

## 安全性

### 敏感信息保护

```python
from kernel.config import Config
import os
from pathlib import Path

class SecureConfig:
    """安全配置管理"""
    
    def __init__(self):
        self.config = Config()
        self._load_secure_config()
    
    def _load_secure_config(self):
        """加载安全配置"""
        # 1. 加载基础配置（不包含敏感信息）
        self.config = Config.from_file("config/base.json")
        
        # 2. 从环境变量加载敏感信息
        self.config.set("database.password", os.getenv("DB_PASSWORD"))
        self.config.set("api.key", os.getenv("API_KEY"))
        self.config.set("secret_key", os.getenv("SECRET_KEY"))
        
        # 3. 或从加密的配置文件加载
        secrets_file = Path("config/secrets.enc")
        if secrets_file.exists():
            secrets = self._decrypt_secrets(secrets_file)
            self.config.merge(secrets, overwrite=True)
    
    def _decrypt_secrets(self, file_path: Path) -> dict:
        """解密敏感配置"""
        # 实现解密逻辑
        # 例如使用 cryptography 库
        pass
    
    def get_safe(self, key: str, default=None):
        """安全获取配置（不记录日志）"""
        # 避免在日志中暴露敏感信息
        return self.config.get(key, default)

# 使用示例
secure_config = SecureConfig()
db_password = secure_config.get_safe("database.password")
```

### 配置访问控制

```python
from kernel.config import Config
from typing import Set

class ProtectedConfig:
    """受保护的配置"""
    
    def __init__(self, config: Config):
        self._config = config
        self._protected_keys: Set[str] = {
            "database.password",
            "api.key",
            "secret_key",
            "credentials.password"
        }
    
    def get(self, key: str, default=None):
        """获取配置值"""
        if key in self._protected_keys:
            # 记录敏感配置访问
            self._audit_access(key)
        return self._config.get(key, default)
    
    def set(self, key: str, value):
        """设置配置值"""
        if key in self._protected_keys:
            # 验证权限
            self._check_permission(key)
        self._config.set(key, value)
    
    def _audit_access(self, key: str):
        """审计敏感配置访问"""
        # 记录访问日志
        print(f"Sensitive config accessed: {key}")
    
    def _check_permission(self, key: str):
        """检查修改权限"""
        # 实现权限检查
        pass
```

### 配置加密

```python
from kernel.config import Config
from cryptography.fernet import Fernet
import json

class EncryptedConfig:
    """加密配置管理"""
    
    def __init__(self, key: bytes = None):
        if key is None:
            # 从环境变量获取密钥
            import os
            key_str = os.getenv("CONFIG_ENCRYPTION_KEY")
            if not key_str:
                raise ValueError("CONFIG_ENCRYPTION_KEY not set")
            key = key_str.encode()
        
        self.cipher = Fernet(key)
    
    def encrypt_config(self, config: Config, output_file: str):
        """加密并保存配置"""
        # 获取配置数据
        data = config.all()
        
        # 序列化
        json_data = json.dumps(data).encode()
        
        # 加密
        encrypted_data = self.cipher.encrypt(json_data)
        
        # 保存
        with open(output_file, 'wb') as f:
            f.write(encrypted_data)
    
    def decrypt_config(self, input_file: str) -> Config:
        """解密配置"""
        # 读取加密数据
        with open(input_file, 'rb') as f:
            encrypted_data = f.read()
        
        # 解密
        json_data = self.cipher.decrypt(encrypted_data)
        
        # 反序列化
        data = json.loads(json_data.decode())
        
        # 创建配置
        return Config.from_dict(data)

# 使用示例
# 生成密钥
# key = Fernet.generate_key()
# print(key.decode())  # 保存到环境变量

# 加密配置
config = Config(
    database_password="secret123",
    api_key="key123"
)
encryptor = EncryptedConfig()
encryptor.encrypt_config(config, "config.enc")

# 解密配置
decrypted_config = encryptor.decrypt_config("config.enc")
```

---

## 性能优化

### 配置缓存

```python
from kernel.config import Config
from functools import lru_cache
from typing import Any

class OptimizedConfig:
    """优化的配置管理"""
    
    def __init__(self, config: Config):
        self._config = config
    
    @lru_cache(maxsize=128)
    def get_cached(self, key: str) -> Any:
        """缓存的配置获取"""
        return self._config.get(key)
    
    def set(self, key: str, value: Any):
        """设置配置并清除缓存"""
        self._config.set(key, value)
        # 清除缓存
        self.get_cached.cache_clear()
    
    def invalidate_cache(self, key: str = None):
        """使缓存失效"""
        if key is None:
            # 清除所有缓存
            self.get_cached.cache_clear()
        else:
            # 清除特定键的缓存（需要自定义实现）
            pass

# 使用示例
config = Config.from_file("config.json")
optimized = OptimizedConfig(config)

# 第一次访问，从配置加载
value1 = optimized.get_cached("database.host")  # 较慢

# 第二次访问，从缓存获取
value2 = optimized.get_cached("database.host")  # 很快
```

### 延迟初始化

```python
from kernel.config import Config
from typing import Optional, Any

class LazyConfig:
    """延迟初始化的配置"""
    
    def __init__(self, config_file: str):
        self._config_file = config_file
        self._config: Optional[Config] = None
        self._cache: dict = {}
    
    @property
    def config(self) -> Config:
        """延迟加载配置"""
        if self._config is None:
            self._config = Config.from_file(self._config_file)
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置（带缓存）"""
        if key not in self._cache:
            self._cache[key] = self.config.get(key, default)
        return self._cache[key]
```

### 配置预加载

```python
from kernel.config import ConfigManager
from concurrent.futures import ThreadPoolExecutor
from typing import List

class PreloadedConfigManager:
    """预加载配置管理器"""
    
    def __init__(self):
        self.manager = ConfigManager()
    
    def preload_configs(self, config_files: List[tuple]):
        """并行预加载配置"""
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for name, file_path in config_files:
                future = executor.submit(
                    self.manager.load_from_file,
                    name,
                    file_path
                )
                futures.append(future)
            
            # 等待所有配置加载完成
            for future in futures:
                future.result()
    
    def get(self, name: str) -> Config:
        """获取配置"""
        return self.manager.get(name)

# 使用示例
manager = PreloadedConfigManager()

# 预加载所有配置
configs = [
    ("app", "config/app.json"),
    ("database", "config/database.json"),
    ("cache", "config/cache.json"),
    ("api", "config/api.json"),
]
manager.preload_configs(configs)

# 快速获取配置
app_config = manager.get("app")
```

---

## 错误处理

### 优雅降级

```python
from kernel.config import Config, ConfigLoadError
from kernel.logger import get_logger

logger = get_logger(__name__)

def load_config_with_fallback() -> Config:
    """带回退的配置加载"""
    
    # 尝试加载主配置
    try:
        config = Config.from_file("config/prod.json")
        logger.info("Loaded production config")
        return config
    except ConfigLoadError as e:
        logger.warning(f"Failed to load prod config: {e}")
    
    # 回退到开发配置
    try:
        config = Config.from_file("config/dev.json")
        logger.info("Loaded development config as fallback")
        return config
    except ConfigLoadError as e:
        logger.warning(f"Failed to load dev config: {e}")
    
    # 使用默认配置
    logger.info("Using default config")
    return Config(
        host="localhost",
        port=8000,
        debug=True
    )
```

### 错误恢复

```python
from kernel.config import Config, ConfigValidationError
from kernel.logger import get_logger

logger = get_logger(__name__)

def load_and_validate_config(file_path: str) -> Config:
    """加载并验证配置（带错误恢复）"""
    
    try:
        # 加载配置
        config = Config.from_file(file_path)
        
        # 验证配置
        config.validate()
        
        logger.info(f"Config loaded and validated: {file_path}")
        return config
        
    except ConfigValidationError as e:
        logger.error(f"Config validation failed: {e}")
        
        # 尝试修复配置
        try:
            config = fix_invalid_config(config)
            logger.info("Config fixed successfully")
            return config
        except Exception as fix_error:
            logger.error(f"Failed to fix config: {fix_error}")
            raise
    
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise

def fix_invalid_config(config: Config) -> Config:
    """修复无效配置"""
    # 设置缺失的必需键
    if not config.has("database.host"):
        config.set("database.host", "localhost")
    
    if not config.has("database.port"):
        config.set("database.port", 5432)
    
    # 修正无效值
    port = config.get("server.port", 0)
    if not (1 <= port <= 65535):
        config.set("server.port", 8000)
    
    # 重新验证
    config.validate()
    return config
```

### 详细错误报告

```python
from kernel.config import Config, ConfigError
from kernel.logger import get_logger
import traceback

logger = get_logger(__name__)

def detailed_config_error_handler(func):
    """配置错误处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConfigError as e:
            # 记录详细错误信息
            logger.error(f"Configuration error in {func.__name__}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")
            
            # 记录配置状态
            if hasattr(e, 'config'):
                logger.error(f"Config state: {e.config.all()}")
            
            raise
    return wrapper

@detailed_config_error_handler
def load_critical_config() -> Config:
    """加载关键配置"""
    config = Config.from_file("config.json")
    config.validate()
    return config
```

---

## 测试

### 测试配置

```python
import pytest
from kernel.config import Config

@pytest.fixture
def test_config():
    """测试配置 fixture"""
    return Config(
        debug=True,
        testing=True,
        database_url="sqlite:///:memory:",
        cache_enabled=False
    )

def test_with_config(test_config):
    """使用测试配置"""
    assert test_config.get("testing") is True
    assert test_config.get("debug") is True
```

### Mock 配置

```python
from unittest.mock import Mock, patch
from kernel.config import Config

def test_with_mock_config():
    """使用 Mock 配置"""
    mock_config = Mock(spec=Config)
    mock_config.get.return_value = "test_value"
    
    # 使用 mock 配置
    value = mock_config.get("key")
    assert value == "test_value"
    
    # 验证调用
    mock_config.get.assert_called_once_with("key")

def test_with_patched_config():
    """使用 patch 的配置"""
    with patch('kernel.config.Config.from_file') as mock_from_file:
        # 设置 mock 返回值
        mock_config = Config(test_mode=True)
        mock_from_file.return_value = mock_config
        
        # 测试代码
        config = Config.from_file("config.json")
        assert config.get("test_mode") is True
```

### 集成测试

```python
import pytest
from pathlib import Path
from kernel.config import Config
import json

@pytest.fixture
def temp_config_file(tmp_path):
    """创建临时配置文件"""
    config_file = tmp_path / "config.json"
    config_data = {
        "app": "test_app",
        "debug": True,
        "database": {
            "host": "localhost",
            "port": 5432
        }
    }
    config_file.write_text(json.dumps(config_data))
    return config_file

def test_config_loading(temp_config_file):
    """测试配置加载"""
    config = Config.from_file(str(temp_config_file))
    
    assert config.get("app") == "test_app"
    assert config.get("debug") is True
    assert config.get("database.host") == "localhost"
    assert config.get("database.port") == 5432

def test_config_modification(temp_config_file):
    """测试配置修改"""
    config = Config.from_file(str(temp_config_file))
    
    # 修改配置
    config.set("app", "modified_app")
    config.set("database.port", 3306)
    
    # 保存配置
    config.save(str(temp_config_file))
    
    # 重新加载并验证
    reloaded_config = Config.from_file(str(temp_config_file))
    assert reloaded_config.get("app") == "modified_app"
    assert reloaded_config.get("database.port") == 3306
```

---

## 常见模式

### 单例配置

```python
from kernel.config import Config
from typing import Optional

class AppConfig:
    """应用配置单例"""
    _instance: Optional[Config] = None
    
    @classmethod
    def get_instance(cls) -> Config:
        """获取配置实例"""
        if cls._instance is None:
            cls._instance = Config.from_file("config.json")
        return cls._instance
    
    @classmethod
    def reload(cls):
        """重新加载配置"""
        cls._instance = None
        return cls.get_instance()

# 使用
config = AppConfig.get_instance()
```

### 配置继承

```python
from kernel.config import Config

class DatabaseConfig(Config):
    """数据库配置"""
    
    def __init__(self, **kwargs):
        # 设置默认值
        defaults = {
            "host": "localhost",
            "port": 5432,
            "pool_size": 10,
            "timeout": 30
        }
        defaults.update(kwargs)
        super().__init__(**defaults)
    
    def get_connection_string(self) -> str:
        """获取连接字符串"""
        host = self.get("host")
        port = self.get("port")
        database = self.get("database")
        return f"postgresql://{host}:{port}/{database}"

# 使用
db_config = DatabaseConfig(database="mydb")
conn_str = db_config.get_connection_string()
```

### 配置构建器

```python
from kernel.config import Config

class ConfigBuilder:
    """配置构建器"""
    
    def __init__(self):
        self._config = Config()
    
    def with_database(self, host: str, port: int, database: str):
        """添加数据库配置"""
        self._config.set("database.host", host)
        self._config.set("database.port", port)
        self._config.set("database.name", database)
        return self
    
    def with_cache(self, enabled: bool, ttl: int):
        """添加缓存配置"""
        self._config.set("cache.enabled", enabled)
        self._config.set("cache.ttl", ttl)
        return self
    
    def with_logging(self, level: str, file: str):
        """添加日志配置"""
        self._config.set("logging.level", level)
        self._config.set("logging.file", file)
        return self
    
    def build(self) -> Config:
        """构建配置"""
        return self._config

# 使用
config = (ConfigBuilder()
    .with_database("localhost", 5432, "mydb")
    .with_cache(True, 3600)
    .with_logging("INFO", "app.log")
    .build())
```

### 配置上下文管理器

```python
from kernel.config import Config
from typing import Optional

class ConfigContext:
    """配置上下文管理器"""
    
    def __init__(self, config: Config, overrides: dict):
        self.config = config
        self.overrides = overrides
        self.original_values = {}
    
    def __enter__(self):
        """进入上下文"""
        # 保存原始值
        for key, value in self.overrides.items():
            if self.config.has(key):
                self.original_values[key] = self.config.get(key)
            self.config.set(key, value)
        return self.config
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        # 恢复原始值
        for key, value in self.original_values.items():
            self.config.set(key, value)
        # 删除临时添加的键
        for key in self.overrides:
            if key not in self.original_values:
                self.config.delete(key)

# 使用
config = Config(debug=False, cache_enabled=True)

with ConfigContext(config, {"debug": True, "cache_enabled": False}):
    # 在这个作用域内，配置被临时修改
    assert config.get("debug") is True
    assert config.get("cache_enabled") is False

# 退出作用域后，配置恢复原值
assert config.get("debug") is False
assert config.get("cache_enabled") is True
```

---

## 总结

遵循这些最佳实践可以帮助你：

1. **提高代码质量** - 通过验证和类型安全
2. **增强安全性** - 保护敏感信息
3. **提升性能** - 通过缓存和优化
4. **简化维护** - 清晰的组织和错误处理
5. **便于测试** - 使用测试配置和 mock

记住关键原则：
- 分离关注点
- 提供合理默认值
- 验证配置
- 保护敏感信息
- 优雅处理错误
- 编写测试

更多信息请参考 [README](README.md) 和 [API 参考](API_REFERENCE.md)。
