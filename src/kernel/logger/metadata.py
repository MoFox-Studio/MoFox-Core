"""
日志元数据管理模块

提供日志记录的上下文信息和元数据管理功能
"""
from contextvars import ContextVar
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


# 全局上下文变量，用于存储请求级别的元数据
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
_session_id: ContextVar[Optional[str]] = ContextVar('session_id', default=None)
_user_id: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_custom_metadata: ContextVar[Dict[str, Any]] = ContextVar('custom_metadata', default={})


class LogMetadata:
    """日志元数据管理类"""
    
    @staticmethod
    def set_request_id(request_id: Optional[str] = None) -> str:
        """
        设置请求ID
        
        Args:
            request_id: 请求ID，如果为None则自动生成
            
        Returns:
            str: 设置的请求ID
        """
        if request_id is None:
            request_id = str(uuid.uuid4())
        _request_id.set(request_id)
        return request_id
    
    @staticmethod
    def get_request_id() -> Optional[str]:
        """获取当前请求ID"""
        return _request_id.get()
    
    @staticmethod
    def set_session_id(session_id: str) -> None:
        """设置会话ID"""
        _session_id.set(session_id)
    
    @staticmethod
    def get_session_id() -> Optional[str]:
        """获取当前会话ID"""
        return _session_id.get()
    
    @staticmethod
    def set_user_id(user_id: str) -> None:
        """设置用户ID"""
        _user_id.set(user_id)
    
    @staticmethod
    def get_user_id() -> Optional[str]:
        """获取当前用户ID"""
        return _user_id.get()
    
    @staticmethod
    def set_custom(key: str, value: Any) -> None:
        """
        设置自定义元数据
        
        Args:
            key: 元数据键
            value: 元数据值
        """
        metadata = _custom_metadata.get().copy()
        metadata[key] = value
        _custom_metadata.set(metadata)
    
    @staticmethod
    def get_custom(key: str, default: Any = None) -> Any:
        """
        获取自定义元数据
        
        Args:
            key: 元数据键
            default: 默认值
            
        Returns:
            元数据值
        """
        return _custom_metadata.get().get(key, default)
    
    @staticmethod
    def get_all_custom() -> Dict[str, Any]:
        """获取所有自定义元数据"""
        return _custom_metadata.get().copy()
    
    @staticmethod
    def clear() -> None:
        """清除所有元数据"""
        _request_id.set(None)
        _session_id.set(None)
        _user_id.set(None)
        _custom_metadata.set({})
    
    @staticmethod
    def get_all() -> Dict[str, Any]:
        """
        获取所有元数据
        
        Returns:
            包含所有元数据的字典
        """
        metadata = {
            'timestamp': datetime.now().isoformat(),
        }
        
        request_id = LogMetadata.get_request_id()
        if request_id:
            metadata['request_id'] = request_id
        
        session_id = LogMetadata.get_session_id()
        if session_id:
            metadata['session_id'] = session_id
        
        user_id = LogMetadata.get_user_id()
        if user_id:
            metadata['user_id'] = user_id
        
        custom = LogMetadata.get_all_custom()
        if custom:
            metadata['custom'] = custom
        
        return metadata


class MetadataContext:
    """元数据上下文管理器，用于临时设置元数据"""
    
    def __init__(self, **kwargs):
        """
        初始化元数据上下文
        
        Args:
            **kwargs: 要设置的元数据键值对
                支持 request_id, session_id, user_id 以及任意自定义字段
        """
        self.kwargs = kwargs
        self.tokens = {}
    
    def __enter__(self):
        """进入上下文时设置元数据"""
        if 'request_id' in self.kwargs:
            self.tokens['request_id'] = _request_id.set(self.kwargs['request_id'])
        
        if 'session_id' in self.kwargs:
            self.tokens['session_id'] = _session_id.set(self.kwargs['session_id'])
        
        if 'user_id' in self.kwargs:
            self.tokens['user_id'] = _user_id.set(self.kwargs['user_id'])
        
        # 处理自定义元数据
        custom_keys = set(self.kwargs.keys()) - {'request_id', 'session_id', 'user_id'}
        if custom_keys:
            old_custom = _custom_metadata.get().copy()
            new_custom = old_custom.copy()
            for key in custom_keys:
                new_custom[key] = self.kwargs[key]
            self.tokens['custom'] = _custom_metadata.set(new_custom)
            self.old_custom = old_custom
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时恢复元数据"""
        if 'request_id' in self.tokens:
            _request_id.reset(self.tokens['request_id'])
        
        if 'session_id' in self.tokens:
            _session_id.reset(self.tokens['session_id'])
        
        if 'user_id' in self.tokens:
            _user_id.reset(self.tokens['user_id'])
        
        if 'custom' in self.tokens:
            _custom_metadata.reset(self.tokens['custom'])
