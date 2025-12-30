# 🧠 MoFox 记忆系统

> ⚠️ **维护说明**: 本模块仅进行缺陷修复，重构前不再添加新功能或进行大规模改动。

MoFox-Core 采用**三层分级记忆架构**，模拟人类记忆的生物特性，实现了高效、可扩展的记忆管理系统。本文档介绍系统架构、使用方法和最佳实践。

---

## 📐 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户交互 (Chat Input)                         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  第1层：感知记忆 (Perceptual Memory) - 即时对话流 (50块)          │
│  ├─ 消息分块存储（每块5条消息）                                 │
│  ├─ 实时激活与召回                                             │
│  ├─ 相似度阈值触发转移                                         │
│  └─ 低开销，高频率访问                                         │
└─────────────────────────────────────────────────────────────────┘
                            ↓ 激活转移
┌─────────────────────────────────────────────────────────────────┐
│  第2层：短期记忆 (Short-term Memory) - 结构化信息 (30条)          │
│  ├─ LLM 驱动的决策（创建/合并/更新/丢弃）                      │
│  ├─ 重要性评分（0.0-1.0）                                       │
│  ├─ 自动转移与泄压机制                                         │
│  └─ 平衡灵活性与容量                                           │
└─────────────────────────────────────────────────────────────────┘
                            ↓ 批量转移
┌─────────────────────────────────────────────────────────────────┐
│  第3层：长期记忆 (Long-term Memory) - 知识图谱                    │
│  ├─ 图数据库存储（人物、事件、关系）                            │
│  ├─ 向量检索与相似度匹配                                       │
│  ├─ 动态节点合并与边生成                                       │
│  └─ 无容量限制，检索精确                                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                  LLM 回复生成（带完整上下文）                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 三层记忆详解

### 第1层：感知记忆 (Perceptual Memory)

**特点**：
- 📍 **位置**：即时对话窗口
- 💾 **容量**：50 块（250 条消息）
- ⏱️ **生命周期**：短暂，激活后可转移
- 🔍 **检索**：相似度匹配

**功能**：
```python
# 添加消息到感知记忆
await perceptual_manager.add_message(
    user_id="user123",
    message="最近在学习Python",
    timestamp=datetime.now()
)

# 召回相关块
blocks = await perceptual_manager.recall_blocks(
    query="你在学什么编程语言",
    top_k=3
)
```

**转移触发条件**：
- 块被多次激活（激活次数 ≥ 3）
- 块满足转移条件后提交到短期层

### 第2层：短期记忆 (Short-term Memory)

**特点**：
- 📍 **位置**：结构化数据存储
- 💾 **容量**：30 条记忆
- ⏱️ **生命周期**：中等，根据重要性动态转移
- 🧠 **处理**：LLM 驱动决策

**功能**：
```python
# LLM 提取结构化记忆
extracted = await short_term_manager.add_from_block(block)

# 检索类似记忆
similar = await short_term_manager.search_memories(
    query="Python 学习进度",
    top_k=5
)

# 查询可转移记忆（用于统计）
to_transfer = short_term_manager.get_memories_for_transfer()
```

**决策类型**：
| 决策 | 说明 | 场景 |
|------|------|------|
| `CREATE_NEW` | 创建新记忆 | 全新信息 |
| `MERGE` | 合并到现有 | 补充细节 |
| `UPDATE` | 更新现有 | 信息演变 |
| `DISCARD` | 丢弃 | 冗余/过时 |

**重要性评分**：
```
重要性评分用于转移后清理，不影响转移触发
高重要性 (≥0.6) → 在转移后保留
低重要性 (<0.6) → 在转移后清理以释放空间
```

**容量管理**：
- ✅ **自动转移**：容量满额 (100%) 时触发转移
- 🛡️ **溢出策略**：支持 `transfer_all`（默认，保留历史）或 `selective_cleanup`（快速释放）
- ⚙️ **配置**：`short_term_max_memories = 30`

**溢出策略配置**：

```toml
[memory]
# 短期记忆溢出策略
short_term_overflow_strategy = "transfer_all"  # 或 "selective_cleanup"
```

