"""
Kokoro Flow Chatter - 统一模式提示词模块

为统一模式（Unified Mode）提供模块化的提示词构建：
1. 核心身份模块 - 人设/人格/背景
2. 行为准则模块 - 规则/边界
3. 情境上下文模块 - 时间/场景/内在状态/关系/记忆
4. 动作能力模块 - 可用动作的描述
5. 输出格式模块 - 表达风格 + JSON格式

设计理念：
- 每个模块只负责自己的部分，互不干扰
- 回复相关内容（人设、上下文）与动作定义分离
- 方便独立调试和优化每个部分

注意：此模块仅用于统一模式，分离模式使用 prompt/builder.py
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.common.logger import get_logger
from src.config.config import global_config
from src.plugin_system.base.component_types import ActionInfo

if TYPE_CHECKING:
    from src.chat.message_receive.chat_stream import ChatStream
    from src.common.data_models.message_manager_data_model import StreamContext

from .models import EventType, MentalLogEntry
from .session import KokoroSession

logger = get_logger("kfc_prompt_unified")


# ============================================================
# 模块1: 核心身份 - 人设/人格/背景
# ============================================================

def build_identity_module() -> str:
    """
    构建核心身份模块

    包含：人格核心、人格细节、外貌身份、世界观背景
    这些是回复内容的基础，决定了"你是谁"
    """
    if global_config is None:
        raise RuntimeError("global_config 未初始化")

    personality_cfg = global_config.personality

    personality_core = personality_cfg.personality_core or "你是一个温暖、真诚的对话伙伴。"
    personality_side = personality_cfg.personality_side or ""
    identity = personality_cfg.identity or ""
    background_story = personality_cfg.background_story or ""

    parts = [personality_core]

    if personality_side:
        parts.append(f"\n{personality_side}")

    if identity:
        parts.append(f"\n{identity}")

    if background_story:
        parts.append(f"\n### 背景故事\n{background_story}")

    return "\n".join(parts)


# ============================================================
# 模块2: 行为准则 - 规则/边界/KFC特有准则
# ============================================================

def build_rules_module() -> str:
    """
    构建行为准则模块

    包含：安全规则 + KFC 通用准则
    这些是行为的边界，决定了"什么能做什么不能做"
    """
    if global_config is None:
        raise RuntimeError("global_config 未初始化")

    safety_guidelines = global_config.personality.safety_guidelines or []
    if isinstance(safety_guidelines, list):
        safety_guidelines_str = "\n".join(f"- {rule}" for rule in safety_guidelines)
    else:
        safety_guidelines_str = str(safety_guidelines)

    # KFC 通用准则
    kfc_rules = """- 说话要自然，像平时发微信一样
- 有自己的边界感，不用无条件迎合
- 称呼对方用自然的昵称，别念复杂的用户名
- 不要模仿聊天记录里的系统格式（比如"[表情包：xxx]"这种是系统标记，要发送表情包请使用emoji动作）"""

    return f"""{safety_guidelines_str}

