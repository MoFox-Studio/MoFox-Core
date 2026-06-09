"""服务组件基类

Service 组件是插件间通信机制，允许插件将自身能力暴露为可供其他插件调用的服务。

设计理念 (参考 Neo-MoFox)：
- Service 通过 service_name 标识，全局唯一
- 插件可在 on_plugin_loaded() 中向 service_manager 注册服务实例
- 其他插件通过 service_api 获取服务并调用其公开方法
- Service 不直接参与消息处理流程，而是作为能力提供方
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, ClassVar

from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.plugin_system.base.plugin_base import BasePlugin

logger = get_logger("base_service")


class BaseService(ABC):
    """服务组件基类。

    插件通过继承 BaseService 并实现公开方法来暴露能力。
    服务实例在插件加载时注册到全局 service_manager，其他插件可通过名称查找。

    Usage::

        class TranslateService(BaseService):
            service_name = "translate"
            service_description = "提供文本翻译能力"

            async def translate(self, text: str, target_lang: str) -> str:
                ...
    """

    # === 子类必须定义的属性 ===
    service_name: ClassVar[str] = ""
    """服务名称，全局唯一标识。必须由子类覆盖。"""

    service_description: ClassVar[str] = ""
    """服务描述。"""

    # === 可选配置 ===
    service_version: ClassVar[str] = "1.0.0"
    """服务版本号。"""

    def __init__(self, plugin: BasePlugin | None = None) -> None:
        """初始化服务组件。

        Args:
            plugin: 所属插件实例，用于访问插件配置等。
        """
        self._plugin = plugin
        self._initialized = False

    @property
    def plugin(self) -> "BasePlugin | None":
        """获取所属插件实例。"""
        return self._plugin

    @property
    def plugin_name(self) -> str:
        """获取所属插件名称。"""
        if self._plugin is not None:
            return getattr(self._plugin, "plugin_name", "unknown")
        return "unknown"

    async def on_service_loaded(self) -> None:
        """服务注册后的初始化回调。

        在服务被 service_manager 注册后调用。
        可用于初始化资源（如加载模型、建立连接等）。
        """
        self._initialized = True
        logger.debug(f"Service '{self.service_name}' 已初始化")

    async def on_service_unloaded(self) -> None:
        """服务卸载前的清理回调。

        在插件被卸载或服务被移除时调用。
        可用于释放资源（如关闭连接、保存状态等）。
        """
        self._initialized = False
        logger.debug(f"Service '{self.service_name}' 已清理")

    def is_initialized(self) -> bool:
        """检查服务是否已初始化。"""
        return self._initialized

    @classmethod
    def get_service_info(cls) -> "ServiceInfo":
        """获取服务组件信息。

        Returns:
            ServiceInfo: 服务信息数据对象。
        """
        from src.plugin_system.base.component_types import ComponentType

        return ServiceInfo(
            name=cls.service_name,
            component_type=ComponentType.SERVICE,
            description=cls.service_description,
            service_version=cls.service_version,
        )


# 延迟导入以避免循环依赖
def _get_service_info_dataclass():
    """获取 ServiceInfo 数据类（延迟导入）。"""
    from dataclasses import dataclass, field

    from src.plugin_system.base.component_types import ComponentType

    @dataclass
    class _ServiceInfo:
        name: str
        component_type: ComponentType = field(default=ComponentType.SERVICE, init=False)
        description: str = ""
        enabled: bool = True
        plugin_name: str = ""
        is_built_in: bool = False
        service_version: str = "1.0.0"
        metadata: dict = field(default_factory=dict)

        def __post_init__(self):
            if self.metadata is None:
                self.metadata = {}

    return _ServiceInfo


# 在模块级别创建 ServiceInfo 引用
ServiceInfo = _get_service_info_dataclass()
