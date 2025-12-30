# StyleLearner Resource Limit Switch (On by default)

## Overview
StyleLearner enforces capacity and cleanup limits to prevent unbounded growth. The switch is **on by default** and can be toggled at runtime.

## Where and How (read this)

The switch lives in code (no config entry) and is on by default.

1) Global runtime toggle (recommended)
   Location: `src/chat/express/style_learner.py` single instance `style_learner_manager`
   ```python
   from src.chat.express.style_learner import style_learner_manager

   # Disable limit (removes cap; use with care)
   style_learner_manager.set_resource_limit(False)

   # Re-enable limit
   style_learner_manager.set_resource_limit(True)
   ```
   - Scope: updates all existing learners in place (syncs `resource_limit_enabled`).
   - Timing: immediate, no restart needed.

2) Set on construction (rare)
   - `StyleLearner(resource_limit_enabled: True|False, ...)`
   - `StyleLearnerManager(resource_limit_enabled: True|False, ...)`
   Usually keep defaults.

3) Defaults
   - Limit is **enabled**: capacity management and cleanup active.
   - No config file entry; persist the state by calling `set_resource_limit` in startup code if needed.

## Behavior when enabled
- Per-chat capacity:
  - `max_styles = 2000`
  - `cleanup_threshold = 0.9` (cleanup when >= 90% capacity)
  - `cleanup_ratio = 0.2` (drop roughly 20% lowest-value styles)
- Value scoring blends usage frequency (log-smoothed) and recency (exponential decay); lowest scores go first.
- Applies to each learner’s capacity only; LRU eviction policy is unchanged.

> Switch effect:
> - **On**: `add_style` checks capacity and can call `_cleanup_styles`; prediction/learning logic unchanged.
> - **Off**: no capacity cleanup; process-level LRU may still evict inactive learners.

## I/O and resilience
- Atomic writes for model and metadata (`.tmp` + `os.replace`) to avoid partial writes.
- `pickle` uses `HIGHEST_PROTOCOL` plus `fsync` to ensure durability.

## Compatibility
- On by default; no config edits needed. Off state behaves like older versions.
- Existing model files load as-is; the switch only affects runtime cleanup policy.

## When to keep it on/off
- On (default): limited RAM/disk or fast style growth; prevent bloat.
- Off: need to keep all historical styles and resources are ample, or for one-off data collection.

## Monitoring and tuning
- Track per-chat style count, cleanup triggers, deleted count, prediction latency p95.
- If cleanup is too aggressive: raise `cleanup_threshold` or lower `cleanup_ratio`.
- If memory/disk remains high: lower `max_styles`, add periodic persistence/compression.
