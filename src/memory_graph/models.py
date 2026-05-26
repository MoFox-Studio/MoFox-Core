"""
记忆图系统核心数据模型

定义节点、边、记忆等核心数据结构（包含三层记忆系统）
使用 __slots__ 优化内存占用和属性访问性能
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np

# ============================================================================
# 三层记忆系统枚举
# ============================================================================


class MemoryTier(Enum):
    """记忆层级枚举"""

    PERCEPTUAL = "perceptual"  # 感知记忆层
    SHORT_TERM = "short_term"  # 短期记忆层
    LONG_TERM = "long_term"  # 长期记忆层


class GraphOperationType(Enum):
    """图操作类型枚举"""

    CREATE_NODE = "create_node"  # 创建节点
    UPDATE_NODE = "update_node"  # 更新节点
    DELETE_NODE = "delete_node"  # 删除节点
    MERGE_NODES = "merge_nodes"  # 合并节点
    CREATE_EDGE = "create_edge"  # 创建边
    UPDATE_EDGE = "update_edge"  # 更新边
    DELETE_EDGE = "delete_edge"  # 删除边
    CREATE_MEMORY = "create_memory"  # 创建记忆
    UPDATE_MEMORY = "update_memory"  # 更新记忆
    DELETE_MEMORY = "delete_memory"  # 删除记忆
    MERGE_MEMORIES = "merge_memories"  # 合并记忆

    @classmethod
    def _missing_(cls, value: Any):  # type: ignore[override]
        """
        在从原始数据重构时，允许进行不区分大小写/别名的查找。
        """
        if isinstance(value, str):
            normalized = value.strip().lower().replace("-", "_")
            for member in cls:
                if (
                    member.value == normalized
                    or member.name.lower() == normalized
                ):
                    return member
        return None


class ShortTermOperation(Enum):
    """短期记忆操作类型枚举"""

    MERGE = "merge"  # 合并到现有记忆
    UPDATE = "update"  # 更新现有记忆
    CREATE_NEW = "create_new"  # 创建新记忆
    DISCARD = "discard"  # 丢弃（低价值）
    KEEP_SEPARATE = "keep_separate"  # 保持独立（暂不合并）


# ============================================================================
# 图谱系统枚举
# ============================================================================


class NodeType(Enum):
    """节点类型枚举"""

    SUBJECT = "主体"  # 记忆的主语（我、小明、老师）
    TOPIC = "主题"  # 动作或状态（吃饭、情绪、学习）
    OBJECT = "客体"  # 宾语（白米饭、学校、书）
    ATTRIBUTE = "属性"  # 延伸属性（时间、地点、原因）
    VALUE = "值"  # 属性的具体值（2025-11-05、不开心）


class MemoryType(Enum):
    """记忆类型枚举"""

    EVENT = "事件"  # 有时间点的动作
    FACT = "事实"  # 相对稳定的状态
    RELATION = "关系"  # 人际关系
    OPINION = "观点"  # 主观评价


class EdgeType(Enum):
    """边类型枚举"""

    MEMORY_TYPE = "记忆类型"  # 主体 → 主题
    CORE_RELATION = "核心关系"  # 主题 → 客体（是/做/有）
    ATTRIBUTE = "属性关系"  # 任意节点 → 属性
    CAUSALITY = "因果关系"  # 记忆 → 记忆
    REFERENCE = "引用关系"  # 记忆 → 记忆（转述）
    RELATION = "关联关系"  # 记忆 → 记忆（自动关联发现的关系）


class MemoryStatus(Enum):
    """记忆状态枚举"""

    STAGED = "staged"  # 临时状态，未整理
    CONSOLIDATED = "consolidated"  # 已整理
    ARCHIVED = "archived"  # 已归档（低价值，很少访问）


@dataclass(slots=True)
class MemoryNode:
    """记忆节点"""

    id: str  # 节点唯一ID
    content: str  # 节点内容（如："我"、"吃饭"、"白米饭"）
    node_type: NodeType  # 节点类型
    embedding: np.ndarray | None = None  # 语义向量（仅主题/客体需要）
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展元数据
    has_vector: bool = False  # 是否已写入向量存储
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """后初始化处理"""
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        # 不序列化 embedding 数据，向量数据由专门的向量数据库管理
        return {
            "id": self.id,
            "content": self.content,
            "node_type": self.node_type.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "has_vector": self.has_vector,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryNode:
        """从字典创建节点"""
        # 不从 JSON 中读取 embedding 数据，向量数据由专门的向量数据库管理
        return cls(
            id=data["id"],
            content=data["content"],
            node_type=NodeType(data["node_type"]),
            embedding=None,  # 向量数据需要从向量数据库中单独加载
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            has_vector=data.get("has_vector", False),
        )

    def has_embedding(self) -> bool:
        """是否持有可用的语义向量数据"""
        return self.embedding is not None

    def mark_vector_stored(self) -> None:
        """标记该节点已写入向量存储，并清理内存中的 embedding 数据。"""
        self.has_vector = True
        self.embedding = None

    def __str__(self) -> str:
        return f"Node({self.node_type.value}: {self.content})"


@dataclass(slots=True)
class MemoryEdge:
    """记忆边（节点之间的关系）"""

    id: str  # 边唯一ID
    source_id: str  # 源节点ID
    target_id: str  # 目标节点ID（或目标记忆ID）
    relation: str  # 关系名称（如："是"、"做"、"时间"、"因为"）
    edge_type: EdgeType  # 边类型
    importance: float = 0.5  # 重要性 [0-1]
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展元数据
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """后初始化处理"""
        if not self.id:
            self.id = str(uuid.uuid4())
        # 确保重要性在有效范围内
        self.importance = max(0.0, min(1.0, self.importance))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "edge_type": self.edge_type.value,
            "importance": self.importance,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEdge:
        """从字典创建边"""
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation=data["relation"],
            edge_type=EdgeType(data["edge_type"]),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def __str__(self) -> str:
        return f"Edge({self.source_id} --{self.relation}--> {self.target_id})"


@dataclass(slots=True)
class Memory:
    """完整记忆（由节点和边组成的子图）"""

    id: str  # 记忆唯一ID
    subject_id: str  # 主体节点ID
    memory_type: MemoryType  # 记忆类型
    nodes: list[MemoryNode]  # 该记忆包含的所有节点
    edges: list[MemoryEdge]  # 该记忆包含的所有边
    importance: float = 0.5  # 整体重要性 [0-1]
    activation: float = 0.0  # 激活度 [0-1]，用于记忆整合和遗忘
    status: MemoryStatus = MemoryStatus.STAGED  # 记忆状态
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None  # 最近一次结构或元数据更新
    last_accessed: datetime = field(default_factory=datetime.now)  # 最后访问时间
    access_count: int = 0  # 访问次数
    decay_factor: float = 1.0  # 衰减因子（随时间变化）
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展元数据

    def __post_init__(self):
        """后初始化处理"""
        if not self.id:
            self.id = str(uuid.uuid4())
        # 确保重要性和激活度在有效范围内
        self.importance = max(0.0, min(1.0, self.importance))
        self.activation = max(0.0, min(1.0, self.activation))
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "memory_type": self.memory_type.value,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "importance": self.importance,
            "activation": self.activation,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "decay_factor": self.decay_factor,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Memory:
        """从字典创建记忆"""
        metadata = data.get("metadata", {})

        # 优先从 metadata 中获取激活度信息
        activation_level = 0.0
        activation_info = metadata.get("activation", {})
        if activation_info and "level" in activation_info:
            activation_level = activation_info["level"]
        else:
            # 备选：使用直接的 activation 字段
            activation_level = data.get("activation", 0.0)

        updated_at_raw = data.get("updated_at")
        if updated_at_raw:
            updated_at = datetime.fromisoformat(updated_at_raw)
        else:
            # 旧数据没有 updated_at，退化为最后访问时间或创建时间
            updated_at = datetime.fromisoformat(data.get("last_accessed", data["created_at"]))

        return cls(
            id=data["id"],
            subject_id=data["subject_id"],
            memory_type=MemoryType(data["memory_type"]),
            nodes=[MemoryNode.from_dict(n) for n in data["nodes"]],
            edges=[MemoryEdge.from_dict(e) for e in data["edges"]],
            importance=data.get("importance", 0.5),
            activation=activation_level,  # 使用统一的激活度值
            status=MemoryStatus(data.get("status", "staged")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=updated_at,
            last_accessed=datetime.fromisoformat(data.get("last_accessed", data["created_at"])),
            access_count=data.get("access_count", 0),
            decay_factor=data.get("decay_factor", 1.0),
            metadata=metadata,
        )

    def update_access(self) -> None:
        """更新访问记录"""
        self.last_accessed = datetime.now()
        self.access_count += 1

    def get_node_by_id(self, node_id: str) -> MemoryNode | None:
        """根据ID获取节点"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_subject_node(self) -> MemoryNode | None:
        """获取主体节点"""
        return self.get_node_by_id(self.subject_id)

    def to_text(self) -> str:
        """转换为文本描述（用于显示和LLM处理）"""
        subject_node = self.get_subject_node()
        if not subject_node:
            return f"[记忆 {self.id[:8]}]"

        # 简单的文本生成逻辑
        parts = [f"{subject_node.content}"]

        # 查找主题节点（通过记忆类型边连接）
        topic_node = None
        for edge in self.edges:
            if edge.edge_type == EdgeType.MEMORY_TYPE and edge.source_id == self.subject_id:
                topic_node = self.get_node_by_id(edge.target_id)
                break

        if topic_node:
            parts.append(topic_node.content)

            # 查找客体节点（通过核心关系边连接）
            for edge in self.edges:
                if edge.edge_type == EdgeType.CORE_RELATION and edge.source_id == topic_node.id:
                    obj_node = self.get_node_by_id(edge.target_id)
                    if obj_node:
                        parts.append(f"{edge.relation} {obj_node.content}")
                        break

        return " ".join(parts)

    def __str__(self) -> str:
        return f"Memory({self.memory_type.value}: {self.to_text()})"


