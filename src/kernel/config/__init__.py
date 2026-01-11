"""
Config 模块

提供统一的配置管理功能
"""

from .config_base import (
    BaseConfig,
    ConfigLoader,
    ConfigMetadata,
    ConfigSource,
    ConfigFormat,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ConfigLoadError
)

from .config import (
    Config,
    ConfigManager,
    get_manager,
    get_config,
    load_config,
    register_config
)

__all__ = [
    # Base
    "BaseConfig",
    "ConfigLoader",
    "ConfigMetadata",
    "ConfigSource",
    "ConfigFormat",
    
    # Exceptions
    "ConfigError",
    "ConfigNotFoundError",
    "ConfigValidationError",
    "ConfigLoadError",
    
    # Config
    "Config",
    "ConfigManager",
    
    # Functions
    "get_manager",
    "get_config",
    "load_config",
    "register_config",
]

__version__ = "0.1.0"