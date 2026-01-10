import asyncio
import collections
import re
import time
import traceback
from collections import deque
from typing import TYPE_CHECKING, Any, Optional, cast

import orjson
from sqlalchemy import desc, insert, select, update
from sqlalchemy.engine import CursorResult

from src.common.data_models.database_data_model import DatabaseMessages
from src.common.database.core import get_db_session
from src.common.database.core.models import Images, Messages
from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream

logger = get_logger("message_storage")

# 预编译的正则表达式（避免重复编译）
_COMPILED_FILTER_PATTERN = re.compile(
    r"<MainRule>.*?</MainRule>|<schedule>.*?</schedule>|<UserMessage>.*?</UserMessage>",
    re.DOTALL
)
_COMPILED_IMAGE_PATTERN = re.compile(r"\[图片：([^\]]+)\]")

# 全局正则表达式缓存
_regex_cache: dict[str, re.Pattern] = {}


class MessageStorageBatcher:
    """
    消息存储批处理器

    优化: 将消息缓存一段时间后批量写入数据库，减少数据库连接池压力
    2025-12: 增加二级缓冲区，降低 commit 频率并使用 Core 批量插入。
    """

    def __init__(
        self,
        batch_size: int = 50,
        flush_interval: float = 5.0,
        *,
        commit_batch_size: int | None = None,
        commit_interval: float | None = None,
        db_chunk_size: int = 200,
    ):
        """
        初始化批处理器

        Args:
            batch_size: 写入队列中触发准备阶段的消息条数
            flush_interval: 自动刷新/检查间隔（秒）
            commit_batch_size: 实际落库前需要累积的条数（默认=2x batch_size，至少100）
            commit_interval: 降低刷盘频率的最大等待时长（默认=max(flush_interval*2, 10s)）
            db_chunk_size: 单次SQL语句批量写入数量上限
        """
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.commit_batch_size = commit_batch_size or max(batch_size * 2, 100)
        self.commit_interval = commit_interval or max(flush_interval * 2, 10.0)
        self.db_chunk_size = max(50, db_chunk_size)

        self.pending_messages: deque = deque()
        self._prepared_buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._flush_barrier = asyncio.Lock()
        self._flush_task = None
        self._running = False
        self._last_commit_ts = time.monotonic()

    async def start(self):
        """启动自动刷新任务"""
        if self._flush_task is None and not self._running:
            self._running = True
            self._last_commit_ts = time.monotonic()
            self._flush_task = asyncio.create_task(self._auto_flush_loop())
            logger.info(
                "消息存储批处理器已启动 (批量大小: %s, 刷新间隔: %ss, commit批量: %s, commit间隔: %ss)",
                self.batch_size,
                self.flush_interval,
                self.commit_batch_size,
                self.commit_interval,
            )

    async def stop(self):
        """停止批处理器"""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # 刷新剩余的消息
        await self.flush(force=True)
        logger.info("消息存储批处理器已停止")

    async def add_message(self, message_data: dict):
        """
        添加消息到批处理队列

        Args:
            message_data: 包含消息对象和chat_stream的字典
                {
                    'message': DatabaseMessages,
                    'chat_stream': ChatStream
                }
        """
        should_force_flush = False
        async with self._lock:
            self.pending_messages.append(message_data)

            if len(self.pending_messages) >= self.batch_size:
                should_force_flush = True

        if should_force_flush:
            logger.debug(f"达到批量大小 {self.batch_size}，立即触发数据库刷新")
            await self.flush(force=True)

    async def flush(self, force: bool = False):
        """执行批量写入, 支持强制落库和延迟提交策略。"""
        async with self._flush_barrier:
            # 原子性地交换消息队列，避免锁定时间过长
            async with self._lock:
                if not self.pending_messages:
                    return
                messages_to_store = self.pending_messages
                self.pending_messages = collections.deque(maxlen=self.batch_size)

            # 处理消息，这部分不在锁内执行，提高并发性
            prepared_messages: list[dict[str, Any]] = []
            for msg_data in messages_to_store:
                try:
                    message_dict = await self._prepare_message_dict(
                        msg_data["message"],
                        msg_data["chat_stream"],
                    )
                    if message_dict:
                        prepared_messages.append(message_dict)
                except Exception as e:
                    logger.error(f"准备消息数据失败: {e}")

            if prepared_messages:
                self._prepared_buffer.extend(prepared_messages)

            await self._maybe_commit_buffer(force=force)

    async def _maybe_commit_buffer(self, *, force: bool = False) -> None:
        """根据阈值/时间窗口判断是否需要真正写库。"""
        if not self._prepared_buffer:
            return

        now = time.monotonic()
        enough_rows = len(self._prepared_buffer) >= self.commit_batch_size
        waited_long_enough = (now - self._last_commit_ts) >= self.commit_interval

        if not (force or enough_rows or waited_long_enough):
            return

        await self._write_buffer_to_database()

    async def _write_buffer_to_database(self) -> None:
        payload = self._prepared_buffer
        if not payload:
            return

        self._prepared_buffer = []
        start_time = time.time()
        total = len(payload)
        max_retries = 3
        
        for attempt in range(max_retries):
            session = None
            try:
                async with get_db_session() as session:
                    for start in range(0, total, self.db_chunk_size):
                        chunk = payload[start : start + self.db_chunk_size]
                        if chunk:
                            await session.execute(insert(Messages), chunk)
                    # 显式 commit，确保立即释放锁
                    await session.commit()

                elapsed = time.time() - start_time
                self._last_commit_ts = time.monotonic()
                per_item = (elapsed / total) * 1000 if total else 0
                logger.info(
                    f"批量存储了 {total} 条消息 (耗时 {elapsed:.3f} 秒, 平均 {per_item:.2f} ms/条, chunk={self.db_chunk_size}, 尝试={attempt+1})"
                )
                return  # 成功，退出重试
                
            except Exception as e:
                error_str = str(e)
                is_lock_error = "database is locked" in error_str or "locked" in error_str.lower()
                is_rollback_error = "invalid transaction" in error_str or "rolled back" in error_str
                
                if (is_lock_error or is_rollback_error) and attempt < max_retries - 1:
                    wait_time = 0.2 * (attempt + 1)  # 递增等待：0.2s, 0.4s, 0.6s
                    logger.warning(f"批量存储消息遇到数据库问题，重试 {attempt + 1}/{max_retries}，等待 {wait_time:.2f}s: {error_str[:100]}")
                    
                    # 🔧 清理"脏" session
                    if session is not None:
                        try:
                            if session.is_active:
                                await session.rollback()
                            await session.close()
                        except Exception:
                            pass
                    
                    await asyncio.sleep(wait_time)
                else:
                    # 最后一次失败，回滚到缓冲区
                    self._prepared_buffer = payload + self._prepared_buffer
                    logger.error(f"批量存储消息失败（尝试 {attempt + 1}/{max_retries}）: {e}", exc_info=True)

    async def _prepare_message_dict(self, message, chat_stream):
        """准备消息字典数据（用于批量INSERT）

        这个方法准备字典而不是ORM对象，性能更高
        """
        message_obj = await self._prepare_message_object(message, chat_stream)
        if message_obj is None:
            return None

        # 将ORM对象转换为字典（只包含列字段）
        # 排除 id 字段，让数据库自动生成（对于 PostgreSQL SERIAL 类型尤其重要）
        message_dict = {}
        for column in Messages.__table__.columns:
            if column.name == "id":
                continue  # 跳过自增主键，让数据库自动生成
            message_dict[column.name] = getattr(message_obj, column.name)

        return message_dict

    async def _prepare_message_object(self, message, chat_stream):
        """准备消息对象（从原 store_message 逻辑提取） - 优化版本"""
        try:
            if not isinstance(message, DatabaseMessages):
                logger.error("MessageStorageBatcher expects DatabaseMessages instances")
                return None

            # 优化：使用预编译的正则表达式
            processed_plain_text = message.processed_plain_text or ""
            if processed_plain_text:
                processed_plain_text = await MessageStorage.replace_image_descriptions(processed_plain_text)
            filtered_processed_plain_text = _COMPILED_FILTER_PATTERN.sub("", processed_plain_text)

            display_message = message.display_message or message.processed_plain_text or ""
            filtered_display_message = _COMPILED_FILTER_PATTERN.sub("", display_message)

            # 优化：一次性构建字典，避免多次条件判断
            user_info = message.user_info
            chat_info = message.chat_info
            chat_info_user = getattr(chat_info, "user_info", None) if chat_info else None
            group_info = message.group_info

            return Messages(
                message_id=message.message_id,
                time=message.time,
                chat_id=message.chat_id,
                reply_to=message.reply_to or "",
                is_mentioned=message.is_mentioned,
                chat_info_stream_id=getattr(chat_info, "stream_id", "") if chat_info else "",
                chat_info_platform=getattr(chat_info, "platform", "") if chat_info else "",
                chat_info_user_platform=getattr(chat_info_user, "platform", "") if chat_info_user else "",
                chat_info_user_id=getattr(chat_info_user, "user_id", "") if chat_info_user else "",
                chat_info_user_nickname=getattr(chat_info_user, "user_nickname", "") if chat_info_user else "",
                chat_info_user_cardname=getattr(chat_info_user, "user_cardname", None) if chat_info_user else None,
                chat_info_group_platform=getattr(group_info, "platform", None) if group_info else None,
                chat_info_group_id=getattr(group_info, "group_id", None) if group_info else None,
                chat_info_group_name=getattr(group_info, "group_name", None) if group_info else None,
                chat_info_create_time=getattr(chat_info, "create_time", 0.0) if chat_info else 0.0,
                chat_info_last_active_time=getattr(chat_info, "last_active_time", 0.0) if chat_info else 0.0,
                user_platform=getattr(user_info, "platform", "") if user_info else "",
                user_id=getattr(user_info, "user_id", "") if user_info else "",
                user_nickname=getattr(user_info, "user_nickname", "") if user_info else "",
                user_cardname=getattr(user_info, "user_cardname", None) if user_info else None,
                processed_plain_text=filtered_processed_plain_text,
                display_message=filtered_display_message,
                memorized_times=getattr(message, "memorized_times", 0),
                interest_value=message.interest_value or 0.0,
                priority_mode=message.priority_mode,
                priority_info=message.priority_info,
                additional_config=message.additional_config,
                is_emoji=message.is_emoji or False,
                is_picid=message.is_picid or False,
                is_notify=message.is_notify or False,
                is_command=message.is_command or False,
                is_public_notice=message.is_public_notice or False,
                notice_type=message.notice_type,
                actions=orjson.dumps(message.actions).decode("utf-8") if message.actions else None,
                should_reply=message.should_reply,
                should_act=message.should_act,
                key_words=MessageStorage._serialize_keywords(message.key_words),
                key_words_lite=MessageStorage._serialize_keywords(message.key_words_lite),
            )

        except Exception as e:
            logger.error(f"准备消息对象失败: {e}")
            return None

    async def _auto_flush_loop(self):
        """自动刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动刷新失败: {e}")


# 全局批处理器实例
_message_storage_batcher: MessageStorageBatcher | None = None
_message_update_batcher: Optional["MessageUpdateBatcher"] = None


def get_message_storage_batcher() -> MessageStorageBatcher:
    """获取消息存储批处理器单例"""
    global _message_storage_batcher
    if _message_storage_batcher is None:
        _message_storage_batcher = MessageStorageBatcher(
            batch_size=50,  # 批量大小：50条消息
            flush_interval=5.0  # 刷新间隔：5秒
        )
    return _message_storage_batcher


class MessageUpdateBatcher:
    """
    消息更新批处理器

    优化: 将多个消息ID更新操作批量处理，减少数据库连接次数
    """

    def __init__(self, batch_size: int = 20, flush_interval: float = 2.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.pending_updates: deque = deque()
        self._lock = asyncio.Lock()
        self._flush_task = None

    async def start(self):
        """启动自动刷新任务"""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._auto_flush_loop())
            logger.debug("消息更新批处理器已启动")

    async def stop(self):
        """停止批处理器"""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # 刷新剩余的更新
        await self.flush()
        logger.debug("消息更新批处理器已停止")

    async def add_update(self, mmc_message_id: str, qq_message_id: str):
        """添加消息ID更新到批处理队列"""
        async with self._lock:
            self.pending_updates.append((mmc_message_id, qq_message_id))

            # 如果达到批量大小，立即刷新
            if len(self.pending_updates) >= self.batch_size:
                await self.flush()

    async def flush(self):
        """执行批量更新"""
        async with self._lock:
            if not self.pending_updates:
                return

            updates = list(self.pending_updates)
            self.pending_updates.clear()

        try:
            async with get_db_session() as session:
                updated_count = 0
                for mmc_id, qq_id in updates:
                    result = await session.execute(
                        update(Messages)
                        .where(Messages.message_id == mmc_id)
                        .values(message_id=qq_id)
                    )
                    if cast(CursorResult, result).rowcount > 0:
                        updated_count += 1

                await session.commit()

                if updated_count > 0:
                    logger.debug(f"批量更新了 {updated_count}/{len(updates)} 条消息ID")

        except Exception as e:
            logger.error(f"批量更新消息ID失败: {e}")

    async def _auto_flush_loop(self):
        """自动刷新循环"""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动刷新出错: {e}")


def get_message_update_batcher() -> MessageUpdateBatcher:
    """获取全局消息更新批处理器"""
    global _message_update_batcher
    if _message_update_batcher is None:
        _message_update_batcher = MessageUpdateBatcher()
    return _message_update_batcher


class MessageStorage:
    @staticmethod
    def _serialize_keywords(keywords) -> str:
        """将关键词列表序列化为JSON字符串"""
        if isinstance(keywords, list):
            return orjson.dumps(keywords).decode("utf-8")
        return "[]"

    @staticmethod
    def _deserialize_keywords(keywords_str: str) -> list:
        """将JSON字符串反序列化为关键词列表"""
        if not keywords_str:
            return []
        try:
            return orjson.loads(keywords_str)
        except (orjson.JSONDecodeError, TypeError):
            return []

    @staticmethod
    async def store_message(message: DatabaseMessages, chat_stream: "ChatStream", use_batch: bool = True) -> None:
        """
        存储消息到数据库

        Args:
            message: 消息对象
            chat_stream: 聊天流对象
            use_batch: 是否使用批处理，默认True，设置为False时直接写入数据库
        """
        if use_batch:
            batcher = get_message_storage_batcher()
            await batcher.add_message({"message": message, "chat_stream": chat_stream})
            return

        try:
            # 直接存储消息（非批处理模式）
            batcher = MessageStorageBatcher()
            message_obj = await batcher._prepare_message_object(message, chat_stream)
            if message_obj is None:
                return

            async with get_db_session() as session:
                session.add(message_obj)
                await session.commit()

        except Exception:
            logger.exception("存储消息失败")
            logger.error(f"消息: {message}")
            traceback.print_exc()

    @staticmethod
    async def update_message(message_data: dict, use_batch: bool = True):
        """
        更新消息ID（从消息字典）- 优化版本

        优化: 添加批处理选项，将多个更新操作合并，减少数据库连接

        Args:
            message_data: 消息数据字典
            use_batch: 是否使用批处理（默认True）
        """
        try:
            # 从字典中提取信息
            message_info = message_data.get("message_info", {})
            mmc_message_id = message_info.get("message_id")

            message_segment = message_data.get("message_segment", {})
            segment_type = message_segment.get("type") if isinstance(message_segment, dict) else None
            segment_data = message_segment.get("data", {}) if isinstance(message_segment, dict) else {}

            # 优化：预定义类型集合，避免重复的 if-elif 检查
            SKIPPED_TYPES = {"adapter_response", "adapter_command"}
            VALID_ID_TYPES = {"notify", "text", "reply"}

            logger.debug(f"尝试更新消息ID: {mmc_message_id}, 消息段类型: {segment_type}")

            # 检查是否是需要跳过的类型
            if segment_type in SKIPPED_TYPES:
                logger.debug(f"跳过消息段类型: {segment_type}")
                return

            # 尝试获取消息ID
            qq_message_id = None
            if segment_type in VALID_ID_TYPES:
                qq_message_id = segment_data.get("id")
                if segment_type == "reply" and qq_message_id:
                    logger.debug(f"从reply消息段获取到消息ID: {qq_message_id}")
            else:
                logger.debug(f"未知的消息段类型: {segment_type}，跳过ID更新")
                return

            if not qq_message_id:
                logger.debug(f"消息段类型 {segment_type} 中未找到有效的message_id，跳过更新")
                logger.debug(f"消息段数据: {segment_data}")
                return

            # 优化: 使用批处理器减少数据库连接
            if use_batch:
                batcher = get_message_update_batcher()
                await batcher.add_update(mmc_message_id, qq_message_id)
                logger.debug(f"消息ID更新已加入批处理队列: {mmc_message_id} -> {qq_message_id}")
            else:
                # 直接更新（保留原有逻辑用于特殊情况）
                from src.common.database.core import get_db_session

                async with get_db_session() as session:
                    matched_message = (
                        await session.execute(
                            select(Messages).where(Messages.message_id == mmc_message_id).order_by(desc(Messages.time))
                        )
                    ).scalar()

                    if matched_message:
                        await session.execute(
                            update(Messages).where(Messages.id == matched_message.id).values(message_id=qq_message_id)
                        )
                        logger.debug(f"更新消息ID成功: {matched_message.message_id} -> {qq_message_id}")
                    else:
                        logger.warning(f"未找到匹配的消息记录: {mmc_message_id}")

        except Exception as e:
            logger.error(f"更新消息ID失败: {e}")
            logger.error(
                f"消息信息: message_id={message_data.get('message_info', {}).get('message_id', 'N/A')}, "
                f"segment_type={message_data.get('message_segment', {}).get('type', 'N/A')}"
            )

    @staticmethod
    async def replace_image_descriptions(text: str) -> str:
        """异步地将文本中的所有[图片：描述]标记替换为[picid:image_id] - 优化版本"""
        # 如果没有匹配项，提前返回以提高效率
        if not _COMPILED_IMAGE_PATTERN.search(text):
            return text

        # re.sub不支持异步替换函数，所以我们需要手动迭代和替换
        new_text = []
        last_end = 0
        for match in _COMPILED_IMAGE_PATTERN.finditer(text):
            # 添加上一个匹配到当前匹配之间的文本
            new_text.append(text[last_end:match.start()])

            description = match.group(1).strip()
            replacement = match.group(0)  # 默认情况下，替换为原始匹配文本
            try:
                async with get_db_session() as session:
                    # 查询数据库以找到具有该描述的最新图片记录
                    result = await session.execute(
                        select(Images.image_id)
                        .where(Images.description == description)
                        .order_by(desc(Images.timestamp))
                        .limit(1)
                    )
                    image_id = result.scalar_one_or_none()

                    if image_id:
                        replacement = f"[picid:{image_id}]"
                        logger.debug(f"成功将描述 '{description[:20]}...' 替换为 picid '{image_id}'")
                    else:
                        logger.warning(f"无法为描述 '{description[:20]}...' 找到对应的picid，将保留原始标记")
            except Exception as e:
                logger.error(f"替换图片描述时查询数据库失败: {e}")

            new_text.append(replacement)
            last_end = match.end()

        # 添加最后一个匹配到字符串末尾的文本
        new_text.append(text[last_end:])

        return "".join(new_text)

    @staticmethod
    async def update_message_interest_value(
        message_id: str,
        interest_value: float,
        should_reply: bool | None = None,
    ) -> None:
        """
        更新数据库中消息的interest_value字段

        Args:
            message_id: 消息ID
            interest_value: 兴趣度值
        """
        try:
            async with get_db_session() as session:
                # 更新消息的interest_value字段
                values = {"interest_value": interest_value}
                if should_reply is not None:
                    values["should_reply"] = should_reply

                stmt = update(Messages).where(Messages.message_id == message_id).values(**values)
                result = await session.execute(stmt)
                await session.commit()

                if cast(CursorResult, result).rowcount > 0:
                    logger.debug(f"成功更新消息 {message_id} 的interest_value为 {interest_value}")
                else:
                    logger.warning(f"未找到消息 {message_id}，无法更新interest_value")

        except Exception as e:
            logger.error(f"更新消息 {message_id} 的interest_value失败: {e}")
            raise

    @staticmethod
    async def bulk_update_interest_values(
        interest_map: dict[str, float],
        reply_map: dict[str, bool] | None = None,
    ) -> None:
        """批量更新消息的兴趣度与回复标记 - 优化版本"""
        if not interest_map:
            return

        try:
            async with get_db_session() as session:
                # 注意：SQLAlchemy 2.0 对 ORM update + executemany 会走
                # “Bulk UPDATE by Primary Key” 路径，要求每行参数包含主键(Messages.id)。
                # 这里我们按 message_id 更新，因此使用 Core Table + bindparam。
                from sqlalchemy import bindparam, update

                messages_table = Messages.__table__

                interest_mappings: list[dict[str, Any]] = [
                    {"b_message_id": message_id, "b_interest_value": interest_value}
                    for message_id, interest_value in interest_map.items()
                ]

                if interest_mappings:
                    stmt_interest = (
                        update(messages_table)
                        .where(messages_table.c.message_id == bindparam("b_message_id"))
                        .values(interest_value=bindparam("b_interest_value"))
                    )
                    await session.execute(stmt_interest, interest_mappings)

                if reply_map:
                    reply_mappings: list[dict[str, Any]] = [
                        {"b_message_id": message_id, "b_should_reply": should_reply}
                        for message_id, should_reply in reply_map.items()
                        if message_id in interest_map
                    ]
                    if reply_mappings and len(reply_mappings) != len(reply_map):
                        logger.debug(
                            f"批量更新 should_reply 过滤了 {len(reply_map) - len(reply_mappings)} 条不在兴趣度更新集合中的记录"
                        )
                    if reply_mappings:
                        stmt_reply = (
                            update(messages_table)
                            .where(messages_table.c.message_id == bindparam("b_message_id"))
                            .values(should_reply=bindparam("b_should_reply"))
                        )
                        await session.execute(stmt_reply, reply_mappings)

                await session.commit()
                logger.debug(f"批量更新兴趣度 {len(interest_map)} 条记录")
        except Exception as e:
            logger.error(f"批量更新消息兴趣度失败: {e}")
            raise

    @staticmethod
    async def fix_zero_interest_values(chat_id: str, since_time: float) -> int:
        """
        修复指定聊天中interest_value为0或null的历史消息记录

        Args:
            chat_id: 聊天ID
            since_time: 从指定时间开始修复（时间戳）

        Returns:
            修复的记录数量
        """
        try:
            async with get_db_session() as session:
                from sqlalchemy import select, update

                from src.common.database.core.models import Messages

                # 查找需要修复的记录：interest_value为0、null或很小的值
                query = (
                    select(Messages)
                    .where(
                        (Messages.chat_id == chat_id)
                        & (Messages.time >= since_time)
                        & (
                            (Messages.interest_value == 0)
                            | (Messages.interest_value.is_(None))
                            | (Messages.interest_value < 0.1)
                        )
                    )
                    .limit(50)
                )  # 限制每次修复的数量，避免性能问题

                result = await session.execute(query)
                messages_to_fix = result.scalars().all()
                fixed_count = 0

                for msg in messages_to_fix:
                    # 为这些消息设置一个合理的默认兴趣度
                    # 可以基于消息长度、内容或其他因素计算
                    default_interest = 0.3  # 默认中等兴趣度

                    # 如果消息内容较长，可能是重要消息，兴趣度稍高
                    if hasattr(msg, "processed_plain_text") and msg.processed_plain_text:
                        text_length = len(msg.processed_plain_text)
                        if text_length > 50:  # 长消息
                            default_interest = 0.4
                        elif text_length > 20:  # 中等长度消息
                            default_interest = 0.35

                    # 如果是被@的消息，兴趣度更高
                    if getattr(msg, "is_mentioned", False):
                        default_interest = min(default_interest + 0.2, 0.8)

                    # 执行更新
                    update_stmt = (
                        update(Messages)
                        .where(Messages.message_id == msg.message_id)
                        .values(interest_value=default_interest)
                    )

                    result = await session.execute(update_stmt)
                    if cast(CursorResult, result).rowcount > 0:
                        fixed_count += 1
                        logger.debug(f"修复消息 {msg.message_id} 的interest_value为 {default_interest}")

                await session.commit()
                logger.info(f"共修复了 {fixed_count} 条历史消息的interest_value值")
                return fixed_count

        except Exception as e:
            logger.error(f"修复历史消息interest_value失败: {e}")
            return 0
