"""
TTS 语音合成命令
"""
from typing import ClassVar

from src.common.logger import get_logger
from src.plugin_system.base.command_args import CommandArgs
from src.plugin_system.base.plus_command import PlusCommand
from src.plugin_system.utils.permission_decorators import require_permission

from ..services.manager import get_service

logger = get_logger("tts_voice_plugin.command")


class TTSVoiceCommand(PlusCommand):
    """
    通过命令手动触发 TTS 语音合成
    """

    command_name: str = "tts"
    command_description: str = "使用GPT-SoVITS或Qwen Omni将文本转换为语音并发送"
    command_aliases: ClassVar[list[str]] = ["语音合成", "说"]
    command_usage = "/tts <要说的文本> [风格]"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @require_permission("plugin.tts_voice_plugin.command.use")
    async def execute(self, args: CommandArgs) -> tuple[bool, str, bool]:
        """
        执行命令的核心逻辑
        """
        all_args = args.get_args()
        if not all_args:
            await self.send_text("请提供要转换为语音的文本内容哦！")
            return False, "缺少文本参数", True

        try:
            tts_service = get_service("tts")
            if not tts_service:
                error_msg = "TTS服务未正确初始化，请检查插件配置（特别是Qwen Omni的API密钥）"
                await self.send_text("❌ " + error_msg)
                return False, error_msg, True

            # 获取可用风格列表 - 兼容不同的 TTS 服务类型
            available_styles = []
            if hasattr(tts_service, 'tts_styles'):
                # GPT-SoVITS 服务
                available_styles = list(tts_service.tts_styles.keys())
            else:
                # Qwen Omni 服务 - 使用默认风格
                available_styles = ["default"]

            text_to_speak = ""
            style_hint = "default"

            # 检查最后一个参数是否是有效的风格
            if len(all_args) > 1 and all_args[-1] in available_styles:
                style_hint = all_args[-1]
                text_to_speak = " ".join(all_args[:-1])
            else:
                # 如果最后一个参数不是风格，则全部都是文本
                text_to_speak = " ".join(all_args)
                # 保持默认风格，让 service 层决定是否需要情感分析
                style_hint = "default"

            if not text_to_speak:
                await self.send_text("请提供要转换为语音的文本内容哦！")
                return False, "文本内容为空", True

            audio_b64 = await tts_service.generate_voice(text_to_speak, style_hint)

            if audio_b64:
                await self.send_type(message_type="voice", content=audio_b64)
                return True, "语音发送成功", True
            else:
                await self.send_text("❌ 语音合成失败，请检查服务状态或配置。")
                return False, "语音合成失败", True

        except Exception as e:
            logger.error(f"执行 /tts 命令时出错: {e}")
            await self.send_text("❌ 语音合成时发生了意想不到的错误，请查看日志。")
            return False, "命令执行异常", True
