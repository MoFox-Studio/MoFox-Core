"""
内存向量数据库备用实现

当可选后端不可用时使用的内存向量数据库。
实现测试所需的最小功能，无需外部依赖。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from collections import defaultdict

from .base import VectorDBBase, VectorDocument, QueryResult, CollectionInfo


class InMemoryVectorDB(VectorDBBase):
    """轻量级向量存储，用于真实后端缺失时的测试"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._collections: Dict[str, List[VectorDocument]] = defaultdict(list)
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        self.logger.info("InMemoryVectorDB 已初始化")

    async def close(self) -> None:
        self._collections.clear()
        self._initialized = False
        self.logger.info("InMemoryVectorDB 已关闭")

    async def create_collection(
        self,
        name: str,
        dimension: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        if name not in self._collections:
            self._collections[name] = []
        return True

    async def delete_collection(self, name: str) -> bool:
        self._collections.pop(name, None)
        return True

    async def list_collections(self) -> List[str]:
        return list(self._collections.keys())

    async def get_collection_info(self, name: str) -> Optional[CollectionInfo]:
        if name not in self._collections:
            return None
        return CollectionInfo(name=name, count=len(self._collections[name]), metadata={})

    async def collection_exists(self, name: str) -> bool:
        return name in self._collections

    async def add_documents(self, collection_name: str, documents: List[VectorDocument], **kwargs) -> bool:
        if collection_name not in self._collections:
            raise KeyError(f"Collection '{collection_name}' does not exist")
        existing = {doc.id: doc for doc in self._collections[collection_name]}
        for doc in documents:
            existing[doc.id] = doc
        self._collections[collection_name] = list(existing.values())
        return True

    async def update_documents(self, collection_name: str, documents: List[VectorDocument], **kwargs) -> bool:
        return await self.add_documents(collection_name, documents, **kwargs)

    async def delete_documents(self, collection_name: str, document_ids: List[str], **kwargs) -> bool:
        if collection_name not in self._collections:
            return False
        remaining = [doc for doc in self._collections[collection_name] if doc.id not in document_ids]
        self._collections[collection_name] = remaining
        return True

    async def query_similar(
        self,
        collection_name: str,
        query_vector: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List[QueryResult]:
        if collection_name not in self._collections:
            raise KeyError(f"Collection '{collection_name}' does not exist")
        if not query_vector:
            raise ValueError("query_vector is required for InMemoryVectorDB")
        docs = self._collections[collection_name]
        results: List[QueryResult] = []
        for doc in docs:
            score = 0.0
            if doc.vector and len(doc.vector) == len(query_vector):
                score = sum(a * b for a, b in zip(doc.vector, query_vector))
                denom = math.sqrt(sum(a * a for a in doc.vector)) * math.sqrt(sum(b * b for b in query_vector))
                if denom:
                    score /= denom
            results.append(
                QueryResult(
                    id=doc.id,
                    score=score,
                    content=doc.content,
                    metadata=doc.metadata,
                    vector=doc.vector,
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def batch_query_similar(
        self,
        collection_name: str,
        query_vectors: Optional[List[List[float]]] = None,
        query_texts: Optional[List[str]] = None,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List[List[QueryResult]]:
        if not query_vectors:
            raise ValueError("query_vectors is required for InMemoryVectorDB")
        results = []
        for qv in query_vectors:
            batch_result = await self.query_similar(
                collection_name=collection_name,
                query_vector=qv,
                top_k=top_k,
                filter_metadata=filter_metadata,
                **kwargs
            )
            results.append(batch_result)
        return results

    async def update_collection_metadata(self, name: str, metadata: Dict[str, Any]) -> bool:
        return True

    async def count_documents(self, collection_name: str) -> int:
        if collection_name not in self._collections:
            return 0
        return len(self._collections[collection_name])

    async def get_document(self, collection_name: str, document_id: str) -> Optional[VectorDocument]:
        if collection_name not in self._collections:
            return None
        for doc in self._collections[collection_name]:
            if doc.id == document_id:
                return doc
        return None

    async def get_documents(self, collection_name: str, document_ids: List[str]) -> List[VectorDocument]:
        if collection_name not in self._collections:
            return []
        return [doc for doc in self._collections[collection_name] if doc.id in document_ids]

    async def health_check(self) -> bool:
        return True


__all__ = ["InMemoryVectorDB"]
