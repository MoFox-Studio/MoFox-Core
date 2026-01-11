"""
配置基础类

提供配置的抽象基类和通用功能
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Set, Callable
from dataclasses import dataclass, field
from pathlib import Path
import os
import json
from enum import Enum

try:
    from ..logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class ConfigFormat(Enum):
    """配置文件格式"""
    JSON = "json"
    YAML = "yaml"
    YML = "yml"
    ENV = "env"
    PYTHON = "py"


class ConfigSource(Enum):
    """配置来源"""
    FILE = "file"
    ENV = "env"
    DICT = "dict"
    DEFAULT = "default"


@dataclass
class ConfigMetadata:
    """配置元数据"""
    source: ConfigSource
    file_path: Optional[str] = None
    format: Optional[ConfigFormat] = None
    loaded_at: Optional[str] = None
    modified_keys: Set[str] = field(default_factory=set)


class ConfigError(Exception):
    """配置错误基类"""
    pass


class ConfigNotFoundError(ConfigError):
    """配置未找到"""
    pass


class ConfigValidationError(ConfigError):
    """配置验证失败"""
    pass


class ConfigLoadError(ConfigError):
    """配置加载失败"""
    pass


class BaseConfig(ABC):
    """配置抽象基类
    
    所有配置类应继承此基类
    """
    
    def __init__(self, **kwargs):
        """初始化配置
        
        Args:
            **kwargs: 配置参数
        """
        self._data: Dict[str, Any] = {}
        self._metadata = ConfigMetadata(source=ConfigSource.DEFAULT)
        self._validators: Dict[str, Callable[[Any], bool]] = {}
        self._required_keys: Set[str] = set()
        
        # 加载配置
        self._load_from_dict(kwargs)
    
    def _load_from_dict(self, data: Dict[str, Any]):
        """从字典加载配置
        
        Args:
            data: 配置字典
        """
        for key, value in data.items():
            self.set(key, value)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键 (e.g., "db.host")
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        keys = key.split(".")
        value = self._data
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any, validate: bool = True):
        """设置配置值
        
        Args:
            key: 配置键
            value: 配置值
            validate: 是否验证
            
        Raises:
            ConfigValidationError: 验证失败
        """
        # 验证
        if validate and key in self._validators:
            validator = self._validators[key]
            if not validator(value):
                raise ConfigValidationError(f"Validation failed for key: {key}")
        
        # 处理嵌套键
        keys = key.split(".")
        if len(keys) == 1:
            self._data[key] = value
        else:
            # 创建嵌套结构
            current = self._data
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value
        
        # 记录修改
        self._metadata.modified_keys.add(key)
        logger.debug(f"Config set: {key} = {value}")
    
    def has(self, key: str) -> bool:
        """检查配置键是否存在
        
        Args:
            key: 配置键
            
        Returns:
            bool: 是否存在
        """
        return self.get(key) is not None
    
    def delete(self, key: str):
        """删除配置键
        
        Args:
            key: 配置键
        """
        keys = key.split(".")
        if len(keys) == 1:
            self._data.pop(key, None)
        else:
            current = self._data
            for k in keys[:-1]:
                if k not in current:
                    return
                current = current[k]
            current.pop(keys[-1], None)
        
        logger.debug(f"Config deleted: {key}")
    
    def update(self, data: Dict[str, Any]):
        """批量更新配置
        
        Args:
            data: 配置字典
        """
        for key, value in data.items():
            self.set(key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典
        
        Returns:
            Dict: 配置字典
        """
        return self._data.copy()
    
    def keys(self) -> List[str]:
        """获取所有配置键
        
        Returns:
            List[str]: 配置键列表
        """
        return list(self._data.keys())
    
    def add_validator(self, key: str, validator: Callable[[Any], bool]):
        """添加验证器
        
        Args:
            key: 配置键
            validator: 验证函数，返回 bool
        """
        self._validators[key] = validator
    
    def add_required_key(self, key: str):
        """添加必需键
        
        Args:
            key: 配置键
        """
        self._required_keys.add(key)
    
    def validate(self) -> bool:
        """验证配置
        
        Returns:
            bool: 是否有效
            
        Raises:
            ConfigValidationError: 验证失败
        """
        # 检查必需键
        for key in self._required_keys:
            if not self.has(key):
                raise ConfigValidationError(f"Required key missing: {key}")
        
        # 执行自定义验证
        return self._validate()
    
    @abstractmethod
    def _validate(self) -> bool:
        """自定义验证逻辑
        
        Returns:
            bool: 是否有效
        """
        pass
    
    def get_metadata(self) -> ConfigMetadata:
        """获取元数据
        
        Returns:
            ConfigMetadata: 配置元数据
        """
        return self._metadata
    
    def __getitem__(self, key: str) -> Any:
        """字典式访问"""
        value = self.get(key)
        if value is None:
            raise KeyError(f"Config key not found: {key}")
        return value
    
    def __setitem__(self, key: str, value: Any):
        """字典式设置"""
        self.set(key, value)
    
    def __contains__(self, key: str) -> bool:
        """in 运算符支持"""
        return self.has(key)
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._data})"