{kfc_rules}"""


# ============================================================
# 模块2.5: 自定义决策提示词 - 用户自定义的决策行为指导
# ============================================================

def build_custom_decision_module() -> str:
    """
    构建自定义决策提示词模块

    允许用户通过配置文件自定义KFC的决策行为指导
    类似于AFC的planner_custom_prompt_content
    """
    from .config import get_config

    kfc_config = get_config()
    custom_prompt = getattr(kfc_config, "custom_decision_prompt", "")

    # 调试输出
    logger.debug(f"[自定义决策提示词] 原始值: {custom_prompt!r}, 类型: {type(custom_prompt)}")

    if not custom_prompt or not custom_prompt.strip():
        logger.debug("[自定义决策提示词] 为空或仅含空白字符，跳过")
        return ""

    logger.info(f"[自定义决策提示词] 已加载: {custom_prompt.strip()}")
    return custom_prompt.strip()


# ============================================================
# 模块3: 情境上下文 - 时间/场景/内在状态/关系/记忆
# ============================================================

def build_context_module(
    session: KokoroSession,
    chat_stream: Optional["ChatStream"] = None,
    context_data: dict[str, str] | None = None,
) -> str:
    """
    构建情境上下文模块

    包含：当前时间、聊天场景、内在状态、关系信息、记忆
    这些是回复的上下文，决定了"当前在什么情况下"

    Args:
        session: 当前会话
        chat_stream: 聊天流（判断群聊/私聊）
        context_data: S4U 上下文数据
    """
    context_data = context_data or {}

    # 时间和场景
    current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    is_group_chat = bool(chat_stream and chat_stream.group_info)
    chat_scene = "你在群里聊天" if is_group_chat else "你在和对方私聊"

    # 日程（如果有）
    schedule_block = context_data.get("schedule", "")

    # 内在状态（从 context_data 获取，如果没有使用默认值）
    mood = context_data.get("mood", "平静")

    # 关系信息
    relation_info = context_data.get("relation_info", "")

    # 记忆
    memory_block = context_data.get("memory_block", "")

    # 工具调用结果
    tool_info = context_data.get("tool_info", "")

    parts = []

    # 时间和场景
    parts.append(f"**时间**: {current_time}")
    parts.append(f"**场景**: {chat_scene}")

    # 日程块
    if schedule_block:
        parts.append(f"{schedule_block}")

    # 内在状态
    parts.append(f"\n你现在的心情：{mood}")

    # 关系信息（章节标题由 build_system_prompt 添加）
    if relation_info:
        parts.append(f"\n{relation_info}")

    # 记忆
    if memory_block:
        parts.append(f"\n{memory_block}")

    # 工具调用结果
    if tool_info:
        parts.append(f"\n{tool_info}")

    return "\n".join(parts)


# ============================================================
# 模块4: 动作能力 - 可用动作的描述
# ============================================================

def build_actions_module(available_actions: dict[str, ActionInfo] | None = None) -> str:
    """
    构建动作能力模块

    包含：所有可用动作的描述、参数、示例
    这部分与回复内容分离，只描述"能做什么"

    Args:
        available_actions: 可用动作字典
    """
    if not available_actions:
        return _get_default_actions_block()

    # 核心限制说明（放在最前面）
    action_blocks = [
        """⚠️ **输出限制（必须遵守）**：
1. `actions` 数组里**只能有一个** `kfc_reply`，不能写多个
2. `kfc_reply` 的 `content` 要简洁，像发微信一样，**不要写长篇大论**
3. 系统会自动把你的回复拆分成多条消息发送，你不需要自己分段
"""
    ]

    for action_name, action_info in available_actions.items():
        description = action_info.description or f"执行 {action_name}"

        # 构建动作块
        action_block = f"### `{action_name}` - {description}"

        # 对 kfc_reply 特殊处理，再次强调限制
        if action_name == "kfc_reply":
            action_block += "\n（只能有一个，内容写完整）"

        # 参数说明（如果有）
        if action_info.action_parameters:
            params_lines = [f"  - `{name}`: {desc}" for name, desc in action_info.action_parameters.items()]
            action_block += f"\n参数:\n{chr(10).join(params_lines)}"

        # 使用场景（如果有）
        if action_info.action_require:
            require_lines = [f"  - {req}" for req in action_info.action_require]
            action_block += f"\n使用场景:\n{chr(10).join(require_lines)}"

        # 示例
        example_params = ""
        if action_info.action_parameters:
            param_examples = [f'"{name}": "..."' for name in action_info.action_parameters.keys()]
            example_params = ", " + ", ".join(param_examples)

        action_block += f'\n```json\n{{"type": "{action_name}"{example_params}}}\n```'

        action_blocks.append(action_block)

    return "\n\n".join(action_blocks)


def _get_default_actions_block() -> str:
    """获取默认的内置动作描述块"""
    return """⚠️ **输出限制（必须遵守）**：
1. `actions` 数组里**只能有一个** `kfc_reply`，不能写多个
2. `kfc_reply` 的 `content` 要简洁，像发微信一样，**不要写长篇大论**
3. 系统会自动把你的回复拆分成多条消息发送，你不需要自己分段

### `kfc_reply` - 发消息
```json
{"type": "kfc_reply", "content": "你想说的话"}
```

### `poke_user` - 戳一戳
```json
{"type": "poke_user"}
```

### `do_nothing` - 不做任何事
```json
{"type": "do_nothing"}
```"""


# ============================================================
# 模块5: 表达与输出格式 - 回复风格 + JSON格式
# ============================================================

def build_output_module(context_data: dict[str, str] | None = None) -> str:
    """
    构建输出格式模块

    包含：表达风格、表达习惯、JSON 输出格式要求
    这部分定义了"怎么说"和"输出什么格式"

    Args:
        context_data: S4U 上下文数据（包含 expression_habits）
    """
    if global_config is None:
        raise RuntimeError("global_config 未初始化")

    context_data = context_data or {}

    reply_style = global_config.personality.reply_style or ""
    expression_habits = context_data.get("expression_habits", "")

    # JSON 输出格式说明（更自然的思考引导）
    json_format = """### 输出格式（JSON）

