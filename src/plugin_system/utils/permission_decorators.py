"""
权限装饰器

提供方便的权限检查装饰器，用于插件命令和其他需要权限验证的地方。
"""

from collections.abc import Callable
from functools import wraps
from inspect import iscoroutinefunction

from src.chat.message_receive.chat_stream import ChatStream
from src.plugin_system.apis.logging_api import get_logger
from src.plugin_system.apis.permission_api import permission_api

logger = get_logger(__name__)


def require_permission(permission_node: str, deny_message: str | None = None, *, use_full_name: bool = False):
    """
    权限检查装饰器

    用于装饰需要特定权限才能执行的函数。如果用户没有权限，会发送拒绝消息并阻止函数执行。

    Args:
        permission_node: 所需的权限节点名称
        deny_message: 权限不足时的提示消息，如果为None则使用默认消息
        use_full_name: 是否明确声明传入的是完整的权限节点（默认False）
            - True: permission_node 已是完整节点名称，如 "plugins.plugin_name.action"，不会再添加前缀
            - False: permission_node 可以是短名称，如 "action"，装饰器会自动添加 "plugins.{plugin_name}." 前缀。
              若传入的值已以 "plugins." 开头，将被视为完整名称并跳过自动前缀（防止重复拼接）。

    Example:
        # 使用完整名称（传统方式）
        @require_permission("plugins.example.admin", use_full_name=True)
        async def admin_command(self):
            pass

        # 使用短名称（推荐方式）
        @require_permission("admin")
        async def admin_command(self):
            # 会自动转换为 "plugins.{当前插件名}.admin"
            pass
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 尝试从参数中提取 ChatStream 对象和插件名
            chat_stream = None
            plugin_name = None

            # 首先检查位置参数中的 ChatStream
            for arg in args:
                if isinstance(arg, ChatStream):
                    chat_stream = arg
                    break



            # 如果还没找到，检查是否是 PlusCommand 方法调用
            if args:
                instance = args[0]
                # 检查第一个参数是否有 chat_stream 属性（PlusCommand 实例）
                if hasattr(instance, "chat_stream") and chat_stream is None:
                    chat_stream = instance.chat_stream

                # 尝试获取插件名
                # 方法1: 从类名获取（通过组件注册表）
                if not plugin_name and hasattr(instance, "command_name"):
                    # 从组件注册表查找这个命令属于哪个插件
                    try:
                        from src.plugin_system.base.component_types import ComponentType
                        from src.plugin_system.core.component_registry import component_registry

                        component_info = component_registry.get_component_info(
                            instance.command_name, ComponentType.PLUS_COMMAND
                        )
                        if component_info:
                            plugin_name = component_info.plugin_name
                    except Exception:
                        pass

            if chat_stream is None:
                logger.error(f"权限装饰器无法找到 ChatStream 对象，函数: {func.__name__}")
                return None

            # 构建完整的权限节点名称（健壮处理，避免重复前缀）
            full_permission_node = permission_node
            if not use_full_name:
                # 如果传入的节点已以 "plugins." 开头，视为完整名称，跳过自动前缀
                if permission_node.startswith("plugins."):
                    logger.debug(
                        f"权限节点已为完整名称，跳过自动构建: {permission_node} (函数: {func.__name__})"
                    )
                else:
                    if not plugin_name:
                        logger.error(
                            f"权限装饰器无法推断插件名，函数: {func.__name__}，"
                            "请使用 use_full_name=True 或确保在插件类中调用"
                        )
                        return None

                    full_permission_node = f"plugins.{plugin_name}.{permission_node}"
                    logger.info(
                        f"自动构建权限节点: {permission_node} -> {full_permission_node} (插件: {plugin_name})"
                    )

            # 检查权限
            if not chat_stream.user_info or not chat_stream.user_info.user_id:
                logger.warning(f"权限检查失败：chat_stream 中缺少 user_info 或 user_id，函数: {func.__name__}")
                if func.__name__ == "execute" and hasattr(args[0], "send_text"):
                    return False, "无法获取用户信息", True
                return None

            # 记录权限检查开始
            logger.info(
                f"[权限检查] 开始检查权限 | 函数: {func.__name__} | 用户: {chat_stream.platform}:{chat_stream.user_info.user_id} | 权限节点: {full_permission_node}"
            )

            has_permission = await permission_api.check_permission(
                chat_stream.platform, chat_stream.user_info.user_id, full_permission_node
            )

            # 记录权限检查结果
            if has_permission:
                logger.info(
                    f"[权限检查] ✓ 权限验证通过 | 函数: {func.__name__} | 用户: {chat_stream.platform}:{chat_stream.user_info.user_id} | 权限节点: {full_permission_node}"
                )
            else:
                logger.warning(
                    f"[权限检查] ✗ 权限验证失败 | 函数: {func.__name__} | 用户: {chat_stream.platform}:{chat_stream.user_info.user_id} | 权限节点: {full_permission_node} | 原因: 用户无此权限"
                )

            if not has_permission:
                # 对于PlusCommand的execute方法，需要返回适当的元组
                if func.__name__ == "execute" and hasattr(args[0], "send_text"):
                    return False, "权限不足", True
                return None

            # 权限检查通过，执行原函数
            return await func(*args, **kwargs)

        if not iscoroutinefunction(func):
            logger.warning(f"函数 {func.__name__} 使用 require_permission 但非异步，已强制阻止执行")

            async def blocked(*_a, **_k):
                logger.error("同步函数不再支持权限装饰器，请改为 async def")
                return None

            return blocked
        return async_wrapper

    return decorator


def require_master(deny_message: str | None = None):
    """
    Master权限检查装饰器

    用于装饰只有Master用户才能执行的函数。

    Args:
        deny_message: 权限不足时的提示消息，如果为None则使用默认消息

    Example:
        @require_master()
        async def master_only_command(message: Message, chat_stream: ChatStream):
            # 只有Master用户才能执行
            pass
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 尝试从参数中提取 ChatStream 对象
            chat_stream = None

            # 首先检查位置参数中的 ChatStream
            for arg in args:
                if isinstance(arg, ChatStream):
                    chat_stream = arg
                    break

            # 如果在位置参数中没找到，尝试从关键字参数中查找
            if chat_stream is None:
                chat_stream = kwargs.get("chat_stream")

            # 如果还没找到，检查是否是 PlusCommand 方法调用
            if chat_stream is None and args:
                instance = args[0]
                # 检查第一个参数是否有 chat_stream 属性（PlusCommand 实例）
                if hasattr(instance, "chat_stream"):
                    chat_stream = instance.chat_stream
                # 兼容旧的 message.chat_stream 属性
                elif hasattr(instance, "message") and hasattr(instance.message, "chat_stream"):
                    chat_stream = instance.message.chat_stream

            if chat_stream is None:
                logger.error(f"Master权限装饰器无法找到 ChatStream 对象，函数: {func.__name__}")
                return None

            # 检查是否为Master用户
            if not chat_stream.user_info or not chat_stream.user_info.user_id:
                logger.warning(f"Master权限检查失败：chat_stream 中缺少 user_info 或 user_id，函数: {func.__name__}")
                if func.__name__ == "execute" and hasattr(args[0], "send_text"):
                    return False, "无法获取用户信息", True
                return None

            # 记录Master检查开始
            logger.info(
                f"[Master检查] 开始检查Master权限 | 函数: {func.__name__} | 用户: {chat_stream.platform}:{chat_stream.user_info.user_id}"
            )

            is_master = await permission_api.is_master(chat_stream.platform, chat_stream.user_info.user_id)

            # 记录Master检查结果
            if is_master:
                logger.info(
                    f"[Master检查] ✓ Master验证通过 | 函数: {func.__name__} | 用户: {chat_stream.platform}:{chat_stream.user_info.user_id}"
                )
            else:
                logger.warning(
                    f"[Master检查] ✗ Master验证失败 | 函数: {func.__name__} | 用户: {chat_stream.platform}:{chat_stream.user_info.user_id} | 原因: 用户不是Master"
                )

            if not is_master:
                if func.__name__ == "execute" and hasattr(args[0], "send_text"):
                    return False, "需要Master权限", True
                return None

            # 权限检查通过，执行原函数
            return await func(*args, **kwargs)

        if not iscoroutinefunction(func):
            logger.warning(f"函数 {func.__name__} 使用 require_master 但非异步，已强制阻止执行")

            async def blocked(*_a, **_k):
                logger.error("同步函数不再支持 require_master，请改为 async def")
                return None

            return blocked
        return async_wrapper

    return decorator


