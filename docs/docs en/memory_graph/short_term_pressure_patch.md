# Short-Term Memory Pressure Relief Patch (Deprecated)

## Background

In some scenarios, the short-term memory layer can quickly accumulate before automatic transfer is triggered, potentially causing the short-term memory to reach capacity limit and block subsequent writes.

## Changes (Patch)

- Added "Pressure Relief" switch: When usage reaches 100%, you can optionally delete low-importance and earliest short-term memories to prevent continuous expansion of the short-term layer.
- Disabled by default; requires explicit activation before automatic deletion executes.

## Switch Configuration

- Entry Point: `UnifiedMemoryManager` constructor parameter
  - `short_term_enable_force_cleanup: bool = False`
- Pass to short-term layer: `ShortTermMemoryManager(enable_force_cleanup=True)`
- Disable Example:
  ```python
  manager = UnifiedMemoryManager(
      short_term_enable_force_cleanup=False,
  )
  ```

## Behavior Description

- When short-term memory usage reaches or exceeds 100%, and there is no pending transfer batch:
  - Triggers `force_cleanup_overflow()`
  - Deletes a batch of memories prioritized by "low importance first, earliest creation time first", reducing capacity back to approximately `max_memories * 0.9`
- Cleanup runs in background persistence, non-blocking to main flow.

## Impact Scope

- Default behavior remains consistent with pre-patch (switch defaults to `off`).
- If the switch is disabled, the short-term layer will not perform forced deletion and only relies on automatic transfer mechanism.

## Rollback

- Set `short_term_enable_force_cleanup=False` during construction to disable; no code rollback needed.
