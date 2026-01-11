"""
向量数据库模块

提供统一的向量数据库接口和工厂函数
"""

from typing import Dict, Any, Optional, Literal
from kernel.logger import get_logger

# 获取模块级别的logger
logger = get_logger(__name__)

# 导出基类和数据类
from .base import (
    VectorDBBase,
    VectorDocument,
    QueryResult,
    CollectionInfo
)

# 导出具体实现
from .chromadb_impl import ChromaDBImpl, CHROMADB_AVAILABLE
from .memory_impl import InMemoryVectorDB

# 支持的向量数据库类型
VectorDBType = Literal['chromadb']

# 向量数据库实现映射
_VECTOR_DB_REGISTRY: Dict[str, type] = {
    'chromadb': ChromaDBImpl if CHROMADB_AVAILABLE else InMemoryVectorDB,
}

if not CHROMADB_AVAILABLE:
    logger.warning("ChromaDB not installed; using in-memory vector DB fallback for 'chromadb'")


def create_vector_db(
    db_type: VectorDBType = 'chromadb',
    config: Optional[Dict[str, Any]] = None,
    auto_initialize: bool = True
) -> VectorDBBase:
    """工厂函数：创建并返回向量数据库实例
    
    Args:
        db_type: 向量数据库类型，目前支持 'chromadb'
        config: 数据库配置字典，具体配置项取决于数据库类型
            
            ChromaDB 配置示例：
            {
                'client_type': 'persistent',  # 'persistent', 'ephemeral', 'http'
                'persist_directory': './data/chroma',  # 持久化目录
                'host': 'localhost',  # HTTP客户端使用
                'port': 8000,  # HTTP客户端使用
                'embedding_function': None,  # 自定义嵌入函数
            }
        
        auto_initialize: 是否自动初始化（同步初始化）
            如果为 True，将尝试同步初始化
            如果为 False，需要手动调用 await db.initialize()
    
    Returns:
        VectorDBBase: 向量数据库实例
    
    Raises:
        ValueError: 不支持的数据库类型
        ImportError: 缺少必要的依赖包
    
    Examples:
        >>> # 创建 ChromaDB 实例（自动初始化）
        >>> db = create_vector_db(
        ...     db_type='chromadb',
        ...     config={'persist_directory': './data/chroma'}
        ... )
        
        >>> # 创建实例但不初始化（需要在异步环境中手动初始化）
        >>> db = create_vector_db(
        ...     db_type='chromadb',
        ...     config={'persist_directory': './data/chroma'},
        ...     auto_initialize=False
        ... )
        >>> await db.initialize()
    """
    if db_type not in _VECTOR_DB_REGISTRY:
        supported = ', '.join(_VECTOR_DB_REGISTRY.keys())
        logger.error(f"不支持的向量数据库类型: '{db_type}'，支持的类型: {supported}")
        raise ValueError(
            f"Unsupported vector database type: '{db_type}'. "
            f"Supported types: {supported}"
        )
    
    logger.info(f"创建向量数据库实例: {db_type}")
    
    # 创建实例
    db_class = _VECTOR_DB_REGISTRY[db_type]
    db_instance = db_class(config=config)
    
    # 如果需要自动初始化（同步方式）
    if auto_initialize:
        import asyncio
        try:
            # 尝试在现有事件循环中初始化
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，创建一个任务
                asyncio.create_task(db_instance.initialize())
            else:
                # 如果循环未运行，同步执行
                loop.run_until_complete(db_instance.initialize())
        except RuntimeError:
            # 没有事件循环，创建一个新的
            asyncio.run(db_instance.initialize())
    
    return db_instance


async def create_vector_db_async(
    db_type: VectorDBType = 'chromadb',
    config: Optional[Dict[str, Any]] = None
) -> VectorDBBase:
    """异步工厂函数：创建并初始化向量数据库实例
    
    推荐在异步环境中使用此函数
    
    Args:
        db_type: 向量数据库类型
        config: 数据库配置字典
    
    Returns:
        VectorDBBase: 已初始化的向量数据库实例
    
    Examples:
        >>> # 在异步函数中使用
        >>> async def main():
        ...     db = await create_vector_db_async(
        ...         db_type='chromadb',
        ...         config={'persist_directory': './data/chroma'}
        ...     )
        ...     # db 已经初始化，可以直接使用
        ...     await db.create_collection('my_collection')
    """
    if db_type not in _VECTOR_DB_REGISTRY:
        supported = ', '.join(_VECTOR_DB_REGISTRY.keys())
        logger.error(f"不支持的向量数据库类型: '{db_type}'，支持的类型: {supported}")
        raise ValueError(
            f"Unsupported vector database type: '{db_type}'. "
            f"Supported types: {supported}"
        )
    
    logger.info(f"异步创建向量数据库实例: {db_type}")
    
    # 创建实例
    db_class = _VECTOR_DB_REGISTRY[db_type]
    db_instance = db_class(config=config)
    
    # 异步初始化
    await db_instance.initialize()
    logger.info(f"向量数据库实例已初始化: {db_type}")
    
    return db_instance


def register_vector_db(name: str, db_class: type) -> None:
    """注册自定义向量数据库实现
    
    允许用户注册自己的向量数据库实现
    
    Args:
        name: 数据库类型名称
        db_class: 数据库实现类，必须继承自 VectorDBBase
    
    Raises:
        TypeError: 如果 db_class 不是 VectorDBBase 的子类
        
    Examples:
        >>> class MyVectorDB(VectorDBBase):
        ...     # 实现所有抽象方法
        ...     pass
        >>> 
        >>> register_vector_db('myvectordb', MyVectorDB)
        >>> db = create_vector_db('myvectordb', config={...})
    """
    if not issubclass(db_class, VectorDBBase):
        logger.error(f"注册失败: {db_class.__name__} 不是 VectorDBBase 的子类")
        raise TypeError(
            f"db_class must be a subclass of VectorDBBase, "
            f"got {db_class.__name__}"
        )
    
    logger.info(f"注册自定义向量数据库: {name} -> {db_class.__name__}")
    _VECTOR_DB_REGISTRY[name] = db_class


def list_supported_databases() -> list:
    """列出所有支持的向量数据库类型
    
    Returns:
        list: 支持的数据库类型列表
    """
    return list(_VECTOR_DB_REGISTRY.keys())


# 导出所有公共接口
__all__ = [
    # 基类和数据类
    'VectorDBBase',
    'VectorDocument',
    'QueryResult',
    'CollectionInfo',
    
    # 具体实现
    'ChromaDBImpl',
    
    # 工厂函数
    'create_vector_db',
    'create_vector_db_async',
    
    # 工具函数
    'register_vector_db',
    'list_supported_databases',
    
    # 类型
    'VectorDBType',
]
