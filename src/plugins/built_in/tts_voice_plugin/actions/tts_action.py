"""
TTS 语音合成 Action
"""

from pathlib import Path
from typing import ClassVar
import traceback

import toml

from src.chat.utils.self_voice_cache import register_self_voice
from src.common.logger import get_logger
from src.plugin_system.base.base_action import BaseAction, ChatMode

from ..services.manager import get_service

logger = get_logger("tts_voice_plugin.action")


def _get_available_styles() -> list[str]:
    """动态读取配置文件，获取所有可用的TTS风格名称"""
    try:
        # 使用更稳健的路径构建方法
        plugin_file = Path(__file__).resolve()
        # 计算插件根目录: Bot/src/plugins/built_in/tts_voice_plugin/actions -> Bot/src/plugins/built_in/tts_voice_plugin
        plugin_root = plugin_file.parent.parent
        
        # 尝试多种可能的配置路径
        possible_paths = [
            # 标准路径: Bot/config/plugins/tts_voice_plugin/config.toml
            plugin_root.parent.parent.parent.parent / "config" / "plugins" / "tts_voice_plugin" / "config.toml",
            # 备用路径: Bot/config/plugins/tts_voice_plugin/config.toml
            plugin_root.parent.parent.parent / "config" / "plugins" / "tts_voice_plugin" / "config.toml",
            # 开发路径: 直接在插件目录下的 config.toml
            plugin_root / "config.toml"
        ]
        
        config_file = None
        for path in possible_paths:
            if path.is_file():
                config_file = path
                break
        
        if not config_file or not config_file.is_file():
            logger.warning("配置文件不存在，使用默认风格列表")
            return ["default"]

        config = toml.loads(config_file.read_text(encoding="utf-8"))

        # 检查当前使用的 TTS 引擎
        engine = config.get("tts", {}).get("engine", "gpt-sovits")
        if not isinstance(styles_config, list):
        
        if engine == "qwen-omni":
            # Qwen Omni 使用默认风格
            return ["default"]
        else:
            # GPT-SoVITS 从配置中读取风格
            styles_config = config.get("tts_styles", [])
            if not isinstance(styles_config, list):
                logger.warning(f"tts_styles 配置不是列表类型: {type(styles_config)}")
                return ["default"]

        # 使用显式循环和类型检查来提取 style_name，以确保 Pylance 类型检查通过
        style_names: list[str] = []
        for style in styles_config:
            if isinstance(style, dict):
                name = style.get("style_name")
                # 确保 name 是一个非空字符串
                if isinstance(name, str) and name:
                    style_names.append(name)

        return style_names if style_names else ["default"]
    except Exception as e:
        logger.error(f"动态加载TTS风格列表时出错: {e}")
        return ["default"]  # 出现任何错误都回退


# 在类定义之前执行函数，获取风格列表
AVAILABLE_STYLES = _get_available_styles()
STYLE_OPTIONS_DESC = ", ".join(f"'{s}'" for s in AVAILABLE_STYLES)


