"""
日志处理器模块

提供不同类型的日志处理器（控制台、文件等）
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from .renderers import CustomFormatter, ColoredRenderer, PlainRenderer, JSONRenderer


class ConsoleHandler(logging.StreamHandler):
    """控制台日志处理器"""
    
    def __init__(
        self,
        level: int = logging.INFO,
        use_colors: bool = True,
        include_metadata: bool = True,
        stream=None
    ):
        """
        初始化控制台处理器
        
        Args:
            level: 日志级别
            use_colors: 是否使用彩色输出
            include_metadata: 是否包含元数据
            stream: 输出流，默认为sys.stderr
        """
        super().__init__(stream or sys.stderr)
        self.setLevel(level)
        
        # 设置彩色格式化器
        renderer = ColoredRenderer(
            include_metadata=include_metadata,
            use_colors=use_colors
        )
        self.setFormatter(CustomFormatter(renderer))


class FileHandler(RotatingFileHandler):
    """文件日志处理器（支持大小轮转）"""
    
    def __init__(
        self,
        filename: str,
        level: int = logging.DEBUG,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        encoding: str = 'utf-8',
        use_json: bool = False,
        include_metadata: bool = True
    ):
        """
        初始化文件处理器
        
        Args:
            filename: 日志文件路径
            level: 日志级别
            max_bytes: 单个日志文件最大大小（字节）
            backup_count: 保留的备份文件数量
            encoding: 文件编码
            use_json: 是否使用JSON格式
            include_metadata: 是否包含元数据
        """
        # 确保日志目录存在
        log_path = Path(filename)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        super().__init__(
            filename=filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding
        )
        self.setLevel(level)
        
        # 设置格式化器
        if use_json:
            renderer = JSONRenderer(include_metadata=include_metadata)
        else:
            renderer = PlainRenderer(include_metadata=include_metadata)
        
        self.setFormatter(CustomFormatter(renderer))


class TimedFileHandler(TimedRotatingFileHandler):
    """时间轮转文件日志处理器"""
    
    def __init__(
        self,
        filename: str,
        level: int = logging.DEBUG,
        when: str = 'midnight',
        interval: int = 1,
        backup_count: int = 30,
        encoding: str = 'utf-8',
        use_json: bool = False,
        include_metadata: bool = True
    ):
        """
        初始化时间轮转文件处理器
        
        Args:
            filename: 日志文件路径
            level: 日志级别
            when: 轮转时间单位 ('S', 'M', 'H', 'D', 'midnight', 'W0'-'W6')
            interval: 轮转间隔
            backup_count: 保留的备份文件数量
            encoding: 文件编码
            use_json: 是否使用JSON格式
            include_metadata: 是否包含元数据
        """
        # 确保日志目录存在
        log_path = Path(filename)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding=encoding
        )
        self.setLevel(level)
        
        # 设置格式化器
        if use_json:
            renderer = JSONRenderer(include_metadata=include_metadata)
        else:
            renderer = PlainRenderer(include_metadata=include_metadata)
        
        self.setFormatter(CustomFormatter(renderer))


class ErrorFileHandler(FileHandler):
    """专门记录错误日志的文件处理器"""
    
    def __init__(
        self,
        filename: str,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        encoding: str = 'utf-8',
        use_json: bool = False,
        include_metadata: bool = True
    ):
        """
        初始化错误文件处理器
        
        Args:
            filename: 错误日志文件路径
            max_bytes: 单个日志文件最大大小（字节）
            backup_count: 保留的备份文件数量
            encoding: 文件编码
            use_json: 是否使用JSON格式
            include_metadata: 是否包含元数据
        """
        super().__init__(
            filename=filename,
            level=logging.ERROR,  # 只记录ERROR及以上级别
            max_bytes=max_bytes,
            backup_count=backup_count,
            encoding=encoding,
            use_json=use_json,
            include_metadata=include_metadata
        )


class AsyncHandler(logging.Handler):
    """异步日志处理器（避免阻塞主线程）"""
    
    def __init__(self, handler: logging.Handler, queue_size: int = 1000):
        """
        初始化异步处理器
        
        Args:
            handler: 实际的日志处理器
            queue_size: 队列大小
        """
        super().__init__()
        self.handler = handler
        self.queue_size = queue_size
        
        # 导入队列处理器
        from logging.handlers import QueueHandler, QueueListener
        from queue import Queue
        
        self.queue = Queue(maxsize=queue_size)
        self.queue_handler = QueueHandler(self.queue)
        self.listener = QueueListener(self.queue, handler, respect_handler_level=True)
        self.listener.start()
    
    def emit(self, record: logging.LogRecord):
        """发送日志记录到队列"""
        try:
            self.queue_handler.emit(record)
        except Exception:
            self.handleError(record)
    
    def close(self):
        """关闭处理器"""
        self.listener.stop()
        self.handler.close()
        super().close()


class LogStoreHandler(logging.Handler):
    """日志存储处理器 - 将日志直接写入到 Storage 的 LogStore"""
    
    def __init__(
        self,
        log_store,  # kernel.storage.LogStore 实例
        level: int = logging.DEBUG,
        include_metadata: bool = True,
        include_exc_info: bool = True
    ):
        """
        初始化日志存储处理器
        
        Args:
            log_store: LogStore 实例（来自 kernel.storage 模块）
            level: 日志级别
            include_metadata: 是否包含上下文元数据（request_id, user_id等）
            include_exc_info: 是否包含异常信息
        """
        super().__init__()
        self.log_store = log_store
        self.setLevel(level)
        self.include_metadata = include_metadata
        self.include_exc_info = include_exc_info
    
    def emit(self, record: logging.LogRecord):
        """
        发送日志记录到 LogStore
        
        Args:
            record: 日志记录对象
        """
        try:
            # 构建日志条目
            log_entry = {
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            
            # 添加元数据
            if self.include_metadata:
                try:
                    from .metadata import LogMetadata
                    log_entry['request_id'] = LogMetadata.get_request_id()
                    log_entry['session_id'] = LogMetadata.get_session_id()
                    log_entry['user_id'] = LogMetadata.get_user_id()
                    custom = LogMetadata.get_custom()
                    if custom:
                        log_entry['metadata'] = custom
                except (ImportError, AttributeError):
                    pass
            
            # 添加异常信息
            if self.include_exc_info and record.exc_info:
                import traceback
                exc_text = ''.join(traceback.format_exception(*record.exc_info))
                log_entry['exception'] = {
                    'type': record.exc_info[0].__name__,
                    'message': str(record.exc_info[1]),
                    'traceback': exc_text
                }
            
            # 写入到 LogStore
            self.log_store.add_log(log_entry)
        except Exception:
            self.handleError(record)


class NullHandler(logging.NullHandler):
    """空日志处理器（什么都不做）"""
    
    def __init__(self):
        """初始化空处理器"""
        super().__init__()
