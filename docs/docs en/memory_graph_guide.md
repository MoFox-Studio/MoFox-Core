# Memory Graph System User Guide

## Overview

The memory graph system is MoFox Bot's next-generation memory management system based on graph-structured storage and retrieval, providing intelligent memory search, consolidation, and forgetting mechanisms.

## Core Features

### 1. Graph-structured Storage
- Uses **node-edge** model to represent memories
- Supports complex memory relationship networks
- Efficient graph traversal and adjacency queries

### 2. Intelligent Memory Retrieval
- **Vector similarity search**: retrieve related memories based on semantic understanding
- **Query optimization**: automatically expand query keywords
- **Importance ranking**: prioritize important memories
- **Graph expansion**: optionally expand to adjacent memories

### 3. Automatic Memory Consolidation
- **Similarity detection**: automatically identify similar memories
- **Smart merging**: merge duplicate memories and boost activation
- **Time window**: configurable consolidation timeframe
- **Periodic execution**: automatic consolidation every hour (configurable)

### 4. Memory Forgetting Mechanism
- **Activation decay**: gradually lower activation of unused memories
- **Auto cleanup**: automatically forget low-activation memories
- **Importance protection**: high-importance memories won't be forgotten

## Configuration Guide

### Basic Configuration (`bot_config.toml`)

```toml
[memory_graph]
# Enable switch
enable = true

# Data storage directory
data_dir = "data/memory_graph"

# Vector database config
vector_collection_name = "memory_nodes"
vector_db_path = ""  # empty uses data_dir

# Search config
search_top_k = 5  # return top 5 related memories
search_min_importance = 0.0  # minimum importance threshold
search_similarity_threshold = 0.0  # similarity threshold
search_optimize_query = true  # enable query optimization

# Memory consolidation config
consolidation_enabled = true  # enable auto consolidation
consolidation_interval_hours = 1.0  # run hourly
consolidation_similarity_threshold = 0.85  # >=0.85 considered duplicate
consolidation_time_window_hours = 24  # consolidate past 24 hours

# Memory forgetting config
forgetting_enabled = true  # enable auto forgetting
forgetting_activation_threshold = 0.1  # forget if activation < 0.1
forgetting_min_importance = 0.3  # don't forget if importance >= 0.3

# Activation config
activation_decay_rate = 0.95  # decay 5% per day
activation_propagation_strength = 0.1  # propagation strength 10%
activation_propagation_depth = 2  # propagation depth 2 levels

# Performance config
max_nodes_per_memory = 50  # max 50 nodes per memory
max_related_memories = 10  # return max 10 related memories
```

### Configuration Items Reference

| Config | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | bool | true | Enable memory graph system |
| `data_dir` | string | "data/memory_graph" | Data storage directory |
| `search_top_k` | int | 5 | Search result count |
| `search_optimize_query` | bool | true | Enable query optimization |
| `consolidation_enabled` | bool | true | Enable auto consolidation |
| `consolidation_interval_hours` | float | 1.0 | Consolidation interval (hours) |
| `consolidation_similarity_threshold` | float | 0.85 | Similarity threshold |
| `forgetting_enabled` | bool | true | Enable auto forgetting |
| `forgetting_activation_threshold` | float | 0.1 | Forgetting threshold |
| `activation_decay_rate` | float | 0.95 | Activation decay rate |

## LLM Tool Usage

### 1. Create Memory (`create_memory`)

**Description**: Create a new memory with subject, topic, and related information.

**Parameters**:
- `subject` (required): Memory subject, e.g., "user", "AI assistant"
- `memory_type` (required): Memory type, e.g., "event", "knowledge", "preference"
- `topic` (required): Memory topic, short description
- `object` (optional): Memory object
- `attributes` (optional): Additional attributes in JSON format
- `importance` (optional): Importance 0.0-1.0, default 0.5

**Example**:
```json
{
  "subject": "user",
  "memory_type": "preference",
  "topic": "likes sunny days",
  "importance": 0.7
}
```

**Return**:
```json
{
  "name": "create_memory",
  "content": "Successfully created memory (ID: mem_xxx)",
  "memory_id": "mem_xxx"
}
```

### 2. Search Memories (`search_memories`)

**Description**: Search related memories based on query.

**Parameters**:
- `query` (required): Search query text
- `top_k` (optional): Result count, default 5
- `expand_depth` (optional): Graph expansion depth, default 1

**Example**:
```json
{
  "query": "weather preference",
  "top_k": 3
}
```

### 3. Link Memories (`link_memories`)

**Description**: Create association between two memories (not exposed to LLM yet).

## Code Usage Examples

### Initialize Memory Manager

```python
from src.memory_graph.manager_singleton import initialize_memory_manager, get_memory_manager

# Initialize (call once at bot startup)
await initialize_memory_manager()

# Get manager instance
manager = get_memory_manager()
```

