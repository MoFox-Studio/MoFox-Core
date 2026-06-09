"""SiliconFlow IndexTTS 语音合成插件"""

from src.plugin_system.base.plugin_metadata import PluginMetadata

from .plugin import SiliconFlowIndexTTSPlugin

__plugin_meta__ = PluginMetadata(
    name="SiliconFlow IndexTTS",
    description="基于SiliconFlow API的IndexTTS语音合成插件，支持高质量的零样本语音克隆和情感控制",
    usage="使用 /tts 命令进行语音合成",
    version="2.0.0",
    author="MoFox Studio",
    keywords=["tts", "voice", "audio", "speech", "indextts", "voice-cloning", "siliconflow"],
    categories=["Audio Tools", "Voice Assistant", "AI Tools"],
    extra={"is_built_in": True},
)
