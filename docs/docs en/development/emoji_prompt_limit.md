# Emoji Replacement Candidate Count Explanation

## Background

`MAX_EMOJI_FOR_PROMPT` is used in scenarios like `replace_a_emoji` to limit the number of candidate emojis sent to the LLM, avoiding excessively long context that could slow down responses or increase token costs.

## Why 20

- **Balance**: Decision quality plateaus after a dozen options, but token/time cost increases linearly.
- **Performance**: With common models and hardware, 20 descriptions can return a decision within acceptable latency.
- **Compatibility**: Historical implementations also use 20, maintaining stable behavior.

## When to Adjust

- **Stronger device/model and want broader coverage**: Can increase to 30-40, but watch for latency and costs.
- **Low computational power or latency sensitive**: Can lower to 10-15 to speed up decisions.
- **Special scenarios** (focused themes, small library): Lowering helps avoid meaningless redundant candidates.

## How to Modify

- **Constant location**: `MAX_EMOJI_FOR_PROMPT` in `src/chat/emoji_system/emoji_constants.py`.
- **For dynamic configuration**: Can migrate it to a config item under `global_config.emoji` and have `emoji_manager` read it.

## Recommendations

- **Observe after adjusting**: replacement decision latency, model costs, false deletion rate (whether deleted emojis were actually needed).
- **If continuing to expand the emoji library**: Consider adding pre-filtering strategy based on usage frequency or time to the candidate list.
