"""
长期记忆层管理器 (Long-term Memory Manager)

负责管理长期记忆图：
- 短期记忆到长期记忆的转移
- 图操作语言的执行
- 激活度衰减优化（长期记忆衰减更慢）
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any

import json_repair

from src.common.logger import get_logger
from src.memory_graph.manager import MemoryManager
from src.memory_graph.models import GraphOperation, GraphOperationType, Memory, ShortTermMemory

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
        self._embedding_retry_limit = 3  # 每个节点最大重试次数
        self._embedding_failed_count = 0  # 失败计数

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

            # 类型断言：确保关键组件已初始化
            assert self.memory_manager.graph_store is not None, "GraphStore未初始化"
            assert self.memory_manager.persistence is not None, "Persistence未初始化"

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

                logger.debug(
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
        处理一批短期记忆（并行处理，带并发控制）

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

        # 从配置获取最大并发LLM调用数
        max_concurrent = getattr(self.memory_manager.config, "max_concurrent_llm_calls", 3)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _process_with_limit(stm: ShortTermMemory) -> tuple[ShortTermMemory, dict[str, Any] | None]:
            """带信号量限制的单记忆处理"""
            async with semaphore:
                single_result = await self._process_single_memory(stm)
                return stm, single_result

        # 并行处理批次中的所有记忆（但受信号量限制）
        tasks = [_process_with_limit(stm) for stm in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 汇总结果
        for item in results:
            if isinstance(item, Exception):
                logger.error(f"处理批次记忆失败: {item}")
                result["failed_count"] += 1
                continue

            if not isinstance(item, tuple) or len(item) != 2:
                logger.error(f"意外的结果格式: {item}")
                result["failed_count"] += 1
                continue

            stm, single_result = item

            if not single_result:
                result["failed_count"] += 1
                continue

            result["processed_count"] += 1
            result["transferred_memory_ids"].append(stm.id)

            # 统计操作类型
            operations = single_result.get("operations", [])
            if isinstance(operations, list):
                for op_type in operations:
                    if op_type == GraphOperationType.CREATE_MEMORY:
                        result["created_count"] += 1
                    elif op_type == GraphOperationType.UPDATE_MEMORY:
                        result["updated_count"] += 1
                    elif op_type == GraphOperationType.MERGE_MEMORIES:
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
        处理单条短期记忆

        Args:
            stm: 短期记忆

        Returns:
            处理结果或None（如果失败）
        """
        # 增加重试机制以应对 LLM/执行的临时失败
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self._max_process_retries:
            try:
                # 步骤1: 在长期记忆中检索相似记忆
                similar_memories = await self._search_similar_long_term_memories(stm)

                # 步骤2: LLM 决策如何更新图结构
                operations = await self._decide_graph_operations(stm, similar_memories)

                # 步骤3: 执行图操作
                success = await self._execute_graph_operations(operations, stm)

                if success:
                    return {
                        "success": True,
                        "operations": [op.operation_type for op in operations]
                    }

                # 如果执行返回 False，视为一次失败，准备重试
                last_exc = RuntimeError("_execute_graph_operations 返回 False")
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
                # 超过重试次数，记录失败并返回 None
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
            use_path_expansion = False
            expand_depth = 0
            if global_config and global_config.memory:
                use_path_expansion = getattr(global_config.memory, "enable_path_expansion", False)
                expand_depth = getattr(global_config.memory, "path_expansion_max_hops", 2) if use_path_expansion else 0

            # 1. 检索记忆
            memories = await self.memory_manager.search_memories(
                query=stm.content,
                top_k=self.search_top_k,
                include_forgotten=False,
                use_multi_query=False,  # 不使用多查询，避免过度扩展
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

    async def _decide_graph_operations(
        self, stm: ShortTermMemory, similar_memories: list[Memory]
    ) -> list[GraphOperation]:
        """
        使用 LLM 决策如何更新图结构

        Args:
            stm: 短期记忆
            similar_memories: 相似的长期记忆列表

        Returns:
            图操作指令列表
        """
        try:
            from src.config.config import model_config
            from src.llm_models.utils_model import LLMRequest

            # 构建提示词
            prompt = self._build_graph_operation_prompt(stm, similar_memories)

            # 调用长期记忆构建模型
            assert model_config.model_task_config is not None, "ModelTaskConfig未初始化"
            llm = LLMRequest(
                model_set=model_config.model_task_config.memory_long_term_builder,
                request_type="long_term_memory.graph_operations",
            )

            response, _ = await llm.generate_response_async(
                prompt,
                temperature=self.llm_temperature,
                max_tokens=2000,
            )

            # 解析图操作指令
            operations = self._parse_graph_operations(response)

            logger.debug(f"LLM 生成 {len(operations)} 个图操作指令")
            return operations

        except Exception as e:
            logger.error(f"LLM 决策图操作失败: {e}")
            # 默认创建新记忆
            return [
                GraphOperation(
                    operation_type=GraphOperationType.CREATE_MEMORY,
                    parameters={
                        "subject": stm.subject or "未知",
                        "topic": stm.topic or stm.content[:50],
                        "object": stm.object,
                        "memory_type": stm.memory_type or "fact",
                        "importance": stm.importance,
                        "attributes": stm.attributes,
                    },
                    reason=f"LLM 决策失败，默认创建新记忆: {e}",
                    confidence=0.5,
                )
            ]

    def _build_graph_operation_prompt(
        self, stm: ShortTermMemory, similar_memories: list[Memory]
    ) -> str:
        """构建图操作的 LLM 提示词"""

        # 格式化短期记忆
        stm_desc = f"""
**待转移的短期记忆：**
- 内容: {stm.content}
- 主体: {stm.subject or '未指定'}
- 主题: {stm.topic or '未指定'}
- 客体: {stm.object or '未指定'}
- 类型: {stm.memory_type or '未指定'}
- 重要性: {stm.importance:.2f}
- 属性: {json.dumps(stm.attributes, ensure_ascii=False)}
"""

        # 格式化相似的长期记忆
        similar_desc = ""
        if similar_memories:
            similar_lines = []
            for i, mem in enumerate(similar_memories):
                mem.get_subject_node()
                mem_text = mem.to_text()
                similar_lines.append(
                    f"{i + 1}. [ID: {mem.id}] {mem_text}\n"
                    f"   - 重要性: {mem.importance:.2f}\n"
                    f"   - 激活度: {mem.activation:.2f}\n"
                    f"   - 节点数: {len(mem.nodes)}"
                )
            similar_desc = "\n\n".join(similar_lines)
        else:
            similar_desc = "（未找到相似记忆）"

        prompt = f"""你是一个记忆图结构管理专家。现在需要将一条短期记忆转移到长期记忆图中。

{stm_desc}

**候选的相似长期记忆：**
{similar_desc}

**图操作语言说明：**

你可以使用以下操作指令来精确控制记忆图的更新：

1. **CREATE_MEMORY** - 创建新记忆
   参数: subject, topic, object, memory_type, importance, attributes
   *注意：target_id 请使用临时ID（如 "TEMP_MEM_1"），后续操作可引用此ID*

2. **UPDATE_MEMORY** - 更新现有记忆
   参数: memory_id, updated_fields (包含要更新的字段)

3. **MERGE_MEMORIES** - 合并多个记忆
   参数: source_memory_ids (要合并的记忆ID列表), merged_content, merged_importance

4. **CREATE_NODE** - 创建新节点
   参数: content, node_type, memory_id (所属记忆ID)
   *注意：target_id 请使用临时ID（如 "TEMP_NODE_1"），后续操作可引用此ID*

5. **UPDATE_NODE** - 更新节点
   参数: node_id, updated_content

6. **MERGE_NODES** - 合并节点
   参数: source_node_ids, merged_content

7. **CREATE_EDGE** - 创建边
   参数: source_node_id, target_node_id, relation, edge_type, importance

8. **UPDATE_EDGE** - 更新边
   参数: edge_id, updated_relation, updated_importance

9. **DELETE_EDGE** - 删除边
   参数: edge_id

**ID 引用规则（非常重要）：**
1. 对于**新创建**的对象（记忆、节点），请在 `target_id` 字段指定一个唯一的临时ID（例如 "TEMP_MEM_1", "TEMP_NODE_1"）。
2. 在后续的操作中（如 `CREATE_NODE` 需要 `memory_id`，或 `CREATE_EDGE` 需要 `source_node_id`），请直接使用这些临时ID。
3. 系统会自动将临时ID解析为真实的UUID。
4. **严禁**使用中文描述作为ID（如"新创建的记忆ID"），必须使用英文临时ID。

**任务要求：**
1. 分析短期记忆与候选长期记忆的关系
2. 决定最佳的图更新策略：
   - 如果没有相似记忆或差异较大 → CREATE_MEMORY
   - 如果有高度相似记忆 → UPDATE_MEMORY 或 MERGE_MEMORIES
   - 如果需要补充信息 → CREATE_NODE + CREATE_EDGE
3. 生成具体的图操作指令列表
4. 确保操作的逻辑性和连贯性

**输出格式（JSON数组）：**
```json
[
  {{
    "operation_type": "CREATE_MEMORY",
    "target_id": "TEMP_MEM_1",
    "parameters": {{
      "subject": "...",
      ...
    }},
    "reason": "创建新记忆",
    "confidence": 0.9
  }},
  {{
    "operation_type": "CREATE_NODE",
    "target_id": "TEMP_NODE_1",
    "parameters": {{
      "content": "...",
      "memory_id": "TEMP_MEM_1"
    }},
    "reason": "为新记忆添加节点",
    "confidence": 0.9
  }}
]
```

请输出JSON数组："""

        return prompt

    def _parse_graph_operations(self, response: str) -> list[GraphOperation]:
        """解析 LLM 生成的图操作指令"""
        try:
            # 优先提取带 json 标注的代码块
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 兼容未标注语言的三引号代码块
                any_block = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
                if any_block:
                    json_str = any_block.group(1)
                else:
                    # 直接使用原文
                    json_str = response.strip()

            # 移除可能的注释
            json_str = re.sub(r"//.*", "", json_str)
            json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)

            data: list[dict] | dict
            try:
                data = json.loads(json_str)
            except Exception:
                # 回退：尝试使用 json_repair 修复
                try:
                    repair_result = json_repair.loads(json_str)
                    # json_repair.loads 可能返回多种类型，需要验证
                    if isinstance(repair_result, (list, dict)):
                        data = repair_result  # type: ignore
                    else:
                        raise TypeError(f"json_repair返回了非预期类型: {type(repair_result)}")
                except Exception:
                    # 再回退：截取首个 JSON 片段 [] 或 {}
                    start_arr, end_arr = json_str.find("["), json_str.rfind("]")
                    start_obj, end_obj = json_str.find("{"), json_str.rfind("}")
                    segment = None
                    if start_arr != -1 and end_arr != -1 and end_arr > start_obj:
                        segment = json_str[start_arr : end_arr + 1]
                    elif start_obj != -1 and end_obj != -1 and end_obj > start_obj:
                        segment = json_str[start_obj : end_obj + 1]
                    if segment is None:
                        raise
                    repair_result = json_repair.loads(segment)
                    if isinstance(repair_result, (list, dict)):
                        data = repair_result  # type: ignore
                    else:
                        raise TypeError(f"json_repair返回了非预期类型: {type(repair_result)}")

            # 统一为列表
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                logger.warning("图操作解析结果非列表，返回空列表")
                return []

            operations: list[GraphOperation] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                op_type_raw = item.get("operation_type", "CREATE_MEMORY")
                try:
                    op = GraphOperation(
                        operation_type=GraphOperationType(op_type_raw),
                        target_id=item.get("target_id"),
                        parameters=item.get("parameters", {}),
                        reason=item.get("reason", ""),
                        confidence=item.get("confidence", 1.0),
                    )
                    operations.append(op)
                except Exception as e:
                    logger.warning(f"解析图操作失败: {e}, 项目: {item}")
                    continue

            return operations

        except Exception as e:
            logger.error(f"图操作解析异常: {e}, 响应: {response[:200]}")
            return []

    async def _execute_graph_operations(
        self, operations: list[GraphOperation], source_stm: ShortTermMemory
    ) -> bool:
        """
        执行图操作指令

        Args:
            operations: 图操作指令列表
            source_stm: 源短期记忆

        Returns:
            是否执行成功
        """
        if not operations:
            logger.warning("没有图操作指令，跳过执行")
            return False

        try:
            success_count = 0
            temp_id_map: dict[str, str] = {}
            active_memory_id: str | None = None

            for op in operations:
                try:
                    if op.operation_type == GraphOperationType.CREATE_MEMORY:
                        await self._execute_create_memory(op, source_stm, temp_id_map)
                        active_memory_id = self._resolve_id(op.target_id, temp_id_map)
                        success_count += 1

                    elif op.operation_type == GraphOperationType.UPDATE_MEMORY:
                        await self._execute_update_memory(op, temp_id_map)
                        active_memory_id = self._resolve_id(op.target_id, temp_id_map)
                        success_count += 1

                    elif op.operation_type == GraphOperationType.MERGE_MEMORIES:
                        await self._execute_merge_memories(op, source_stm, temp_id_map)
                        # 获取合并后的目标记忆ID
                        params = self._resolve_parameters(op.parameters, temp_id_map)
                        source_ids = params.get("source_memory_ids", [])
                        if source_ids:
                            active_memory_id = source_ids[0]
                        success_count += 1

                    elif op.operation_type == GraphOperationType.CREATE_NODE:
                        await self._execute_create_node(op, temp_id_map)
                        # 更新当前上下文记忆ID
                        params = self._resolve_parameters(op.parameters, temp_id_map)
                        if params.get("memory_id"):
                            active_memory_id = params.get("memory_id")
                        success_count += 1

                    elif op.operation_type == GraphOperationType.UPDATE_NODE:
                        await self._execute_update_node(op, temp_id_map)
                        success_count += 1

                    elif op.operation_type == GraphOperationType.MERGE_NODES:
                        await self._execute_merge_nodes(op, temp_id_map)
                        success_count += 1

                    elif op.operation_type == GraphOperationType.CREATE_EDGE:
                        await self._execute_create_edge(
                            op, temp_id_map, default_memory_id=active_memory_id
                        )
                        success_count += 1

                    elif op.operation_type == GraphOperationType.UPDATE_EDGE:
                        await self._execute_update_edge(op, temp_id_map)
                        success_count += 1

                    elif op.operation_type == GraphOperationType.DELETE_EDGE:
                        await self._execute_delete_edge(op, temp_id_map)
                        success_count += 1

                    else:
                        logger.warning(f"未实现的操作类型: {op.operation_type}")

                except Exception as e:
                    logger.error(f"执行图操作失败: {op}, 错误: {e}")

            logger.debug(f"执行了 {success_count}/{len(operations)} 个图操作")
            return success_count > 0

        except Exception as e:
            logger.error(f"执行图操作失败: {e}")
            return False

    @staticmethod
    def _is_placeholder_id(candidate: str | None) -> bool:
        if not candidate or not isinstance(candidate, str):
            return False
        lowered = candidate.strip().lower()
        return lowered.startswith(("new_", "temp_"))

    def _register_temp_id(
        self,
        placeholder: str | None,
        actual_id: str,
        temp_id_map: dict[str, str],
        force: bool = False,
    ) -> None:
        if not actual_id or not placeholder or not isinstance(placeholder, str):
            return
        if placeholder == actual_id:
            return
        if force or self._is_placeholder_id(placeholder):
            temp_id_map[placeholder] = actual_id

    def _resolve_id(self, raw_id: str | None, temp_id_map: dict[str, str]) -> str | None:
        if raw_id is None:
            return None
        return temp_id_map.get(raw_id, raw_id)

    def _resolve_value(self, value: Any, temp_id_map: dict[str, str]) -> Any:
        """优化的值解析，减少递归和类型检查"""
        value_type = type(value)

        if value_type is str:
            return temp_id_map.get(value, value)
        elif value_type is list:
            return [temp_id_map.get(v, v) if isinstance(v, str) else v for v in value]
        elif value_type is dict:
            return {k: temp_id_map.get(v, v) if isinstance(v, str) else v
                    for k, v in value.items()}
        return value

    def _resolve_parameters(
        self, params: dict[str, Any], temp_id_map: dict[str, str]
    ) -> dict[str, Any]:
        """优化的参数解析"""
        if not temp_id_map:
            return params
        return {k: self._resolve_value(v, temp_id_map) for k, v in params.items()}

    def _register_aliases_from_params(
        self,
        params: dict[str, Any],
        actual_id: str,
        temp_id_map: dict[str, str],
        *,
        extra_keywords: tuple[str, ...] = (),
        force: bool = False,
    ) -> None:
        alias_keywords = ("alias", "placeholder", "temp_id", "register_as", *tuple(extra_keywords))
        for key, value in params.items():
            if isinstance(value, str):
                lower_key = key.lower()
                if any(keyword in lower_key for keyword in alias_keywords):
                    self._register_temp_id(value, actual_id, temp_id_map, force=force)
            elif isinstance(value, list):
                lower_key = key.lower()
                if any(keyword in lower_key for keyword in alias_keywords):
                    for item in value:
                        if isinstance(item, str):
                            self._register_temp_id(item, actual_id, temp_id_map, force=force)
            elif isinstance(value, dict):
                self._register_aliases_from_params(
                    value,
                    actual_id,
                    temp_id_map,
                    extra_keywords=extra_keywords,
                    force=force,
                )

    async def _execute_create_memory(
        self,
        op: GraphOperation,
        source_stm: ShortTermMemory,
        temp_id_map: dict[str, str],
    ) -> None:
        """执行创建记忆操作"""
        params = self._resolve_parameters(op.parameters, temp_id_map)

        memory = await self.memory_manager.create_memory(
            subject=params.get("subject", source_stm.subject or "未知"),
            memory_type=params.get("memory_type", source_stm.memory_type or "fact"),
            topic=params.get("topic", source_stm.topic or source_stm.content[:50]),
            obj=params.get("object", source_stm.object),
            attributes=params.get("attributes", source_stm.attributes),
            importance=params.get("importance", source_stm.importance),
        )

        if memory:
            # 标记为从短期记忆转移而来
            memory.metadata["transferred_from_stm"] = source_stm.id
            memory.metadata["transfer_time"] = datetime.now().isoformat()

            logger.debug(f"创建长期记忆: {memory.id} (来自短期记忆 {source_stm.id})")
            # 强制注册 target_id，无论它是否符合 placeholder 格式
            # 这样即使 LLM 使用了中文描述作为 ID (如 "新创建的记忆"), 也能正确映射
            self._register_temp_id(op.target_id, memory.id, temp_id_map, force=True)
            self._register_aliases_from_params(
                op.parameters,
                memory.id,
                temp_id_map,
                extra_keywords=("memory_id", "memory_alias", "memory_placeholder"),
                force=True,
            )
        else:
            logger.error(f"创建长期记忆失败: {op}")

    async def _execute_update_memory(
        self, op: GraphOperation, temp_id_map: dict[str, str]
    ) -> None:
        """执行更新记忆操作"""
        memory_id = self._resolve_id(op.target_id, temp_id_map)
        if not memory_id:
            logger.error("更新操作缺少目标记忆ID")
            return

        updates_raw = op.parameters.get("updated_fields", {})
        updates = (
            self._resolve_parameters(updates_raw, temp_id_map)
            if isinstance(updates_raw, dict)
            else updates_raw
        )

        success = await self.memory_manager.update_memory(memory_id, **updates)

        if success:
            logger.debug(f"更新长期记忆: {memory_id}")
        else:
            logger.error(f"更新长期记忆失败: {memory_id}")

    async def _execute_merge_memories(
        self,
        op: GraphOperation,
        source_stm: ShortTermMemory,
        temp_id_map: dict[str, str],
    ) -> None:
        """执行合并记忆操作 (智能合并版)"""
        params = self._resolve_parameters(op.parameters, temp_id_map)
        source_ids = params.get("source_memory_ids", [])
        merged_content = params.get("merged_content", "")
        merged_importance = params.get("merged_importance", source_stm.importance)

        if not source_ids:
            logger.warning("合并操作缺少源记忆ID，跳过")
            return

        # 目标记忆（保留的那个）
        target_id = source_ids[0]

        # 待合并记忆（将被删除的）
        memories_to_merge = source_ids[1:]

        if not memories_to_merge:
            logger.debug(f"合并操作未指定源记忆，跳过实际合并: target={target_id}")
            # 即使没有要合并的记忆，也可能需要更新元数据（例如 merged_content）
            # 所以继续执行，但 merge_memories 调用会是空的
        else:
            logger.debug(f"开始智能合并记忆: {memories_to_merge} -> {target_id}")

        # 1. 调用 GraphStore 的合并功能（转移节点和边）
        # 使用 to_thread 防止同步操作阻塞事件循环
        merge_success = await asyncio.to_thread(
            self.memory_manager.graph_store.merge_memories,
            target_id,
            memories_to_merge
        )

        if merge_success:
            # 2. 更新目标记忆的元数据
            await self.memory_manager.update_memory(
                target_id,
                metadata={
                    "merged_content": merged_content,
                    "merged_from": memories_to_merge,
                    "merged_from_stm": source_stm.id,
                    "merge_time": datetime.now().isoformat()
                },
                importance=merged_importance,
            )

            # 3. 异步保存（后台任务，不需要等待）
            asyncio.create_task(  # noqa: RUF006
                self.memory_manager._async_save_graph_store("合并记忆")
            )

            # 4. 注册临时ID（如果存在），以便后续操作引用
            self._register_temp_id(op.target_id, target_id, temp_id_map, force=True)

            logger.debug(f"合并记忆完成: {source_ids} -> {target_id}")
        else:
            logger.error(f"合并记忆失败: {source_ids}")

    async def _execute_create_node(
        self, op: GraphOperation, temp_id_map: dict[str, str]
    ) -> None:
        """执行创建节点操作"""
        params = self._resolve_parameters(op.parameters, temp_id_map)
        content = params.get("content")
        node_type = params.get("node_type", "OBJECT")
        memory_id = params.get("memory_id")

        if not content or not memory_id:
            logger.warning(f"创建节点失败: 缺少必要参数 (content={content}, memory_id={memory_id})")
            return

        import uuid
        node_id = str(uuid.uuid4())

        success = self.memory_manager.graph_store.add_node(
            node_id=node_id,
            content=content,
            node_type=node_type,
            memory_id=memory_id,
            metadata={"created_by": "long_term_manager"}
        )

        if success:
            # 将embedding生成加入队列，批量处理
            await self._queue_embedding_generation(node_id, content)
            logger.debug(f"创建节点: {content} ({node_type}) -> {memory_id}")
            # 强制注册 target_id，无论它是否符合 placeholder 格式
            self._register_temp_id(op.target_id, node_id, temp_id_map, force=True)
            self._register_aliases_from_params(
                op.parameters,
                node_id,
                temp_id_map,
                extra_keywords=("node_id", "node_alias", "node_placeholder"),
                force=True,
            )
        else:
            logger.error(f"创建节点失败: {op}")

    async def _execute_update_node(
        self, op: GraphOperation, temp_id_map: dict[str, str]
    ) -> None:
        """执行更新节点操作"""
        node_id = self._resolve_id(op.target_id, temp_id_map)
        params = self._resolve_parameters(op.parameters, temp_id_map)
        updated_content = params.get("updated_content")

        if not node_id:
            logger.warning("更新节点失败: 缺少 node_id")
            return

        success = self.memory_manager.graph_store.update_node(
            node_id=node_id,
            content=updated_content
        )

        if success:
            logger.debug(f"更新节点: {node_id}")
        else:
            logger.error(f"更新节点失败: {node_id}")

    async def _execute_merge_nodes(
        self, op: GraphOperation, temp_id_map: dict[str, str]
    ) -> None:
        """执行合并节点操作"""
        params = self._resolve_parameters(op.parameters, temp_id_map)
        source_node_ids = params.get("source_node_ids", [])
        merged_content = params.get("merged_content")

        if not source_node_ids or len(source_node_ids) < 2:
            logger.warning("合并节点失败: 需要至少两个节点")
            return

        target_id = source_node_ids[0]
        sources = source_node_ids[1:]

        # 更新目标节点内容
        if merged_content:
            self.memory_manager.graph_store.update_node(target_id, content=merged_content)

        # 合并其他节点到目标节点
        for source_id in sources:
            self.memory_manager.graph_store.merge_nodes(source_id, target_id)

        logger.debug(f"合并节点: {sources} -> {target_id}")

    async def _execute_create_edge(
        self,
        op: GraphOperation,
        temp_id_map: dict[str, str],
        default_memory_id: str | None = None,
    ) -> None:
        """执行创建边操作"""
        params = self._resolve_parameters(op.parameters, temp_id_map)
        source_id = params.get("source_node_id")
        target_id = params.get("target_node_id")
        relation = params.get("relation", "related")
        edge_type = params.get("edge_type", "RELATION")
        importance = params.get("importance", 0.5)

        if not source_id or not target_id:
            logger.warning(f"创建边失败: 缺少节点ID ({source_id} -> {target_id})")
            return

        if not self.memory_manager.graph_store:
            logger.warning("创建边失败: 图存储未初始化")
            return

        # 辅助函数：推断 memory_id
        def _infer_memory_id(existing_node_id: str) -> str | None:
            memories = self.memory_manager.graph_store.get_memories_by_node(existing_node_id)
            if memories:
                return memories[0].id
            return None

        # 检查和创建节点（如果不存在则创建占位符）
        if not self.memory_manager.graph_store.graph.has_node(source_id):
            # 尝试推断 memory_id
            memory_id = default_memory_id
            if not memory_id and self.memory_manager.graph_store.graph.has_node(target_id):
                memory_id = _infer_memory_id(target_id)

            if not memory_id:
                logger.warning(f"源节点不存在且无法推断 memory_id，跳过创建: {source_id}")
                return

            logger.debug(f"源节点不存在，创建占位符节点: {source_id} (memory_id={memory_id})")
            self.memory_manager.graph_store.add_node(
                node_id=source_id,
                node_type="event",
                content=f"临时节点 - {source_id}",
                memory_id=memory_id,
                metadata={
                    "placeholder": True,
                    "created_by": "long_term_manager_edge_creation",
                },
            )

        if not self.memory_manager.graph_store.graph.has_node(target_id):
            # 尝试推断 memory_id
            memory_id = default_memory_id
            if not memory_id and self.memory_manager.graph_store.graph.has_node(source_id):
                memory_id = _infer_memory_id(source_id)

            if not memory_id:
                logger.warning(f"目标节点不存在且无法推断 memory_id，跳过创建: {target_id}")
                return

            logger.debug(f"目标节点不存在，创建占位符节点: {target_id} (memory_id={memory_id})")
            self.memory_manager.graph_store.add_node(
                node_id=target_id,
                node_type="event",
                content=f"临时节点 - {target_id}",
                memory_id=memory_id,
                metadata={
                    "placeholder": True,
                    "created_by": "long_term_manager_edge_creation",
                },
            )

        # 现在两个节点都存在，可以创建边
        edge_id = self.memory_manager.graph_store.add_edge(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            edge_type=edge_type,
            importance=importance,
            metadata={"created_by": "long_term_manager"}
        )

        if edge_id:
            logger.debug(f"创建边: {source_id} -> {target_id} ({relation})")
        else:
            logger.error(f"创建边失败: {op}")

    async def _execute_update_edge(
        self, op: GraphOperation, temp_id_map: dict[str, str]
    ) -> None:
        """执行更新边操作"""
        edge_id = self._resolve_id(op.target_id, temp_id_map)
        params = self._resolve_parameters(op.parameters, temp_id_map)
        updated_relation = params.get("updated_relation")
        updated_importance = params.get("updated_importance")

        if not edge_id:
            logger.warning("更新边失败: 缺少 edge_id")
            return

        success = self.memory_manager.graph_store.update_edge(
            edge_id=edge_id,
            relation=updated_relation,
            importance=updated_importance
        )

        if success:
            logger.debug(f"更新边: {edge_id}")
        else:
            logger.error(f"更新边失败: {edge_id}")

    async def _execute_delete_edge(
        self, op: GraphOperation, temp_id_map: dict[str, str]
    ) -> None:
        """执行删除边操作"""
        edge_id = self._resolve_id(op.target_id, temp_id_map)

        if not edge_id:
            logger.warning("删除边失败: 缺少 edge_id")
            return

        success = self.memory_manager.graph_store.remove_edge(edge_id)

        if success:
            logger.debug(f"删除边: {edge_id}")
        else:
            logger.error(f"删除边失败: {edge_id}")

    async def _queue_embedding_generation(self, node_id: str, content: str) -> None:
        """将节点加入embedding生成队列"""
        # 检查是否已经失败过多次
        if node_id in self._failed_embedding_nodes:
            logger.debug(f"节点 {node_id} 已标记为失败，跳过embedding生成")
            return

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

        if not self.memory_manager.vector_store or not self.memory_manager.embedding_generator:
            return

        try:
            # 批量生成embeddings
            contents = [content for _, content in batch]
            embeddings = await self.memory_manager.embedding_generator.generate_batch(contents)

            if not embeddings or len(embeddings) != len(batch):
                logger.warning(
                    f"批量生成embedding失败或数量不匹配 (期望{len(batch)}, 实际{len(embeddings) if embeddings else 0})"
                )
                self._embedding_failed_count += len(batch)
                # 将失败的节点标记，避免无限重试
                for node_id, _ in batch:
                    self._failed_embedding_nodes.add(node_id)
                logger.info(f"已将 {len(batch)} 个节点标记为embedding失败，不再重试")
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
            logger.error(f"批量生成embedding异常: {e}")
            self._embedding_failed_count += len(batch)
            # 将失败的节点标记，避免无限重试
            for node_id, _ in batch:
                self._failed_embedding_nodes.add(node_id)
            logger.info(f"已将 {len(batch)} 个节点标记为embedding失败，不再重试")

    async def _generate_node_embedding_single(self, node_id: str, content: str) -> None:
        """为单个节点生成 embedding 并存入向量库（回退方法）
        
        注意：此方法不应再将失败的节点重新加入队列，避免无限循环
        """
        try:
            if not self.memory_manager.vector_store or not self.memory_manager.embedding_generator:
                return

            # 检查是否已标记为失败
            if node_id in self._failed_embedding_nodes:
                logger.debug(f"节点 {node_id} 已标记为失败，跳过单个生成")
                return

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
                logger.debug(f"单个生成节点 {node_id} 的embedding成功")
            else:
                # embedding为None，标记为失败
                self._failed_embedding_nodes.add(node_id)
                self._embedding_failed_count += 1
                logger.warning(f"节点 {node_id} embedding生成返回None，已标记为失败")
        except Exception as e:
            # 异常时标记为失败，避免重复尝试
            self._failed_embedding_nodes.add(node_id)
            self._embedding_failed_count += 1
            logger.warning(f"生成节点 {node_id} embedding失败: {e}，已标记为失败")

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

            logger.debug(f"长期记忆衰减完成: {decayed_count} 条记忆已更新")
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
        stats["embedding_stats"] = {
            "failed_count": self._embedding_failed_count,
            "failed_nodes": len(self._failed_embedding_nodes),
            "pending_count": len(self._pending_embeddings),
        }

        return stats

    async def shutdown(self) -> None:
        """关闭管理器"""
        if not self._initialized:
            return

        try:
            logger.info("正在关闭长期记忆管理器...")

            # 输出embedding统计信息
            if self._embedding_failed_count > 0:
                logger.warning(
                    f"Embedding生成统计: 失败次数={self._embedding_failed_count}, "
                    f"失败节点数={len(self._failed_embedding_nodes)}, "
                    f"待处理数={len(self._pending_embeddings)}"
                )

            # 清空待处理的embedding队列
            await self._flush_pending_embeddings()

            # 清空缓存
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
