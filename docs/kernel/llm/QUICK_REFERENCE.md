# LLM 模块快速参考

常用功能速查表。

## 基础生成

```python
from kernel.llm import generate

# 简单生成
response = await generate(
    model="gpt-4",
    messages=[{"role": "user", "content": "你好"}],
    provider="openai"
)
print(response.content)
```

## 流式生成

```python
from kernel.llm import stream_generate

async for chunk in stream_generate(
    model="gpt-4",
    messages=[{"role": "user", "content": "讲个故事"}],
    provider="openai"
):
    print(chunk.content, end="", flush=True)
```

## 消息构建

```python
from kernel.llm import MessageBuilder

# 系统消息
system = MessageBuilder.create_system_message("你是助手")

# 用户消息
user = MessageBuilder.create_user_message("问题")

# 助手消息
assistant = MessageBuilder.create_assistant_message("回答")

# 多模态消息
multimodal = MessageBuilder.create_multimodal_message(
    text="这是什么？",
    image_paths=["image.jpg"]
)

messages = [system, user]
```

## 工具调用

```python
from kernel.llm import generate_with_tools, ToolBuilder

# 定义工具
tool = ToolBuilder.create_tool(
    name="get_weather",
    description="获取天气",
    parameters=[
        ToolBuilder.create_parameter(
            "city", "string", "城市名", required=True
        )
    ]
)

# 使用工具
response = await generate_with_tools(
    model="gpt-4",
    messages=[{"role": "user", "content": "北京天气"}],
    tools=[tool],
    provider="openai"
)

# 处理工具调用
if response.tool_calls:
    for call in response.tool_calls:
        name = call["function"]["name"]
        args = call["function"]["arguments"]
```

## 提示词

```python
from kernel.llm import get_system_prompt, PromptTemplates

# 预设提示词
system = get_system_prompt("coding")  # 编程助手
# 可用: coding, translation, data_analysis, 
#      creative, education, customer_service

# 问答模板
prompt = PromptTemplates.QA_TEMPLATE.substitute(
    context="上下文",
    question="问题"
)

# 总结模板
prompt = PromptTemplates.SUMMARY_TEMPLATE.substitute(
    content="内容",
    max_length=200
)
```

## 客户端注册

```python
from kernel.llm import register_client, OpenAIClient

# OpenAI
client = OpenAIClient(api_key="sk-...")
register_client("openai", client)

# 兼容 API
client = OpenAIClient(
    api_key="key",
    base_url="https://custom-api.com/v1"
)
register_client("custom", client)

# Gemini
from kernel.llm import GeminiClient
client = GeminiClient(api_key="...")
register_client("gemini", client)

# Bedrock
from kernel.llm import BedrockClient
client = BedrockClient(region_name="us-east-1")
register_client("bedrock", client)
```

## 错误处理

```python
from kernel.llm import (
    LLMError,
    AuthenticationError,
    RateLimitError,
    ContextLengthExceededError
)

try:
    response = await generate(model="gpt-4", messages=messages)
except AuthenticationError:
    print("认证失败")
except RateLimitError:
    print("速率限制")
except ContextLengthExceededError:
    print("上下文过长")
except LLMError as e:
    print(f"错误: {e}")
```

## 生成参数

```python
response = await generate(
    model="gpt-4",
    messages=messages,
    provider="openai",
    temperature=0.7,        # 0-2, 创造性
    max_tokens=1000,        # 最大输出长度
    top_p=0.9,              # 核采样
    frequency_penalty=0.5,  # 频率惩罚
    presence_penalty=0.5,   # 存在惩罚
    stop=["###", "END"]     # 停止序列
)
```

## 响应解析

```python
from kernel.llm import ResponseParser

# 提取内容
content = ResponseParser.extract_content(response)

# 提取工具调用
tool_calls = ResponseParser.extract_tool_calls(response)

# 提取使用统计
usage = ResponseParser.extract_usage(response)

# 检查是否完成
is_complete = ResponseParser.is_complete(response)
```

## 文本嵌入

```python
from kernel.llm import create_embeddings

embeddings = await create_embeddings(
    texts=["文本1", "文本2", "文本3"],
    model="text-embedding-ada-002",
    provider="openai"
)

# embeddings: List[List[float]]
```

## 图像处理

```python
from kernel.llm import (
    image_to_base64,
    create_data_url,
    compress_image
)

# 转 base64
base64_str = image_to_base64("image.jpg", compress=True)

# 创建 data URL
data_url = create_data_url("image.jpg")

# 压缩图像
compressed = compress_image(
    "image.jpg",
    max_size=(1024, 1024),
    quality=85
)
```

## Token 估算

