"""
统一消息处理器 (Message Handler)

利用 mofox_wire.MessageRuntime 的路由功能，简化消息处理链条：

1. 使用 @runtime.on_message() 装饰器注册按消息类型路由的处理器
2. 使用 before_hook 进行消息预处理（ID标准化、过滤等）
3. 使用 after_hook 进行消息后处理（存储、情绪更新等）
4. 使用 error_hook 统一处理异常

消息流向：
  适配器 → CoreSinkManager → MessageRuntime
                ↓
        [before_hook] 消息预处理、过滤
                ↓
        [on_message] 按类型路由处理（命令、普通消息等）
                ↓
        [after_hook] 存储、情绪更新等
                ↓
        回复生成 → CoreSinkManager.send_outgoing() → 适配器

重构说明（2025-11）：
- 移除手动的消息处理链，改用 MessageRuntime 路由
- MessageHandler 变成处理器注册器，在初始化时注册各种处理器
- 利用 runtime 的钩子机制简化前置/后置处理
"""

from __future__ import annotations

import os
import re
import traceback
from typing import TYPE_CHECKING, Any, ClassVar, cast

from mofox_wire import MessageEnvelope, MessageRuntime

from src.chat.message_manager import message_manager
from src.chat.message_receive.storage import MessageStorage
from src.chat.utils.utils import is_mentioned_bot_in_message
from src.common.data_models.database_data_model import DatabaseGroupInfo, DatabaseMessages, DatabaseUserInfo
from src.common.logger import get_logger
from src.config.config import global_config
from src.mood.mood_manager import mood_manager
from src.plugin_system.base import BaseCommand, EventType
from src.plugin_system.core import component_registry, event_manager, global_announcement_manager

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream
    from src.common.core_sink_manager import CoreSinkManager

logger = get_logger("message_handler")

# 项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# 预编译的正则表达式缓存（避免重复编译）
_compiled_regex_cache: dict[str, re.Pattern] = {}

# 硬编码过滤关键词（缓存到全局变量，避免每次创建列表）
_MEDIA_FAILURE_KEYWORDS = frozenset(["[表情包(描述生成失败)]", "[图片(描述生成失败)]"])

def _get_compiled_pattern(pattern: str) -> re.Pattern | None:
    """获取编译的正则表达式，使用缓存避免重复编译"""
    if pattern not in _compiled_regex_cache:
        try:
            _compiled_regex_cache[pattern] = re.compile(pattern)
        except re.error as e:
            logger.warning(f"正则表达式编译失败: {pattern}, 错误: {e}")
            return None
    return _compiled_regex_cache.get(pattern)

def _check_ban_words(text: str, chat: "ChatStream", userinfo) -> bool:
    """检查消息是否包含过滤词"""
    if global_config is None:
        return False
    for word in global_config.message_receive.ban_words:
        if word in text:
            chat_name = chat.group_info.group_name if chat.group_info else "私聊"
            logger.info(f"[{chat_name}]{userinfo.user_nickname}:{text}")
            logger.info(f"[过滤词识别]消息中含有{word}，filtered")
            return True
    return False
def _check_ban_regex(text: str, chat: "ChatStream", userinfo) -> bool:
    """检查消息是否匹配过滤正则表达式 - 优化版本使用预编译缓存"""
    if global_config is None:
        return False

    for pattern in global_config.message_receive.ban_msgs_regex:
        compiled_pattern = _get_compiled_pattern(pattern)
        if compiled_pattern and compiled_pattern.search(text):
            chat_name = chat.group_info.group_name if chat.group_info else "私聊"
            logger.info(f"[{chat_name}]{userinfo.user_nickname}:{text}")
            logger.info(f"[正则表达式过滤]消息匹配到{pattern}，filtered")
            return True
    return False


