"""
日志系统使用示例

展示各种日志功能的使用方法
"""

from kernel.logger import (
    setup_logger,
    get_logger,
    LoggerConfig,
    with_metadata,
    create_development_config,
    create_production_config,
    create_auto_cleaner,
    LogMetadata
)


def basic_usage_example():
    """基本使用示例"""
    print("\n=== 基本使用示例 ===")
    
    # 1. 设置日志系统（使用默认配置）
    setup_logger()
    
    # 2. 获取日志器
    logger = get_logger(__name__)
    
    # 3. 记录不同级别的日志
    logger.debug("这是一条调试信息")
    logger.info("这是一条普通信息")
    logger.warning("这是一条警告信息")
    logger.error("这是一条错误信息")
    logger.critical("这是一条严重错误信息")


def custom_config_example():
    """自定义配置示例"""
    print("\n=== 自定义配置示例 ===")
    
    # 创建自定义配置
    config = LoggerConfig(
        name="my_app",
        level="DEBUG",
        console_enabled=True,
        console_colors=True,
        file_enabled=True,
        file_path="logs/my_app.log",
        file_format="json",  # 使用JSON格式
        error_file_enabled=True,
        error_file_path="logs/error.log",
    )
    
    # 使用自定义配置设置日志系统
    setup_logger(config)
    
    logger = get_logger("my_app")
    logger.info("使用自定义配置的日志")


def metadata_example():
    """元数据使用示例"""
    print("\n=== 元数据使用示例 ===")
    
    setup_logger()
    logger = get_logger(__name__)
    
    # 方式1: 使用上下文管理器
    with with_metadata(user_id="user123", session_id="sess456"):
        logger.info("用户登录")
        logger.info("用户执行操作")
    
    # 方式2: 手动设置元数据
    LogMetadata.set_user_id("user789")
    LogMetadata.set_session_id("sess101")
    LogMetadata.set_custom("ip_address", "192.168.1.100")
    logger.info("带自定义元数据的日志")
    
    # 清除元数据
    LogMetadata.clear()
    logger.info("元数据已清除")


def exception_logging_example():
    """异常日志示例"""
    print("\n=== 异常日志示例 ===")
    
    setup_logger()
    logger = get_logger(__name__)
    
    try:
        # 模拟异常
        result = 1 / 0
    except Exception:
        # 记录异常（会自动包含堆栈信息）
        logger.exception("发生了除零错误")


def environment_config_example():
    """不同环境配置示例"""
    print("\n=== 环境配置示例 ===")
    
    # 开发环境配置
    dev_config = create_development_config()
    setup_logger(dev_config)
    logger = get_logger("dev")
    logger.debug("开发环境日志（显示DEBUG级别）")
    
    # 生产环境配置
    prod_config = create_production_config()
    setup_logger(prod_config)
    logger = get_logger("prod")
    logger.debug("生产环境日志（不会显示DEBUG级别）")
    logger.info("生产环境日志（只显示INFO及以上）")


def log_cleanup_example():
    """日志清理示例"""
    print("\n=== 日志清理示例 ===")
    
    # 创建自动清理器
    cleaner = create_auto_cleaner(
        log_directory="logs",
        max_age_days=30,        # 保留30天
        max_size_mb=100,        # 最大100MB
        compress_after_days=7   # 7天后压缩
    )
    
    # 执行清理
    results = cleaner.run()
    print(f"清理结果: {results}")


def structured_logging_example():
    """结构化日志示例"""
    print("\n=== 结构化日志示例 ===")
    
    # 使用JSON格式的配置
    config = LoggerConfig(
        console_enabled=True,
        file_enabled=True,
        file_path="logs/structured.log",
        file_format="json",
        include_metadata=True
    )
    setup_logger(config)
    
    logger = get_logger(__name__)
    
    with with_metadata(
        user_id="user123",
        action="purchase",
        product_id="prod456"
    ):
        logger.info("用户完成购买")


def multi_logger_example():
    """多日志器示例"""
    print("\n=== 多日志器示例 ===")
    
    setup_logger()
    
    # 为不同模块创建不同的日志器
    auth_logger = get_logger("auth")
    db_logger = get_logger("database")
    api_logger = get_logger("api")
    
    auth_logger.info("用户认证成功")
    db_logger.debug("执行数据库查询")
    api_logger.warning("API调用频率过高")


if __name__ == "__main__":
    # 运行所有示例
    print("MoFox Logger 使用示例")
    print("=" * 50)
    
    basic_usage_example()
    custom_config_example()
    metadata_example()
    exception_logging_example()
    environment_config_example()
    structured_logging_example()
    multi_logger_example()
    
    # 注意：log_cleanup_example() 会实际清理日志文件，这里注释掉
    # log_cleanup_example()
    
    print("\n" + "=" * 50)
    print("示例运行完成！")