@dataclass(slots=True)
class StagedMemory:
    """临时记忆（未整理状态）"""

    memory: Memory  # 原始记忆对象
    status: MemoryStatus = MemoryStatus.STAGED  # 状态
    created_at: datetime = field(default_factory=datetime.now)
    consolidated_at: datetime | None = None  # 整理时间
    merge_history: list[str] = field(default_factory=list)  # 被合并的节点ID列表

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "memory": self.memory.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "consolidated_at": self.consolidated_at.isoformat() if self.consolidated_at else None,
            "merge_history": self.merge_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StagedMemory:
        """从字典创建临时记忆"""
        return cls(
            memory=Memory.from_dict(data["memory"]),
            status=MemoryStatus(data.get("status", "staged")),
            created_at=datetime.fromisoformat(data["created_at"]),
            consolidated_at=datetime.fromisoformat(data["consolidated_at"]) if data.get("consolidated_at") else None,
            merge_history=data.get("merge_history", []),
        )


# ============================================================================
# 三层记忆系统数据模型
# ============================================================================


@dataclass(slots=True)
class MemoryBlock:
    """
    感知记忆块

    表示 n 条消息组成的一个语义单元，是感知记忆的基本单位。
    """

    id: str  # 记忆块唯一ID
    messages: list[dict[str, Any]]  # 原始消息列表（包含消息内容、发送者、时间等）
    combined_text: str  # 合并后的文本（用于生成向量）
    embedding: np.ndarray | None = None  # 整个块的向量表示
    created_at: datetime = field(default_factory=datetime.now)
    recall_count: int = 0  # 被召回次数（用于判断是否激活）
    last_recalled: datetime | None = None  # 最后一次被召回的时间
    position_in_stack: int = 0  # 在记忆堆中的位置（0=最顶层）
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def __post_init__(self):
        """后初始化处理"""
        if not self.id:
            self.id = f"block_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "messages": self.messages,
            "combined_text": self.combined_text,
            "created_at": self.created_at.isoformat(),
            "recall_count": self.recall_count,
            "last_recalled": self.last_recalled.isoformat() if self.last_recalled else None,
            "position_in_stack": self.position_in_stack,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryBlock:
        """从字典创建记忆块"""
        return cls(
            id=data["id"],
            messages=data["messages"],
            combined_text=data["combined_text"],
            embedding=None,  # 向量数据需要单独加载
            created_at=datetime.fromisoformat(data["created_at"]),
            recall_count=data.get("recall_count", 0),
            last_recalled=datetime.fromisoformat(data["last_recalled"]) if data.get("last_recalled") else None,
            position_in_stack=data.get("position_in_stack", 0),
            metadata=data.get("metadata", {}),
        )

    def increment_recall(self) -> None:
        """增加召回计数"""
        self.recall_count += 1
        self.last_recalled = datetime.now()

    def __str__(self) -> str:
        return f"MemoryBlock({self.id[:8]}, messages={len(self.messages)}, recalls={self.recall_count})"


