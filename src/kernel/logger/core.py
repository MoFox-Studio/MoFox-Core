"""
日志系统核心模块

提供日志系统的主入口和全局接口
"""
import logging
from typing import Optional, Dict, List

from .config import LoggerConfig, ConfigManager
from .handlers import (
    ConsoleHandler,
    FileHandler,
    TimedFileHandler,
    ErrorFileHandler,
    AsyncHandler
)
from .metadata import LogMetadata, MetadataContext
from .cleanup import LogCleaner, AutoCleaner


class LoggerManager:
    """日志管理器（单例）"""
    
    _instance: Optional['LoggerManager'] = None
    _initialized: bool = False
    _loggers: Dict[str, logging.Logger] = {}
    _config: Optional[LoggerConfig] = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化日志管理器"""
        # 单例模式下，只初始化一次
        if not self._initialized:
            self._config = None
            self._loggers = {}
            self._handlers: List[logging.Handler] = []
            self._initialized = True
    
    def setup(self, config: Optional[LoggerConfig] = None) -> None:
        """
        设置日志系统
        
        Args:
            config: 日志配置对象，如果为None则使用默认配置
        """
        if config is None:
            config = LoggerConfig()
        
        self._config = config
        ConfigManager().set_config(config)
        
        # 清理已有的处理器
        self._clear_handlers()
        
        # 设置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(config.get_level_value(config.level))
        
        # 添加控制台处理器
        if config.console_enabled:
            console_handler = ConsoleHandler(
                level=config.get_level_value(config.console_level),
                use_colors=config.console_colors,
                include_metadata=config.include_metadata
            )
            
            if config.async_logging:
                console_handler = AsyncHandler(
                    console_handler,
                    queue_size=config.async_queue_size
                )
            
            root_logger.addHandler(console_handler)
            self._handlers.append(console_handler)
        
        # 添加文件处理器
        if config.file_enabled:
            file_handler = FileHandler(
                filename=config.file_path,
                level=config.get_level_value(config.file_level),
                max_bytes=config.file_max_bytes,
                backup_count=config.file_backup_count,
                use_json=(config.file_format == 'json'),
                include_metadata=config.include_metadata
            )
            
            if config.async_logging:
                file_handler = AsyncHandler(
                    file_handler,
                    queue_size=config.async_queue_size
                )
            
            root_logger.addHandler(file_handler)
            self._handlers.append(file_handler)
        
        # 添加错误文件处理器
        if config.error_file_enabled:
            error_handler = ErrorFileHandler(
                filename=config.error_file_path,
                max_bytes=config.error_file_max_bytes,
                backup_count=config.error_file_backup_count,
                use_json=(config.file_format == 'json'),
                include_metadata=config.include_metadata
            )
            
            if config.async_logging:
                error_handler = AsyncHandler(
                    error_handler,
                    queue_size=config.async_queue_size
                )
            
            root_logger.addHandler(error_handler)
            self._handlers.append(error_handler)
        
        # 添加时间轮转文件处理器
        if config.timed_file_enabled:
            timed_handler = TimedFileHandler(
                filename=config.timed_file_path,
                level=config.get_level_value(config.file_level),
                when=config.timed_file_when,
                interval=config.timed_file_interval,
                backup_count=config.timed_file_backup_count,
                use_json=(config.file_format == 'json'),
                include_metadata=config.include_metadata
            )
            
            if config.async_logging:
                timed_handler = AsyncHandler(
                    timed_handler,
                    queue_size=config.async_queue_size
                )
            
            root_logger.addHandler(timed_handler)
            self._handlers.append(timed_handler)
        
        # 设置第三方库日志级别
        for lib_name, level_str in config.third_party_levels.items():
            lib_logger = logging.getLogger(lib_name)
            lib_logger.setLevel(config.get_level_value(level_str))
        
        # 记录初始化完成
        logger = self.get_logger(config.name)
        logger.info(f"Logger system initialized with config: {config.name}")
    
    def _clear_handlers(self) -> None:
        """清理所有处理器"""
        root_logger = logging.getLogger()
        
        # 关闭并移除所有处理器
        for handler in self._handlers[:]:
            try:
                handler.close()
                root_logger.removeHandler(handler)
            except Exception:
                pass
        
        self._handlers.clear()
    
    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """
        获取日志器
        
        Args:
            name: 日志器名称，如果为None则返回根日志器
            
        Returns:
            日志器对象
        """
        if name is None:
            return logging.getLogger()
        
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        
        return self._loggers[name]
    
    def set_level(self, level: str, logger_name: Optional[str] = None) -> None:
        """
        设置日志级别
        
        Args:
            level: 日志级别字符串
            logger_name: 日志器名称，None表示设置根日志器
        """
        logger = self.get_logger(logger_name)
        if self._config:
            logger.setLevel(self._config.get_level_value(level))
    
    def shutdown(self) -> None:
        """关闭日志系统"""
        self._clear_handlers()
        self._loggers.clear()
        logging.shutdown()
    
    def get_config(self) -> Optional[LoggerConfig]:
        """获取当前配置"""
        return self._config


# 全局日志管理器实例
_manager = LoggerManager()


def setup_logger(config: Optional[LoggerConfig] = None) -> None:
    """
    设置日志系统（全局函数）
    
    Args:
        config: 日志配置对象
    """
    _manager.setup(config)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志器（全局函数）
    
    Args:
        name: 日志器名称
        
    Returns:
        日志器对象
    """
    return _manager.get_logger(name)


