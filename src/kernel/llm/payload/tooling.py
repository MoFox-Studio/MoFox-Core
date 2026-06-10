"""工具调用相关类型定义。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .content import Content


@runtime_checkable
class LLMUsable(Protocol):
    @classmethod
    def to_schema(cls) -> dict[str, Any]:
        """将组件描述为可被 LLM 调用的 schema。"""
        ...


class LLMUsableExecutionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass
class LLMUsableExecution:
    status: LLMUsableExecutionStatus
    result: Any = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ToolCall(Content):
    id: str | None
    name: str
    args: dict[str, Any] | str


@dataclass(frozen=True, slots=True)
class ToolResult(Content):
    """工具执行结果。"""

    value: Any
    call_id: str | None = None
    name: str | None = None

    def to_text(self) -> str:
        if isinstance(self.value, str):
            return self.value
        try:
            return json.dumps(self.value, ensure_ascii=False)
        except Exception:
            return str(self.value)


class ToolRegistry:
    """工具注册表，支持动态注册和发现工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, type[LLMUsable]] = {}
        self._aliases: dict[str, str] = {}

    def register(self, tool: type[LLMUsable], alias: str | None = None) -> None:
        name = alias or self._get_tool_name(tool)
        if not name:
            raise ValueError(f"无法确定工具名称：{tool}")
        self._tools[name] = tool
        if alias and alias != name:
            self._aliases[alias] = name

    def get(self, name: str) -> type[LLMUsable] | None:
        resolved = self._aliases.get(name, name)
        return self._tools.get(resolved)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        resolved = self._aliases.get(name, name)
        return resolved in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    @staticmethod
    def _get_tool_name(tool: type[LLMUsable]) -> str:
        schema = tool.to_schema()
        if isinstance(schema, dict) and "name" in schema:
            return str(schema["name"])
        name_attr = getattr(tool, "__tool_name__", None)
        if name_attr:
            return str(name_attr)
        return tool.__name__
