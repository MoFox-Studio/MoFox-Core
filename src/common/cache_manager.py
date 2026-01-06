import hashlib
import time
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import orjson

from src.common.config_helpers import resolve_embedding_dimension
from src.common.database.compatibility import db_query, db_save
from src.common.database.core.models import CacheEntries
from src.common.logger import get_logger
from src.common.vector_db import vector_db_service
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest

logger = get_logger("cache_manager")

# 🔍 性能监控：缓存增长检测（保留用于诊断）
_last_cache_report_time = time.time()
_cache_operation_count = 0
_last_l1_size = 0
_last_vector_size = 0


class CacheManager:
    """
    一个支持分层和语义缓存的通用工具缓存管理器。
    采用单例模式，确保在整个应用中只有一个缓存实例。
    L1缓存: 内存字典 (KV) + FAISS (Vector)。
    L2缓存: 数据库 (KV) + ChromaDB (Vector)。
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, default_ttl: int | None = None):
        """
        初始化缓存管理器。
        """
        if not hasattr(self, "_initialized"):
            assert global_config is not None
            assert model_config is not None

            self.default_ttl = default_ttl or 3600
            self.semantic_cache_collection_name = "semantic_cache"

            # L1 缓存 (内存)
            self.l1_kv_cache: dict[str, dict[str, Any]] = {}
            embedding_dim = resolve_embedding_dimension(global_config.lpmm_knowledge.embedding_dimension)
            if not embedding_dim:
                embedding_dim = global_config.lpmm_knowledge.embedding_dimension

            self.embedding_dimension = embedding_dim
            self.l1_vector_index = faiss.IndexFlatIP(embedding_dim)
            self.l1_vector_id_to_key: dict[int, str] = {}

            # L2 向量缓存 (使用新的服务)
            vector_db_service.get_or_create_collection(self.semantic_cache_collection_name)

            # 嵌入模型
            self.embedding_model = LLMRequest(model_config.model_task_config.embedding)

            # 工具调用统计
            self.tool_stats = {
                "total_tool_calls": 0,
                "cache_hits_by_tool": {},  # 按工具名称统计缓存命中
                "execution_times_by_tool": {},  # 按工具名称统计执行时间
                "most_used_tools": {},  # 最常用的工具
            }

            self._initialized = True
            logger.info("缓存管理器已初始化: L1 (内存+FAISS), L2 (数据库+ChromaDB) + 工具统计")

    @staticmethod
    def _validate_embedding(embedding_result: Any) -> np.ndarray | None:
        """
        验证和标准化嵌入向量格式
        """
        try:
            if embedding_result is None:
                return None

            # 确保embedding_result是一维数组或列表
            if isinstance(embedding_result, list | tuple | np.ndarray):
                # 转换为numpy数组进行处理
                embedding_array = np.array(embedding_result)

                # 如果是多维数组，展平它
                if embedding_array.ndim > 1:
                    embedding_array = embedding_array.flatten()

                # 检查维度是否符合预期
                assert global_config is not None
                expected_dim = (
                    getattr(CacheManager, "embedding_dimension", None)
                    or global_config.lpmm_knowledge.embedding_dimension
                )
                if embedding_array.shape[0] != expected_dim:
                    logger.warning(f"嵌入向量维度不匹配: 期望 {expected_dim}, 实际 {embedding_array.shape[0]}")
                    return None

                # 检查是否包含有效的数值
                if np.isnan(embedding_array).any() or np.isinf(embedding_array).any():
                    logger.warning("嵌入向量包含无效的数值 (NaN 或 Inf)")
                    return None

                return embedding_array.astype("float32")
            else:
                logger.warning(f"嵌入结果格式不支持: {type(embedding_result)}")
                return None

        except Exception as e:
            logger.error(f"验证嵌入向量时发生错误: {e}")
            return None

    @staticmethod
    def _generate_key(tool_name: str, function_args: dict[str, Any], tool_file_path: str | Path) -> str:
        """生成确定性的缓存键，包含文件修改时间以实现自动失效。"""
        try:
            tool_file_path = Path(tool_file_path)
            if tool_file_path.exists():
                file_name = tool_file_path.name
                file_mtime = tool_file_path.stat().st_mtime
                file_hash = hashlib.md5(f"{file_name}:{file_mtime}".encode()).hexdigest()
            else:
                file_hash = "unknown"
                logger.warning(f"工具文件不存在: {tool_file_path}")
        except (OSError, TypeError) as e:
            file_hash = "unknown"
            logger.warning(f"无法获取文件信息: {tool_file_path}，错误: {e}")

        try:
            sorted_args = orjson.dumps(function_args, option=orjson.OPT_SORT_KEYS).decode("utf-8")
        except TypeError:
            sorted_args = repr(sorted(function_args.items()))
        return f"{tool_name}::{sorted_args}::{file_hash}"

    async def get(
        self,
        tool_name: str,
        function_args: dict[str, Any],
        tool_file_path: str | Path,
        semantic_query: str | None = None,
    ) -> Any | None:
        """
        从缓存获取结果，查询顺序: L1-KV -> L1-Vector -> L2-KV -> L2-Vector。
        """
        # 步骤 1: L1 精确缓存查询
        key = self._generate_key(tool_name, function_args, tool_file_path)
        logger.debug(f"生成的缓存键: {key}")
        if semantic_query:
            logger.debug(f"使用的语义查询: '{semantic_query}'")

        if key in self.l1_kv_cache:
            entry = self.l1_kv_cache[key]
            if time.time() < entry["expires_at"]:
                logger.debug(f"命中L1键值缓存: {key}")
                return entry["data"]
            else:
                del self.l1_kv_cache[key]

        # 步骤 2: L1/L2 语义和L2精确缓存查询
        query_embedding = None
        if semantic_query and self.embedding_model:
            embedding_result = await self.embedding_model.get_embedding(semantic_query)
            if embedding_result:
                # embedding_result是一个元组(embedding_vector, model_name)，取第一个元素
                embedding_vector = embedding_result[0] if isinstance(embedding_result, tuple) else embedding_result
                validated_embedding = self._validate_embedding(embedding_vector)
                if validated_embedding is not None:
                    query_embedding = np.array([validated_embedding], dtype="float32")

        # 步骤 2a: L1 语义缓存 (FAISS)
        if query_embedding is not None and self.l1_vector_index.ntotal > 0:
            faiss.normalize_L2(query_embedding)
            distances, indices = self.l1_vector_index.search(query_embedding, 1)  # type: ignore
            if indices.size > 0 and distances[0][0] > 0.75:  # IP 越大越相似
                hit_index = indices[0][0]
                l1_hit_key = self.l1_vector_id_to_key.get(hit_index)
                if l1_hit_key and l1_hit_key in self.l1_kv_cache:
                    logger.debug(f"命中L1语义缓存: {l1_hit_key}")
                    return self.l1_kv_cache[l1_hit_key]["data"]

        # 步骤 2b: L2 精确缓存 (数据库)
        cache_results_obj = await db_query(
            model_class=CacheEntries, query_type="get", filters={"cache_key": key}, single_result=True
        )

        if cache_results_obj:
            # 使用 getattr 安全访问属性，避免 Pylance 类型检查错误
            expires_at = getattr(cache_results_obj, "expires_at", 0)
            if time.time() < expires_at:
                logger.debug(f"命中L2键值缓存: {key}")
                cache_value = getattr(cache_results_obj, "cache_value", "{}")
                data = orjson.loads(cache_value)

                # 更新访问统计
                await db_query(
                    model_class=CacheEntries,
                    query_type="update",
                    filters={"cache_key": key},
                    data={
                        "last_accessed": time.time(),
                        "access_count": getattr(cache_results_obj, "access_count", 0) + 1,
                    },
                )

                # 回填 L1
                self.l1_kv_cache[key] = {"data": data, "expires_at": expires_at}
                return data
            else:
                # 删除过期的缓存条目
                await db_query(model_class=CacheEntries, query_type="delete", filters={"cache_key": key})

        # 步骤 2c: L2 语义缓存 (VectorDB Service)
        if query_embedding is not None:
            try:
                results = vector_db_service.query(
                    collection_name=self.semantic_cache_collection_name,
                    query_embeddings=query_embedding.tolist(),
                    n_results=1,
                )
                if results and results.get("ids") and results["ids"][0]:
                    distance = (
                        results["distances"][0][0] if results.get("distances") and results["distances"][0] else "N/A"
                    )
                    logger.debug(f"L2语义搜索找到最相似的结果: id={results['ids'][0]}, 距离={distance}")

                    if distance != "N/A" and distance < 0.75:
                        l2_hit_key = results["ids"][0][0] if isinstance(results["ids"][0], list) else results["ids"][0]
                        logger.debug(f"命中L2语义缓存: key='{l2_hit_key}', 距离={distance:.4f}")

                        # 从数据库获取缓存数据
                        semantic_cache_results_obj = await db_query(
                            model_class=CacheEntries,
                            query_type="get",
                            filters={"cache_key": l2_hit_key},
                            single_result=True,
                        )

                        if semantic_cache_results_obj:
                            expires_at = getattr(semantic_cache_results_obj, "expires_at", 0)
                            if time.time() < expires_at:
                                cache_value = getattr(semantic_cache_results_obj, "cache_value", "{}")
                                data = orjson.loads(cache_value)
                                logger.debug(f"L2语义缓存返回的数据: {data}")

                                # 回填 L1
                                self.l1_kv_cache[key] = {"data": data, "expires_at": expires_at}
                                if query_embedding is not None:
                                    try:
                                        new_id = self.l1_vector_index.ntotal
                                        faiss.normalize_L2(query_embedding)
                                        self.l1_vector_index.add(x=query_embedding)  # type: ignore
                                        self.l1_vector_id_to_key[new_id] = key
                                    except Exception as e:
                                        logger.error(f"回填L1向量索引时发生错误: {e}")
                                return data
            except Exception as e:
                logger.warning(f"VectorDB Service 查询失败: {e}")

        logger.debug(f"缓存未命中: {key}")
        return None

    async def set(
        self,
        tool_name: str,
        function_args: dict[str, Any],
        tool_file_path: str | Path,
        data: Any,
        ttl: int | None = None,
        semantic_query: str | None = None,
    ):
        """将结果存入所有缓存层。"""
        if ttl is None:
            ttl = self.default_ttl
        if ttl <= 0:
            return

        key = self._generate_key(tool_name, function_args, tool_file_path)
        expires_at = time.time() + ttl

        # 写入 L1
        self.l1_kv_cache[key] = {"data": data, "expires_at": expires_at}

        # 写入 L2 (数据库)
        cache_data = {
            "cache_key": key,
            "cache_value": orjson.dumps(data).decode("utf-8"),
            "expires_at": expires_at,
            "tool_name": tool_name,
            "created_at": time.time(),
            "last_accessed": time.time(),
            "access_count": 1,
        }

        await db_save(model_class=CacheEntries, data=cache_data, key_field="cache_key", key_value=key)

        # 写入语义缓存
        if semantic_query and self.embedding_model:
            try:
                embedding_result = await self.embedding_model.get_embedding(semantic_query)
                if embedding_result:
                    embedding_vector = embedding_result[0] if isinstance(embedding_result, tuple) else embedding_result
                    validated_embedding = self._validate_embedding(embedding_vector)
                    if validated_embedding is not None:
                        embedding = np.array([validated_embedding], dtype="float32")

                        # 写入 L1 Vector
                        new_id = self.l1_vector_index.ntotal
                        faiss.normalize_L2(embedding)
                        self.l1_vector_index.add(x=embedding)  # type: ignore
                        self.l1_vector_id_to_key[new_id] = key

                        # 写入 L2 Vector (使用新的服务)
                        vector_db_service.add(
                            collection_name=self.semantic_cache_collection_name,
                            embeddings=embedding.tolist(),
                            ids=[key],
                        )
            except Exception as e:
                logger.warning(f"语义缓存写入失败: {e}")

        # 🔍 监控：记录缓存增长
        global _last_cache_report_time, _cache_operation_count, _last_l1_size, _last_vector_size
        _cache_operation_count += 1
        
        # 定期输出缓存状态（每100次操作或每5分钟）
        current_time = time.time()
        if _cache_operation_count % 100 == 0 or (current_time - _last_cache_report_time) > 300:
            current_l1_size = len(self.l1_kv_cache)
            current_vector_size = self.l1_vector_index.ntotal if hasattr(self.l1_vector_index, 'ntotal') else 0
            
            l1_growth = current_l1_size - _last_l1_size
            vector_growth = current_vector_size - _last_vector_size
            
            logger.info(
                f"📊 [缓存监控] L1缓存: {current_l1_size}条 (增长+{l1_growth}) | "
                f"向量索引: {current_vector_size}条 (增长+{vector_growth}) | "
                f"总操作数: {_cache_operation_count}"
            )
            
            # 🚨 检查是否持续增长且从未清理
            if current_l1_size > 500:
                logger.warning(
                    f"⚠️ [性能警告] L1缓存已经达到 {current_l1_size} 条，可能存在内存泄漏！"
                    f"检查 clean_expired() 方法是否被定期调用。"
                )
            
            if current_vector_size > 300:
                logger.warning(
                    f"⚠️ [性能警告] 向量索引已达 {current_vector_size} 条，查询性能可能下降。"
                )
            
            _last_cache_report_time = current_time
            _last_l1_size = current_l1_size
            _last_vector_size = current_vector_size

        logger.debug(f"已缓存条目: {key}, TTL: {ttl}s")

    def clear_l1(self):
        """清空L1缓存。"""
        self.l1_kv_cache.clear()
        self.l1_vector_index.reset()
        self.l1_vector_id_to_key.clear()
        logger.info("L1 (内存+FAISS) 缓存已清空。")

    async def clear_l2(self):
        """清空L2缓存。"""
        # 清空数据库缓存
        await db_query(
            model_class=CacheEntries,
            query_type="delete",
            filters={},  # 删除所有记录
        )

        # 清空 VectorDB
        try:
            vector_db_service.delete_collection(name=self.semantic_cache_collection_name)
            vector_db_service.get_or_create_collection(name=self.semantic_cache_collection_name)
        except Exception as e:
            logger.warning(f"清空 VectorDB 集合失败: {e}")

        logger.info("L2 (数据库 & VectorDB) 缓存已清空。")

    async def clear_all(self):
        """清空所有缓存。"""
        self.clear_l1()
        await self.clear_l2()
        logger.info("所有缓存层级已清空。")

    async def clean_expired(self):
        """清理过期的缓存条目"""
        current_time = time.time()

        # 清理L1过期条目
        expired_keys = []
        for key, entry in self.l1_kv_cache.items():
            if current_time >= entry["expires_at"]:
                expired_keys.append(key)

        for key in expired_keys:
            del self.l1_kv_cache[key]

        # 清理L2过期条目
        await db_query(model_class=CacheEntries, query_type="delete", filters={"expires_at": {"$lt": current_time}})

        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期的L1缓存条目")

    def get_health_stats(self) -> dict[str, Any]:
        """获取缓存健康统计信息"""
        # 简化的健康统计，不包含内存监控（因为相关属性未定义）
        return {
            "l1_count": len(self.l1_kv_cache),
            "l1_vector_count": self.l1_vector_index.ntotal if hasattr(self.l1_vector_index, "ntotal") else 0,
            "tool_stats": {
                "total_tool_calls": self.tool_stats.get("total_tool_calls", 0),
                "tracked_tools": len(self.tool_stats.get("most_used_tools", {})),
                "cache_hits": sum(data.get("hits", 0) for data in self.tool_stats.get("cache_hits_by_tool", {}).values()),
                "cache_misses": sum(data.get("misses", 0) for data in self.tool_stats.get("cache_hits_by_tool", {}).values()),
            }
        }

    def check_health(self) -> tuple[bool, list[str]]:
        """检查缓存健康状态

        Returns:
            (is_healthy, warnings) - 是否健康，警告列表
        """
        warnings = []

        # 检查L1缓存大小
        l1_size = len(self.l1_kv_cache)
        if l1_size > 1000:  # 如果超过1000个条目
            warnings.append(f"⚠️ L1缓存条目数较多: {l1_size}")

        # 检查向量索引大小
        vector_count = self.l1_vector_index.ntotal if hasattr(self.l1_vector_index, "ntotal") else 0
        if isinstance(vector_count, int) and vector_count > 500:
            warnings.append(f"⚠️ 向量索引条目数较多: {vector_count}")

        # 检查工具统计健康
        total_calls = self.tool_stats.get("total_tool_calls", 0)
        if total_calls > 0:
            total_hits = sum(data.get("hits", 0) for data in self.tool_stats.get("cache_hits_by_tool", {}).values())
            cache_hit_rate = (total_hits / total_calls) * 100
            if cache_hit_rate < 50:  # 缓存命中率低于50%
                warnings.append(f"⚡ 整体缓存命中率较低: {cache_hit_rate:.1f}%")

        return len(warnings) == 0, warnings

    async def get_tool_result_with_stats(self,
                                       tool_name: str,
                                       function_args: dict[str, Any],
                                       tool_file_path: str | Path,
                                       semantic_query: str | None = None) -> tuple[Any | None, bool]:
        """获取工具结果并更新统计信息

        Args:
            tool_name: 工具名称
            function_args: 函数参数
            tool_file_path: 工具文件路径
            semantic_query: 语义查询字符串

        Returns:
            Tuple[结果, 是否命中缓存]
        """
        # 更新总调用次数
        self.tool_stats["total_tool_calls"] += 1

        # 🔧 限制统计字典大小，防止内存泄漏
        MAX_TOOLS_TRACKED = 100  # 最多跟踪100个不同的工具
        
        # 更新工具使用统计
        if tool_name not in self.tool_stats["most_used_tools"]:
            # 如果已达上限，删除使用最少的工具
            if len(self.tool_stats["most_used_tools"]) >= MAX_TOOLS_TRACKED:
                least_used = min(self.tool_stats["most_used_tools"].items(), key=lambda x: x[1])
                del self.tool_stats["most_used_tools"][least_used[0]]
                # 同时清理相关统计
                self.tool_stats["cache_hits_by_tool"].pop(least_used[0], None)
                self.tool_stats["execution_times_by_tool"].pop(least_used[0], None)
            self.tool_stats["most_used_tools"][tool_name] = 0
        self.tool_stats["most_used_tools"][tool_name] += 1

        # 尝试获取缓存
        result = await self.get(tool_name, function_args, tool_file_path, semantic_query)

        # 更新缓存命中统计
        if tool_name not in self.tool_stats["cache_hits_by_tool"]:
            self.tool_stats["cache_hits_by_tool"][tool_name] = {"hits": 0, "misses": 0}

        if result is not None:
            self.tool_stats["cache_hits_by_tool"][tool_name]["hits"] += 1
            logger.info(f"工具缓存命中: {tool_name}")
            return result, True
        else:
            self.tool_stats["cache_hits_by_tool"][tool_name]["misses"] += 1
            return None, False

    async def set_tool_result_with_stats(self,
                                       tool_name: str,
                                       function_args: dict[str, Any],
                                       tool_file_path: str | Path,
                                       data: Any,
                                       execution_time: float | None = None,
                                       ttl: int | None = None,
                                       semantic_query: str | None = None):
        """存储工具结果并更新统计信息

        Args:
            tool_name: 工具名称
            function_args: 函数参数
            tool_file_path: 工具文件路径
            data: 结果数据
            execution_time: 执行时间
            ttl: 缓存TTL
            semantic_query: 语义查询字符串
        """
        # 更新执行时间统计
        if execution_time is not None:
            if tool_name not in self.tool_stats["execution_times_by_tool"]:
                self.tool_stats["execution_times_by_tool"][tool_name] = []
            self.tool_stats["execution_times_by_tool"][tool_name].append(execution_time)

            # 只保留最近100次的执行时间记录
            if len(self.tool_stats["execution_times_by_tool"][tool_name]) > 100:
                self.tool_stats["execution_times_by_tool"][tool_name] = \
                    self.tool_stats["execution_times_by_tool"][tool_name][-100:]

        # 存储到缓存
        await self.set(tool_name, function_args, tool_file_path, data, ttl, semantic_query)

    def get_tool_performance_stats(self) -> dict[str, Any]:
        """获取工具性能统计信息

        Returns:
            统计信息字典
        """
        stats = self.tool_stats.copy()

        # 计算平均执行时间
        avg_times = {}
        for tool_name, times in stats["execution_times_by_tool"].items():
            if times:
                avg_times[tool_name] = {
                    "average": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times),
                    "count": len(times),
                }

        # 计算缓存命中率
        cache_hit_rates = {}
        for tool_name, hit_data in stats["cache_hits_by_tool"].items():
            total = hit_data["hits"] + hit_data["misses"]
            if total > 0:
                cache_hit_rates[tool_name] = {
                    "hit_rate": (hit_data["hits"] / total) * 100,
                    "hits": hit_data["hits"],
                    "misses": hit_data["misses"],
                    "total": total,
                }

        # 按使用频率排序工具
        most_used = sorted(stats["most_used_tools"].items(), key=lambda x: x[1], reverse=True)

        return {
            "total_tool_calls": stats["total_tool_calls"],
            "average_execution_times": avg_times,
            "cache_hit_rates": cache_hit_rates,
            "most_used_tools": most_used[:10],  # 前10个最常用工具
            "cache_health": self.get_health_stats(),
        }

    def get_tool_recommendations(self) -> dict[str, Any]:
        """获取工具优化建议

        Returns:
            优化建议字典
        """
        recommendations = []

        # 分析缓存命中率低的工具
        cache_hit_rates = {}
        for tool_name, hit_data in self.tool_stats["cache_hits_by_tool"].items():
            total = hit_data["hits"] + hit_data["misses"]
            if total >= 5:  # 至少调用5次才分析
                hit_rate = (hit_data["hits"] / total) * 100
                cache_hit_rates[tool_name] = hit_rate

                if hit_rate < 30:  # 缓存命中率低于30%
                    recommendations.append({
                        "tool": tool_name,
                        "type": "low_cache_hit_rate",
                        "message": f"工具 {tool_name} 的缓存命中率仅为 {hit_rate:.1f}%，建议检查缓存配置或参数变化频率",
                        "severity": "medium" if hit_rate > 10 else "high",
                    })

        # 分析执行时间长的工具
        for tool_name, times in self.tool_stats["execution_times_by_tool"].items():
            if len(times) >= 3:  # 至少3次执行才分析
                avg_time = sum(times) / len(times)
                if avg_time > 5.0:  # 平均执行时间超过5秒
                    recommendations.append({
                        "tool": tool_name,
                        "type": "slow_execution",
                        "message": f"工具 {tool_name} 平均执行时间较长 ({avg_time:.2f}s)，建议优化算法或增加缓存",
                        "severity": "medium" if avg_time < 10.0 else "high",
                    })

        return {
            "recommendations": recommendations,
            "summary": {
                "total_issues": len(recommendations),
                "high_priority": len([r for r in recommendations if r["severity"] == "high"]),
                "medium_priority": len([r for r in recommendations if r["severity"] == "medium"]),
            }
        }

    async def recall_relevant_cache(
        self,
        query_text: str,
        tool_name: str | None = None,
        top_k: int = 3,
        similarity_threshold: float = 0.70,
    ) -> list[dict[str, Any]]:
        """
        根据语义相似度主动召回相关的缓存条目

        用于在回复前扫描缓存，找到与当前对话相关的历史搜索结果

        Args:
            query_text: 用于语义匹配的查询文本（通常是最近几条聊天内容）
            tool_name: 可选，限制只召回特定工具的缓存（如 "web_search"）
            top_k: 返回的最大结果数
            similarity_threshold: 相似度阈值（L2距离，越小越相似）

        Returns:
            相关缓存条目列表，每个条目包含 {tool_name, query, content, similarity}
        """
        if not query_text or not self.embedding_model:
            return []

        try:
            # 生成查询向量
            embedding_result = await self.embedding_model.get_embedding(query_text)
            if not embedding_result:
                return []

            embedding_vector = embedding_result[0] if isinstance(embedding_result, tuple) else embedding_result
            validated_embedding = self._validate_embedding(embedding_vector)
            if validated_embedding is None:
                return []

            query_embedding = np.array([validated_embedding], dtype="float32")

            # 从 L2 向量数据库查询
            results = vector_db_service.query(
                collection_name=self.semantic_cache_collection_name,
                query_embeddings=query_embedding.tolist(),
                n_results=top_k * 2,  # 多取一些，后面会过滤
            )

            if not results or not results.get("ids") or not results["ids"][0]:
                logger.debug("[缓存召回] 未找到相关缓存")
                return []

            recalled_items = []
            ids = results["ids"][0] if isinstance(results["ids"][0], list) else [results["ids"][0]]
            distances = results.get("distances", [[]])[0] if results.get("distances") else []

            for i, cache_key in enumerate(ids):
                distance = distances[i] if i < len(distances) else 1.0

                # 过滤相似度不够的
                if distance > similarity_threshold:
                    continue

                # 从数据库获取缓存数据
                cache_obj = await db_query(
                    model_class=CacheEntries,
                    query_type="get",
                    filters={"cache_key": cache_key},
                    single_result=True,
                )

                if not cache_obj:
                    continue

                # 检查是否过期
                expires_at = getattr(cache_obj, "expires_at", 0)
                if time.time() >= expires_at:
                    continue

                # 获取工具名称并过滤
                cached_tool_name = getattr(cache_obj, "tool_name", "")
                if tool_name and cached_tool_name != tool_name:
                    continue

                # 解析缓存内容
                try:
                    cache_value = getattr(cache_obj, "cache_value", "{}")
                    data = orjson.loads(cache_value)
                    content = data.get("content", "") if isinstance(data, dict) else str(data)

                    # 从 cache_key 中提取原始查询（格式: tool_name::{"query": "xxx", ...}::file_hash）
                    original_query = ""
                    try:
                        key_parts = cache_key.split("::")
                        if len(key_parts) >= 2:
                            args_json = key_parts[1]
                            args = orjson.loads(args_json)
                            original_query = args.get("query", "")
                    except Exception:
                        pass

                    recalled_items.append({
                        "tool_name": cached_tool_name,
                        "query": original_query,
                        "content": content,
                        "similarity": 1.0 - distance,  # 转换为相似度分数
                    })

                except Exception as e:
                    logger.warning(f"解析缓存内容失败: {e}")
                    continue

                if len(recalled_items) >= top_k:
                    break

            if recalled_items:
                logger.info(f"[缓存召回] 找到 {len(recalled_items)} 条相关缓存")

            return recalled_items

        except Exception as e:
            logger.error(f"[缓存召回] 语义召回失败: {e}")
            return []


# 全局实例
tool_cache = CacheManager()