```python
from kernel.llm import estimate_tokens, truncate_text

# 估算 tokens
count = estimate_tokens("这是一段文本", model="gpt-4")

# 截断文本
truncated = truncate_text(
    long_text,
    max_tokens=1000,
    model="gpt-4"
)
```

## 批量处理

```python
import asyncio

# 并发生成
tasks = [
    generate(model="gpt-4", messages=[msg])
    for msg in message_list
]
responses = await asyncio.gather(*tasks)

# 限制并发数
from asyncio import Semaphore

semaphore = Semaphore(5)  # 最多5个并发

async def generate_limited(msg):
    async with semaphore:
        return await generate(model="gpt-4", messages=[msg])

tasks = [generate_limited(msg) for msg in message_list]
responses = await asyncio.gather(*tasks)
```

## JSON 模式

```python
# GPT-4 Turbo 支持
response = await generate(
    model="gpt-4-1106-preview",
    messages=[
        {"role": "system", "content": "以JSON格式输出"},
        {"role": "user", "content": "分析情感"}
    ],
    response_format={"type": "json_object"}
)

import json
result = json.loads(response.content)
```

## 完整示例

### 对话机器人

```python
from kernel.llm import generate, MessageBuilder

async def chat_bot(user_input: str, history: list):
    """简单对话机器人"""
    # 构建消息
    messages = [
        MessageBuilder.create_system_message("你是友好的助手")
    ]
    messages.extend(history)
    messages.append(
        MessageBuilder.create_user_message(user_input)
    )
    
    # 生成响应
    response = await generate(
        model="gpt-4",
        messages=messages,
        provider="openai",
        temperature=0.8
    )
    
    # 更新历史
    history.append(
        MessageBuilder.create_user_message(user_input)
    )
    history.append(
        MessageBuilder.create_assistant_message(response.content)
    )
    
    return response.content, history

# 使用
history = []
response, history = await chat_bot("你好", history)
response, history = await chat_bot("天气如何", history)
```

### 工具调用助手

```python
from kernel.llm import generate_with_tools, ToolBuilder
import json

# 定义工具
tools = [
    ToolBuilder.create_tool(
        name="search",
        description="搜索信息",
        parameters=[
            ToolBuilder.create_parameter(
                "query", "string", "搜索查询", required=True
            )
        ]
    ),
    ToolBuilder.create_tool(
        name="calculate",
        description="计算数学表达式",
        parameters=[
            ToolBuilder.create_parameter(
                "expression", "string", "数学表达式", required=True
            )
        ]
    )
]

# 函数映射
FUNCTIONS = {
    "search": lambda query: f"搜索结果: {query}",
    "calculate": lambda expr: eval(expr)
}

async def assistant_with_tools(user_input: str):
    """带工具的助手"""
    messages = [{"role": "user", "content": user_input}]
    
    while True:
        response = await generate_with_tools(
            model="gpt-4",
            messages=messages,
            tools=tools,
            provider="openai"
        )
        
        if not response.tool_calls:
            return response.content
        
        # 执行工具调用
        messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": response.tool_calls
        })
        
        for call in response.tool_calls:
            func_name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            
            result = FUNCTIONS[func_name](**args)
            
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": str(result)
            })
```

### 流式对话

```python
from kernel.llm import stream_generate

async def streaming_chat(user_input: str):
    """流式对话"""
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": user_input}
    ]
    
    full_response = ""
    
    async for chunk in stream_generate(
        model="gpt-4",
        messages=messages,
        provider="openai"
    ):
        content = chunk.content
        full_response += content
        
        # 实时显示
        print(content, end="", flush=True)
        
        # 检查完成
        if chunk.finish_reason:
            print(f"\n[完成: {chunk.finish_reason}]")
            break
    
    return full_response
```

## 常见模型

### OpenAI
- `gpt-4-turbo` - 最新 GPT-4
- `gpt-4` - GPT-4 标准
- `gpt-4-vision-preview` - 支持图像
- `gpt-3.5-turbo` - 快速高效
- `text-embedding-ada-002` - 嵌入

### Gemini
- `gemini-pro` - 文本生成
- `gemini-pro-vision` - 多模态
- `embedding-001` - 嵌入

### Bedrock
- `anthropic.claude-3-opus` - Claude 最强
- `anthropic.claude-3-sonnet` - Claude 平衡
- `meta.llama3-70b` - Llama 3
- `amazon.titan-embed-text-v1` - Titan 嵌入

## 环境变量

```bash
# .env 文件
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

# 自动从环境变量读取
from kernel.llm import OpenAIClient
client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
```

## 更多资源

- [完整文档](README.md)
- [API 参考](API_REFERENCE.md)
- [最佳实践](BEST_PRACTICES.md)
- [提示词指南](PROMPT_GUIDE.md)
- [工具调用指南](TOOL_CALLING_GUIDE.md)