⚠️ **核心规则**：actions 中只能有**一个** `kfc_reply`动作！不能有多个`kfc_reply`动作！想说的话全写在一条消息里，系统会自动拆分发送。

```json
{
  "thought": "你心里的真实想法，像日记一样自然",
  "expected_user_reaction": "猜猜对方看到会怎么想",
  "max_wait_seconds": "预估的等待时间（秒）",
  "actions": [
    {"type": "kfc_reply", "content": "你想说的所有话，写在这里面"}
  ]
}
```

关于 max_wait_seconds（等待时间）：
- 如果你问了一个问题，想等对方回答，可以设置一个等待时间（比如 60-180 秒）
- 如果你发的是陈述句（分享、感叹、总结），对方不一定需要回复，设为 0 是合理的
- 如果对话感觉已经聊完了，设为 0 表示自然结束
- 设为 0 不代表冷淡或急着结束，而是一种正常的对话节奏
- 不确定的时候，设为 0 是安全的选择——真实的对话本来就不需要每次都等回复

关于 thought（内心想法）：
- 写你真正在想的，不是在分析任务
- 像心里嘀咕一样，比如"这家伙又来撒娇了" "有点困了但还想再聊会儿"
- 不要写"根据设定""我需要""我应该"这种规划性的话
- 就是你作为这个人，此刻心里在想什么

关于 expected_user_reaction（预期反应）：
- 随便猜一下对方可能的反应就行
- 比如"可能会撒娇""估计要睡了""应该会觉得好笑"
- 不用分析得很正式

不想做任何事就用 `{"type": "do_nothing"}`"""

    parts = []

    if reply_style:
        parts.append(reply_style)

    if expression_habits:
        parts.append(expression_habits)

    parts.append(json_format)

    return "\n\n".join(parts)


# ============================================================
# 组装完整的 System Prompt（复刻旧版）
# ============================================================

def build_system_prompt(
    session: KokoroSession,
    available_actions: dict[str, ActionInfo] | None = None,
    context_data: dict[str, str] | None = None,
    chat_stream: Optional["ChatStream"] = None,
) -> str:
    """
    组装完整的系统提示词

    按模块顺序组装：
    1. 角色框架
    2. 核心身份（人设）
    3. 行为准则（规则）
    4. 情境上下文（时间/状态/关系）
    5. 动作能力（可用动作）
    6. 输出格式（表达风格 + JSON）

    Args:
        session: 当前会话
        available_actions: 可用动作字典
        context_data: S4U 上下文数据
        chat_stream: 聊天流

    Returns:
        完整的系统提示词
    """
    # 角色框架（不提AI，直接进入角色）
    role_frame = "你是一个真实的人，有自己的生活、想法和情绪。像平时和朋友聊天一样自然地交流。"

    # 获取自定义决策提示词
    custom_decision_block = build_custom_decision_module()

    # 组装各模块（方案B：动作放在规则后面，作为能力描述）
    # 逻辑链条：
    # 1. 你是谁 + 规则 + 能力 → 人设定义
    # 2. 当前情境 → 时间/状态/关系/记忆
    # 3. 怎么回复 → 输出格式（放在最后，紧接对话内容）
    modules = [
        role_frame,
        "",
        "## 1. 你是谁",
        build_identity_module(),
        "",
        "## 2. 规则",
        build_rules_module(),
    ]

    # 如果有自定义决策提示词，插入到规则后面
    if custom_decision_block:
        modules.extend([
            "",
            "## 3. 决策指导",
            custom_decision_block,
        ])
        # 动作能力放在决策指导后面
        modules.extend([
            "",
            "## 4. 你能做的事",
            build_actions_module(available_actions),
            "",
            "## 5. 现在的情况",
            build_context_module(session, chat_stream, context_data),
            "",
            "## 6. 怎么回复",
            build_output_module(context_data),
        ])
    else:
        # 没有自定义决策时，动作能力直接跟在规则后面
        modules.extend([
            "",
            "## 3. 你能做的事",
            build_actions_module(available_actions),
            "",
            "## 4. 现在的情况",
            build_context_module(session, chat_stream, context_data),
            "",
            "## 5. 怎么回复",
            build_output_module(context_data),
        ])

    return "\n".join(modules)


# ============================================================
# User Prompt 模板（复刻旧版）
# ============================================================

RESPONDING_USER_PROMPT_TEMPLATE = """## 聊天记录
{narrative_history}

