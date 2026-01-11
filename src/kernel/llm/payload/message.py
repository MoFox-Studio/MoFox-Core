"""
标准消息构建

提供统一的消息格式构建功能
"""

from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum


class MessageRole(Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


@dataclass
class TextContent:
    """文本内容"""
    type: str = "text"
    text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "text": self.text}


@dataclass
class ImageContent:
    """图片内容"""
    type: str = "image_url"
    image_url: Union[str, Dict[str, str]] = ""
    
    def to_dict(self) -> Dict[str, Any]:
        if isinstance(self.image_url, str):
            return {
                "type": self.type,
                "image_url": {"url": self.image_url}
            }
        return {
            "type": self.type,
            "image_url": self.image_url
        }


class MessageBuilder:
    """消息构建器
    
    提供便捷的方法构建标准格式的消息
    """
    
    @staticmethod
    def create_system_message(content: str) -> Dict[str, str]:
        """创建系统消息
        
        Args:
            content: 消息内容
            
        Returns:
            Dict: 标准格式的系统消息
        """
        return {
            "role": MessageRole.SYSTEM.value,
            "content": content
        }
    
    @staticmethod
    def create_user_message(
        content: Union[str, List[Union[TextContent, ImageContent, Dict]]],
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建用户消息
        
        Args:
            content: 消息内容（文本或多模态内容列表）
            name: 用户名称（可选）
            
        Returns:
            Dict: 标准格式的用户消息
        """
        message: Dict[str, Any] = {
            "role": MessageRole.USER.value
        }
        
        # 处理内容
        if isinstance(content, str):
            message["content"] = content
        else:
            # 多模态内容
            formatted_content = []
            for item in content:
                if isinstance(item, (TextContent, ImageContent)):
                    formatted_content.append(item.to_dict())
                elif isinstance(item, dict):
                    formatted_content.append(item)
                else:
                    raise ValueError(f"Unsupported content type: {type(item)}")
            message["content"] = formatted_content
        
        if name:
            message["name"] = name
        
        return message
    
    @staticmethod
    def create_assistant_message(
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        function_call: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建助手消息
        
        Args:
            content: 消息内容
            tool_calls: 工具调用列表
            function_call: 函数调用（已弃用，用tool_calls）
            name: 助手名称（可选）
            
        Returns:
            Dict: 标准格式的助手消息
        """
        message: Dict[str, Any] = {
            "role": MessageRole.ASSISTANT.value
        }
        
        if content is not None:
            message["content"] = content
        
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        if function_call:
            message["function_call"] = function_call
        
        if name:
            message["name"] = name
        
        return message
    
    @staticmethod
    def create_tool_message(
        tool_call_id: str,
        content: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建工具响应消息
        
        Args:
            tool_call_id: 工具调用ID
            content: 工具返回的内容
            name: 工具名称（可选）
            
        Returns:
            Dict: 标准格式的工具消息
        """
        message: Dict[str, Any] = {
            "role": MessageRole.TOOL.value,
            "tool_call_id": tool_call_id,
            "content": content
        }
        
        if name:
            message["name"] = name
        
        return message
    
    @staticmethod
    def create_function_message(
        name: str,
        content: str
    ) -> Dict[str, Any]:
        """创建函数响应消息（已弃用，使用create_tool_message）
        
        Args:
            name: 函数名称
            content: 函数返回的内容
            
        Returns:
            Dict: 标准格式的函数消息
        """
        return {
            "role": MessageRole.FUNCTION.value,
            "name": name,
            "content": content
        }
    
    @staticmethod
    def create_multimodal_message(
        text: Optional[str] = None,
        images: Optional[List[str]] = None,
        role: MessageRole = MessageRole.USER
    ) -> Dict[str, Any]:
        """创建多模态消息（包含文本和图片）
        
        Args:
            text: 文本内容
            images: 图片URL列表
            role: 消息角色
            
        Returns:
            Dict: 标准格式的多模态消息
        """
        content = []
        
        if text:
            content.append(TextContent(text=text).to_dict())
        
        if images:
            for image_url in images:
                content.append(ImageContent(image_url=image_url).to_dict())
        
        return {
            "role": role.value,
            "content": content
        }
    
    @staticmethod
    def format_conversation(
        system: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        user_message: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """格式化完整对话
        
        Args:
            system: 系统提示词
            messages: 历史消息列表
            user_message: 当前用户消息
            
        Returns:
            List[Dict]: 格式化的消息列表
        """
        formatted = []
        
        if system:
            formatted.append(MessageBuilder.create_system_message(system))
        
        if messages:
            formatted.extend(messages)
        
        if user_message:
            formatted.append(MessageBuilder.create_user_message(user_message))
        
        return formatted
    
    @staticmethod
    def validate_message(message: Dict[str, Any]) -> bool:
        """验证消息格式
        
        Args:
            message: 消息字典
            
        Returns:
            bool: 是否有效
        """
        # 必须有 role 字段
        if "role" not in message:
            return False
        
        # 验证 role 值
        valid_roles = [r.value for r in MessageRole]
        if message["role"] not in valid_roles:
            return False
        
        # 大多数消息需要 content 字段（除了带 tool_calls 的 assistant 消息）
        if message["role"] != MessageRole.ASSISTANT.value:
            if "content" not in message:
                return False
        
        return True
    
    @staticmethod
    def count_tokens_estimate(messages: List[Dict[str, Any]]) -> int:
        """粗略估算消息列表的token数
        
        Args:
            messages: 消息列表
            
        Returns:
            int: 估算的token数
        """
        from ..utils import estimate_tokens
        
        total = 0
        for message in messages:
            # 角色标记 ~4 tokens
            total += 4
            
            # 内容
            if isinstance(message.get("content"), str):
                total += estimate_tokens(message["content"])
            elif isinstance(message.get("content"), list):
                for item in message["content"]:
                    if item.get("type") == "text":
                        total += estimate_tokens(item.get("text", ""))
                    elif item.get("type") == "image_url":
                        # 图片约 85-170 tokens，取中间值
                        total += 128
            
            # 工具调用
            if "tool_calls" in message:
                # 每个工具调用约 ~10 tokens
                total += len(message["tool_calls"]) * 10
        
        return total
