# Napcat Video Processing Guide

## Overview

How to configure and control video message handling in the Napcat adapter for MoFox-Bot.

**Related issue**: [#10 - Add a switch to control video download](https://github.com/MoFox-Studio/MoFox-Core/issues/10)

---

## Quick Start

### Disable video downloads (recommended for low spec or limited bandwidth)

Edit `config/bot_config.toml`, find `[napcat_adapter.features]`, and set:

```toml
[napcat_adapter.features]
enable_video_processing = false  # Disable video handling
```

Effect: Video messages show as `[video message]` and are not downloaded.

---

## Configuration Options

### Main switch: `enable_video_processing`

| Field | Value |
| --- | --- |
| **Type** | bool (`true` / `false`) |
| **Default** | `true` |
| **Meaning** | Whether to download/process video messages |

**Enabled (`true`)**:
- ✅ Auto-download videos
- ✅ Convert to base64 and send to AI
- ⚠️ Uses bandwidth and CPU

**Disabled (`false`)**:
- ✅ Skip video downloads
- ✅ Show `[video message]` placeholder
- ✅ Much lower bandwidth and CPU

### Advanced options

#### `video_max_size_mb`

| Field | Value |
| --- | --- |
| **Type** | int |
| **Default** | `100` (MB) |
| **Suggested range** | 10–500 MB |
| **Meaning** | Max allowed video size to download |

Use this to avoid fetching oversized videos.

Suggested values:
- **Low spec** (2GB RAM): 10–20 MB
- **Mid** (8GB RAM): 50–100 MB
- **High** (16GB+ RAM): 100–500 MB

```toml
# Allow only videos under 50MB
video_max_size_mb = 50
```

#### `video_download_timeout`

| Field | Value |
| --- | --- |
| **Type** | int |
| **Default** | `60` (seconds) |
| **Suggested range** | 30–180 seconds |
| **Meaning** | Download timeout |

Use this to avoid hanging on bad downloads.

Suggested values:
- **Poor network** (2–5 Mbps): 120–180s
- **Average** (5–20 Mbps): 60–120s
- **Good** (20+ Mbps): 30–60s

```toml
# Increase timeout to 120s
video_download_timeout = 120
```

---

## Common Scenarios

### Scenario 1: Limited server bandwidth

**Symptom**: Many videos in group chats saturate bandwidth.

**Solution**:
```toml
[napcat_adapter.features]
enable_video_processing = false
```

### Scenario 2: Low-performance machine

**Symptom**: High CPU while processing videos slows other features.

**Solution**:
```toml
[napcat_adapter.features]
enable_video_processing = true
video_max_size_mb = 20         # small videos only
video_download_timeout = 30    # quick timeout
```

### Scenario 3: Disable during specific hours

If needed for certain periods:

1. Edit config.
2. Reload config via API (if available).

Example: off during work hours, on after.

### Scenario 4: Keep full processing (default)

```toml
[napcat_adapter.features]
enable_video_processing = true
video_max_size_mb = 100
video_download_timeout = 60
```

---

## How It Works

### When enabled

```
Message arrives
  ↓
Check enable_video_processing
  ├─ false → return [video message] placeholder ✓
  └─ true  ↓
      Check file size
        ├─ > video_max_size_mb → return error ✓
        └─ ≤ video_max_size_mb ↓
            Start download (wait up to video_download_timeout)
              ├─ Success → return video data ✓
              ├─ Timeout → return timeout error ✓
              └─ Failure → return error ✓
```

### When disabled

```
Message arrives
  ↓
Check enable_video_processing
  └─ false → immediately return [video message] placeholder ✓
             (saves bandwidth and CPU)
```

---

## Error Handling

Placeholders shown to users when issues occur:

| Message | Meaning |
| --- | --- |
| `[video message]` | Video handling disabled or data incomplete |
| `[video message] (too large)` | Video exceeds size limit |
| `[video message] (download failed)` | Network error or service unavailable |
| `[video message error]` | Other exceptions |

These prevent crashes when video handling fails.

---

## Performance Comparison

| Mode | Bandwidth | CPU | Memory | Latency |
| --- | --- | --- | --- | --- |
| **Disabled** (`false`) | 🟢 Very low | 🟢 Very low | 🟢 Very low | 🟢 Very fast |
| **Enabled, small videos** (≤20MB) | 🟡 Medium | 🟡 Medium | 🟡 Medium | 🟡 Moderate |
| **Enabled, large videos** (≤100MB) | 🔴 High | 🔴 High | 🔴 High | 🔴 Slower |

---

## Monitoring and Debugging

### Verify config

After startup, check logs for:

```
[napcat_adapter] Video downloader initialized: max_size=100MB, timeout=60s
```

### Observe processing

During video handling, logs show:

```
[video_handler] Start download: https://...
[video_handler] Download success, size: 25.50 MB
```

Or:

```
[napcat_adapter] Video handling disabled, skip
```

---

## FAQ

### Q1: Will disabling video affect AI replies?

**A**: No. AI still sees `[video message]` placeholders and can judge context.

### Q2: Different strategies per group?

**A**: Not supported yet; all groups share one config. Propose it via issue/discussion if needed.

### Q3: Does downloading add latency?

**A**: Yes. Large videos take seconds. Suggestions:
- Set a reasonable `video_download_timeout`.
- Or disable video processing for fastest responses.

### Q4: Need restart after config change?

**A**: Yes. Restart the bot to apply.

### Q5: How to diagnose download problems quickly?

**A**:
1. Check error logs.
2. Verify network.
3. Ensure `video_max_size_mb` is not too small.
4. Try increasing `video_download_timeout`.

---

## Best Practices

1. **New users**: Start with video enabled; tune or disable if performance issues appear.

2. **Production**:
   - Monitor video errors in logs regularly.
   - Adjust parameters based on actual network/CPU.
   - Consider disabling during peak times.

3. **Development/debug**:
   - Enable DEBUG logs.
   - Test different `video_max_size_mb` values.
   - Check timeout suitability for the network.

---

## Links

- **GitHub Issue #10**: [Add a switch to control video download](https://github.com/MoFox-Studio/MoFox-Core/issues/10)
- **Config file**: `config/bot_config.toml`
- **Implementation**: 
  - `src/plugins/built_in/napcat_adapter/plugin.py`
  - `src/plugins/built_in/napcat_adapter/src/handlers/to_core/message_handler.py`
  - `src/plugins/built_in/napcat_adapter/src/handlers/video_handler.py`

---

## Feedback

For questions or suggestions, please open a GitHub issue.

**Version**: v2.1.0  
**Last Updated**: 2025-12-16
