"""LLM 模块类型定义

提供 LLM 模块使用的类型别名和 TypedDict 定义。
"""

from enum import Enum
from typing import Any, TypeAlias, TypedDict


class RequestType(str, Enum):
    """LLM 请求类型。"""

    COMPLETIONS = "completions"
    EMBEDDINGS = "embeddings"
    RERANK = "rerank"


class ModelEntry(TypedDict, total=True):
    """模型配置条目

    定义单个 LLM 模型的完整配置信息。
    """

    api_provider: str
    base_url: str
    model_identifier: str
    api_key: str
    client_type: str
    max_retry: int
    timeout: float
    retry_interval: float
    price_in: float
    cache_hit_price_in: float
    price_out: float
    temperature: float
    max_tokens: int
    max_context: int
    tool_call_compat: bool
    extra_params: dict[str, Any]


# 模型集合类型：一组可用的模型配置
ModelSet: TypeAlias = list[ModelEntry]


__all__ = [
    "ModelEntry",
    "ModelSet",
    "RequestType",
]
