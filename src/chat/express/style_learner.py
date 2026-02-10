"""
风格学习引擎
基于ExpressorModel实现的表达风格学习和预测系统
支持多聊天室独立建模和在线学习
"""
import asyncio
import os
import pickle
import time

from src.common.logger import get_logger

from .expressor_model import ExpressorModel

logger = get_logger("expressor.style_learner")


class StyleLearner:
    """单个聊天室的表达风格学习器"""

    def __init__(self, chat_id: str, model_config: dict | None = None, resource_limit_enabled: bool = True):
        """
        Args:
            chat_id: 聊天室ID
            model_config: 模型配置
            resource_limit_enabled: 是否启用资源上限控制（默认关闭）
        """
        self.chat_id = chat_id
        self.model_config = model_config or {
            "alpha": 0.5,
            "beta": 0.5,
            "gamma": 0.99,  # 衰减因子，支持遗忘
            "vocab_size": 200000,
            "use_jieba": True,
        }

        # 初始化表达模型
        self.expressor = ExpressorModel(**self.model_config)

        # 资源上限控制开关（默认开启，可按需关闭）
        self.resource_limit_enabled = resource_limit_enabled

        # 动态风格管理
        self.max_styles = 2000  # 每个chat_id最多2000个风格
        self.cleanup_threshold = 0.9  # 达到90%容量时触发清理
        self.cleanup_ratio = 0.2  # 每次清理20%的风格
        self.style_to_id: dict[str, str] = {}  # style文本 -> style_id
        self.id_to_style: dict[str, str] = {}  # style_id -> style文本
        self.id_to_situation: dict[str, str] = {}  # style_id -> situation文本
        self.next_style_id = 0

        # 学习统计
        self.learning_stats = {
            "total_samples": 0,
            "style_counts": {},
            "style_last_used": {},  # 记录每个风格最后使用时间
            "last_update": time.time(),
        }

    def add_style(self, style: str, situation: str | None = None) -> bool:
        """
        动态添加一个新的风格

        Args:
            style: 风格文本
            situation: 情境文本

        Returns:
            是否添加成功
        """
        try:
            # 检查是否已存在
            if style in self.style_to_id:
                return True

            # 检查是否需要清理（仅计算一次阈值）
            if self.resource_limit_enabled:
                current_count = len(self.style_to_id)
                cleanup_trigger = int(self.max_styles * self.cleanup_threshold)
                if current_count >= cleanup_trigger:
                    if current_count >= self.max_styles:
                        logger.warning(f"已达到最大风格数量限制 ({self.max_styles})，开始清理")
                    else:
                        logger.info(f"风格数量达到 {current_count}/{self.max_styles}，触发预防性清理")
                    self._cleanup_styles()

            # 生成新的style_id
            style_id = f"style_{self.next_style_id}"
            self.next_style_id += 1

            # 添加到映射
            self.style_to_id[style] = style_id
            self.id_to_style[style_id] = style
            if situation:
                self.id_to_situation[style_id] = situation

            # 添加到expressor模型
            self.expressor.add_candidate(style_id, style, situation)

            # 初始化统计
            self.learning_stats.setdefault("style_counts", {})[style_id] = 0
            self.learning_stats.setdefault("style_last_used", {})

            logger.debug(f"添加风格成功: {style_id} -> {style}")
            return True

        except Exception as e:
            logger.error(f"添加风格失败: {e}")
            return False

    def _cleanup_styles(self):
        """
        清理低价值的风格，为新风格腾出空间

        清理策略：
        1. 综合考虑使用次数和最后使用时间
        2. 删除得分最低的风格
        3. 默认清理 cleanup_ratio (20%) 的风格
        """
        try:
            total_styles = len(self.style_to_id)
            if total_styles == 0:
                return

            # 只有在达到阈值时才执行昂贵的排序
            cleanup_count = max(1, int(total_styles * self.cleanup_ratio))
            if cleanup_count <= 0:
                return

            current_time = time.time()
            # 局部引用加速频繁调用的函数
            from math import exp, log1p

            # 计算每个风格的价值分数
            style_scores = []
            for style_id in self.style_to_id.values():
                usage_count = self.learning_stats["style_counts"].get(style_id, 0)
                last_used = self.learning_stats["style_last_used"].get(style_id, 0)

                time_since_used = current_time - last_used if last_used > 0 else float("inf")
                usage_score = log1p(usage_count)
                days_unused = time_since_used / 86400
                time_score = exp(-days_unused / 30)

                total_score = 0.8 * usage_score + 0.2 * time_score
                style_scores.append((style_id, total_score, usage_count, days_unused))

            if not style_scores:
                return

            # 按分数排序，分数低的先删除
            style_scores.sort(key=lambda x: x[1])

            deleted_styles = []
            for style_id, score, usage, days in style_scores[:cleanup_count]:
                style_text = self.id_to_style.get(style_id)
                if not style_text:
                    continue

                # 从映射中删除
                self.style_to_id.pop(style_text, None)
                self.id_to_style.pop(style_id, None)
                self.id_to_situation.pop(style_id, None)

                # 从统计中删除
                self.learning_stats["style_counts"].pop(style_id, None)
                self.learning_stats["style_last_used"].pop(style_id, None)

                # 从expressor模型中删除
                self.expressor.remove_candidate(style_id)

                deleted_styles.append((style_text[:30], usage, f"{days:.1f}天"))

            logger.info(
                f"风格清理完成: 删除了 {len(deleted_styles)}/{len(style_scores)} 个风格，"
                f"剩余 {len(self.style_to_id)} 个风格"
            )

            if deleted_styles:
                logger.debug(f"被删除的风格样例(前5): {deleted_styles[:5]}")

        except Exception as e:
            logger.error(f"清理风格失败: {e}")

    def learn_mapping(self, up_content: str, style: str) -> bool:
        """
        学习一个up_content到style的映射

        Args:
            up_content: 前置内容
            style: 目标风格

        Returns:
            是否学习成功
        """
        try:
            # 如果style不存在，先添加它
            if style not in self.style_to_id:
                if not self.add_style(style):
                    return False

            # 获取style_id
            style_id = self.style_to_id[style]

            # 使用正反馈学习
            self.expressor.update_positive(up_content, style_id)

            # 更新统计
            current_time = time.time()
            self.learning_stats["total_samples"] += 1
            self.learning_stats.setdefault("style_counts", {})
            self.learning_stats.setdefault("style_last_used", {})
            self.learning_stats["style_counts"][style_id] = self.learning_stats["style_counts"].get(style_id, 0) + 1
            self.learning_stats["style_last_used"][style_id] = current_time  # 更新最后使用时间
            self.learning_stats["last_update"] = current_time

            logger.debug(f"学习映射成功: {up_content[:20]}... -> {style}")
            return True

        except Exception as e:
            logger.error(f"学习映射失败: {e}")
            return False

    def predict_style(self, up_content: str, top_k: int = 5) -> tuple[str | None, dict[str, float]]:
        """
        根据up_content预测最合适的style

        Args:
            up_content: 前置内容
            top_k: 返回前k个候选

        Returns:
            (最佳style文本, 所有候选的分数字典)
        """
        try:
            # 先检查是否有训练数据
            if not self.style_to_id:
                logger.debug(f"StyleLearner还没有任何训练数据: chat_id={self.chat_id}")
                return None, {}

            best_style_id, scores = self.expressor.predict(up_content, k=top_k)

            if best_style_id is None:
                logger.debug(f"ExpressorModel未返回预测结果: chat_id={self.chat_id}, up_content={up_content[:50]}...")
                return None, {}

            # 将style_id转换为style文本
            best_style = self.id_to_style.get(best_style_id)

            if best_style is None:
                logger.warning(
                    f"style_id无法转换为style文本: style_id={best_style_id}, "
                    f"已知的id_to_style数量={len(self.id_to_style)}"
                )
                return None, {}

            # 转换所有分数
            style_scores = {}
            for sid, score in scores.items():
                style_text = self.id_to_style.get(sid)
                if style_text:
                    style_scores[style_text] = score
                else:
                    logger.warning(f"跳过无法转换的style_id: {sid}")

            # 更新最后使用时间（仅针对最佳风格）
            if best_style_id:
                self.learning_stats["style_last_used"][best_style_id] = time.time()

            logger.debug(
                f"预测成功: up_content={up_content[:30]}..., "
                f"best_style={best_style}, top3_scores={list(style_scores.items())[:3]}"
            )

            return best_style, style_scores

        except Exception as e:
            logger.error(f"预测style失败: {e}")
            return None, {}

    def get_style_info(self, style: str) -> tuple[str | None, str | None]:
        """
        获取style的完整信息

        Args:
            style: 风格文本

        Returns:
            (style_id, situation)
        """
        style_id = self.style_to_id.get(style)
        if not style_id:
            return None, None

        situation = self.id_to_situation.get(style_id)
        return style_id, situation

    def get_all_styles(self) -> list[str]:
        """
        获取所有风格列表

        Returns:
            风格文本列表
        """
        return list(self.style_to_id.keys())

    def cleanup_old_styles(self, ratio: float | None = None) -> int:
        """
        手动清理旧风格

        Args:
            ratio: 清理比例，如果为None则使用默认的cleanup_ratio

        Returns:
            清理的风格数量
        """
        old_count = len(self.style_to_id)
        if ratio is not None:
            old_cleanup_ratio = self.cleanup_ratio
            self.cleanup_ratio = ratio
            self._cleanup_styles()
            self.cleanup_ratio = old_cleanup_ratio
        else:
            self._cleanup_styles()

        new_count = len(self.style_to_id)
        cleaned = old_count - new_count
        logger.info(f"手动清理完成: chat_id={self.chat_id}, 清理了 {cleaned} 个风格")
        return cleaned

    def apply_decay(self, factor: float | None = None):
        """
        应用知识衰减

        Args:
            factor: 衰减因子
        """
        self.expressor.decay(factor)
        logger.debug(f"应用知识衰减: chat_id={self.chat_id}")

    def _sync_save(self, base_path: str) -> bool:
        """同步保存逻辑（供异步方法调用）"""
        try:
            # 创建保存目录
            save_dir = os.path.join(base_path, self.chat_id)
            os.makedirs(save_dir, exist_ok=True)

            # 保存expressor模型
            model_path = os.path.join(save_dir, "expressor_model.pkl")
            tmp_model_path = f"{model_path}.tmp"
            self.expressor.save(tmp_model_path)
            os.replace(tmp_model_path, model_path)

            # 保存映射关系和统计信息（原子写）
            meta_path = os.path.join(save_dir, "meta.pkl")

            # 确保 learning_stats 包含所有必要字段
            if "style_last_used" not in self.learning_stats:
                self.learning_stats["style_last_used"] = {}

            meta_data = {
                "style_to_id": self.style_to_id,
                "id_to_style": self.id_to_style,
                "id_to_situation": self.id_to_situation,
                "next_style_id": self.next_style_id,
                "learning_stats": self.learning_stats,
            }

            tmp_meta_path = f"{meta_path}.tmp"
            with open(tmp_meta_path, "wb") as f:
                pickle.dump(meta_data, f, protocol=pickle.HIGHEST_PROTOCOL)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_meta_path, meta_path)
            return True
        except Exception as e:
            logger.error(f"保存StyleLearner失败: {e}")
            return False

    def save(self, base_path: str) -> bool:
        """保存学习器到文件 (兼容旧接口，同步调用)"""
        return self._sync_save(base_path)

    async def save_async(self, base_path: str) -> bool:
        """异步保存学习器到文件"""
        return await asyncio.to_thread(self._sync_save, base_path)

    def load(self, base_path: str) -> bool:
        """
        从文件加载学习器

        Args:
            base_path: 基础加载路径

        Returns:
            是否加载成功
        """
        try:
            save_dir = os.path.join(base_path, self.chat_id)

            # 检查目录是否存在
            if not os.path.exists(save_dir):
                logger.debug(f"StyleLearner保存目录不存在: {save_dir}")
                return False

            # 加载expressor模型
            model_path = os.path.join(save_dir, "expressor_model.pkl")
            if os.path.exists(model_path):
                self.expressor.load(model_path)

            # 加载映射关系和统计信息
            meta_path = os.path.join(save_dir, "meta.pkl")
            if os.path.exists(meta_path):
                with open(meta_path, "rb") as f:
                    meta_data = pickle.load(f)

                self.style_to_id = meta_data["style_to_id"]
                self.id_to_style = meta_data["id_to_style"]
                self.id_to_situation = meta_data["id_to_situation"]
                self.next_style_id = meta_data["next_style_id"]
                self.learning_stats = meta_data["learning_stats"]

                # 确保旧数据兼容：如果没有 style_last_used 字段，添加它
                if "style_last_used" not in self.learning_stats:
                    self.learning_stats["style_last_used"] = {}

            return True

        except Exception as e:
            logger.error(f"加载StyleLearner失败: {e}")
            return False

    def get_stats(self) -> dict:
        """获取统计信息"""
        model_stats = self.expressor.get_stats()
        return {
            "chat_id": self.chat_id,
            "n_styles": len(self.style_to_id),
            "total_samples": self.learning_stats["total_samples"],
            "last_update": self.learning_stats["last_update"],
            "model_stats": model_stats,
        }


