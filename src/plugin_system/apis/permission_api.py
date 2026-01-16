"""
纯异步权限API定义。

这个模块提供了一套完整的权限管理系统，用于控制用户对各种功能的访问权限。
所有外部调用方必须使用 await 关键字，因为这是异步API。

主要组件：
- PermissionLevel: 权限等级枚举
- PermissionNode: 权限节点数据类，描述单个权限项
- UserInfo: 用户信息数据类，标识用户身份
- IPermissionManager: 权限管理器抽象接口
- PermissionAPI: 对外暴露的权限API封装类
"""

from abc import ABC, abstractmethod  # ABC: 抽象基类，abstractmethod: 抽象方法装饰器
from dataclasses import dataclass  # dataclass: 自动生成 __init__, __repr__ 等方法的装饰器
from enum import Enum  # Enum: 枚举类型基类
from typing import Any  # Any: 表示任意类型

from src.common.logger import get_logger

logger = get_logger(__name__)  # 获取当前模块的日志记录器


class PermissionLevel(Enum):
    """
    权限等级枚举类。

    定义了系统中的权限等级，目前只有 MASTER（管理员/主人）级别。
    MASTER 用户拥有最高权限，可以执行所有操作。
    """
    MASTER = "master"  # 管理员/主人权限


@dataclass
class PermissionNode:
    """
    权限节点数据类。

    每个权限节点代表一个具体的权限项，例如"发送消息"、"管理用户"等。

    属性:
        node_name: 权限节点名称，例如 "plugin.chat.send_message"
        description: 权限描述，用于向用户展示这个权限的用途
        plugin_name: 注册这个权限的插件名称
        default_granted: 是否默认授予所有用户，False 表示需要显式授权
    """
    node_name: str           # 权限节点唯一标识名
    description: str         # 权限的人类可读描述
    plugin_name: str         # 所属插件名称
    default_granted: bool = False  # 默认是否授予（默认不授予）


@dataclass
class UserInfo:
    """
    用户信息数据类。

    用于唯一标识一个用户，通过平台+用户ID的组合确定用户身份。

    属性:
        platform: 用户所在平台，例如 "qq", "telegram", "discord"
        user_id: 用户在该平台上的唯一标识ID
    """
    platform: str   # 平台标识，如 "qq", "telegram"
    user_id: str    # 用户ID

    def __post_init__(self):
        """
        dataclass 的后初始化钩子。

        确保 user_id 始终是字符串类型，即使传入的是数字也会被转换。
        这样可以避免类型不一致导致的比较问题。
        """
        self.user_id = str(self.user_id)


class IPermissionManager(ABC):
    """
    权限管理器抽象接口（Interface）。

    这是一个抽象基类，定义了权限管理器必须实现的所有方法。
    具体的权限管理实现类需要继承此接口并实现所有抽象方法。

    使用抽象接口的好处：
    1. 解耦：PermissionAPI 不需要知道具体的实现细节
    2. 可测试：可以轻松创建 Mock 实现用于测试
    3. 可替换：可以随时更换不同的权限管理实现
    """

    @abstractmethod
    async def check_permission(self, user: UserInfo, permission_node: str) -> bool:
        """
        检查用户是否拥有指定权限。

        Args:
            user: 要检查的用户信息
            permission_node: 权限节点名称

        Returns:
            bool: True 表示用户拥有该权限，False 表示没有
        """
        ...

    @abstractmethod
    async def is_master(self, user: UserInfo) -> bool:
        """
        检查用户是否是管理员/主人。

        管理员拥有最高权限，通常绕过所有权限检查。

        Args:
            user: 要检查的用户信息

        Returns:
            bool: True 表示是管理员，False 表示不是
        """
        ...

    @abstractmethod
    async def register_permission_node(self, node: PermissionNode) -> bool:
        """
        注册一个新的权限节点。

        插件在加载时会调用此方法注册自己需要的权限。

        Args:
            node: 要注册的权限节点信息

        Returns:
            bool: True 表示注册成功，False 表示失败（可能是重复注册）
        """
        ...

    @abstractmethod
    async def grant_permission(self, user: UserInfo, permission_node: str) -> bool:
        """
        授予用户指定权限。

        Args:
            user: 目标用户信息
            permission_node: 要授予的权限节点名称

        Returns:
            bool: True 表示授权成功，False 表示失败
        """
        ...

    @abstractmethod
    async def revoke_permission(self, user: UserInfo, permission_node: str) -> bool:
        """
        撤销用户的指定权限。

        Args:
            user: 目标用户信息
            permission_node: 要撤销的权限节点名称

        Returns:
            bool: True 表示撤销成功，False 表示失败
        """
        ...

    @abstractmethod
    async def get_user_permissions(self, user: UserInfo) -> list[str]:
        """
        获取用户拥有的所有权限列表。

        Args:
            user: 目标用户信息

        Returns:
            list[str]: 用户拥有的权限节点名称列表
        """
        ...

    @abstractmethod
    async def get_all_permission_nodes(self) -> list[PermissionNode]:
        """
        获取系统中所有已注册的权限节点。

        Returns:
            list[PermissionNode]: 所有权限节点的列表
        """
        ...

    @abstractmethod
    async def get_plugin_permission_nodes(self, plugin_name: str) -> list[PermissionNode]:
        """
        获取指定插件注册的所有权限节点。

        Args:
            plugin_name: 插件名称

        Returns:
            list[PermissionNode]: 该插件注册的权限节点列表
        """
        ...


