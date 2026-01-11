"""
ChromaDB 向量数据库实现

基于 ChromaDB 的向量数据库具体实现
"""

import asyncio
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
from pathlib import Path

# 在运行时尝试导入 chromadb，可选依赖
try:
    import chromadb  # type: ignore
    from chromadb.config import Settings  # type: ignore
    from chromadb.api.models.Collection import Collection  # type: ignore
    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None  # type: ignore
    Settings = Any  # type: ignore
    Collection = Any  # type: ignore
    CHROMADB_AVAILABLE = False

from .base import (
    VectorDBBase,
    VectorDocument,
    QueryResult,
    CollectionInfo
)


class ChromaDBImpl(VectorDBBase):
    """ChromaDB 向量数据库实现
    
    配置参数：
        - persist_directory: 持久化目录路径（可选）
        - client_type: 客户端类型 ('persistent', 'ephemeral', 'http') 默认 'persistent'
        - host: HTTP客户端的主机地址（仅client_type='http'时使用）
        - port: HTTP客户端的端口（仅client_type='http'时使用）
        - embedding_function: 自定义嵌入函数（可选）
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化 ChromaDB 客户端
        
        Args:
            config: 配置字典
        """
        if chromadb is None:
            raise ImportError(
                "ChromaDB is not installed. "
                "Please install it with: pip install chromadb"
            )
        
        super().__init__(config)
        self._client: Any = None
        self._collections_cache: Dict[str, Any] = {}
        self.logger.info(f"初始化 ChromaDB 实例，配置: {config}")
        
    async def initialize(self) -> None:
        """初始化数据库连接"""
        client_type = self.config.get('client_type', 'persistent')
        self.logger.info(f"开始初始化 ChromaDB 连接，客户端类型: {client_type}")
        
        try:
            if client_type == 'http':
                # HTTP 客户端
                host = self.config.get('host', 'localhost')
                port = self.config.get('port', 8000)
                self._client = chromadb.HttpClient(  # type: ignore[attr-defined]
                    host=host,
                    port=port
                )
            elif client_type == 'ephemeral':
                # 临时客户端（仅内存）
                self._client = chromadb.EphemeralClient()  # type: ignore[attr-defined]
            else:
                # 持久化客户端（默认）
                persist_dir = self.config.get('persist_directory')
                if persist_dir:
                    persist_path = Path(persist_dir)
                    persist_path.mkdir(parents=True, exist_ok=True)
                    settings = Settings(  # type: ignore[assignment]
                        persist_directory=str(persist_path),
                        anonymized_telemetry=False
                    )
                    self._client = chromadb.PersistentClient(  # type: ignore[attr-defined]
                        path=str(persist_path),
                        settings=settings
                    )
                else:
                    self._client = chromadb.PersistentClient()  # type: ignore[attr-defined]
            
            self.logger.info(f"ChromaDB 连接初始化成功，客户端类型: {client_type}")
                    
        except Exception as e:
            self.logger.error(f"ChromaDB 连接初始化失败: {e}")
            raise ConnectionError(f"Failed to initialize ChromaDB: {e}")
    
    async def close(self) -> None:
        """关闭数据库连接"""
        self.logger.info("关闭 ChromaDB 连接")
        self._collections_cache.clear()
        # ChromaDB 不需要显式关闭
        self._client = None
        self.logger.debug("ChromaDB 连接已关闭")
    
    def _ensure_client(self):
        """确保客户端已初始化"""
        if self._client is None:
            raise RuntimeError("ChromaDB client not initialized. Call initialize() first.")
    
    def _get_embedding_function(self):
        """获取嵌入函数"""
        return self.config.get('embedding_function')
    
    # ==================== 集合操作 ====================
    
    async def create_collection(
        self,
        name: str,
        dimension: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """创建集合"""
        self._ensure_client()
        
        try:
            # 在事件循环中运行同步操作
            def _create():
                embedding_function = self._get_embedding_function()
                collection = self._client.create_collection(
                    name=name,
                    metadata=metadata,
                    embedding_function=embedding_function
                )
                self._collections_cache[name] = collection
                self.logger.info(f"创建集合成功: {name}")
                return True
            
            return await asyncio.to_thread(_create)
        except Exception as e:
            if "already exists" in str(e).lower():
                self.logger.warning(f"集合已存在: {name}")
                return False
            self.logger.error(f"创建集合失败 '{name}': {e}")
            raise ValueError(f"Failed to create collection '{name}': {e}")
    
    async def delete_collection(self, name: str) -> bool:
        """删除集合"""
        self._ensure_client()
        
        try:
            def _delete():
                self._client.delete_collection(name=name)
                self._collections_cache.pop(name, None)
                self.logger.info(f"删除集合成功: {name}")
                return True
            
            return await asyncio.to_thread(_delete)
        except Exception as e:
            self.logger.warning(f"删除集合失败 '{name}': {e}")
            return False
    
    async def list_collections(self) -> List[str]:
        """列出所有集合名称"""
        self._ensure_client()
        
        def _list():
            collections = self._client.list_collections()
            return [col.name for col in collections]
        
        return await asyncio.to_thread(_list)
    
    async def get_collection_info(self, name: str) -> Optional[CollectionInfo]:
        """获取集合信息"""
        self._ensure_client()
        
        try:
            def _get_info():
                collection = self._get_or_load_collection(name)
                count = collection.count()
                metadata = collection.metadata
                
                return CollectionInfo(
                    name=name,
                    count=count,
                    metadata=metadata
                )
            
            return await asyncio.to_thread(_get_info)
        except Exception:
            return None
    
    async def collection_exists(self, name: str) -> bool:
        """检查集合是否存在"""
        collections = await self.list_collections()
        return name in collections
    
    def _get_or_load_collection(self, name: str) -> Any:
        """获取或加载集合（同步方法）"""
        if name not in self._collections_cache:
            embedding_function = self._get_embedding_function()
            collection = self._client.get_collection(
                name=name,
                embedding_function=embedding_function
            )
            self._collections_cache[name] = collection
        return self._collections_cache[name]
    
    # ==================== 文档操作 ====================
    
    async def add_documents(
        self,
        collection_name: str,
        documents: List[VectorDocument],
        **kwargs
    ) -> bool:
        """添加文档到集合"""
        self._ensure_client()
        
        if not documents:
            return True
        
        try:
            def _add():
                collection = self._get_or_load_collection(collection_name)
                
                # 准备数据
                ids = [doc.id for doc in documents]
                embeddings = [doc.vector for doc in documents if doc.vector]
                texts = [doc.content for doc in documents if doc.content]
                metadatas = [doc.metadata for doc in documents if doc.metadata]
                
                # 根据数据构建参数
                add_kwargs: Dict[str, Any] = {'ids': ids}
                if embeddings and len(embeddings) == len(documents):
                    add_kwargs['embeddings'] = embeddings
                if texts and len(texts) == len(documents):
                    add_kwargs['documents'] = texts
                if metadatas and len(metadatas) == len(documents):
                    add_kwargs['metadatas'] = metadatas
                
                collection.add(**add_kwargs)
                self.logger.info(f"添加 {len(documents)} 个文档到集合 '{collection_name}'")
                return True
            
            return await asyncio.to_thread(_add)
        except Exception as e:
            self.logger.error(f"添加文档失败 '{collection_name}': {e}")
            raise ValueError(f"Failed to add documents to '{collection_name}': {e}")
    
    async def update_documents(
        self,
        collection_name: str,
        documents: List[VectorDocument],
        **kwargs
    ) -> bool:
        """更新集合中的文档"""
        self._ensure_client()
        
        if not documents:
            return True
        
        try:
            def _update():
                collection = self._get_or_load_collection(collection_name)
                
                # 准备数据
                ids = [doc.id for doc in documents]
                embeddings = [doc.vector for doc in documents if doc.vector]
                texts = [doc.content for doc in documents if doc.content]
                metadatas = [doc.metadata for doc in documents if doc.metadata]
                
                # 根据数据构建参数
                update_kwargs: Dict[str, Any] = {'ids': ids}
                if embeddings and len(embeddings) == len(documents):
                    update_kwargs['embeddings'] = embeddings
                if texts and len(texts) == len(documents):
                    update_kwargs['documents'] = texts
                if metadatas and len(metadatas) == len(documents):
                    update_kwargs['metadatas'] = metadatas
                
                collection.update(**update_kwargs)
                self.logger.info(f"更新 {len(documents)} 个文档在集合 '{collection_name}'")
                return True
            
            return await asyncio.to_thread(_update)
        except Exception as e:
            self.logger.error(f"更新文档失败 '{collection_name}': {e}")
            raise ValueError(f"Failed to update documents in '{collection_name}': {e}")
    
    async def delete_documents(
        self,
        collection_name: str,
        document_ids: List[str],
        **kwargs
    ) -> bool:
        """从集合中删除文档"""
        self._ensure_client()
        
        if not document_ids:
            return True
        
        try:
            def _delete():
                collection = self._get_or_load_collection(collection_name)
                collection.delete(ids=document_ids)
                self.logger.info(f"删除 {len(document_ids)} 个文档从集合 '{collection_name}'")
                return True
            
            return await asyncio.to_thread(_delete)
        except Exception as e:
            self.logger.error(f"删除文档失败 '{collection_name}': {e}")
            raise ValueError(f"Failed to delete documents from '{collection_name}': {e}")
    
    async def get_document(
        self,
        collection_name: str,
        document_id: str,
        **kwargs
    ) -> Optional[VectorDocument]:
        """获取单个文档"""
        self._ensure_client()
        
        try:
            def _get():
                collection = self._get_or_load_collection(collection_name)
                result = collection.get(
                    ids=[document_id],
                    include=['embeddings', 'documents', 'metadatas']
                )
                
                if not result['ids']:
                    return None
                
                return VectorDocument(
                    id=result['ids'][0],
                    vector=result['embeddings'][0] if result.get('embeddings') else None,
                    content=result['documents'][0] if result.get('documents') else None,
                    metadata=result['metadatas'][0] if result.get('metadatas') else None
                )
            
            return await asyncio.to_thread(_get)
        except Exception:
            return None
    
    # ==================== 查询操作 ====================
    
    async def query_similar(
        self,
        collection_name: str,
        query_vector: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        top_k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[QueryResult]:
        """查询相似文档"""
        self._ensure_client()
        
        if query_vector is None and query_text is None:
            raise ValueError("Either query_vector or query_text must be provided")
        
        try:
            def _query():
                collection = self._get_or_load_collection(collection_name)
                
                # 构建查询参数
                query_kwargs = {
                    'n_results': top_k,
                    'include': ['embeddings', 'documents', 'metadatas', 'distances']
                }
                
                if query_vector:
                    query_kwargs['query_embeddings'] = [query_vector]
                elif query_text:
                    query_kwargs['query_texts'] = [query_text]
                
                if filter_metadata:
                    query_kwargs['where'] = filter_metadata
                
                results = collection.query(**query_kwargs)
                
                # 转换结果
                query_results = []
                if results['ids'] and results['ids'][0]:
                    for i in range(len(results['ids'][0])):
                        query_results.append(QueryResult(
                            id=results['ids'][0][i],
                            score=1.0 - results['distances'][0][i],  # ChromaDB 返回距离，转换为相似度
                            content=results['documents'][0][i] if results.get('documents') else None,
                            metadata=results['metadatas'][0][i] if results.get('metadatas') else None,
                            vector=results['embeddings'][0][i] if results.get('embeddings') else None
                        ))
                
                return query_results
            
            result = await asyncio.to_thread(_query)
            self.logger.debug(f"查询集合 '{collection_name}' 返回 {len(result)} 个结果")
            return result
        except Exception as e:
            self.logger.error(f"查询失败 '{collection_name}': {e}")
            raise ValueError(f"Failed to query '{collection_name}': {e}")
    
    async def batch_query_similar(
        self,
        collection_name: str,
        query_vectors: Optional[List[List[float]]] = None,
        query_texts: Optional[List[str]] = None,
        top_k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[List[QueryResult]]:
        """批量查询相似文档"""
        self._ensure_client()
        
        if query_vectors is None and query_texts is None:
            raise ValueError("Either query_vectors or query_texts must be provided")
        
        try:
            def _batch_query():
                collection = self._get_or_load_collection(collection_name)
                
                # 构建查询参数
                query_kwargs = {
                    'n_results': top_k,
                    'include': ['embeddings', 'documents', 'metadatas', 'distances']
                }
                
                if query_vectors:
                    query_kwargs['query_embeddings'] = query_vectors
                elif query_texts:
                    query_kwargs['query_texts'] = query_texts
                
                if filter_metadata:
                    query_kwargs['where'] = filter_metadata
                
                results = collection.query(**query_kwargs)
                
                # 转换结果
                batch_results = []
                for batch_idx in range(len(results['ids'])):
                    query_results = []
                    if results['ids'][batch_idx]:
                        for i in range(len(results['ids'][batch_idx])):
                            query_results.append(QueryResult(
                                id=results['ids'][batch_idx][i],
                                score=1.0 - results['distances'][batch_idx][i],
                                content=results['documents'][batch_idx][i] if results.get('documents') else None,
                                metadata=results['metadatas'][batch_idx][i] if results.get('metadatas') else None,
                                vector=results['embeddings'][batch_idx][i] if results.get('embeddings') else None
                            ))
                    batch_results.append(query_results)
                
                return batch_results
            
            result = await asyncio.to_thread(_batch_query)
            total_results = sum(len(r) for r in result)
            self.logger.debug(f"批量查询集合 '{collection_name}'，{len(result)} 个查询返回共 {total_results} 个结果")
            return result
        except Exception as e:
            self.logger.error(f"批量查询失败 '{collection_name}': {e}")
            raise ValueError(f"Failed to batch query '{collection_name}': {e}")
    
    # ==================== 统计操作 ====================
    
    async def count_documents(
        self,
        collection_name: str,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> int:
        """统计集合中的文档数量"""
        self._ensure_client()
        
        try:
            def _count():
                collection = self._get_or_load_collection(collection_name)
                if filter_metadata:
                    # 使用过滤条件查询并计数
                    result = collection.get(where=filter_metadata)
                    return len(result['ids'])
                else:
                    return collection.count()
            
            return await asyncio.to_thread(_count)
        except Exception as e:
            raise ValueError(f"Failed to count documents in '{collection_name}': {e}")
