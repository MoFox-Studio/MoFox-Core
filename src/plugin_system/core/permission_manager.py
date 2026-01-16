"""
权限管理器实现

这个模块提供了权限系统的核心实现，包括权限检查、权限节点管理、用户权限管理等功能。
"""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.common.database.core import get_engine
from src.common.database.core.models import PermissionNodes, UserPermissions
from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.apis.permission_api import IPermissionManager, PermissionNode, UserInfo

logger = get_logger(__name__)


class PermissionManager(IPermissionManager):
    """权限管理器实现类"""

    def __init__(self):
        self._master_users: set[tuple[str, str]] = set()
        self._load_master_users()

    async def initialize(self):
        """异步初始化数据库连接"""
        self.engine = await get_engine()
        self.SessionLocal = async_sessionmaker(bind=self.engine)
        logger.debug("权限管理器初始化完成")

    def _load_master_users(self):
        """从配置文件加载Master用户列表"""
        logger.debug("开始从配置文件加载Master用户...")
        try:
            master_users_config = global_config.permission.master_users
            if not isinstance(master_users_config, list):
                logger.warning("配置文件中的 permission.master_users 不是一个列表，已跳过加载。")
                self._master_users = set()
                return

            self._master_users = set()
            for i, user_info in enumerate(master_users_config):
                if not isinstance(user_info, list) or len(user_info) != 2:
                    logger.warning(f'Master用户配置项格式错误 (索引: {i}): {user_info}，应为 ["platform", "user_id"]')
                    continue

                platform, user_id = user_info
                if not isinstance(platform, str) or not isinstance(user_id, str):
                    logger.warning(
                        f"Master用户配置项 platform 或 user_id 类型错误 (索引: {i}): [{type(platform).__name__}, {type(user_id).__name__}]，应为字符串"
                    )
                    continue

                self._master_users.add((platform, user_id))
                logger.debug(f"成功加载Master用户: platform={platform}, user_id={user_id}")

            logger.info(f"成功加载 {len(self._master_users)} 个Master用户")

        except Exception as e:
            logger.error(f"加载Master用户配置时发生严重错误: {e}")
            self._master_users = set()

    def reload_master_users(self):
        """重新加载Master用户配置"""
        logger.info("正在重新加载Master用户配置...")
        self._load_master_users()
        logger.info("Master用户配置已重新加载")

    async def is_master(self, user: UserInfo) -> bool:
        """
        检查用户是否为Master用户

        Args:
            user: 用户信息

        Returns:
            bool: 是否为Master用户
        """
        user_tuple = (user.platform, user.user_id)
        
        logger.debug(
            f"[PermissionManager.is_master] 检查用户 {user.platform}:{user.user_id} | "
            f"当前Master用户列表: {self._master_users}"
        )
        
        is_master_flag = user_tuple in self._master_users
        
        if is_master_flag:
            logger.info(f"[PermissionManager.is_master] ✓ 用户 {user.platform}:{user.user_id} 是Master用户")
        else:
            logger.debug(
                f"[PermissionManager.is_master] ✗ 用户 {user.platform}:{user.user_id} 不是Master用户 | "
                f"用户元组: {user_tuple} 不在Master列表中"
            )
        
        return is_master_flag

    async def check_permission(self, user: UserInfo, permission_node: str) -> bool:
        """
        检查用户是否拥有指定权限节点

        Args:
            user: 用户信息
            permission_node: 权限节点名称

        Returns:
            bool: 是否拥有权限
        """
        try:
            # Master用户拥有所有权限
            if await self.is_master(user):
                logger.debug(f"Master用户 {user.platform}:{user.user_id} 拥有权限节点 {permission_node}")
                return True

            async with self.SessionLocal() as session:
                # 检查权限节点是否存在
                result = await session.execute(select(PermissionNodes).filter_by(node_name=permission_node))
                node = result.scalar_one_or_none()
                if not node:
                    logger.warning(f"权限节点 {permission_node} 不存在")
                    return False

                # 检查用户是否有明确的权限设置
                result = await session.execute(
                    select(UserPermissions).filter_by(
                        platform=user.platform, user_id=user.user_id, permission_node=permission_node
                    )
                )
                user_perm = result.scalar_one_or_none()

                if user_perm:
                    # 有明确设置，返回设置的值
                    res = user_perm.granted
                    logger.debug(f"用户 {user.platform}:{user.user_id} 对权限节点 {permission_node} 的明确设置: {res}")
                    return res
                else:
                    # 没有明确设置，使用默认值
                    res = node.default_granted
                    logger.debug(
                        f"用户 {user.platform}:{user.user_id} 对权限节点 {permission_node} 使用默认设置: {res}"
                    )
                    return res

        except SQLAlchemyError as e:
            logger.error(f"检查权限时数据库错误: {e}")
            return False
        except Exception as e:
            logger.error(f"检查权限时发生未知错误: {e}")
            return False

    async def register_permission_node(self, node: PermissionNode) -> bool:
        """
        注册权限节点

        Args:
            node: 权限节点

        Returns:
            bool: 注册是否成功
        """
        try:
            async with self.SessionLocal() as session:
                # 检查节点是否已存在
                result = await session.execute(select(PermissionNodes).filter_by(node_name=node.node_name))
                existing_node = result.scalar_one_or_none()
                if existing_node:
                    # 更新现有节点的信息
                    existing_node.description = node.description
                    existing_node.plugin_name = node.plugin_name
                    existing_node.default_granted = node.default_granted
                    await session.commit()
                    logger.debug(f"更新权限节点: {node.node_name}")
                    return True

                # 创建新节点
                new_node = PermissionNodes(
                    node_name=node.node_name,
                    description=node.description,
                    plugin_name=node.plugin_name,
                    default_granted=node.default_granted,
                    created_at=datetime.utcnow(),
                )
                session.add(new_node)
                await session.commit()
                logger.info(f"注册新权限节点: {node.node_name} (插件: {node.plugin_name})")
                return True

        except IntegrityError as e:
            logger.error(f"注册权限节点时发生完整性错误: {e}")
            return False
        except SQLAlchemyError as e:
            logger.error(f"注册权限节点时数据库错误: {e}")
            return False
        except Exception as e:
            logger.error(f"注册权限节点时发生未知错误: {e}")
            return False

    async def grant_permission(self, user: UserInfo, permission_node: str) -> bool:
        """
        授权用户权限节点

        Args:
            user: 用户信息
            permission_node: 权限节点名称

        Returns:
            bool: 授权是否成功
        """
        try:
            async with self.SessionLocal() as session:
                # 检查权限节点是否存在
                result = await session.execute(select(PermissionNodes).filter_by(node_name=permission_node))
                node = result.scalar_one_or_none()
                if not node:
                    logger.error(f"尝试授权不存在的权限节点: {permission_node}")
                    return False

                # 检查是否已有权限记录
                result = await session.execute(
                    select(UserPermissions).filter_by(
                        platform=user.platform, user_id=user.user_id, permission_node=permission_node
                    )
                )
                existing_perm = result.scalar_one_or_none()

                if existing_perm:
                    # 更新现有记录
                    existing_perm.granted = True
                    existing_perm.granted_at = datetime.utcnow()
                else:
                    # 创建新记录
                    new_perm = UserPermissions(
                        platform=user.platform,
                        user_id=user.user_id,
                        permission_node=permission_node,
                        granted=True,
                        granted_at=datetime.utcnow(),
                    )
                    session.add(new_perm)

                await session.commit()
                logger.info(f"已授权用户 {user.platform}:{user.user_id} 权限节点 {permission_node}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"授权权限时数据库错误: {e}")
            return False
        except Exception as e:
            logger.error(f"授权权限时发生未知错误: {e}")
            return False

    async def revoke_permission(self, user: UserInfo, permission_node: str) -> bool:
        """
        撤销用户权限节点

        Args:
            user: 用户信息
            permission_node: 权限节点名称

        Returns:
            bool: 撤销是否成功
        """
        try:
            async with self.SessionLocal() as session:
                # 检查权限节点是否存在
                result = await session.execute(select(PermissionNodes).filter_by(node_name=permission_node))
                node = result.scalar_one_or_none()
                if not node:
                    logger.error(f"尝试撤销不存在的权限节点: {permission_node}")
                    return False

                # 检查是否已有权限记录
                result = await session.execute(
                    select(UserPermissions).filter_by(
                        platform=user.platform, user_id=user.user_id, permission_node=permission_node
                    )
                )
                existing_perm = result.scalar_one_or_none()

                if existing_perm:
                    # 更新现有记录
                    existing_perm.granted = False
                    existing_perm.granted_at = datetime.utcnow()
                else:
                    # 创建新记录（明确撤销）
                    new_perm = UserPermissions(
                        platform=user.platform,
                        user_id=user.user_id,
                        permission_node=permission_node,
                        granted=False,
                        granted_at=datetime.utcnow(),
                    )
                    session.add(new_perm)

                await session.commit()
                logger.info(f"已撤销用户 {user.platform}:{user.user_id} 权限节点 {permission_node}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"撤销权限时数据库错误: {e}")
            return False
        except Exception as e:
            logger.error(f"撤销权限时发生未知错误: {e}")
            return False

    async def get_user_permissions(self, user: UserInfo) -> list[str]:
        """
        获取用户拥有的所有权限节点

        Args:
            user: 用户信息

        Returns:
            List[str]: 权限节点列表
        """
        try:
            # Master用户拥有所有权限
            if await self.is_master(user):
                async with self.SessionLocal() as session:
                    result = await session.execute(select(PermissionNodes.node_name))
                    all_nodes = list(result.scalars().all())
                    return all_nodes

            permissions = []

            async with self.SessionLocal() as session:
                # 获取所有权限节点
                result = await session.execute(select(PermissionNodes))
                all_nodes = result.scalars().all()

                for node in all_nodes:
                    # 检查用户是否有明确的权限设置
                    result = await session.execute(
                        select(UserPermissions).filter_by(
                            platform=user.platform, user_id=user.user_id, permission_node=node.node_name
                        )
                    )
                    user_perm = result.scalar_one_or_none()

                    if user_perm:
                        # 有明确设置，使用设置的值
                        if user_perm.granted:
                            permissions.append(node.node_name)
                    else:
                        # 没有明确设置，使用默认值
                        if node.default_granted:
                            permissions.append(node.node_name)

            return permissions

        except SQLAlchemyError as e:
            logger.error(f"获取用户权限时数据库错误: {e}")
            return []
        except Exception as e:
            logger.error(f"获取用户权限时发生未知错误: {e}")
            return []

    async def get_all_permission_nodes(self) -> list[PermissionNode]:
        """
        获取所有已注册的权限节点

        Returns:
            List[PermissionNode]: 权限节点列表
        """
        try:
            async with self.SessionLocal() as session:
                result = await session.execute(select(PermissionNodes))
                nodes = result.scalars().all()
                return [
                    PermissionNode(
                        node_name=node.node_name,
                        description=node.description,
                        plugin_name=node.plugin_name,
                        default_granted=node.default_granted,
                    )
                    for node in nodes
                ]

        except SQLAlchemyError as e:
            logger.error(f"获取所有权限节点时数据库错误: {e}")
            return []
        except Exception as e:
            logger.error(f"获取所有权限节点时发生未知错误: {e}")
            return []

    async def get_plugin_permission_nodes(self, plugin_name: str) -> list[PermissionNode]:
        """
        获取指定插件的所有权限节点

        Args:
            plugin_name: 插件名称

        Returns:
            List[PermissionNode]: 权限节点列表
        """
        try:
            async with self.SessionLocal() as session:
                result = await session.execute(select(PermissionNodes).filter_by(plugin_name=plugin_name))
                nodes = result.scalars().all()
                return [
                    PermissionNode(
                        node_name=node.node_name,
                        description=node.description,
                        plugin_name=node.plugin_name,
                        default_granted=node.default_granted,
                    )
                    for node in nodes
                ]

        except SQLAlchemyError as e:
            logger.error(f"获取插件权限节点时数据库错误: {e}")
            return []
        except Exception as e:
            logger.error(f"获取插件权限节点时发生未知错误: {e}")
            return []

    async def delete_plugin_permissions(self, plugin_name: str) -> bool:
        """
        删除指定插件的所有权限节点（用于插件卸载时清理）

        Args:
            plugin_name: 插件名称

        Returns:
            bool: 删除是否成功
        """
        try:
            async with self.SessionLocal() as session:
                # 获取插件的所有权限节点
                result = await session.execute(select(PermissionNodes).filter_by(plugin_name=plugin_name))
                plugin_nodes = result.scalars().all()
                node_names = [node.node_name for node in plugin_nodes]

                if not node_names:
                    logger.info(f"插件 {plugin_name} 没有注册任何权限节点")
                    return True

                # 删除用户权限记录
                result = await session.execute(
                    delete(UserPermissions).where(UserPermissions.permission_node.in_(node_names))
                )
                deleted_user_perms = result.rowcount

                # 删除权限节点
                result = await session.execute(delete(PermissionNodes).filter_by(plugin_name=plugin_name))
                deleted_nodes = result.rowcount

                await session.commit()
                logger.info(
                    f"已删除插件 {plugin_name} 的 {deleted_nodes} 个权限节点和 {deleted_user_perms} 条用户权限记录"
                )
                return True

        except SQLAlchemyError as e:
            logger.error(f"删除插件权限时数据库错误: {e}")
            return False
        except Exception as e:
            logger.error(f"删除插件权限时发生未知错误: {e}")
            return False

    async def get_users_with_permission(self, permission_node: str) -> list[tuple[str, str]]:
        """
        获取拥有指定权限的所有用户

        Args:
            permission_node: 权限节点名称

        Returns:
            List[Tuple[str, str]]: 用户列表，格式为 [(platform, user_id), ...]
        """
        try:
            users = []

            async with self.SessionLocal() as session:
                # 检查权限节点是否存在
                result = await session.execute(select(PermissionNodes).filter_by(node_name=permission_node))
                node = result.scalar_one_or_none()
                if not node:
                    logger.warning(f"权限节点 {permission_node} 不存在")
                    return users

                # 获取明确授权的用户
                result = await session.execute(
                    select(UserPermissions).filter_by(permission_node=permission_node, granted=True)
                )
                granted_users = result.scalars().all()

                users.extend((user_perm.platform, user_perm.user_id) for user_perm in granted_users)

                # 如果是默认授权的权限节点，还需要考虑没有明确设置的用户
                # 但这里我们只返回明确授权的用户，避免返回所有用户

            # 添加Master用户（他们拥有所有权限）
            users.extend(list(self._master_users))

            # 去重
            return list(set(users))

        except SQLAlchemyError as e:
            logger.error(f"获取拥有权限的用户时数据库错误: {e}")
            return []
        except Exception as e:
            logger.error(f"获取拥有权限的用户时发生未知错误: {e}")
            return []
