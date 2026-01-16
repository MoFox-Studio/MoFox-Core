"""
MoFox Logger - 日志系统模块

提供统一的日志记录、格式化、清理和管理功能

基本使用：
    from kernel.logger import setup_logger, get_logger
    
    # 设置日志系统
    setup_logger()
    
    # 获取日志器并记录日志
    logger = get_logger(__name__)
    logger.info("Hello, MoFox!")

高级使用：
    from kernel.logger import setup_logger, get_logger, LoggerConfig, with_metadata
    
    # 使用自定义配置
    config = LoggerConfig(
        level="DEBUG",
        console_colors=True,
        file_enabled=True,
        file_path="logs/app.log"
    )
    setup_logger(config)
    
    # 使用元数据
    with with_metadata(user_id="user123", session_id="sess456"):
        logger = get_logger(__name__)
        logger.info("User action")  # 日志会自动包含user_id和session_id
"""

# 核心功能
from .core import (
    setup_logger,
    get_logger,
    set_level,
    shutdown,
    with_metadata,
    LoggerManager,
)

# 便捷日志函数
from .core import (
    debug,
    info,
    warning,
    error,
    critical,
    exception,
)

# 配置相关
from .config import (
    LoggerConfig,
    ConfigManager,
    create_default_config,
    create_development_config,
    create_production_config,
    create_testing_config,
)

# 元数据管理
from .metadata import (
    LogMetadata,
    MetadataContext,
)

# 清理功能
from .cleanup import (
    LogCleaner,
    AutoCleaner,
)

from .core import (
    create_cleaner,
    create_auto_cleaner,
)

# 渲染器（高级用户）
from .renderers import (
    PlainRenderer,
    JSONRenderer,
    ColoredRenderer,
    StructuredRenderer,
    CustomFormatter,
)

# 处理器（高级用户）
from .handlers import (
    ConsoleHandler,
    FileHandler,
    TimedFileHandler,
    ErrorFileHandler,
    AsyncHandler,
    LogStoreHandler,
    NullHandler,
)


__all__ = [
    # 核心接口
    'setup_logger',
    'get_logger',
    'set_level',
    'shutdown',
    'with_metadata',
    'LoggerManager',
    
    # 便捷函数
    'debug',
    'info',
    'warning',
    'error',
    'critical',
    'exception',
    
    # 配置
    'LoggerConfig',
    'ConfigManager',
    'create_default_config',
    'create_development_config',
    'create_production_config',
    'create_testing_config',
    
    # 元数据
    'LogMetadata',
    'MetadataContext',
    
    # 清理
    'LogCleaner',
    'AutoCleaner',
    'create_cleaner',
    'create_auto_cleaner',
    
    # 渲染器
    'PlainRenderer',
    'JSONRenderer',
    'ColoredRenderer',
    'StructuredRenderer',
    'CustomFormatter',
    
    # 处理器
    'ConsoleHandler',
    'FileHandler',
    'TimedFileHandler',
    'ErrorFileHandler',
    'AsyncHandler',
    'LogStoreHandler',
    'NullHandler',
]


# 版本信息
__version__ = '1.0.0'
__author__ = 'MoFox Team'