@dataclass(slots=True)
class PerceptualMemory:
    """
    感知记忆（记忆堆的完整状态）

    全局单例，管理所有感知记忆块
    """

    blocks: list[MemoryBlock] = field(default_factory=list)  # 记忆块列表（有序，新的在前）
    max_blocks: int = 50  # 记忆堆最大容量
    block_size: int = 5  # 每个块包含的消息数量
    pending_messages: list[dict[str, Any]] = field(default_factory=list)  # 等待组块的消息缓存
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)  # 全局元数据

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "max_blocks": self.max_blocks,
            "block_size": self.block_size,
            "pending_messages": self.pending_messages,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerceptualMemory:
        """从字典创建感知记忆"""
        return cls(
            blocks=[MemoryBlock.from_dict(b) for b in data.get("blocks", [])],
            max_blocks=data.get("max_blocks", 50),
            block_size=data.get("block_size", 5),
            pending_messages=data.get("pending_messages", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class ShortTermMemory:
    """
    短期记忆

    结构化的活跃记忆，介于感知记忆和长期记忆之间。
    使用与长期记忆相同的 Memory 结构，但不包含图关系。
    """

    id: str  # 短期记忆唯一ID
    content: str  # 记忆的文本内容（LLM 结构化后的描述）
    embedding: np.ndarray | None = None  # 向量表示
    importance: float = 0.5  # 重要性评分 [0-1]
    source_block_ids: list[str] = field(default_factory=list)  # 来源感知记忆块ID列表
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0  # 访问次数
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据

    # 记忆结构化字段（与长期记忆 Memory 兼容）
    subject: str | None = None  # 主体
    topic: str | None = None  # 主题
    object: str | None = None  # 客体
    memory_type: str | None = None  # 记忆类型
    attributes: dict[str, str] = field(default_factory=dict)  # 属性

    def __post_init__(self):
        """后初始化处理"""
        if not self.id:
            self.id = f"stm_{uuid.uuid4().hex[:12]}"
        # 确保重要性在有效范围内
        self.importance = max(0.0, min(1.0, self.importance))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "content": self.content,
            "importance": self.importance,
            "source_block_ids": self.source_block_ids,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata,
            "subject": self.subject,
            "topic": self.topic,
            "object": self.object,
            "memory_type": self.memory_type,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShortTermMemory:
        """从字典创建短期记忆"""
        return cls(
            id=data["id"],
            content=data["content"],
            embedding=None,  # 向量数据需要单独加载
            importance=data.get("importance", 0.5),
            source_block_ids=data.get("source_block_ids", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data.get("last_accessed", data["created_at"])),
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
            subject=data.get("subject"),
            topic=data.get("topic"),
            object=data.get("object"),
            memory_type=data.get("memory_type"),
            attributes=data.get("attributes", {}),
        )

    def update_access(self) -> None:
        """更新访问记录"""
        self.last_accessed = datetime.now()
        self.access_count += 1

    def __str__(self) -> str:
        return f"ShortTermMemory({self.id[:8]}, content={self.content[:30]}..., importance={self.importance:.2f})"


@dataclass(slots=True)
class GraphOperation:
    """
    图操作指令

    表示一个对长期记忆图的原子操作，由 LLM 生成。
    """

    operation_type: GraphOperationType  # 操作类型
    target_id: str | None = None  # 目标对象ID（节点/边/记忆ID）
    target_ids: list[str] = field(default_factory=list)  # 多个目标ID（用于合并操作）
    parameters: dict[str, Any] = field(default_factory=dict)  # 操作参数
    reason: str = ""  # 操作原因（LLM 的推理过程）
    confidence: float = 1.0  # 操作置信度 [0-1]

    def __post_init__(self):
        """后初始化处理"""
        self.confidence = max(0.0, min(1.0, self.confidence))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "operation_type": self.operation_type.value,
            "target_id": self.target_id,
            "target_ids": self.target_ids,
            "parameters": self.parameters,
            "reason": self.reason,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphOperation:
        """从字典创建操作"""
        return cls(
            operation_type=GraphOperationType(data["operation_type"]),
            target_id=data.get("target_id"),
            target_ids=data.get("target_ids", []),
            parameters=data.get("parameters", {}),
            reason=data.get("reason", ""),
            confidence=data.get("confidence", 1.0),
        )

    def __str__(self) -> str:
        return f"GraphOperation({self.operation_type.value}, target={self.target_id}, confidence={self.confidence:.2f})"


@dataclass(slots=True)
class JudgeDecision:
    """
    裁判模型决策结果

    用于判断检索到的记忆是否充足
    """

    is_sufficient: bool  # 是否充足
    confidence: float = 0.5  # 置信度 [0-1]
    reasoning: str = ""  # 推理过程
    additional_queries: list[str] = field(default_factory=list)  # 额外需要检索的 query
    missing_aspects: list[str] = field(default_factory=list)  # 缺失的信息维度

    def __post_init__(self):
        """后初始化处理"""
        self.confidence = max(0.0, min(1.0, self.confidence))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "is_sufficient": self.is_sufficient,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "additional_queries": self.additional_queries,
            "missing_aspects": self.missing_aspects,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeDecision:
        """从字典创建决策"""
        return cls(
            is_sufficient=data["is_sufficient"],
            confidence=data.get("confidence", 0.5),
            reasoning=data.get("reasoning", ""),
            additional_queries=data.get("additional_queries", []),
            missing_aspects=data.get("missing_aspects", []),
        )

    def __str__(self) -> str:
        status = "充足" if self.is_sufficient else "不足"
        return f"JudgeDecision({status}, confidence={self.confidence:.2f}, extra_queries={len(self.additional_queries)})"


@dataclass(slots=True)
class ShortTermDecision:
    """
    短期记忆决策结果

    LLM 对新短期记忆的处理决策
    """

    operation: ShortTermOperation  # 操作类型
    target_memory_id: str | None = None  # 目标记忆ID（用于 MERGE/UPDATE）
    merged_content: str | None = None  # 合并后的内容
    reasoning: str = ""  # 推理过程
    confidence: float = 1.0  # 置信度 [0-1]
    updated_importance: float | None = None  # 更新后的重要性
    updated_metadata: dict[str, Any] = field(default_factory=dict)  # 更新后的元数据

    def __post_init__(self):
        """后初始化处理"""
        self.confidence = max(0.0, min(1.0, self.confidence))
        if self.updated_importance is not None:
            self.updated_importance = max(0.0, min(1.0, self.updated_importance))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "operation": self.operation.value,
            "target_memory_id": self.target_memory_id,
            "merged_content": self.merged_content,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "updated_importance": self.updated_importance,
            "updated_metadata": self.updated_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShortTermDecision:
        """从字典创建决策"""
        return cls(
            operation=ShortTermOperation(data["operation"]),
            target_memory_id=data.get("target_memory_id"),
            merged_content=data.get("merged_content"),
            reasoning=data.get("reasoning", ""),
            confidence=data.get("confidence", 1.0),
            updated_importance=data.get("updated_importance"),
            updated_metadata=data.get("updated_metadata", {}),
        )

    def __str__(self) -> str:
        return f"ShortTermDecision({self.operation.value}, target={self.target_memory_id}, confidence={self.confidence:.2f})"


# ============================================================================
# 统一配置
# ============================================================================


@dataclass
class MemoryConfig:
    """记忆系统总配置

    聚合三层记忆系统所有参数，单一数据源。
    通过 from_global_config() 从 TOML 配置构建。
    """

    # ---- 基础 ----
    enabled: bool = False
    data_dir: str = "data/memory_graph"

    # ---- 感知记忆层 ----
    perceptual_max_blocks: int = 50
    perceptual_block_size: int = 5
    perceptual_activation_threshold: int = 3
    perceptual_recall_top_k: int = 5
    perceptual_recall_threshold: float = 0.55

    # ---- 短期记忆层 ----
    short_term_max_memories: int = 30
    short_term_transfer_threshold: float = 0.6
    short_term_overflow_strategy: str = "transfer_all"
    short_term_enable_force_cleanup: bool = True
    short_term_cleanup_keep_ratio: float = 0.9

    # ---- 长期记忆层 ----
    long_term_batch_size: int = 10
    long_term_search_top_k: int = 5
    long_term_decay_factor: float = 0.95
    long_term_auto_transfer_interval: int = 600

    # ---- 智能检索 ----
    judge_confidence_threshold: float = 0.7

    # ---- 图存储 ----
    vector_collection_name: str = "memory_graph"
    search_top_k: int = 10
    search_similarity_threshold: float = 0.5
    path_expansion_max_hops: int = 2
    enable_path_expansion: bool = False

    @classmethod
    def from_global_config(cls) -> "MemoryConfig":
        """从 global_config.memory 构建 MemoryConfig"""
        try:
            from src.config.config import global_config
        except ImportError:
            return cls()

        cfg = global_config.memory if global_config and global_config.memory else None
        if cfg is None:
            return cls()

        storage_cfg = getattr(cfg, "storage", None)
        return cls(
            enabled=getattr(cfg, "enable", False),
            data_dir=getattr(cfg, "data_dir", "data/memory_graph"),
            perceptual_max_blocks=getattr(cfg, "perceptual_max_blocks", 50),
            perceptual_block_size=getattr(cfg, "perceptual_block_size", 5),
            perceptual_activation_threshold=getattr(cfg, "perceptual_activation_threshold", 3),
            perceptual_recall_top_k=getattr(cfg, "perceptual_topk", 5),
            perceptual_recall_threshold=getattr(cfg, "perceptual_similarity_threshold", 0.55),
            short_term_max_memories=getattr(cfg, "short_term_max_memories", 30),
            short_term_transfer_threshold=getattr(cfg, "short_term_transfer_threshold", 0.6),
            short_term_overflow_strategy=getattr(cfg, "short_term_overflow_strategy", "transfer_all"),
            short_term_enable_force_cleanup=getattr(cfg, "short_term_enable_force_cleanup", True),
            short_term_cleanup_keep_ratio=getattr(cfg, "short_term_cleanup_keep_ratio", 0.9),
            long_term_batch_size=getattr(cfg, "long_term_batch_size", 10),
            long_term_search_top_k=getattr(cfg, "search_top_k", 5),
            long_term_decay_factor=getattr(cfg, "long_term_decay_factor", 0.95),
            long_term_auto_transfer_interval=getattr(cfg, "long_term_auto_transfer_interval", 600),
            judge_confidence_threshold=getattr(cfg, "judge_confidence_threshold", 0.7),
            vector_collection_name=getattr(storage_cfg, "vector_collection_name", "memory_graph") if storage_cfg else "memory_graph",
            search_top_k=getattr(cfg, "search_top_k", 10),
            search_similarity_threshold=getattr(cfg, "search_similarity_threshold", 0.5),
            path_expansion_max_hops=getattr(cfg, "path_expansion_max_hops", 2),
            enable_path_expansion=getattr(cfg, "enable_path_expansion", False),
        )

    def to_perceptual_kwargs(self) -> dict:
        """提取感知记忆层初始化参数"""
        return {
            "max_blocks": self.perceptual_max_blocks,
            "block_size": self.perceptual_block_size,
            "activation_threshold": self.perceptual_activation_threshold,
            "recall_top_k": self.perceptual_recall_top_k,
            "recall_similarity_threshold": self.perceptual_recall_threshold,
        }

    def to_short_term_kwargs(self) -> dict:
        """提取短期记忆层初始化参数"""
        return {
            "max_memories": self.short_term_max_memories,
            "transfer_importance_threshold": self.short_term_transfer_threshold,
            "overflow_strategy": self.short_term_overflow_strategy,
            "enable_force_cleanup": self.short_term_enable_force_cleanup,
            "cleanup_keep_ratio": self.short_term_cleanup_keep_ratio,
        }

    def to_long_term_kwargs(self) -> dict:
        """提取长期记忆层初始化参数"""
        return {
            "batch_size": self.long_term_batch_size,
            "search_top_k": self.long_term_search_top_k,
            "long_term_decay_factor": self.long_term_decay_factor,
        }
