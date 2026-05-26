"""
统一记忆管理器 (Unified Memory Manager)

整合三层记忆系统：
- 感知记忆层
- 短期记忆层
- 长期记忆层

提供统一的接口供外部调用
"""

import asyncio
from pathlib import Path
from typing import Any

from src.common.logger import get_logger
from src.memory_graph.long_term_manager import LongTermMemoryManager
from src.memory_graph.manager import MemoryManager
from src.memory_graph.models import JudgeDecision, MemoryBlock, MemoryConfig, ShortTermMemory
from src.memory_graph.perceptual_manager import PerceptualMemoryManager
from src.memory_graph.short_term_manager import ShortTermMemoryManager

logger = get_logger(__name__)


class UnifiedMemoryManager:
    """
    统一记忆管理器

    整合三层记忆系统，提供统一接口
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        memory_manager: MemoryManager | None = None,
        config: MemoryConfig | None = None,
        # 感知记忆配置
        perceptual_max_blocks: int = 50,
        perceptual_block_size: int = 5,
        perceptual_activation_threshold: int = 3,
        perceptual_recall_top_k: int = 5,
        perceptual_recall_threshold: float = 0.55,
        # 短期记忆配置
        short_term_max_memories: int = 30,
        short_term_transfer_threshold: float = 0.6,
        short_term_overflow_strategy: str = "transfer_all",
        short_term_enable_force_cleanup: bool = False,
        short_term_cleanup_keep_ratio: float = 0.9,
        # 长期记忆配置
        long_term_batch_size: int = 10,
        long_term_search_top_k: int = 5,
        long_term_decay_factor: float = 0.95,
        long_term_auto_transfer_interval: int = 600,
        # 智能检索配置
        judge_confidence_threshold: float = 0.7,
    ):
        """
        初始化统一记忆管理器

        Args:
            data_dir: 数据存储目录
            perceptual_max_blocks: 感知记忆堆最大容量
            perceptual_block_size: 每个记忆块的消息数量
            perceptual_activation_threshold: 激活阈值（召回次数）
            perceptual_recall_top_k: 召回时返回的最大块数
            perceptual_recall_threshold: 召回的相似度阈值
            short_term_max_memories: 短期记忆最大数量
            short_term_transfer_threshold: 转移到长期记忆的重要性阈值
            long_term_batch_size: 批量处理的短期记忆数量
            long_term_search_top_k: 检索相似记忆的数量
            long_term_decay_factor: 长期记忆的衰减因子
            long_term_auto_transfer_interval: 自动转移间隔（秒）
            judge_confidence_threshold: 裁判模型的置信度阈值
        """
        self.data_dir = data_dir or Path("data/memory_graph")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 统一配置对象（优先使用传入的 config）
        if config is not None:
            self.config = config
        else:
            self.config = MemoryConfig(
                data_dir=str(self.data_dir),
                perceptual_max_blocks=perceptual_max_blocks,
                perceptual_block_size=perceptual_block_size,
                perceptual_activation_threshold=perceptual_activation_threshold,
                perceptual_recall_top_k=perceptual_recall_top_k,
                perceptual_recall_threshold=perceptual_recall_threshold,
                short_term_max_memories=short_term_max_memories,
                short_term_transfer_threshold=short_term_transfer_threshold,
                short_term_overflow_strategy=short_term_overflow_strategy,
                short_term_enable_force_cleanup=short_term_enable_force_cleanup,
                short_term_cleanup_keep_ratio=short_term_cleanup_keep_ratio,
                long_term_batch_size=long_term_batch_size,
                long_term_search_top_k=long_term_search_top_k,
                long_term_decay_factor=long_term_decay_factor,
                long_term_auto_transfer_interval=long_term_auto_transfer_interval,
                judge_confidence_threshold=judge_confidence_threshold,
            )

        # 配置参数（向后兼容）
        self.judge_confidence_threshold = self.config.judge_confidence_threshold

        # 三层管理器
        self.perceptual_manager: PerceptualMemoryManager
        self.short_term_manager: ShortTermMemoryManager
        self.long_term_manager: LongTermMemoryManager

        # 底层 MemoryManager（长期记忆）
        self.memory_manager: MemoryManager = memory_manager

        # 配置参数存储（用于初始化）
        self._config = {
            "perceptual": self.config.to_perceptual_kwargs(),
            "short_term": self.config.to_short_term_kwargs(),
            "long_term": self.config.to_long_term_kwargs(),
        }

        # 状态
        self._initialized = False
        self._auto_transfer_task: asyncio.Task | None = None
        self._auto_transfer_interval = max(10.0, float(self.config.long_term_auto_transfer_interval))
        self._transfer_wakeup_event: asyncio.Event | None = None

        logger.info("统一记忆管理器已创建")

    async def initialize(self) -> None:
        """初始化统一记忆管理器"""
        if self._initialized:
            logger.warning("统一记忆管理器已经初始化")
            return

        try:
            logger.debug("开始初始化统一记忆管理器...")

            # 初始化底层 MemoryManager（长期记忆）
            if self.memory_manager is None:
                # 如果未提供外部 MemoryManager，则创建一个新的
                # 假设 data_dir 是 three_tier 子目录，则 MemoryManager 使用父目录
                # 如果 data_dir 是根目录，则 MemoryManager 使用该目录
                self.memory_manager = MemoryManager(data_dir=self.data_dir)
                await self.memory_manager.initialize()
            else:
                logger.debug("使用外部提供的 MemoryManager")
                # 确保外部 MemoryManager 已初始化
                if not getattr(self.memory_manager, "_initialized", False):
                    await self.memory_manager.initialize()

            # 初始化感知记忆层
            self.perceptual_manager = PerceptualMemoryManager(
                data_dir=self.data_dir,
                **self._config["perceptual"],
            )
            await self.perceptual_manager.initialize()

            # 初始化短期记忆层
            self.short_term_manager = ShortTermMemoryManager(
                data_dir=self.data_dir,
                **self._config["short_term"],
            )
            await self.short_term_manager.initialize()

            # 初始化长期记忆层
            self.long_term_manager = LongTermMemoryManager(
                memory_manager=self.memory_manager,
                **self._config["long_term"],
            )
            await self.long_term_manager.initialize()

            self._initialized = True
            logger.info("统一记忆管理器初始化完成")

            # 启动自动转移任务
            self._start_auto_transfer_task()

        except Exception as e:
            logger.error(f"统一记忆管理器初始化失败: {e}")
            raise

    async def add_message(self, message: dict[str, Any]) -> MemoryBlock | None:
        """
        添加消息到感知记忆层

        Args:
            message: 消息字典

        Returns:
            如果创建了新块，返回 MemoryBlock
        """
        if not self._initialized:
            await self.initialize()

        new_block = await self.perceptual_manager.add_message(message)

        # 注意：感知→短期的转移由召回触发，不是由添加消息触发
        # 转移逻辑在 search_memories 中处理

        return new_block

    # 已移除 _process_activated_blocks 方法
    # 转移逻辑现在在 search_memories 中处理：
    # 当召回某个记忆块时，如果其 recall_count >= activation_threshold，
    # 立即将该块转移到短期记忆

    async def search_memories(
        self, query_text: str, use_judge: bool = True, recent_chat_history: str = ""
    ) -> dict[str, Any]:
        """
        智能检索记忆

        流程：
        1. 优先检索感知记忆和短期记忆
        2. 使用裁判模型评估是否充足
        3. 如果不充足，生成补充 query 并检索长期记忆

        Args:
            query_text: 查询文本
            use_judge: 是否使用裁判模型
            recent_chat_history: 最近的聊天历史上下文（可选）

        Returns:
            检索结果字典，包含：
            - perceptual_blocks: 感知记忆块列表
            - short_term_memories: 短期记忆列表
            - long_term_memories: 长期记忆列表
            - judge_decision: 裁判决策（如果使用）
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = {
                "perceptual_blocks": [],
                "short_term_memories": [],
                "long_term_memories": [],
                "judge_decision": None,
            }

            # 步骤1: 并行检索感知记忆和短期记忆（优化：消除任务创建开销）
            perceptual_blocks, short_term_memories = await asyncio.gather(
                self.perceptual_manager.recall_blocks(query_text),
                self.short_term_manager.search_memories(query_text),
            )

            # 步骤1.5: 检查需要转移的感知块，推迟到后台处理（优化：单遍扫描与转移）
            blocks_to_transfer = []
            for block in perceptual_blocks:
                if block.metadata.get("needs_transfer", False):
                    block.metadata["needs_transfer"] = False  # 立即标记，避免重复
                    blocks_to_transfer.append(block)

            if blocks_to_transfer:
                logger.debug(
                    f"检测到 {len(blocks_to_transfer)} 个感知记忆需要转移，已交由后台后处理任务执行"
                )
                self._schedule_perceptual_block_transfer(blocks_to_transfer)

            result["perceptual_blocks"] = perceptual_blocks
            result["short_term_memories"] = short_term_memories

            # 步骤2: 裁判模型评估
            if use_judge:
                judge_decision = await self._judge_retrieval_sufficiency(
                    query_text, perceptual_blocks, short_term_memories, recent_chat_history
                )
                result["judge_decision"] = judge_decision

                # 步骤3: 如果不充足，检索长期记忆
                if not judge_decision.is_sufficient:
                    logger.info("判官判断记忆不足，开始检索长期记忆")

                    queries = [query_text, *judge_decision.additional_queries]
                    long_term_memories = await self._retrieve_long_term_memories(
                        base_query=query_text,
                        queries=queries,
                        recent_chat_history=recent_chat_history,
                    )

                    result["long_term_memories"] = long_term_memories

            else:
                # 不使用裁判，直接检索长期记忆
                long_term_memories = await self.memory_manager.search_memories(
                    query=query_text,
                    top_k=5,
                    use_multi_query=False,
                )
                result["long_term_memories"] = long_term_memories

            return result

        except Exception as e:
            logger.error(f"智能检索失败: {e}")
            return {
                "perceptual_blocks": [],
                "short_term_memories": [],
                "long_term_memories": [],
                "error": str(e),
            }

    async def _judge_retrieval_sufficiency(
        self,
        query: str,
        perceptual_blocks: list[MemoryBlock],
        short_term_memories: list[ShortTermMemory],
        recent_chat_history: str = "",
    ) -> JudgeDecision:
        """
        使用裁判模型评估检索结果是否充足

        Args:
            query: 原始查询
            perceptual_blocks: 感知记忆块
            short_term_memories: 短期记忆
            recent_chat_history: 最近的聊天历史上下文（可选）

        Returns:
            裁判决策
        """
        try:
            from src.config.config import model_config
            from src.llm_models.utils_model import LLMRequest
            from src.memory_graph.utils.three_tier_formatter import memory_formatter

            # 使用新的三级记忆格式化器
            perceptual_desc = await memory_formatter.format_perceptual_memory(perceptual_blocks)
            short_term_desc = memory_formatter.format_short_term_memory(short_term_memories)

            # 构建聊天历史块（如果提供）
            chat_history_block = ""
            if recent_chat_history:
                chat_history_block = f"""**最近的聊天历史：**
{recent_chat_history}

"""

            prompt = f"""你是“记忆判官”（记忆检索评估专家）。你的任务是：基于给定的历史消息、当前消息，以及我们已经检索到的“感知记忆”和“短期记忆”，判断是否还需要检索“长期记忆”（LTM）来支撑一次准确、完整、上下文一致的回复。

**总体偏好（重要）：**
- 我们宁可多花一点资源去检索长期记忆，也不要在本该检索时漏检索。
- 因此：只要存在明显不确定、信息缺口、或需要更精确细节的情况，就倾向于判定“现有记忆不充足”（`is_sufficient: false`）。

**输入：**
**当前用户消息：**
{query}

{chat_history_block}**已检索到的感知记忆（即时对话，格式：【时间 (聊天流)】消息列表）：**
{perceptual_desc or '（无）'}

**已检索到的短期记忆（结构化信息，自然语言描述）：**
{short_term_desc or '（无）'}

**什么时候必须检索长期记忆（满足任一条 → `is_sufficient: false`）：**
1. **用户明确要求回忆/找回过去信息**：例如“你还记得…？”“上次我们说到…？”“帮我回忆一下…/之前…/那天…/某次…”
2. **你对答案没有把握或存在不确定性**：例如无法确定人物/事件/时间/地点/偏好/承诺/任务细节，或只能给出模糊猜测。
3. **现有记忆不足以给出精确回答**：要给出具体结论、细节、步骤、承诺、时间线、决定依据，但感知/短期记忆缺少关键事实。
4. **对话依赖用户个体历史**：涉及用户的个人信息、偏好、长期目标、过往经历、已约定事项、持续进行的项目/任务，需要更早的上下文才能回答。
5. **指代不清或背景缺失**：出现“那个/那件事/他/她/它/之前说的/你知道的”等省略指代，现有记忆不足以唯一指向。
6. **记忆冲突或碎片化**：感知/短期记忆之间存在矛盾、时间线断裂、或信息片段无法拼成完整图景。

**什么时候可以不检索（同时满足全部条件 → `is_sufficient: true`）：**
- 用户只是闲聊/打招呼/情绪表达/泛化问题（不依赖用户个人历史），且现有记忆已足以给出可靠且一致的回复；
- 你能在不猜测的情况下回答，且不需要更早的细节来保证准确性。

**输出要求（JSON）：**
- `is_sufficient`: `true` 表示“无需检索长期记忆”；`false` 表示“需要检索长期记忆”
- `confidence`: 0~1，表示你对该判断的把握；若你偏向检索但仍不确定，也应输出较低/中等置信度并保持 `is_sufficient: false`
- `missing_aspects`: 列出阻碍精确回答的缺失点（可为空数组）
- `additional_queries`: 给出 1~5 条用于检索长期记忆的补充 query（尽量短、可检索、包含关键实体/事件/时间线线索；可为空数组）

请仅输出 JSON（可以用 ```json 包裹，也可以直接输出纯 JSON）："""

            # 调用记忆裁判模型
            if not model_config.model_task_config:
                raise ValueError("模型任务配置未加载")
            llm = LLMRequest(
                model_set=model_config.model_task_config.memory_judge,
                request_type="unified_memory.judge",
            )

            response, _ = await llm.generate_response_async(
                prompt,
                temperature=0.1,
                max_tokens=600,
            )

            # 解析响应
            import json
            import re

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()

            data = json.loads(json_str)

            decision = JudgeDecision(
                is_sufficient=data.get("is_sufficient", False),
                confidence=data.get("confidence", 0.5),
                reasoning=data.get("reasoning", ""),
                additional_queries=data.get("additional_queries", []),
                missing_aspects=data.get("missing_aspects", []),
            )

            return decision

        except Exception as e:
            logger.error(f"裁判模型评估失败: {e}")
            # 默认判定为不充足，需要检索长期记忆
            return JudgeDecision(
                is_sufficient=False,
                confidence=0.3,
                reasoning=f"裁判模型失败: {e}",
                additional_queries=[query],
            )

    def _schedule_perceptual_block_transfer(self, blocks: list[MemoryBlock]) -> None:
        """将感知记忆块转移到短期记忆，后台执行以避免阻塞（优化：避免不必要的列表复制）"""
        if not blocks:
            return

        # 优化：直接传递 blocks 而不再 list(blocks)
        task = asyncio.create_task(
            self._transfer_blocks_to_short_term(blocks)
        )
        self._attach_background_task_callback(task, "perceptual->short-term transfer")

    def _attach_background_task_callback(self, task: asyncio.Task, task_name: str) -> None:
        """确保后台任务异常被记录"""

        def _callback(done_task: asyncio.Task) -> None:
            try:
                done_task.result()
            except asyncio.CancelledError:
                logger.info(f"{task_name} 后台任务已取消")
            except Exception as exc:
                logger.error(f"{task_name} 后台任务失败: {exc}")

        task.add_done_callback(_callback)

    def _trigger_transfer_wakeup(self) -> None:
        """通知自动转移任务立即检查缓存"""
        if self._transfer_wakeup_event and not self._transfer_wakeup_event.is_set():
            self._transfer_wakeup_event.set()

    async def _transfer_blocks_to_short_term(self, blocks: list[MemoryBlock]) -> None:
        """实际转换逻辑在后台执行（优化：并行处理多个块，批量触发唤醒）"""
        logger.debug(f"正在后台处理 {len(blocks)} 个感知记忆块")

        # 优化：使用 asyncio.gather 并行处理转移
        async def _transfer_single(block: MemoryBlock) -> tuple[MemoryBlock, bool]:
            try:
                stm = await self.short_term_manager.add_from_block(block)
                if not stm:
                    return block, False

                await self.perceptual_manager.remove_block(block.id)
                logger.debug(f"✓ 记忆块 {block.id} 已被转移到短期记忆 {stm.id}")
                return block, True
            except Exception as exc:
                logger.error(f"后台转移失败，记忆块 {block.id}: {exc}")
                return block, False

        # 并行处理所有块
        results = await asyncio.gather(*[_transfer_single(block) for block in blocks], return_exceptions=True)

        # 统计成功的转移
        success_count = sum(1 for result in results if isinstance(result, tuple) and result[1])
        if success_count > 0:
            self._trigger_transfer_wakeup()
            logger.debug(f"✅ 后台转移: 成功 {success_count}/{len(blocks)} 个块")

    def _build_manual_multi_queries(self, queries: list[str]) -> list[dict[str, float]]:
        """去重裁判查询并附加权重以进行多查询搜索（优化：使用字典推导式）"""
        # 优化：单遍去重（避免多次 strip 和 in 检查）
        seen = set()
        decay = 0.15
        manual_queries: list[dict[str, Any]] = []

        for raw in queries:
            text = (raw or "").strip()
            if text and text not in seen:
                seen.add(text)
                weight = max(0.3, 1.0 - len(manual_queries) * decay)
                manual_queries.append({"text": text, "weight": round(weight, 2)})

        # 过滤单条或空列表
        return manual_queries if len(manual_queries) > 1 else []

    async def _retrieve_long_term_memories(
        self,
        base_query: str,
        queries: list[str],
        recent_chat_history: str = "",
    ) -> list[Any]:
        """可一次性运行多查询搜索的集中式长期检索条目（优化：减少中间对象创建）"""
        manual_queries = self._build_manual_multi_queries(queries)

        # 优化：仅在必要时创建 context 字典
        search_params: dict[str, Any] = {
            "query": base_query,
            "top_k": self._config["long_term"]["search_top_k"],
            "use_multi_query": bool(manual_queries),
        }

        if recent_chat_history or manual_queries:
            context: dict[str, Any] = {}
            if recent_chat_history:
                context["chat_history"] = recent_chat_history
            if manual_queries:
                context["manual_multi_queries"] = manual_queries
            search_params["context"] = context

        memories = await self.memory_manager.search_memories(**search_params)
        return self._deduplicate_memories(memories)

    def _deduplicate_memories(self, memories: list[Any]) -> list[Any]:
        """通过 memory.id 去重（优化：支持 dict 和 object，单遍处理）"""
        seen_ids: set[str] = set()
        unique_memories: list[Any] = []

        for mem in memories:
            # 支持两种 ID 访问方式
            mem_id = None
            if isinstance(mem, dict):
                mem_id = mem.get("id")
            else:
                mem_id = getattr(mem, "id", None)

            # 检查去重
            if mem_id and mem_id in seen_ids:
                continue

            unique_memories.append(mem)
            if mem_id:
                seen_ids.add(mem_id)

        return unique_memories


    def _start_auto_transfer_task(self) -> None:
        """启动自动转移任务"""
        if self._auto_transfer_task and not self._auto_transfer_task.done():
            logger.warning("自动转移任务已在运行")
            return

        if self._transfer_wakeup_event is None:
            self._transfer_wakeup_event = asyncio.Event()
        else:
            self._transfer_wakeup_event.clear()

        self._auto_transfer_task = asyncio.create_task(self._auto_transfer_loop())
        # 立即触发一次检查，避免启动初期的长时间等待
        self._transfer_wakeup_event.set()
        logger.debug("自动转移任务已启动并触发首次检查")

    async def _auto_transfer_loop(self) -> None:
        """自动转移循环：按重要性阈值筛选，定时分批转移"""

        while True:
            try:
                sleep_interval = self._auto_transfer_interval
                if self._transfer_wakeup_event is not None:
                    try:
                        await asyncio.wait_for(
                            self._transfer_wakeup_event.wait(),
                            timeout=sleep_interval,
                        )
                        self._transfer_wakeup_event.clear()
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(sleep_interval)

                threshold = self.config.short_term_transfer_threshold
                candidates = [
                    m for m in self.short_term_manager.memories
                    if m.importance >= threshold
                ]
                if not candidates:
                    continue

                logger.info(
                    f"自动转移: {len(candidates)}/{len(self.short_term_manager.memories)} "
                    f"条短期记忆满足重要性阈值 ({threshold})"
                )

                # 分批转移
                batch_size = self.config.long_term_batch_size
                for i in range(0, len(candidates), batch_size):
                    batch = candidates[i : i + batch_size]
                    result = await self.long_term_manager.transfer_from_short_term(batch)
                    if result.get("transferred_memory_ids"):
                        await self.short_term_manager.clear_transferred_memories(
                            result["transferred_memory_ids"]
                        )
                    await asyncio.sleep(0.01)

                logger.debug(f"✅ 自动转移完成: 处理 {len(candidates)} 条候选")

            except asyncio.CancelledError:
                logger.debug("自动转移循环被取消")
                break
            except Exception as e:
                logger.error(f"自动转移循环异常: {e}")

    async def manual_transfer(self) -> dict[str, Any]:
        """
        手动触发短期记忆到长期记忆的转移

        按重要性阈值筛选候选记忆，始终允许手动触发。

        Returns:
            转移结果
        """
        if not self._initialized:
            await self.initialize()

        try:
            threshold = self.config.short_term_transfer_threshold
            candidates = [
                m for m in self.short_term_manager.memories
                if m.importance >= threshold
            ]
            if not candidates:
                return {
                    "message": f"没有满足重要性阈值 ({threshold}) 的记忆",
                    "transferred_count": 0,
                }

            result = await self.long_term_manager.transfer_from_short_term(candidates)

            if result.get("transferred_memory_ids"):
                await self.short_term_manager.clear_transferred_memories(
                    result["transferred_memory_ids"]
                )

            logger.info(f"手动转移完成: {result}")
            return result

        except Exception as e:
            logger.error(f"手动转移失败: {e}")
            return {"error": str(e), "transferred_count": 0}

    def get_statistics(self) -> dict[str, Any]:
        """获取三层记忆系统的统计信息"""
        if not self._initialized:
            return {}

        return {
            "perceptual": self.perceptual_manager.get_statistics(),
            "short_term": self.short_term_manager.get_statistics(),
            "long_term": self.long_term_manager.get_statistics(),
            "total_system_memories": (
                self.perceptual_manager.get_statistics().get("total_messages", 0)
                + self.short_term_manager.get_statistics().get("total_memories", 0)
                + self.long_term_manager.get_statistics().get("total_memories", 0)
            ),
        }

    async def shutdown(self) -> None:
        """关闭统一记忆管理器"""
        if not self._initialized:
            return

        try:
            logger.info("正在关闭统一记忆管理器...")

            # 取消自动转移任务
            if self._auto_transfer_task and not self._auto_transfer_task.done():
                self._auto_transfer_task.cancel()
                try:
                    await self._auto_transfer_task
                except asyncio.CancelledError:
                    pass

            # 确保最终保存（带超时保护）
            if self.memory_manager and self.memory_manager.persistence:
                try:
                    await asyncio.wait_for(
                        self.memory_manager._save_graph_store("shutdown"),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.error("最终保存超时（10s）")
                except Exception as save_err:
                    logger.error(f"最终保存失败: {save_err}")

            # 关闭各层管理器
            if self.perceptual_manager:
                await self.perceptual_manager.shutdown()

            if self.short_term_manager:
                await self.short_term_manager.shutdown()

            if self.long_term_manager:
                await self.long_term_manager.shutdown()

            if self.memory_manager:
                await self.memory_manager.shutdown()

            self._initialized = False
            logger.info("统一记忆管理器已关闭")

        except Exception as e:
            logger.error(f"关闭统一记忆管理器失败: {e}")
