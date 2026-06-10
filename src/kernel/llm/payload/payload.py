"""LLMPayload 数据类定义。"""

from __future__ import annotations

from dataclasses import dataclass

from ..roles import ROLE
from .content import Content
from .tooling import LLMUsable


def _normalize_content(content: Content | LLMUsable | list[Content | LLMUsable]) -> list[Content | LLMUsable]:
    """规范化内容输入，确保 content 字段始终是一个列表。"""
    if isinstance(content, list):
        return content
    return [content]


@dataclass(slots=True)
class LLMPayload:
    role: ROLE
    content: list[Content | LLMUsable]

    def __init__(self, role: ROLE, content: Content | LLMUsable | list[Content | LLMUsable]):
        self.role = role
        self.content = _normalize_content(content)
