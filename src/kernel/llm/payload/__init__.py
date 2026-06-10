"""
LLM Payload 子模块

提供标准化的 LLM 请求和响应构建工具
"""

from .message import MessageBuilder, MessageRole
from .resp_format import (
    Choice,
    CompletionResponse,
    FinishReason,
    FunctionCall,
    Message,
    ResponseParser,
    ToolCall,
    Usage,
)
from .standard_prompt import (
    PromptBuilder,
    PromptTemplates,
    SystemPrompts,
    create_qa_prompt,
    create_summary_prompt,
    create_translation_prompt,
    get_system_prompt,
)
from .tool_option import FunctionDefinition, Parameter, ParameterType, ToolBuilder, ToolDefinition, ToolType

__all__ = [
    # Message
    "MessageBuilder",
    "MessageRole",

    # Tool
    "ToolBuilder",
    "ToolType",
    "ParameterType",
    "Parameter",
    "FunctionDefinition",
    "ToolDefinition",

    # Response
    "ResponseParser",
    "CompletionResponse",
    "Choice",
    "Message",
    "Usage",
    "FunctionCall",
    "ToolCall",
    "FinishReason",

    # Prompt
    "SystemPrompts",
    "PromptTemplates",
    "PromptBuilder",
    "get_system_prompt",
    "create_qa_prompt",
    "create_summary_prompt",
    "create_translation_prompt",
]