class MessageHandler:
    """
    统一消息处理器

    利用 MessageRuntime 的路由功能，将消息处理逻辑注册为路由和钩子。

    架构说明：
    - 在 register_handlers() 中向 MessageRuntime 注册各种处理器
    - 使用 @runtime.on_message(message_type=...) 按消息类型路由
    - 使用 before_hook 进行消息预处理
    - 使用 after_hook 进行消息后处理
    - 使用 error_hook 统一处理异常

    主要功能：
    1. 消息预处理：ID标准化、过滤检查
    2. 适配器响应处理：处理 adapter_response 类型消息
    3. 命令处理：PlusCommand 和 BaseCommand
    4. 普通消息处理：触发事件、存储、情绪更新
    """

    # 类级别缓存：命令查询结果缓存（减少重复查询）
    _plus_command_cache: ClassVar[dict[str, Any]] = {}
    _base_command_cache: ClassVar[dict[str, Any]] = {}

    def __init__(self):
        self._started = False
        self._message_manager_started = False
        self._core_sink_manager: CoreSinkManager | None = None
        self._shutting_down = False
        self._runtime: MessageRuntime | None = None

    def set_core_sink_manager(self, manager: "CoreSinkManager") -> None:
        """设置 CoreSinkManager 引用"""
        self._core_sink_manager = manager

    async def _get_or_create_chat_stream(
        self, platform: str, user_info: dict | None, group_info: dict | None
    ) -> "ChatStream":
        """获取或创建聊天流 - 统一方法"""
        from src.chat.message_receive.chat_stream import get_chat_manager

        return await get_chat_manager().get_or_create_stream(
            platform=platform,
            user_info=DatabaseUserInfo.from_dict(cast(dict[str, Any], user_info)) if user_info else None,
            group_info=DatabaseGroupInfo.from_dict(cast(dict[str, Any], group_info)) if group_info else None,
        )

    async def _process_message_to_database(
        self, envelope: MessageEnvelope, chat: "ChatStream", skip_media_processing: bool = False
    ) -> DatabaseMessages:
        """将消息信封转换为 DatabaseMessages - 统一方法"""
        from src.chat.message_receive.message_processor import process_message_from_dict

        message = await process_message_from_dict(
            message_dict=envelope,
            stream_id=chat.stream_id,
            platform=chat.platform,
            skip_media_processing=skip_media_processing
        )

        # 填充聊天流时间信息
        message.chat_info.create_time = chat.create_time
        message.chat_info.last_active_time = chat.last_active_time

        return message

    def register_handlers(self, runtime: MessageRuntime) -> None:
        """
        向 MessageRuntime 注册消息处理器和钩子

        这是核心方法，在系统初始化时调用，将所有处理逻辑注册到 runtime。

        Args:
            runtime: MessageRuntime 实例
        """
        self._runtime = runtime

        # 注册前置钩子：消息预处理和过滤
        runtime.register_before_hook(self._before_hook)

        # 注册错误钩子：统一异常处理
        runtime.register_error_hook(self._error_hook)

        # 注册适配器响应处理器（最高优先级）
        def _is_adapter_response(env: MessageEnvelope) -> bool:
            segment = env.get("message_segment")
            if isinstance(segment, dict):
                return segment.get("type") == "adapter_response"
            return False

        runtime.add_route(
            predicate=_is_adapter_response,
            handler=self._handle_adapter_response_route,
            name="adapter_response_handler",
            priority=100
        )

        # 注册 notice 消息处理器（处理通知消息，如戳一戳、禁言等）
        def _is_notice_message(env: MessageEnvelope) -> bool:
            """检查是否为 notice 消息"""
            message_info = env.get("message_info")
            if not isinstance(message_info, dict):
                return False
            additional_config = message_info.get("additional_config")
            if isinstance(additional_config, dict):
                return additional_config.get("is_notice", False)
            return False

        runtime.add_route(
            predicate=_is_notice_message,
            handler=self._handle_notice_message,
            name="notice_message_handler",
            priority=90
        )

        # 注册默认消息处理器（处理所有其他消息）
        runtime.add_route(
            predicate=lambda _: True,  # 匹配所有消息
            handler=self._handle_normal_message,
            name="default_message_handler",
            priority=50
        )

        logger.info("MessageHandler 已向 MessageRuntime 注册处理器和钩子")

    async def ensure_started(self) -> None:
        """确保所有依赖任务已启动"""
        if not self._started:
            logger.debug("确保 MessageHandler 所有任务已启动")

            # 启动消息管理器
            if not self._message_manager_started:
                await message_manager.start()
                self._message_manager_started = True
                logger.info("消息管理器已启动")

            self._started = True

    async def _before_hook(self, envelope: MessageEnvelope) -> None:
        """
        前置钩子：消息预处理

        1. 标准化 ID 为字符串
        2. 检查是否为 echo 消息（自身发送的消息上报）
        3. 附加预处理数据到 envelope（chat_stream, message 等）
        """
        if self._shutting_down:
            raise UserWarning("系统正在关闭，拒绝处理消息")

        # 确保依赖服务已启动
        await self.ensure_started()

        # 提取消息信息
        message_info = envelope.get("message_info")
        if not isinstance(message_info, dict):
            logger.debug(
                "收到缺少 message_info 的消息，已跳过。可用字段: %s",
                ", ".join(envelope.keys()),
            )
            raise UserWarning("消息缺少 message_info")

        # 标准化 ID 为字符串
        if message_info.get("group_info") is not None:
            message_info["group_info"]["group_id"] = str(  # type: ignore
                message_info["group_info"]["group_id"]  # type: ignore
            )
        if message_info.get("user_info") is not None:
            message_info["user_info"]["user_id"] = str(  # type: ignore
                message_info["user_info"]["user_id"]  # type: ignore
            )

        # 处理自身消息上报（echo）
        additional_config = message_info.get("additional_config", {})
        if additional_config and isinstance(additional_config, dict):
            sent_message = additional_config.get("echo", False)
            if sent_message:
                # 更新消息ID
                await MessageStorage.update_message(dict(envelope))
                raise UserWarning("Echo 消息已处理")


    async def _error_hook(self, envelope: MessageEnvelope, exc: BaseException) -> None:
        """
        错误钩子：统一异常处理
        """
        if isinstance(exc, UserWarning):
            # UserWarning 是预期的流程控制，只记录 debug 日志
            logger.debug(f"消息处理流程控制: {exc}")
        else:
            message_id = envelope.get("message_info", {}).get("message_id", "UNKNOWN")
            logger.error(f"处理消息 {message_id} 时出错: {exc}")

    async def _handle_adapter_response_route(self, envelope: MessageEnvelope) -> MessageEnvelope | None:
        """
        处理适配器响应消息的路由处理器
        """
        message_segment = envelope.get("message_segment")
        if message_segment and isinstance(message_segment, dict):
            seg_data = message_segment.get("data")
            if isinstance(seg_data, dict):
                await self._handle_adapter_response(seg_data)
        return None

    async def _handle_notice_message(self, envelope: MessageEnvelope) -> MessageEnvelope | None:
        """
        Notice 消息专属处理器：处理通知消息（戳一戳、禁言、表情回复等）

        Notice 消息与普通消息不同，它们不需要完整的消息处理链：
        1. 不触发命令处理
        2. 存储到数据库
        3. 添加到全局 Notice 管理器
        4. 触发 ON_NOTICE_RECEIVED 事件供插件监听
        """
        try:
            message_info = envelope.get("message_info")
            if not isinstance(message_info, dict):
                logger.debug("Notice 消息缺少 message_info，已跳过")
                return None

            # 获取 notice 配置
            additional_config = message_info.get("additional_config", {})
            if not isinstance(additional_config, dict):
                additional_config = {}

            notice_type = additional_config.get("notice_type", "unknown")
            is_public_notice = additional_config.get("is_public_notice", False)

            # 获取用户和群组信息
            group_info = message_info.get("group_info")
            user_info = message_info.get("user_info")

            if not user_info:
                logger.debug("Notice 消息缺少用户信息，已跳过")
                return None

            # 获取或创建聊天流
            platform = message_info.get("platform", "unknown")
            chat = await self._get_or_create_chat_stream(platform, user_info, group_info)

            # 将消息信封转换为 DatabaseMessages
            message = await self._process_message_to_database(envelope, chat)

            # 标记为 notice 消息
            message.is_notify = True
            message.notice_type = notice_type

            # 打印接收日志
            chat_name = chat.group_info.group_name if chat.group_info else "私聊"
            user_nickname = message.user_info.user_nickname if message.user_info else "未知用户"
            logger.info(f"[Notice][{chat_name}][{notice_type}] {user_nickname}: {message.processed_plain_text}\u001b[0m")

            # 存储消息到数据库
            await MessageStorage.store_message(message, chat)

            # 添加到全局 Notice 管理器
            await self._add_notice_to_manager(message, chat.stream_id, is_public_notice, notice_type)

            # 触发 notice 事件（可供插件监听）
            await event_manager.trigger_event(
                EventType.ON_NOTICE_RECEIVED,
                permission_group="SYSTEM",
                message=message,
                notice_type=notice_type,
                chat_stream=chat,
            )

            # 根据配置决定是否触发聊天流程
            if global_config and global_config.notice and global_config.notice.enable_notice_trigger_chat:
                logger.debug(f"Notice 消息将触发聊天流程: {chat.stream_id}")
                # 添加到聊天流上下文，触发正常的消息处理流程
                from src.chat.message_manager.distribution_manager import stream_loop_manager
                await stream_loop_manager.start_stream_loop(chat.stream_id)
                await chat.context.add_message(message)
            else:
                logger.debug(f"Notice 消息不触发聊天流程: {chat.stream_id}")

            return None

        except Exception as e:
            logger.error(f"处理 Notice 消息时出错: {e}")
            logger.error(traceback.format_exc())
            return None

    async def _add_notice_to_manager(
        self,
        message: DatabaseMessages,
        stream_id: str,
        is_public_notice: bool,
        notice_type: str
    ) -> None:
        """将 notice 消息添加到全局 Notice 管理器

        Args:
            message: 数据库消息对象
            stream_id: 聊天流ID
            is_public_notice: 是否为公共 notice
            notice_type: notice 类型
        """
        try:
            from src.chat.message_manager.global_notice_manager import NoticeScope

            # 确定作用域
            scope = NoticeScope.PUBLIC if is_public_notice else NoticeScope.STREAM

            # 获取 TTL
            ttl = self._get_notice_ttl(notice_type)

            # 添加到全局 notice 管理器
            success = message_manager.notice_manager.add_notice(
                message=message,
                scope=scope,
                target_stream_id=stream_id if scope == NoticeScope.STREAM else None,
                ttl=ttl
            )

            if success:
                logger.debug(
                    f"Notice 消息已添加到全局管理器: message_id={message.message_id}, "
                    f"scope={scope.value}, stream={stream_id}, ttl={ttl}s"
                )
            else:
                logger.warning(f"Notice 消息添加失败: message_id={message.message_id}")

        except Exception as e:
            logger.error(f"添加 notice 到管理器失败: {e}")

    def _get_notice_ttl(self, notice_type: str) -> int:
        """根据 notice 类型获取生存时间（秒）

        Args:
            notice_type: notice 类型

        Returns:
            int: TTL 秒数
        """
        ttl_mapping = {
            "poke": 1800,  # 戳一戳 30 分钟
            "emoji_like": 3600,  # 表情回复 1 小时
            "group_ban": 7200,  # 禁言 2 小时
            "group_lift_ban": 7200,  # 解禁 2 小时
            "group_whole_ban": 3600,  # 全体禁言 1 小时
            "group_whole_lift_ban": 3600,  # 解除全体禁言 1 小时
            "group_upload": 3600,  # 群文件上传 1 小时
        }
        return ttl_mapping.get(notice_type, 3600)  # 默认 1 小时

    async def _handle_normal_message(self, envelope: MessageEnvelope) -> MessageEnvelope | None:
        """
        默认消息处理器：处理普通消息

        1. 获取或创建聊天流
        2. 转换为 DatabaseMessages
        3. 过滤检查
        4. 命令处理
        5. 触发事件、存储、情绪更新
        """
        try:
            message_info = envelope.get("message_info")
            if not isinstance(message_info, dict):
                return None

            # 获取用户和群组信息
            group_info = message_info.get("group_info")
            user_info = message_info.get("user_info")

            if not user_info and not group_info:
                logger.debug("消息缺少用户信息，已跳过处理")
                return None

            # 获取或创建聊天流
            platform = message_info.get("platform", "unknown")
            chat = await self._get_or_create_chat_stream(platform, user_info, group_info)

            # --- 方案二：提前过滤静默群组的媒体处理 ---
            skip_media = False
            is_group = bool(group_info)
            if global_config and is_group:
                group_id_str = str(group_info.get("group_id", "")) # type: ignore
                if group_id_str in global_config.message_receive.mute_group_list:
                    # 检查是否提及机器人 (增强版预检)
                    is_mentioned = False
                    message_segment = envelope.get("message_segment", [])
                    if isinstance(message_segment, dict):
                        message_segment = [message_segment]
                    
                    bot_qq = str(global_config.bot.qq_account)
                    
                    for seg in message_segment:
                        s_type = seg.get("type")
                        s_data = seg.get("data")
                        
                        # 1. 显式提及标志
                        if s_type == "mention_bot" and s_data:
                            is_mentioned = True
                            break
                        
                        # 2. 检查 AT 段
                        if s_type == "at" and isinstance(s_data, str):
                            # 格式可能是 "nickname:qq" 或纯 "qq"
                            if bot_qq in s_data:
                                is_mentioned = True
                                break
                        
                        # 3. 检查回复段 (如果回复的是机器人)
                        if s_type == "reply" and str(s_data) == message_info.get("self_id"):
                            is_mentioned = True
                            break
                    
                    if not is_mentioned:
                        # 是静默群且没被 @，启用跳过媒体处理
                        skip_media = True
                        logger.debug(f"[MessageHandler] 群组 {group_id_str} 处于静默模式且未被@，将跳过昂贵的媒体处理")

            # 将消息信封转换为 DatabaseMessages
            message = await self._process_message_to_database(envelope, chat, skip_media_processing=skip_media)

            # 注册消息到聊天管理器
            from src.chat.message_receive.chat_stream import get_chat_manager
            get_chat_manager().register_message(message)

            # 检测是否提及机器人
            message.is_mentioned, _ = is_mentioned_bot_in_message(message)

            # 打印接收日志
            chat_name = chat.group_info.group_name if chat.group_info else "私聊"
            user_nickname = message.user_info.user_nickname if message.user_info else "未知用户"
            logger.info(f"[{chat_name}]{user_nickname}:{message.processed_plain_text}\u001b[0m")

            # 硬编码过滤
            processed_text = message.processed_plain_text or ""
            if any(keyword in processed_text for keyword in _MEDIA_FAILURE_KEYWORDS):
                logger.info(f"[硬编码过滤] 检测到媒体内容处理失败（{processed_text}），消息被静默处理。")
                return None

            # 过滤检查
            raw_text = message.display_message or message.processed_plain_text or ""
            if _check_ban_words(processed_text, chat, message.user_info) or _check_ban_regex(
                raw_text, chat, message.user_info
            ):
                return None

            # 处理命令和后续流程
            await self._process_commands(message, chat)

            # 触发消息事件
            result = await event_manager.trigger_event(
                EventType.ON_MESSAGE,
                permission_group="SYSTEM",
                message=message
            )
            if result and not result.all_continue_process():
                raise UserWarning(
                    f"插件{result.get_summary().get('stopped_handlers', '')}于消息到达时取消了消息处理"
                )

            # 预处理消息
            await self._preprocess_message(message, chat)


        except UserWarning as uw:
            logger.info(str(uw))
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            logger.error(traceback.format_exc())

        return None


    async def _process_commands(self, message: DatabaseMessages, chat: "ChatStream") -> None:
        """处理命令和继续消息流程"""
        try:
            # 首先尝试 PlusCommand
            is_plus_command, plus_cmd_result, plus_continue_process = await self._process_plus_commands(message, chat)

            if is_plus_command and not plus_continue_process:
                await MessageStorage.store_message(message, chat)
                logger.info(f"PlusCommand处理完成，跳过后续消息处理: {plus_cmd_result}")
                return

            # 如果不是 PlusCommand，尝试传统 BaseCommand
            if not is_plus_command:
                is_command, cmd_result, continue_process = await self._process_base_commands(message, chat)

                if is_command and not continue_process:
                    await MessageStorage.store_message(message, chat)
                    logger.info(f"命令处理完成，跳过后续消息处理: {cmd_result}")
                    return

        except UserWarning as uw:
            logger.info(str(uw))
        except Exception as e:
            logger.error(f"处理命令时出错: {e}")
            logger.error(traceback.format_exc())

    async def _process_plus_commands(
        self,
        message: DatabaseMessages,
        chat: "ChatStream"
    ) -> tuple[bool, Any, bool]:
        """处理 PlusCommand 系统"""
        try:
            text = message.processed_plain_text or ""

            # 获取配置的命令前缀
            if global_config is None:
                return False, None, True
            prefixes = global_config.command.command_prefixes

            # 检查是否以任何前缀开头
            matched_prefix = None
            for prefix in prefixes:
                if text.startswith(prefix):
                    matched_prefix = prefix
                    break

            if not matched_prefix:
                return False, None, True

            # 移除前缀
            command_part = text[len(matched_prefix):].strip()

            # 分离命令名和参数
            parts = command_part.split(None, 1)
            if not parts:
                return False, None, True

            command_word = parts[0].lower()
            args_text = parts[1] if len(parts) > 1 else ""

            # 查找匹配的 PlusCommand
            plus_command_registry = component_registry.get_plus_command_registry()
            matching_commands = []

            for plus_command_name, plus_command_class in plus_command_registry.items():
                plus_command_info = component_registry.get_registered_plus_command_info(plus_command_name)
                if not plus_command_info:
                    continue

                all_commands = [plus_command_name.lower()] + [
                    alias.lower() for alias in plus_command_info.command_aliases
                ]
                if command_word in all_commands:
                    matching_commands.append((plus_command_class, plus_command_info, plus_command_name))

            if not matching_commands:
                return False, None, True

            # 按优先级排序
            if len(matching_commands) > 1:
                matching_commands.sort(key=lambda x: x[1].priority, reverse=True)

            plus_command_class, plus_command_info, plus_command_name = matching_commands[0]

            # 检查是否被禁用
            if (
                chat
                and chat.stream_id
                and plus_command_name in global_announcement_manager.get_disabled_chat_commands(chat.stream_id)
            ):
                logger.info("用户禁用的PlusCommand，跳过处理")
                return False, None, True

            message.is_command = True

            # 获取插件配置
            plugin_config = component_registry.get_plugin_config(plus_command_name)

            # 创建实例
            plus_command_instance = plus_command_class(message, plugin_config)
            setattr(plus_command_instance, "chat_stream", chat)

            try:
                if not plus_command_instance.is_chat_type_allowed():
                    is_group = chat.group_info is not None
                    logger.info(
                        f"PlusCommand {plus_command_class.__name__} 不支持当前聊天类型: {'群聊' if is_group else '私聊'}"
                    )
                    return False, None, True

                from src.plugin_system.base.command_args import CommandArgs
                command_args = CommandArgs(args_text)
                plus_command_instance.args = command_args

                success, response, intercept_message = await plus_command_instance.execute(command_args)

                if success:
                    logger.info(f"PlusCommand执行成功: {plus_command_class.__name__} (拦截: {intercept_message})")
                else:
                    logger.warning(f"PlusCommand执行失败: {plus_command_class.__name__} - {response}")

                return True, response, not intercept_message

            except Exception as e:
                logger.error(f"执行PlusCommand时出错: {plus_command_class.__name__} - {e}")
                logger.error(traceback.format_exc())

                try:
                    await plus_command_instance.send_text(f"命令执行出错: {e!s}")
                except Exception:
                    pass

                return True, str(e), False

        except Exception as e:
            logger.error(f"处理PlusCommand时出错: {e}")
            return False, None, True

    async def _process_base_commands(
        self,
        message: DatabaseMessages,
        chat: "ChatStream"
    ) -> tuple[bool, Any, bool]:
        """处理传统 BaseCommand 系统"""
        try:
            text = message.processed_plain_text or ""

            command_result = component_registry.find_command_by_text(text)
            if command_result:
                command_class, matched_groups, command_info = command_result
                plugin_name = command_info.plugin_name
                command_name = command_info.name

                if (
                    chat
                    and chat.stream_id
                    and command_name in global_announcement_manager.get_disabled_chat_commands(chat.stream_id)
                ):
                    logger.info("用户禁用的命令，跳过处理")
                    return False, None, True

                message.is_command = True

                plugin_config = component_registry.get_plugin_config(plugin_name)
                command_instance: BaseCommand = command_class(message, plugin_config)
                command_instance.set_matched_groups(matched_groups)
                setattr(command_instance, "chat_stream", chat)

                try:
                    if not command_instance.is_chat_type_allowed():
                        is_group = chat.group_info is not None
                        logger.info(
                            f"命令 {command_class.__name__} 不支持当前聊天类型: {'群聊' if is_group else '私聊'}"
                        )
                        return False, None, True

                    success, response, intercept_message = await command_instance.execute()

                    if success:
                        logger.info(f"命令执行成功: {command_class.__name__} (拦截: {intercept_message})")
                    else:
                        logger.warning(f"命令执行失败: {command_class.__name__} - {response}")

                    return True, response, not intercept_message

                except Exception as e:
                    logger.error(f"执行命令时出错: {command_class.__name__} - {e}")
                    logger.error(traceback.format_exc())

                    try:
                        await command_instance.send_text(f"命令执行出错: {e!s}")
                    except Exception:
                        pass

                    return True, str(e), False

            return False, None, True

        except Exception as e:
            logger.error(f"处理命令时出错: {e}")
            return False, None, True

    async def _preprocess_message(self, message: DatabaseMessages, chat: "ChatStream") -> None:
        """预处理消息：存储、情绪更新等"""
        try:
            if global_config is None:
                return

            group_info = chat.group_info

            # 检查是否需要处理消息
            should_process_in_manager = True
            if group_info and str(group_info.group_id) in global_config.message_receive.mute_group_list:
                # 只有未提及机器人的消息才会被静默处理
                if not message.is_mentioned:
                    is_image_or_emoji = message.is_picid or message.is_emoji
                    if not is_image_or_emoji:
                        logger.debug(
                            f"群组 {group_info.group_id} 在静默列表中，且未提及机器人，跳过消息处理"
                        )
                        should_process_in_manager = False
                    else:
                        logger.debug(f"群组 {group_info.group_id} 在静默列表中，图片消息未提及机器人，静默处理")
                        should_process_in_manager = False
                else:
                    # 如果提到了机器人，即使在静默群组中也要处理
                    logger.info(f"[MessageHandler] 静默群组 {group_info.group_id} 中检测到提及机器人的消息，允许处理")

            if should_process_in_manager:
                await message_manager.add_message(chat.stream_id, message)
                logger.debug(f"消息已添加到消息管理器: {chat.stream_id}")

            # 存储消息
            try:
                await MessageStorage.store_message(message, chat)
            except Exception as e:
                logger.error(f"存储消息到数据库失败: {e}")
                traceback.print_exc()

            # 情绪系统更新
            try:
                if global_config.mood.enable_mood:
                    interest_rate = message.interest_value or 0.0
                    logger.debug(f"开始更新情绪状态，兴趣度: {interest_rate:.2f}")

                    chat_mood = mood_manager.get_mood_by_chat_id(chat.stream_id)
                    await chat_mood.update_mood_by_message(message, interest_rate)
                    logger.debug("情绪状态更新完成")
            except Exception as e:
                logger.error(f"更新情绪状态失败: {e}")
                traceback.print_exc()

        except Exception as e:
            logger.error(f"预处理消息失败: {e}")
            traceback.print_exc()

    async def _handle_adapter_response(self, seg_data: dict | None) -> None:
        """处理适配器命令响应"""
        try:
            from src.plugin_system.apis.send_api import put_adapter_response

            if isinstance(seg_data, dict):
                request_id = seg_data.get("request_id")
                response_data = seg_data.get("response")
            else:
                request_id = None
                response_data = None

            if request_id and response_data:
                logger.debug(f"收到适配器响应，request_id={request_id}")
                put_adapter_response(request_id, response_data)
            else:
                logger.warning(
                    f"适配器响应消息格式不正确: request_id={request_id}, response_data={response_data}"
                )

        except Exception as e:
            logger.error(f"处理适配器响应时出错: {e}")

    async def shutdown(self) -> None:
        """关闭消息处理器"""
        self._shutting_down = True
        logger.info("MessageHandler 正在关闭...")


# 全局单例
_message_handler: MessageHandler | None = None


def get_message_handler() -> MessageHandler:
    """获取 MessageHandler 单例"""
    global _message_handler
    if _message_handler is None:
        _message_handler = MessageHandler()
    return _message_handler


async def shutdown_message_handler() -> None:
    """关闭 MessageHandler"""
    global _message_handler
    if _message_handler:
        await _message_handler.shutdown()
        _message_handler = None


__all__ = [
    "MessageHandler",
    "get_message_handler",
    "shutdown_message_handler",
]
