"""
TTS 核心服务
"""
import asyncio
import base64
import io
import os
import re
import traceback
from collections.abc import Callable
from typing import Any

import aiohttp
import soundfile as sf
from pedalboard import Convolution, Pedalboard, Reverb
from pedalboard.io import AudioFile

from src.common.logger import get_logger

logger = get_logger("tts_voice_plugin.service")


class TTSService:
    """GPT-SoVITS TTS 服务"""

    def __init__(self, get_config_func: Callable[[str, Any], Any]):
        self.get_config = get_config_func
        self.tts_styles: dict[str, Any] = {}
        self.timeout: int = 60
        self.max_text_length: int = 500
        self._load_config()

    def _load_config(self) -> None:
        """加载插件配置"""
        try:
            self.timeout = self.get_config("tts.timeout", 60)
            self.max_text_length = self.get_config("tts.max_text_length", 500)
            self.tts_styles = self._load_tts_styles()

            if self.tts_styles:
                logger.info(f"GPT-SoVITS服务已成功加载风格: {list(self.tts_styles.keys())}")
            else:
                logger.warning("TTS风格配置为空，请检查配置文件")
        except Exception as e:
            logger.error(f"GPT-SoVITS服务配置加载失败: {e}")

    def _load_tts_styles(self) -> dict[str, dict[str, Any]]:
        """加载 TTS 风格配置"""
        styles = {}
        global_server = self.get_config("tts.server", "http://127.0.0.1:9880")
        tts_styles_config = self.get_config("tts_styles", [])

        if not isinstance(tts_styles_config, list):
            logger.error(f"tts_styles 配置不是一个列表, 而是 {type(tts_styles_config)}")
            return styles

        default_cfg = next((s for s in tts_styles_config if s.get("style_name") == "default"), None)
        if not default_cfg:
            logger.error("在 tts_styles 配置中未找到 'default' 风格，这是必需的。")
            return styles

        default_refer_wav = default_cfg.get("refer_wav_path", "")
        default_prompt_text = default_cfg.get("prompt_text", "")
        default_gpt_weights = default_cfg.get("gpt_weights", "")
        default_sovits_weights = default_cfg.get("sovits_weights", "")

        if not default_refer_wav:
            logger.warning("TTS 'default' style is missing 'refer_wav_path'.")

        for style_cfg in tts_styles_config:
            if not isinstance(style_cfg, dict):

                continue

            style_name = style_cfg.get("style_name")
            if not style_name:

                continue

            styles[style_name] = {
                "url": global_server,
                "name": style_cfg.get("name", style_name),
                "refer_wav_path": style_cfg.get("refer_wav_path", default_refer_wav),
                "prompt_text": style_cfg.get("prompt_text", default_prompt_text),
                "prompt_language": style_cfg.get("prompt_language", "zh"),
                "gpt_weights": style_cfg.get("gpt_weights", default_gpt_weights),
                "sovits_weights": style_cfg.get("sovits_weights", default_sovits_weights),
                "speed_factor": style_cfg.get("speed_factor"),
                "text_language": style_cfg.get("text_language", "auto"),  # 新增：读取文本语言模式
            }
        return styles

    def _determine_final_language(self, text: str, mode: str) -> str:
        """根据配置的语言策略和文本内容，决定最终发送给API的语言代码"""
        # 如果策略是具体的语言（如 all_zh, ja），直接使用
        if mode not in ["auto", "auto_yue"]:
            return mode

        # 对于 auto 和 auto_yue 策略，进行内容检测
        # 优先检测粤语
        if mode == "auto_yue":
            cantonese_keywords = ["嘅", "喺", "咗", "唔", "係", "啲", "咩", "乜", "喂"]
            if any(keyword in text for keyword in cantonese_keywords):
                logger.info("在 auto_yue 模式下检测到粤语关键词，最终语言: yue")
                return "yue"

        # 检测日语（简单启发式规则）
        japanese_chars = len(re.findall(r"[\u3040-\u309f\u30a0-\u30ff]", text))
        if japanese_chars > 5 and japanese_chars > len(re.findall(r"[\u4e00-\u9fff]", text)) * 0.5:
            logger.info("检测到日语字符，最终语言: ja")
            return "ja"

        # 默认回退到中文
        logger.info(f"在 {mode} 模式下未检测到特定语言，默认回退到: zh")
        return "zh"
        except Exception as e:
            logger.error(f"语言检测失败: {e}")
            return "zh"

    def _clean_text_for_tts(self, text: str) -> str:
        # 1. 基本清理
        text = re.sub(r"[\(（\[【].*?[\)）\]】]", "", text)
        text = re.sub(r"([，。！？、；：,.!?;:~\-`])\1+", r"\1", text)
        text = re.sub(r"~{2,}|～{2,}", "，", text)
        text = re.sub(r"\.{3,}|…{1,}", "。", text)

        # 2. 词语替换
        replacements = {"www": "哈哈哈", "hhh": "哈哈", "233": "哈哈", "666": "厉害", "88": "拜拜"}
        for old, new in replacements.items():
            text = text.replace(old, new)

        # 3. 移除不必要的字符 (恢复使用更安全的原版正则，避免误删)
        text = re.sub(r"[^\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ffa-zA-Z0-9\s，。！？、；：,.!?;:~～]", "", text)

        # 4. 确保结尾有标点
        if text and not text.endswith(tuple("，。！？、；：,.!?;:")):
            text += "。"

        # 5. 智能截断 (保留改进的截断逻辑)
        if len(text) > self.max_text_length:
            cut_text = text[:self.max_text_length]
            punctuation = "。！？.…"
            last_punc_pos = max(cut_text.rfind(p) for p in punctuation)

            if last_punc_pos != -1:
                text = cut_text[:last_punc_pos + 1]
            else:
                last_comma_pos = max(cut_text.rfind(p) for p in "，、；,;")
                if last_comma_pos != -1:
                    text = cut_text[:last_comma_pos + 1]
                else:
                    text = cut_text

        return text.strip()
        except Exception as e:
            logger.error(f"文本清理失败: {e}")
            return text

    async def _call_tts_api(self, server_config: dict, text: str, text_language: str, **kwargs) -> bytes | None:
        """
        最终修复版：先切换模型，然后仅通过路径发送合成请求。
        """
        ref_wav_path = kwargs.get("refer_wav_path")
        if not ref_wav_path:
            logger.error(f"API 调用失败：缺少 refer_wav_path。当前风格配置: {server_config}")
            return None
        try:
            base_url = server_config["url"].rstrip("/")

            # --- 步骤一：像稳定版一样，先切换模型 ---
            async def switch_model_weights(weights_path: str | None, weight_type: str):
                if not weights_path:

                    return
                api_endpoint = f"/set_{weight_type}_weights"
                switch_url = f"{base_url}{api_endpoint}"
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                        async with session.get(switch_url, params={"weights_path": weights_path}) as resp:
                            if resp.status != 200:
                                error_text = await resp.text()
                                logger.error(f"切换 {weight_type} 模型失败: {resp.status} - {error_text}")
                            else:
                                logger.info(f"成功切换 {weight_type} 模型为: {weights_path}")
                except Exception as e:
                    logger.error(f"请求切换 {weight_type} 模型时发生网络异常: {e}")

            await switch_model_weights(kwargs.get("gpt_weights"), "gpt")
            await switch_model_weights(kwargs.get("sovits_weights"), "sovits")

            # --- 步骤二：构建纯净的、不含Base64的请求数据 ---
            data = {
                "text": text,
                "text_lang": text_language,
                "ref_audio_path": ref_wav_path,
                "prompt_text": kwargs.get("prompt_text", ""),
                "prompt_lang": kwargs.get("prompt_language", "zh"),
                # 在稳定版中，这两个参数是通过API切换的，而不是直接放在请求体里
                # "gpt_model_path": kwargs.get("gpt_weights"),
                # "sovits_model_path": kwargs.get("sovits_weights"),
            }

            # 合并高级配置
            advanced_config = self.get_config("tts_advanced", {})
            if isinstance(advanced_config, dict):
                data.update({k: v for k, v in advanced_config.items() if v is not None})

            # 优先使用风格特定的语速
            if server_config.get("speed_factor") is not None:
                data["speed_factor"] = server_config["speed_factor"]

            # --- 步骤三：发送最终的合成请求 ---
            tts_url = base_url if base_url.endswith("/tts") else f"{base_url}/tts"
            logger.info(f"发送到 GPT-SoVITS API 的数据: {data}")

            async with aiohttp.ClientSession() as session:
                async with session.post(tts_url, json=data, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        error_info = await response.text()
                        logger.error(f"GPT-SoVITS API调用失败: {response.status} - {error_info}")
                        return None
        except asyncio.TimeoutError:
            logger.error("GPT-SoVITS服务请求超时")
            return None
        except Exception as e:
            logger.error(f"GPT-SoVITS API调用异常: {e}")
            return None

    async def _apply_spatial_audio_effect(self, audio_data: bytes) -> bytes | None:
        """根据配置应用空间效果（混响和卷积）"""
        try:
            effects_config = self.get_config("spatial_effects", {})
            if not effects_config.get("enabled", False):

                return audio_data

            # 获取插件目录和IR文件路径
            # 基于 __file__ 构建稳健的、独立于当前工作目录的路径
            plugin_file = os.path.abspath(__file__)
            # services -> tts_voice_plugin -> plugins -> Bot
            bot_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(plugin_file))))
            ir_path = os.path.join(bot_root, "assets", "small_room_ir.wav")

            effects = []

            # 根据配置添加Reverb效果
            if effects_config.get("reverb_enabled", False):
                effects.append(Reverb(
                    room_size=effects_config.get("room_size", 0.15),
                    damping=effects_config.get("damping", 0.5),
                    wet_level=effects_config.get("wet_level", 0.33),
                    dry_level=effects_config.get("dry_level", 0.4),
                    width=effects_config.get("width", 1.0)
                ))

            # 根据配置添加Convolution效果
            if effects_config.get("convolution_enabled", False) and os.path.exists(ir_path):
                effects.append(Convolution(
                    impulse_response_filename=ir_path,
                    mix=effects_config.get("convolution_mix", 0.5)
                ))
            elif effects_config.get("convolution_enabled"):
                logger.warning(f"卷积混响已启用，但IR文件不存在 ({ir_path})，跳过该效果。")

            if not effects:


                return audio_data

            # 将原始音频数据加载到内存中的 AudioFile 对象
            with io.BytesIO(audio_data) as audio_stream:
                with AudioFile(audio_stream, "r") as f:
                    board = Pedalboard(effects)
                    effected = board(f.read(f.frames), f.samplerate)

            # 将处理后的音频数据写回内存中的字节流
            with io.BytesIO() as output_stream:
                # 使用 soundfile 写入，因为它更稳定
                sf.write(output_stream, effected.T, f.samplerate, format="WAV")
                processed_audio_data = output_stream.getvalue()

            logger.info("成功应用空间效果。")
            return processed_audio_data

        except Exception as e:
            logger.error(f"应用空间效果时出错: {e}")
            return audio_data  # 如果出错，返回原始音频

    async def generate_voice(self, text: str, style_hint: str = "default", language_hint: str | None = None) -> str | None:
        self._load_config()

        if not self.tts_styles:
            logger.error("TTS风格配置为空，无法生成语音。")
            return None

        style = style_hint if style_hint in self.tts_styles else "default"
        if style not in self.tts_styles:
            if "default" in self.tts_styles:
                style = "default"
                logger.warning(f"指定风格 '{style_hint}' 不存在，自动回退到: 'default'")
            elif self.tts_styles:
                style = next(iter(self.tts_styles))
                logger.warning(f"指定风格 '{style_hint}' 和 'default' 均不存在，自动回退到第一个可用风格: {style}")
            else:
                logger.error("没有任何可用的TTS风格配置")
                return None

        server_config = self.tts_styles[style]
        clean_text = self._clean_text_for_tts(text)
        if not clean_text:

            return None

        # 语言决策流程：
        # 1. 优先使用决策模型直接指定的 language_hint (最高优先级)
        if language_hint:
            final_language = language_hint
            logger.info(f"使用决策模型指定的语言: {final_language}")
        else:
            # 2. 如果模型未指定，则使用风格配置的 language_policy
            language_policy = server_config.get("text_language", "auto")
            final_language = self._determine_final_language(clean_text, language_policy)
            logger.info(f"决策模型未指定语言，使用策略 '{language_policy}' -> 最终语言: {final_language}")

            logger.info(f"开始GPT-SoVITS语音合成，文本：{clean_text[:50]}..., 风格：{style}, 最终语言: {final_language}")

            audio_data = await self._call_gpt_sovits_api(
            server_config=server_config, text=clean_text, text_language=final_language,
            refer_wav_path=server_config.get("refer_wav_path"),
            prompt_text=server_config.get("prompt_text"),
            prompt_language=server_config.get("prompt_language"),
            gpt_weights=server_config.get("gpt_weights"),
            sovits_weights=server_config.get("sovits_weights"),
        )

        if audio_data:
            # 检查是否启用空间音频效果
            spatial_config = self.get_config("spatial_effects", {})
            if spatial_config.get("enabled", False):
                logger.info("检测到已启用空间音频效果，开始处理...")
                processed_audio = await self._apply_spatial_audio_effect(audio_data)
                if processed_audio:
                    logger.info("空间音频效果应用成功！")
                    audio_data = processed_audio
                else:
                    logger.warning("空间音频效果应用失败，将使用原始音频。")

            return base64.b64encode(audio_data).decode("utf-8")
        return None
