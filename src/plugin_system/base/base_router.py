"""路由组件基类

Router 组件允许插件注册 HTTP API 端点，基于 FastAPI 实现。

设计理念 (参考 Neo-MoFox)：
- Router 通过 router_name 标识，全局唯一
- 子类重写 register_endpoints(router) 来注册路由
- plugin_manager 在插件加载时自动将 Router 挂载到全局 FastAPI app
- Router 仅用于 HTTP API，不要用于聊天逻辑

Usage::

    class HealthRouter(BaseRouter):
        router_name = "health_api"
        router_description = "健康检查接口"
        custom_route_path = "/api/health"

        def register_endpoints(self, router: APIRouter) -> None:
            @router.get("/ping")
            async def ping():
                return {"status": "ok"}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from fastapi import APIRouter

from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.plugin_system.base.plugin_base import BasePlugin

logger = get_logger("base_router")


class BaseRouter(ABC):
    """路由组件基类。

    为插件提供 HTTP API 注册能力。每个 Router 对应一个独立的
    FastAPI APIRouter，并挂载到全局 FastAPI app 的指定路径下。

    子类必须覆盖:
        - router_name: 路由标识名称
        - register_endpoints(): 注册具体的 API 端点
    """

    # === 子类必须定义的属性 ===
    router_name: ClassVar[str] = ""
    """路由名称，全局唯一标识。必须由子类覆盖。"""

    # === 可选配置 ===
    router_description: ClassVar[str] = ""
    """路由描述。"""

    custom_route_path: ClassVar[str | None] = None
    """自定义路由前缀路径。

    如果未指定，默认使用 /plugins/{plugin_name}/{router_name}。
    例如: "/api/health"、"/admin/tools"。
    """

    cors_origins: ClassVar[list[str]] = ["*"]
    """允许的 CORS 来源列表。"""

    tags: ClassVar[list[str]] = []
    """OpenAPI 文档标签。"""

    include_in_schema: ClassVar[bool] = True
    """是否包含在 OpenAPI schema 中。"""

    def __init__(self, plugin: BasePlugin | None = None) -> None:
        """初始化路由组件。

        Args:
            plugin: 所属插件实例。
        """
        self._plugin = plugin
        self._apirouter: APIRouter | None = None

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

    def create_apirouter(self) -> APIRouter:
        """创建并配置 FastAPI APIRouter。

        Returns:
            APIRouter: 已配置的路由器实例。
        """
        if self.custom_route_path:
            prefix = self.custom_route_path
        else:
            prefix = f"/plugins/{self.plugin_name}/{self.router_name}"

        self._apirouter = APIRouter(
            prefix=prefix,
            tags=self.tags or [self.plugin_name],
            include_in_schema=self.include_in_schema,
        )

        # 如果子类定义了 CORSMiddleware 需求，这里可以配置
        # 实际 CORS 由全局 FastAPI app 统一管理

        logger.debug(f"Router '{self.router_name}' APIRouter 已创建，前缀: {prefix}")
        return self._apirouter

    def get_apirouter(self) -> APIRouter | None:
        """获取当前的 APIRouter 实例。"""
        return self._apirouter

    async def on_router_mounted(self) -> None:
        """路由挂载到全局 app 后的回调。

        可用于初始化路由所需的资源。
        """
        logger.debug(f"Router '{self.router_name}' 已挂载")

    async def on_router_unmounted(self) -> None:
        """路由从全局 app 卸载前的回调。

        可用于清理路由相关资源。
        """
        logger.debug(f"Router '{self.router_name}' 已卸载")

    @abstractmethod
    def register_endpoints(self, router: APIRouter) -> None:
        """注册 API 端点。

        子类必须实现此方法，在提供的 APIRouter 上注册路由。

        Args:
            router: 已配置好前缀的 APIRouter 实例。

        Example::

            def register_endpoints(self, router: APIRouter) -> None:
                @router.get("/status")
                async def status():
                    return {"service": self.router_name, "ok": True}

                @router.post("/action")
                async def do_action(data: dict = Body(...)):
                    result = await self.plugin.do_something(data)
                    return {"result": result}
        """
        ...

    @classmethod
    def get_router_info(cls) -> "RouterInfo":
        """获取路由组件信息。

        Returns:
            RouterInfo: 路由信息数据对象。
        """
        from src.plugin_system.base.component_types import ComponentType

        return RouterInfo(
            name=cls.router_name,
            component_type=ComponentType.ROUTER,
            description=cls.router_description,
            route_path=cls.custom_route_path or f"/plugins/{{plugin}}/{cls.router_name}",
        )


# 延迟导入以避免循环依赖
def _get_router_info_dataclass():
    """获取 RouterInfo 数据类（延迟导入）。"""
    from dataclasses import dataclass, field

    from src.plugin_system.base.component_types import ComponentType

    @dataclass
    class _RouterInfo:
        name: str
        component_type: ComponentType = field(default=ComponentType.ROUTER, init=False)
        description: str = ""
        enabled: bool = True
        plugin_name: str = ""
        is_built_in: bool = False
        route_path: str = ""
        metadata: dict = field(default_factory=dict)

        def __post_init__(self):
            if self.metadata is None:
                self.metadata = {}

    return _RouterInfo


RouterInfo = _get_router_info_dataclass()
