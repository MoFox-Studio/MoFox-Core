"""
记忆构建器：自动构造记忆子图
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

from src.common.logger import get_logger
from src.memory_graph.models import (
    EdgeType,
    Memory,
    MemoryEdge,
    MemoryNode,
    MemoryStatus,
    NodeType,
)
from src.memory_graph.storage.graph_store import GraphStore
from src.memory_graph.storage.vector_store import VectorStore

logger = get_logger(__name__)


class MemoryBuilder:
    """
    记忆构建器

    负责：
    1. 根据提取的元素自动构造记忆子图
    2. 创建节点和边的完整结构
    3. 生成语义嵌入向量
    4. 检查并复用已存在的相似节点
    5. 构造符合层级结构的记忆对象
    """

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        embedding_generator: Any | None = None,
    ):
        """
        初始化记忆构建器

        Args:
            vector_store: 向量存储
            graph_store: 图存储
            embedding_generator: 嵌入向量生成器（可选）
        """
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.embedding_generator = embedding_generator

    async def build_memory(self, extracted_params: dict[str, Any]) -> Memory:
        """
        构建完整的记忆对象

        Args:
            extracted_params: 提取器返回的标准化参数

        Returns:
            Memory 对象（状态为 STAGED）
        """
        try:
            nodes = []
            edges = []
            memory_id = self._generate_memory_id()

            # 1. 创建主体节点 (SUBJECT)
            subject_node = await self._create_or_reuse_node(
                content=extracted_params["subject"],
                node_type=NodeType.SUBJECT,
                memory_id=memory_id,
            )
            nodes.append(subject_node)

            # 2. 创建主题节点 (TOPIC) - 需要嵌入向量
            topic_node = await self._create_topic_node(
                content=extracted_params["topic"], memory_id=memory_id
            )
            nodes.append(topic_node)

            # 3. 连接主体 -> 记忆类型 -> 主题
            memory_type_edge = MemoryEdge(
                id=self._generate_edge_id(),
                source_id=subject_node.id,
                target_id=topic_node.id,
                relation=extracted_params["memory_type"].value,
                edge_type=EdgeType.MEMORY_TYPE,
                importance=extracted_params["importance"],
                metadata={"memory_id": memory_id},
            )
            edges.append(memory_type_edge)

            # 4. 如果有客体，创建客体节点并连接
            if extracted_params.get("object"):
                object_node = await self._create_object_node(
                    content=extracted_params["object"], memory_id=memory_id
                )
                nodes.append(object_node)

                # 连接主题 -> 核心关系 -> 客体
                core_relation_edge = MemoryEdge(
                    id=self._generate_edge_id(),
                    source_id=topic_node.id,
                    target_id=object_node.id,
                    relation="核心关系",  # 默认关系名
                    edge_type=EdgeType.CORE_RELATION,
                    importance=extracted_params["importance"],
                    metadata={"memory_id": memory_id},
                )
                edges.append(core_relation_edge)

            # 5. 处理属性
            if extracted_params.get("attributes"):
                attr_nodes, attr_edges = await self._process_attributes(
                    attributes=extracted_params["attributes"],
                    parent_id=topic_node.id,
                    memory_id=memory_id,
                    importance=extracted_params["importance"],
                )
                nodes.extend(attr_nodes)
                edges.extend(attr_edges)

            # 6. 构建 Memory 对象
            # 新记忆应该有较高的初始激活度
            initial_activation = 0.75  # 新记忆初始激活度为 0.75

            memory = Memory(
                id=memory_id,
                subject_id=subject_node.id,
                memory_type=extracted_params["memory_type"],
                nodes=nodes,
                edges=edges,
                importance=extracted_params["importance"],
                activation=initial_activation,  # 设置较高的初始激活度
                created_at=extracted_params["timestamp"],
                last_accessed=extracted_params["timestamp"],
                access_count=0,
                status=MemoryStatus.STAGED,
                metadata={
                    "subject": extracted_params["subject"],
                    "topic": extracted_params["topic"],
                    "activation": {
                        "level": initial_activation,
                        "last_access": extracted_params["timestamp"].isoformat(),
                        "access_count": 0,
                        "created_at": extracted_params["timestamp"].isoformat(),
                    },
                },
            )

            # 降低非必要日志级别
            logger.debug(
                f"构建记忆成功: {memory_id} - {len(nodes)} 节点, {len(edges)} 边"
            )
            return memory

        except Exception as e:
            logger.error(f"记忆构建失败: {e}")
            raise RuntimeError(f"记忆构建失败: {e}")

    async def _create_or_reuse_node(
        self, content: str, node_type: NodeType, memory_id: str
    ) -> MemoryNode:
        """
        创建新节点或复用已存在的相似节点

        对于主体(SUBJECT)和属性(ATTRIBUTE)，检查是否已存在相同内容的节点

        Args:
            content: 节点内容
            node_type: 节点类型
            memory_id: 所属记忆ID

        Returns:
            MemoryNode 对象
        """
        # 对于主体，尝试查找已存在的节点
        if node_type == NodeType.SUBJECT:
            existing = await self._find_existing_node(content, node_type)
            if existing:
                logger.debug(f"复用已存在的主体节点: {existing.id}")
                return existing

        # 为主体和值节点生成嵌入向量（用于人名/实体和重要描述检索）
        embedding = None
        if node_type in (NodeType.SUBJECT, NodeType.VALUE):
            # 只为有足够内容的节点生成嵌入（避免浪费）
            if len(content.strip()) >= 2:
                embedding = await self._generate_embedding(content)

        # 创建新节点
        node = MemoryNode(
            id=self._generate_node_id(),
            content=content,
            node_type=node_type,
            embedding=embedding,  # 主体、值需要嵌入，属性不需要
            metadata={"memory_ids": [memory_id]},
        )

        return node

    async def _create_topic_node(self, content: str, memory_id: str) -> MemoryNode:
        """
        创建主题节点（需要生成嵌入向量）

        Args:
            content: 节点内容
            memory_id: 所属记忆ID

        Returns:
            MemoryNode 对象
        """
        # 生成嵌入向量
        embedding = await self._generate_embedding(content)

        # 检查是否存在高度相似的节点
        existing = await self._find_similar_topic(content, embedding)
        if existing:
            logger.debug(f"复用相似的主题节点: {existing.id}")
            # 添加当前记忆ID到元数据
            if "memory_ids" not in existing.metadata:
                existing.metadata["memory_ids"] = []
            existing.metadata["memory_ids"].append(memory_id)
            return existing

        # 创建新节点
        node = MemoryNode(
            id=self._generate_node_id(),
            content=content,
            node_type=NodeType.TOPIC,
            embedding=embedding,
            metadata={"memory_ids": [memory_id]},
        )

        return node

    async def _create_object_node(self, content: str, memory_id: str) -> MemoryNode:
        """
        创建客体节点（需要生成嵌入向量）

        Args:
            content: 节点内容
            memory_id: 所属记忆ID

        Returns:
            MemoryNode 对象
        """
        # 生成嵌入向量
        embedding = await self._generate_embedding(content)

        # 检查是否存在高度相似的节点
        existing = await self._find_similar_object(content, embedding)
        if existing:
            logger.debug(f"复用相似的客体节点: {existing.id}")
            if "memory_ids" not in existing.metadata:
                existing.metadata["memory_ids"] = []
            existing.metadata["memory_ids"].append(memory_id)
            return existing

        # 创建新节点
        node = MemoryNode(
            id=self._generate_node_id(),
            content=content,
            node_type=NodeType.OBJECT,
            embedding=embedding,
            metadata={"memory_ids": [memory_id]},
        )

        return node

    async def _process_attributes(
        self,
        attributes: dict[str, Any],
        parent_id: str,
        memory_id: str,
        importance: float,
    ) -> tuple[list[MemoryNode], list[MemoryEdge]]:
        """
        处理属性，构建属性子图

        结构：TOPIC -> ATTRIBUTE -> VALUE

        Args:
            attributes: 属性字典
            parent_id: 父节点ID（通常是TOPIC）
            memory_id: 所属记忆ID
            importance: 重要性

        Returns:
            (属性节点列表, 属性边列表)
        """
        nodes = []
        edges = []

        for attr_name, attr_value in attributes.items():
            # 创建属性节点
            attr_node = await self._create_or_reuse_node(
                content=attr_name, node_type=NodeType.ATTRIBUTE, memory_id=memory_id
            )
            nodes.append(attr_node)

            # 连接父节点 -> 属性
            attr_edge = MemoryEdge(
                id=self._generate_edge_id(),
                source_id=parent_id,
                target_id=attr_node.id,
                relation="属性",
                edge_type=EdgeType.ATTRIBUTE,
                importance=importance * 0.8,  # 属性的重要性略低
                metadata={"memory_id": memory_id},
            )
            edges.append(attr_edge)

            # 创建值节点
            value_node = await self._create_or_reuse_node(
                content=str(attr_value), node_type=NodeType.VALUE, memory_id=memory_id
            )
            nodes.append(value_node)

            # 连接属性 -> 值
            value_edge = MemoryEdge(
                id=self._generate_edge_id(),
                source_id=attr_node.id,
                target_id=value_node.id,
                relation="值",
                edge_type=EdgeType.ATTRIBUTE,
                importance=importance * 0.8,
                metadata={"memory_id": memory_id},
            )
            edges.append(value_edge)

        return nodes, edges

    async def _generate_embedding(self, text: str) -> np.ndarray | None:
        """
        生成文本的嵌入向量

        Args:
            text: 文本内容

        Returns:
            嵌入向量，失败时返回 None
        """
        if self.embedding_generator:
            try:
                embedding = await self.embedding_generator.generate(text)
                return embedding
            except Exception as e:
                logger.warning(f"嵌入生成失败，跳过: {e}")

        # 嵌入生成失败，返回 None
        return None

    async def _find_existing_node(
        self, content: str, node_type: NodeType
    ) -> MemoryNode | None:
        """
        查找已存在的完全匹配节点（用于主体和属性）

        Args:
            content: 节点内容
            node_type: 节点类型

        Returns:
            已存在的节点，如果没有则返回 None
        """
        # 在图存储中查找
        for node_id in self.graph_store.graph.nodes():
            node_data = self.graph_store.graph.nodes[node_id]
            if node_data.get("content") == content and node_data.get("node_type") == node_type.value:
                # 重建 MemoryNode 对象（embedding 数据从向量数据库单独获取）
                return MemoryNode(
                    id=node_id,
                    content=node_data["content"],
                    node_type=NodeType(node_data["node_type"]),
                    embedding=None,  # 图存储不包含 embedding，需要从向量数据库获取
                    metadata=node_data.get("metadata", {}),
                    has_vector=node_data.get("has_vector", False),
                )

        return None

    async def _find_similar_topic(
        self, content: str, embedding: np.ndarray | None
    ) -> MemoryNode | None:
        """
        查找相似的主题节点（基于语义相似度）

        Args:
            content: 内容
            embedding: 嵌入向量

        Returns:
            相似节点，如果没有则返回 None
        """
        # 如果嵌入为空，无法进行相似性搜索
        if embedding is None:
            logger.debug("嵌入向量为空，跳过相似节点搜索")
            return None

        try:
            # 搜索相似节点（阈值 0.95）
            similar_nodes = await self.vector_store.search_similar_nodes(
                query_embedding=embedding,
                limit=1,
                node_types=[NodeType.TOPIC],
                min_similarity=0.95,
            )

            if similar_nodes and similar_nodes[0][1] >= 0.95:
                node_id, similarity, metadata = similar_nodes[0]
                logger.debug(
                    f"找到相似主题节点: {metadata.get('content', '')} (相似度: {similarity:.3f})"
                )
                # 从图存储中获取完整节点
                if node_id in self.graph_store.graph.nodes:
                    node_data = self.graph_store.graph.nodes[node_id]
                    existing_node = MemoryNode(
                        id=node_id,
                        content=node_data["content"],
                        node_type=NodeType(node_data["node_type"]),
                        embedding=None,  # 图存储不包含 embedding，需要从向量数据库获取
                        metadata=node_data.get("metadata", {}),
                        has_vector=node_data.get("has_vector", False),
                    )
                    # 添加当前记忆ID到元数据
                    return existing_node

        except Exception as e:
            logger.warning(f"相似节点搜索失败: {e}")

        return None

    async def _find_similar_object(
        self, content: str, embedding: np.ndarray | None
    ) -> MemoryNode | None:
        """
        查找相似的客体节点（基于语义相似度）

        Args:
            content: 内容
            embedding: 嵌入向量

        Returns:
            相似节点，如果没有则返回 None
        """
        # 如果嵌入为空，无法进行相似性搜索
        if embedding is None:
            logger.debug("嵌入向量为空，跳过相似节点搜索")
            return None

        try:
            # 搜索相似节点（阈值 0.95）
            similar_nodes = await self.vector_store.search_similar_nodes(
                query_embedding=embedding,
                limit=1,
                node_types=[NodeType.OBJECT],
                min_similarity=0.95,
            )

            if similar_nodes and similar_nodes[0][1] >= 0.95:
                node_id, similarity, metadata = similar_nodes[0]
                logger.debug(
                    f"找到相似客体节点: {metadata.get('content', '')} (相似度: {similarity:.3f})"
                )
                # 从图存储中获取完整节点
                if node_id in self.graph_store.graph.nodes:
                    node_data = self.graph_store.graph.nodes[node_id]
                    existing_node = MemoryNode(
                        id=node_id,
                        content=node_data["content"],
                        node_type=NodeType(node_data["node_type"]),
                        embedding=None,  # 图存储不包含 embedding，需要从向量数据库获取
                        metadata=node_data.get("metadata", {}),
                        has_vector=node_data.get("has_vector", False),
                    )
                    return existing_node

        except Exception as e:
            logger.warning(f"相似节点搜索失败: {e}")

        return None

    def _generate_memory_id(self) -> str:
        """生成记忆ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"mem_{timestamp}"

    def _generate_node_id(self) -> str:
        """生成节点ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"node_{timestamp}"

    def _generate_edge_id(self) -> str:
        """生成边ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"edge_{timestamp}"

    async def link_memories(
        self,
        source_memory: Memory,
        target_memory: Memory,
        relation_type: str,
        importance: float = 0.6,
    ) -> MemoryEdge:
        """
        关联两个记忆（创建因果或引用边）

        Args:
            source_memory: 源记忆
            target_memory: 目标记忆
            relation_type: 关系类型（如 "导致", "引用"）
            importance: 重要性

        Returns:
            创建的边
        """
        try:
            # 获取两个记忆的主题节点（作为连接点）
            source_topic = self._find_topic_node(source_memory)
            target_topic = self._find_topic_node(target_memory)

            if not source_topic or not target_topic:
                raise ValueError("无法找到记忆的主题节点")

            # 确定边的类型
            edge_type = self._determine_edge_type(relation_type)

            # 创建边
            edge_id = f"edge_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            edge = MemoryEdge(
                id=edge_id,
                source_id=source_topic.id,
                target_id=target_topic.id,
                relation=relation_type,
                edge_type=edge_type,
                importance=importance,
                metadata={
                    "source_memory_id": source_memory.id,
                    "target_memory_id": target_memory.id,
                },
            )

            logger.info(
                f"关联记忆: {source_memory.id} --{relation_type}--> {target_memory.id}"
            )
            return edge

        except Exception as e:
            logger.error(f"记忆关联失败: {e}")
            raise RuntimeError(f"记忆关联失败: {e}")

    def _find_topic_node(self, memory: Memory) -> MemoryNode | None:
        """查找记忆中的主题节点"""
        for node in memory.nodes:
            if node.node_type == NodeType.TOPIC:
                return node
        return None

    def _determine_edge_type(self, relation_type: str) -> EdgeType:
        """根据关系类型确定边的类型"""
        causality_keywords = ["导致", "引起", "造成", "因为", "所以"]
        reference_keywords = ["引用", "基于", "关于", "参考"]

        for keyword in causality_keywords:
            if keyword in relation_type:
                return EdgeType.CAUSALITY

        for keyword in reference_keywords:
            if keyword in relation_type:
                return EdgeType.REFERENCE

        # 默认为引用类型
        return EdgeType.REFERENCE
