# LLM 模块 API 参考

完整的 LLM 模块 API 文档。

## 目录

- [客户端](#客户端)
  - [BaseLLMClient](#basellmclient)
  - [OpenAIClient](#openaiclient)
  - [GeminiClient](#geminiclient)
  - [BedrockClient](#bedrockclient)
- [请求管理](#请求管理)
  - [LLMRequest](#llmrequest)
  - [LLMRequestManager](#llmrequestmanager)
  - [便捷函数](#便捷函数)
- [消息构建](#消息构建)
  - [MessageBuilder](#messagebuilder)
- [工具调用](#工具调用)
  - [ToolBuilder](#toolbuilder)
  - [Parameter](#parameter)
- [响应处理](#响应处理)
  - [ResponseParser](#responseparser)
  - [CompletionResponse](#completionresponse)
- [提示词](#提示词)
  - [PromptBuilder](#promptbuilder)
  - [SystemPrompts](#systemprompts)
- [异常](#异常)
- [工具函数](#工具函数)

---

## 客户端

### BaseLLMClient

所有 LLM 客户端的抽象基类。

```python
class BaseLLMClient(ABC):
    """LLM 客户端抽象基类"""
```

#### 方法

##### `initialize()`
```python
async def initialize() -> bool
```
初始化客户端连接。

**返回**：
- `bool` - 是否初始化成功

**示例**：
```python
client = OpenAIClient(api_key="...")
success = await client.initialize()
```

##### `close()`
```python
async def close() -> None
```
关闭客户端连接，释放资源。

##### `generate()`
```python
async def generate(
    messages: List[Dict[str, Any]],
    model: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
    **kwargs
) -> LLMResponse
```
生成文本响应。

**参数**：
- `messages` - 消息列表，格式：`[{"role": "user", "content": "..."}]`
- `model` - 模型名称
- `temperature` - 温度参数 (0-2)，控制随机性
- `max_tokens` - 最大生成 token 数
- `top_p` - 核采样参数 (0-1)
- 其他提供商特定参数通过 `kwargs` 传入（如 `frequency_penalty`、`presence_penalty` 等）。
- `stop` - 停止序列列表

**返回**：
- `LLMResponse` - 生成结果

**示例**：
```python
response = await client.generate(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4",
    temperature=0.7,
    max_tokens=1000
)
print(response.content)
```

##### `stream_generate()`
```python
async def stream_generate(
    messages: List[Dict[str, Any]],
    model: str,
    **kwargs
) -> AsyncIterator[StreamChunk]
```
流式生成文本。

**参数**：与 `generate()` 相同

**返回**：
- `AsyncIterator[StreamChunk]` - 文本片段迭代器

**示例**：
```python
async for chunk in client.stream_generate(
    messages=messages,
    model="gpt-4"
):
    print(chunk.content, end="", flush=True)
```

##### `generate_with_tools()`
```python
async def generate_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: str,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    **kwargs
) -> LLMResponse
```
使用工具调用生成。

**参数**：
- `messages` - 消息列表
- `tools` - 工具定义列表
- `model` - 模型名称
- `tool_choice` - 工具选择策略：可为字符串（如 "auto"、"none"、"required" 或工具名）或 OpenAI 风格的字典；当为 `None` 时默认按提供商实现采用 "auto"。

**返回**：
- `LLMResponse` - 包含工具调用的响应

##### `create_embeddings()`
```python
async def create_embeddings(
    texts: List[str],
    model: str,
    **kwargs
) -> List[List[float]]
```
创建文本嵌入向量。

**参数**：
- `texts` - 文本列表
- `model` - 嵌入模型名称

**返回**：
- `List[List[float]]` - 嵌入向量列表

##### `get_model_info()`
```python
async def get_model_info(model: str) -> ModelInfo
```
获取模型信息。

**返回**：
- `ModelInfo` - 模型能力和限制信息

---

### OpenAIClient

OpenAI 和兼容 API 的客户端。

```python
class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs
    )
```

**参数**：
- `api_key` - OpenAI API 密钥
- `base_url` - 自定义 API 基础 URL（用于兼容 API）
- `organization` - 组织 ID
- `timeout` - 请求超时时间（秒）
- `max_retries` - 最大重试次数

**示例**：
```python
# 标准 OpenAI
client = OpenAIClient(api_key="sk-...")

# 兼容 API (如 Azure OpenAI)
client = OpenAIClient(
    api_key="your-key",
    base_url="https://your-resource.openai.azure.com/openai/deployments"
)

# DeepSeek
client = OpenAIClient(
    api_key="your-key",
    base_url="https://api.deepseek.com/v1"
)
```

**支持的模型**：
- GPT-4 系列：`gpt-4`, `gpt-4-turbo`, `gpt-4-vision-preview`
- GPT-3.5 系列：`gpt-3.5-turbo`, `gpt-3.5-turbo-16k`
- 嵌入模型：`text-embedding-ada-002`, `text-embedding-3-small`, `text-embedding-3-large`

---

### GeminiClient

Google Gemini API 客户端。

```python
class GeminiClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs
    )
```

**参数**：
- `api_key` - Google API 密钥
- `base_url` - API 基础 URL（默认：官方 API）
- `timeout` - 请求超时时间
- `max_retries` - 最大重试次数

**示例**：
```python
client = GeminiClient(api_key="your-google-api-key")

response = await client.generate(
    messages=[{"role": "user", "content": "Hello"}],
    model="gemini-pro"
)
```

**支持的模型**：
- `gemini-pro` - 文本生成
- `gemini-pro-vision` - 多模态（文本+图像）
- `embedding-001` - 文本嵌入

**特殊功能**：
- 支持多模态输入（图像+文本）
- 支持安全设置（safety_settings）
- 自动转换消息格式

---

### BedrockClient

AWS Bedrock 多模型客户端。

```python
class BedrockClient(BaseLLMClient):
    def __init__(
        self,
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        profile_name: Optional[str] = None,
        **kwargs
    )
```

**参数**：
- `region_name` - AWS 区域
- `aws_access_key_id` - AWS 访问密钥
- `aws_secret_access_key` - AWS 秘密密钥
- `aws_session_token` - 会话令牌
- `profile_name` - AWS 配置文件名

**示例**：
```python
# 使用默认凭证
client = BedrockClient(region_name="us-east-1")

# 使用显式凭证
client = BedrockClient(
    region_name="us-east-1",
    aws_access_key_id="...",
    aws_secret_access_key="..."
)

# 使用配置文件
client = BedrockClient(profile_name="my-profile")
```

**支持的模型**：
- **Anthropic Claude**：`anthropic.claude-3-opus`, `anthropic.claude-3-sonnet`, `anthropic.claude-v2`
- **Meta Llama**：`meta.llama3-70b-instruct`, `meta.llama3-8b-instruct`
- **Amazon Titan**：`amazon.titan-text-express`, `amazon.titan-embed-text-v1`
- **AI21 Labs**：`ai21.j2-ultra`, `ai21.j2-mid`
- **Cohere**：`cohere.command-text-v14`

---

## 请求管理

### LLMRequest

LLM 请求配置数据类。

```python
@dataclass
class LLMRequest:
    model: str
    messages: List[Dict[str, Any]]
    provider: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[Union[str, List[str]]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    stream: bool = False
    response_format: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    user: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**方法**：

##### `validate()`
```python
def validate() -> bool
```
验证请求参数。

**抛出**：
- `ValidationError` - 参数无效

**示例**：
```python
request = LLMRequest(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7
)

request.validate()  # 检查参数有效性
```

---

### LLMRequestManager

LLM 请求管理器，管理客户端生命周期。

```python
class LLMRequestManager:
    def __init__(self, registry: Optional[ClientRegistry] = None)
```

**方法**：

##### `generate()`
```python
async def generate(
    request: LLMRequest,
    **kwargs
) -> LLMResponse
```
执行生成请求。

##### `stream_generate()`
```python
async def stream_generate(
    request: LLMRequest,
    **kwargs
) -> AsyncIterator[StreamChunk]
```
执行流式生成。

##### `generate_with_tools()`
```python
async def generate_with_tools(
    request: LLMRequest,
    **kwargs
) -> LLMResponse
```
执行工具调用生成。

##### `create_embeddings()`
```python
async def create_embeddings(
    texts: List[str],
    model: str,
    provider: Optional[str] = None,
    **kwargs
) -> List[List[float]]
```
创建文本嵌入。

##### `close()`
```python
async def close()
```
关闭所有客户端。

**示例**：
```python
manager = LLMRequestManager()

request = LLMRequest(
    model="gpt-4",
    messages=messages,
    provider="openai"
)

response = await manager.generate(request)
await manager.close()
```

---

### 便捷函数

模块提供了全局便捷函数：

##### `generate()`
```python
async def generate(
    model: str,
    messages: List[Dict[str, Any]],
    provider: Optional[str] = None,
    **kwargs
) -> LLMResponse
```

##### `stream_generate()`
```python
async def stream_generate(
    model: str,
    messages: List[Dict[str, Any]],
    provider: Optional[str] = None,
    **kwargs
) -> AsyncIterator[StreamChunk]
```

##### `generate_with_tools()`
```python
async def generate_with_tools(
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    provider: Optional[str] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    **kwargs
) -> LLMResponse
```

##### `create_embeddings()`
```python
async def create_embeddings(
    texts: List[str],
    model: str,
    provider: Optional[str] = None,
    **kwargs
) -> List[List[float]]
```

**示例**：
```python
from kernel.llm import generate, stream_generate

# 简单生成
response = await generate(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    provider="openai"
)

# 流式生成
async for chunk in stream_generate(
    model="gpt-4",
    messages=messages,
    provider="openai"
):
    print(chunk.content, end="")
```

---

## 消息构建

### MessageBuilder

消息构建器，提供便捷的消息创建方法。

```python
class MessageBuilder:
    """消息构建器"""
```

#### 静态方法

##### `create_system_message()`
```python
@staticmethod
def create_system_message(content: str) -> Dict[str, str]
```
创建系统消息。

**参数**：
- `content` - 系统提示词内容

**返回**：
- `Dict` - 系统消息

##### `create_user_message()`
```python
@staticmethod
def create_user_message(content: str, name: Optional[str] = None) -> Dict[str, Any]
```
创建用户消息。

**参数**：
- `content` - 用户消息内容
- `name` - 用户名（可选）

##### `create_assistant_message()`
```python
@staticmethod
def create_assistant_message(
    content: str,
    name: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]
```
创建助手消息。

##### `create_tool_message()`
```python
@staticmethod
def create_tool_message(
    tool_call_id: str,
    content: str
) -> Dict[str, Any]
```
创建工具响应消息。

##### `create_multimodal_message()`
```python
@staticmethod
def create_multimodal_message(
    text: str,
    image_urls: Optional[List[str]] = None,
    image_paths: Optional[List[str]] = None,
    detail: str = "auto"
) -> Dict[str, Any]
```
创建多模态消息（文本+图像）。

**参数**：
- `text` - 文本内容
- `image_urls` - 图像 URL 列表
- `image_paths` - 本地图像路径列表（会自动转换为 base64）
- `detail` - 图像细节级别："low", "high", "auto"

**示例**：
```python
from kernel.llm import MessageBuilder

# 系统消息
system = MessageBuilder.create_system_message("你是一个助手")

# 用户消息
user = MessageBuilder.create_user_message("你好")

# 多模态消息
multimodal = MessageBuilder.create_multimodal_message(
    text="这张图片里有什么？",
    image_paths=["photo.jpg"],
    detail="high"
)

# 工具响应消息
tool_response = MessageBuilder.create_tool_message(
    tool_call_id="call_123",
    content='{"temperature": 20, "condition": "sunny"}'
)

messages = [system, user, multimodal]
```

---

## 工具调用

### ToolBuilder

工具定义构建器。

```python
class ToolBuilder:
    """工具构建器"""
```

#### 静态方法

##### `create_tool()`
```python
@staticmethod
def create_tool(
    name: str,
    description: str,
    parameters: Optional[List[Parameter]] = None
) -> Dict[str, Any]
```
创建工具定义。

**参数**：
- `name` - 工具名称
- `description` - 工具描述
- `parameters` - 参数列表

**返回**：
- `Dict` - 标准格式的工具定义

##### `create_parameter()`
```python
@staticmethod
def create_parameter(
    name: str,
    param_type: Union[ParameterType, str],
    description: str,
    required: bool = False,
    **kwargs
) -> Parameter
```
创建参数定义。

**参数**：
- `name` - 参数名
- `param_type` - 参数类型："string", "number", "integer", "boolean", "array", "object"
- `description` - 参数描述
- `required` - 是否必需
- `**kwargs` - 其他属性（enum, default, items, properties）

##### `create_tool_choice()`
```python
@staticmethod
def create_tool_choice(
    choice: Union[Literal["auto", "none"], str, Dict[str, Any]]
) -> Union[str, Dict[str, Any]]
```
创建工具选择策略。

##### `from_python_function()`
```python
@staticmethod
def from_python_function(
    func: callable,
    name: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]
```
从 Python 函数创建工具定义（需要类型注解）。

**示例**：
```python
from kernel.llm import ToolBuilder, ParameterType

# 创建工具
tool = ToolBuilder.create_tool(
    name="get_weather",
    description="获取指定城市的天气信息",
    parameters=[
        ToolBuilder.create_parameter(
            name="city",
            param_type=ParameterType.STRING,
            description="城市名称",
            required=True
        ),
        ToolBuilder.create_parameter(
            name="unit",
            param_type=ParameterType.STRING,
            description="温度单位",
            enum=["celsius", "fahrenheit"],
            default="celsius"
        )
    ]
)

# 从函数创建
def calculate_sum(a: int, b: int) -> int:
    """计算两个数的和"""
    return a + b

tool = ToolBuilder.from_python_function(calculate_sum)

# 工具选择
tool_choice = ToolBuilder.create_tool_choice("auto")  # 自动选择
tool_choice = ToolBuilder.create_tool_choice("get_weather")  # 强制使用
```

---

### Parameter

参数定义数据类。

```python
@dataclass
class Parameter:
    name: str
    type: ParameterType
    description: str
    required: bool = False
    enum: Optional[List[Any]] = None
    items: Optional[Dict[str, Any]] = None
    properties: Optional[Dict[str, Any]] = None
    default: Optional[Any] = None
```

---

## 响应处理

### ResponseParser

响应解析器。

```python
class ResponseParser:
    """响应解析器"""
```

#### 静态方法

##### `parse_completion()`
```python
@staticmethod
def parse_completion(response: Dict[str, Any]) -> CompletionResponse
```
解析完整响应。

##### `extract_content()`
```python
@staticmethod
def extract_content(response: Dict[str, Any]) -> Optional[str]
```
提取响应内容。

##### `extract_tool_calls()`
```python
@staticmethod
def extract_tool_calls(response: Dict[str, Any]) -> List[ToolCall]
```
提取工具调用。

##### `extract_usage()`
```python
@staticmethod
def extract_usage(response: Dict[str, Any]) -> Optional[Usage]
```
提取使用统计。

##### `is_complete()`
```python
@staticmethod
def is_complete(response: Dict[str, Any]) -> bool
```
判断响应是否完成。

**示例**：
```python
from kernel.llm import ResponseParser

# 解析响应
parsed = ResponseParser.parse_completion(raw_response)

# 提取内容
content = ResponseParser.extract_content(raw_response)

# 提取工具调用
tool_calls = ResponseParser.extract_tool_calls(raw_response)
if tool_calls:
    for call in tool_calls:
        print(f"调用: {call.function.name}")
        args = call.function.get_arguments()
        print(f"参数: {args}")

# 检查完成状态
if ResponseParser.is_complete(raw_response):
    print("响应已完成")
```

---

### CompletionResponse

完整响应数据类。

```python
@dataclass
class CompletionResponse:
    id: str
    object: str
    created: int
    model: str
    choices: List[Choice]
    usage: Optional[Usage] = None
    system_fingerprint: Optional[str] = None
```

**方法**：

##### `get_first_message()`
```python
def get_first_message() -> Optional[Message]
```

##### `get_content()`
```python
def get_content() -> Optional[str]
```

##### `has_tool_calls()`
```python
def has_tool_calls() -> bool
```

##### `get_tool_calls()`
```python
def get_tool_calls() -> List[ToolCall]
```

---

## 提示词

### PromptBuilder

提示词构建器。

```python
class PromptBuilder:
    """提示词构建器"""
```

#### 静态方法

##### `build_system_prompt()`
```python
@staticmethod
def build_system_prompt(
    role: str = "assistant",
    capabilities: Optional[List[str]] = None,
    constraints: Optional[List[str]] = None,
    tone: Optional[str] = None
) -> str
```
构建系统提示词。

**示例**：
```python
from kernel.llm import PromptBuilder

prompt = PromptBuilder.build_system_prompt(
    role="专业的数据分析师",
    capabilities=[
        "分析数据趋势",
        "生成可视化建议",
        "解释统计结果"
    ],
    constraints=[
        "使用准确的术语",
        "提供可操作建议"
    ],
    tone="专业而友好"
)
```

##### `build_few_shot_prompt()`
```python
@staticmethod
def build_few_shot_prompt(
    task_description: str,
    examples: List[Dict[str, str]],
    query: str
) -> str
```
构建少样本学习提示词。

**示例**：
```python
prompt = PromptBuilder.build_few_shot_prompt(
    task_description="将文本分类为积极或消极",
    examples=[
        {"input": "这个产品很棒！", "output": "积极"},
        {"input": "质量太差了", "output": "消极"}
    ],
    query="服务很好"
)
```

##### `build_chain_of_thought_prompt()`
```python
@staticmethod
def build_chain_of_thought_prompt(
    question: str,
    require_reasoning: bool = True
) -> str
```
构建思维链提示词。

##### `build_structured_output_prompt()`
```python
@staticmethod
def build_structured_output_prompt(
    task: str,
    output_format: Dict[str, Any],
    example: Optional[Dict[str, Any]] = None
) -> str
```
构建结构化输出提示词。

---

### SystemPrompts

预设系统提示词。

```python
class SystemPrompts:
    BASIC_ASSISTANT = "..."
    PROFESSIONAL_ASSISTANT = "..."
    CODING_ASSISTANT = "..."
    DATA_ANALYSIS_ASSISTANT = "..."
    CREATIVE_WRITING_ASSISTANT = "..."
    TRANSLATION_ASSISTANT = "..."
    EDUCATION_ASSISTANT = "..."
    CUSTOMER_SERVICE_ASSISTANT = "..."
    JSON_MODE = "..."
    FUNCTION_CALLING_MODE = "..."
```

**使用**：
```python
from kernel.llm import SystemPrompts, get_system_prompt

# 直接使用
system = SystemPrompts.CODING_ASSISTANT

# 使用便捷函数
system = get_system_prompt("coding")
```

---

## 异常

完整的异常层次结构：

```python
LLMError                          # 基础异常
├── AuthenticationError           # 认证失败
├── RateLimitError                # 速率限制
├── ModelNotFoundError            # 模型不存在
├── InvalidRequestError           # 请求无效
├── APIConnectionError            # 连接失败
├── ContextLengthExceededError    # 上下文过长
├── InvalidResponseError          # 响应无效
├── TimeoutError                  # 超时
├── StreamError                   # 流式错误
└── ValidationError               # 验证错误
```

**使用**：
```python
from kernel.llm import (
    LLMError,
    AuthenticationError,
    RateLimitError
)

try:
    response = await generate(model="gpt-4", messages=messages)
except AuthenticationError:
    print("API 密钥无效")
except RateLimitError:
    print("请求过于频繁")
except LLMError as e:
    print(f"LLM 错误: {e}")
```

---

## 工具函数

### 图像处理

##### `compress_image()`
```python
def compress_image(
    image_path: str,
    max_size: tuple = (1024, 1024),
    quality: int = 85
) -> bytes
```
压缩图像。

##### `image_to_base64()`
```python
def image_to_base64(image_path: str, compress: bool = True) -> str
```
将图像转换为 base64。

##### `base64_to_image()`
```python
def base64_to_image(base64_str: str, output_path: str) -> None
```
将 base64 转换回图像。

##### `create_data_url()`
```python
def create_data_url(
    image_path: str,
    compress: bool = True
) -> str
```
创建 data URL。

### 文本处理

##### `estimate_tokens()`
```python
def estimate_tokens(text: str, model: str = "gpt-4") -> int
```
估算文本的 token 数量。

##### `truncate_text()`
```python
def truncate_text(
    text: str,
    max_tokens: int,
    model: str = "gpt-4"
) -> str
```
截断文本到指定 token 数。

**示例**：
```python
from kernel.llm import (
    image_to_base64,
    create_data_url,
    estimate_tokens,
    truncate_text
)

# 图像转 base64
base64_str = image_to_base64("photo.jpg", compress=True)

# 创建 data URL
data_url = create_data_url("photo.jpg")

# 估算 tokens
count = estimate_tokens("这是一段文本")
print(f"约 {count} tokens")

# 截断文本
truncated = truncate_text(long_text, max_tokens=1000)
```

---

## 数据类型

### LLMResponse

```python
@dataclass
class LLMResponse:
    content: str
    model: str
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Dict[str, int] = field(default_factory=dict)
    raw_response: Optional[Dict[str, Any]] = None
```

### StreamChunk

```python
@dataclass
class StreamChunk:
    content: str
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
```

### ModelInfo

```python
@dataclass
class ModelInfo:
    id: str
    provider: str
    capabilities: Set[ModelCapability]
    context_window: int
    max_output_tokens: int
    supports_streaming: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### ModelCapability

```python
class ModelCapability(Enum):
    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    CODE_GENERATION = "code_generation"
```

---

## 更多资源

- [README](README.md) - 模块总览
- [最佳实践](BEST_PRACTICES.md) - 使用建议
- [快速参考](QUICK_REFERENCE.md) - 常用功能
- [提示词指南](PROMPT_GUIDE.md) - 提示词工程
- [工具调用指南](TOOL_CALLING_GUIDE.md) - Function Calling