| 策略 | 转移行为 | 适用场景 |
|------|--------|---------|
| `transfer_all`（默认） | 转移全部 30 条 → 删除低重要性(≥0.6) | 记忆密集型，需要保留历史 |
| `selective_cleanup` | 仅转移高重要性 → 直接删除低重要性 | 性能优先，高频场景 |

**工作原理**：
```
短期记忆满额（100%）
    ↓
转移高重要性记忆到长期层
    ↓
根据策略处理低重要性记忆：
  - transfer_all: 也转移到长期，然后删除 ↓ 历史完整
  - selective_cleanup: 直接删除 ↓ 快速释放空间
    ↓
短期层恢复容量
```

### 第3层：长期记忆 (Long-term Memory)

**特点**：
- 📍 **位置**：图数据库（NetworkX + Chroma）
- 💾 **容量**：无限
- ⏱️ **生命周期**：持久，可检索
- 📊 **结构**：知识图谱

**功能**：
```python
# 转移短期记忆到长期图
result = await long_term_manager.transfer_from_short_term(
    short_term_memories
)

# 图检索
results = await memory_manager.search_memories(
    query="用户的编程经验",
    top_k=5
)
```

**知识图谱节点类型**：
- 👤 **PERSON**：人物、角色
- 📅 **EVENT**：发生过的事件
- 💡 **CONCEPT**：概念、想法
- 🎯 **GOAL**：目标、计划

**节点关系**：
- `participated_in`：参与了某事件
- `mentioned`：提及了某人/物
- `similar_to`：相似
- `related_to`：相关
- `caused_by`：由...导致

---

## 🔧 配置说明

### 基础配置

**文件**：`config/bot_config.toml`

```toml
[memory]
# 启用/禁用记忆系统
enable = true

# 数据存储
data_dir = "data/memory_graph"
vector_collection_name = "memory_nodes"
vector_db_path = "data/memory_graph/chroma_db"

# 感知记忆
perceptual_max_blocks = 50              # 最大块数
perceptual_block_size = 5               # 每块消息数
perceptual_similarity_threshold = 0.55  # 召回阈值
perceptual_activation_threshold = 3     # 转移激活阈值

# 短期记忆
short_term_max_memories = 30                    # 容量上限
short_term_transfer_threshold = 0.6             # 转移重要性阈值
short_term_overflow_strategy = "transfer_all"   # 溢出策略（transfer_all/selective_cleanup）

# 长期记忆
long_term_batch_size = 10                       # 批量转移大小
long_term_decay_factor = 0.95                   # 激活衰减因子
long_term_auto_transfer_interval = 180          # 转移检查间隔（秒）

# 检索配置
search_top_k = 10                      # 默认返回数量
search_min_importance = 0.3            # 最小重要性过滤
search_similarity_threshold = 0.6      # 相似度阈值
```

### 高级配置

```toml
[memory]
# 路径评分扩展（更精确的图检索）
enable_path_expansion = false                   # 启用算法
path_expansion_max_hops = 2                     # 最大跳数
path_expansion_damping_factor = 0.85            # 衰减因子
path_expansion_max_branches = 10                # 分支限制

# 记忆激活
activation_decay_rate = 0.9                     # 每天衰减10%
activation_propagation_strength = 0.5          # 传播强度
activation_propagation_depth = 1               # 传播深度

# 遗忘机制
forgetting_enabled = true                      # 启用遗忘
forgetting_activation_threshold = 0.1          # 遗忘激活度阈值
forgetting_min_importance = 0.8                # 保护重要性阈值
```

---

## 📚 使用示例

### 1. 初始化记忆系统

```python
from src.memory_graph.manager_singleton import (
    initialize_unified_memory_manager,
    get_unified_memory_manager
)

# 初始化系统
await initialize_unified_memory_manager()

# 获取管理器
manager = get_unified_memory_manager()
```

### 2. 添加感知记忆

```python
from src.memory_graph.models import MemoryBlock

# 模拟一个消息块
block = MemoryBlock(
    id="msg_001",
    content="用户提到在做一个Python爬虫项目",
    timestamp=datetime.now(),
    source="chat"
)

# 添加到感知层
await manager.add_memory(block, source="perceptual")
```

