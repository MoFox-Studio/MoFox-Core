"""
TTS Voice 插件 - 重构版
"""
import base64
import io
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict, AsyncIterator, Optional
import asyncio

import toml
import numpy as np
import soundfile as sf
from openai import AsyncOpenAI  # Changed to async client

from src.common.logger import get_logger
from src.plugin_system import BasePlugin, ComponentInfo, register_plugin
from src.plugin_system.base.component_types import PermissionNodeField
from src.plugin_system.base.config_types import ConfigField

from .actions.tts_action import TTSVoiceAction
from .commands.tts_command import TTSVoiceCommand
from .services.manager import register_service
from .services.tts_service import TTSService, clean_text_for_tts

logger = get_logger("tts_voice_plugin")



@register_plugin
class TTSVoicePlugin(BasePlugin):
    """
    GPT-SoVITS 和 Qwen Omni 语音合成插件  
    """

    plugin_name = "tts_voice_plugin"
    plugin_description = "基于GPT-SoVITS和Qwen Omni的文本转语音插件"
    plugin_version = "3.2.0"
    plugin_author = "Kilo Code & 靚仔"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies: ClassVar[list[str]] = []


    permission_nodes: ClassVar[list[PermissionNodeField]] = [
        PermissionNodeField(node_name="command.use", description="是否可以使用 /tts 命令"),
    ]

    config_schema: ClassVar[dict] = {}
    config_section_descriptions: ClassVar[dict] = {
        "plugin": "插件基本配置",
        "components": "组件启用控制",
        "tts": "TTS语音合成基础配置",
        "qwen_omni": "Qwen Omni大模型TTS配置（需要API Key）",
        "tts_advanced": "TTS高级参数配置",
        "spatial_effects": "空间音频效果配置"
    }

    def __init__(self, *args, **kwargs):
        try:
            logger.info("TTSVoicePlugin 初始化开始")
            super().__init__(*args, **kwargs)
            self.tts_service = None
            logger.info("TTSVoicePlugin 初始化完成")
        except Exception as e:
            logger.error(f"TTSVoicePlugin 初始化失败: {e}")
            logger.error(traceback.format_exc())
            raise

    def _create_default_config(self, config_file: Path):
        """
        如果配置文件不存在，则创建一个默认的配置文件。
        """
        if config_file.is_file():
            return

        logger.info(f"TTS 配置文件不存在，正在创建默认配置文件于: {config_file}")

        default_config_content = """# 插件基础配置
[plugin]
enable = true
keywords = [
    "发语音", "语音", "说句话", "用语音说", "听你", "听声音", "想听你", "想听声音",
    "讲个话", "说段话", "念一下", "读一下", "用嘴说", "说", "能发语音吗","亲口"
]

# 组件启用控制
[components]
action_enabled = true
command_enabled = true

# TTS 语音合成基础配置
[tts]
server = "http://127.0.0.1:9880"
timeout = 180
max_text_length = 1000

# TTS引擎选择
# 可选值: gpt-sovits, qwen-omni
engine = "qwen-omni"

# Qwen Omni大模型TTS配置（需要API Key）
[qwen_omni]

# Qwen Omni API密钥 (必需)
api_key = "your-api-key-here"

# Qwen Omni API基础URL
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Qwen Omni模型名称
model_name = "qwen-omni-turbo"

# 语音角色
voice_character = "Chelsie"

# 音频格式
media_format = "wav"
# TTS 风格参数配置
# 每个 [[tts_styles]] 代表一个独立的语音风格配置
[[tts_styles]]
# 风格的唯一标识符，必须有一个名为 "default"
style_name = "default"
# 显示名称
name = "默认"
# 参考音频路径
refer_wav_path = "C:/path/to/your/reference.wav"
# 参考音频文本
prompt_text = "这是一个示例文本，请替换为您自己的参考音频文本。"
# 参考音频语言
prompt_language = "zh"
# GPT 模型路径
gpt_weights = "C:/path/to/your/gpt_weights.ckpt"
# SoVITS 模型路径
sovits_weights = "C:/path/to/your/sovits_weights.pth"
# 语速
speed_factor = 1.0

# TTS 高级参数配置
[tts_advanced]
media_type = "wav"
top_k = 9
top_p = 0.8
temperature = 0.8
batch_size = 6
batch_threshold = 0.75
text_split_method = "cut5"
repetition_penalty = 1.4
sample_steps = 150
super_sampling = true

# 空间音效配置
[spatial_effects]

# 是否启用空间音效处理
enabled = false

# 是否启用标准混响效果
reverb_enabled = false

# 混响的房间大小 (建议范围 0.0-1.0)
room_size = 0.2

# 混响的阻尼/高频衰减 (建议范围 0.0-1.0)
damping = 0.6

# 混响的湿声（效果声）比例 (建议范围 0.0-1.0)
wet_level = 0.3

# 混响的干声（原声）比例 (建议范围 0.0-1.0)
dry_level = 0.8

# 混响的立体声宽度 (建议范围 0.0-1.0)
width = 1.0

# 是否启用卷积混响（需要assets/small_room_ir.wav文件）
convolution_enabled = false

# 卷积混响的干湿比 (建议范围 0.0-1.0)
convolution_mix = 0.7
"""

        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(default_config_content.strip())
            logger.info("默认 TTS 配置文件创建成功。")
        except Exception as e:
            logger.error(f"创建默认 TTS 配置文件失败: {e}")

    def _get_config_wrapper(self, key: str, default: Any = None) -> Any:
        """
        配置获取的包装器，用于解决 get_config 无法直接获取动态表（如 tts_styles）和未在 schema 中定义的节的问题。
        由于插件系统的 schema 为空时不会加载未定义的键，这里手动读取配置文件以获取所需配置。
        """
        # 需要手动加载的顶级配置节
        manual_load_keys = ["tts_styles", "spatial_effects", "tts_advanced", "tts", "qwen_omni"]
        top_key = key.split(".")[0]

        if top_key in manual_load_keys:
            try:
                plugin_file = Path(__file__).resolve()
                bot_root = plugin_file.parent.parent.parent.parent.parent
                config_file = bot_root / "config" / "plugins" / self.plugin_name / self.config_file_name

                if not config_file.is_file():
                    logger.error(f"TTS config file not found at robustly constructed path: {config_file}")
                    return default

                full_config = toml.loads(config_file.read_text(encoding="utf-8"))

                # 支持点状路径访问
                value = full_config
                for k in key.split("."):
                    if isinstance(value, dict):
                        value = value.get(k)
                    else:
                        return default

                return value if value is not None else default

            except Exception as e:
                logger.error(f"Failed to manually load '{key}' from config: {e}")
                return default

        return self.get_config(key, default)

    async def on_plugin_loaded(self):
        """
        插件加载完成后的回调，初始化并注册服务。
        """
        try:
            logger.info("开始初始化 TTSVoicePlugin...")
            
            # 确保配置文件存在
            plugin_file = Path(__file__).resolve()
            bot_root = plugin_file.parent.parent.parent.parent.parent
            config_file = bot_root / "config" / "plugins" / self.plugin_name / self.config_file_name
            self._create_default_config(config_file)

            # 获取当前使用的TTS引擎
            engine = self._get_config_wrapper("tts.engine", "gpt-sovits")
            logger.info(f"当前TTS引擎: {engine}")

            if engine == "gpt-sovits":
                # 实例化 GPT-SoVITS 服务
                logger.info("初始化 GPT-SoVITS 服务...")
                self.tts_service = TTSService(self._get_config_wrapper)
                register_service("tts", self.tts_service)
                logger.info("GPT-SoVITS TTS服务已成功初始化并注册。")
            
            elif engine == "qwen-omni":
                # 检查API Key
                api_key = self._get_config_wrapper("qwen_omni.api_key", "")
                if not api_key or api_key == "your-api-key-here":
                    logger.error("Qwen Omni 需要配置有效的 API Key，但当前配置为空或为默认值。")
                    logger.error("TTS 功能将被禁用，请检查插件配置中的 qwen_omni.api_key 设置。")
                    # 创建空服务，明确禁用TTS功能
                    self.tts_service = None
                    # 仍然注册一个空服务，但后续调用会明确失败
                    register_service("tts", None)
                else:
                    # 实例化 Qwen Omni 服务
                    logger.info("初始化 Qwen Omni 服务...")
                    self.tts_service = QwenOmniTTSModel(self._get_config_wrapper)
                    register_service("tts", self.tts_service)
                    logger.info("Qwen Omni TTS服务已成功初始化并注册。")
            else:
                logger.error(f"不支持的 TTS 引擎: {engine}")
                self.tts_service = None
                register_service("tts", None)

            logger.info("TTSVoicePlugin 初始化完成")

        except Exception as e:
            logger.error(f"TTSVoicePlugin 初始化过程中发生错误: {e}")
            logger.error(traceback.format_exc())
            # 不要重新抛出异常，避免影响主程序

    def get_plugin_components(self) -> list[tuple[ComponentInfo, type]]:
        """
        返回插件包含的组件列表。
        """
        components = []
        if self.get_config("components.action_enabled", True):
            components.append((TTSVoiceAction.get_action_info(), TTSVoiceAction))
        if self.get_config("components.command_enabled", True):
            components.append((TTSVoiceCommand.get_plus_command_info(), TTSVoiceCommand))
        return components


