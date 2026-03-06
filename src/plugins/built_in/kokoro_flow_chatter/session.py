"""
Kokoro Flow Chatter - 会话管理

极简的会话状态管理：
- Session 只有 IDLE 和 WAITING 两种状态
- 包含 mental_log（心理活动历史）
- 包含 waiting_config（等待配置）

性能优化：
- 使用 asyncio.to_thread() 将同步文件 I/O 异步化，避免阻塞事件循环
- 支持高并发场景下的会话管理
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

from src.common.logger import get_logger

from .models import (
    EventType,
    MentalLogEntry,
    SessionStatus,
    WaitingConfig,
)

logger = get_logger("kfc_session")


class KokoroSession:
    """
    Kokoro Flow Chatter 会话

    为每个私聊用户维护一个独立的会话，包含：
    - 基本信息（user_id, stream_id）
    - 状态（只有 IDLE 和 WAITING）
    - 心理活动历史（mental_log）
    - 等待配置（waiting_config）
    """

    # 心理活动日志最大保留条数
    MAX_MENTAL_LOG_SIZE = 50

    def __init__(
        self,
        user_id: str,
        stream_id: str,
    ):
        self.user_id = user_id
        self.stream_id = stream_id

        # 状态（只有 IDLE 和 WAITING）
        self._status: SessionStatus = SessionStatus.IDLE

        # 心理活动历史
        self.mental_log: list[MentalLogEntry] = []

        # 等待配置
        self.waiting_config: WaitingConfig = WaitingConfig()

        # 时间戳
        self.created_at: float = time.time()
        self.last_activity_at: float = time.time()

        # 统计
        self.total_interactions: int = 0

        # 上次主动思考时间
        self.last_proactive_at: float | None = None

        # 连续超时计数（用于避免过度打扰用户）
        self.consecutive_timeout_count: int = 0

        # 用户最后发消息的时间（用于计算距离用户上次回复的时间）
        self.last_user_message_at: float | None = None

    @property
    def status(self) -> SessionStatus:
        return self._status

    @status.setter
    def status(self, value: SessionStatus) -> None:
        old_status = self._status
        self._status = value
        if old_status != value:
            logger.debug(f"Session {self.user_id} 状态变更: {old_status} → {value}")

    def add_entry(self, entry: MentalLogEntry) -> None:
        """添加心理活动日志条目"""
        self.mental_log.append(entry)
        self.last_activity_at = time.time()

        # 保持日志在合理大小
        if len(self.mental_log) > self.MAX_MENTAL_LOG_SIZE:
            self.mental_log = self.mental_log[-self.MAX_MENTAL_LOG_SIZE:]

    def add_user_message(
        self,
        content: str,
        user_name: str,
        user_id: str,
        timestamp: float | None = None,
    ) -> MentalLogEntry:
        """添加用户消息事件"""
        msg_time = timestamp or time.time()

        entry = MentalLogEntry(
            event_type=EventType.USER_MESSAGE,
            timestamp=msg_time,
            content=content,
            user_name=user_name,
            user_id=user_id,
        )

        # 收到用户消息，重置连续超时计数
        self.consecutive_timeout_count = 0
        self.last_user_message_at = msg_time

        # 如果之前在等待，记录收到回复的情况
        if self.status == SessionStatus.WAITING and self.waiting_config.is_active():
            elapsed = self.waiting_config.get_elapsed_seconds()
            max_wait = self.waiting_config.max_wait_seconds

            if elapsed <= max_wait:
                entry.metadata["reply_status"] = "in_time"
                entry.metadata["elapsed_seconds"] = elapsed
                entry.metadata["max_wait_seconds"] = max_wait
            else:
                entry.metadata["reply_status"] = "late"
                entry.metadata["elapsed_seconds"] = elapsed
                entry.metadata["max_wait_seconds"] = max_wait

        self.add_entry(entry)
        return entry

    def add_bot_planning(
        self,
        thought: str,
        actions: list[dict],
        expected_reaction: str = "",
        max_wait_seconds: int = 0,
        timestamp: float | None = None,
    ) -> MentalLogEntry:
        """添加 Bot 规划事件"""
        entry = MentalLogEntry(
            event_type=EventType.BOT_PLANNING,
            timestamp=timestamp or time.time(),
            thought=thought,
            actions=actions,
            expected_reaction=expected_reaction,
            max_wait_seconds=max_wait_seconds,
        )
        self.add_entry(entry)
        self.total_interactions += 1
        return entry

    def add_waiting_update(
        self,
        waiting_thought: str,
        mood: str = "",
        timestamp: float | None = None,
    ) -> MentalLogEntry:
        """添加等待期间的心理变化"""
        entry = MentalLogEntry(
            event_type=EventType.WAITING_UPDATE,
            timestamp=timestamp or time.time(),
            waiting_thought=waiting_thought,
            mood=mood,
            elapsed_seconds=self.waiting_config.get_elapsed_seconds(),
        )
        self.add_entry(entry)
        return entry

    def start_waiting(
        self,
        expected_reaction: str,
        max_wait_seconds: int,
    ) -> None:
        """开始等待"""
        if max_wait_seconds <= 0:
            # 不等待，直接进入 IDLE
            self.status = SessionStatus.IDLE
            self.waiting_config.reset()
            return

        self.status = SessionStatus.WAITING
        self.waiting_config = WaitingConfig(
            expected_reaction=expected_reaction,
            max_wait_seconds=max_wait_seconds,
            started_at=time.time(),
            last_thinking_at=0.0,
            thinking_count=0,
        )
        logger.debug(
            f"Session {self.user_id} 开始等待: "
            f"max_wait={max_wait_seconds}s, expected={expected_reaction[:30]}..."
        )

    def end_waiting(self) -> None:
        """结束等待"""
        self.status = SessionStatus.IDLE
        self.waiting_config.reset()
        # 更新活动时间，防止 ProactiveThinker 并发处理
        self.last_activity_at = time.time()

    def get_recent_entries(self, limit: int = 20) -> list[MentalLogEntry]:
        """获取最近的心理活动日志"""
        return self.mental_log[-limit:] if self.mental_log else []

    def get_last_bot_message(self) -> str | None:
        """获取最后一条 Bot 发送的消息"""
        for entry in reversed(self.mental_log):
            if entry.event_type == EventType.BOT_PLANNING:
                for action in entry.actions:
                    if action.get("type") in ("kfc_reply", "respond"):
                        return action.get("content", "")
        return None

    def to_dict(self) -> dict:
        """转换为字典（用于持久化）"""
        return {
            "user_id": self.user_id,
            "stream_id": self.stream_id,
            "status": str(self.status),
            "mental_log": [e.to_dict() for e in self.mental_log],
            "waiting_config": self.waiting_config.to_dict(),
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "total_interactions": self.total_interactions,
            "last_proactive_at": self.last_proactive_at,
            "consecutive_timeout_count": self.consecutive_timeout_count,
            "last_user_message_at": self.last_user_message_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KokoroSession":
        """从字典创建会话"""
        session = cls(
            user_id=data.get("user_id", ""),
            stream_id=data.get("stream_id", ""),
        )

        # 状态
        status_str = data.get("status", "idle")
        try:
            session._status = SessionStatus(status_str)
        except ValueError:
            session._status = SessionStatus.IDLE

        # 心理活动历史
        mental_log_data = data.get("mental_log", [])
        session.mental_log = [MentalLogEntry.from_dict(e) for e in mental_log_data]

        # 等待配置
        waiting_data = data.get("waiting_config", {})
        session.waiting_config = WaitingConfig.from_dict(waiting_data)

        # 时间戳
        session.created_at = data.get("created_at", time.time())
        session.last_activity_at = data.get("last_activity_at", time.time())
        session.total_interactions = data.get("total_interactions", 0)
        session.last_proactive_at = data.get("last_proactive_at")

        # 连续超时相关
        session.consecutive_timeout_count = data.get("consecutive_timeout_count", 0)
        session.last_user_message_at = data.get("last_user_message_at")

        return session


class SessionManager:
    """
    会话管理器

    负责会话的创建、获取、保存和清理
    """

    _instance: Optional["SessionManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        data_dir: str = "data/kokoro_flow_chatter/sessions",
        max_session_age_days: int = 30,
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self.data_dir = Path(data_dir)
        self.max_session_age_days = max_session_age_days

        # 内存缓存
        self._sessions: dict[str, KokoroSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"SessionManager 初始化完成: {self.data_dir}")

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户级别的锁"""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _get_file_path(self, user_id: str) -> Path:
        """获取会话文件路径"""
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        return self.data_dir / f"{safe_id}.json"

    async def get_session(self, user_id: str, stream_id: str) -> KokoroSession:
        """获取或创建会话"""
        async with self._get_lock(user_id):
            # 检查内存缓存
            if user_id in self._sessions:
                session = self._sessions[user_id]
                session.stream_id = stream_id  # 更新 stream_id
                return session

            # 尝试从文件加载
            session = await self._load_from_file(user_id)
            if session:
                session.stream_id = stream_id
                self._sessions[user_id] = session
                return session

            # 创建新会话
            session = KokoroSession(user_id=user_id, stream_id=stream_id)
            self._sessions[user_id] = session
            logger.info(f"创建新会话: {user_id}")
            return session

    def _sync_load_from_file(self, file_path: Path) -> dict | None:
        """同步文件加载操作（在线程池中执行）"""
        if not file_path.exists():
            return None
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    async def _load_from_file(self, user_id: str) -> KokoroSession | None:
        """从文件加载会话（异步化，不阻塞事件循环）"""
        file_path = self._get_file_path(user_id)
        if not file_path.exists():
            return None

        try:
            # 使用 asyncio.to_thread 将同步 I/O 放到线程池执行，避免阻塞事件循环
            data = await asyncio.to_thread(self._sync_load_from_file, file_path)
            if data is None:
                return None
            session = KokoroSession.from_dict(data)
            logger.debug(f"从文件加载会话: {user_id}")
            return session
        except Exception as e:
            logger.error(f"加载会话失败 {user_id}: {e}")
            return None

    def _sync_save_to_file(self, temp_path: Path, file_path: Path, data: dict) -> bool:
        """同步文件保存操作（在线程池中执行）"""
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, file_path)
        return True

    async def save_session(self, user_id: str) -> bool:
        """保存会话到文件（异步化，不阻塞事件循环）"""
        async with self._get_lock(user_id):
            if user_id not in self._sessions:
                return False

            session = self._sessions[user_id]
            file_path = self._get_file_path(user_id)

            try:
                # 在锁内准备数据，但 I/O 操作在线程池执行
                data = session.to_dict()
                temp_path = file_path.with_suffix(".json.tmp")

                # 使用 asyncio.to_thread 将同步 I/O 放到线程池执行，避免阻塞事件循环
                await asyncio.to_thread(self._sync_save_to_file, temp_path, file_path, data)
                return True
            except Exception as e:
                logger.error(f"保存会话失败 {user_id}: {e}")
                return False

    async def save_all(self) -> int:
        """保存所有会话"""
        count = 0
        for user_id in list(self._sessions.keys()):
            if await self.save_session(user_id):
                count += 1
        return count

    async def get_waiting_sessions(self) -> list[KokoroSession]:
        """获取所有处于等待状态的会话"""
        return [s for s in self._sessions.values() if s.status == SessionStatus.WAITING]

    async def get_all_sessions(self) -> list[KokoroSession]:
        """获取所有会话"""
        return list(self._sessions.values())

    def get_session_sync(self, user_id: str) -> KokoroSession | None:
        """同步获取会话（仅从内存）"""
        return self._sessions.get(user_id)


# 全局单例
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