def set_level(level: str, logger_name: Optional[str] = None) -> None:
    """
    设置日志级别（全局函数）
    
    Args:
        level: 日志级别字符串
        logger_name: 日志器名称
    """
    _manager.set_level(level, logger_name)


def shutdown() -> None:
    """关闭日志系统（全局函数）"""
    _manager.shutdown()


def with_metadata(**kwargs):
    """
    创建元数据上下文管理器（装饰器友好）
    
    Args:
        **kwargs: 元数据键值对
        
    Returns:
        元数据上下文管理器
    """
    return MetadataContext(**kwargs)


# 便捷日志函数
def debug(message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    """记录DEBUG级别日志"""
    get_logger(logger_name).debug(message, **kwargs)


def info(message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    """记录INFO级别日志"""
    get_logger(logger_name).info(message, **kwargs)


def warning(message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    """记录WARNING级别日志"""
    get_logger(logger_name).warning(message, **kwargs)


def error(message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    """记录ERROR级别日志"""
    get_logger(logger_name).error(message, **kwargs)


def critical(message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    """记录CRITICAL级别日志"""
    get_logger(logger_name).critical(message, **kwargs)


def exception(message: str, logger_name: Optional[str] = None, **kwargs) -> None:
    """记录异常日志（自动包含异常堆栈）"""
    get_logger(logger_name).exception(message, **kwargs)


# 导出清理相关功能
def create_cleaner(log_directory: str = "logs") -> LogCleaner:
    """
    创建日志清理器
    
    Args:
        log_directory: 日志目录
        
    Returns:
        日志清理器实例
    """
    return LogCleaner(log_directory)


def create_auto_cleaner(
    log_directory: str = "logs",
    max_age_days: int = 30,
    max_size_mb: int = 100,
    compress_after_days: int = 7
) -> AutoCleaner:
    """
    创建自动清理器
    
    Args:
        log_directory: 日志目录
        max_age_days: 最大保留天数
        max_size_mb: 最大目录大小
        compress_after_days: 多少天后压缩
        
    Returns:
        自动清理器实例
    """
    return AutoCleaner(
        log_directory=log_directory,
        max_age_days=max_age_days,
        max_size_mb=max_size_mb,
        compress_after_days=compress_after_days
    )


__all__ = [
    # 主要接口
    'setup_logger',
    'get_logger',
    'set_level',
    'shutdown',
    'with_metadata',
    # 便捷函数
    'debug',
    'info',
    'warning',
    'error',
    'critical',
    'exception',
    # 配置类
    'LoggerConfig',
    'LoggerManager',
    # 元数据
    'LogMetadata',
    'MetadataContext',
    # 清理功能
    'LogCleaner',
    'AutoCleaner',
    'create_cleaner',
    'create_auto_cleaner',
]
