from src.plugin_system.base.plugin_metadata import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="GPT-SoVITS 语音合成插件",
    description="基于 GPT-SoVITS 和 Qwen Omni 的文本转语音插件，支持多种语言和多风格语音合成。",
    usage=" ",
    version="3.2.0",
    author="靓仔",
    license="AGPL-v3.0",
    repository_url="https://github.com/xuqian13/tts_voice_plugin",
    keywords=["tts", "语音合成", "文本转语音", "gpt-sovits", "qwen-omni", "语音", "朗读", "多风格", "语音播报"],
    categories=["Utility", "Communication", "Accessibility"],
    extra={
        "is_built_in": True,
        "plugin_type": "tools",
    },
    python_dependencies = ["aiohttp", "soundfile", "pedalboard", "openai", "toml", "numpy"]
)
