"""
配置管理器

提供统一的配置管理功能
"""

from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from datetime import datetime

from .config_base import (
    BaseConfig,
    ConfigLoader,
    ConfigSource,
    ConfigFormat,
    ConfigError,
    ConfigNotFoundError
)

try:
    from ..logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class Config(BaseConfig):
    """通用配置类
    
    提供完整的配置管理功能
    """
    
    def __init__(self, **kwargs):
        """初始化配置
        
        Args:
            **kwargs: 配置参数
        """
        super().__init__(**kwargs)
    
    def _validate(self) -> bool:
        """验证配置
        
        Returns:
            bool: 配置是否有效
        """
        # 通用配置没有特殊验证规则
        return True
    
    @classmethod
    def from_file(cls, file_path: str) -> 'Config':
        """从文件创建配置
        
        Args:
            file_path: 配置文件路径
            
        Returns:
            Config: 配置实例
        """
        data = ConfigLoader.load_from_file(file_path)
        config = cls(**data)
        
        # 更新元数据
        config._metadata.source = ConfigSource.FILE
        config._metadata.file_path = file_path
        config._metadata.loaded_at = datetime.now().isoformat()
        
        # 推断格式
        suffix = Path(file_path).suffix.lower()
        if suffix == ".json":
            config._metadata.format = ConfigFormat.JSON
        elif suffix in [".yaml", ".yml"]:
            config._metadata.format = ConfigFormat.YAML
        elif suffix == ".env":
            config._metadata.format = ConfigFormat.ENV
        elif suffix == ".py":
            config._metadata.format = ConfigFormat.PYTHON
        
        logger.info(f"Config loaded from {file_path}")
        return config
    
    @classmethod
    def from_env(cls, prefix: str = "") -> 'Config':
        """从环境变量创建配置
        
        Args:
            prefix: 环境变量前缀
            
        Returns:
            Config: 配置实例
        """
        data = ConfigLoader.load_from_env(prefix)
        config = cls(**data)
        config._metadata.source = ConfigSource.ENV
        config._metadata.loaded_at = datetime.now().isoformat()
        
        logger.info(f"Config loaded from environment variables (prefix: {prefix})")
        return config
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """从字典创建配置
        
        Args:
            data: 配置字典
            
        Returns:
            Config: 配置实例
        """
        config = cls(**data)
        config._metadata.source = ConfigSource.DICT
        config._metadata.loaded_at = datetime.now().isoformat()
        
        logger.info("Config loaded from dictionary")
        return config
    
    def save(self, file_path: str):
        """保存配置到文件
        
        Args:
            file_path: 文件路径
        """
        ConfigLoader.save_to_file(self.to_dict(), file_path)
        self._metadata.file_path = file_path
    
    def merge(self, other: Union['Config', Dict[str, Any]], overwrite: bool = True):
        """合并配置
        
        Args:
            other: 另一个配置或字典
            overwrite: 是否覆盖现有值
        """
        if isinstance(other, Config):
            data = other.to_dict()
        else:
            data = other
        
        for key, value in data.items():
            if overwrite or not self.has(key):
                self.set(key, value)
        
        logger.debug(f"Config merged with {len(data)} keys")
    
    def reload(self):
        """重新加载配置
        
        只对从文件加载的配置有效
        
        Raises:
            ConfigError: 配置不是从文件加载的
        """
        if self._metadata.source != ConfigSource.FILE:
            raise ConfigError("Cannot reload: config was not loaded from file")
        
        if not self._metadata.file_path:
            raise ConfigError("Cannot reload: file path is unknown")
        
        # 重新加载
        data = ConfigLoader.load_from_file(self._metadata.file_path)
        self._data = {}
        self._load_from_dict(data)
        self._metadata.loaded_at = datetime.now().isoformat()
        self._metadata.modified_keys.clear()
        
        logger.info(f"Config reloaded from {self._metadata.file_path}")


