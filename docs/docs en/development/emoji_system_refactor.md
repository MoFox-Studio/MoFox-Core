# Emoji System Refactoring Report

Date: 2025-12-15

## Goals

- Decouple the monolithic `emoji_manager.py` by separating entities, constants, and file utilities.
- Reduce event loop blocking during scanning/registration periods.
- Preserve existing behavior (LLM/VLM workflow, capacity replacement, cache lookup) while improving maintainability.

## New Structure

- `src/chat/emoji_system/emoji_constants.py`: Shared paths and prompt/quantity limits.
- `src/chat/emoji_system/emoji_entities.py`: `MaiEmoji` (hashing, format detection, database insert/delete, cache invalidation).
- `src/chat/emoji_system/emoji_utils.py`: Directory assurance, temporary cleanup, incremental file scanning, DB row to entity conversion.
- `src/chat/emoji_system/emoji_manager.py`: Handles integrity checks, scanning, registration, VLM/LLM descriptions, replacement and caching, delegating to the above modules.
- `src/chat/emoji_system/README.md`: Quick start/lifecycle guide.

## Behavioral Changes

- Integrity checking now uses cursor-based incremental scanning, yielding to the event loop after processing every 50 files.
- Heavy file operations within the loop (exists, listdir, remove, makedirs) are offloaded to the main loop via `asyncio.to_thread`.
- Directory scanning uses `os.scandir` (via `list_image_files`), reducing redundant stat calls and returning both file list and empty status.
- Fast lookup: Rebuild `_emoji_index` on load, keep in sync during add/delete; `get_emoji_from_manager` prioritizes index lookups.
- Registration and replacement workflows simultaneously update the index and asynchronously clean up failed/duplicate files.

## Migration Notes

- Existing calls continue using `get_emoji_manager()` and `EmojiManager` API; external interfaces are unchanged.
- If you previously imported constants or utilities directly from `emoji_manager`, change to importing from `emoji_constants`, `emoji_entities`, or `emoji_utils`.
- Tests/scripts relying on synchronous file timing may observe different latency, but logic is equivalent.

## Future Recommendations

1. Add unit tests for `list_image_files`, `clean_unused_emojis`, and incremental cursor behavior.
2. Externalize VLM/LLM prompt templates into configuration for easier iteration.
3. Expose metrics like scan latency, cleanup count, and registration delay for observability.
4. Add retry limits for `replace_a_emoji` LLM calls and log prompt/decision for audit trails.
