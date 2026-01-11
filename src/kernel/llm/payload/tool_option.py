"""
标准工具负载构建

提供函数调用和工具调用的标准格式构建
"""

from typing import List, Dict, Any, Optional, Union, Literal
from dataclasses import dataclass, field
from enum import Enum
import json


class ToolType(Enum):
    """工具类型枚举"""
    FUNCTION = "function"


class ParameterType(Enum):
    """参数类型枚举"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


@dataclass
class Parameter:
    """函数参数定义"""
    name: str
    type: ParameterType
    description: str
    required: bool = False
    enum: Optional[List[Any]] = None
    items: Optional[Dict[str, Any]] = None  # 用于 array 类型
    properties: Optional[Dict[str, Any]] = None  # 用于 object 类型
    default: Optional[Any] = None
    
    def to_schema(self) -> Dict[str, Any]:
        """转换为 JSON Schema 格式"""
        schema = {
            "type": self.type.value,
            "description": self.description
        }
        
        if self.enum:
            schema["enum"] = self.enum
        
        if self.items:
            schema["items"] = self.items
        
        if self.properties:
            schema["properties"] = self.properties
        
        if self.default is not None:
            schema["default"] = self.default
        
        return schema


@dataclass
class FunctionDefinition:
    """函数定义"""
    name: str
    description: str
    parameters: List[Parameter] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        # 构建 parameters schema
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)
        
        parameters_schema = {
            "type": "object",
            "properties": properties
        }
        
        if required:
            parameters_schema["required"] = required
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters_schema
        }


@dataclass
class ToolDefinition:
    """工具定义（OpenAI 风格）"""
    type: str = "function"  # 目前只支持 "function"
    function: Optional[FunctionDefinition] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {"type": self.type}
        if self.function:
            result["function"] = self.function.to_dict()
        return result


class ToolBuilder:
    """工具构建器
    
    提供便捷的方法构建工具定义
    """
    
    @staticmethod
    def create_function(
        name: str,
        description: str,
        parameters: Optional[List[Parameter]] = None
    ) -> Dict[str, Any]:
        """创建函数定义
        
        Args:
            name: 函数名称
            description: 函数描述
            parameters: 参数列表
            
        Returns:
            Dict: 标准格式的函数定义
        """
        func_def = FunctionDefinition(
            name=name,
            description=description,
            parameters=parameters or []
        )
        return func_def.to_dict()
    
    @staticmethod
    def create_tool(
        name: str,
        description: str,
        parameters: Optional[List[Parameter]] = None
    ) -> Dict[str, Any]:
        """创建工具定义（OpenAI 风格）
        
        Args:
            name: 工具名称
            description: 工具描述
            parameters: 参数列表
            
        Returns:
            Dict: 标准格式的工具定义
        """
        func_def = FunctionDefinition(
            name=name,
            description=description,
            parameters=parameters or []
        )
        tool_def = ToolDefinition(function=func_def)
        return tool_def.to_dict()
    
    @staticmethod
    def create_parameter(
        name: str,
        param_type: Union[ParameterType, str],
        description: str,
        required: bool = False,
        **kwargs
    ) -> Parameter:
        """创建参数
        
        Args:
            name: 参数名称
            param_type: 参数类型
            description: 参数描述
            required: 是否必需
            **kwargs: 其他参数（enum, items, properties, default）
            
        Returns:
            Parameter: 参数对象
        """
        if isinstance(param_type, str):
            param_type = ParameterType(param_type)
        
        return Parameter(
            name=name,
            type=param_type,
            description=description,
            required=required,
            **kwargs
        )
    
    @staticmethod
    def create_tool_choice(
        choice: Union[Literal["auto", "none"], str, Dict[str, Any]]
    ) -> Union[str, Dict[str, Any]]:
        """创建工具选择策略
        
        Args:
            choice: 选择策略
                - "auto": 模型自动决定
                - "none": 不使用工具
                - "required": 必须使用工具
                - 工具名称: 强制使用指定工具
                - Dict: {"type": "function", "function": {"name": "tool_name"}}
                
        Returns:
            Union[str, Dict]: tool_choice 参数
        """
        if isinstance(choice, dict):
            return choice
        elif choice in ["auto", "none", "required"]:
            return choice
        else:
            # 假设是工具名称
            return {
                "type": "function",
                "function": {"name": choice}
            }
    
    @staticmethod
    def create_tool_call(
        tool_call_id: str,
        function_name: str,
        arguments: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """创建工具调用对象
        
        Args:
            tool_call_id: 工具调用ID
            function_name: 函数名称
            arguments: 函数参数（字符串或字典）
            
        Returns:
            Dict: 工具调用对象
        """
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments, ensure_ascii=False)
        
        return {
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": function_name,
                "arguments": arguments
            }
        }
    
    @staticmethod
    def parse_tool_call_arguments(arguments: str) -> Dict[str, Any]:
        """解析工具调用参数
        
        Args:
            arguments: JSON 格式的参数字符串
            
        Returns:
            Dict: 解析后的参数字典
            
        Raises:
            json.JSONDecodeError: 解析失败
        """
        return json.loads(arguments)
    
    @staticmethod
    def from_python_function(
        func: callable,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """从 Python 函数创建工具定义
        
        注意：需要函数有适当的类型注解和文档字符串
        
        Args:
            func: Python 函数
            name: 工具名称（默认使用函数名）
            description: 工具描述（默认使用文档字符串）
            
        Returns:
            Dict: 工具定义
        """
        import inspect
        
        # 获取函数名和描述
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip().split('\n')[0]
        
        # 获取函数签名
        sig = inspect.signature(func)
        parameters = []
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            # 推断类型
            param_type = ParameterType.STRING  # 默认
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = ParameterType.INTEGER
                elif param.annotation == float:
                    param_type = ParameterType.NUMBER
                elif param.annotation == bool:
                    param_type = ParameterType.BOOLEAN
                elif param.annotation == list:
                    param_type = ParameterType.ARRAY
                elif param.annotation == dict:
                    param_type = ParameterType.OBJECT
            
            # 判断是否必需
            required = param.default == inspect.Parameter.empty
            
            parameters.append(Parameter(
                name=param_name,
                type=param_type,
                description=f"Parameter {param_name}",
                required=required
            ))
        
        return ToolBuilder.create_tool(tool_name, tool_desc, parameters)
