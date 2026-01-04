"""
Kokoro Flow Chatter - 插件注册

注册 Chatter
"""

from typing import Any, ClassVar

from src.common.logger import get_logger
from src.plugin_system import register_plugin
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.config_types import ConfigField

from .chatter import KokoroFlowChatter
from .config import get_config
from .proactive_thinker import start_proactive_thinker, stop_proactive_thinker

logger = get_logger("kfc_plugin")


@register_plugin
class KokoroFlowChatterPlugin(BasePlugin):
    """
    Kokoro Flow Chatter 插件

    专为私聊设计的增强 Chatter：
    - 线性叙事提示词架构
    - 等待机制与心理状态演变
    - 主动思考能力
    """

    plugin_name: str = "kokoro_flow_chatter"
    enable_plugin: bool = True
    plugin_priority: int = 50  # 高于默认 Chatter
    dependencies: ClassVar[list[str]] = []
    python_dependencies: ClassVar[list[str]] = []
    config_file_name: str = "config.toml"
    generate_config_file: bool = True
    config_schema = {
        "main": {
            "fast_mode_enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用极速模式（私聊下禁用动作筛选和记忆判官，单次 API 调用）",
            ),
        },
        "llm": {
            "model_name": ConfigField(
                type=str,
                default="",
                description="KFC 专用模型名称（留空则使用全局默认模型）",
            ),
            "temperature": ConfigField(
                type=float,
                default=0.8,
                description="KFC 专用生成温度",
            ),
        },
    }

    config_section_descriptions = {
        "main": "极速模式设置",
        "llm": "KFC 专用模型覆盖（可选）",
    }

    # 状态
    _is_started: bool = False

    async def on_plugin_loaded(self):
        """插件加载时"""
        config = get_config()

        if not config.enabled:
            logger.info("[KFC] 插件已禁用")
            return

        logger.info("[KFC] 插件已加载")

        # 启动主动思考器
        if config.proactive.enabled:
            try:
                await start_proactive_thinker()
                logger.info("[KFC] 主动思考器已启动")
                self._is_started = True
            except Exception as e:
                logger.error(f"[KFC] 启动主动思考器失败: {e}")

    async def on_plugin_unloaded(self):
        """插件卸载时"""
        try:
            await stop_proactive_thinker()
            logger.info("[KFC] 主动思考器已停止")
            self._is_started = False
        except Exception as e:
            logger.warning(f"[KFC] 停止主动思考器失败: {e}")

    def get_plugin_components(self):
        """返回组件列表"""
        config = get_config()

        if not config.enabled:
            return []

        components = []

        try:
            # 注册 Chatter
            components.append((
                KokoroFlowChatter.get_chatter_info(),
                KokoroFlowChatter,
            ))
            logger.debug("[KFC] 成功加载 KokoroFlowChatter 组件")
        except Exception as e:
            logger.error(f"[KFC] 加载 Chatter 组件失败: {e}")

        try:
            # 注册 KFC 专属 Reply 动作
            from .actions.reply import KFCReplyAction

            components.append((
                KFCReplyAction.get_action_info(),
                KFCReplyAction,
            ))
            logger.debug("[KFC] 成功加载 KFCReplyAction 组件")
        except Exception as e:
            logger.error(f"[KFC] 加载 Reply 动作失败: {e}")

        return components

    def get_plugin_info(self) -> dict[str, Any]:
        """获取插件信息"""
        return {
            "name": self.plugin_name,
            "display_name": "Kokoro Flow Chatter",
            "version": "2.0.0",
            "author": "MoFox",
            "description": "专为私聊设计的增强 Chatter",
            "features": [
                "线性叙事提示词架构",
                "心理活动流记录",
                "等待机制与超时处理",
                "主动思考能力",
            ],
        }
