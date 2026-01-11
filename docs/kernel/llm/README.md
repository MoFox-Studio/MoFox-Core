# LLM 模块文档

MoFox LLM 模块提供统一的大语言模型交互接口，支持多个主流 LLM 提供商。

## 📚 文档导航

- [API 参考](API_REFERENCE.md) - 完整的 API 文档
- [最佳实践](BEST_PRACTICES.md) - 使用建议和最佳实践
- [快速参考](QUICK_REFERENCE.md) - 常用功能速查
- [提示词指南](PROMPT_GUIDE.md) - 提示词工程最佳实践
- [工具调用指南](TOOL_CALLING_GUIDE.md) - Function Calling 完整指南
- [inkfox 集成指南](INKFOX_INTEGRATION.md) - 视频关键帧提取功能

## 🎯 核心特性

### 多提供商支持
- **OpenAI** - GPT-3.5/GPT-4 系列
- **Google Gemini** - Gemini Pro/Ultra
- **AWS Bedrock** - Claude、Llama、Titan 等

### 统一接口
```python
# 所有提供商使用相同的 API
response = await generate(
    model="gpt-4",
    messages=[{"role": "user", "content": "你好"}],
    provider="openai"
)
```

### 功能完整
- ✅ 文本生成
- ✅ 流式响应
- ✅ 工具调用（Function Calling）
- ✅ 多模态（文本+图像）
- ✅ 文本嵌入
- ✅ 异步支持
- ✅ 自动重试
- ✅ 日志集成
- ✅ 视频关键帧提取（inkfox）

## 🚀 快速开始

### 安装依赖

```bash
# 基础依赖
pip install openai aiohttp boto3

# 可选依赖
pip install inkfox  # 视频关键帧提取（需要 Python >= 3.11）
pip install pillow  # 图像处理
```

> Windows 提示：如遇到 `pip` 读取 `requirements.txt` 的编码错误（例如 `gbk` 解码失败），可先在终端执行 `chcp 65001` 切换到 UTF-8，再安装依赖；或先单独安装关键依赖验证：

```bash
chcp 65001
py -3.11 -m pip install -r requirements.txt

# 仅安装关键依赖验证运行
py -3.11 -m pip install "openai>=1.10.0"
py -3.11 -m pytest -q
```

> VS Code 解释器：若编辑器报 “无法解析导入 openai”，请在 VS Code 右下角选择与你运行一致的 Python 解释器（推荐 3.11），或在工作区设置中配置 `python.defaultInterpreterPath`。

### 基础使用

```python
from kernel.llm import generate, MessageBuilder

# 创建消息
messages = [
    MessageBuilder.create_system_message("你是一个有帮助的助手"),
    MessageBuilder.create_user_message("什么是机器学习？")
]

# 生成响应
response = await generate(
    model="gpt-4",
    messages=messages,
    provider="openai",
    temperature=0.7
)

print(response.content)
print(f"使用 tokens: {response.usage['total_tokens']}")
```

### 流式生成

```python
from kernel.llm import stream_generate

async for chunk in stream_generate(
    model="gpt-4",
    messages=messages,
    provider="openai"
):
    print(chunk.content, end="", flush=True)
```

### 工具调用

```python
from kernel.llm import generate_with_tools, ToolBuilder

# 定义工具
tool = ToolBuilder.create_tool(
    name="get_weather",
    description="获取指定城市的天气信息",
    parameters=[
        ToolBuilder.create_parameter(
            name="city",
            param_type="string",
            description="城市名称",
            required=True
        ),
        ToolBuilder.create_parameter(
            name="unit",
            param_type="string",
            description="温度单位",
            enum=["celsius", "fahrenheit"],
            default="celsius"
        )
    ]
)

# 使用工具
response = await generate_with_tools(
    model="gpt-4",
    messages=[MessageBuilder.create_user_message("北京今天天气如何？")],
    tools=[tool],
    provider="openai"
)

# 检查是否有工具调用
if response.tool_calls:
    for call in response.tool_calls:
        print(f"调用工具: {call['function']['name']}")
        print(f"参数: {call['function']['arguments']}")
```