class ConfigManager:
    """配置管理器
    
    管理多个配置实例
    """
    
    def __init__(self):
        """初始化配置管理器"""
        self._configs: Dict[str, Config] = {}
        self._default_name = "default"
    
    def register(self, name: str, config: Config):
        """注册配置
        
        Args:
            name: 配置名称
            config: 配置实例
        """
        self._configs[name] = config
        logger.info(f"Config registered: {name}")
    
    def unregister(self, name: str):
        """注销配置
        
        Args:
            name: 配置名称
        """
        if name in self._configs:
            del self._configs[name]
            logger.info(f"Config unregistered: {name}")
    
    def get(self, name: Optional[str] = None) -> Config:
        """获取配置
        
        Args:
            name: 配置名称，None 则返回默认配置
            
        Returns:
            Config: 配置实例
            
        Raises:
            ConfigNotFoundError: 配置不存在
        """
        name = name or self._default_name
        
        if name not in self._configs:
            raise ConfigNotFoundError(f"Config not found: {name}")
        
        return self._configs[name]
    
    def has(self, name: str) -> bool:
        """检查配置是否存在
        
        Args:
            name: 配置名称
            
        Returns:
            bool: 是否存在
        """
        return name in self._configs
    
    def list_configs(self) -> List[str]:
        """列出所有配置名称
        
        Returns:
            List[str]: 配置名称列表
        """
        return list(self._configs.keys())
    
    def set_default(self, name: str):
        """设置默认配置
        
        Args:
            name: 配置名称
            
        Raises:
            ConfigNotFoundError: 配置不存在
        """
        if name not in self._configs:
            raise ConfigNotFoundError(f"Config not found: {name}")
        
        self._default_name = name
        logger.info(f"Default config set to: {name}")
    
    def load_from_file(self, name: str, file_path: str, set_default: bool = False):
        """从文件加载配置
        
        Args:
            name: 配置名称
            file_path: 文件路径
            set_default: 是否设置为默认配置
        """
        config = Config.from_file(file_path)
        self.register(name, config)
        
        if set_default:
            self.set_default(name)
    
    def load_from_env(self, name: str, prefix: str = "", set_default: bool = False):
        """从环境变量加载配置
        
        Args:
            name: 配置名称
            prefix: 环境变量前缀
            set_default: 是否设置为默认配置
        """
        config = Config.from_env(prefix)
        self.register(name, config)
        
        if set_default:
            self.set_default(name)
    
    def load_from_dict(self, name: str, data: Dict[str, Any], set_default: bool = False):
        """从字典加载配置
        
        Args:
            name: 配置名称
            data: 配置字典
            set_default: 是否设置为默认配置
        """
        config = Config.from_dict(data)
        self.register(name, config)
        
        if set_default:
            self.set_default(name)
    
    def load_multi_files(
        self,
        configs: Dict[str, str],
        default: Optional[str] = None
    ):
        """从多个文件加载配置
        
        Args:
            configs: 配置名称到文件路径的映射
            default: 默认配置名称
        """
        for name, file_path in configs.items():
            self.load_from_file(name, file_path)
        
        if default:
            self.set_default(default)
    
    def reload_all(self):
        """重新加载所有配置"""
        for name, config in self._configs.items():
            try:
                config.reload()
                logger.info(f"Reloaded config: {name}")
            except ConfigError as e:
                logger.warning(f"Cannot reload config {name}: {e}")
    
    def clear(self):
        """清除所有配置"""
        self._configs.clear()
        logger.info("All configs cleared")


# 全局配置管理器
_global_manager: Optional[ConfigManager] = None


def get_manager() -> ConfigManager:
    """获取全局配置管理器
    
    Returns:
        ConfigManager: 全局配置管理器实例
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = ConfigManager()
    return _global_manager


def get_config(name: Optional[str] = None) -> Config:
    """获取配置（便捷函数）
    
    Args:
        name: 配置名称
        
    Returns:
        Config: 配置实例
    """
    return get_manager().get(name)


def load_config(
    name: str,
    source: Union[str, Dict[str, Any]],
    set_default: bool = False
):
    """加载配置（便捷函数）
    
    Args:
        name: 配置名称
        source: 文件路径或配置字典
        set_default: 是否设置为默认配置
    """
    manager = get_manager()
    
    if isinstance(source, str):
        manager.load_from_file(name, source, set_default)
    elif isinstance(source, dict):
        manager.load_from_dict(name, source, set_default)
    else:
        raise ConfigError(f"Invalid config source type: {type(source)}")


def register_config(name: str, config: Config):
    """注册配置（便捷函数）
    
    Args:
        name: 配置名称
        config: 配置实例
    """
    get_manager().register(name, config)