"""
LLM Model Client 子模块

提供各种 LLM 提供商的客户端实现
"""

from .base_client import (
    BaseLLMClient,
    ModelInfo,
    LLMResponse,
    StreamChunk,
    ModelCapability
)

# 条件导入客户端实现
try:
    from .openai_client import OpenAIClient
    OPENAI_CLIENT_AVAILABLE = True
except ImportError:
    OPENAI_CLIENT_AVAILABLE = False
    OpenAIClient = None

try:
    from .aiohttp_gemini_clinet import GeminiClient
    GEMINI_CLIENT_AVAILABLE = True
except ImportError:
    GEMINI_CLIENT_AVAILABLE = False
    GeminiClient = None

try:
    from .bedrock_client import BedrockClient
    BEDROCK_CLIENT_AVAILABLE = True
except ImportError:
    BEDROCK_CLIENT_AVAILABLE = False
    BedrockClient = None


__all__ = [
    # Base
    "BaseLLMClient",
    "ModelInfo",
    "LLMResponse",
    "StreamChunk",
    "ModelCapability",
    
    # Clients
    "OpenAIClient",
    "GeminiClient",
    "BedrockClient",
    
    # Availability flags
    "OPENAI_CLIENT_AVAILABLE",
    "GEMINI_CLIENT_AVAILABLE",
    "BEDROCK_CLIENT_AVAILABLE",
]