"""
标准响应解析

提供统一的 LLM 响应解析和格式化功能
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import json


class FinishReason(Enum):
    """完成原因枚举"""
    STOP = "stop"  # 正常结束
    LENGTH = "length"  # 达到最大长度
    CONTENT_FILTER = "content_filter"  # 内容过滤
    TOOL_CALLS = "tool_calls"  # 调用工具
    FUNCTION_CALL = "function_call"  # 调用函数
    NULL = "null"  # 未完成（流式响应）


@dataclass
class Usage:
    """使用情况统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Usage':
        """从字典创建"""
        return cls(
            prompt_tokens=data.get('prompt_tokens', 0),
            completion_tokens=data.get('completion_tokens', 0),
            total_tokens=data.get('total_tokens', 0)
        )
    
    def to_dict(self) -> Dict[str, int]:
        """转换为字典"""
        return {
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.total_tokens
        }


@dataclass
class FunctionCall:
    """函数调用信息"""
    name: str
    arguments: str  # JSON 字符串
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FunctionCall':
        """从字典创建"""
        return cls(
            name=data.get('name', ''),
            arguments=data.get('arguments', '{}')
        )
    
    def get_arguments(self) -> Dict[str, Any]:
        """解析参数"""
        try:
            return json.loads(self.arguments)
        except json.JSONDecodeError:
            return {}
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return {
            'name': self.name,
            'arguments': self.arguments
        }


@dataclass
class ToolCall:
    """工具调用信息"""
    id: str
    type: str = "function"
    function: Optional[FunctionCall] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolCall':
        """从字典创建"""
        function_data = data.get('function')
        function = FunctionCall.from_dict(function_data) if function_data else None
        
        return cls(
            id=data.get('id', ''),
            type=data.get('type', 'function'),
            function=function
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            'id': self.id,
            'type': self.type
        }
        if self.function:
            result['function'] = self.function.to_dict()
        return result


@dataclass
class Message:
    """消息对象"""
    role: str
    content: Optional[str] = None
    function_call: Optional[FunctionCall] = None
    tool_calls: Optional[List[ToolCall]] = None
    name: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """从字典创建"""
        # 解析 function_call
        function_call = None
        if 'function_call' in data:
            function_call = FunctionCall.from_dict(data['function_call'])
        
        # 解析 tool_calls
        tool_calls = None
        if 'tool_calls' in data:
            tool_calls = [
                ToolCall.from_dict(tc) for tc in data['tool_calls']
            ]
        
        return cls(
            role=data.get('role', ''),
            content=data.get('content'),
            function_call=function_call,
            tool_calls=tool_calls,
            name=data.get('name')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {'role': self.role}
        
        if self.content is not None:
            result['content'] = self.content
        
        if self.function_call:
            result['function_call'] = self.function_call.to_dict()
        
        if self.tool_calls:
            result['tool_calls'] = [tc.to_dict() for tc in self.tool_calls]
        
        if self.name:
            result['name'] = self.name
        
        return result


@dataclass
class Choice:
    """响应选项"""
    index: int
    message: Message
    finish_reason: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Choice':
        """从字典创建"""
        message_data = data.get('message', {})
        message = Message.from_dict(message_data)
        
        return cls(
            index=data.get('index', 0),
            message=message,
            finish_reason=data.get('finish_reason')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            'index': self.index,
            'message': self.message.to_dict()
        }
        
        if self.finish_reason:
            result['finish_reason'] = self.finish_reason
        
        return result


@dataclass
class CompletionResponse:
    """完整响应对象"""
    id: str
    object: str
    created: int
    model: str
    choices: List[Choice]
    usage: Optional[Usage] = None
    system_fingerprint: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompletionResponse':
        """从字典创建"""
        choices = [Choice.from_dict(c) for c in data.get('choices', [])]
        
        usage = None
        if 'usage' in data:
            usage = Usage.from_dict(data['usage'])
        
        return cls(
            id=data.get('id', ''),
            object=data.get('object', ''),
            created=data.get('created', 0),
            model=data.get('model', ''),
            choices=choices,
            usage=usage,
            system_fingerprint=data.get('system_fingerprint')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            'id': self.id,
            'object': self.object,
            'created': self.created,
            'model': self.model,
            'choices': [c.to_dict() for c in self.choices]
        }
        
        if self.usage:
            result['usage'] = self.usage.to_dict()
        
        if self.system_fingerprint:
            result['system_fingerprint'] = self.system_fingerprint
        
        return result
    
    def get_first_message(self) -> Optional[Message]:
        """获取第一个选项的消息"""
        if self.choices:
            return self.choices[0].message
        return None
    
    def get_content(self) -> Optional[str]:
        """获取第一个选项的内容"""
        message = self.get_first_message()
        return message.content if message else None
    
    def has_tool_calls(self) -> bool:
        """是否包含工具调用"""
        message = self.get_first_message()
        return bool(message and message.tool_calls)
    
    def get_tool_calls(self) -> List[ToolCall]:
        """获取工具调用列表"""
        message = self.get_first_message()
        return message.tool_calls if message and message.tool_calls else []


class ResponseParser:
    """响应解析器
    
    提供统一的响应解析方法
    """
    
    @staticmethod
    def parse_completion(response: Dict[str, Any]) -> CompletionResponse:
        """解析完整响应
        
        Args:
            response: API 响应字典
            
        Returns:
            CompletionResponse: 解析后的响应对象
        """
        return CompletionResponse.from_dict(response)
    
    @staticmethod
    def extract_content(response: Dict[str, Any]) -> Optional[str]:
        """提取响应内容
        
        Args:
            response: API 响应字典
            
        Returns:
            Optional[str]: 内容字符串
        """
        parsed = ResponseParser.parse_completion(response)
        return parsed.get_content()
    
    @staticmethod
    def extract_tool_calls(response: Dict[str, Any]) -> List[ToolCall]:
        """提取工具调用
        
        Args:
            response: API 响应字典
            
        Returns:
            List[ToolCall]: 工具调用列表
        """
        parsed = ResponseParser.parse_completion(response)
        return parsed.get_tool_calls()
    
    @staticmethod
    def extract_usage(response: Dict[str, Any]) -> Optional[Usage]:
        """提取使用情况
        
        Args:
            response: API 响应字典
            
        Returns:
            Optional[Usage]: 使用情况对象
        """
        parsed = ResponseParser.parse_completion(response)
        return parsed.usage
    
    @staticmethod
    def is_complete(response: Dict[str, Any]) -> bool:
        """判断响应是否完成
        
        Args:
            response: API 响应字典
            
        Returns:
            bool: 是否完成
        """
        parsed = ResponseParser.parse_completion(response)
        if parsed.choices:
            finish_reason = parsed.choices[0].finish_reason
            return finish_reason == FinishReason.STOP.value
        return False
