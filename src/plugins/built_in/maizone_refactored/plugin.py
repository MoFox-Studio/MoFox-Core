"""
MaiZone（麦麦空间）- 重构版
"""

import asyncio

from src.common.logger import get_logger
from src.plugin_system import BasePlugin, ComponentInfo, register_plugin
from src.plugin_system.base.component_types import PermissionNodeField
from src.plugin_system.base.config_types import ConfigField

# 全局背景任务集合
_background_tasks = set()

from .actions.read_feed_action import ReadFeedAction
from .actions.send_feed_action import SendFeedAction
from .commands.send_feed_command import SendFeedCommand
from .services.content_service import ContentService
from .services.cookie_service import CookieService
from .services.image_service import ImageService
from .services.manager import register_service
from .services.monitor_service import MonitorService
from .services.qzone_service import QZoneService
from .services.reply_tracker_service import ReplyTrackerService
from .services.scheduler_service import SchedulerService

logger = get_logger("MaiZone.Plugin")


@register_plugin
class MaiZoneRefactoredPlugin(BasePlugin):
    plugin_name: str = "MaiZoneRefactored"
    plugin_version: str = "3.0.0"
    plugin_author: str = "Kilo Code"
    plugin_description: str = "重构版的MaiZone插件"
    config_file_name: str = "config.toml"
    enable_plugin: bool = True
    dependencies: list[str] = []
    python_dependencies: list[str] = []

    config_schema: dict = {
        "plugin": {"enable": ConfigField(type=bool, default=True, description="是否启用插件")},
        "ai_image": {
            "enable_ai_image": ConfigField(type=bool, default=False, description="是否启用AI生成配图"),
            "provider": ConfigField(type=str, default="siliconflow", description="AI生图服务提供商（siliconflow/novelai）"),
            "image_number": ConfigField(type=int, default=1, description="生成图片数量（1-4张）"),
        },
        "siliconflow": {
            "api_key": ConfigField(type=str, default="", description="硅基流动API密钥"),
        },
        "novelai": {
            "api_key": ConfigField(type=str, default="", description="NovelAI官方API密钥"),
            "character_prompt": ConfigField(type=str, default="", description="Bot角色外貌描述（AI判断需要bot出镜时插入）"),
            "base_negative_prompt": ConfigField(type=str, default="nsfw, nude, explicit, sexual content, lowres, bad anatomy, bad hands, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality", description="基础负面提示词（禁止不良内容）"),
            "proxy_host": ConfigField(type=str, default="", description="代理服务器地址（如：127.0.0.1）"),
            "proxy_port": ConfigField(type=int, default=0, description="代理服务器端口（如：7890）"),
        },
        "send": {
            "permission": ConfigField(type=list, default=[], description="发送权限QQ号列表"),
            "permission_type": ConfigField(type=str, default="whitelist", description="权限类型"),
            "enable_reply": ConfigField(type=bool, default=True, description="完成后是否回复"),
        },
        "read": {
            "permission": ConfigField(type=list, default=[], description="阅读权限QQ号列表"),
            "permission_type": ConfigField(type=str, default="blacklist", description="权限类型"),
            "read_number": ConfigField(type=int, default=5, description="一次读取的说说数量"),
            "like_possibility": ConfigField(type=float, default=1.0, description="点赞概率"),
            "comment_possibility": ConfigField(type=float, default=0.3, description="评论概率"),
        },
        "monitor": {
            "enable_auto_monitor": ConfigField(type=bool, default=False, description="是否启用自动监控"),
            "interval_minutes": ConfigField(type=int, default=10, description="监控间隔分钟数"),
            "enable_auto_reply": ConfigField(type=bool, default=False, description="是否启用自动回复自己说说的评论"),
        },
        "schedule": {
            "enable_schedule": ConfigField(type=bool, default=False, description="是否启用定时发送"),
            "random_interval_min_minutes": ConfigField(type=int, default=120, description="随机间隔分钟数下限"),
            "random_interval_max_minutes": ConfigField(type=int, default=135, description="随机间隔分钟数上限"),
            "forbidden_hours_start": ConfigField(type=int, default=2, description="禁止发送的开始小时(24小时制)"),
            "forbidden_hours_end": ConfigField(type=int, default=6, description="禁止发送的结束小时(24小时制)"),
        },
        "cookie": {
            "http_fallback_host": ConfigField(
                type=str, default="127.0.0.1", description="备用Cookie获取服务的主机地址"
            ),
            "http_fallback_port": ConfigField(type=int, default=9999, description="备用Cookie获取服务的端口"),
            "napcat_token": ConfigField(type=str, default="", description="Napcat服务的认证Token（可选）"),
        },
        "cross_context": {
            "user_id": ConfigField(type=str, default="", description="用于获取互通上下文的目标用户QQ号"),
        },
    }

    permission_nodes: list[PermissionNodeField] = [
        PermissionNodeField(node_name="send_feed", description="是否可以使用机器人发送QQ空间说说"),
        PermissionNodeField(node_name="read_feed", description="是否可以使用机器人读取QQ空间说说"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_plugin_loaded(self):
        """插件加载完成后的回调，初始化服务并启动后台任务"""
        # --- 创建并注册所有服务实例 ---
        content_service = ContentService(self.get_config)
        image_service = ImageService(self.get_config)
        cookie_service = CookieService(self.get_config)
        reply_tracker_service = ReplyTrackerService()

        qzone_service = QZoneService(
            self.get_config,
            content_service,
            image_service,
            cookie_service,
            reply_tracker_service,
        )
        scheduler_service = SchedulerService(self.get_config, qzone_service)
        monitor_service = MonitorService(self.get_config, qzone_service)

        register_service("qzone", qzone_service)
        register_service("reply_tracker", reply_tracker_service)
        register_service("get_config", self.get_config)

        logger.info("MaiZone重构版插件服务已注册。")

        # --- 启动后台任务 ---
        task1 = asyncio.create_task(scheduler_service.start())
        _background_tasks.add(task1)
        task1.add_done_callback(_background_tasks.discard)

        task2 = asyncio.create_task(monitor_service.start())
        _background_tasks.add(task2)
        task2.add_done_callback(_background_tasks.discard)

        logger.info("MaiZone后台监控和定时任务已启动。")

    def get_plugin_components(self) -> list[tuple[ComponentInfo, type]]:
        return [
            (SendFeedAction.get_action_info(), SendFeedAction),
            (ReadFeedAction.get_action_info(), ReadFeedAction),
            (SendFeedCommand.get_plus_command_info(), SendFeedCommand),
        ]
