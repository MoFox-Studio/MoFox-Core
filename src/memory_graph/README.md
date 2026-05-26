# MoFox 记忆系统

> 三层分级记忆架构，模拟人类记忆特性，高效可扩展。

---

## 系统架构

```
用户交互 (Chat Input)
       |
       v
第1层：感知记忆 (Perceptual Memory) — 即时对话流 (50块)
 |— 消息分块存储（每块5条消息）
 |— 实时激活与 TopK 召回
 |— 相似度阈值触发转移
 |— 低开销，高频率访问
       | 激活转移
       v
第2层：短期记忆 (Short-term Memory) — 结构化信息 (30条)
 |— LLM 驱动的决策（创建/合并/更新/丢弃）
 |— 重要性评分（0.0-1.0）
 |— 按重要性阈值渐进转移到长期层
 |— 平衡灵活性与容量
       | 按阈值转移
       v
第3层：长期记忆 (Long-term Memory) — 知识图谱
 |— NetworkX 图数据库存储（人物、事件、关系）
 |— ChromaDB 向量检索与相似度匹配
 |— 动态节点合并与边缘生成
 |— LLM 结构化提取 + 直接 CRUD
```

### 数据流

```
消息 → [感知层] 分块 + 向量化
         ↓ 召回 ≥ 激活阈值
       [短期层] LLM 结构化提取 → 决策 (create/update/merge)
         ↓ importance ≥ transfer_threshold
       [长期层] LLM 提取字段 → create_memory() / update_memory() → MemoryBuilder 自动构建子图
```

---

## 快速开始

### 配置

```toml
[memory]
enable = true
data_dir = "data/memory_graph"

# 感知记忆层
perceptual_max_blocks = 50
perceptual_block_size = 5
perceptual_activation_threshold = 3
perceptual_topk = 5
perceptual_similarity_threshold = 0.55

# 短期记忆层
short_term_max_memories = 30
short_term_transfer_threshold = 0.6       # 转移到长期的重要性阈值
short_term_overflow_strategy = "transfer_all"

# 长期记忆层
long_term_batch_size = 10
long_term_decay_factor = 0.95
long_term_auto_transfer_interval = 600    # 自动转移间隔（秒）

# 智能检索
judge_confidence_threshold = 0.7
search_top_k = 10
search_similarity_threshold = 0.5
```

### 初始化

```python
from src.memory_graph.manager_singleton import initialize_unified_memory_manager, get_unified_memory_manager

# 初始化（自动读取 global_config.memory）
mgr = await initialize_unified_memory_manager()

# 或使用便捷方法（自动初始化）
mgr = await ensure_unified_memory_manager_initialized()

# 获取已初始化的实例
mgr = get_unified_memory_manager()
```

### 基本使用

```python
# 添加消息到感知层
await mgr.add_message({
    "role": "user",
    "content": "我喜欢喝咖啡",
    "timestamp": "2026-05-26T10:00:00",
    "stream_id": "chat_123",
})

# 检索记忆（自动跨三层 + 裁判模型评估）
result = await mgr.search_memories(
    query_text="用户喜欢喝什么？",
    use_judge=True,
)
# result["perceptual_blocks"]  — 感知记忆块
# result["short_term_memories"] — 短期结构化记忆
# result["long_term_memories"]  — 长期图谱记忆
# result["judge_decision"]      — 裁判决策

# 手动触发短期→长期转移
result = await mgr.manual_transfer()

# 查看统计
stats = mgr.get_statistics()
```

---

## 核心模块

