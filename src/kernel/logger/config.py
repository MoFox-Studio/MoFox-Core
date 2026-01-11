"""
日志配置辅助模块

提供日志系统的配置管理功能
"""
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class LoggerConfig:
    """日志配置类"""
    
    # 基本配置
    name: str = "mofox"
    level: str = "INFO"
    
    # 控制台配置
    console_enabled: bool = True
    console_level: str = "INFO"
    console_colors: bool = True
    
    # 文件配置
    file_enabled: bool = True
    file_level: str = "DEBUG"
    file_path: str = "logs/mofox.log"
    file_max_bytes: int = 10 * 1024 * 1024  # 10MB
    file_backup_count: int = 5
    file_format: str = "plain"  # plain, json
    
    # 错误文件配置
    error_file_enabled: bool = True
    error_file_path: str = "logs/error.log"
    error_file_max_bytes: int = 10 * 1024 * 1024
    error_file_backup_count: int = 5
    
    # 时间轮转配置
    timed_file_enabled: bool = False
    timed_file_path: str = "logs/mofox_timed.log"
    timed_file_when: str = "midnight"
    timed_file_interval: int = 1
    timed_file_backup_count: int = 30
    
    # 元数据配置
    include_metadata: bool = True
    
    # 异步配置
    async_logging: bool = False
    async_queue_size: int = 1000
    
    # 第三方库日志级别配置
    third_party_levels: Dict[str, str] = field(default_factory=lambda: {
        "urllib3": "WARNING",
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "asyncio": "WARNING",
    })
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'level': self.level,
            'console_enabled': self.console_enabled,
            'console_level': self.console_level,
            'console_colors': self.console_colors,
            'file_enabled': self.file_enabled,
            'file_level': self.file_level,
            'file_path': self.file_path,
            'file_max_bytes': self.file_max_bytes,
            'file_backup_count': self.file_backup_count,
            'file_format': self.file_format,
            'error_file_enabled': self.error_file_enabled,
            'error_file_path': self.error_file_path,
            'error_file_max_bytes': self.error_file_max_bytes,
            'error_file_backup_count': self.error_file_backup_count,
            'timed_file_enabled': self.timed_file_enabled,
            'timed_file_path': self.timed_file_path,
            'timed_file_when': self.timed_file_when,
            'timed_file_interval': self.timed_file_interval,
            'timed_file_backup_count': self.timed_file_backup_count,
            'include_metadata': self.include_metadata,
            'async_logging': self.async_logging,
            'async_queue_size': self.async_queue_size,
            'third_party_levels': self.third_party_levels,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LoggerConfig':
        """从字典创建配置"""
        return cls(**data)
    
    def get_level_value(self, level_str: str) -> int:
        """
        获取日志级别数值
        
        Args:
            level_str: 日志级别字符串
            
        Returns:
            日志级别数值
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        return level_map.get(level_str.upper(), logging.INFO)


class ConfigManager:
    """配置管理器"""
    
    _instance: Optional['ConfigManager'] = None
    _config: Optional[LoggerConfig] = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def set_config(self, config: LoggerConfig) -> None:
        """
        设置日志配置
        
        Args:
            config: 日志配置对象
        """
        self._config = config
    
    def get_config(self) -> LoggerConfig:
        """
        获取日志配置
        
        Returns:
            日志配置对象
        """
        if self._config is None:
            self._config = LoggerConfig()
        return self._config
    
    def update_config(self, **kwargs) -> None:
        """
        更新配置项
        
        Args:
            **kwargs: 要更新的配置项
        """
        config = self.get_config()
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    def reset_config(self) -> None:
        """重置为默认配置"""
        self._config = LoggerConfig()


def create_default_config() -> LoggerConfig:
    """
    创建默认配置
    
    Returns:
        默认日志配置
    """
    return LoggerConfig()


def create_development_config() -> LoggerConfig:
    """
    创建开发环境配置
    
    Returns:
        开发环境日志配置
    """
    return LoggerConfig(
        level="DEBUG",
        console_enabled=True,
        console_level="DEBUG",
        console_colors=True,
        file_enabled=True,
        file_level="DEBUG",
        error_file_enabled=True,
    )


def create_production_config() -> LoggerConfig:
    """
    创建生产环境配置
    
    Returns:
        生产环境日志配置
    """
    return LoggerConfig(
        level="INFO",
        console_enabled=False,
        file_enabled=True,
        file_level="INFO",
        file_format="json",
        error_file_enabled=True,
        timed_file_enabled=True,
        async_logging=True,
    )


def create_testing_config() -> LoggerConfig:
    """
    创建测试环境配置
    
    Returns:
        测试环境日志配置
    """
    return LoggerConfig(
        level="WARNING",
        console_enabled=True,
        console_level="WARNING",
        console_colors=False,
        file_enabled=False,
        error_file_enabled=False,
    )
