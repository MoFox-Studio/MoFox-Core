"""
LLM 模块

提供统一的 LLM 交互接口，支持多种提供商和模型
"""

# 基础组件
from .model_client import (
    BaseLLMClient,
    ModelInfo,
    LLMResponse,
    StreamChunk,
    ModelCapability,
    OpenAIClient,
    GeminiClient,
    BedrockClient,
    OPENAI_CLIENT_AVAILABLE,
    GEMINI_CLIENT_AVAILABLE,
    BEDROCK_CLIENT_AVAILABLE
)

# 客户端注册
from .client_registry import (
    ClientRegistry,
    get_registry,
    register_client,
    unregister_client,
    get_client,
    create_client,
    list_clients
)

# 异常
from .exceptions import (
    LLMError,
    AuthenticationError,
    RateLimitError,
    ModelNotFoundError,
    InvalidRequestError,
    APIConnectionError,
    ContextLengthExceededError,
    InvalidResponseError,
    ValidationError,
    TimeoutError as LLMTimeoutError,
    StreamError
)

# 请求管理
from .llm_request import (
    LLMRequest,
    LLMRequestManager,
    get_manager,
    generate,
    stream_generate,
    generate_with_tools,
    create_embeddings
)

# Payload 构建器
from .payload import (
    # Message
    MessageBuilder,
    MessageRole,
    
    # Tool
    ToolBuilder,
    ToolType,
    ParameterType,
    Parameter,
    FunctionDefinition,
    ToolDefinition,
    
    # Response
    ResponseParser,
    CompletionResponse,
    Choice,
    Message,
    Usage,
    FunctionCall,
    ToolCall,
    FinishReason,
    
    # Prompt
    SystemPrompts,
    PromptTemplates,
    PromptBuilder,
    get_system_prompt,
    create_qa_prompt,
    create_summary_prompt,
    create_translation_prompt
)

# 工具函数
from .utils import (
    compress_image,
    image_to_base64,
    base64_to_image,
    create_data_url,
    estimate_tokens,
    truncate_text
)

# 视频处理（inkfox）
from .video_utils import (
    VideoKeyframeExtractor,
    extract_keyframes_from_video,
    get_system_info,
    check_inkfox_available,
    INKFOX_AVAILABLE
)


__all__ = [
    # Base Client
    "BaseLLMClient",
    "ModelInfo",
    "LLMResponse",
    "StreamChunk",
    "ModelCapability",
    
    # Client Implementations
    "OpenAIClient",
    "GeminiClient",
    "BedrockClient",
    "OPENAI_CLIENT_AVAILABLE",
    "GEMINI_CLIENT_AVAILABLE",
    "BEDROCK_CLIENT_AVAILABLE",
    
    # Registry
    "ClientRegistry",
    "get_registry",
    "register_client",
    "unregister_client",
    "get_client",
    "create_client",
    "list_clients",
    
    # Exceptions
    "LLMError",
    "AuthenticationError",
    "RateLimitError",
    "ModelNotFoundError",
    "InvalidRequestError",
    "APIConnectionError",
    "ContextLengthExceededError",
    "InvalidResponseError",
    "LLMTimeoutError",
    "StreamError",
    
    # Request
    "LLMRequest",
    "LLMRequestManager",
    "get_manager",
    "generate",
    "stream_generate",
    "generate_with_tools",
    "create_embeddings",
    
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
    
    # Utils
    "compress_image",
    "image_to_base64",
    "base64_to_image",
    "create_data_url",
    "estimate_tokens",
    "truncate_text",
    
    # Video Utils (inkfox)
    "VideoKeyframeExtractor",
    "extract_keyframes_from_video",
    "get_system_info",
    "check_inkfox_available",
    "INKFOX_AVAILABLE",
]


# 版本信息
__version__ = "0.1.0"
