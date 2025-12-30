# Model Configuration Guide

This document will guide you on how to configure the `model_config.toml` file, which is used to configure various AI models and API service providers for MoFox_Bot.

## Configuration File Structure

The configuration file mainly contains the following sections:
- Version information
- API service provider configuration
- Model configuration
- Model task configuration

## 1. Version Information

```toml
[inner]
version = "1.1.1"
```

Used to identify the configuration file version, following semantic versioning rules.

## 2. API Service Provider Configuration

### 2.1 Basic Configuration

Use `[[api_providers]]` array to configure multiple API service providers:

```toml
[[api_providers]]
name = "DeepSeek"                       # Provider name (custom)
base_url = "https://api.deepseek.cn/v1" # API service base URL
api_key = "your-api-key-here"           # API key
client_type = "openai"                  # Client type
max_retry = 2                           # Maximum retry times
timeout = 30                            # Timeout (seconds)
retry_interval = 10                     # Retry interval (seconds)
```

### 2.2 Configuration Parameters

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| `name` | ✅ | Service provider name, referenced in model configuration | - |
| `base_url` | ✅ | API service base URL | - |
| `api_key` | ✅ | API key, replace with actual key | - |
| `client_type` | ❌ | Client type: `openai`, `gemini` or `aiohttp_gemini` | `openai` |
| `max_retry` | ❌ | Maximum retry times on API call failure | 2 |
| `timeout` | ❌ | API request timeout (seconds) | 30 |
| `retry_interval` | ❌ | Retry interval time (seconds) | 10 |

### 2.3 Supported Provider Examples

#### DeepSeek
```toml
[[api_providers]]
name = "DeepSeek"
base_url = "https://api.deepseek.cn/v1"
api_key = "your-deepseek-api-key"
client_type = "openai"
```

#### SiliconFlow
```toml
[[api_providers]]
name = "SiliconFlow"
base_url = "https://api.siliconflow.cn/v1"
api_key = "your-siliconflow-api-key"
client_type = "openai"
```

#### Google Gemini
```toml
[[api_providers]]
name = "Google"
base_url = "https://generativelanguage.googleapis.com/v1beta"
api_key = "your-google-api-key"
client_type = "aiohttp_gemini"  # Note: Gemini requires special client
```

## 3. Model Configuration

### 3.1 Basic Model Configuration

Use `[[models]]` array to configure multiple models:

```toml
[[models]]
model_identifier = "deepseek-chat"  # Model identifier in API provider
name = "deepseek-v3"               # Custom model name
api_provider = "DeepSeek"          # Referenced API provider name
price_in = 2.0                     # Input price (CNY/M tokens)
price_out = 8.0                    # Output price (CNY/M tokens)
```

### 3.2 Advanced Model Configuration

#### Force Streaming Output
For models that don't support non-streaming output:
```toml
[[models]]
model_identifier = "some-model"
name = "custom-name"
api_provider = "Provider"
force_stream_mode = true  # Enable forced streaming output
```

#### Extra Parameters Configuration `extra_params`
```toml
[[models]]
model_identifier = "Qwen/Qwen3-8B"
name = "qwen3-8b"
api_provider = "SiliconFlow"
[models.extra_params]
enable_thinking = false # Disable thinking
```

The `extra_params` can contain any additional parameters supported by the API provider. **Refer to the corresponding API documentation when configuring.**

Please note that `extra_params` configuration should form a valid TOML dictionary structure, with specific content depending on the API provider's requirements.

### 3.3 Configuration Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `model_identifier` | ✅ | Model identifier provided by API provider |
| `name` | ✅ | Custom model name, used in task configuration |
| `api_provider` | ✅ | Corresponding API provider name |
| `price_in` | ❌ | Input price (CNY/M tokens), for cost accounting |
| `price_out` | ❌ | Output price (CNY/M tokens), for cost accounting |
| `force_stream_mode` | ❌ | Whether to force streaming output |
| `extra_params` | ❌ | Additional model parameter configuration |
| `anti_truncation` | ❌ | Whether to enable anti-truncation feature |

## 4. Model Task Configuration

### utils - Utility Model
Used for emoji, naming, relationship modules and other core functions:
```toml
[model_task_config.utils]
model_list = ["siliconflow-deepseek-v3"]
temperature = 0.2
max_tokens = 800
```

### utils_small - Small Utility Model
For high-frequency scenarios, recommend using fast small models:
```toml
[model_task_config.utils_small]
model_list = ["qwen3-8b"]
temperature = 0.7
max_tokens = 800
```

### replyer_1 - Primary Reply Model
Primary reply model, also used for expression and expression learning:
```toml
[model_task_config.replyer_1]
model_list = ["siliconflow-deepseek-v3"]
temperature = 0.2
max_tokens = 800
```

### replyer_2 - Secondary Reply Model
```toml
[model_task_config.replyer_2]
model_list = ["siliconflow-deepseek-v3"]
temperature = 0.7
max_tokens = 800
```

