"""
AWS Bedrock 客户端实现

支持 AWS Bedrock 的各种模型（Claude, Llama, Titan 等）
"""

from typing import List, Dict, Any, Optional, AsyncIterator, Union, TYPE_CHECKING
import json
import asyncio

from .base_client import BaseLLMClient, ModelInfo, LLMResponse, StreamChunk, ModelCapability
from ..exceptions import (
    LLMError,
    AuthenticationError,
    RateLimitError,
    ModelNotFoundError,
    InvalidRequestError,
    APIConnectionError
)

try:
    from ...logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# boto3 是可选的
try:
    import boto3  # type: ignore[import-not-found]
    from botocore.exceptions import ClientError, BotoCoreError  # type: ignore[import-not-found]
    BOTO3_AVAILABLE = True
except ImportError:
    boto3 = None  # type: ignore[assignment]
    class ClientError(Exception):
        pass
    class BotoCoreError(Exception):
        pass
    BOTO3_AVAILABLE = False
    logger.warning("boto3 package not available. Install with: pip install boto3")

if TYPE_CHECKING:
    pass  # type: ignore[import-not-found]


class BedrockClient(BaseLLMClient):
    """AWS Bedrock 客户端
    
    支持多种模型提供商：
    - Anthropic Claude
    - Meta Llama
    - Amazon Titan
    - AI21 Jurassic
    - Cohere Command
    """
    
    def __init__(
        self,
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        profile_name: Optional[str] = None,
        **kwargs
    ):
        """初始化 Bedrock 客户端
        
        Args:
            region_name: AWS 区域
            aws_access_key_id: AWS 访问密钥 ID
            aws_secret_access_key: AWS 秘密访问密钥
            aws_session_token: AWS 会话令牌
            profile_name: AWS 配置文件名称
            **kwargs: 其他参数
        """
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 package is required for BedrockClient. "
                "Install with: pip install boto3"
            )
        assert boto3 is not None
        
        super().__init__()
        
        self.region_name = region_name
        
        # 创建会话
        session_kwargs = {}
        if aws_access_key_id:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key
        if aws_session_token:
            session_kwargs["aws_session_token"] = aws_session_token
        if profile_name:
            session_kwargs["profile_name"] = profile_name
        
        self.session = boto3.Session(**session_kwargs)
        self.client = self.session.client(
            service_name="bedrock-runtime",
            region_name=region_name
        )
        
        logger.info(f"Bedrock client initialized for region {region_name}")
    
    async def initialize(self) -> bool:
        """初始化客户端
        
        Returns:
            bool: 是否初始化成功
        """
        try:
            # 测试连接 - 尝试列出基础模型
            bedrock_client = self.session.client(
                service_name="bedrock",
                region_name=self.region_name
            )
            
            # 同步调用，需要在线程池中执行
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                bedrock_client.list_foundation_models
            )
            
            logger.debug(f"Bedrock client initialized, {len(response.get('modelSummaries', []))} models available")
            return True
            
        except ClientError as e:
            error_response = getattr(e, "response", {}) or {}
            error_code = error_response.get("Error", {}).get("Code", "")
            if error_code == "UnrecognizedClientException":
                raise AuthenticationError("Invalid AWS credentials")
            logger.error(f"Initialization failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    async def close(self):
        """关闭客户端"""
        # boto3 客户端不需要显式关闭
        logger.info("Bedrock client closed")
    
    def _handle_error(self, error: ClientError) -> LLMError:
        """处理错误
        
        Args:
            error: boto3 客户端错误
            
        Returns:
            LLMError: 转换后的错误
        """
        error_response = getattr(error, "response", {}) or {}
        error_code = error_response.get("Error", {}).get("Code", "")
        error_message = error_response.get("Error", {}).get("Message", "")
        
        if error_code == "UnrecognizedClientException":
            return AuthenticationError(f"Authentication failed: {error_message}")
        elif error_code == "ThrottlingException":
            return RateLimitError(f"Rate limit exceeded: {error_message}")
        elif error_code == "ResourceNotFoundException":
            return ModelNotFoundError(f"Model not found: {error_message}")
        elif error_code == "ValidationException":
            return InvalidRequestError(f"Invalid request: {error_message}")
        elif error_code == "ServiceUnavailableException":
            return APIConnectionError(f"Service unavailable: {error_message}")
        else:
            return LLMError(f"Bedrock error: {error_message}")
    
    def _convert_messages_to_bedrock_format(
        self,
        messages: List[Dict[str, Any]],
        model_id: str
    ) -> Dict[str, Any]:
        """转换消息格式为 Bedrock 格式
        
        Args:
            messages: OpenAI 风格的消息列表
            model_id: 模型 ID
            
        Returns:
            Dict: Bedrock 格式的请求体
        """
        # 根据模型类型选择格式
        if "anthropic.claude" in model_id:
            return self._convert_to_claude_format(messages)
        elif "meta.llama" in model_id:
            return self._convert_to_llama_format(messages)
        elif "amazon.titan" in model_id:
            return self._convert_to_titan_format(messages)
        else:
            # 默认格式
            return self._convert_to_claude_format(messages)
    
    def _convert_to_claude_format(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """转换为 Claude 格式"""
        # Claude 使用特殊的提示格式
        system = None
        conversation = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                system = content
            elif role == "user":
                conversation.append({"role": "user", "content": content})
            elif role == "assistant":
                conversation.append({"role": "assistant", "content": content})
        
        request_body = {"messages": conversation}
        
        if system:
            request_body["system"] = system
        
        return request_body
    
    def _convert_to_llama_format(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """转换为 Llama 格式"""
        # Llama 使用简单的提示格式
        prompt_parts = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"<<SYS>>\n{content}\n<</SYS>>")
            elif role == "user":
                prompt_parts.append(f"[INST] {content} [/INST]")
            elif role == "assistant":
                prompt_parts.append(content)
        
        return {"prompt": "\n\n".join(prompt_parts)}
    
    def _convert_to_titan_format(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """转换为 Titan 格式"""
        # Titan 使用简单的输入格式
        input_text = "\n\n".join(
            f"{msg.get('role')}: {msg.get('content', '')}" 
            for msg in messages
        )
        
        return {"inputText": input_text}
    
    async def generate(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> LLMResponse:
        """生成文本
        
        Args:
            messages: 消息列表
            model: 模型 ID
            temperature: 温度参数
            max_tokens: 最大 token 数
            top_p: Top-p 采样
            stop: 停止序列
            **kwargs: 其他参数
            
        Returns:
            LLMResponse: 生成结果
        """
        try:
            # 转换消息格式
            request_body = self._convert_messages_to_bedrock_format(messages, model)
            
            # 添加生成配置
            if "anthropic.claude" in model:
                request_body["max_tokens"] = max_tokens or 2048
                request_body["temperature"] = temperature
                request_body["top_p"] = top_p
                if stop:
                    request_body["stop_sequences"] = stop
            
            elif "meta.llama" in model:
                request_body["max_gen_len"] = max_tokens or 2048
                request_body["temperature"] = temperature
                request_body["top_p"] = top_p
            
            elif "amazon.titan" in model:
                request_body["textGenerationConfig"] = {
                    "maxTokenCount": max_tokens or 2048,
                    "temperature": temperature,
                    "topP": top_p
                }
                if stop:
                    request_body["textGenerationConfig"]["stopSequences"] = stop
            
            logger.debug(f"Generating with model {model}")
            
            # 调用 API（在线程池中执行同步调用）
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.invoke_model(
                    modelId=model,
                    body=json.dumps(request_body)
                )
            )
            
            # 解析响应
            response_body = json.loads(response["body"].read())
            
            # 提取内容（根据模型类型）
            if "anthropic.claude" in model:
                content = response_body.get("content", [{}])[0].get("text", "")
                usage = {
                    "prompt_tokens": response_body.get("usage", {}).get("input_tokens", 0),
                    "completion_tokens": response_body.get("usage", {}).get("output_tokens", 0),
                    "total_tokens": 0
                }
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                finish_reason = response_body.get("stop_reason", "stop")
            
            elif "meta.llama" in model:
                content = response_body.get("generation", "")
                usage = {
                    "prompt_tokens": response_body.get("prompt_token_count", 0),
                    "completion_tokens": response_body.get("generation_token_count", 0),
                    "total_tokens": 0
                }
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                finish_reason = response_body.get("stop_reason", "stop")
            
            elif "amazon.titan" in model:
                results = response_body.get("results", [{}])
                content = results[0].get("outputText", "") if results else ""
                usage = {
                    "prompt_tokens": response_body.get("inputTextTokenCount", 0),
                    "completion_tokens": results[0].get("tokenCount", 0) if results else 0,
                    "total_tokens": 0
                }
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                finish_reason = results[0].get("completionReason", "FINISH") if results else "FINISH"
            
            else:
                content = str(response_body)
                usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                finish_reason = "stop"
            
            result = LLMResponse(
                content=content,
                model=model,
                finish_reason=finish_reason,
                usage=usage,
                raw_response=response_body
            )
            
            logger.debug(f"Generation completed: {result.usage}")
            return result
            
        except ClientError as e:
            logger.error(f"Generation failed: {e}")
            raise self._handle_error(e)
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise LLMError(f"Bedrock error: {e}") from e
    
    async def stream_generate(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """流式生成文本
        
        Args:
            messages: 消息列表
            model: 模型 ID
            temperature: 温度参数
            max_tokens: 最大 token 数
            top_p: Top-p 采样
            stop: 停止序列
            **kwargs: 其他参数
            
        Yields:
            StreamChunk: 生成的文本片段
        """
        try:
            # 转换消息格式
            request_body = self._convert_messages_to_bedrock_format(messages, model)
            
            # 添加生成配置（与 generate 相同）
            if "anthropic.claude" in model:
                request_body["max_tokens"] = max_tokens or 2048
                request_body["temperature"] = temperature
                request_body["top_p"] = top_p
                if stop:
                    request_body["stop_sequences"] = stop
            
            logger.debug(f"Streaming generation with model {model}")
            
            # 流式调用 API
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.invoke_model_with_response_stream(
                    modelId=model,
                    body=json.dumps(request_body)
                )
            )
            
            # 读取流
            stream = response.get("body")
            if stream:
                for event in stream:
                    chunk_data = event.get("chunk")
                    if chunk_data:
                        chunk_json = json.loads(chunk_data.get("bytes").decode())
                        
                        # 提取内容（根据模型类型）
                        content = ""
                        finish_reason = None
                        
                        if "anthropic.claude" in model:
                            delta = chunk_json.get("delta", {})
                            content = delta.get("text", "")
                            if chunk_json.get("type") == "message_stop":
                                finish_reason = chunk_json.get("stop_reason")
                        
                        elif "meta.llama" in model:
                            content = chunk_json.get("generation", "")
                        
                        elif "amazon.titan" in model:
                            content = chunk_json.get("outputText", "")
                        
                        if content:
                            yield StreamChunk(
                                content=content,
                                model=model,
                                finish_reason=finish_reason
                            )
            
            logger.debug("Streaming generation completed")
            
        except ClientError as e:
            logger.error(f"Streaming generation failed: {e}")
            raise self._handle_error(e)
        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            raise LLMError(f"Bedrock error: {e}") from e
    
    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto",
        **kwargs
    ) -> LLMResponse:
        """使用工具调用生成
        
        注意：目前主要支持 Claude 3 模型的工具调用
        
        Args:
            messages: 消息列表
            tools: 工具列表
            model: 模型 ID
            tool_choice: 工具选择策略
            **kwargs: 其他参数
            
        Returns:
            LLMResponse: 生成结果
        """
        if "anthropic.claude-3" not in model:
            logger.warning(f"Model {model} may not support tool calling")
        
        try:
            # 转换消息格式
            request_body = self._convert_messages_to_bedrock_format(messages, model)
            
            # 转换工具格式（Claude 格式）
            claude_tools = []
            for tool in tools:
                if tool.get("type") == "function":
                    func = tool.get("function", {})
                    claude_tools.append({
                        "name": func.get("name"),
                        "description": func.get("description"),
                        "input_schema": func.get("parameters")
                    })
            
            request_body["tools"] = claude_tools
            
            # 添加工具选择策略
            if tool_choice and tool_choice != "auto":
                if tool_choice == "none":
                    request_body["tool_choice"] = {"type": "auto"}
                else:
                    request_body["tool_choice"] = {
                        "type": "tool",
                        "name": tool_choice
                    }
            
            logger.debug(f"Generating with tools, model {model}")
            
            # 调用 API
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.invoke_model(
                    modelId=model,
                    body=json.dumps(request_body)
                )
            )
            
            # 解析响应
            response_body = json.loads(response["body"].read())
            
            # 提取内容和工具调用
            content_blocks = response_body.get("content", [])
            content = ""
            tool_calls = []
            
            for block in content_blocks:
                if block.get("type") == "text":
                    content += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {}))
                        }
                    })
            
            # 提取使用情况
            usage = {
                "prompt_tokens": response_body.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": response_body.get("usage", {}).get("output_tokens", 0),
                "total_tokens": 0
            }
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            
            result = LLMResponse(
                content=content,
                model=model,
                finish_reason=response_body.get("stop_reason", "stop"),
                tool_calls=tool_calls if tool_calls else None,
                usage=usage,
                raw_response=response_body
            )
            
            logger.debug(f"Tool calling completed: {len(tool_calls)} calls")
            return result
            
        except ClientError as e:
            logger.error(f"Tool calling failed: {e}")
            raise self._handle_error(e)
        except Exception as e:
            logger.error(f"Tool calling failed: {e}")
            raise LLMError(f"Bedrock error: {e}") from e
    
    async def create_embeddings(
        self,
        texts: List[str],
        model: str = "amazon.titan-embed-text-v1",
        **kwargs
    ) -> List[List[float]]:
        """创建文本嵌入
        
        Args:
            texts: 文本列表
            model: 模型 ID
            **kwargs: 其他参数
            
        Returns:
            List[List[float]]: 嵌入向量列表
        """
        try:
            logger.debug(f"Creating embeddings for {len(texts)} texts")
            
            embeddings = []
            loop = asyncio.get_event_loop()
            
            # Bedrock 嵌入 API 每次处理一个文本
            for text in texts:
                request_body = {"inputText": text}
                
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.invoke_model(
                        modelId=model,
                        body=json.dumps(request_body)
                    )
                )
                
                response_body = json.loads(response["body"].read())
                embedding = response_body.get("embedding", [])
                embeddings.append(embedding)
            
            logger.debug(f"Embeddings created: {len(embeddings)} vectors")
            return embeddings
            
        except ClientError as e:
            logger.error(f"Embeddings creation failed: {e}")
            raise self._handle_error(e)
        except Exception as e:
            logger.error(f"Embeddings creation failed: {e}")
            raise LLMError(f"Bedrock error: {e}") from e
    
    async def get_model_info(self, model: str) -> ModelInfo:
        """获取模型信息
        
        Args:
            model: 模型 ID
            
        Returns:
            ModelInfo: 模型信息
        """
        # Bedrock 不提供详细的模型信息 API，使用预定义的信息
        capabilities = {ModelCapability.CHAT}
        
        # 根据模型 ID 推断能力
        if "anthropic.claude-3" in model:
            capabilities.add(ModelCapability.FUNCTION_CALLING)
            if "opus" in model or "sonnet" in model:
                capabilities.add(ModelCapability.VISION)
        
        if "embed" in model:
            capabilities = {ModelCapability.EMBEDDINGS}
        
        # 预定义的上下文窗口
        context_windows = {
            "anthropic.claude-3-opus": 200000,
            "anthropic.claude-3-sonnet": 200000,
            "anthropic.claude-3-haiku": 200000,
            "anthropic.claude-v2": 100000,
            "meta.llama3-70b": 8192,
            "meta.llama3-8b": 8192,
            "amazon.titan-text": 32000
        }
        
        context_window = 8192  # 默认值
        for key, value in context_windows.items():
            if key in model:
                context_window = value
                break
        
        return ModelInfo(
            provider="bedrock",
            model=model,
            capabilities=capabilities,
            context_window=context_window,
            max_output_tokens=context_window // 2,
            supports_streaming=True
        )