### Create Memory

```python
memory = await manager.create_memory(
    subject="user",
    memory_type="event",
    topic="asking about weather",
    object_="Shanghai",
    attributes={"time": "morning"},
    importance=0.7
)
print(f"Created memory: {memory.id}")
```

### Search Memories

```python
memories = await manager.search_memories(
    query="weather",
    top_k=5,
    optimize_query=True  # enable query optimization
)

for mem in memories:
    print(f"- {mem.get_subject_node().content}: {mem.importance}")
```

### Activate Memory

```python
# Memory automatically activates on access
await manager.activate_memory(memory.id, strength=0.5)
```

### Manual Maintenance

```python
# Consolidate similar memories
result = await manager.consolidate_memories(
    similarity_threshold=0.85,
    time_window_hours=24
)
print(f"Merged {result['merged_count']} memories")

# Forget low-activation memories
forgotten = await manager.auto_forget_memories(
    activation_threshold=0.1,
    min_importance=0.3
)
print(f"Forgot {forgotten} memories")
```

### Get Statistics

```python
stats = manager.get_statistics()
print(f"Total memories: {stats['total_memories']}")
print(f"Active memories: {stats['active_memories']}")
print(f"Avg activation: {stats['avg_activation']:.3f}")
```

## Best Practices

### 1. Memory Importance Scoring

- **0.8-1.0**: Very important (user core preferences, key events)
- **0.6-0.8**: Important (common preferences, important conversations)
- **0.4-0.6**: Medium (regular events)
- **0.2-0.4**: Secondary (temporary information)
- **0.0-0.2**: Unimportant (trivial details)

### 2. Memory Type Selection

- **event**: Specific things that happened (questions, answers, activities)
- **knowledge**: Factual information (definitions, explanations)
- **preference**: User likes/dislikes
- **relationship**: Relationships between entities
- **skill**: Abilities or techniques

### 3. Performance Optimization

- Regular cleanup: manually run deep consolidation weekly
- Adjust thresholds: adjust similarity and forgetting thresholds based on usage
- Limit quantity: keep single memory node count < 50
- Batch operations: use batch APIs to reduce calls

### 4. Maintenance Recommendations

- **Daily**: auto consolidation and forgetting (system automatic)
- **Weekly**: check statistics and adjust configs
- **Monthly**: backup memory data (`data/memory_graph/`)

## Data Persistence

### Storage Structure

```
data/memory_graph/
├── memory_graph.json     # graph structure data
└── chroma_db/            # vector database
    └── memory_nodes/     # node vector collection
```

### Backup Recommendations

```bash
# Backup entire memory graph directory
cp -r data/memory_graph/ backup/memory_graph_$(date +%Y%m%d)/

# Or use git
cd data/memory_graph/
git add .
git commit -m "Backup: $(date)"
```

## Troubleshooting

### Issue 1: Memory Search Returns Empty

**Possible causes**:
- Vector database not initialized
- Query keyword too vague
- Similarity threshold set too high

**Solution**:
```python
# Lower similarity threshold
memories = await manager.search_memories(
    query="specific keyword",
    top_k=10,
    min_similarity=0.0  # lower threshold
)
```

### Issue 2: Overly Aggressive Memory Consolidation

**Possible cause**:
- Similarity threshold set too low

**Solution**:
```toml
# Increase consolidation threshold
consolidation_similarity_threshold = 0.90  # from 0.85 to 0.90
```

### Issue 3: High Memory Usage

**Possible causes**:
- Too many memories
- High vector dimension

**Solution**:
```toml
# Enable more aggressive forgetting
forgetting_activation_threshold = 0.2  # from 0.1 to 0.2
forgetting_min_importance = 0.4  # from 0.3 to 0.4
```

## Migration Guide

### Migrating from Old Memory System

The old memory system (`[memory]` config) is deprecated; migration to new system recommended:

1. **Backup old data**: backup `data/memory/` directory
2. **Update config**: remove `[memory]` config, enable `[memory_graph]`
3. **Restart system**: new system will auto-initialize
4. **Verify functionality**: test memory creation and retrieval

**Note**: Old memory data won't auto-migrate; manual import needed if required.

## API Reference

Complete API documentation available at:
- `src/memory_graph/manager.py` - MemoryManager core API
- `src/memory_graph/plugin_tools/memory_plugin_tools.py` - LLM tools
- `src/memory_graph/models.py` - data models

## Changelog

### v7.6.0 (2025-11-05)
- ✅ Complete memory graph system implementation
- ✅ LLM tool integration
- ✅ Auto consolidation and forgetting mechanisms
- ✅ Configuration system support
- ✅ Complete integration tests (5/5 passing)

---

**Related Documentation**:
- [System Architecture](architecture/memory_graph_architecture.md)
- [API Documentation](api/memory_graph_api.md)
- [Development Guide](development/memory_graph_dev.md)