## 新消息
{incoming_messages}

---
看完这些消息，你想怎么回应？用 JSON 输出你的想法和决策。"""


TIMEOUT_DECISION_USER_PROMPT_TEMPLATE = """## 聊天记录
{narrative_history}

## 现在的情况
你发了消息，等了 {wait_duration_seconds:.0f} 秒（{wait_duration_minutes:.1f} 分钟），对方还没回。
你之前觉得对方可能会：{expected_user_reaction}
{followup_warning}
你发的最后一条消息是：「{last_bot_message}」

---
你拿起手机看了一眼，发现对方还没回复。你想怎么办？

**什么是正常的行为？**

真实的人在聊天时，不会因为对方没回复就一直追问。正常的节奏是这样的：
- 发了消息后，等一会儿看对方回不回
- 如果等了一段时间没回，可能会再发一条问一下
- 如果还是没回，就放下手机做自己的事，等收到回应再继续话题——这是完全正常的

**结束等待是正常的选择**。不是每次对话都需要有明确的"结束语"，也不是每次没收到回复都要追问。对方可能在忙、在休息、在做别的事，这些都很正常。给对方空间，有时间再聊，这才是真实的相处方式。

**决策参考：**

- **继续等待**：如果你问了一个问题，对方可能需要时间思考或打字，可以再等一会儿。
  - 动作：使用 `do_nothing`，设置合理的 `max_wait_seconds`

- **冒个泡问一下**：如果等了挺久了想确认一下，可以发条简短的消息。
  - 动作：使用 `kfc_reply`，内容简短自然即可

- **结束等待**：如果觉得话题已经聊完了，或者对方可能暂时没空，就自然地结束。
  - 动作：使用 `do_nothing`，将 `max_wait_seconds` 设为 0
  - 这是完全正常的选择，不需要有负担

**判断依据：**
- 你的最后一条消息是陈述句还是疑问句？陈述句的话，对方不一定需要回复
- 话题是不是已经聊得差不多了？如果是，结束等待很自然
- 对方是不是可能在忙？给对方一些空间是尊重的表现

用 JSON 输出你的想法和最终决策。"""


PROACTIVE_THINKING_USER_PROMPT_TEMPLATE = """## 聊天记录
{narrative_history}

## 现在的情况
现在是 {current_time}，距离你们上次聊天已经过了 {silence_duration}。
{relation_block}

{trigger_context}

---
你突然想起了对方。要不要联系一下？

说实话，不联系也完全没问题——不打扰也是一种温柔。
如果决定联系，想好说什么，要自然一点。