### 3. 智能检索记忆

```python
# 统一检索（从感知→短期→长期）
result = await manager.retrieve_memories(
    query="最近在做什么项目",
    use_judge=True  # 使用裁判模型评估是否需要检索长期
)

# 访问不同层的结果
perceptual = result["perceptual_blocks"]
short_term = result["short_term_memories"]
long_term = result["long_term_memories"]
```

### 4. 手动触发转移

```python
# 立即转移短期→长期
result = await manager.manual_transfer()

print(f"转移了 {result['transferred_memory_ids']} 条记忆到长期层")
```

### 5. 获取统计信息

```python
stats = manager.get_statistics()

print(f"感知记忆块数：{stats['perceptual']['total_blocks']}")
print(f"短期记忆数：{stats['short_term']['total_memories']}")
print(f"长期记忆节点数：{stats['long_term']['total_memories']}")
print(f"系统总记忆数：{stats['total_system_memories']}")
```

---

## 🔄 转移流程

### 自动转移循环

系统在后台持续运行自动转移循环，确保记忆及时流转：

```
每 N 秒（可配置）：
  1. 检查短期记忆容量
  2. 获取待转移的高重要性记忆
  3. 如果缓存满或容量高，触发转移
  4. 发送到长期管理器处理
  5. 从短期层清除已转移记忆
```

**自动转移触发条件**：
- 短期记忆容量达到 100% (满额)

**代码位置**：`src/memory_graph/unified_manager.py` 第 576-650 行

### 转移决策

长期记忆管理器对每条短期记忆做出决策：

```python
# LLM 决策过程
for short_term_memory in batch:
    # 1. 检索相似的长期记忆
    similar = await search_long_term(short_term_memory)
    
    # 2. LLM 做出决策
    decision = await llm_decide({
        'short_term': short_term_memory,
        'similar_long_term': similar
    })
    
    # 3. 执行决策
    if decision == 'CREATE_NEW':
        create_new_node()
    elif decision == 'MERGE':
        merge_into_existing()
    elif decision == 'UPDATE':
        update_existing()
```

---

##  性能特性

### 时间复杂度

| 操作 | 复杂度 | 说明 |
|------|--------|------|
| 感知记忆添加 | O(1) | 直接追加 |
| 感知记忆召回 | O(n) | 相似度匹配 |
| 短期记忆添加 | O(1) | 直接追加 |
| 短期记忆搜索 | O(n) | 向量相似度 |
| 长期记忆检索 | O(log n) | 向量数据库 + 图遍历 |
| 转移操作 | O(n) | 批量处理 |

### 空间复杂度

| 层级 | 估计空间 | 配置 |
|------|---------|------|
| 感知层 | ~5-10 MB | 50 块 × 5 消息 |
| 短期层 | ~1-2 MB | 30 条记忆 |
| 长期层 | ~50-200 MB | 根据对话历史 |

### 优化技巧

1. **缓存去重**：避免同一记忆被转移多次
2. **批量转移**：减少 LLM 调用次数
3. **异步操作**：后台转移，不阻塞主流程
4. **自适应轮询**：根据容量压力调整检查间隔

---

## 🔍 检索策略

### 三层联合检索

```python
result = await manager.retrieve_memories(query, use_judge=True)
```

**流程**：
1. 检索感知层（即时对话）
2. 检索短期层（结构化信息）
3. 使用裁判模型判断是否充足
4. 如不充足，检索长期层（知识图）

**裁判模型**：
- 评估现有记忆是否满足查询
- 生成补充查询词
- 决策是否需要长期检索

### 路径评分扩展（可选）

启用后使用 PageRank 风格算法在图中传播分数：

```toml
enable_path_expansion = true
path_expansion_max_hops = 2
path_expansion_damping_factor = 0.85
```

**优势**：
- 发现间接关联信息
- 上下文更丰富
- 精确度提高 15-25%

---

## 🐛 故障排查

> **详细故障排查步骤请参考 [故障排查手册](../docs/TROUBLESHOOTING.md)**

以下是常见问题的快速检查：

### 问题1：短期记忆快速堆积