### planner - Decision Model
Responsible for deciding what MoFox_Bot should do:
```toml
[model_task_config.planner]
model_list = ["siliconflow-deepseek-v3"]
temperature = 0.3
max_tokens = 800
```

### emotion - Emotion Model
Responsible for MoFox_Bot's mood changes:
```toml
[model_task_config.emotion]
model_list = ["siliconflow-deepseek-v3"]
temperature = 0.3
max_tokens = 800
```

### memory - Memory Model
```toml
[model_task_config.memory]
model_list = ["qwen3-30b"]
temperature = 0.7
max_tokens = 800
```

### vlm - Vision Language Model
For image recognition:
```toml
[model_task_config.vlm]
model_list = ["qwen2.5-vl-72b"]
max_tokens = 800
```

### voice - Speech Recognition Model
```toml
[model_task_config.voice]
model_list = ["sensevoice-small"]
```

### embedding - Embedding Model
```toml
[model_task_config.embedding]
model_list = ["bge-m3"]
```

### tool_use - Tool Call Model
Must use models that support tool calling:
```toml
[model_task_config.tool_use]
model_list = ["qwen3-14b"]
temperature = 0.7
max_tokens = 800
```

### lpmm_entity_extract - Entity Extraction Model
```toml
[model_task_config.lpmm_entity_extract]
model_list = ["siliconflow-deepseek-v3"]
temperature = 0.2
max_tokens = 800
```

### lpmm_rdf_build - RDF Build Model
```toml
[model_task_config.lpmm_rdf_build]
model_list = ["siliconflow-deepseek-v3"]
temperature = 0.2
max_tokens = 800
```

### lpmm_qa - Q&A Model
```toml
[model_task_config.lpmm_qa]
model_list = ["deepseek-r1-distill-qwen-32b"]
temperature = 0.7
max_tokens = 800
```

### schedule_generator - Schedule Generation Model
```toml
[model_task_config.schedule_generator]
model_list = ["deepseek-v3"]
temperature = 0.5
max_tokens = 1024
```

### monthly_plan_generator - Monthly Plan Generation Model
```toml
[model_task_config.monthly_plan_generator]
model_list = ["deepseek-v3"]
temperature = 0.7
max_tokens = 1024
```

### emoji_vlm - Emoji VLM Model
```toml
[model_task_config.emoji_vlm]
model_list = ["qwen-vl-max"]
max_tokens = 800
```

### anti_injection - Anti-injection Model
```toml
[model_task_config.anti_injection]
model_list = ["deepseek-v3"]
temperature = 0.1
max_tokens = 512
```

### utils_video - Video Analysis Model
```toml
[model_task_config.utils_video]
model_list = ["qwen-vl-max"]
max_tokens = 800
```

## 5. Configuration Recommendations

### 5.1 Temperature Parameter Selection

| Task Type | Recommended Temp | Description |
|-----------|------------------|-------------|
| Precision tasks (tool calling, entity extraction) | 0.1-0.3 | Need accuracy and consistency |
| Creative tasks (conversation, memory) | 0.5-0.8 | Need diversity and creativity |
| Balanced tasks (decision, emotion) | 0.3-0.5 | Balance accuracy and flexibility |

### 5.2 Model Selection Recommendations

| Task Type | Recommended Model Type | Examples |
|-----------|------------------------|----------|
| High-precision tasks | Large models | DeepSeek-V3, GPT-5, Gemini-2.5-Pro |
| High-frequency tasks | Small models | Qwen3-8B |
| Multimodal tasks | Specialized models | Qwen2.5-VL, SenseVoice |
| Tool calling | Models supporting Function Call | Qwen3-14B |

### 5.3 Cost Optimization

1. **Tiered usage**: Use high-quality models for core functions, economical models for auxiliary functions
2. **Reasonable max_tokens configuration**: Set based on actual needs to avoid waste

## 6. Configuration Validation

### 6.1 Required Checks

1. ✅ Is the API key correctly configured?
2. ✅ Does the model identifier match what the API provider provides?
3. ✅ Are model names referenced in task configuration defined in models section?
4. ✅ Is a dedicated model configured for multimodal tasks?

### 6.2 Test Configuration

Recommended before official use:
1. Validate configuration with small test data
2. Check if API calls work normally
3. Confirm cost accounting functionality works

## 7. Troubleshooting

### 7.1 Common Issues

**Issue 1**: API call failed
- Check if API key is correct
- Confirm base_url is accessible
- Verify model identifier is correct

**Issue 2**: Model not found
- Confirm model name is consistent between task configuration and model definition
- Check if api_provider name matches

**Issue 3**: Abnormal response
- Check if temperature parameter is reasonable (between 0-1)
- Confirm max_tokens setting is appropriate
- Verify model supports required features

### 7.2 View Logs

Check log files in `logs/` directory for relevant error messages.

## 8. Updates and Maintenance

1. **Regular updates**: Monitor model updates from API providers and adjust configuration timely
2. **Performance monitoring**: Monitor model call costs and performance
3. **Backup configuration**: Backup current configuration file before making changes