@dataclass
class QwenOmniConfig:
    """Qwen Omni TTS 配置"""
    api_key: str
    model_name: str = "qwen-omni-turbo"
    voice_character: str = "Chelsie"
    media_format: str = "wav"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QwenOmniConfig":
        return cls(
            api_key=data.get("api_key", ""),
            model_name=data.get("model_name", "qwen-omni-turbo"),
            voice_character=data.get("voice_character", "Chelsie"),
            media_format=data.get("media_format", "wav"),
            base_url=data.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )


class QwenOmniTTSModel:
    """Qwen Omni TTS 模型"""
    
    def __init__(self, get_config_func):
        """初始化TTS模型
        
        Args:
            get_config_func: 插件配置获取函数
        """
        self.get_config = get_config_func
        self.config = self._load_config()
        self.max_text_length = self.get_config("tts.max_text_length", 500)  # 获取最大文本长度

    def _load_config(self) -> QwenOmniConfig:
        """从插件配置加载Qwen Omni配置"""
        try:
            config_data = {
                "api_key": self.get_config("qwen_omni.api_key", ""),
                "model_name": self.get_config("qwen_omni.model_name", "qwen-omni-turbo"),
                "voice_character": self.get_config("qwen_omni.voice_character", "Chelsie"),
                "media_format": self.get_config("qwen_omni.media_format", "wav"),
                "base_url": self.get_config("qwen_omni.base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            }
            return QwenOmniConfig.from_dict(config_data)
        except Exception as e:
            logger.error(f"加载 Qwen Omni 配置失败: {e}")
            return QwenOmniConfig(api_key="")

    async def tts(self, text: str, **kwargs) -> Optional[bytes]:
        """文本转语音 - 将PCM数据转换为WAV文件"""
        try:
            # 使用列表收集数据块，避免O(n²)性能问题
            chunks = []
            
            async for chunk in self._tts_stream(text, **kwargs):
                chunks.append(chunk)
                
            if not chunks:
                logger.error("没有收到任何音频数据")
                return None
                
            # 使用join连接所有数据块
            audio_base64_string = "".join(chunks)
            
            # 解码base64得到PCM数据
            pcm_data = base64.b64decode(audio_base64_string)
            
            # 将PCM数据转换为WAV文件
            wav_bytes = self._pcm_to_wav_soundfile(pcm_data)
            
            if wav_bytes is None:
                logger.error("PCM到WAV转换失败，无法生成有效的WAV音频")
                return None
                
            return wav_bytes
            
        except Exception as e:
            logger.error(f"Qwen Omni TTS 失败: {e}")
            logger.error(traceback.format_exc())
            return None

    def _pcm_to_wav_soundfile(self, pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> Optional[bytes]:
        """使用soundfile将PCM数据转换为WAV文件"""
        try:
            # 将PCM字节数据转换为numpy数组
            # 假设是16位有符号整数（这是最常见的PCM格式）
            audio_array = np.frombuffer(pcm_data, dtype=np.int16)
            
            # 创建字节流
            wav_io = io.BytesIO()
            
            # 使用soundfile写入WAV格式
            sf.write(wav_io, audio_array, sample_rate, format='WAV', subtype='PCM_16')
            
            # 获取WAV文件数据
            wav_bytes = wav_io.getvalue()
            wav_io.close()
            
            logger.info(f"使用soundfile转换PCM到WAV: {len(pcm_data)}字节PCM -> {len(wav_bytes)}字节WAV")
            return wav_bytes
            
        except Exception as e:
            logger.error(f"使用soundfile转换PCM到WAV失败: {e}")
            logger.error(traceback.format_exc())
            return None  # 返回None而不是原始PCM数据
            
    async def _tts_stream(self, text: str, **kwargs) -> AsyncIterator[str]:
        """使用大模型流式生成音频数据（异步版本）"""
        try:
            logger.info(f"开始调用Qwen Omni API生成音频，文本: {text[:30]}{'...' if len(text) > 30 else ''}")
            
            # 使用公共清理函数清理文本
            safe_text = clean_text_for_tts(text, self.max_text_length)
            
            # 使用更安全的提示词格式，复用清理后的文本
            prompt = f"""请用自然流畅的语音朗读以下文本，不要添加任何解释、前缀或后缀：{safe_text}请确保只输出指定的文本内容，不要添加任何其他内容。"""
            
            logger.info(f"使用安全的提示词格式，清理后文本长度: {len(safe_text)}")
            
            # 使用异步OpenAI客户端
            client = AsyncOpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
            
            # 使用异步流式调用
            completion = await client.chat.completions.create(
                model=self.config.model_name,
                messages=[{"role": "user", "content": prompt}],
                modalities=["text", "audio"],
                audio={
                    "voice": self.config.voice_character,
                    "format": self.config.media_format,
                },
                stream=True,
                stream_options={"include_usage": True},
            )
        
            audio_data_received = False
            total_audio_length = 0
            
            # 异步迭代流式响应
            async for chunk in completion:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                
                    # 检查音频数据
                    if hasattr(delta, "audio") and delta.audio:
                        audio_dict = delta.audio
                        if isinstance(audio_dict, dict) and 'data' in audio_dict and audio_dict['data']:
                            audio_data = audio_dict['data']
                            total_audio_length += len(audio_data)
                            audio_data_received = True
                            yield audio_data
                        else:
                            logger.debug(f"音频字典内容: {audio_dict}")
                
                    # 记录文本内容用于调试
                    if hasattr(delta, "content") and delta.content:
                        logger.debug(f"收到文本内容: {delta.content}")
                        
                if hasattr(chunk, "usage") and chunk.usage:
                    logger.info(f"本次使用量: {chunk.usage}")
        
            logger.info(f"音频数据接收完成，总base64长度: {total_audio_length}")
            if not audio_data_received:
                logger.warning("API调用成功但没有收到音频数据")
                
        except Exception as e:
            logger.error(f"Qwen Omni API调用失败: {e}")
            logger.error(traceback.format_exc())
            raise

    async def generate_voice(self, text: str, style_hint: str = "default", language_hint: str | None = None) -> str | None:
        """生成语音的兼容接口"""
        try:
            logger.info(f"开始生成语音，文本: {text}")
            audio_data = await self.tts(text)
            if audio_data:
                logger.info(f"语音生成成功，数据长度: {len(audio_data)} 字节")
                # 直接返回base64编码的WAV数据
                return base64.b64encode(audio_data).decode("utf-8")
            else:
                logger.error("语音生成失败，audio_data 为 None")
                return None
        except Exception as e:
            logger.error(f"Qwen Omni 语音生成失败: {e}")
            logger.error(traceback.format_exc())
            return None