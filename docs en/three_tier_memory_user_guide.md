# Three-Tier Memory System User Guide

## Overview

The three-tier memory system is inspired by human memory and contains three layers:

1. **Perceptual Memory**: short buffer that stores the most recent message chunks
2. **Short-Term Memory**: active structured memories for important information
3. **Long-Term Memory**: persistent graph-based knowledge base

## Quick Start

### 1) Enable the system

Edit `config/bot_config.toml`:

```toml
[three_tier_memory]
enable = true
data_dir = "data/memory_graph/three_tier"
```

### 2) Configure parameters

Perceptual layer
```toml
perceptual_max_blocks = 50
perceptual_block_size = 5
perceptual_similarity_threshold = 0.55
perceptual_topk = 3
```

Short-term layer
```toml
short_term_max_memories = 100
short_term_transfer_threshold = 0.6
short_term_search_top_k = 5
short_term_decay_factor = 0.98
activation_threshold = 3
```

Long-term layer
```toml
long_term_batch_size = 10
long_term_decay_factor = 0.95
long_term_auto_transfer_interval = 600
```

Judge model
```toml
judge_model_name = "utils_small"
judge_temperature = 0.1
enable_judge_retrieval = true
```

### 3) Start the bot

```powershell
python bot.py
```

The system will:
- Initialize the three-tier manager
- Create required data directories
- Start auto-transfer tasks (every 10 minutes)

## How It Works

### Message flow

```
New message
    ↓
Append to perceptual memory (message block)
    ↓
Accumulate 5 messages → build embedding
    ↓
Recalled TopK 3 times → activate
    ↓
Activated block moves to short-term
    ↓
LLM extracts structured info (subject/topic/object)
    ↓
LLM decides merge/update/create/drop
    ↓
Importance ≥ 0.6 → move to long-term
    ↓
LLM creates graph ops (CREATE/UPDATE/MERGE nodes/edges)
    ↓
Update memory graph
```

### Retrieval flow

```
User query
    ↓
Retrieve perceptual (TopK similar blocks)
    ↓
Retrieve short-term (TopK structured memories)
    ↓
Judge model checks sufficiency
    ↓
If insufficient → query long-term graph
    ↓
Merge results and return
```

## Examples

### Daily chat

User: "I went to the supermarket and bought milk and bread today"

Processing:
1. Add to perceptual block
2. After 5 messages, build embedding
3. If recalled 3 times, move to short-term
4. LLM extracts: subject=user, topic=shopping, object=milk and bread
5. Importance < 0.6, stay in short-term

### Important event

User: "I have an important interview next Wednesday"

Processing:
1. Perceptual → short-term (activated)
2. LLM extracts: subject=user, topic=interview, object=next Wednesday
3. Importance ≥ 0.6 (future plan)
4. Move to long-term
5. Graph op:
   ```json
   {
     "operation": "CREATE_MEMORY",
     "content": "User will attend an important interview next Wednesday"
   }
   ```

### Smart retrieval

Query: "When was the interview I mentioned?"

Flow:
1. Perceptual: find recent blocks mentioning the interview
2. Short-term: find structured interview memory
3. Judge: "need more context"
4. Long-term: find the "next Wednesday interview" event
5. Return combined result:
   - Perceptual: recent dialog snippet
   - Short-term: structured interview info
   - Long-term: full interview plan details

## Operations

### View statistics

```python
from src.memory_graph.three_tier.manager_singleton import get_unified_memory_manager

manager = get_unified_memory_manager()
stats = await manager.get_statistics()

print(f"Perceptual blocks: {stats['perceptual']['total_blocks']}")
print(f"Short-term memories: {stats['short_term']['total_memories']}")
print(f"Long-term memories: {stats['long_term']['total_memories']}")
```

### Manual transfer

```python
transferred = await manager.transfer_to_long_term()
print(f"Transferred {transferred} memories to long term")
```

### Cleanup

```python
from src.memory_graph.three_tier.short_term_manager import get_short_term_manager

short_term = get_short_term_manager()
await short_term.cleanup_low_importance(threshold=0.2)
```

## Best Practices

### Model choices

- Judge: fast small models (utils_small, gpt-4o-mini)
- Extraction: stronger understanding (gpt-4, claude-3.5-sonnet)
- Graph ops: logical reasoning (gpt-4, claude)

### Parameter tuning

High-traffic chats (groups):
```toml
perceptual_max_blocks = 100
activation_threshold = 5
short_term_max_memories = 200
```

Low-traffic deep chats (DM):
```toml
perceptual_max_blocks = 30
activation_threshold = 2
short_term_transfer_threshold = 0.5
```

### Performance

- Batch transfers to long-term (default 10 per batch)
- Cache judge decisions to avoid repeated calls
- All operations are async; do not block main flow

### Data safety

- Back up `data/memory_graph/three_tier/`
- JSON persistence for all data
- Crash recovery from last saved state

## Troubleshooting

### System not initialized

- Check `[three_tier_memory] enable = true` in `bot_config.toml`
- Ensure config path is correct
- Restart the bot

### LLM call failures

- Verify model config (`model_config.toml`)
- Check API keys
- Try another model
- Inspect logs for details

### Memories not transferring

- Lower `short_term_transfer_threshold`
- Ensure auto-transfer task is running
- Trigger transfer manually
- Inspect LLM-generated graph ops

### Irrelevant retrieval

- Adjust `perceptual_similarity_threshold` upward
- Increase `short_term_search_top_k`
- Enable `enable_judge_retrieval`
- Verify embeddings are generated correctly

## Performance Metrics

Expected:
- Perceptual add: <5 ms
- Short-term search: <100 ms
- Long-term transfer: 1-3 s per item (LLM)
- Smart retrieval: 200-500 ms (with Judge)

Resource footprint:
- Memory:
  - Perceptual: ~10 MB (50 blocks × 5 messages)
  - Short-term: ~20 MB (100 structured memories)
  - Long-term: depends on the existing graph system
- Disk:
  - JSON: ~1-5 MB
  - Vector store: ~10-50 MB (ChromaDB)

## Related Docs

- database_refactoring_completion.md
- memory_graph_guide.md
- unified_scheduler_guide.md
- plugins/quick-start.md

## Contributing

If you encounter issues or have suggestions:
1. Check GitHub Issues
2. File detailed reports (with logs)
3. Review sample code and best practices

---

Version: 1.0.0  
Last updated: 2025-01-13  
Maintainer: MoFox_Bot Team
