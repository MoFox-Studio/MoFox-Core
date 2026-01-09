"""
图存储层：基于 NetworkX 的图结构管理
"""

from __future__ import annotations

from collections.abc import Iterable

import networkx as nx

from src.common.logger import get_logger
from src.memory_graph.models import EdgeType, Memory, MemoryEdge

logger = get_logger(__name__)


class GraphStore:
    """
    图存储封装类

    负责：
    1. 记忆图的构建和维护
    2. 节点和边的快速查询
    3. 图遍历算法（BFS/DFS）
    4. 邻接关系查询
    """

    def __init__(self):
        """初始化图存储"""
        # 使用有向图（记忆关系通常是有向的）
        self.graph = nx.DiGraph()

        # 索引：记忆ID -> 记忆对象
        self.memory_index: dict[str, Memory] = {}

        # 索引：节点ID -> 所属记忆ID集合
        self.node_to_memories: dict[str, set[str]] = {}

        # 节点 -> {memory_id: [MemoryEdge]}，用于快速获取邻接边
        self.node_edge_index: dict[str, dict[str, list[MemoryEdge]]] = {}

    def _register_memory_edges(self, memory: Memory) -> None:
        """在记忆中的边加入邻接索引"""
        for edge in memory.edges:
            self._register_edge_reference(memory.id, edge)

    def _register_edge_reference(self, memory_id: str, edge: MemoryEdge) -> None:
        """在节点邻接索引中登记一条边"""
        for node_id in (edge.source_id, edge.target_id):
            node_edges = self.node_edge_index.setdefault(node_id, {})
            edge_list = node_edges.setdefault(memory_id, [])
            if not any(existing.id == edge.id for existing in edge_list):
                edge_list.append(edge)

    def _unregister_memory_edges(self, memory: Memory) -> None:
        """从节点邻接索引中移除记忆相关的边"""
        for edge in memory.edges:
            self._unregister_edge_reference(memory.id, edge)

    def _unregister_edge_reference(self, memory_id: str, edge: MemoryEdge) -> None:
        """在节点邻接索引中删除一条边"""
        for node_id in (edge.source_id, edge.target_id):
            node_edges = self.node_edge_index.get(node_id)
            if not node_edges:
                continue
            if memory_id not in node_edges:
                continue
            node_edges[memory_id] = [e for e in node_edges[memory_id] if e.id != edge.id]
            if not node_edges[memory_id]:
                del node_edges[memory_id]
            if not node_edges:
                del self.node_edge_index[node_id]

    def _rebuild_node_edge_index(self) -> None:
        """重建节点邻接索引"""
        self.node_edge_index.clear()
        for memory in self.memory_index.values():
            self._register_memory_edges(memory)

    def add_memory(self, memory: Memory) -> None:
        """
        添加记忆到图

        Args:
            memory: 要添加的记忆
        """
        try:
            # 1. 添加所有节点到图
            for node in memory.nodes:
                if not self.graph.has_node(node.id):
                    self.graph.add_node(
                        node.id,
                        content=node.content,
                        node_type=node.node_type.value,
                        created_at=node.created_at.isoformat(),
                        metadata=node.metadata,
                        has_vector=node.has_vector,
                    )

                # 更新节点到记忆的映射
                if node.id not in self.node_to_memories:
                    self.node_to_memories[node.id] = set()
                self.node_to_memories[node.id].add(memory.id)

            # 2. 添加所有边到图
            for edge in memory.edges:
                self.graph.add_edge(
                    edge.source_id,
                    edge.target_id,
                    edge_id=edge.id,
                    relation=edge.relation,
                    edge_type=edge.edge_type.value,
                    importance=edge.importance,
                    metadata=edge.metadata,
                    created_at=edge.created_at.isoformat(),
                )

            # 3. 保存记忆对象
            self.memory_index[memory.id] = memory

            # 4. 注册记忆中的边到邻接索引
            self._register_memory_edges(memory)

            logger.debug(f"添加记忆到图: {memory}")

        except Exception as e:
            logger.error(f"添加记忆失败: {e}")
            raise

    def add_node(
        self,
        node_id: str,
        content: str,
        node_type: str,
        memory_id: str,
        metadata: dict | None = None,
    ) -> bool:
        """
        添加单个节点到图和指定记忆

        Args:
            node_id: 节点ID
            content: 节点内容
            node_type: 节点类型
            memory_id: 所属记忆ID
            metadata: 元数据

        Returns:
            是否添加成功
        """
        try:
            # 1. 检查记忆是否存在
            if memory_id not in self.memory_index:
                logger.warning(f"添加节点失败: 记忆不存在 {memory_id}")
                return False

            memory = self.memory_index[memory_id]

            # 1.5. 注销记忆中的边的邻接索引记录
            self._unregister_memory_edges(memory)

            # 2. 添加节点到图
            if not self.graph.has_node(node_id):
                from datetime import datetime
                self.graph.add_node(
                    node_id,
                    content=content,
                    node_type=node_type,
                    created_at=datetime.now().isoformat(),
                    metadata=metadata or {},
                    has_vector=(metadata or {}).get("has_vector", False),
                )
            else:
                # 如果节点已存在，更新内容（可选）
                pass

            # 3. 更新节点到记忆的映射
            if node_id not in self.node_to_memories:
                self.node_to_memories[node_id] = set()
            self.node_to_memories[node_id].add(memory_id)

            # 4. 更新记忆对象的 nodes 列表
            # 检查是否已在列表中
            if not any(n.id == node_id for n in memory.nodes):
                from src.memory_graph.models import MemoryNode, NodeType
                # 尝试转换 node_type 字符串为枚举
                try:
                    node_type_enum = NodeType(node_type)
                except ValueError:
                    node_type_enum = NodeType.OBJECT # 默认

                new_node = MemoryNode(
                    id=node_id,
                    content=content,
                    node_type=node_type_enum,
                    metadata=metadata or {},
                    has_vector=(metadata or {}).get("has_vector", False)
                )
                memory.nodes.append(new_node)

            # 5. 重新注册记忆中的边到邻接索引
            self._register_memory_edges(memory)

            logger.debug(f"添加节点成功: {node_id} -> {memory_id}")
            return True

        except Exception as e:
            logger.error(f"添加节点失败: {e}")
            return False

    def update_node(
        self,
        node_id: str,
        content: str | None = None,
        metadata: dict | None = None
    ) -> bool:
        """
        更新节点信息

        Args:
            node_id: 节点ID
            content: 新内容
            metadata: 要更新的元数据

        Returns:
            是否更新成功
        """
        if not self.graph.has_node(node_id):
            logger.warning(f"更新节点失败: 节点不存在 {node_id}")
            return False

        try:
            # 更新图中的节点数据
            if content is not None:
                self.graph.nodes[node_id]["content"] = content

            if metadata:
                if "metadata" not in self.graph.nodes[node_id]:
                    self.graph.nodes[node_id]["metadata"] = {}
                self.graph.nodes[node_id]["metadata"].update(metadata)

            # 同步更新所有相关记忆中的节点对象
            if node_id in self.node_to_memories:
                for mem_id in self.node_to_memories[node_id]:
                    memory = self.memory_index.get(mem_id)
                    if memory:
                        for node in memory.nodes:
                            if node.id == node_id:
                                if content is not None:
                                    node.content = content
                                if metadata:
                                    node.metadata.update(metadata)
                                break

            return True
        except Exception as e:
            logger.error(f"更新节点失败: {e}")
            return False

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        edge_type: str,
        importance: float = 0.5,
        metadata: dict | None = None,
    ) -> str | None:
        """
        添加边到图

        Args:
            source_id: 源节点ID
            target_id: 目标节点ID
            relation: 关系描述
            edge_type: 边类型
            importance: 重要性
            metadata: 元数据

        Returns:
            新边的ID，失败返回 None
        """
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            logger.warning(f"添加边失败: 节点不存在 ({source_id}, {target_id})")
            return None

        try:
            import uuid
            from datetime import datetime

            from src.memory_graph.models import EdgeType, MemoryEdge

            edge_id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()

            # 1. 添加到图
            self.graph.add_edge(
                source_id,
                target_id,
                edge_id=edge_id,
                relation=relation,
                edge_type=edge_type,
                importance=importance,
                metadata=metadata or {},
                created_at=created_at,
            )

            # 2. 同步到相关记忆
            # 找到包含源节点或目标节点的记忆
            related_memory_ids = set()
            if source_id in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[source_id])
            if target_id in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[target_id])

            # 尝试转换 edge_type
            try:
                edge_type_enum = EdgeType(edge_type)
            except ValueError:
                edge_type_enum = EdgeType.RELATION

            new_edge = MemoryEdge(
                id=edge_id,
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                edge_type=edge_type_enum,
                importance=importance,
                metadata=metadata or {}
            )

            for mem_id in related_memory_ids:
                memory = self.memory_index.get(mem_id)
                if memory:
                    memory.edges.append(new_edge)
                    self._register_edge_reference(mem_id, new_edge)

            logger.debug(f"添加边成功: {source_id} -> {target_id} ({relation})")
            return edge_id

        except Exception as e:
            logger.error(f"添加边失败: {e}")
            return None

    def update_edge(
        self,
        edge_id: str,
        relation: str | None = None,
        importance: float | None = None
    ) -> bool:
        """
        更新边信息

        Args:
            edge_id: 边ID
            relation: 新关系描述
            importance: 新重要性

        Returns:
            是否更新成功
        """
        # NetworkX 的边是通过 (u, v) 索引的，没有直接的 edge_id 索引
        # 需要遍历查找（或者维护一个 edge_id -> (u, v) 的映射，这里简化处理）
        target_edge = None
        source_node = None
        target_node = None

        for u, v, data in self.graph.edges(data=True):
            if data.get("edge_id") == edge_id or data.get("id") == edge_id:
                target_edge = data
                source_node = u
                target_node = v
                break

        if not target_edge:
            logger.warning(f"更新边失败: 边不存在 {edge_id}")
            return False

        try:
            # 更新图数据
            if relation is not None:
                self.graph[source_node][target_node]["relation"] = relation
            if importance is not None:
                self.graph[source_node][target_node]["importance"] = importance

            # 同步更新记忆中的边对象
            related_memory_ids = set()
            if source_node in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[source_node])
            if target_node in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[target_node])

            for mem_id in related_memory_ids:
                memory = self.memory_index.get(mem_id)
                if memory:
                    for edge in memory.edges:
                        if edge.id == edge_id:
                            if relation is not None:
                                edge.relation = relation
                            if importance is not None:
                                edge.importance = importance
                            break

            return True
        except Exception as e:
            logger.error(f"更新边失败: {e}")
            return False

    def remove_edge(self, edge_id: str) -> bool:
        """
        删除边

        Args:
            edge_id: 边ID

        Returns:
            是否删除成功
        """
        target_edge = None
        source_node = None
        target_node = None

        for u, v, data in self.graph.edges(data=True):
            if data.get("edge_id") == edge_id or data.get("id") == edge_id:
                target_edge = data
                source_node = u
                target_node = v
                break

        if not target_edge:
            logger.warning(f"删除边失败: 边不存在 {edge_id}")
            return False

        try:
            # 从图中删除
            self.graph.remove_edge(source_node, target_node)

            # 从相关记忆中删除
            related_memory_ids = set()
            if source_node in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[source_node])
            if target_node in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[target_node])

            for mem_id in related_memory_ids:
                memory = self.memory_index.get(mem_id)
                if memory:
                    removed_edges = [e for e in memory.edges if e.id == edge_id]
                    if removed_edges:
                        for edge_obj in removed_edges:
                            self._unregister_edge_reference(mem_id, edge_obj)
                    memory.edges = [e for e in memory.edges if e.id != edge_id]

            return True
        except Exception as e:
            logger.error(f"删除边失败: {e}")
            return False

    def merge_memories(self, target_memory_id: str, source_memory_ids: list[str]) -> bool:
        """
        合并多个记忆到目标记忆

        将源记忆的所有节点和边转移到目标记忆，然后删除源记忆。

        Args:
            target_memory_id: 目标记忆ID
            source_memory_ids: 源记忆ID列表

        Returns:
            是否合并成功
        """
        if target_memory_id not in self.memory_index:
            logger.error(f"合并失败: 目标记忆不存在 {target_memory_id}")
            return False

        target_memory = self.memory_index[target_memory_id]

        try:
            for source_id in source_memory_ids:
                if source_id not in self.memory_index:
                    continue

                source_memory = self.memory_index[source_id]

                # 1. 转移节点
                for node in source_memory.nodes:
                    # 更新映射
                    if node.id in self.node_to_memories:
                        self.node_to_memories[node.id].discard(source_id)
                        self.node_to_memories[node.id].add(target_memory_id)

                    # 添加到目标记忆（如果不存在）
                    if not any(n.id == node.id for n in target_memory.nodes):
                        target_memory.nodes.append(node)

                # 2. 转移边
                for edge in source_memory.edges:
                    # 添加到目标记忆（如果不存在）
                    already_exists = any(e.id == edge.id for e in target_memory.edges)
                    self._unregister_edge_reference(source_id, edge)
                    if not already_exists:
                        target_memory.edges.append(edge)
                        self._register_edge_reference(target_memory_id, edge)

                # 3. 删除源记忆（不清理孤立节点，因为节点已转移）
                del self.memory_index[source_id]

            logger.info(f"成功合并记忆: {source_memory_ids} -> {target_memory_id}")
            return True

        except Exception as e:
            logger.error(f"合并记忆失败: {e}")
            return False

    def get_memory_by_id(self, memory_id: str) -> Memory | None:
        """
        根据ID获取记忆

        Args:
            memory_id: 记忆ID

        Returns:
            记忆对象或 None
        """
        return self.memory_index.get(memory_id)

    def get_memories_by_ids(self, memory_ids: Iterable[str]) -> dict[str, Memory]:
        """
        根据一组ID批量获取记忆

        Args:
            memory_ids: 记忆ID集合

        Returns:
            {memory_id: Memory} 映射
        """
        result: dict[str, Memory] = {}
        missing_ids: list[str] = []

        # dict.fromkeys 可以保持参数序列的原始顺序同时帮忙去重
        for mem_id in dict.fromkeys(memory_ids):
            memory = self.memory_index.get(mem_id)
            if memory is not None:
                result[mem_id] = memory
            else:
                missing_ids.append(mem_id)

        if missing_ids:
            logger.debug(f"批量获取记忆: 未找到 {missing_ids}")

        return result

    def get_all_memories(self) -> list[Memory]:
        """
        获取所有记忆

        Returns:
            所有记忆的列表
        """
        return list(self.memory_index.values())

    def get_memories_by_node(self, node_id: str) -> list[Memory]:
        """
        获取包含指定节点的所有记忆

        Args:
            node_id: 节点ID

        Returns:
            记忆列表
        """
        if node_id not in self.node_to_memories:
            return []

        memory_ids = self.node_to_memories[node_id]
        return [self.memory_index[mid] for mid in memory_ids if mid in self.memory_index]

    def get_edges_for_node(self, node_id: str) -> list[MemoryEdge]:
        """
        获取节点相关的全部边（包含入边和出边）

        Args:
            node_id: 节点ID

        Returns:
            MemoryEdge 列表
        """
        node_edges = self.node_edge_index.get(node_id)
        if not node_edges:
            return []

        unique_edges: dict[str | tuple[str, str, str, str], MemoryEdge] = {}
        for edges in node_edges.values():
            for edge in edges:
                key: str | tuple[str, str, str, str]
                if edge.id:
                    key = edge.id
                else:
                    key = (edge.source_id, edge.target_id, edge.relation, edge.edge_type.value)
                unique_edges[key] = edge

        return list(unique_edges.values())

    def get_edges_from_node(self, node_id: str, relation_types: list[str] | None = None) -> list[dict]:
        """
        获取从指定节点出发的所有边

        Args:
            node_id: 源节点ID
            relation_types: 关系类型过滤（可选）

        Returns:
            边信息列表
        """
        if not self.graph.has_node(node_id):
            return []

        edges = []
        for _, target_id, edge_data in self.graph.out_edges(node_id, data=True):
            # 过滤关系类型
            if relation_types and edge_data.get("relation") not in relation_types:
                continue

            edges.append(
                {
                    "source_id": node_id,
                    "target_id": target_id,
                    "relation": edge_data.get("relation"),
                    "edge_type": edge_data.get("edge_type"),
                    "importance": edge_data.get("importance", 0.5),
                    **edge_data,
                }
            )

        return edges

    def get_neighbors(
        self, node_id: str, direction: str = "out", relation_types: list[str] | None = None
    ) -> list[tuple[str, dict]]:
        """
        获取节点的邻居节点

        Args:
            node_id: 节点ID
            direction: 方向 ("out"=出边, "in"=入边, "both"=双向)
            relation_types: 关系类型过滤

        Returns:
            List of (neighbor_id, edge_data)
        """
        if not self.graph.has_node(node_id):
            return []

        neighbors = []

        # 处理出边
        if direction in ["out", "both"]:
            for _, target_id, edge_data in self.graph.out_edges(node_id, data=True):
                if not relation_types or edge_data.get("relation") in relation_types:
                    neighbors.append((target_id, edge_data))

        # 处理入边
        if direction in ["in", "both"]:
            for source_id, _, edge_data in self.graph.in_edges(node_id, data=True):
                if not relation_types or edge_data.get("relation") in relation_types:
                    neighbors.append((source_id, edge_data))

        return neighbors

    def find_path(self, source_id: str, target_id: str, max_length: int | None = None) -> list[str] | None:
        """
        查找两个节点之间的最短路径

        Args:
            source_id: 源节点ID
            target_id: 目标节点ID
            max_length: 最大路径长度（可选）

        Returns:
            路径节点ID列表，或 None（如果不存在路径）
        """
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            return None

        try:
            if max_length:
                # 使用 cutoff 限制路径长度
                path = nx.shortest_path(self.graph, source_id, target_id, weight=None)
                if len(path) - 1 <= max_length:  # 边数 = 节点数 - 1
                    return path
                return None
            else:
                return nx.shortest_path(self.graph, source_id, target_id, weight=None)

        except nx.NetworkXNoPath:
            return None
        except Exception as e:
            logger.error(f"查找路径失败: {e}")
            return None

    def bfs_expand(
        self,
        start_nodes: list[str],
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> set[str]:
        """
        从起始节点进行广度优先搜索扩展

        Args:
            start_nodes: 起始节点ID列表
            depth: 扩展深度
            relation_types: 关系类型过滤

        Returns:
            扩展到的所有节点ID集合
        """
        visited = set()
        queue = [(node_id, 0) for node_id in start_nodes if self.graph.has_node(node_id)]

        while queue:
            current_node, current_depth = queue.pop(0)

            if current_node in visited:
                continue
            visited.add(current_node)

            if current_depth >= depth:
                continue

            # 获取邻居并加入队列
            neighbors = self.get_neighbors(current_node, direction="out", relation_types=relation_types)
            for neighbor_id, _ in neighbors:
                if neighbor_id not in visited:
                    queue.append((neighbor_id, current_depth + 1))

        return visited

    def get_subgraph(self, node_ids: list[str]) -> nx.DiGraph:
        """
        获取包含指定节点的子图

        Args:
            node_ids: 节点ID列表

        Returns:
            NetworkX 子图
        """
        return self.graph.subgraph(node_ids).copy()

    def merge_nodes(self, source_id: str, target_id: str) -> None:
        """
        合并两个节点（将source的所有边转移到target，然后删除source）

        Args:
            source_id: 源节点ID（将被删除）
            target_id: 目标节点ID（保留）
        """
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            logger.warning(f"合并节点失败: 节点不存在 ({source_id}, {target_id})")
            return

        try:
            # 1. 转移入边
            for pred, _, edge_data in self.graph.in_edges(source_id, data=True):
                if pred != target_id:  # 避免自环
                    self.graph.add_edge(pred, target_id, **edge_data)

            # 2. 转移出边
            for _, succ, edge_data in self.graph.out_edges(source_id, data=True):
                if succ != target_id:  # 避免自环
                    self.graph.add_edge(target_id, succ, **edge_data)

            # 3. 更新节点到记忆的映射
            if source_id in self.node_to_memories:
                memory_ids = self.node_to_memories[source_id]
                if target_id not in self.node_to_memories:
                    self.node_to_memories[target_id] = set()
                self.node_to_memories[target_id].update(memory_ids)
                del self.node_to_memories[source_id]

            # 4. 删除源节点
            self.graph.remove_node(source_id)

            logger.debug(f"节点合并: {source_id} → {target_id}")

        except Exception as e:
            logger.error(f"合并节点失败: {e}")
            raise

    def get_node_degree(self, node_id: str) -> tuple[int, int]:
        """
        获取节点的度数

        Args:
            node_id: 节点ID

        Returns:
            (in_degree, out_degree)
        """
        if not self.graph.has_node(node_id):
            return (0, 0)

        return (self.graph.in_degree(node_id), self.graph.out_degree(node_id))

    def get_statistics(self) -> dict[str, int]:
        """获取图的统计信息"""
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "total_memories": len(self.memory_index),
            "connected_components": nx.number_weakly_connected_components(self.graph),
        }

    def to_dict(self) -> dict:
        """
        将图转换为字典（用于持久化）

        Returns:
            图的字典表示
        """
        return {
            "nodes": [
                {"id": node_id, **self.graph.nodes[node_id]} for node_id in self.graph.nodes()
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    **data,
                }
                for u, v, data in self.graph.edges(data=True)
            ],
            "memories": {memory_id: memory.to_dict() for memory_id, memory in self.memory_index.items()},
            "node_to_memories": {node_id: list(mem_ids) for node_id, mem_ids in self.node_to_memories.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> GraphStore:
        """
        从字典加载图

        Args:
            data: 图的字典表示

        Returns:
            GraphStore 实例
        """
        store = cls()

        # 1. 加载节点
        for node_data in data.get("nodes", []):
            node_id = node_data.pop("id")
            store.graph.add_node(node_id, **node_data)

        # 2. 加载边
        for edge_data in data.get("edges", []):
            source = edge_data.pop("source")
            target = edge_data.pop("target")
            store.graph.add_edge(source, target, **edge_data)

        # 3. 加载记忆
        for memory_id, memory_dict in data.get("memories", {}).items():
            store.memory_index[memory_id] = Memory.from_dict(memory_dict)

        # 4. 加载节点到记忆的映射
        for node_id, mem_ids in data.get("node_to_memories", {}).items():
            store.node_to_memories[node_id] = set(mem_ids)

        # 5. 同步图中的边到 Memory.edges（保证内存对象和图一致）
        try:
            store._sync_memory_edges_from_graph()
        except Exception:
            logger.exception("同步图边到记忆.edges 失败")

        store._rebuild_node_edge_index()
        return store

    def _sync_memory_edges_from_graph(self) -> None:
        """
        将 NetworkX 图中的边重建为 MemoryEdge 并注入到对应的 Memory.edges 列表中。

        目的：当从持久化数据加载时，确保 memory_index 中的 Memory 对象的
        edges 列表反映图中实际存在的边（避免只有图中存在而 memory.edges 为空的不同步情况）。

        规则：对于图中每条边(u, v, data)，会尝试将该边注入到所有包含 u 或 v 的记忆中（避免遗漏跨记忆边）。
        已存在的边（通过 edge.id 检查）将不会重复添加。
        """

        # 构建快速查重索引：memory_id -> set(edge_id)
        existing_edges = {mid: {e.id for e in mem.edges} for mid, mem in self.memory_index.items()}

        for u, v, data in self.graph.edges(data=True):
            # 兼容旧数据：edge_id 可能在 data 中，或叫 id
            edge_id = data.get("edge_id") or data.get("id") or ""

            edge_dict = {
                "id": edge_id or "",
                "source_id": u,
                "target_id": v,
                "relation": data.get("relation", ""),
                "edge_type": data.get("edge_type", data.get("edge_type", "")),
                "importance": data.get("importance", 0.5),
                "metadata": data.get("metadata", {}),
                "created_at": data.get("created_at", "1970-01-01T00:00:00"),
            }

            # 找到相关记忆（包含源或目标节点）
            related_memory_ids = set()
            if u in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[u])
            if v in self.node_to_memories:
                related_memory_ids.update(self.node_to_memories[v])

            for mid in related_memory_ids:
                mem = self.memory_index.get(mid)
                if mem is None:
                    continue

                # 检查是否已存在
                if edge_dict["id"] and edge_dict["id"] in existing_edges.get(mid, set()):
                    continue

                try:
                    # 使用 MemoryEdge.from_dict 构建对象
                    mem_edge = MemoryEdge.from_dict(edge_dict)
                except Exception:
                    # 兼容性：直接构造对象
                    # 确保 edge_type 是 EdgeType 枚举
                    edge_type_value = edge_dict["edge_type"]
                    if isinstance(edge_type_value, str):
                        try:
                            edge_type_enum = EdgeType(edge_type_value)
                        except ValueError:
                            logger.warning(f"未知的边类型: {edge_type_value}, 使用默认值")
                            edge_type_enum = EdgeType.RELATION
                    else:
                        edge_type_enum = edge_type_value

                    mem_edge = MemoryEdge(
                        id=edge_dict["id"] or "",
                        source_id=edge_dict["source_id"],
                        target_id=edge_dict["target_id"],
                        relation=edge_dict["relation"],
                        edge_type=edge_type_enum,
                        importance=edge_dict.get("importance", 0.5),
                        metadata=edge_dict.get("metadata", {}),
                    )

                mem.edges.append(mem_edge)
                existing_edges.setdefault(mid, set()).add(mem_edge.id)
        self._rebuild_node_edge_index()

    def remove_memory(self, memory_id: str, cleanup_orphans: bool = True) -> bool:
        """
        从图中删除指定记忆

        Args:
            memory_id: 要删除的记忆ID
            cleanup_orphans: 是否立即清理孤立节点（默认True，批量删除时设为False）

        Returns:
            是否删除成功
        """
        try:
            # 1. 检查记忆是否存在
            if memory_id not in self.memory_index:
                logger.warning(f"记忆不存在，无法删除: {memory_id}")
                return False

            memory = self.memory_index[memory_id]

            # 2. 从节点映射中移除此记忆
            for node in memory.nodes:
                if node.id in self.node_to_memories:
                    self.node_to_memories[node.id].discard(memory_id)

                    # 可选：立即清理孤立节点
                    if cleanup_orphans:
                        # 如果该节点不再属于任何记忆，从图中移除节点
                        if not self.node_to_memories[node.id]:
                            if self.graph.has_node(node.id):
                                self.graph.remove_node(node.id)
                            del self.node_to_memories[node.id]

            # 3. 从记忆索引中移除
            del self.memory_index[memory_id]

            logger.debug(f"成功删除记忆: {memory_id}")
            return True

        except Exception as e:
            logger.error(f"删除记忆失败 {memory_id}: {e}")
            return False

    def clear(self) -> None:
        """清空图（危险操作，仅用于测试）"""
        self.graph.clear()
        self.memory_index.clear()
        self.node_to_memories.clear()
        self.node_edge_index.clear()
        logger.warning("图存储已清空")
