# GPT-SoVITS & Qwen Omni 语音合成插件（多引擎多风格版）

## 简介
本插件支持 GPT-SoVITS 和 Qwen Omni 双引擎，实现文本转语音（TTS）功能，支持多种语音风格和多语言（中文/英文/日文/粤语/韩文）。适用于需要将文本内容以语音形式发送的场景，如语音回复、朗读长文本、增强表达效果等。
(此版本适用于麦麦09x版)
## 功能特性
- 支持多种语音风格（如默认、温柔等，可自定义扩展）
- 支持多语言自动检测与指定（zh/en/ja）
- 可配置参考音频、参考文本、模型权重等参数
- 兼容多种聊天平台（如 QQ、Telegram 等）
- 关键词激活，灵活触发

## 安装与配置
**拷贝插件文件夹**到你的插件目录下（如 `plugins/tts_voice_plugin/`）。


## 使用方法
- 在聊天中输入关键词（如“语音”、“说话”、“朗读”、“voice”、“tts”等）即可触发语音合成功能
- 可通过参数指定风格、语言、参考音频等
- 支持自动检测文本语言

## 主要参数说明
| 参数名           | 说明                       |
|------------------|----------------------------|
| text             | 要转换为语音的文本内容     |
| text_language    | 文本语言（zh/en/ja）       |
| refer_wav_path   | 参考音频路径（可选）       |
| prompt_text      | 参考音频文本（可选）       |
| prompt_language  | 参考音频语言（可选）       |
| voice_style      | 语音风格（如 default/gentle）|

## 扩展风格
如需添加新风格，在 `config.toml` 的 `[tts_styles]` 下增加分组即可。例如：

```toml
[tts_styles."活泼"]
refer_wav = "path/to/lively.wav"
prompt_text = "活泼的语气"
prompt_language = "zh"
gpt_weights = ""
sovits_weights = ""
```

## 依赖
- Python 3.7+
- aiohttp
- GPT-SoVITS 服务端

## 作者
- 插件作者：靓仔
- 插件版本：1.0.0

## License
AGPL-3.0
