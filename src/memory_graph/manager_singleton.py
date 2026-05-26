"""
记忆系统管理单例

提供全局访问的 MemoryManager 和 UnifiedMemoryManager 实例
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.common.logger import get_logger
from src.memory_graph.manager import MemoryManager

logger = get_logger(__name__)

# 全局 MemoryManager 实例（旧的单层记忆系统，已弃用）
_memory_manager: MemoryManager | None = None
_initialized: bool = False

# 全局 UnifiedMemoryManager 实例（新的三层记忆系统）
_unified_memory_manager = None
_unified_memory_init_lock: asyncio.Lock | None = None


# ============================================================================
# 旧的单层记忆系统 API（已弃用，保留用于向后兼容）
# ============================================================================


async def initialize_memory_manager(
    data_dir: Path | str | None = None,
) -> MemoryManager | None:
    """
    初始化全局 MemoryManager（兼容包装）

    委托给 initialize_unified_memory_manager()，
    返回内部的 MemoryManager 实例。

    Args:
        data_dir: 数据目录（可选，默认从配置读取）

    Returns:
        MemoryManager 实例，如果禁用则返回 None
    """
    global _memory_manager, _initialized

    unified = await initialize_unified_memory_manager(data_dir=data_dir)
    if unified is None:
        _initialized = False
        _memory_manager = None
        return None

    _memory_manager = unified.memory_manager
    _initialized = True
    return _memory_manager


def get_memory_manager() -> MemoryManager | None:
    """
    获取全局 MemoryManager 实例（兼容包装）

    优先从 UnifiedMemoryManager 获取内部 MemoryManager。

    Returns:
        MemoryManager 实例，如果未初始化则返回 None
    """
    # 优先从统一管理器获取
    unified = get_unified_memory_manager()
    if unified and unified.memory_manager:
        return unified.memory_manager

    # 回退：旧的直接引用
    if _initialized and _memory_manager:
        return _memory_manager

    logger.warning("MemoryManager 尚未初始化，请先调用 initialize_memory_manager()")
    return None


async def shutdown_memory_manager():
    """关闭全局 MemoryManager（兼容包装，委托给统一管理器）"""
    global _memory_manager, _initialized
    _memory_manager = None
    _initialized = False
    await shutdown_unified_memory_manager()


def is_initialized() -> bool:
    """检查记忆系统是否已初始化"""
    return get_unified_memory_manager() is not None


# ============================================================================
# 新的三层记忆系统 API（推荐使用）
# ============================================================================


async def initialize_unified_memory_manager(data_dir: Path | str | None = None):

    """
    初始化统一记忆管理器（三层记忆系统）

    从全局配置读取参数

    Args:
        data_dir: 数据目录（可选，默认从配置读取）

    Returns:
        初始化后的管理器实例，未启用返回 None
    """

    if _unified_memory_manager is not None:
        logger.warning("统一记忆管理器已经初始化")
        return _unified_memory_manager

    try:
        from src.config.config import global_config
        from src.memory_graph.unified_manager import UnifiedMemoryManager

        # 检查是否启用三层记忆系统
        if not global_config or not global_config.memory or not getattr(
            global_config.memory, "enable", False
        ):
            logger.warning("三层记忆系统未启用，跳过初始化")
            return None

        if not global_config or not global_config.memory:
            logger.warning("未找到内存配置，跳过统一内存管理器初始化。")
            return None
        config = global_config.memory

        # 创建管理器实例
        # 注意：我们将 data_dir 指向 three_tier 子目录，以隔离感知/短期记忆数据
        # 同时传入全局 _memory_manager 以共享长期记忆图存储
        base_data_dir = Path(data_dir) if data_dir else Path(getattr(config, "data_dir", "data/memory_graph"))

        from src.memory_graph.models import MemoryConfig

        mem_cfg = MemoryConfig.from_global_config()
        _unified_memory_manager = UnifiedMemoryManager(
            data_dir=base_data_dir,
            memory_manager=_memory_manager,
            config=mem_cfg,
        )

        # 初始化
        await _unified_memory_manager.initialize()
        return _unified_memory_manager

    except Exception as e:
        logger.error(f"初始化统一记忆管理器失败: {e}")
        raise


def get_unified_memory_manager():
    """
    获取统一记忆管理器实例（三层记忆系统）

    Returns:
        管理器实例，未初始化返回 None
    """
    if _unified_memory_manager is None:
        logger.warning("统一记忆管理器尚未初始化，请先调用 initialize_unified_memory_manager()")
    return _unified_memory_manager


async def ensure_unified_memory_manager_initialized():
    """
    确保统一记忆管理器已初始化。

    在首次访问时自动初始化，避免调用方重复判断。
    """
    global _unified_memory_init_lock, _unified_memory_manager

    if _unified_memory_manager is not None:
        return _unified_memory_manager

    if _unified_memory_init_lock is None:
        _unified_memory_init_lock = asyncio.Lock()

    async with _unified_memory_init_lock:
        if _unified_memory_manager is not None:
            return _unified_memory_manager

        return await initialize_unified_memory_manager()


async def shutdown_unified_memory_manager() -> None:
    """关闭统一记忆管理器"""
    global _unified_memory_manager

    if _unified_memory_manager is None:
        logger.warning("统一记忆管理器未初始化，无需关闭")
        return

    try:
        await _unified_memory_manager.shutdown()
        _unified_memory_manager = None
        logger.info("统一记忆管理器已关闭")

    except Exception as e:
        logger.error(f"关闭统一记忆管理器失败: {e}")

