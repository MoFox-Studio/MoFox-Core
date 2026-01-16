# LLM 模块最佳实践

本文档提供 LLM 模块使用的最佳实践和建议。

## 目录

- [客户端管理](#客户端管理)
- [错误处理](#错误处理)
- [性能优化](#性能优化)
- [安全性](#安全性)
- [提示词工程](#提示词工程)
- [工具调用](#工具调用)
- [多模态处理](#多模态处理)
- [监控和日志](#监控和日志)

---

## 客户端管理

### ✅ 推荐做法

#### 1. 使用客户端注册系统

```python
from kernel.llm import register_client, OpenAIClient

# 在应用启动时注册客户端
def initialize_llm():
    openai_client = OpenAIClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=60.0,
        max_retries=3
    )
    register_client("openai", openai_client)
    
    # 注册其他客户端...
```

#### 2. 复用客户端实例

```python
from kernel.llm import get_manager

# 使用全局管理器，自动复用客户端
manager = get_manager()

for prompt in prompts:
    response = await manager.generate(
        LLMRequest(model="gpt-4", messages=[prompt])
    )
```

#### 3. 正确关闭客户端

```python
from kernel.llm import LLMRequestManager

async def main():
    manager = LLMRequestManager()
    try:
        # 使用管理器
        response = await manager.generate(request)
    finally:
        # 确保关闭
        await manager.close()

# 或使用上下文管理器
async def main():
    manager = LLMRequestManager()
    async with manager.with_client("openai") as client:
        response = await client.generate(...)
```

### ❌ 避免

#### 1. 每次请求创建新客户端

```python
# ❌ 不推荐
async def bad_practice():
    for i in range(100):
        client = OpenAIClient(api_key="...")  # 重复创建
        response = await client.generate(...)
```

#### 2. 忘记关闭客户端

```python
# ❌ 可能导致资源泄漏
client = OpenAIClient(api_key="...")
response = await client.generate(...)
# 忘记调用 await client.close()
```

---

## 错误处理

### ✅ 推荐做法

#### 1. 分层错误处理

```python
from kernel.llm import (
    generate,
    AuthenticationError,
    RateLimitError,
    ContextLengthExceededError,
    LLMError
)
import asyncio

async def robust_generate(messages, max_retries=3):
    """带重试的生成函数"""
    for attempt in range(max_retries):
        try:
            return await generate(
                model="gpt-4",
                messages=messages,
                provider="openai"
            )
        
        except AuthenticationError as e:
            # 认证错误不重试
            logger.error(f"认证失败: {e}")
            raise
        
        except RateLimitError as e:
            # 速率限制，使用指数退避
            wait_time = 2 ** attempt
            logger.warning(f"速率限制，等待 {wait_time}s")
            await asyncio.sleep(wait_time)
            continue
        
        except ContextLengthExceededError as e:
            # 上下文过长，尝试截断
            logger.warning("上下文过长，尝试截断")
            messages = truncate_messages(messages)
            continue
        
        except LLMError as e:
            # 其他错误，重试
            if attempt < max_retries - 1:
                logger.warning(f"请求失败，重试 {attempt + 1}/{max_retries}")
                await asyncio.sleep(1)
                continue
            raise
    
    raise LLMError("达到最大重试次数")
```

#### 2. 优雅降级

```python
async def generate_with_fallback(messages):
    """带降级的生成"""
    models = ["gpt-4", "gpt-3.5-turbo", "gemini-pro"]
    
    for model in models:
        try:
            logger.info(f"尝试使用模型: {model}")
            response = await generate(
                model=model,
                messages=messages,
                provider=get_provider(model)
            )
            return response
        except Exception as e:
            logger.warning(f"模型 {model} 失败: {e}")
            continue
    
    raise LLMError("所有模型都失败了")
```

#### 3. 详细日志记录

```python
from kernel.logger import get_logger

logger = get_logger(__name__)

try:
    response = await generate(
        model="gpt-4",
        messages=messages,
        provider="openai"
    )
    logger.info(f"生成成功，使用 {response.usage['total_tokens']} tokens")
except LLMError as e:
    logger.error(f"生成失败: {e}", exc_info=True)
    # 记录详细上下文
    logger.debug(f"消息: {messages}")
    logger.debug(f"模型: gpt-4")
```

---

## 性能优化

### ✅ 推荐做法

#### 1. 并发请求

```python
import asyncio

async def batch_generate(prompts):
    """批量并发生成"""
    tasks = [
        generate(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            provider="openai"
        )
        for prompt in prompts
    ]
    
    # 并发执行
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    results = []
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            logger.error(f"Prompt {i} 失败: {response}")
            results.append(None)
        else:
            results.append(response.content)
    
    return results
```

#### 2. 控制并发数

```python
import asyncio

async def batch_generate_limited(prompts, max_concurrent=5):
    """限制并发数的批量生成"""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def generate_with_semaphore(prompt):
        async with semaphore:
            return await generate(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                provider="openai"
            )
    
    tasks = [generate_with_semaphore(p) for p in prompts]
    return await asyncio.gather(*tasks)
```

#### 3. 使用流式响应减少延迟

```python
from kernel.llm import stream_generate

async def interactive_chat(message):
    """交互式对话，实时显示"""
    async for chunk in stream_generate(
        model="gpt-4",
        messages=[{"role": "user", "content": message}],
        provider="openai"
    ):
        # 实时显示
        print(chunk.content, end="", flush=True)
        
        # 或发送到前端
        await websocket.send(chunk.content)
```

#### 4. 缓存常见请求

```python
from functools import lru_cache
import hashlib
import json

class LLMCache:
    def __init__(self):
        self.cache = {}
    
    def _make_key(self, model, messages, **kwargs):
        """生成缓存键"""
        data = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        return hashlib.md5(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()
    
    async def generate_cached(self, model, messages, **kwargs):
        """带缓存的生成"""
        key = self._make_key(model, messages, **kwargs)
        
        if key in self.cache:
            logger.info("使用缓存结果")
            return self.cache[key]
        
        response = await generate(
            model=model,
            messages=messages,
            **kwargs
        )
        
        self.cache[key] = response
        return response
```

#### 5. 合理设置 max_tokens

```python
from kernel.llm import estimate_tokens

# 估算 prompt tokens
prompt_tokens = sum(
    estimate_tokens(msg["content"]) 
    for msg in messages
)

# 留出足够的输出空间
context_window = 8192  # GPT-4
max_tokens = min(
    4000,  # 期望的最大输出
    context_window - prompt_tokens - 100  # 留100 buffer
)

response = await generate(
    model="gpt-4",
    messages=messages,
    max_tokens=max_tokens
)
```

---

## 安全性

### ✅ 推荐做法

#### 1. 安全存储 API 密钥

```python
import os
from dotenv import load_dotenv

# 使用环境变量
load_dotenv()

client = OpenAIClient(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ❌ 不要硬编码
# client = OpenAIClient(api_key="sk-...")
```

#### 2. 输入验证和清理

```python
from kernel.llm import ValidationError

def validate_user_input(text: str) -> bool:
    """验证用户输入"""
    # 长度检查
    if len(text) > 10000:
        raise ValidationError("输入过长")
    
    # 内容检查
    forbidden_patterns = ["<script>", "DROP TABLE", ...]
    for pattern in forbidden_patterns:
        if pattern.lower() in text.lower():
            raise ValidationError("检测到不安全内容")
    
    return True

# 使用
try:
    validate_user_input(user_message)
    response = await generate(
        model="gpt-4",
        messages=[{"role": "user", "content": user_message}]
    )
except ValidationError as e:
    logger.warning(f"输入验证失败: {e}")
    return "输入不符合要求"
```

#### 3. 内容过滤

```python
class ContentFilter:
    """内容过滤器"""
    
    def filter_output(self, text: str) -> str:
        """过滤输出内容"""
        # PII 检测
        text = self._remove_pii(text)
        
        # 敏感词过滤
        text = self._filter_sensitive_words(text)
        
        return text
    
    def _remove_pii(self, text: str) -> str:
        """移除个人身份信息"""
        import re
        # 移除邮箱
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[邮箱]', text)
        # 移除电话
        text = re.sub(r'\b\d{3}-\d{4}-\d{4}\b', '[电话]', text)
        return text
    
    def _filter_sensitive_words(self, text: str) -> str:
        """过滤敏感词"""
        # 实现敏感词过滤逻辑
        return text

# 使用
filter = ContentFilter()
response = await generate(model="gpt-4", messages=messages)
safe_content = filter.filter_output(response.content)
```

#### 4. 速率限制

```python
from asyncio import Semaphore
from time import time

class RateLimiter:
    """速率限制器"""
    
    def __init__(self, max_requests: int, time_window: float):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
        self.semaphore = Semaphore(max_requests)
    
    async def acquire(self):
        """获取请求许可"""
        async with self.semaphore:
            now = time()
            # 清理过期请求
            self.requests = [t for t in self.requests if now - t < self.time_window]
            
            if len(self.requests) >= self.max_requests:
                wait_time = self.time_window - (now - self.requests[0])
                logger.info(f"速率限制，等待 {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            self.requests.append(now)

# 使用
limiter = RateLimiter(max_requests=10, time_window=60.0)

async def limited_generate(messages):
    await limiter.acquire()
    return await generate(model="gpt-4", messages=messages)
```

#### 5. 用户标识

```python
# 为每个用户设置标识，便于追踪
response = await generate(
    model="gpt-4",
    messages=messages,
    user=f"user_{user_id}"  # 帮助 OpenAI 检测滥用
)
```

---

## 提示词工程

### ✅ 推荐做法

#### 1. 清晰的指令

```python
# ✅ 好的提示词
prompt = """请分析以下文本的情感：

文本：{text}

请按以下格式输出：
- 情感类型：积极/中性/消极
- 置信度：0-100%
- 关键词：列出影响情感的关键词"""

# ❌ 模糊的提示词
prompt = "分析这个"
```

#### 2. 提供上下文

```python
from kernel.llm import MessageBuilder

# 构建完整对话上下文
messages = [
    MessageBuilder.create_system_message(
        "你是一个专业的Python编程助手，擅长解决算法和数据结构问题。"
    ),
    MessageBuilder.create_user_message("什么是二叉树？"),
    MessageBuilder.create_assistant_message(
        "二叉树是一种树形数据结构..."
    ),
    MessageBuilder.create_user_message("如何遍历二叉树？")
]
```

#### 3. 使用示例（Few-shot Learning）

```python
from kernel.llm import PromptBuilder

prompt = PromptBuilder.build_few_shot_prompt(
    task_description="将产品评论分类为积极或消极",
    examples=[
        {
            "input": "这个产品质量很好，非常满意！",
            "output": "积极"
        },
        {
            "input": "完全不值这个价格，太差了",
            "output": "消极"
        },
        {
            "input": "还可以吧，没什么特别的",
            "output": "中性"
        }
    ],
    query="物流速度很快，包装也很好"
)
```

#### 4. 思维链（Chain of Thought）

```python
from kernel.llm import PromptBuilder

prompt = PromptBuilder.build_chain_of_thought_prompt(
    question="""小明有15个苹果，给了小红5个，又买了8个，
    然后吃了3个。小明现在有多少个苹果？""",
    require_reasoning=True
)

# 模型会展示推理过程：
# 1. 开始：15个
# 2. 给了小红：15 - 5 = 10个
# 3. 买了：10 + 8 = 18个
# 4. 吃了：18 - 3 = 15个
# 答案：15个
```

#### 5. 结构化输出

```python
from kernel.llm import PromptBuilder

prompt = PromptBuilder.build_structured_output_prompt(
    task="分析这条产品评论",
    output_format={
        "sentiment": "string (positive/negative/neutral)",
        "score": "number (0-100)",
        "aspects": {
            "quality": "string",
            "price": "string",
            "service": "string"
        },
        "summary": "string"
    },
    example={
        "sentiment": "positive",
        "score": 85,
        "aspects": {
            "quality": "excellent",
            "price": "reasonable",
            "service": "good"
        },
        "summary": "Overall a great product"
    }
)
```

---

## 工具调用

### ✅ 推荐做法

#### 1. 详细的工具描述

```python
from kernel.llm import ToolBuilder

# ✅ 好的工具定义
tool = ToolBuilder.create_tool(
    name="get_weather",
    description="""获取指定城市的当前天气信息。
    
    这个函数会返回：
    - 温度（摄氏度）
    - 天气状况（晴天、多云、雨等）
    - 湿度百分比
    - 风速（km/h）
    
    注意：只支持中国的主要城市。""",
    parameters=[
        ToolBuilder.create_parameter(
            name="city",
            param_type="string",
            description="城市名称，如'北京'、'上海'、'深圳'",
            required=True
        )
    ]
)
```

#### 2. 处理工具调用循环

```python
async def chat_with_tools(user_message, tools, max_iterations=5):
    """支持多轮工具调用的对话"""
    messages = [{"role": "user", "content": user_message}]
    
    for iteration in range(max_iterations):
        response = await generate_with_tools(
            model="gpt-4",
            messages=messages,
            tools=tools,
            provider="openai"
        )
        
        # 检查是否有工具调用
        if not response.tool_calls:
            # 没有工具调用，返回最终答案
            return response.content
        
        # 执行工具调用
        messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": response.tool_calls
        })
        
        for tool_call in response.tool_calls:
            function_name = tool_call["function"]["name"]
            arguments = json.loads(tool_call["function"]["arguments"])
            
            # 执行函数
            result = execute_function(function_name, arguments)
            
            # 添加工具响应
            messages.append(
                MessageBuilder.create_tool_message(
                    tool_call_id=tool_call["id"],
                    content=json.dumps(result)
                )
            )
    
    raise LLMError("达到最大迭代次数")
```

#### 3. 错误处理

```python
def execute_function_safe(function_name: str, arguments: dict) -> dict:
    """安全执行函数"""
    try:
        # 验证函数名
        if function_name not in ALLOWED_FUNCTIONS:
            return {
                "error": f"未知函数: {function_name}",
                "success": False
            }
        
        # 执行函数
        func = ALLOWED_FUNCTIONS[function_name]
        result = func(**arguments)
        
        return {
            "result": result,
            "success": True
        }
    
    except Exception as e:
        logger.error(f"函数执行失败: {e}")
        return {
            "error": str(e),
            "success": False
        }
```

---

## 多模态处理

### ✅ 推荐做法

#### 1. 图像预处理

```python
from kernel.llm import compress_image, create_data_url, MessageBuilder

def create_vision_message(text: str, image_paths: List[str]) -> dict:
    """创建优化的视觉消息"""
    # 压缩大图像
    processed_images = []
    for path in image_paths:
        # 压缩到合适大小
        compressed = compress_image(
            path,
            max_size=(1024, 1024),
            quality=85
        )
        # 转换为 data URL
        data_url = create_data_url(path, compress=True)
        processed_images.append(data_url)
    
    # 创建消息
    return MessageBuilder.create_multimodal_message(
        text=text,
        image_urls=processed_images,
        detail="high"
    )
```

#### 2. 批量图像处理

```python
import asyncio

async def analyze_images_batch(
    images: List[str],
    question: str,
    batch_size: int = 5
):
    """批量分析图像"""
    results = []
    
    for i in range(0, len(images), batch_size):
        batch = images[i:i + batch_size]
        
        tasks = [
            generate(
                model="gpt-4-vision-preview",
                messages=[
                    create_vision_message(question, [img])
                ],
                provider="openai"
            )
            for img in batch
        ]
        
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)
    
    return results
```

---

## 监控和日志

### ✅ 推荐做法

#### 1. 详细的使用统计

```python
class LLMMetrics:
    """LLM 使用指标收集"""
    
    def __init__(self):
        self.total_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.errors = 0
    
    def record_request(self, response: LLMResponse, model: str):
        """记录请求指标"""
        self.total_requests += 1
        self.total_tokens += response.usage.get("total_tokens", 0)
        self.total_cost += self._calculate_cost(
            response.usage,
            model
        )
    
    def record_error(self, error: Exception):
        """记录错误"""
        self.errors += 1
        logger.error(f"LLM 错误: {error}")
    
    def _calculate_cost(self, usage: dict, model: str) -> float:
        """计算成本"""
        # 实现成本计算逻辑
        return 0.0
    
    def get_summary(self) -> dict:
        """获取统计摘要"""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "errors": self.errors,
            "average_tokens_per_request": (
                self.total_tokens / self.total_requests
                if self.total_requests > 0 else 0
            )
        }
```

#### 2. 请求追踪

```python
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar('request_id')

async def generate_with_tracking(messages, **kwargs):
    """带追踪的生成"""
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    
    logger.info(f"[{request_id}] 开始请求")
    logger.debug(f"[{request_id}] 消息: {messages}")
    
    try:
        response = await generate(messages=messages, **kwargs)
        logger.info(
            f"[{request_id}] 请求完成，"
            f"tokens: {response.usage['total_tokens']}"
        )
        return response
    except Exception as e:
        logger.error(f"[{request_id}] 请求失败: {e}")
        raise
```

---

## 总结

遵循这些最佳实践可以帮助你：

1. **提高性能** - 通过并发、缓存和合理的资源管理
2. **增强安全性** - 通过输入验证、内容过滤和安全的密钥管理
3. **提升可靠性** - 通过错误处理、重试机制和降级策略
4. **改善可维护性** - 通过清晰的代码结构和详细的日志
5. **优化成本** - 通过监控使用情况和优化 token 使用

更多信息请参考：
- [API 参考](API_REFERENCE.md)
- [快速参考](QUICK_REFERENCE.md)
- [提示词指南](PROMPT_GUIDE.md)