用 JSON 输出你的想法和决策。不想发消息就用 `do_nothing`。"""


# ============================================================
# 格式化历史记录
# ============================================================

def format_narrative_history(
    mental_log: list[MentalLogEntry],
    max_entries: int = 15,
) -> str:
    """
    将心理活动日志格式化为叙事历史

    Args:
        mental_log: 心理活动日志列表
        max_entries: 最大条目数

    Returns:
        str: 格式化的叙事历史文本
    """
    if not mental_log:
        return "（这是对话的开始，还没有历史记录）"

    # 获取最近的日志条目
    recent_entries = mental_log[-max_entries:]

    narrative_parts = []
    for entry in recent_entries:
        timestamp_str = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(entry.timestamp)
        )

        if entry.event_type == EventType.USER_MESSAGE:
            user_name = entry.user_name or "用户"
            narrative_parts.append(
                f"[{timestamp_str}] {user_name}说：{entry.content}"
            )
        elif entry.event_type == EventType.BOT_PLANNING:
            if entry.thought:
                narrative_parts.append(
                    f"[{timestamp_str}] （你的内心：{entry.thought}）"
                )
            # 格式化动作
            for action in entry.actions:
                action_type = action.get("type", "")
                if action_type == "kfc_reply" or action_type == "reply":
                    content = action.get("content", "")
                    if content:
                        narrative_parts.append(
                            f"[{timestamp_str}] 你回复：{content}"
                        )
        elif entry.event_type == EventType.WAITING_UPDATE:
            if entry.waiting_thought:
                narrative_parts.append(
                    f"[{timestamp_str}] （等待中的想法：{entry.waiting_thought}）"
                )

    return "\n".join(narrative_parts) if narrative_parts else "（这是对话的开始，还没有历史记录）"


def format_history_from_context(
    context: "StreamContext",
    mental_log: list[MentalLogEntry] | None = None,
) -> str:
    """
    从 StreamContext 的历史消息构建叙事历史

    这是实现"无缝融入"的关键：
    - 从同一个数据库读取历史消息（与AFC共享）
    - 遵循全局配置 [chat].max_context_size
    - 将消息串渲染成KFC的叙事体格式

    Args:
        context: 聊天流上下文，包含共享的历史消息
        mental_log: 可选的心理活动日志，用于补充内心独白

    Returns:
        str: 格式化的叙事历史文本
    """
    # 从 StreamContext 获取历史消息，遵循全局上下文长度配置
    max_context = 25  # 默认值
    if global_config and hasattr(global_config, "chat") and global_config.chat:
        max_context = getattr(global_config.chat, "max_context_size", 25)
    history_messages = context.get_messages(limit=max_context, include_unread=False)

    if not history_messages and not mental_log:
        return "（这是对话的开始，还没有历史记录）"

    # 获取Bot的用户ID用于判断消息来源
    bot_user_id = None
    if global_config and hasattr(global_config, "bot") and global_config.bot:
        bot_user_id = str(getattr(global_config.bot, "qq_account", ""))

    narrative_parts = []

    # 首先，将数据库历史消息转换为叙事格式
    for msg in history_messages:
        timestamp_str = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(msg.time or time.time())
        )

        # 判断是用户消息还是Bot消息
        msg_user_id = str(msg.user_info.user_id) if msg.user_info else ""
        is_bot_message = bot_user_id and msg_user_id == bot_user_id
        content = msg.processed_plain_text or msg.display_message or ""

        if is_bot_message:
            narrative_parts.append(f"[{timestamp_str}] 你回复：{content}")
        else:
            sender_name = msg.user_info.user_nickname if msg.user_info else "用户"
            narrative_parts.append(f"[{timestamp_str}] {sender_name}说：{content}")

    # 然后，补充 mental_log 中的内心独白（如果有）
    if mental_log:
        for entry in mental_log[-5:]:  # 只取最近5条心理活动
            timestamp_str = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(entry.timestamp)
            )

            if entry.event_type == EventType.BOT_PLANNING and entry.thought:
                narrative_parts.append(f"[{timestamp_str}] （你的内心：{entry.thought}）")

    return "\n".join(narrative_parts) if narrative_parts else "（这是对话的开始，还没有历史记录）"


def format_incoming_messages(
    message_content: str,
    sender_name: str,
    sender_id: str,
    message_time: float | None = None,
    all_unread_messages: list | None = None,
) -> str:
    """
    格式化收到的消息

    支持单条消息（兼容旧调用）和多条消息（打断合并场景）

    Args:
        message_content: 主消息内容
        sender_name: 发送者名称
        sender_id: 发送者ID
        message_time: 消息时间戳
        all_unread_messages: 所有未读消息列表

    Returns:
        str: 格式化的消息文本
    """
    if message_time is None:
        message_time = time.time()

    # 如果有多条消息，格式化为消息组
    if all_unread_messages and len(all_unread_messages) > 1:
        lines = [f"**用户连续发送了 {len(all_unread_messages)} 条消息：**\n"]

        for i, msg in enumerate(all_unread_messages, 1):
            msg_time = msg.time or time.time()
            msg_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg_time))
            msg_sender = msg.user_info.user_nickname if msg.user_info else sender_name
            msg_content = msg.processed_plain_text or msg.display_message or ""

            lines.append(f"[{i}] 来自：{msg_sender}")
            lines.append(f"    时间：{msg_time_str}")
            lines.append(f"    内容：{msg_content}")
            lines.append("")

        lines.append("**提示**：请综合理解这些消息的整体意图，不需要逐条回复。")
        return "\n".join(lines)

    # 单条消息（兼容旧格式）
    message_time_str = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(message_time)
    )
    return f"""来自：{sender_name}（用户ID: {sender_id}）
时间：{message_time_str}
内容：{message_content}"""