### 多模态输入

```python
from kernel.llm import MessageBuilder

# 创建包含图像的消息
message = MessageBuilder.create_multimodal_message(
    text="这张图片里有什么？",
    image_paths=["image.jpg"]  # 自动处理图像
)

response = await generate(
    model="gpt-4-vision-preview",
    messages=[message],
    provider="openai"
)
```

## 🔧 客户端注册

### 注册自定义客户端

```python
from kernel.llm import register_client, OpenAIClient

# 注册 OpenAI 客户端
client = OpenAIClient(
    api_key="your-api-key",
    base_url="https://api.openai.com/v1"
)

register_client("openai", client)
```

### 使用自定义 API

```python
# 注册兼容 OpenAI 的 API（如 DeepSeek）
deepseek_client = OpenAIClient(
    api_key="your-deepseek-key",
    base_url="https://api.deepseek.com/v1"
)

register_client("deepseek", deepseek_client)

# 使用
response = await generate(
    model="deepseek-chat",
    messages=messages,
    provider="deepseek"
)
```

## 📝 提示词管理

### 使用预设提示词

```python
from kernel.llm import get_system_prompt

# 获取预设系统提示词
system_prompt = get_system_prompt("coding")  # 编程助手
# system_prompt = get_system_prompt("translation")  # 翻译助手
# system_prompt = get_system_prompt("data_analysis")  # 数据分析助手

messages = [
    MessageBuilder.create_system_message(system_prompt),
    MessageBuilder.create_user_message("用 Python 实现快速排序")
]
```

### 使用提示词模板

```python
from kernel.llm import PromptTemplates

# 问答模板
prompt = PromptTemplates.QA_TEMPLATE.substitute(
    context="Python 是一种高级编程语言...",
    question="Python 的主要特点是什么？"
)

# 总结模板
prompt = PromptTemplates.SUMMARY_TEMPLATE.substitute(
    content="长篇文章内容...",
    max_length=200
)
```

### 自定义提示词构建

```python
from kernel.llm import PromptBuilder

# 构建结构化提示词
prompt = PromptBuilder.build_system_prompt(
    role="专业的数据分析师",
    capabilities=[
        "分析数据趋势",
        "生成可视化建议",
        "解释统计结果"
    ],
    constraints=[
        "使用准确的统计术语",
        "提供可操作的建议",
        "避免过度技术化"
    ],
    tone="专业而友好"
)
```

## 🎨 响应处理

### 解析响应

```python
from kernel.llm import ResponseParser

# 解析完整响应
parsed = ResponseParser.parse_completion(raw_response)

# 提取内容
content = ResponseParser.extract_content(raw_response)

# 提取工具调用
tool_calls = ResponseParser.extract_tool_calls(raw_response)

# 提取使用情况
usage = ResponseParser.extract_usage(raw_response)
```

### 处理流式响应

```python
from kernel.llm import stream_generate

full_content = ""
async for chunk in stream_generate(model="gpt-4", messages=messages):
    full_content += chunk.content
    
    # 检查是否完成
    if chunk.finish_reason:
        print(f"\n完成原因: {chunk.finish_reason}")
        break
```

## 🔄 错误处理

```python
from kernel.llm import (
    generate,
    LLMError,
    AuthenticationError,
    RateLimitError,
    ContextLengthExceededError
)

try:
    response = await generate(
        model="gpt-4",
        messages=messages,
        provider="openai"
    )
except AuthenticationError as e:
    print(f"认证失败: {e}")
except RateLimitError as e:
    print(f"速率限制: {e}")
    # 实现退避重试
except ContextLengthExceededError as e:
    print(f"上下文过长: {e}")
    # 截断消息或使用更大窗口的模型
except LLMError as e:
    print(f"LLM 错误: {e}")
```

## 📊 使用统计

