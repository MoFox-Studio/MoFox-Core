"""服务管理 API

提供插件的 Service 组件注册、查找和调用能力。

设计理念 (参考 Neo-MoFox)：
- 全局单例 service_manager 管理所有已注册的服务
- 插件通过 service_api 查找和使用其他插件的服务
- 服务按 plugin_name.service_name 进行索引
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.plugin_system.base.base_service import BaseService

logger = get_logger("service_api")


class ServiceManager:
    """全局服务管理器。

    单例模式，管理所有插件注册的 Service 组件。
    """

    def __init__(self) -> None:
        self._services: dict[str, BaseService] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, plugin_name: str, service_name: str) -> str:
        """生成服务索引键。

        Args:
            plugin_name: 插件名称。
            service_name: 服务名称。

        Returns:
            str: 格式为 "plugin_name:service_name" 的键。
        """
        return f"{plugin_name}:{service_name}"

    async def register(
        self,
        service: BaseService,
        plugin_name: str,
    ) -> bool:
        """注册一个服务组件。

        Args:
            service: 服务实例。
            plugin_name: 所属插件名称。

        Returns:
            bool: 注册是否成功。

        Raises:
            ValueError: 如果同名服务已存在。
        """
        if not service.service_name:
            logger.error("Service 缺少 service_name，无法注册")
            return False

        key = self._make_key(plugin_name, service.service_name)

        async with self._lock:
            if key in self._services:
                existing = self._services[key]
                logger.warning(
                    f"Service '{key}' 已注册 (由 {existing.plugin_name} 提供)，跳过重复注册"
                )
                return False

            self._services[key] = service
            await service.on_service_loaded()
            logger.info(
                f"Service '{service.service_name}' (插件: {plugin_name}) 已注册"
            )
            return True

    async def unregister(self, plugin_name: str, service_name: str) -> bool:
        """注销一个服务组件。

        Args:
            plugin_name: 所属插件名称。
            service_name: 服务名称。

        Returns:
            bool: 注销是否成功。
        """
        key = self._make_key(plugin_name, service_name)

        async with self._lock:
            service = self._services.pop(key, None)
            if service is None:
                logger.warning(f"Service '{key}' 未注册，无法注销")
                return False

            await service.on_service_unloaded()
            logger.info(f"Service '{key}' 已注销")
            return True

    async def unregister_all_for_plugin(self, plugin_name: str) -> int:
        """注销指定插件的所有服务。

        Args:
            plugin_name: 插件名称。

        Returns:
            int: 注销的服务数量。
        """
        prefix = f"{plugin_name}:"
        count = 0

        async with self._lock:
            keys_to_remove = [k for k in self._services if k.startswith(prefix)]
            for key in keys_to_remove:
                service = self._services.pop(key)
                await service.on_service_unloaded()
                count += 1

        if count > 0:
            logger.info(f"已注销插件 '{plugin_name}' 的 {count} 个服务")
        return count

    def get(self, plugin_name: str, service_name: str) -> BaseService | None:
        """获取指定服务（同步）。

        Args:
            plugin_name: 插件名称。
            service_name: 服务名称。

        Returns:
            BaseService | None: 服务实例，或 None。
        """
        key = self._make_key(plugin_name, service_name)
        return self._services.get(key)

    def find_by_name(self, service_name: str) -> list[BaseService]:
        """按服务名称模糊查找（可能返回多个不同插件提供的同名服务）。

        Args:
            service_name: 服务名称。

        Returns:
            list[BaseService]: 匹配的服务列表。
        """
        results = []
        for key, svc in self._services.items():
            if key.endswith(f":{service_name}"):
                results.append(svc)
        return results

    def list_all(self) -> dict[str, str]:
        """列出所有已注册的服务。

        Returns:
            dict[str, str]: {key: service_description}。
        """
        return {key: svc.service_description for key, svc in self._services.items()}

    async def clear_all(self) -> int:
        """清除所有已注册的服务（用于系统关闭）。

        Returns:
            int: 清除的服务数量。
        """
        async with self._lock:
            count = len(self._services)
            for service in self._services.values():
                await service.on_service_unloaded()
            self._services.clear()
            logger.info(f"已清除所有 {count} 个服务")
            return count


# 全局单例
_service_manager: ServiceManager | None = None
_lock = asyncio.Lock()


async def get_service_manager() -> ServiceManager:
    """获取全局服务管理器单例。

    Returns:
        ServiceManager: 全局服务管理器实例。
    """
    global _service_manager, _lock
    if _service_manager is None:
        async with _lock:
            if _service_manager is None:
                _service_manager = ServiceManager()
    return _service_manager


# 便捷 API
async def register_service(service: BaseService, plugin_name: str) -> bool:
    """注册服务（便捷函数）。"""
    manager = await get_service_manager()
    return await manager.register(service, plugin_name)


def get_service(plugin_name: str, service_name: str) -> BaseService | None:
    """获取服务（便捷函数）。

    注意：此函数是同步的，可在非异步上下文中使用，
    因为它仅查询已初始化的全局单例。
    """
    global _service_manager
    if _service_manager is None:
        logger.warning("ServiceManager 尚未初始化")
        return None
    return _service_manager.get(plugin_name, service_name)


async def find_service(service_name: str) -> list[BaseService]:
    """按名称查找服务（便捷函数）。"""
    manager = await get_service_manager()
    return manager.find_by_name(service_name)


async def list_services() -> dict[str, str]:
    """列出所有服务（便捷函数）。"""
    manager = await get_service_manager()
    return manager.list_all()
