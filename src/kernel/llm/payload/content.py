"""LLM payload content 类型定义。"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BufferedIOBase, RawIOBase
from os import PathLike
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True, slots=True)
class Content:
    """Payload content 基类。"""


def _normalize_file_to_base64(
    source: str | "PathLike[str]" | BinaryIO,
) -> str:
    """将文件路径、文件对象或 base64 字符串统一规范化为纯 base64 字符串。"""
    if isinstance(source, (RawIOBase, BufferedIOBase)):
        try:
            data = source.read()
            if isinstance(data, str):
                data = data.encode("utf-8")
            return base64.b64encode(data).decode("utf-8")
        except Exception:
            raise ValueError("无法读取文件对象内容") from None

    if not isinstance(source, str):
        raise TypeError(
            f"File 不支持的输入类型：{type(source).__name__}。"
            f"请传入文件路径（str/Path）、文件对象（BinaryIO）或 base64 字符串。"
        )

    s = source

    # 处理 data: URL
    if s.startswith("data:") and ";base64," in s:
        return s.split(";base64,", 1)[1]

    # 处理 base64| 前缀
    if s.startswith("base64|"):
        return s[len("base64|"):]

    # 优先尝试验证是否为纯 base64 字符串
    try:
        cleaned = s.replace("\n", "").replace("\r", "").replace(" ", "")
        base64.b64decode(cleaned, validate=True)
        return cleaned
    except Exception:
        pass

    # 尝试作为文件路径处理
    path = Path(s)
    try:
        if path.exists() and path.is_file():
            return base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        raise ValueError(
            f"无法识别的 File 输入：既不是有效的文件路径，也不是合法的 base64 字符串。"
            f"收到：{s!r}"
        ) from None

    raise ValueError(
        f"无法识别的 File 输入：既不是有效的文件路径，也不是合法的 base64 字符串。"
        f"收到：{s!r}"
    )


class File(Content):
    """文件内容。接受文件路径、文件对象或 base64 字符串，统一规范化为 pure base64。"""

    __slots__ = ("value",)

    value: str

    def __init__(
        self,
        source: str | "PathLike[str]" | BinaryIO,
    ) -> None:
        normalized = _normalize_file_to_base64(source)
        object.__setattr__(self, "value", normalized)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("File 实例是不可变的，不允许修改属性。")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("File 实例是不可变的，不允许删除属性。")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, File):
            return self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        preview = self.value[:16] + "..." if len(self.value) > 16 else self.value
        return f"File(value={preview!r})"


@dataclass(frozen=True, slots=True)
class Text(Content):
    """文本内容。"""

    text: str


@dataclass(frozen=True, slots=True)
class ReasoningText(Content):
    """思维链/推理内容。"""

    text: str
    signature: str | None = None
    redacted_data: str | None = None


class Image(File):
    """图片内容，继承自 File。"""

    def __repr__(self) -> str:
        preview = self.value[:16] + "..." if len(self.value) > 16 else self.value
        return f"Image(value={preview!r})"


class Audio(File):
    """音频内容，继承自 File。"""

    def __repr__(self) -> str:
        preview = self.value[:16] + "..." if len(self.value) > 16 else self.value
        return f"Audio(value={preview!r})"


class Video(File):
    """视频内容，继承自 File，支持 MIME 类型。"""

    __slots__ = ("mime_type", "value")

    mime_type: str

    def __init__(
        self,
        source: str | "PathLike[str]" | BinaryIO,
        mime_type: str = "video/mp4",
    ) -> None:
        if isinstance(source, str) and source.startswith("data:") and ";base64," in source:
            extracted = source.split(";", 1)[0][len("data:"):]
            if extracted:
                mime_type = extracted
        super().__init__(source)
        object.__setattr__(self, "mime_type", mime_type)

    def __repr__(self) -> str:
        preview = self.value[:16] + "..." if len(self.value) > 16 else self.value
        return f"Video(mime_type={self.mime_type!r}, value={preview!r})"