class TTSVoiceAction(BaseAction):
    """
    通过关键词或规划器自动触发 TTS 语音合成
    """

    action_name = "tts_voice_action"
    action_description = "将你生成好的文本转换为语音并发送。你必须提供要转换的文本。"

    mode_enable = ChatMode.ALL
    parallel_action = False

    action_parameters: ClassVar[dict] = {
        "tts_voice_text": {
            "type": "string",
            "description": "需要转换为语音并发送的完整、自然、适合口语的文本内容。",
            "required": True
        },
        "voice_style": {
            "type": "string",
            "description": f"语音的风格。可用选项: [{STYLE_OPTIONS_DESC}]。请根据对话的情感和上下文选择一个最合适的风格。如果未提供，将使用默认风格。",
            "required": False
        },
        "text_language": {
            "type": "string",
            "description": (
                "指定用于合成的语言模式，请务必根据文本内容选择最精确、范围最小的选项以获得最佳效果。"
                "可用选项说明：\n"
                "- 'zh': 中文与英文混合 (最优选)\n"
                "- 'ja': 日文与英文混合 (最优选)\n"
                "- 'yue': 粤语与英文混合 (最优选)\n"
                "- 'ko': 韩文与英文混合 (最优选)\n"
                "- 'en': 纯英文\n"
                "- 'all_zh': 纯中文\n"
                "- 'all_ja': 纯日文\n"
                "- 'all_yue': 纯粤语\n"
                "- 'all_ko': 纯韩文\n"
                "- 'auto': 多语种混合自动识别 (备用选项，当前两种语言时优先使用上面的精确选项)\n"
                "- 'auto_yue': 多语种混合自动识别（包含粤语）(备用选项)"
            ),
            "required": False
        }
    }

    action_require: ClassVar[list] = [
        "在调用此动作时，你必须在 'text' 参数中提供要合成语音的完整回复内容。这是强制性的。",
        "当用户明确请求使用语音进行回复时，例如‘发个语音听听’、‘用语音说’等。",
        "当对话内容适合用语音表达，例如讲故事、念诗、撒嬌或进行角色扮演时。",
        "在表达特殊情感（如安慰、鼓励、庆祝）的场景下，可以主动使用语音来增强感染力。",
        "不要在日常的、简短的问答或闲聊中频繁使用语音，避免打扰用户。",
        "提供的 'text' 内容必须是纯粹的对话，不能包含任何括号或方括号括起来的动作、表情、或场景描述（例如，不要出现 '(笑)' 或 '[歪头]'）",
        "**重要**：此动作专为语音合成设计，因此 'text' 参数的内容必须是纯净、标准的口语文本。请务必抑制你通常的、富有表现力的文本风格，不要使用任何辅助聊天或增强视觉效果的特殊符号（例如 '♪', '～', '∽', '☆' 等），因为它们无法被正确合成为语音。",
        "【**最终规则**】'text' 参数中，所有句子和停顿【必须】使用且只能使用以下四个标准标点符号：'，' (逗号)、'。' (句号)、'？' (问号)、'！' (叹号)。任何其他符号，特别是 '...'、'～' 以及任何表情符号或装饰性符号，都【严禁】出现，否则将导致语音合成严重失败。"
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 关键配置项现在由 TTSService 管理
        self.tts_service = get_service("tts")

    async def go_activate(self, llm_judge_model=None) -> bool:
        """
        判断此 Action 是否应该被激活。
        满足以下任一条件即可激活：
        1. 25% 的随机概率
        2. 匹配到预设的关键词
        3. LLM 判断当前场景适合发送语音
        """
        # 条件1: 随机激活
        if await self._random_activation(0.25):
            logger.info(f"{self.log_prefix} 随机激活成功 (25%)")
            return True

        # 条件2: 关键词激活
        keywords = [
            "发语音", "语音", "说句话", "用语音说", "听你", "听声音", "想你", "想听声音",
            "讲个话", "说段话", "念一下", "读一下", "用嘴说", "说", "能发语音吗", "亲口"
        ]
        if await self._keyword_match(keywords):
            logger.info(f"{self.log_prefix} 关键词激活成功")
            return True

        # 条件3: LLM 判断激活
        # 注意：这里我们复用 action_require 里的描述，让 LLM 的判断更精准
        if await self._llm_judge_activation(
            llm_judge_model=llm_judge_model
        ):
            logger.info(f"{self.log_prefix} LLM 判断激活成功")
            return True

        logger.debug(f"{self.log_prefix} 所有激活条件均未满足，不激活")
        return False
        except Exception as e:
            logger.error(f"{self.log_prefix} 激活判断失败: {e}")
            return False

    async def execute(self) -> tuple[bool, str]:
        """
        执行 Action 的核心逻辑
        """
        try:
            if not self.tts_service:
                logger.error(f"{self.log_prefix} TTSService 未注册或初始化失败，静默处理。")
                return False, "TTSService 未注册或初始化失败"

            initial_text = self.action_data.get("tts_voice_text", "").strip()
            voice_style = self.action_data.get("voice_style", "default")
            # 新增：从决策模型获取指定的语言模式
            text_language = self.action_data.get("text_language") # 如果模型没给，就是 None
            logger.info(f"{self.log_prefix} 接收到规划器初步文本: '{initial_text[:70]}...', 指定风格: {voice_style}, 指定语言: {text_language}")

            # 1. 使用规划器提供的文本
            text = initial_text
            if not text:
                logger.warning(f"{self.log_prefix} 规划器提供的文本为空，静默处理。")
                return False, "规划器提供的文本为空"

            # 2. 调用 TTSService 生成语音
            logger.info(f"{self.log_prefix} 使用最终文本进行语音合成: '{text[:70]}...'")
            audio_b64 = await self.tts_service.generate_voice(
                text=text,
                style_hint=voice_style,
                language_hint=text_language  # 新增：将决策模型指定的语言传递给服务
            )

            if audio_b64:
                # 在发送语音前，将文本注册到缓存中
                register_self_voice(audio_b64, text)
                await self.send_custom(message_type="voice", content=audio_b64)
                logger.info(f"{self.log_prefix} GPT-SoVITS语音发送成功")
                await self.store_action_info(
                    action_prompt_display=f"将文本转换为语音并发送 (风格:{voice_style})",
                    action_done=True
                )
                return True, f"成功生成并发送语音，文本长度: {len(text)}字符"
            else:
                logger.error(f"{self.log_prefix} TTS服务未能返回音频数据，静默处理。")
                await self.store_action_info(
                    action_prompt_display="语音合成失败: TTS服务未能返回音频数据",
                    action_done=False
                )
                return False, "语音合成失败"

        except Exception as e:
            logger.error(f"{self.log_prefix} 语音合成过程中发生未知错误: {e!s}")
            await self.store_action_info(
                action_prompt_display=f"语音合成失败: {e!s}",
                action_done=False
            )
            return False, f"语音合成出错: {e!s}"