**症状**：短期层记忆数快速增长，转移缓慢

**排查**：
```python
# 查看统计信息
stats = manager.get_statistics()
occupancy = stats['short_term']['total_memories'] / stats['short_term']['max_memories']
print(f"短期记忆占用率: {occupancy:.0%}")
print(f"待转移记忆: {len(manager.short_term_manager.get_memories_for_transfer())}")
```

**解决**：
- 减小 `long_term_auto_transfer_interval`（加快转移频率）
- 增加 `long_term_batch_size`（一次转移更多）
- 提高 `short_term_transfer_threshold`（更多记忆被转移）

### 问题2：长期记忆检索结果不相关

**症状**：搜索返回的记忆与查询不匹配

**排查**：
```python
# 启用调试日志
import logging
logging.getLogger("src.memory_graph").setLevel(logging.DEBUG)

# 重试检索
result = await manager.retrieve_memories(query, use_judge=True)
# 检查日志中的相似度评分
```

**解决**：
- 增加 `search_top_k`（返回更多候选）
- 降低 `search_similarity_threshold`（放宽相似度要求）
- 检查向量模型是否加载正确

### 问题3：转移失败导致记忆丢失

**症状**：短期记忆无故消失，长期层未出现

**排查**：
```python
# 检查日志中的转移错误
# 查看长期管理器的错误日志
```

**解决**：
- 检查 LLM 模型配置
- 确保长期图存储正常运行
- 增加转移超时时间

---

## 🎓 最佳实践

### 1. 合理配置容量

```toml
# 低频场景（私聊）
perceptual_max_blocks = 20
short_term_max_memories = 15

# 中等频率（小群）
perceptual_max_blocks = 50
short_term_max_memories = 30

# 高频场景（大群/客服）
perceptual_max_blocks = 100
short_term_max_memories = 50
short_term_overflow_strategy = "selective_cleanup"  # 快速释放空间
```

### 2. 根据场景选择溢出策略

```python
# 在定时任务中检查
async def monitor_memory():
    stats = manager.get_statistics()
    occupancy = stats['short_term']['total_memories'] / stats['short_term']['max_memories']
    if occupancy > 0.8:
        logger.warning("短期记忆压力高，考虑扩容或调整溢出策略")
    if stats['long_term'].get('total_memories', 0) > 10000:
        logger.warning("长期图规模大，检索可能变慢")
```

### 3. 使用裁判模型

```python
# 启用以提高检索质量
result = await manager.retrieve_memories(
    query=user_query,
    use_judge=True  # 自动判断是否需要长期检索
)
```

---

## 📖 相关文档

- [三层记忆系统用户指南](../../docs/three_tier_memory_user_guide.md)
- [记忆图谱架构](../../docs/memory_graph_guide.md)
- [短期记忆压力泄压补丁](../../docs/short_term_pressure_patch.md)
- [统一调度器指南](../../docs/unified_scheduler_guide.md)
- [故障排查手册](../docs/TROUBLESHOOTING.md)

---

## 🎯 快速导航

### 核心模块

| 模块 | 功能 | 文件 |
|------|------|------|
| 感知管理 | 消息分块、激活、转移 | `perceptual_manager.py` |
| 短期管理 | LLM 决策、合并、转移 | `short_term_manager.py` |
| 长期管理 | 图操作、节点合并 | `long_term_manager.py` |
| 统一接口 | 自动转移循环、检索 | `unified_manager.py` |
| 单例访问 | 全局管理器获取 | `manager_singleton.py` |

### 辅助工具

| 工具 | 功能 | 文件 |
|------|------|------|
| 向量生成 | 文本嵌入 | `utils/embeddings.py` |
| 相似度计算 | 余弦相似度 | `utils/similarity.py` |
| 格式化器 | 三层数据格式化 | `utils/three_tier_formatter.py` |
| 存储系统 | 磁盘持久化 | `storage/` |

---

## 📝 版本信息

- **架构**：三层分级记忆系统
- **存储**：SQLAlchemy 2.0 + Chroma 向量库
- **图数据库**：NetworkX
- **最后更新**：2025 年 12 月 21 日