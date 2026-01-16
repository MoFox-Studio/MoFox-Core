"""
Logger 与 Storage 模块集成示例

展示如何使用 LogStoreHandler 将日志直接存储到 JSON 文件中
"""
import logging
from pathlib import Path

# 导入 logger 模块
from kernel.logger import (
    setup_logger,
    get_logger,
    LoggerConfig,
    LogStoreHandler,
    MetadataContext,
)

# 导入 storage 模块
from kernel.storage import LogStore


class LoggerWithStorage:
    """集成 Logger 和 Storage 的日志系统"""
    
    def __init__(
        self,
        app_name: str = "myapp",
        log_dir: str = "logs",
        console_output: bool = True,
        json_storage: bool = True
    ):
        """
        初始化日志系统（集成存储）
        
        Args:
            app_name: 应用名称（用于日志文件前缀）
            log_dir: 日志目录
            console_output: 是否输出到控制台
            json_storage: 是否存储到 JSON 文件
        """
        self.app_name = app_name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建日志存储器
        if json_storage:
            self.log_store = LogStore(
                directory=str(self.log_dir),
                prefix=app_name,
                max_entries_per_file=1000,
                auto_rotate=True
            )
        else:
            self.log_store = None
        
        # 配置 logger
        config = LoggerConfig(
            level="DEBUG",
            console_enabled=console_output,
            console_colors=True,
            file_enabled=False,  # 我们使用 LogStore 代替普通文件
            include_metadata=True
        )
        
        setup_logger(config)
        
        # 添加存储处理器
        if self.log_store:
            self._add_storage_handler()
    
    def _add_storage_handler(self):
        """为根日志器添加存储处理器"""
        root_logger = logging.getLogger()
        
        # 创建并添加存储处理器
        storage_handler = LogStoreHandler(
            log_store=self.log_store,
            level=logging.DEBUG,
            include_metadata=True,
            include_exc_info=True
        )
        
        root_logger.addHandler(storage_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取日志器"""
        return get_logger(name)
    
    def get_logs(self, days: int = 1) -> dict:
        """获取最近N天的日志统计"""
        if not self.log_store:
            return {}
        
        from datetime import datetime, timedelta
        
        start_date = datetime.now() - timedelta(days=days)
        logs = self.log_store.get_logs(start_date=start_date)
        
        # 统计
        stats = {
            'total': len(logs),
            'by_level': {},
            'by_logger': {}
        }
        
        for log in logs:
            # 按日志级别统计
            level = log.get('level', 'UNKNOWN')
            stats['by_level'][level] = stats['by_level'].get(level, 0) + 1
            
            # 按日志器名称统计
            logger_name = log.get('logger', 'UNKNOWN')
            stats['by_logger'][logger_name] = stats['by_logger'].get(logger_name, 0) + 1
        
        return stats
    
    def get_error_logs(self, days: int = 1) -> list:
        """获取错误日志"""
        if not self.log_store:
            return []
        
        from datetime import datetime, timedelta
        
        start_date = datetime.now() - timedelta(days=days)
        logs = self.log_store.get_logs(
            start_date=start_date,
            filter_func=lambda log: log.get('level') in ['ERROR', 'CRITICAL']
        )
        return logs
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """清理旧日志"""
        if not self.log_store:
            return 0
        return self.log_store.clear_old_logs(days=days)


# ============================================================================
# 使用示例
# ============================================================================

def example_basic_usage():
    """基础使用示例"""
    print("\n=== 基础使用示例 ===\n")
    
    # 初始化日志系统（自动集成存储）
    logger_system = LoggerWithStorage(
        app_name="myapp",
        log_dir="logs",
        console_output=True,
        json_storage=True
    )
    
    # 获取日志器
    logger = logger_system.get_logger("app.main")
    
    # 记录日志
    logger.debug("调试信息")
    logger.info("应用启动")
    logger.warning("这是一个警告")
    logger.error("发生了一个错误")
    
    # 获取日志统计
    stats = logger_system.get_logs(days=1)
    print(f"\n日志统计: {stats}")


def example_with_metadata():
    """使用元数据的示例"""
    print("\n=== 使用元数据示例 ===\n")
    
    logger_system = LoggerWithStorage(
        app_name="myapp_with_metadata",
        log_dir="logs/metadata"
    )
    
    logger = logger_system.get_logger("app.users")
    
    # 使用上下文元数据
    with MetadataContext(user_id="user_123", request_id="req_456"):
        logger.info("用户登录")
        logger.info("处理用户请求")
    
    with MetadataContext(user_id="user_789", session_id="sess_abc"):
        logger.info("用户执行操作")
    
    # 查询日志
    logs = logger_system.get_logs(days=1)
    print(f"日志统计: {logs}")


def example_error_tracking():
    """错误追踪示例"""
    print("\n=== 错误追踪示例 ===\n")
    
    logger_system = LoggerWithStorage(
        app_name="myapp_errors",
        log_dir="logs/errors"
    )
    
    logger = logger_system.get_logger("app.handlers")
    
    # 记录错误
    try:
        result = 10 / 0
    except ZeroDivisionError:
        logger.exception("数学错误")
    
    try:
        data = {'name': 'Alice'}
        age = data['age']  # KeyError
    except KeyError:
        logger.exception("字典键错误")
    
    # 获取错误日志
    error_logs = logger_system.get_error_logs(days=1)
    print(f"\n错误日志数量: {len(error_logs)}")
    
    for log in error_logs:
        print(f"  - {log.get('level')}: {log.get('message')}")
        if 'exception' in log:
            print(f"    异常类型: {log['exception'].get('type')}")


def example_multi_logger():
    """多日志器示例"""
    print("\n=== 多日志器示例 ===\n")
    
    logger_system = LoggerWithStorage(
        app_name="myapp_multi",
        log_dir="logs/multi"
    )
    
    # 不同模块的日志器
    logger_db = logger_system.get_logger("app.database")
    logger_api = logger_system.get_logger("app.api")
    logger_auth = logger_system.get_logger("app.auth")
    
    # 模拟不同模块的日志
    logger_db.info("连接到数据库")
    logger_db.debug("执行查询: SELECT * FROM users")
    
    logger_api.info("API请求: GET /users")
    logger_api.debug("参数: page=1, limit=10")
    
    logger_auth.info("用户认证")
    logger_auth.debug("验证令牌有效性")
    
    # 按日志器统计
    stats = logger_system.get_logs(days=1)
    print("\n按日志器统计:")
    for logger_name, count in stats['by_logger'].items():
        print(f"  {logger_name}: {count} 条日志")


def example_performance_monitoring():
    """性能监控示例"""
    print("\n=== 性能监控示例 ===\n")
    
    import time
    
    logger_system = LoggerWithStorage(
        app_name="myapp_perf",
        log_dir="logs/perf"
    )
    
    logger = logger_system.get_logger("app.performance")
    
    # 模拟不同操作
    operations = [
        ("用户认证", 0.1),
        ("数据库查询", 0.3),
        ("API调用", 0.2),
        ("数据处理", 0.15),
    ]
    
    for op_name, duration in operations:
        start = time.time()
        time.sleep(duration)
        elapsed = time.time() - start
        
        logger.info(
            f"操作完成: {op_name}",
            extra={'duration': elapsed, 'operation': op_name}
        )
    
    # 统计
    stats = logger_system.get_logs(days=1)
    print(f"操作日志统计: {stats}")


def example_context_logging():
    """上下文日志示例"""
    print("\n=== 上下文日志示例 ===\n")
    
    logger_system = LoggerWithStorage(
        app_name="myapp_context",
        log_dir="logs/context"
    )
    
    logger = logger_system.get_logger("app.business")
    
    # 处理订单
    with MetadataContext(request_id="order_123", user_id="user_456"):
        logger.info("开始处理订单")
        
        with MetadataContext(order_id="order_123", product_id="prod_789"):
            logger.info("验证订单")
            logger.info("检查库存")
            logger.info("处理支付")
        
        logger.info("订单处理完成")
    
    # 处理另一个订单
    with MetadataContext(request_id="order_234", user_id="user_567"):
        logger.info("开始处理订单")
        logger.info("订单处理完成")
    
    print("日志已存储到 JSON 文件")


def example_direct_storage_usage():
    """直接使用 LogStore 访问日志"""
    print("\n=== 直接访问存储示例 ===\n")
    
    logger_system = LoggerWithStorage(
        app_name="myapp_direct",
        log_dir="logs/direct"
    )
    
    logger = logger_system.get_logger("app.demo")
    
    # 记录一些日志
    for i in range(5):
        logger.info(f"日志条目 {i}")
    
    # 直接访问存储
    if logger_system.log_store:
        logs = logger_system.log_store.get_logs()
        
        print(f"\n共有 {len(logs)} 条日志")
        print("最后 3 条日志:")
        for log in logs[-3:]:
            print(f"  - [{log.get('level')}] {log.get('message')}")
            print(f"    记录器: {log.get('logger')}")
            print(f"    文件: {log.get('module')}.{log.get('function')} (第 {log.get('line')} 行)")
            if 'timestamp' in log:
                print(f"    时间: {log.get('timestamp')}")


# ============================================================================
# 对比：有存储 vs 无存储
# ============================================================================

def example_comparison():
    """对比有存储和无存储"""
    print("\n=== 对比：有存储 vs 无存储 ===\n")
    
    # 无存储
    print("1. 无存储的日志系统:")
    logger_system_no_storage = LoggerWithStorage(
        app_name="no_storage",
        json_storage=False
    )
    logger = logger_system_no_storage.get_logger("app")
    logger.info("这条日志只输出到控制台")
    logger.info("无法持久化存储")
    
    stats = logger_system_no_storage.get_logs(days=1)
    print(f"统计信息: {stats}")
    
    # 有存储
    print("\n2. 有存储的日志系统:")
    logger_system_with_storage = LoggerWithStorage(
        app_name="with_storage",
        json_storage=True
    )
    logger = logger_system_with_storage.get_logger("app")
    logger.info("这条日志会被存储到 JSON 文件")
    logger.info("可以后续查询和分析")
    
    stats = logger_system_with_storage.get_logs(days=1)
    print(f"统计信息: {stats}")
    
    print("\n✅ 有存储的系统优势:")
    print("  - 日志持久化，可后续查询")
    print("  - 支持日志统计和分析")
    print("  - 支持时间范围查询")
    print("  - 支持过滤和搜索")
    print("  - 自动轮转和清理旧日志")


if __name__ == "__main__":
    print("=" * 80)
    print("Logger 与 Storage 模块集成示例")
    print("=" * 80)
    
    # 运行示例
    example_basic_usage()
    example_with_metadata()
    example_error_tracking()
    example_multi_logger()
    example_performance_monitoring()
    example_context_logging()
    example_direct_storage_usage()
    example_comparison()
    
    print("\n" + "=" * 80)
    print("所有示例执行完成!")
    print("=" * 80)
