"""
向量数据库抽象基类

定义了所有向量数据库实现必须遵循的接口
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from ..logger import get_logger


@dataclass
class VectorDocument:
    """向量文档数据类"""
    id: str  # 文档唯一标识
    vector: Optional[List[float]] = None  # 向量表示
    content: Optional[str] = None  # 文档内容
    metadata: Optional[Dict[str, Any]] = None  # 元数据


@dataclass
class QueryResult:
    """查询结果数据类"""
    id: str  # 文档ID
    score: float  # 相似度分数
    content: Optional[str] = None  # 文档内容
    metadata: Optional[Dict[str, Any]] = None  # 元数据
    vector: Optional[List[float]] = None  # 向量


@dataclass
class CollectionInfo:
    """集合信息数据类"""
    name: str  # 集合名称
    count: int  # 文档数量
    dimension: Optional[int] = None  # 向量维度
    metadata: Optional[Dict[str, Any]] = None  # 集合元数据


class VectorDBBase(ABC):
    """向量数据库抽象基类
    
    所有向量数据库实现必须继承此类并实现所有抽象方法
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化向量数据库
        
        Args:
            config: 数据库配置字典
        """
        self.config = config or {}
        self.logger = get_logger(f"{self.__class__.__module__}.{self.__class__.__name__}")
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化数据库连接
        
        Raises:
            ConnectionError: 连接失败时抛出
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭数据库连接"""
        pass
    
    # ==================== 集合操作 ====================
    
    @abstractmethod
    async def create_collection(
        self,
        name: str,
        dimension: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """创建集合
        
        Args:
            name: 集合名称
            dimension: 向量维度
            metadata: 集合元数据
            **kwargs: 其他特定于实现的参数
            
        Returns:
            bool: 是否创建成功
            
        Raises:
            ValueError: 参数错误时抛出
        """
        pass
    
    @abstractmethod
    async def delete_collection(self, name: str) -> bool:
        """删除集合
        
        Args:
            name: 集合名称
            
        Returns:
            bool: 是否删除成功
        """
        pass
    
    @abstractmethod
    async def list_collections(self) -> List[str]:
        """列出所有集合名称
        
        Returns:
            List[str]: 集合名称列表
        """
        pass
    
    @abstractmethod
    async def get_collection_info(self, name: str) -> Optional[CollectionInfo]:
        """获取集合信息
        
        Args:
            name: 集合名称
            
        Returns:
            Optional[CollectionInfo]: 集合信息，不存在时返回None
        """
        pass
    
    @abstractmethod
    async def collection_exists(self, name: str) -> bool:
        """检查集合是否存在
        
        Args:
            name: 集合名称
            
        Returns:
            bool: 集合是否存在
        """
        pass
    
    # ==================== 文档操作 ====================
    
    @abstractmethod
    async def add_documents(
        self,
        collection_name: str,
        documents: List[VectorDocument],
        **kwargs
    ) -> bool:
        """添加文档到集合
        
        Args:
            collection_name: 集合名称
            documents: 文档列表
            **kwargs: 其他特定于实现的参数
            
        Returns:
            bool: 是否添加成功
            
        Raises:
            ValueError: 参数错误时抛出
            KeyError: 集合不存在时抛出
        """
        pass
    
    @abstractmethod
    async def update_documents(
        self,
        collection_name: str,
        documents: List[VectorDocument],
        **kwargs
    ) -> bool:
        """更新集合中的文档
        
        Args:
            collection_name: 集合名称
            documents: 文档列表
            **kwargs: 其他特定于实现的参数
            
        Returns:
            bool: 是否更新成功
            
        Raises:
            ValueError: 参数错误时抛出
            KeyError: 集合不存在时抛出
        """
        pass
    
    @abstractmethod
    async def delete_documents(
        self,
        collection_name: str,
        document_ids: List[str],
        **kwargs
    ) -> bool:
        """从集合中删除文档
        
        Args:
            collection_name: 集合名称
            document_ids: 文档ID列表
            **kwargs: 其他特定于实现的参数
            
        Returns:
            bool: 是否删除成功
            
        Raises:
            KeyError: 集合不存在时抛出
        """
        pass
    
    @abstractmethod
    async def get_document(
        self,
        collection_name: str,
        document_id: str,
        **kwargs
    ) -> Optional[VectorDocument]:
        """获取单个文档
        
        Args:
            collection_name: 集合名称
            document_id: 文档ID
            **kwargs: 其他特定于实现的参数
            
        Returns:
            Optional[VectorDocument]: 文档对象，不存在时返回None
            
        Raises:
            KeyError: 集合不存在时抛出
        """
        pass
    
    # ==================== 查询操作 ====================
    
    @abstractmethod
    async def query_similar(
        self,
        collection_name: str,
        query_vector: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        top_k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[QueryResult]:
        """查询相似文档
        
        Args:
            collection_name: 集合名称
            query_vector: 查询向量（与query_text二选一）
            query_text: 查询文本（与query_vector二选一）
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件
            **kwargs: 其他特定于实现的参数
            
        Returns:
            List[QueryResult]: 查询结果列表，按相似度降序排列
            
        Raises:
            ValueError: 参数错误时抛出
            KeyError: 集合不存在时抛出
        """
        pass
    
    @abstractmethod
    async def batch_query_similar(
        self,
        collection_name: str,
        query_vectors: Optional[List[List[float]]] = None,
        query_texts: Optional[List[str]] = None,
        top_k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[List[QueryResult]]:
        """批量查询相似文档
        
        Args:
            collection_name: 集合名称
            query_vectors: 查询向量列表（与query_texts二选一）
            query_texts: 查询文本列表（与query_vectors二选一）
            top_k: 每个查询返回结果数量
            filter_metadata: 元数据过滤条件
            **kwargs: 其他特定于实现的参数
            
        Returns:
            List[List[QueryResult]]: 查询结果列表的列表
            
        Raises:
            ValueError: 参数错误时抛出
            KeyError: 集合不存在时抛出
        """
        pass
    
    # ==================== 统计操作 ====================
    
    @abstractmethod
    async def count_documents(
        self,
        collection_name: str,
        filter_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> int:
        """统计集合中的文档数量
        
        Args:
            collection_name: 集合名称
            filter_metadata: 元数据过滤条件
            **kwargs: 其他特定于实现的参数
            
        Returns:
            int: 文档数量
            
        Raises:
            KeyError: 集合不存在时抛出
        """
        pass
    
    # ==================== 辅助方法 ====================
    
    async def health_check(self) -> bool:
        """健康检查
        
        Returns:
            bool: 数据库是否正常工作
        """
        try:
            # 默认实现：尝试列出集合
            await self.list_collections()
            self.logger.debug("数据库健康检查通过")
            return True
        except Exception as e:
            self.logger.warning(f"数据库健康检查失败: {e}")
            return False
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(config={self.config})"
