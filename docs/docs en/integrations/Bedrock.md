# AWS Bedrock Integration Guide

## Overview

MoFox-Bot has fully integrated AWS Bedrock, supporting unified calling of all Bedrock models using **Converse API**, including:
- Amazon Nova series
- Anthropic Claude 3/3.5
- Meta Llama 2/3
- Mistral AI
- Cohere Command
- AI21 Jamba
- Stability AI SDXL

## Configuration Example

### 1. Configure API Provider

Add Bedrock Provider in `config/model_config.toml`:

```toml
[[api_providers]]
name = "bedrock_us_east"
base_url = ""  # Bedrock doesn't need base_url, leave empty
api_key = "YOUR_AWS_ACCESS_KEY_ID"  # AWS Access Key ID
client_type = "bedrock"
max_retry = 2
timeout = 60
retry_interval = 10

[api_providers.extra_params]
aws_secret_key = "YOUR_AWS_SECRET_ACCESS_KEY"  # AWS Secret Access Key
region = "us-east-1"  # AWS region, default us-east-1
```

### 2. Configure Models

Add model configuration in the same file:

```toml
# Claude 3.5 Sonnet (Bedrock cross-region inference profile)
[[models]]
model_identifier = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
name = "claude-3.5-sonnet-bedrock"
api_provider = "bedrock_us_east"
price_in = 3.0   # Input token price (USD per million)
price_out = 15.0  # Output token price (USD per million)
force_stream_mode = false

# Amazon Nova Pro
[[models]]
model_identifier = "us.amazon.nova-pro-v1:0"
name = "nova-pro"
api_provider = "bedrock_us_east"
price_in = 0.8
price_out = 3.2
force_stream_mode = false

# Llama 3.1 405B
[[models]]
model_identifier = "us.meta.llama3-2-90b-instruct-v1:0"
name = "llama-3.1-405b-bedrock"
api_provider = "bedrock_us_east"
price_in = 0.00532
price_out = 0.016
force_stream_mode = false
```

## Supported Features

### ✅ Implemented

- **Conversation Generation**: Support multi-turn conversation, automatically handle system prompt
- **Streaming Output**: Support streaming responses (`force_stream_mode = true`)
- **Tool Calling**: Full support for Tool Use (function calling)
- **Multimodal**: Support image input (PNG, JPEG, GIF, WebP)
- **Text Embedding**: Support Titan Embeddings and other embedding models
- **Cross-region Inference**: Support Inference Profile (such as `us.anthropic.claude-3-5-sonnet-20240620-v1:0`)

### ⚠️ Limitations

- **Audio Transcription**: Bedrock doesn't directly support speech-to-text, recommend using AWS Transcribe
- **System Role**: Bedrock Converse API handles system messages separately, not included in messages list
- **Tool Role**: Currently doesn't support Tool message feedback (need to simulate with User role)

## Model ID Reference

### Inference Profile (Cross-region)

| Model | Model ID | Region Coverage |
|-------|----------|-----------------|
| Claude 3.5 Sonnet | `us.anthropic.claude-3-5-sonnet-20240620-v1:0` | us-east-1, us-west-2 |
| Claude 3 Opus | `us.anthropic.claude-3-opus-20240229-v1:0` | Multiple regions |
| Nova Pro | `us.amazon.nova-pro-v1:0` | Multiple regions |
| Llama 3.1 405B | `us.meta.llama3-2-90b-instruct-v1:0` | Multiple regions |

### Single-region Base Models

| Model | Model ID | Region |
|-------|----------|--------|
| Claude 3.5 Sonnet | `anthropic.claude-3-5-sonnet-20240620-v1:0` | Single region |
| Nova Micro | `amazon.nova-micro-v1:0` | us-east-1 |
| Nova Lite | `amazon.nova-lite-v1:0` | us-east-1 |
| Titan Embeddings G1 | `amazon.titan-embed-text-v1` | Multiple regions |

Complete model list: https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html

## Usage Examples

### Python Calling Example

```python
from src.llm_models import get_llm_client
from src.llm_models.payload_content.message import MessageBuilder

# Get client
client = get_llm_client("bedrock_us_east")

# Build message
builder = MessageBuilder()
builder.add_user_message("Hello, please introduce AWS Bedrock")

# Call model
response = await client.get_response(
    model_info=get_model_info("claude-3.5-sonnet-bedrock"),
    message_list=[builder.build()],
    max_tokens=1024,
    temperature=0.7
)

print(response.content)
```

### Multimodal Example (Image Input)

```python
import base64

builder = MessageBuilder()
builder.add_text_content("What's in this image?")

# Add image (supports JPEG, PNG, GIF, WebP)
with open("image.jpg", "rb") as f:
    image_data = base64.b64encode(f.read()).decode()
    builder.add_image_content("jpeg", image_data)

builder.set_role_user()

response = await client.get_response(
    model_info=get_model_info("claude-3.5-sonnet-bedrock"),
    message_list=[builder.build()],
    max_tokens=1024
)
```

### Tool Calling Example

```python
from src.llm_models.payload_content.tool_option import ToolOption, ToolParam, ParamType

# Define tool
tool = ToolOption(
    name="get_weather",
    description="Get weather information for specified city",
    params=[
        ToolParam(
            name="city",
            param_type=ParamType.String,
            description="City name",
            required=True
        )
    ]
)

# Call
response = await client.get_response(
    model_info=get_model_info("claude-3.5-sonnet-bedrock"),
    message_list=messages,
    tool_options=[tool],
    max_tokens=1024
)

# Check tool calls
if response.tool_calls:
    for call in response.tool_calls:
        print(f"Tool: {call.name}, Arguments: {call.arguments}")
```

## Permission Configuration

### IAM Policy Example

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/*",
        "arn:aws:bedrock:*:*:inference-profile/*"
      ]
    }
  ]
}
```

## Cost Optimization Recommendations

1. **Use Inference Profile**: Automatically routes to low-cost regions
2. **Enable Caching**: Bedrock supports prompt caching for repeated system prompts
3. **Batch Processing**: Embedding tasks can be called in batch to reduce request count
4. **Monitor Usage**: `LLMUsageRecorder` automatically records token consumption and costs

## Troubleshooting

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `AccessDeniedException` | Insufficient IAM permissions | Check if IAM policy includes `bedrock:InvokeModel` |
| `ResourceNotFoundException` | Wrong model ID or unsupported region | Verify model_identifier and region configuration |
| `ThrottlingException` | Exceeded quota limit | Increase retry_interval or request quota increase |
| `ValidationException` | Invalid request parameters | Check messages format and max_tokens range |

### Debug Mode

Enable detailed logging:

```python
from src.common.logger import get_logger

logger = get_logger("Bedrock Client")
logger.setLevel("DEBUG")
```

## Dependency Installation

```bash
pip install aioboto3 botocore
```

Or use project's `requirements.txt`.

## References

- [AWS Bedrock Official Documentation](https://docs.aws.amazon.com/bedrock/)
- [Converse API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
- [Supported Models List](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)
- [Pricing Calculator](https://aws.amazon.com/bedrock/pricing/)

---

**Integration Date**: December 6, 2025  
**Status**: ✅ Production Ready