class PermissionChecker:
    """
    权限检查工具类

    提供一些便捷的权限检查方法，用于在代码中进行权限验证。
    """

    @staticmethod
    def check_permission(chat_stream: ChatStream, permission_node: str) -> bool:
        raise RuntimeError(
            "PermissionChecker.check_permission 已移除同步支持，请直接 await permission_api.check_permission"
        )

    @staticmethod
    async def is_master(chat_stream: ChatStream) -> bool:
        """
        检查用户是否为Master用户

        Args:
            chat_stream: 聊天流对象

        Returns:
            bool: 是否为Master用户
        """
        if not chat_stream.user_info or not chat_stream.user_info.user_id:
            logger.debug("[PermissionChecker.is_master] 用户信息缺失，返回False")
            return False
        
        logger.debug(
            f"[PermissionChecker.is_master] 检查用户 {chat_stream.platform}:{chat_stream.user_info.user_id}"
        )
        
        is_master = await permission_api.is_master(chat_stream.platform, chat_stream.user_info.user_id)
        
        logger.debug(
            f"[PermissionChecker.is_master] 用户 {chat_stream.platform}:{chat_stream.user_info.user_id} Master检查结果: {is_master}"
        )
        
        return is_master

    @staticmethod
    async def ensure_permission(chat_stream: ChatStream, permission_node: str, deny_message: str | None = None) -> bool:
        """
        确保用户拥有指定权限，如果没有权限会发送消息并返回False

        Args:
            chat_stream: 聊天流对象
            permission_node: 权限节点名称
            deny_message: 权限不足时的提示消息

        Returns:
            bool: 是否拥有权限
        """
        if not chat_stream.user_info or not chat_stream.user_info.user_id:
            logger.debug("[PermissionChecker.ensure_permission] 用户信息缺失，返回False")
            return False
        
        logger.debug(
            f"[PermissionChecker.ensure_permission] 检查用户 {chat_stream.platform}:{chat_stream.user_info.user_id} 权限节点: {permission_node}"
        )
        
        has_permission = await permission_api.check_permission(
            chat_stream.platform, chat_stream.user_info.user_id, permission_node
        )
        
        logger.debug(
            f"[PermissionChecker.ensure_permission] 用户 {chat_stream.platform}:{chat_stream.user_info.user_id} 权限节点: {permission_node} 检查结果: {has_permission}"
        )

        return has_permission

    @staticmethod
    async def ensure_master(chat_stream: ChatStream, deny_message: str | None = None) -> bool:
        """
        确保用户为Master用户，如果不是会发送消息并返回False

        Args:
            chat_stream: 聊天流对象
            deny_message: 权限不足时的提示消息

        Returns:
            bool: 是否为Master用户
        """
        logger.debug(
            f"[PermissionChecker.ensure_master] 开始检查用户 {chat_stream.platform if chat_stream.user_info else 'unknown'}:{chat_stream.user_info.user_id if chat_stream.user_info else 'unknown'}"
        )
        
        is_master = await PermissionChecker.is_master(chat_stream)
        
        logger.debug(
            f"[PermissionChecker.ensure_master] 用户 {chat_stream.platform if chat_stream.user_info else 'unknown'}:{chat_stream.user_info.user_id if chat_stream.user_info else 'unknown'} Master检查结果: {is_master}"
        )

        return is_master
