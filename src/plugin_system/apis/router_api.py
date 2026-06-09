"""路由管理 API

管理插件 Router 组件的挂载和卸载。

设计理念 (参考 Neo-MoFox)：
- 全局单例 router_manager 管理所有 Router 组件的挂载
- plugin_manager 在加载插件时自动将 Router 挂载到全局 FastAPI app
- 支持动态添加/移除路由
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter

from src.common.logger import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from src.plugin_system.base.base_router import BaseRouter

logger = get_logger("router_api")


class RouterManager:
    """全局路由管理器。

    管理所有插件 Router 组件的挂载和卸载。
    """

    def __init__(self) -> None:
        self._routers: dict[str, BaseRouter] = {}
        self._mounted: dict[str, APIRouter] = {}
        self._app: "FastAPI | None" = None
        self._lock = asyncio.Lock()

    def set_app(self, app: "FastAPI") -> None:
        """设置全局 FastAPI 应用实例。

        Args:
            app: FastAPI 应用实例。
        """
        self._app = app
        logger.debug("RouterManager 已绑定 FastAPI app")

    @property
    def app(self) -> "FastAPI | None":
        """获取已绑定的 FastAPI 应用实例。"""
        return self._app

    def _make_key(self, plugin_name: str, router_name: str) -> str:
        """生成路由索引键。"""
        return f"{plugin_name}:{router_name}"

    async def register(self, router: BaseRouter, plugin_name: str) -> bool:
        """注册并挂载路由组件。

        Args:
            router: Router 组件实例。
            plugin_name: 所属插件名称。

        Returns:
            bool: 挂载是否成功。
        """
        if not router.router_name:
            logger.error("Router 缺少 router_name，无法注册")
            return False

        key = self._make_key(plugin_name, router.router_name)

        async with self._lock:
            if key in self._routers:
                logger.warning(f"Router '{key}' 已注册，跳过")
                return False

            # 创建 APIRouter
            apirouter = router.create_apirouter()

            # 让 Router 注册端点
            router.register_endpoints(apirouter)

            # 挂载到全局 FastAPI app
            if self._app is not None:
                self._app.include_router(apirouter)
                await router.on_router_mounted()
                logger.info(f"Router '{key}' 已挂载到 FastAPI app")
            else:
                # 延迟挂载：先存储，等 app 初始化后再挂载
                logger.debug(f"FastAPI app 未就绪，Router '{key}' 将在 app 初始化后挂载")

            self._routers[key] = router
            self._mounted[key] = apirouter
            return True

    async def unregister(self, plugin_name: str, router_name: str) -> bool:
        """卸载路由组件。

        Args:
            plugin_name: 插件名称。
            router_name: 路由名称。

        Returns:
            bool: 卸载是否成功。
        """
        key = self._make_key(plugin_name, router_name)

        async with self._lock:
            router = self._routers.pop(key, None)
            if router is None:
                return False

            self._mounted.pop(key, None)

            # FastAPI 不支持直接卸载路由，
            # 但我们可以通过重建 app 或标记路由为不可用来处理
            await router.on_router_unmounted()
            logger.info(f"Router '{key}' 已卸载")
            return True

    async def unregister_all_for_plugin(self, plugin_name: str) -> int:
        """卸载指定插件的所有路由。

        Args:
            plugin_name: 插件名称。

        Returns:
            int: 卸载的路由数量。
        """
        prefix = f"{plugin_name}:"
        count = 0

        async with self._lock:
            keys_to_remove = [k for k in self._routers if k.startswith(prefix)]
            for key in keys_to_remove:
                router = self._routers.pop(key)
                self._mounted.pop(key, None)
                await router.on_router_unmounted()
                count += 1

        if count > 0:
            logger.info(f"已卸载插件 '{plugin_name}' 的 {count} 个路由")
        return count

    async def mount_all_pending(self) -> int:
        """挂载所有待挂载的路由（在 FastAPI app 初始化后调用）。

        Returns:
            int: 挂载的路由数量。
        """
        if self._app is None:
            logger.warning("无法挂载待处理路由：FastAPI app 未设置")
            return 0

        count = 0
        async with self._lock:
            for key, router in self._routers.items():
                if key not in self._mounted:
                    apirouter = self._mounted.get(key)
                    if apirouter is not None:
                        self._app.include_router(apirouter)
                        await router.on_router_mounted()
                        count += 1

        if count > 0:
            logger.info(f"已挂载 {count} 个待处理路由")
        return count

    def list_all(self) -> dict[str, str]:
        """列出所有已注册的路由。

        Returns:
            dict[str, str]: {key: router_description}。
        """
        return {key: r.router_description for key, r in self._routers.items()}


# 全局单例
_router_manager: RouterManager | None = None
_lock = asyncio.Lock()


async def get_router_manager() -> RouterManager:
    """获取全局路由管理器单例。"""
    global _router_manager, _lock
    if _router_manager is None:
        async with _lock:
            if _router_manager is None:
                _router_manager = RouterManager()
    return _router_manager