class ConfigLoader:
    """配置加载器"""
    
    @staticmethod
    def load_from_file(file_path: str) -> Dict[str, Any]:
        """从文件加载配置
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict: 配置字典
            
        Raises:
            ConfigLoadError: 加载失败
        """
        path = Path(file_path)
        
        if not path.exists():
            raise ConfigNotFoundError(f"Config file not found: {file_path}")
        
        try:
            # 根据扩展名选择加载方式
            suffix = path.suffix.lower()
            
            if suffix == ".json":
                return ConfigLoader._load_json(path)
            elif suffix in [".yaml", ".yml"]:
                return ConfigLoader._load_yaml(path)
            elif suffix == ".env":
                return ConfigLoader._load_env(path)
            elif suffix == ".py":
                return ConfigLoader._load_python(path)
            else:
                raise ConfigLoadError(f"Unsupported file format: {suffix}")
        
        except Exception as e:
            logger.error(f"Failed to load config from {file_path}: {e}")
            raise ConfigLoadError(f"Failed to load config: {e}") from e
    
    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        """加载 JSON 文件"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        """加载 YAML 文件"""
        try:
            import importlib
            yaml = importlib.import_module("yaml")
        except Exception:
            raise ConfigLoadError(
                "PyYAML is required for YAML config files. "
                "Install with: pip install pyyaml"
            )
        
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    
    @staticmethod
    def _load_env(path: Path) -> Dict[str, Any]:
        """加载 .env 文件"""
        config = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()
        return config
    
    @staticmethod
    def _load_python(path: Path) -> Dict[str, Any]:
        """加载 Python 文件"""
        import importlib.util
        
        spec = importlib.util.spec_from_file_location("config_module", path)
        if spec is None or spec.loader is None:
            raise ConfigLoadError(f"Cannot load Python config: {path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 提取配置变量（大写的变量）
        config = {}
        for name in dir(module):
            if name.isupper() and not name.startswith("_"):
                config[name] = getattr(module, name)
        
        return config
    
    @staticmethod
    def load_from_env(prefix: str = "") -> Dict[str, Any]:
        """从环境变量加载配置
        
        Args:
            prefix: 环境变量前缀
            
        Returns:
            Dict: 配置字典
        """
        config = {}
        
        for key, value in os.environ.items():
            if not prefix or key.startswith(prefix):
                # 移除前缀
                config_key = key[len(prefix):] if prefix else key
                config[config_key] = value
        
        return config
    
    @staticmethod
    def save_to_file(config: Dict[str, Any], file_path: str):
        """保存配置到文件
        
        Args:
            config: 配置字典
            file_path: 文件路径
            
        Raises:
            ConfigLoadError: 保存失败
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            suffix = path.suffix.lower()
            
            if suffix == ".json":
                ConfigLoader._save_json(config, path)
            elif suffix in [".yaml", ".yml"]:
                ConfigLoader._save_yaml(config, path)
            elif suffix == ".env":
                ConfigLoader._save_env(config, path)
            else:
                raise ConfigLoadError(f"Unsupported file format for saving: {suffix}")
            
            logger.info(f"Config saved to {file_path}")
        
        except Exception as e:
            logger.error(f"Failed to save config to {file_path}: {e}")
            raise ConfigLoadError(f"Failed to save config: {e}") from e
    
    @staticmethod
    def _save_json(config: Dict[str, Any], path: Path):
        """保存为 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def _save_yaml(config: Dict[str, Any], path: Path):
        """保存为 YAML 文件"""
        try:
            import importlib
            yaml = importlib.import_module("yaml")
        except Exception:
            raise ConfigLoadError(
                "PyYAML is required for YAML config files. "
                "Install with: pip install pyyaml"
            )
        
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True)
    
    @staticmethod
    def _save_env(config: Dict[str, Any], path: Path):
        """保存为 .env 文件"""
        with open(path, "w", encoding="utf-8") as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")