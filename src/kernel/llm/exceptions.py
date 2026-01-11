"""
LLM 异常类定义

定义 LLM 请求过程中可能出现的各种异常
"""


class LLMError(Exception):
    """LLM 异常基类"""
    pass


class ConfigurationError(LLMError):
    """配置错误异常"""
    pass


class AuthenticationError(LLMError):
    """认证错误异常
    
    当 API 密钥无效或认证失败时抛出
    """
    pass


class RateLimitError(LLMError):
    """速率限制异常
    
    当达到 API 调用速率限制时抛出
    """
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after  # 建议重试的秒数


class QuotaExceededError(LLMError):
    """配额超限异常
    
    当达到账户配额限制时抛出
    """
    pass


class InvalidRequestError(LLMError):
    """无效请求异常
    
    当请求参数无效时抛出
    """
    pass


class ModelNotFoundError(LLMError):
    """模型未找到异常
    
    当请求的模型不存在或不可用时抛出
    """
    def __init__(self, model_name: str, message: str = None):
        self.model_name = model_name
        msg = message or f"Model '{model_name}' not found or not available"
        super().__init__(msg)


class ContextLengthExceededError(LLMError):
    """上下文长度超限异常
    
    当输入超过模型的最大上下文长度时抛出
    """
    def __init__(self, message: str, max_tokens: int = None, actual_tokens: int = None):
        super().__init__(message)
        self.max_tokens = max_tokens
        self.actual_tokens = actual_tokens


class ContentFilterError(LLMError):
    """内容过滤异常
    
    当内容被安全过滤器拦截时抛出
    """
    pass


class TimeoutError(LLMError):
    """超时异常
    
    当请求超时时抛出
    """
    def __init__(self, message: str, timeout: float = None):
        super().__init__(message)
        self.timeout = timeout


class NetworkError(LLMError):
    """网络错误异常
    
    当网络连接失败时抛出
    """
    pass


class APIConnectionError(NetworkError):
    """API 连接错误
    
    当与远端 API 建立或维持连接失败时抛出
    """
    pass


class ServerError(LLMError):
    """服务器错误异常
    
    当 API 服务器返回 5xx 错误时抛出
    """
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class ResponseParseError(LLMError):
    """响应解析错误异常
    
    当无法解析 API 响应时抛出
    """
    pass


class InvalidResponseError(LLMError):
    """响应格式或内容不合法时抛出"""
    pass


class ValidationError(LLMError):
    """请求参数验证失败时抛出"""
    pass


class StreamError(LLMError):
    """流式响应错误异常
    
    当流式响应出现错误时抛出
    """
    pass


class ToolCallError(LLMError):
    """工具调用错误异常
    
    当函数调用或工具调用失败时抛出
    """
    pass