| 模块 | 功能 | 文件 |
|---|---|---|
| 统一入口 | 整合三层，自动转移循环，智能检索 | `unified_manager.py` |
| 感知层 | 消息分块、向量召回、FIFO 淘汰 | `perceptual_manager.py` |
| 短期层 | LLM 决策、合并、转移 | `short_term_manager.py` |
| 长期层 | 结构化提取、直接 CRUD、衰减 | `long_term_manager.py` |
| 图存储 | NetworkX 有向图，节点/边索引 | `storage/graph_store.py` |
| 向量存储 | ChromaDB 持久化语义检索 | `storage/vector_store.py` |
| 持久化 | orjson 原子写入，Windows 文件锁 | `storage/persistence.py` |
| 记忆构建 | 自动构造子图，节点去重合并 | `core/builder.py` |
| 节点合并 | 相似节点自动检测与合并 | `core/node_merger.py` |
| 配置 | 统一参数管理 | `models.py` (MemoryConfig) |
| 单例 | 全局实例访问 | `manager_singleton.py` |

---

## 转移策略

**自动转移**：定时循环（默认每 600 秒），筛选 `importance >= short_term_transfer_threshold` 的短期记忆，分批转移到长期记忆。

**手动转移**：`manual_transfer()` 始终可用，不检查短期层是否满额。

**长期层存储**：LLM 从短期记忆中提取结构化字段 `{action, subject, topic, object, type, importance}`，直接调用 `create_memory()` / `update_memory()`，由 `MemoryBuilder` 自动构建图谱子图，`NodeMerger` 自动合并相似节点。

---

## 配置模式

```python
from src.memory_graph.models import MemoryConfig

# 从全局配置构建
cfg = MemoryConfig.from_global_config()

# 或手动构建
cfg = MemoryConfig(
    perceptual_max_blocks=30,
    short_term_transfer_threshold=0.7,
    long_term_auto_transfer_interval=300,
)

# 传递给管理器
mgr = UnifiedMemoryManager(config=cfg)
```

---

## 最佳实践

### 容量配置

```toml
# 低频场景（私聊）
perceptual_max_blocks = 20
short_term_max_memories = 15

# 中频场景（小群）
perceptual_max_blocks = 50
short_term_max_memories = 30

# 高频场景（大群/客服）
perceptual_max_blocks = 100
short_term_max_memories = 50
```

### 转移策略选择

- 提高 `short_term_transfer_threshold`：只转移高价值记忆，减少长期层膨胀
- 降低 `long_term_auto_transfer_interval`：更快清理短期层，适合高频场景
- 增大 `long_term_batch_size`：减少 LLM 调用次数

### 监控

```python
stats = mgr.get_statistics()
# stats["perceptual"]["total_messages"]  — 感知层消息数
# stats["short_term"]["total_memories"]  — 短期记忆数
# stats["long_term"]["total_memories"]   — 长期记忆数
# stats["total_system_memories"]         — 总计

occupancy = stats["short_term"]["total_memories"] / stats["short_term"]["max_memories"]
if occupancy > 0.8:
    logger.warning("短期记忆压力高，考虑扩容或调整转移阈值")
```

---

## 故障排查

### 短期记忆不转移
- 检查 `short_term_transfer_threshold` 是否过高
- 所有记忆 `importance < threshold` 则不会转移
- 手动调用 `manual_transfer()` 验证

### 长期记忆检索不相关
- 增大 `search_top_k`
- 降低 `search_similarity_threshold`
- 检查 ChromaDB 向量模型是否正确加载

### 数据丢失
- 关键操作（创建/删除）现在使用同步保存
- `shutdown()` 有 10 秒超时保护确保最终写入
- 检查 `data/memory_graph/memory_graph.json` 文件完整性

---

## 版本信息

- **架构**：三层分级记忆系统
- **存储**：NetworkX 图谱 + ChromaDB 向量库
- **持久化**：orjson 原子写入
- **重构**：2026-05-26（v1.0 — 统一配置、精简长期层、修复转移策略）

---

## 相关文档

- [重构设计文档](docs/REFACTOR_PLAN.md)
- [开发者指南](docs/DEVELOPER_GUIDE.md)
- [统一记忆管理器](docs/unified_memory_manager.md)
- [故障排查手册](docs/memory_graph/TROUBLESHOOTING.md)
- [工具调用指南](docs/memory_graph/tool_calling_guide.md)