class PermissionAPI:
    """
    权限API封装类。

    这是对外暴露的权限操作接口，插件和其他模块通过这个类来进行权限相关操作。
    它封装了底层的 IPermissionManager，提供更简洁的调用方式。

    使用方式：
        from src.plugin_system.apis.permission_api import permission_api

        # 检查权限
        has_perm = await permission_api.check_permission("qq", "12345", "chat.send")

        # 检查是否是管理员
        is_admin = await permission_api.is_master("qq", "12345")

    设计模式：
        这是一个单例模式的变体，模块级别的 permission_api 实例供全局使用。
    """

    def __init__(self):
        """
        初始化 PermissionAPI。

        初始时权限管理器为 None，需要在系统启动时通过 set_permission_manager 设置。
        """
        self._permission_manager: IPermissionManager | None = None  # 底层权限管理器实例

    def set_permission_manager(self, manager: IPermissionManager):
        """
        设置权限管理器实例。

        这个方法应该在系统启动时被调用，注入具体的权限管理器实现。

        Args:
            manager: 实现了 IPermissionManager 接口的权限管理器实例
        """
        self._permission_manager = manager

    def _ensure_manager(self):
        """
        确保权限管理器已设置（内部辅助方法）。

        如果权限管理器未设置，抛出 RuntimeError 异常。
        这是一个防御性编程措施，帮助开发者快速发现配置问题。

        Raises:
            RuntimeError: 当权限管理器未设置时
        """
        if self._permission_manager is None:
            raise RuntimeError("权限管理器未设置，请先调用 set_permission_manager")

    async def check_permission(self, platform: str, user_id: str, permission_node: str) -> bool:
        """
        检查用户是否拥有指定权限。

        这是最常用的权限检查方法，在执行需要权限的操作前调用。

        Args:
            platform: 用户所在平台（如 "qq", "telegram"）
            user_id: 用户ID
            permission_node: 要检查的权限节点名称

        Returns:
            bool: True 表示用户拥有权限，False 表示没有

        Example:
            if await permission_api.check_permission("qq", "12345", "admin.ban_user"):
                # 执行封禁操作
                pass
        """
        self._ensure_manager()
        if not self._permission_manager:
            logger.warning(
                f"[permission_api.check_permission] 权限管理器未设置，返回False | "
                f"用户: {platform}:{user_id} | 权限节点: {permission_node}"
            )
            return False
        
        logger.debug(
            f"[permission_api.check_permission] 开始检查权限 | "
            f"用户: {platform}:{user_id} | 权限节点: {permission_node}"
        )
        
        has_permission = await self._permission_manager.check_permission(UserInfo(platform, user_id), permission_node)
        
        if has_permission:
            logger.info(
                f"[permission_api.check_permission] ✓ 权限检查通过 | "
                f"用户: {platform}:{user_id} | 权限节点: {permission_node}"
            )
        else:
            logger.debug(
                f"[permission_api.check_permission] ✗ 权限检查失败 | "
                f"用户: {platform}:{user_id} | 权限节点: {permission_node}"
            )
        
        return has_permission

    async def is_master(self, platform: str, user_id: str) -> bool:
        """
        检查用户是否是管理员/主人。

        管理员是系统的最高权限用户，通常在配置文件中指定。

        Args:
            platform: 用户所在平台
            user_id: 用户ID

        Returns:
            bool: True 表示是管理员，False 表示不是
        """
        self._ensure_manager()
        if not self._permission_manager:
            logger.warning(f"[permission_api.is_master] 权限管理器未设置，返回False | 用户: {platform}:{user_id}")
            return False
        
        logger.debug(f"[permission_api.is_master] 开始检查Master权限 | 用户: {platform}:{user_id}")
        
        is_master = await self._permission_manager.is_master(UserInfo(platform, user_id))
        
        if is_master:
            logger.info(f"[permission_api.is_master] ✓ 用户是Master | 用户: {platform}:{user_id}")
        else:
            logger.debug(f"[permission_api.is_master] ✗ 用户不是Master | 用户: {platform}:{user_id}")
        
        return is_master

    async def register_permission_node(
        self,
        node_name: str,
        description: str,
        plugin_name: str,
        default_granted: bool = False,
        *,
        allow_relative: bool = True,  # 仅关键字参数，目前未使用，预留给相对权限名功能
    ) -> bool:
        """
        注册一个新的权限节点。

        插件在初始化时应调用此方法注册自己需要的权限节点。

        Args:
            node_name: 权限节点名称，建议使用 "插件名.功能.操作" 的格式
            description: 权限描述，向用户解释这个权限的作用
            plugin_name: 注册此权限的插件名称
            default_granted: 是否默认授予所有用户（默认 False，需要显式授权）
            allow_relative: 预留参数，是否允许相对权限名（目前未使用）

        Returns:
            bool: True 表示注册成功，False 表示失败

        Example:
            await permission_api.register_permission_node(
                node_name="my_plugin.chat.send_image",
                description="允许发送图片消息",
                plugin_name="my_plugin",
                default_granted=True  # 所有用户默认都能发图片
            )
        """
        self._ensure_manager()

        # 创建权限节点对象
        node = PermissionNode(node_name, description, plugin_name, default_granted)
        if not self._permission_manager:
            return False
        return await self._permission_manager.register_permission_node(node)



    async def grant_permission(self, platform: str, user_id: str, permission_node: str) -> bool:
        """
        授予用户指定权限。

        通常由管理员调用，给某个用户赋予特定权限。

        Args:
            platform: 目标用户所在平台
            user_id: 目标用户ID
            permission_node: 要授予的权限节点名称

        Returns:
            bool: True 表示授权成功，False 表示失败

        Example:
            # 授予用户管理权限
            await permission_api.grant_permission("qq", "12345", "admin.manage_users")
        """
        self._ensure_manager()
        if not self._permission_manager:
            return False
        return await self._permission_manager.grant_permission(UserInfo(platform, user_id), permission_node)

    async def revoke_permission(self, platform: str, user_id: str, permission_node: str) -> bool:
        """
        撤销用户的指定权限。

        通常由管理员调用，移除某个用户的特定权限。

        Args:
            platform: 目标用户所在平台
            user_id: 目标用户ID
            permission_node: 要撤销的权限节点名称

        Returns:
            bool: True 表示撤销成功，False 表示失败
        """
        self._ensure_manager()
        if not self._permission_manager:
            return False
        return await self._permission_manager.revoke_permission(UserInfo(platform, user_id), permission_node)

    async def get_user_permissions(self, platform: str, user_id: str) -> list[str]:
        """
        获取用户拥有的所有权限列表。

        可用于展示用户的权限信息，或进行批量权限检查。

        Args:
            platform: 目标用户所在平台
            user_id: 目标用户ID

        Returns:
            list[str]: 用户拥有的所有权限节点名称列表

        Example:
            perms = await permission_api.get_user_permissions("qq", "12345")
            print(f"用户拥有以下权限: {perms}")
        """
        self._ensure_manager()
        if not self._permission_manager:
            return []
        return await self._permission_manager.get_user_permissions(UserInfo(platform, user_id))

    async def get_all_permission_nodes(self) -> list[dict[str, Any]]:
        """
        获取系统中所有已注册的权限节点。

        返回所有插件注册的权限节点信息，可用于权限管理界面展示。

        Returns:
            list[dict]: 权限节点信息列表，每个字典包含：
                - node_name: 权限节点名称
                - description: 权限描述
                - plugin_name: 所属插件名称
                - default_granted: 是否默认授予

        Note:
            返回字典而非 PermissionNode 对象，便于序列化和API响应。
        """
        self._ensure_manager()
        if not self._permission_manager:
            return []
        nodes = await self._permission_manager.get_all_permission_nodes()
        # 将 PermissionNode 对象转换为字典，便于序列化
        return [
            {
                "node_name": n.node_name,
                "description": n.description,
                "plugin_name": n.plugin_name,
                "default_granted": n.default_granted,
            }
            for n in nodes
        ]

    async def get_plugin_permission_nodes(self, plugin_name: str) -> list[dict[str, Any]]:
        """
        获取指定插件注册的所有权限节点。

        用于查看某个特定插件定义了哪些权限。

        Args:
            plugin_name: 插件名称

        Returns:
            list[dict]: 该插件的权限节点信息列表，格式同 get_all_permission_nodes
        """
        self._ensure_manager()
        if not self._permission_manager:
            return []
        nodes = await self._permission_manager.get_plugin_permission_nodes(plugin_name)
        # 将 PermissionNode 对象转换为字典
        return [
            {
                "node_name": n.node_name,
                "description": n.description,
                "plugin_name": n.plugin_name,
                "default_granted": n.default_granted,
            }
            for n in nodes
        ]


# ============================================================
# 模块级单例实例
# ============================================================
# 全局权限API实例，供其他模块导入使用
# 使用方式: from src.plugin_system.apis.permission_api import permission_api
permission_api = PermissionAPI()
