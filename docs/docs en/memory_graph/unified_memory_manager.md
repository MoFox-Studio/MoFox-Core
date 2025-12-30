# Unified Memory Manager Usage Guide

> Applicable to three-tier memory (perceptual / short-term / long-term) unified scheduling and retrieval.

## Positioning and Responsibilities

- Entry Point: Unified encapsulation in [src/memory_graph/unified_manager.py](src/memory_graph/unified_manager.py), responsible for initialization, retrieval, transfer, and statistics of three-tier memory.
- Goal: Hide implementation details of each layer from upper-level callers, providing consistent `initialize → add_message → search_memories → shutdown` lifecycle.
- Collaborative Components:
  - Perceptual Layer: `PerceptualMemoryManager` (message block buffering/activation detection)
  - Short-Term Layer: `ShortTermMemoryManager` (structured, importance assessment)
  - Long-Term Layer: `LongTermMemoryManager` (persistence, semantic retrieval, batch transfer)

## Initialization and Configuration

When calling `UnifiedMemoryManager()`, the following key parameters can be overridden (see defaults in file):
- Perceptual Layer: `perceptual_max_blocks`, `perceptual_block_size`, `perceptual_activation_threshold`, `perceptual_recall_top_k`, `perceptual_recall_threshold`
- Short-Term Layer: `short_term_max_memories`, `short_term_transfer_threshold`, `short_term_overflow_strategy`, `short_term_enable_force_cleanup`, `short_term_cleanup_keep_ratio`
- Long-Term Layer: `long_term_batch_size`, `long_term_search_top_k`, `long_term_decay_factor`, `long_term_auto_transfer_interval`
- Intelligent Judge: `judge_confidence_threshold` (confidence below threshold tends to trigger long-term retrieval)

### Lifecycle Hooks

- `initialize()`: Create/initialize three-tier managers and underlying `MemoryManager`, and start automatic transfer task.
- `shutdown()`: Cancel background tasks, sequentially shut down each layer manager and underlying storage.

## Core Call Flow

### 1) Write Path

- `add_message(message: dict)`: Append new message to perceptual layer. Perceptual→short-term transfer doesn't happen here; it's triggered during retrieval phase.

### 2) Retrieval Path

- `search_memories(query_text, use_judge=True, recent_chat_history="")`: Main entry point. Process overview:
  1. Parallel retrieval of perceptual blocks and short-term memories.
  2. One-time scan of perceptual blocks, mark `needs_transfer` blocks and transfer to short-term layer in background.
  3. Send recalled results to "Memory Judge" model:
     - If insufficient, generate supplementary query and trigger long-term retrieval (multi-query weighted).
     - If sufficient, directly return perceptual/short-term results.
  4. Final output includes three-tier memory list and judge decision.

### 3) Long-Term Retrieval Details

- `_build_manual_multi_queries()`: Deduplicate supplementary queries from judge and assign decreasing weights.
- `_retrieve_long_term_memories()`: Trigger multi-query search based on base query and supplementary queries, can attach recent chat context to optimize recall.
- `_deduplicate_memories()`: Deduplicate based on `memory.id`, compatible with dict/object results.

## Automatic and Background Tasks

- Perceptual→Short-Term Transfer:
  - `_schedule_perceptual_block_transfer()`: Process multiple blocks in parallel in background, trigger wake event after successful transfer.
  - `_transfer_blocks_to_short_term()`: Delete perceptual blocks after successful transfer to avoid duplicate processing.
- Auto-Transfer Loop:
  - `_auto_transfer_loop()`: Batch transfer from short-term to long-term when full; wait interval adaptively adjusted by `_calculate_auto_sleep_interval()` based on usage rate.
  - Support manual trigger `manual_transfer()` for debugging or exception fallback.

## Statistics and Observation

- `get_statistics()`: Return three-tier statistics and total count (perceptual messages + short-term memories + long-term memories).
- Logging: All background tasks attach exception callbacks for easy failure location in logs.

## Failure and Fallback Strategy

- When judge model fails, default to "need to retrieve long-term memory" to reduce miss risk.
- Auto-transfer task exceptions are caught and logged without blocking main flow; swallow `CancelledError` on cancellation.

## Usage Example

```python
from src.memory_graph.unified_manager import UnifiedMemoryManager

mgr = UnifiedMemoryManager()
await mgr.initialize()

# Write message
await mgr.add_message({"content": "I ran 5 kilometers today", "sender_id": "user_1"})

# Intelligent retrieval (with judge and long-term supplementary retrieval)
result = await mgr.search_memories(
    query_text="User's exercise records",
    use_judge=True,
    recent_chat_history="Talked about running plan yesterday",
)

# Manual transfer (only executes if short-term layer is full)
await mgr.manual_transfer()

# Shutdown
await mgr.shutdown()
```

## Debugging Suggestions

- If short-term layer fails to transfer for a long time, check if `short_term_max_memories` and current usage have reached capacity limit.
- If long-term retrieval returns no results, confirm judge model configuration and supplementary query hit target entity; if necessary, set `use_judge=False` to directly use long-term retrieval.
- Adjusting `long_term_auto_transfer_interval` and `_calculate_auto_sleep_interval()` can balance latency and resource consumption.