```python
# 响应包含详细的使用统计
response = await generate(model="gpt-4", messages=messages)

print(f"提示词 tokens: {response.usage['prompt_tokens']}")
print(f"生成 tokens: {response.usage['completion_tokens']}")
print(f"总计 tokens: {response.usage['total_tokens']}")
print(f"完成原因: {response.finish_reason}")
```

## 🛠️ 高级功能

### 自定义生成参数

```python
response = await generate(
    model="gpt-4",
    messages=messages,
    temperature=0.9,          # 创造性 (0-2)
    max_tokens=1000,          # 最大输出长度
    top_p=0.95,               # 核采样
    frequency_penalty=0.5,    # 频率惩罚
    presence_penalty=0.5,     # 存在惩罚
    stop=["###", "---"]       # 停止序列
)
```

### JSON 模式

```python
# 要求 JSON 格式响应
response = await generate(
    model="gpt-4-1106-preview",
    messages=[
        MessageBuilder.create_system_message(get_system_prompt("json")),
        MessageBuilder.create_user_message("分析这个文本的情感")
    ],
    response_format={"type": "json_object"}
)

import json
result = json.loads(response.content)
```

### 批量嵌入

```python
from kernel.llm import create_embeddings

texts = [
    "机器学习是人工智能的一个分支",
    "深度学习使用神经网络",
    "自然语言处理处理文本数据"
]

embeddings = await create_embeddings(
    texts=texts,
    model="text-embedding-ada-002",
    provider="openai"
)

# embeddings 是一个列表，每个元素是一个向量
print(f"生成了 {len(embeddings)} 个向量")
print(f"向量维度: {len(embeddings[0])}")
```

## 🔍 调试和日志

LLM 模块集成了 kernel.logger，自动记录关键操作：

```python
# 日志会自动记录：
# - 客户端初始化
# - API 调用（DEBUG 级别）
# - 使用统计（DEBUG 级别）
# - 错误信息（ERROR 级别）

# 查看日志配置
from kernel.logger import get_logger

logger = get_logger("kernel.llm")
logger.setLevel("DEBUG")  # 查看详细日志
```

## 📈 性能优化

### 客户端复用

```python
from kernel.llm import LLMRequestManager

# 创建管理器（会缓存客户端）
manager = LLMRequestManager()

# 多次调用会复用客户端
for i in range(10):
    response = await manager.generate(
        LLMRequest(model="gpt-4", messages=messages)
    )

# 清理
await manager.close()
```

### 并发请求

```python
import asyncio

# 并发调用多个模型
tasks = [
    generate(model="gpt-3.5-turbo", messages=messages, provider="openai"),
    generate(model="gemini-pro", messages=messages, provider="gemini"),
    generate(model="anthropic.claude-v2", messages=messages, provider="bedrock")
]

responses = await asyncio.gather(*tasks)
```

## 🔐 安全最佳实践

1. **API 密钥管理**
```python
import os

# 从环境变量读取
api_key = os.getenv("OPENAI_API_KEY")

client = OpenAIClient(api_key=api_key)
```

2. **输入验证**
```python
from kernel.llm import LLMRequest

request = LLMRequest(
    model="gpt-4",
    messages=messages,
    max_tokens=1000  # 限制输出长度
)

# 验证请求
request.validate()  # 会抛出 ValidationError 如果无效
```

3. **内容过滤**
```python
# 实现自定义内容过滤
def filter_content(text: str) -> bool:
    # 检查敏感内容
    return True

if filter_content(user_input):
    response = await generate(model="gpt-4", messages=messages)
```

## 📖 更多资源

- [API 完整参考](API_REFERENCE.md)
- [最佳实践详解](BEST_PRACTICES.md)
- [提示词工程](PROMPT_GUIDE.md)
- [工具调用详解](TOOL_CALLING_GUIDE.md)
- [故障排除](TROUBLESHOOTING.md)

## 🤝 贡献

欢迎贡献代码、报告问题或提出改进建议！

## 📄 许可

本模块遵循 MoFox 项目的许可协议。
