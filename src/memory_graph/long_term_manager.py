"""
长期记忆层管理器 (Long-term Memory Manager)

负责管理长期记忆图：
- 短期记忆到长期记忆的转移
- 结构化提取 + 直接 CRUD
- 激活度衰减优化（长期记忆衰减更慢）
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any


from src.common.logger import get_logger
from src.memory_graph.manager import MemoryManager
from src.memory_graph.models import Memory, ShortTermMemory

logger = get_logger(__name__)


class LongTermMemoryManager:
    """
    长期记忆层管理器

    基于现有的 MemoryManager，扩展支持：
    - 短期记忆的批量转移
    - 图操作语言的解析和执行
    - 优化的激活度衰减策略
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        batch_size: int = 10,
        search_top_k: int = 5,
        llm_temperature: float = 0.2,
        long_term_decay_factor: float = 0.95,
    ):
        """
        初始化长期记忆层管理器

        Args:
            memory_manager: 现有的 MemoryManager 实例
            batch_size: 批量处理的短期记忆数量
            search_top_k: 检索相似记忆的数量
            llm_temperature: LLM 决策的温度参数
            long_term_decay_factor: 长期记忆的衰减因子（比短期记忆慢）
        """
        self.memory_manager = memory_manager
        self.batch_size = batch_size
        self.search_top_k = search_top_k
        self.llm_temperature = llm_temperature
        self.long_term_decay_factor = long_term_decay_factor

        # 状态
        self._initialized = False

        # 批量embedding生成队列
        self._pending_embeddings: list[tuple[str, str]] = []  # (node_id, content)
        self._embedding_batch_size = 10
        self._embedding_lock = asyncio.Lock()
        self._failed_embedding_nodes: set[str] = set()  # 记录失败的节点ID，避免重复尝试
        self._embedding_batch_retry_limit = 2
        self._embedding_single_retry_limit = 2
        self._embedding_failure_threshold = 3
        self._embedding_consecutive_failures = 0
        self._embedding_cooldown_seconds = 5.0
        self._embedding_cooldown_until: float | None = None
        self._embedding_failed_count = 0

        # 相似记忆缓存 (stm_id -> memories)
        self._similar_memory_cache: dict[str, list[Memory]] = {}
        self._cache_max_size = 100

        # 错误/重试统计与配置
        self._max_process_retries = 2
        self._retry_backoff = 0.5
        self._total_processed = 0
        self._failed_single_memory_count = 0
        self._retry_attempts = 0

        logger.info(
            f"长期记忆管理器已创建 (batch_size={batch_size}, "
            f"search_top_k={search_top_k}, decay_factor={long_term_decay_factor:.2f})"
        )

    async def initialize(self) -> None:
        """初始化管理器"""
        if self._initialized:
            logger.warning("长期记忆管理器已经初始化")
            return

        try:
            logger.debug("开始初始化长期记忆管理器...")

            # 确保底层 MemoryManager 已初始化
            if not self.memory_manager._initialized:
                await self.memory_manager.initialize()

            self._initialized = True
            logger.debug("长期记忆管理器初始化完成")

        except Exception as e:
            logger.error(f"长期记忆管理器初始化失败: {e}")
            raise

    async def transfer_from_short_term(
        self, short_term_memories: list[ShortTermMemory]
    ) -> dict[str, Any]:
        """
        将短期记忆批量转移到长期记忆

        流程：
        1. 分批处理短期记忆
        2. 对每条短期记忆，在长期记忆中检索相似记忆
        3. 将短期记忆和候选长期记忆发送给 LLM 决策
        4. 解析并执行图操作指令
        5. 保存更新

        Args:
            short_term_memories: 待转移的短期记忆列表

        Returns:
            转移结果统计
        """
        if not self._initialized:
            await self.initialize()

        try:
            logger.debug(f"开始转移 {len(short_term_memories)} 条短期记忆到长期记忆...")

            result = {
                "processed_count": 0,
                "created_count": 0,
                "updated_count": 0,
                "merged_count": 0,
                "failed_count": 0,
                "transferred_memory_ids": [],
            }

            # 分批处理
            for batch_start in range(0, len(short_term_memories), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(short_term_memories))
                batch = short_term_memories[batch_start:batch_end]

                logger.info(
                    f"处理批次 {batch_start // self.batch_size + 1}/"
                    f"{(len(short_term_memories) - 1) // self.batch_size + 1} "
                    f"({len(batch)} 条记忆)"
                )

                # 处理当前批次
                batch_result = await self._process_batch(batch)

                # 汇总结果
                result["processed_count"] += batch_result["processed_count"]
                result["created_count"] += batch_result["created_count"]
                result["updated_count"] += batch_result["updated_count"]
                result["merged_count"] += batch_result["merged_count"]
                result["failed_count"] += batch_result["failed_count"]
                result["transferred_memory_ids"].extend(batch_result["transferred_memory_ids"])

                # 让出控制权
                await asyncio.sleep(0.01)

            logger.debug(f"短期记忆转移完成: {result}")
            return result

        except Exception as e:
            logger.error(f"转移短期记忆失败: {e}")
            return {"error": str(e), "processed_count": 0}

    async def _process_batch(self, batch: list[ShortTermMemory]) -> dict[str, Any]:
        """
        处理一批短期记忆（并行处理）

        Args:
            batch: 短期记忆批次

        Returns:
            批次处理结果
        """
        result = {
            "processed_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "merged_count": 0,
            "failed_count": 0,
            "transferred_memory_ids": [],
        }

        # 并行处理批次中的所有记忆
        # 从配置获取最大并发LLM调用数
        max_concurrent = getattr(self.memory_manager.config, "max_concurrent_llm_calls", 3) if self.memory_manager.config else 3
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _process_with_limit(stm: ShortTermMemory):
            """带信号量限制的单记忆处理"""
            async with semaphore:
                return await self._process_single_memory(stm)

        tasks = [_process_with_limit(stm) for stm in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 汇总结果
        for stm, single_result in zip(batch, results):
            if isinstance(single_result, Exception):
                logger.error(f"处理短期记忆 {stm.id} 失败: {single_result}")
                result["failed_count"] += 1
            elif single_result and isinstance(single_result, dict):
                result["processed_count"] += 1
                result["transferred_memory_ids"].append(stm.id)

                action = single_result.get("action", "create")
                if action == "create":
                    result["created_count"] += 1
                elif action == "update":
                    result["updated_count"] += 1
                elif action == "merge":
                    result["merged_count"] += 1
            else:
                result["failed_count"] += 1

        # 更新全局计数
        self._total_processed += result["processed_count"]
        self._failed_single_memory_count += result["failed_count"]

        # 处理完批次后，批量生成embeddings
        await self._flush_pending_embeddings()

        return result

    async def _process_single_memory(self, stm: ShortTermMemory) -> dict[str, Any] | None:
        """
        处理单条短期记忆（简化版）

        1. 检索相似长期记忆
        2. LLM 提取结构化字段
        3. 直接 CRUD 到图谱

        Args:
            stm: 短期记忆

        Returns:
            处理结果或None（如果失败）
        """
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self._max_process_retries:
            try:
                # 步骤1: 在长期记忆中检索相似记忆
                similar_memories = await self._search_similar_long_term_memories(stm)

                # 步骤2: LLM 提取结构化字段 + 决策 (create/update/merge)
                extraction = await self._extract_structured_memory(stm, similar_memories)

                # 步骤3: 执行 CRUD
                memory_id = await self._upsert_long_term_memory(extraction, stm)
                action = extraction.get("action", "create")  # 回退时 _upsert 会更新为 "create"

                if memory_id:
                    return {
                        "success": True,
                        "action": action,
                        "memory_id": memory_id,
                    }

                last_exc = RuntimeError("_upsert_long_term_memory 返回空")
                raise last_exc

            except Exception as e:
                last_exc = e
                attempt += 1
                if attempt <= self._max_process_retries:
                    self._retry_attempts += 1
                    backoff = self._retry_backoff * attempt
                    logger.warning(
                        f"处理短期记忆 {stm.id} 时发生可恢复错误，重试 {attempt}/{self._max_process_retries}，等待 {backoff}s: {e}"
                    )
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"处理短期记忆 {stm.id} 最终失败: {last_exc}")
                self._failed_single_memory_count += 1
                return None

    async def _search_similar_long_term_memories(
        self, stm: ShortTermMemory
    ) -> list[Memory]:
        """
        在长期记忆中检索与短期记忆相似的记忆

        优化：使用缓存并减少重复查询
        """
        # 检查缓存
        if stm.id in self._similar_memory_cache:
            logger.debug(f"使用缓存的相似记忆: {stm.id}")
            return self._similar_memory_cache[stm.id]

        try:
            from src.config.config import global_config

            # 检查是否启用了高级路径扩展算法
            use_path_expansion = getattr(global_config.memory, "enable_path_expansion", False)
            expand_depth = getattr(global_config.memory, "path_expansion_max_hops", 2) if use_path_expansion else 0

            # 1. 检索记忆
            memories = await self.memory_manager.search_memories(
                query=stm.content,
                top_k=self.search_top_k,
                include_forgotten=False,
                use_multi_query=getattr(global_config.memory, "use_multi_query", True),  # 从配置读取，默认启用多查询
                expand_depth=expand_depth
            )

            # 2. 如果启用了高级路径扩展，直接返回
            if use_path_expansion:
                logger.debug(f"已使用路径扩展算法检索到 {len(memories)} 条记忆")
                self._cache_similar_memories(stm.id, memories)
                return memories

            # 3. 简化的图扩展（仅在未启用高级算法时）
            if memories:
                # 批量获取相关记忆ID，减少单次查询
                related_ids_batch = await self._batch_get_related_memories(
                    [m.id for m in memories], max_depth=1, max_per_memory=2
                )

                # 批量加载相关记忆
                seen_ids = {m.id for m in memories}
                new_memories = []
                for rid in related_ids_batch:
                    if rid not in seen_ids and len(new_memories) < self.search_top_k:
                        related_mem = await self.memory_manager.get_memory(rid)
                        if related_mem:
                            new_memories.append(related_mem)
                            seen_ids.add(rid)

                memories.extend(new_memories)

            logger.debug(f"为短期记忆 {stm.id} 找到 {len(memories)} 个长期记忆")

            # 缓存结果
            self._cache_similar_memories(stm.id, memories)
            return memories

        except Exception as e:
            logger.error(f"检索相似长期记忆失败: {e}")
            return []

    async def _batch_get_related_memories(
        self, memory_ids: list[str], max_depth: int = 1, max_per_memory: int = 2
    ) -> set[str]:
        """
        批量获取相关记忆ID

        Args:
            memory_ids: 记忆ID列表
            max_depth: 最大深度
            max_per_memory: 每个记忆最多获取的相关记忆数

        Returns:
            相关记忆ID集合
        """
        all_related_ids = set()

        try:
            for mem_id in memory_ids:
                if len(all_related_ids) >= max_per_memory * len(memory_ids):
                    break

                try:
                    related_ids = self.memory_manager._get_related_memories(mem_id, max_depth=max_depth)
                    # 限制每个记忆的相关数量
                    for rid in list(related_ids)[:max_per_memory]:
                        all_related_ids.add(rid)
                except Exception as e:
                    logger.warning(f"获取记忆 {mem_id} 的相关记忆失败: {e}")

        except Exception as e:
            logger.error(f"批量获取相关记忆失败: {e}")

        return all_related_ids

    def _cache_similar_memories(self, stm_id: str, memories: list[Memory]) -> None:
        """
        缓存相似记忆

        Args:
            stm_id: 短期记忆ID
            memories: 相似记忆列表
        """
        # 简单的LRU策略：如果超过最大缓存数，删除最早的
        if len(self._similar_memory_cache) >= self._cache_max_size:
            # 删除第一个（最早的）
            first_key = next(iter(self._similar_memory_cache))
            del self._similar_memory_cache[first_key]

        self._similar_memory_cache[stm_id] = memories

    async def _extract_structured_memory(
        self, stm: ShortTermMemory, similar_memories: list[Memory]
    ) -> dict[str, Any]:
        """
        使用 LLM 从短期记忆中提取结构化字段

        替代旧的 _decide_graph_operations，LLM 不再输出图操作指令，
        而是输出简单的结构化字段 + action (create/update/merge)。

        Args:
            stm: 短期记忆
            similar_memories: 相似的长期记忆列表

        Returns:
            {"action": "create"|"update"|"merge", "subject": ..., "topic": ..., ...}
        """
        try:
            from src.config.config import model_config
            from src.llm_models.utils_model import LLMRequest

            prompt = self._build_extraction_prompt(stm, similar_memories)

            llm = LLMRequest(
                model_set=model_config.model_task_config.memory_long_term_builder,
                request_type="long_term_memory.structured_extraction",
            )

            response, _ = await llm.generate_response_async(
                prompt,
                temperature=self.llm_temperature,
                max_tokens=800,
            )

            result = self._parse_extraction_result(response, stm)
            logger.debug(
                f"LLM 提取结果: action={result.get('action')}, "
                f"subject={result.get('subject')}, topic={result.get('topic')}"
            )
            return result

        except Exception as e:
            logger.error(f"LLM 结构化提取失败: {e}")
            return {
                "action": "create",
                "subject": stm.subject or "未知",
                "topic": stm.topic or stm.content[:50],
                "object": stm.object,
                "memory_type": stm.memory_type or "fact",
                "importance": stm.importance,
                "attributes": stm.attributes,
            }

    def _build_extraction_prompt(
        self, stm: ShortTermMemory, similar_memories: list[Memory]
    ) -> str:
        """构建结构化提取的 LLM 提示词（简化版）"""

        stm_desc = f"""- 内容: {stm.content}
- 主体: {stm.subject or '未指定'}
- 主题: {stm.topic or '未指定'}
- 客体: {stm.object or '未指定'}
- 类型: {stm.memory_type or '未指定'}
- 重要性: {stm.importance:.2f}
- 属性: {json.dumps(stm.attributes, ensure_ascii=False)}"""

        similar_desc = ""
        if similar_memories:
            lines = []
            for i, mem in enumerate(similar_memories[:5]):
                lines.append(
                    f"{i + 1}. [ID: {mem.id}] {mem.to_text()[:200]}"
                )
            similar_desc = "\n".join(lines)
        else:
            similar_desc = "（无相似记忆）"

        return f"""你是记忆结构化提取专家。分析以下短期记忆和候选长期记忆，输出一个 JSON 对象。

**短期记忆：**
{stm_desc}

**候选长期记忆：**
{similar_desc}

**决策规则：**
- 如果短期记忆与候选记忆无关联 → `"action": "create"`
- 如果短期记忆补充/修正了某条候选记忆 → `"action": "update"`，填 `target_memory_id`
- 如果短期记忆与某条候选记忆高度重叠 → `"action": "merge"`，填 `target_memory_id`

**输出格式（纯 JSON）：**
```json
{{
  "action": "create",
  "subject": "...",
  "topic": "...",
  "object": "...",
  "memory_type": "fact",
  "importance": 0.7,
  "attributes": {{}},
  "target_memory_id": null
}}
```"""

    def _parse_extraction_result(
        self, response: str, stm: ShortTermMemory
    ) -> dict[str, Any]:
        """解析 LLM 的结构化提取结果"""
        import json as _json

        try:
            # 提取 JSON
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()

            # 移除注释
            json_str = re.sub(r"//.*", "", json_str)

            data = _json.loads(json_str)
            if not isinstance(data, dict):
                raise ValueError("结果不是字典")

            return {
                "action": data.get("action", "create"),
                "subject": data.get("subject", stm.subject or "未知"),
                "topic": data.get("topic", stm.topic or stm.content[:50]),
                "object": data.get("object", stm.object),
                "memory_type": data.get("memory_type", stm.memory_type or "fact"),
                "importance": float(data.get("importance", stm.importance)),
                "attributes": data.get("attributes", stm.attributes or {}),
                "target_memory_id": data.get("target_memory_id"),
            }

        except Exception as e:
            logger.warning(f"解析提取结果失败，回退为 create: {e}")
            return {
                "action": "create",
                "subject": stm.subject or "未知",
                "topic": stm.topic or stm.content[:50],
                "object": stm.object,
                "memory_type": stm.memory_type or "fact",
                "importance": stm.importance,
                "attributes": stm.attributes or {},
            }

    async def _upsert_long_term_memory(
        self, extraction: dict[str, Any], source_stm: ShortTermMemory
    ) -> str | None:
        """
        创建或更新长期记忆（直接 CRUD，不再使用图操作语言）

        Args:
            extraction: LLM 提取的结构化字段
            source_stm: 源短期记忆

        Returns:
            创建/更新的记忆 ID，失败返回 None
        """
        action = extraction.get("action", "create")
        target_id = extraction.get("target_memory_id")

        try:
            if action in ("update", "merge") and target_id:
                # 更新已有记忆
                success = await self.memory_manager.update_memory(
                    target_id,
                    importance=extraction.get("importance"),
                    metadata={
                        "updated_from_stm": source_stm.id,
                        "update_time": datetime.now().isoformat(),
                        "updated_topic": extraction.get("topic"),
                        "updated_object": extraction.get("object"),
                    },
                )
                if success:
                    logger.info(
                        f"{action} 长期记忆: {target_id} (来自短期记忆 {source_stm.id})"
                    )
                    return target_id
                else:
                    logger.warning(f"{action} 失败，目标记忆不存在: {target_id}，回退为 create")
                    # 回退为创建
                    action = "create"
                    extraction["action"] = "create"

            if action == "create" or (action in ("update", "merge") and not target_id):
                # 创建新记忆
                memory = await self.memory_manager.create_memory(
                    subject=extraction.get("subject", source_stm.subject or "未知"),
                    memory_type=extraction.get("memory_type", source_stm.memory_type or "fact"),
                    topic=extraction.get("topic", source_stm.topic or source_stm.content[:50]),
                    obj=extraction.get("object", source_stm.object),
                    attributes=extraction.get("attributes", source_stm.attributes),
                    importance=extraction.get("importance", source_stm.importance),
                )
                if memory:
                    memory.metadata["transferred_from_stm"] = source_stm.id
                    memory.metadata["transfer_time"] = datetime.now().isoformat()
                    logger.info(
                        f"创建长期记忆: {memory.id} (来自短期记忆 {source_stm.id})"
                    )
                    return memory.id

            return None

        except Exception as e:
            logger.error(f"_upsert_long_term_memory 失败: {e}")
            return None


    def _in_embedding_cooldown(self) -> bool:
        """检查是否在 embedding 冷却期内"""
        return self._embedding_cooldown_until is not None and datetime.now().timestamp() < self._embedding_cooldown_until

    def _enter_embedding_cooldown(self) -> None:
        """进入 embedding 冷却期"""
        self._embedding_cooldown_until = datetime.now().timestamp() + self._embedding_cooldown_seconds

    async def _queue_embedding_generation(self, node_id: str, content: str) -> None:
        """将节点加入embedding生成队列"""
        # 先在锁内写入，再在锁外触发批量处理，避免自锁
        should_flush = False
        async with self._embedding_lock:
            self._pending_embeddings.append((node_id, content))
            if len(self._pending_embeddings) >= self._embedding_batch_size:
                should_flush = True

        if should_flush:
            await self._flush_pending_embeddings()

    async def _flush_pending_embeddings(self) -> None:
        """批量处理待生成的embeddings"""
        async with self._embedding_lock:
            if not self._pending_embeddings:
                return

            batch = self._pending_embeddings[:]
            self._pending_embeddings.clear()

        # 检查是否在冷却期
        if self._in_embedding_cooldown():
            cooldown_left = self._embedding_cooldown_until - datetime.now().timestamp()
            logger.debug(f"embedding 冷却中，跳过 {len(batch)} 个节点 (剩余 {cooldown_left:.1f}s)")
            return


        if not self.memory_manager.vector_store or not self.memory_manager.embedding_generator:
            return

        try:
            # 批量生成embeddings
            contents = [content for _, content in batch]
            embeddings = await self.memory_manager.embedding_generator.generate_batch(contents)

            if not embeddings or len(embeddings) != len(batch):
                logger.warning("批量生成embedding失败或数量不匹配")
                # 回退到单个生成
                for node_id, content in batch:
                    await self._generate_node_embedding_single(node_id, content)
                return

            # 批量添加到向量库
            from src.memory_graph.models import MemoryNode, NodeType
            nodes = [
                MemoryNode(
                    id=node_id,
                    content=content,
                    node_type=NodeType.OBJECT,
                    embedding=embedding
                )
                for (node_id, content), embedding in zip(batch, embeddings)
                if embedding is not None
            ]

            if nodes:
                # 批量添加节点
                await self.memory_manager.vector_store.add_nodes_batch(nodes)

                # 批量更新图存储
                for node in nodes:
                    node.mark_vector_stored()
                    if self.memory_manager.graph_store.graph.has_node(node.id):
                        self.memory_manager.graph_store.graph.nodes[node.id]["has_vector"] = True

                logger.debug(f"批量生成 {len(nodes)} 个节点的embedding")

        except Exception as e:
            logger.error(f"批量生成embedding失败: {e}")
            # 回退到单个生成
            for node_id, content in batch:
                await self._generate_node_embedding_single(node_id, content)

    async def _generate_node_embedding_single(self, node_id: str, content: str) -> None:
        """为单个节点生成 embedding 并存入向量库（带回退 + 重试）"""
        try:
            if not self.memory_manager.vector_store or not self.memory_manager.embedding_generator:
                return

            # 跳过已知失败节点
            if node_id in self._failed_embedding_nodes:
                logger.debug(f"跳过已知失败的embedding节点: {node_id}")
                return

            for attempt in range(1, self._embedding_single_retry_limit + 1):
                try:
                    embedding = await self.memory_manager.embedding_generator.generate(content)
                    if embedding is not None:
                        from src.memory_graph.models import MemoryNode, NodeType
                        node = MemoryNode(
                            id=node_id,
                            content=content,
                            node_type=NodeType.OBJECT,
                            embedding=embedding
                        )
                        await self.memory_manager.vector_store.add_node(node)
                        node.mark_vector_stored()
                        if self.memory_manager.graph_store.graph.has_node(node_id):
                            self.memory_manager.graph_store.graph.nodes[node_id]["has_vector"] = True
                        self._embedding_consecutive_failures = 0
                        self._embedding_cooldown_until = None
                        return
                    else:
                        logger.debug(f"节点 {node_id} embedding 生成返回 None")
                        self._failed_embedding_nodes.add(node_id)
                        self._embedding_failed_count += 1
                        return
                except Exception as e:
                    self._embedding_consecutive_failures += 1
                    if attempt < self._embedding_single_retry_limit:
                        backoff = 0.5 * attempt
                        logger.warning(
                            f"生成节点 {node_id} embedding 失败，重试 {attempt}/{self._embedding_single_retry_limit}，等待 {backoff}s: {e}"
                        )
                        await asyncio.sleep(backoff)
                    else:
                        logger.error(f"生成节点 {node_id} embedding 最终失败: {e}")
                        self._failed_embedding_nodes.add(node_id)
                        self._embedding_failed_count += 1
                        if self._embedding_consecutive_failures >= self._embedding_failure_threshold:
                            self._enter_embedding_cooldown()
                            logger.warning(
                                f"embedding生成连续失败 {self._embedding_consecutive_failures} 次，进入 {self._embedding_cooldown_seconds}s 冷却期"
                            )
        except Exception as e:
            logger.warning(f"生成节点 embedding 失败: {e}")

    async def apply_long_term_decay(self) -> dict[str, Any]:
        """
        应用长期记忆的激活度衰减（优化版）

        长期记忆的衰减比短期记忆慢，使用更高的衰减因子。

        Returns:
            衰减结果统计
        """
        if not self._initialized:
            await self.initialize()

        try:
            logger.info("开始应用长期记忆激活度衰减...")

            all_memories = self.memory_manager.graph_store.get_all_memories()
            decayed_count = 0
            now = datetime.now()

            # 预计算衰减因子的幂次方（缓存常用值）
            decay_cache = {i: self.long_term_decay_factor ** i for i in range(1, 31)}  # 缓存1-30天

            memories_to_update = []

            for memory in all_memories:
                # 跳过已遗忘的记忆
                if memory.metadata.get("forgotten", False):
                    continue

                # 计算衰减
                activation_info = memory.metadata.get("activation", {})
                last_access = activation_info.get("last_access")

                if last_access:
                    try:
                        last_access_dt = datetime.fromisoformat(last_access)
                        days_passed = (now - last_access_dt).days

                        if days_passed > 0:
                            # 使用缓存的衰减因子或计算新值
                            decay_factor = decay_cache.get(
                                days_passed,
                                self.long_term_decay_factor ** days_passed
                            )

                            base_activation = activation_info.get("level", memory.activation)
                            new_activation = base_activation * decay_factor

                            # 更新激活度
                            memory.activation = new_activation
                            activation_info["level"] = new_activation
                            memory.metadata["activation"] = activation_info

                            memories_to_update.append(memory)
                            decayed_count += 1

                    except (ValueError, TypeError) as e:
                        logger.warning(f"解析时间失败: {e}")

            # 批量保存更新（如果有变化）
            if memories_to_update:
                await self.memory_manager.persistence.save_graph_store(
                    self.memory_manager.graph_store
                )

            logger.info(f"长期记忆衰减完成: {decayed_count} 条记忆已更新")
            return {"decayed_count": decayed_count, "total_memories": len(all_memories)}

        except Exception as e:
            logger.error(f"应用长期记忆衰减失败: {e}")
            return {"error": str(e), "decayed_count": 0}

    def get_statistics(self) -> dict[str, Any]:
        """获取长期记忆层统计信息"""
        if not self._initialized or not self.memory_manager.graph_store:
            return {}

        stats = self.memory_manager.get_statistics()
        stats["decay_factor"] = self.long_term_decay_factor
        stats["batch_size"] = self.batch_size
        stats["failed_embedding_nodes"] = len(self._failed_embedding_nodes)
        stats["embedding_consecutive_failures"] = self._embedding_consecutive_failures
        stats["embedding_cooldown_until"] = self._embedding_cooldown_until

        return stats

    async def shutdown(self) -> None:
        """关闭管理器"""
        if not self._initialized:
            return

        try:
            logger.info("正在关闭长期记忆管理器...")

            # 清空待处理的embedding队列
            await self._flush_pending_embeddings()

            # 清空缓存
            # 记录 embedding 失败统计
            if self._failed_embedding_nodes or self._embedding_failed_count:
                logger.warning(
                    f"embedding 失败统计: 失败节点数={len(self._failed_embedding_nodes)}, 累计失败={self._embedding_failed_count}"
                )
            self._similar_memory_cache.clear()

            # 长期记忆的保存由 MemoryManager 负责

            self._initialized = False
            logger.info("长期记忆管理器已关闭")

        except Exception as e:
            logger.error(f"关闭长期记忆管理器失败: {e}")


# 全局单例
_long_term_manager_instance: LongTermMemoryManager | None = None


def get_long_term_manager() -> LongTermMemoryManager:
    """获取长期记忆管理器单例（需要先初始化记忆图系统）"""
    global _long_term_manager_instance
    if _long_term_manager_instance is None:
        from src.memory_graph.manager_singleton import get_memory_manager

        memory_manager = get_memory_manager()
        if memory_manager is None:
            raise RuntimeError("记忆图系统未初始化，无法创建长期记忆管理器")
        _long_term_manager_instance = LongTermMemoryManager(memory_manager)
    return _long_term_manager_instance
