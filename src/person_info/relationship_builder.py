"""
关系构建器

性能优化：
- 使用 asyncio.to_thread() 将同步文件 I/O 异步化，避免阻塞事件循环
- 支持高并发场景下的关系构建
"""

import asyncio
import os
import pickle
import random
import time
import traceback
from typing import Any

from src.chat.utils.chat_message_builder import (
    get_raw_msg_before_timestamp_with_chat,
    get_raw_msg_by_timestamp_with_chat,
    get_raw_msg_by_timestamp_with_chat_inclusive,
    num_new_messages_since,
)
from src.common.logger import get_logger
from src.config.config import global_config
from src.person_info.person_info import PersonInfoManager, get_person_info_manager
from src.person_info.relationship_manager import get_relationship_manager

logger = get_logger("relationship_builder")

# 消息段清理配置
SEGMENT_CLEANUP_CONFIG = {
    "enable_cleanup": True,  # 是否启用清理
    "max_segment_age_days": 3,  # 消息段最大保存天数
    "max_segments_per_user": 10,  # 每用户最大消息段数
    "cleanup_interval_hours": 0.5,  # 清理间隔（小时）
}

MAX_MESSAGE_COUNT = 80  # 默认消息计数，旧的relation_frequency配置已移除


class RelationshipBuilder:
    """关系构建器

    独立运行的关系构建类，基于特定的chat_id进行工作
    负责跟踪用户消息活动、管理消息段、触发关系构建和印象更新
    """

    def __init__(self, chat_id: str):
        """初始化关系构建器

        Args:
            chat_id: 聊天ID
        """
        self.chat_id = chat_id
        # 新的消息段缓存结构：
        # {person_id: [{"start_time": float, "end_time": float, "last_msg_time": float, "message_count": int}, ...]}
        self.person_engaged_cache: dict[str, list[dict[str, Any]]] = {}

        # 持久化存储文件路径
        self.cache_file_path = os.path.join("data", "relationship", f"relationship_cache_{self.chat_id}.pkl")

        # 最后处理的消息时间，避免重复处理相同消息
        current_time = time.time()
        self.last_processed_message_time = current_time

        # 最后清理时间，用于定期清理老消息段
        self.last_cleanup_time = 0.0

        # log_prefix 将在异步方法中初始化
        self.log_prefix = f"[{self.chat_id}]"
        self._log_prefix_initialized = False

        # 加载持久化的缓存
        self._load_cache()

    async def _initialize_log_prefix(self):
        """异步初始化log_prefix"""
        if not self._log_prefix_initialized:
            try:
                from src.chat.message_receive.chat_stream import get_chat_manager

                chat_name = await get_chat_manager().get_stream_name(self.chat_id)
                self.log_prefix = f"[{chat_name}]"
            except Exception:
                self.log_prefix = f"[{self.chat_id}]"
            self._log_prefix_initialized = True

    # ================================
    # 缓存管理模块
    # 负责持久化存储、状态管理、缓存读写
    # ================================

    def _sync_load_cache_from_file(self) -> dict | None:
        """同步文件加载操作（在线程池中执行）"""
        if not os.path.exists(self.cache_file_path):
            return None
        with open(self.cache_file_path, "rb") as f:
            return pickle.load(f)

    def _load_cache(self):
        """从文件加载持久化的缓存（初始化时同步调用）"""
        if os.path.exists(self.cache_file_path):
            try:
                cache_data = self._sync_load_cache_from_file()
                if cache_data:
                    # 新格式：包含额外信息的缓存
                    self.person_engaged_cache = cache_data.get("person_engaged_cache", {})
                    self.last_processed_message_time = cache_data.get("last_processed_message_time", 0.0)
                    self.last_cleanup_time = cache_data.get("last_cleanup_time", 0.0)

                    logger.info(
                        f"{self.log_prefix} 成功加载关系缓存，包含 {len(self.person_engaged_cache)} 个用户，最后处理时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_processed_message_time)) if self.last_processed_message_time > 0 else '未设置'}"
                    )
            except Exception as e:
                logger.error(f"{self.log_prefix} 加载关系缓存失败: {e}")
                self.person_engaged_cache = {}
                self.last_processed_message_time = 0.0
        else:
            logger.info(f"{self.log_prefix} 关系缓存文件不存在，使用空缓存")

    def _sync_save_cache_to_file(self, cache_data: dict):
        """同步文件保存操作（在线程池中执行）"""
        os.makedirs(os.path.dirname(self.cache_file_path), exist_ok=True)
        with open(self.cache_file_path, "wb") as f:
            pickle.dump(cache_data, f)

    def _save_cache(self):
        """保存缓存到文件（同步版本，用于非异步上下文）"""
        try:
            cache_data = {
                "person_engaged_cache": self.person_engaged_cache,
                "last_processed_message_time": self.last_processed_message_time,
                "last_cleanup_time": self.last_cleanup_time,
            }
            self._sync_save_cache_to_file(cache_data)
            logger.debug(f"{self.log_prefix} 成功保存关系缓存")
        except Exception as e:
            logger.error(f"{self.log_prefix} 保存关系缓存失败: {e}")

    async def _save_cache_async(self):
        """保存缓存到文件（异步版本，不阻塞事件循环）"""
        try:
            cache_data = {
                "person_engaged_cache": self.person_engaged_cache,
                "last_processed_message_time": self.last_processed_message_time,
                "last_cleanup_time": self.last_cleanup_time,
            }
            # 使用 asyncio.to_thread 将同步 I/O 放到线程池执行
            await asyncio.to_thread(self._sync_save_cache_to_file, cache_data)
            logger.debug(f"{self.log_prefix} 成功保存关系缓存(异步)")
        except Exception as e:
            logger.error(f"{self.log_prefix} 保存关系缓存失败(异步): {e}")

    # ================================
    # 消息段管理模块
    # 负责跟踪用户消息活动、管理消息段、清理过期数据
    # ================================

    async def _update_message_segments(self, person_id: str, message_time: float):
        """更新用户的消息段

        Args:
            person_id: 用户ID
            message_time: 消息时间戳
        """
        if person_id not in self.person_engaged_cache:
            self.person_engaged_cache[person_id] = []

        segments = self.person_engaged_cache[person_id]

        # 获取该消息前5条消息的时间作为潜在的开始时间
        before_messages = await get_raw_msg_before_timestamp_with_chat(self.chat_id, message_time, limit=5)
        potential_start_time = before_messages[0]["time"] if before_messages else message_time

        # 如果没有现有消息段，创建新的
        if not segments:
            new_segment = {
                "start_time": potential_start_time,
                "end_time": message_time,
                "last_msg_time": message_time,
                "message_count": await self._count_messages_in_timerange(potential_start_time, message_time),
            }
            segments.append(new_segment)
            person_name = get_person_info_manager().get_value(person_id, "person_name") or person_id
            logger.debug(
                f"{self.log_prefix} 眼熟用户 {person_name} 在 {time.strftime('%H:%M:%S', time.localtime(potential_start_time))} - {time.strftime('%H:%M:%S', time.localtime(message_time))} 之间有 {new_segment['message_count']} 条消息"
            )
            # 使用异步版本保存缓存，避免阻塞事件循环
            await self._save_cache_async()
            return

        # 获取最后一个消息段
        last_segment = segments[-1]

        # 计算从最后一条消息到当前消息之间的消息数量（不包含边界）
        messages_between = await self._count_messages_between(last_segment["last_msg_time"], message_time)

        if messages_between <= 10:
            last_segment["end_time"] = message_time
            last_segment["last_msg_time"] = message_time
            last_segment["message_count"] = await self._count_messages_in_timerange(
                last_segment["start_time"], last_segment["end_time"]
            )
            logger.debug(f"{self.log_prefix} 延伸用户 {person_id} 的消息段: {last_segment}")
        else:
            current_time = time.time()
            after_messages = await get_raw_msg_by_timestamp_with_chat(
                self.chat_id, last_segment["last_msg_time"], current_time, limit=5, limit_mode="earliest"
            )
            if after_messages and len(after_messages) >= 5:
                last_segment["end_time"] = after_messages[4]["time"]

            last_segment["message_count"] = await self._count_messages_in_timerange(
                last_segment["start_time"], last_segment["end_time"]
            )

            new_segment = {
                "start_time": potential_start_time,
                "end_time": message_time,
                "last_msg_time": message_time,
                "message_count": await self._count_messages_in_timerange(potential_start_time, message_time),
            }
            segments.append(new_segment)
            person_info_manager = get_person_info_manager()
            person_name = await person_info_manager.get_value(person_id, "person_name") or person_id
            logger.debug(
                f"{self.log_prefix} 重新眼熟用户 {person_name} 创建新消息段（超过10条消息间隔）: {new_segment}"
            )

        # 使用异步版本保存缓存，避免阻塞事件循环
        await self._save_cache_async()

    async def _count_messages_in_timerange(self, start_time: float, end_time: float) -> int:
        """计算指定时间范围内的消息数量（包含边界）"""
        messages = await get_raw_msg_by_timestamp_with_chat_inclusive(self.chat_id, start_time, end_time)
        return len(messages)

    async def _count_messages_between(self, start_time: float, end_time: float) -> int:
        """计算两个时间点之间的消息数量（不包含边界），用于间隔检查"""
        return await num_new_messages_since(self.chat_id, start_time, end_time)

    def _get_total_message_count(self, person_id: str) -> int:
        """获取用户所有消息段的总消息数量"""
        if person_id not in self.person_engaged_cache:
            return 0

        return sum(segment["message_count"] for segment in self.person_engaged_cache[person_id])

    def _cleanup_old_segments(self) -> bool:
        """清理老旧的消息段"""
        if not SEGMENT_CLEANUP_CONFIG["enable_cleanup"]:
            return False

        current_time = time.time()

        # 检查是否需要执行清理（基于时间间隔）
        cleanup_interval_seconds = SEGMENT_CLEANUP_CONFIG["cleanup_interval_hours"] * 3600
        if current_time - self.last_cleanup_time < cleanup_interval_seconds:
            return False

        logger.info(f"{self.log_prefix} 开始执行老消息段清理...")

        cleanup_stats = {
            "users_cleaned": 0,
            "segments_removed": 0,
            "total_segments_before": 0,
            "total_segments_after": 0,
        }

        max_age_seconds = SEGMENT_CLEANUP_CONFIG["max_segment_age_days"] * 24 * 3600
        max_segments_per_user = SEGMENT_CLEANUP_CONFIG["max_segments_per_user"]

        users_to_remove = []

        for person_id, segments in self.person_engaged_cache.items():
            cleanup_stats["total_segments_before"] += len(segments)
            original_segment_count = len(segments)

            # 1. 按时间清理：移除过期的消息段
            segments_after_age_cleanup = []
            for segment in segments:
                segment_age = current_time - segment["end_time"]
                if segment_age <= max_age_seconds:
                    segments_after_age_cleanup.append(segment)
                else:
                    cleanup_stats["segments_removed"] += 1
                    logger.debug(
                        f"{self.log_prefix} 移除用户 {person_id} 的过期消息段: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(segment['start_time']))} - {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(segment['end_time']))}"
                    )

            # 2. 按数量清理：如果消息段数量仍然过多，保留最新的
            if len(segments_after_age_cleanup) > max_segments_per_user:
                # 按end_time排序，保留最新的
                segments_after_age_cleanup.sort(key=lambda x: x["end_time"], reverse=True)
                segments_removed_count = len(segments_after_age_cleanup) - max_segments_per_user
                cleanup_stats["segments_removed"] += segments_removed_count
                segments_after_age_cleanup = segments_after_age_cleanup[:max_segments_per_user]
                logger.debug(
                    f"{self.log_prefix} 用户 {person_id} 消息段数量过多，移除 {segments_removed_count} 个最老的消息段"
                )

            # 更新缓存
            if len(segments_after_age_cleanup) == 0:
                # 如果没有剩余消息段，标记用户为待移除
                users_to_remove.append(person_id)
            else:
                self.person_engaged_cache[person_id] = segments_after_age_cleanup
                cleanup_stats["total_segments_after"] += len(segments_after_age_cleanup)

            if original_segment_count != len(segments_after_age_cleanup):
                cleanup_stats["users_cleaned"] += 1

        # 移除没有消息段的用户
        for person_id in users_to_remove:
            del self.person_engaged_cache[person_id]
            logger.debug(f"{self.log_prefix} 移除用户 {person_id}：没有剩余消息段")

        # 更新最后清理时间
        self.last_cleanup_time = current_time

        # 保存缓存
        if cleanup_stats["segments_removed"] > 0 or users_to_remove:
            self._save_cache()
            logger.info(
                f"{self.log_prefix} 清理完成 - 影响用户: {cleanup_stats['users_cleaned']}, 移除消息段: {cleanup_stats['segments_removed']}, 移除用户: {len(users_to_remove)}"
            )
            logger.info(
                f"{self.log_prefix} 消息段统计 - 清理前: {cleanup_stats['total_segments_before']}, 清理后: {cleanup_stats['total_segments_after']}"
            )
        else:
            logger.debug(f"{self.log_prefix} 清理完成 - 无需清理任何内容")

        return cleanup_stats["segments_removed"] > 0 or len(users_to_remove) > 0

    def force_cleanup_user_segments(self, person_id: str) -> bool:
        """强制清理指定用户的所有消息段"""
        if person_id in self.person_engaged_cache:
            segments_count = len(self.person_engaged_cache[person_id])
            del self.person_engaged_cache[person_id]
            self._save_cache()
            logger.info(f"{self.log_prefix} 强制清理用户 {person_id} 的 {segments_count} 个消息段")
            return True
        return False

    def get_cache_status(self) -> str:
        # sourcery skip: merge-list-append, merge-list-appends-into-extend
        """获取缓存状态信息，用于调试和监控"""
        if not self.person_engaged_cache:
            return f"{self.log_prefix} 关系缓存为空"

        status_lines = [
            f"{self.log_prefix} 关系缓存状态：",
            f"最后处理消息时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_processed_message_time)) if self.last_processed_message_time > 0 else '未设置'}",
            f"最后清理时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_cleanup_time)) if self.last_cleanup_time > 0 else '未执行'}",
            f"总用户数：{len(self.person_engaged_cache)}",
            f"清理配置：{'启用' if SEGMENT_CLEANUP_CONFIG['enable_cleanup'] else '禁用'} (最大保存{SEGMENT_CLEANUP_CONFIG['max_segment_age_days']}天, 每用户最多{SEGMENT_CLEANUP_CONFIG['max_segments_per_user']}段)",
            "",
        ]

        for person_id, segments in self.person_engaged_cache.items():
            total_count = self._get_total_message_count(person_id)
            status_lines.append(f"用户 {person_id}:")
            status_lines.append(f"  总消息数：{total_count} ({total_count}/60)")
            status_lines.append(f"  消息段数：{len(segments)}")

            for i, segment in enumerate(segments):
                start_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(segment["start_time"]))
                end_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(segment["end_time"]))
                last_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(segment["last_msg_time"]))
                status_lines.append(
                    f"    段{i + 1}: {start_str} -> {end_str} (最后消息: {last_str}, 消息数: {segment['message_count']})"
                )
            status_lines.append("")

        return "\n".join(status_lines)

    # ================================
    # 主要处理流程
    # 统筹各模块协作、对外提供服务接口
    # ================================

    async def build_relation(self, immediate_build: str = "", max_build_threshold: int = MAX_MESSAGE_COUNT):
        """构建关系
        immediate_build: 立即构建关系，可选值为"all"或person_id
        """
        # 初始化log_prefix
        await self._initialize_log_prefix()

        self._cleanup_old_segments()
        current_time = time.time()

        if latest_messages := await get_raw_msg_by_timestamp_with_chat(
            self.chat_id,
            self.last_processed_message_time,
            current_time,
            limit=50,  # 获取自上次处理后的消息
        ):
            # 处理所有新的非bot消息
            for latest_msg in latest_messages:
                user_id = latest_msg.get("user_id")
                platform = latest_msg.get("user_platform") or latest_msg.get("chat_info_platform")
                msg_time = latest_msg.get("time", 0)

                if (
                    user_id
                    and platform
                    and user_id != global_config.bot.qq_account
                    and msg_time > self.last_processed_message_time
                ):
                    person_id = PersonInfoManager.get_person_id(platform, user_id)
                    await self._update_message_segments(person_id, msg_time)
                    logger.debug(
                        f"{self.log_prefix} 更新用户 {person_id} 的消息段，消息时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg_time))}"
                    )
                    self.last_processed_message_time = max(self.last_processed_message_time, msg_time)

        # 1. 检查是否有用户达到关系构建条件（总消息数达到45条）
        users_to_build_relationship = []
        for person_id, segments in self.person_engaged_cache.items():
            total_message_count = self._get_total_message_count(person_id)
            person_name = get_person_info_manager().get_value(person_id, "person_name") or person_id

            if total_message_count >= max_build_threshold or (
                total_message_count >= 5 and (immediate_build == person_id or immediate_build == "all")
            ):
                users_to_build_relationship.append(person_id)
                logger.info(
                    f"{self.log_prefix} 用户 {person_name} 满足关系构建条件，总消息数：{total_message_count}，消息段数：{len(segments)}"
                )
            elif total_message_count > 0:
                # 记录进度信息
                logger.debug(
                    f"{self.log_prefix} 用户 {person_name} 进度：{total_message_count}/60 条消息，{len(segments)} 个消息段"
                )

        # 2. 为满足条件的用户构建关系
        for person_id in users_to_build_relationship:
            segments = self.person_engaged_cache[person_id]
            # 异步执行关系构建（使用 asyncio 模块已在文件顶部导入）
            asyncio.create_task(self.update_impression_on_segments(person_id, self.chat_id, segments))  # noqa: RUF006
            # 移除已处理的用户缓存
            del self.person_engaged_cache[person_id]
            # 使用异步版本保存缓存，避免阻塞事件循环
            await self._save_cache_async()

    # ================================
    # 关系构建模块
    # 负责触发关系构建、整合消息段、更新用户印象
    # ================================

    async def update_impression_on_segments(self, person_id: str, chat_id: str, segments: list[dict[str, Any]]):
        """基于消息段更新用户印象"""
        original_segment_count = len(segments)
        logger.debug(f"开始为 {person_id} 基于 {original_segment_count} 个消息段更新印象")
        try:
            # 筛选要处理的消息段，每个消息段有10%的概率被丢弃
            segments_to_process = [s for s in segments if random.random() >= 0.1]

            # 如果所有消息段都被丢弃，但原来有消息段，则至少保留一个（最新的）
            if not segments_to_process and segments:
                segments.sort(key=lambda x: x["end_time"], reverse=True)
                segments_to_process.append(segments[0])
                logger.debug("随机丢弃了所有消息段，强制保留最新的一个以进行处理。")

            dropped_count = original_segment_count - len(segments_to_process)
            if dropped_count > 0:
                logger.debug(f"为 {person_id} 随机丢弃了 {dropped_count} / {original_segment_count} 个消息段")

            processed_messages = []

            # 对筛选后的消息段进行排序，确保时间顺序
            segments_to_process.sort(key=lambda x: x["start_time"])

            for segment in segments_to_process:
                start_time = segment["start_time"]
                end_time = segment["end_time"]
                start_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_time))

                # 获取该段的消息（包含边界）
                segment_messages = await get_raw_msg_by_timestamp_with_chat_inclusive(
                    self.chat_id, start_time, end_time
                )
                logger.debug(
                    f"消息段: {start_date} - {time.strftime('%Y-%m-%d %H:%M', time.localtime(end_time))}, 消息数: {len(segment_messages)}"
                )

                if segment_messages:
                    # 如果 processed_messages 不为空，说明这不是第一个被处理的消息段，在消息列表前添加间隔标识
                    if processed_messages:
                        # 创建一个特殊的间隔消息
                        gap_message = {
                            "time": start_time - 0.1,  # 稍微早于段开始时间
                            "user_id": "system",
                            "user_platform": "system",
                            "user_nickname": "系统",
                            "user_cardname": "",
                            "display_message": f"...（中间省略一些消息）{start_date} 之后的消息如下...",
                            "is_action_record": True,
                            "chat_info_platform": segment_messages[0].get("chat_info_platform", ""),
                            "chat_id": chat_id,
                        }
                        processed_messages.append(gap_message)

                    # 添加该段的所有消息
                    processed_messages.extend(segment_messages)

            if processed_messages:
                # 按时间排序所有消息（包括间隔标识）
                processed_messages.sort(key=lambda x: x["time"])

                logger.debug(f"为 {person_id} 获取到总共 {len(processed_messages)} 条消息（包含间隔标识）用于印象更新")
                relationship_manager = get_relationship_manager()

                # 调用原有的更新方法
                await relationship_manager.update_person_impression(
                    person_id=person_id, timestamp=time.time(), bot_engaged_messages=processed_messages
                )
            else:
                logger.info(f"没有找到 {person_id} 的消息段对应的消息，不更新印象")

        except Exception as e:
            logger.error(f"为 {person_id} 更新印象时发生错误: {e}")
            logger.error(traceback.format_exc())