class StyleLearnerManager:
    """多聊天室表达风格学习管理器

    添加 LRU 淘汰机制，限制最大活跃 learner 数量
    """

    # 🔧 最大活跃 learner 数量
    MAX_ACTIVE_LEARNERS = 50

    def __init__(self, model_save_path: str = "data/expression/style_models", resource_limit_enabled: bool = True):
        """
        Args:
            model_save_path: 模型保存路径
            resource_limit_enabled: 是否启用资源上限控制（默认开启）
        """
        self.learners: dict[str, StyleLearner] = {}
        self.learner_last_used: dict[str, float] = {}  # 🔧 记录最后使用时间
        self.model_save_path = model_save_path
        self.resource_limit_enabled = resource_limit_enabled

        # 确保保存目录存在
        os.makedirs(model_save_path, exist_ok=True)

        logger.debug(f"StyleLearnerManager初始化成功, 模型保存路径: {model_save_path}")

    def _evict_if_needed(self) -> None:
        """🔧 内存优化：如果超过最大数量，淘汰最久未使用的 learner"""
        if len(self.learners) < self.MAX_ACTIVE_LEARNERS:
            return

        # 按最后使用时间排序，淘汰最旧的 20%
        evict_count = max(1, len(self.learners) // 5)
        sorted_by_time = sorted(
            self.learner_last_used.items(),
            key=lambda x: x[1]
        )

        evicted = []
        for chat_id, last_used in sorted_by_time[:evict_count]:
            if chat_id in self.learners:
                # 先保存再淘汰
                try:
                    self.learners[chat_id].save(self.model_save_path)
                except Exception as e:
                    logger.error(f"LRU淘汰时保存学习器失败: chat_id={chat_id}, error={e}")
                del self.learners[chat_id]
                del self.learner_last_used[chat_id]
                evicted.append(chat_id)

        if evicted:
            logger.info(f"StyleLearner LRU淘汰: 释放了 {len(evicted)} 个不活跃的学习器")

    def get_learner(self, chat_id: str, model_config: dict | None = None) -> StyleLearner:
        """
        获取或创建指定chat_id的学习器

        Args:
            chat_id: 聊天室ID
            model_config: 模型配置

        Returns:
            StyleLearner实例
        """
        # 🔧 更新最后使用时间
        self.learner_last_used[chat_id] = time.time()

        if chat_id not in self.learners:
            # 🔧 检查是否需要淘汰
            self._evict_if_needed()

            # 创建新的学习器
            learner = StyleLearner(
                chat_id,
                model_config,
                resource_limit_enabled=self.resource_limit_enabled,
            )

            # 尝试加载已保存的模型
            learner.load(self.model_save_path)

            self.learners[chat_id] = learner

        return self.learners[chat_id]

    def set_resource_limit(self, enabled: bool) -> None:
        """动态开启/关闭资源上限控制（默认关闭）。"""
        self.resource_limit_enabled = enabled
        for learner in self.learners.values():
            learner.resource_limit_enabled = enabled

    def learn_mapping(self, chat_id: str, up_content: str, style: str) -> bool:
        """
        学习一个映射关系

        Args:
            chat_id: 聊天室ID
            up_content: 前置内容
            style: 目标风格

        Returns:
            是否学习成功
        """
        learner = self.get_learner(chat_id)
        return learner.learn_mapping(up_content, style)

    def predict_style(self, chat_id: str, up_content: str, top_k: int = 5) -> tuple[str | None, dict[str, float]]:
        """
        预测最合适的风格

        Args:
            chat_id: 聊天室ID
            up_content: 前置内容
            top_k: 返回前k个候选

        Returns:
            (最佳style, 分数字典)
        """
        learner = self.get_learner(chat_id)
        return learner.predict_style(up_content, top_k)

    def save_all(self) -> bool:
        """
        保存所有学习器

        Returns:
            是否全部保存成功
        """
        success = True
        for learner in self.learners.values():
            if not learner.save(self.model_save_path):
                success = False

        logger.debug(f"保存所有StyleLearner {'成功' if success else '部分失败'}")
        return success

    def cleanup_all_old_styles(self, ratio: float | None = None) -> dict[str, int]:
        """
        对所有学习器清理旧风格

        Args:
            ratio: 清理比例

        Returns:
            {chat_id: 清理数量}
        """
        cleanup_results = {}
        for chat_id, learner in self.learners.items():
            cleaned = learner.cleanup_old_styles(ratio)
            if cleaned > 0:
                cleanup_results[chat_id] = cleaned

        total_cleaned = sum(cleanup_results.values())
        logger.debug(f"清理所有StyleLearner完成: 总共清理了 {total_cleaned} 个风格")
        return cleanup_results

    def apply_decay_all(self, factor: float | None = None):
        """
        对所有学习器应用知识衰减

        Args:
            factor: 衰减因子
        """
        for learner in self.learners.values():
            learner.apply_decay(factor)

        logger.debug("对所有StyleLearner应用知识衰减")

    def get_all_stats(self) -> dict[str, dict]:
        """
        获取所有学习器的统计信息

        Returns:
            {chat_id: stats}
        """
        return {chat_id: learner.get_stats() for chat_id, learner in self.learners.items()}


# 全局单例
style_learner_manager = StyleLearnerManager()
