"""
定义了 LLM 对话中的角色枚举，包括系统、用户、助手以及工具相关的角色。
这些角色用于区分对话中的不同参与者和功能，帮助模型理解和处理对话内容。
"""

from __future__ import annotations

from enum import Enum


class ROLE(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

    # 声明可用工具（函数）列表；不是模型对话角色。
    TOOL = "tool"

    # 工具执行结果回传给模型。
    TOOL_RESULT = "tool_result"
