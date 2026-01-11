"""
日志格式化器模块

提供不同格式的日志输出渲染器
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from .metadata import LogMetadata


class BaseRenderer:
    """日志渲染器基类"""
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录
        
        Args:
            record: 日志记录对象
            
        Returns:
            格式化后的字符串
        """
        raise NotImplementedError


class PlainRenderer(BaseRenderer):
    """纯文本渲染器"""
    
    def __init__(self, include_metadata: bool = True):
        """
        初始化纯文本渲染器
        
        Args:
            include_metadata: 是否包含元数据信息
        """
        self.include_metadata = include_metadata
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化为纯文本"""
        # 基本信息
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        level = record.levelname
        logger_name = record.name
        message = record.getMessage()
        
        # 构建基本日志行
        parts = [f"[{timestamp}]", f"[{level}]", f"[{logger_name}]", message]
        
        # 添加元数据
        if self.include_metadata:
            metadata = LogMetadata.get_all()
            if metadata:
                metadata_parts = []
                if 'request_id' in metadata:
                    metadata_parts.append(f"req={metadata['request_id'][:8]}")
                if 'session_id' in metadata:
                    metadata_parts.append(f"sess={metadata['session_id'][:8]}")
                if 'user_id' in metadata:
                    metadata_parts.append(f"user={metadata['user_id']}")
                
                if metadata_parts:
                    parts.insert(-1, f"[{', '.join(metadata_parts)}]")
        
        # 添加异常信息
        if record.exc_info:
            exc_text = logging.Formatter().formatException(record.exc_info)
            parts.append(f"\n{exc_text}")
        
        return " ".join(parts)


class JSONRenderer(BaseRenderer):
    """JSON格式渲染器"""
    
    def __init__(self, include_metadata: bool = True, indent: Optional[int] = None):
        """
        初始化JSON渲染器
        
        Args:
            include_metadata: 是否包含元数据信息
            indent: JSON缩进级别，None表示紧凑格式
        """
        self.include_metadata = include_metadata
        self.indent = indent
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化为JSON"""
        log_data: Dict[str, Any] = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # 添加元数据
        if self.include_metadata:
            metadata = LogMetadata.get_all()
            if 'request_id' in metadata:
                log_data['request_id'] = metadata['request_id']
            if 'session_id' in metadata:
                log_data['session_id'] = metadata['session_id']
            if 'user_id' in metadata:
                log_data['user_id'] = metadata['user_id']
            if 'custom' in metadata:
                log_data['custom'] = metadata['custom']
        
        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = logging.Formatter().formatException(record.exc_info)
        
        # 添加自定义字段
        if hasattr(record, 'extra'):
            log_data['extra'] = record.extra
        
        return json.dumps(log_data, ensure_ascii=False, indent=self.indent)


class ColoredRenderer(BaseRenderer):
    """彩色控制台渲染器"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m',       # 重置
        'BOLD': '\033[1m',        # 粗体
        'DIM': '\033[2m',         # 暗淡
    }
    
    def __init__(self, include_metadata: bool = True, use_colors: bool = True):
        """
        初始化彩色渲染器
        
        Args:
            include_metadata: 是否包含元数据信息
            use_colors: 是否使用颜色
        """
        self.include_metadata = include_metadata
        self.use_colors = use_colors
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化为彩色文本"""
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        level = record.levelname
        logger_name = record.name
        message = record.getMessage()
        
        if self.use_colors:
            # 应用颜色
            color = self.COLORS.get(level, self.COLORS['RESET'])
            reset = self.COLORS['RESET']
            dim = self.COLORS['DIM']
            bold = self.COLORS['BOLD']
            
            # 构建彩色日志行
            parts = [
                f"{dim}[{timestamp}]{reset}",
                f"{color}{bold}[{level}]{reset}",
                f"{dim}[{logger_name}]{reset}",
            ]
            
            # 添加元数据
            if self.include_metadata:
                metadata = LogMetadata.get_all()
                if metadata:
                    metadata_parts = []
                    if 'request_id' in metadata:
                        metadata_parts.append(f"req={metadata['request_id'][:8]}")
                    if 'session_id' in metadata:
                        metadata_parts.append(f"sess={metadata['session_id'][:8]}")
                    if 'user_id' in metadata:
                        metadata_parts.append(f"user={metadata['user_id']}")
                    
                    if metadata_parts:
                        parts.append(f"{dim}[{', '.join(metadata_parts)}]{reset}")
            
            parts.append(message)
            
            # 添加异常信息
            if record.exc_info:
                exc_text = logging.Formatter().formatException(record.exc_info)
                parts.append(f"\n{color}{exc_text}{reset}")
            
            return " ".join(parts)
        else:
            # 无颜色模式
            plain_renderer = PlainRenderer(include_metadata=self.include_metadata)
            return plain_renderer.format(record)


class StructuredRenderer(BaseRenderer):
    """结构化渲染器（键值对格式）"""
    
    def __init__(self, include_metadata: bool = True):
        """
        初始化结构化渲染器
        
        Args:
            include_metadata: 是否包含元数据信息
        """
        self.include_metadata = include_metadata
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化为结构化键值对"""
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        
        fields = [
            f"time={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"module={record.module}",
            f"function={record.funcName}",
            f"line={record.lineno}",
            f'msg="{record.getMessage()}"',
        ]
        
        # 添加元数据
        if self.include_metadata:
            metadata = LogMetadata.get_all()
            if 'request_id' in metadata:
                fields.append(f'request_id={metadata["request_id"]}')
            if 'session_id' in metadata:
                fields.append(f'session_id={metadata["session_id"]}')
            if 'user_id' in metadata:
                fields.append(f'user_id={metadata["user_id"]}')
        
        # 添加异常信息
        if record.exc_info:
            exc_text = logging.Formatter().formatException(record.exc_info)
            fields.append(f'exception="{exc_text}"')
        
        return " ".join(fields)


class CustomFormatter(logging.Formatter):
    """自定义格式化器，支持不同的渲染器"""
    
    def __init__(self, renderer: Optional[BaseRenderer] = None):
        """
        初始化自定义格式化器
        
        Args:
            renderer: 使用的渲染器，默认为PlainRenderer
        """
        super().__init__()
        self.renderer = renderer or PlainRenderer()
    
    def format(self, record: logging.LogRecord) -> str:
        """使用渲染器格式化日志记录"""
        return self.renderer.format(record)
