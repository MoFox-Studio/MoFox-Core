# Vector DB API 参考文档

## 目录

- [数据类](#数据类)
- [抽象基类](#抽象基类)
- [ChromaDB 实现](#chromadb-实现)
- [工厂函数](#工厂函数)
- [工具函数](#工具函数)

---

## 数据类

### VectorDocument

**描述**: 向量文档数据类，表示一个包含向量、内容和元数据的文档。

**定义**:
```python
@dataclass
class VectorDocument:
    id: str
    vector: Optional[List[float]] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

**字段**:

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | `str` | ✅ | 文档唯一标识符 |
| `vector` | `Optional[List[float]]` | ❌ | 文档的向量表示（嵌入） |
| `content` | `Optional[str]` | ❌ | 文档的文本内容 |
| `metadata` | `Optional[Dict[str, Any]]` | ❌ | 附加的元数据字典 |

**使用示例**:
```python
doc = VectorDocument(
    id='doc_001',
    content='人工智能是计算机科学的一个分支',
    vector=[0.1, 0.2, 0.3, ...],
    metadata={
        'category': 'AI',
        'language': 'zh',
        'author': 'MoFox',
        'created_at': '2026-01-06'
    }
)
```

---

### QueryResult

**描述**: 查询结果数据类，表示相似度查询返回的单个结果。

**定义**:
```python
@dataclass
class QueryResult:
    id: str
    score: float
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    vector: Optional[List[float]] = None
```

**字段**:

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | `str` | ✅ | 匹配文档的ID |
| `score` | `float` | ✅ | 相似度分数（0-1，越大越相似） |
| `content` | `Optional[str]` | ❌ | 文档内容 |
| `metadata` | `Optional[Dict[str, Any]]` | ❌ | 文档元数据 |
| `vector` | `Optional[List[float]]` | ❌ | 文档向量 |

**使用示例**:
```python
# 查询结果自动构造
results = await db.query_similar(
    collection_name='docs',
    query_vector=query_vec,
    top_k=5
)

for result in results:
    print(f"文档ID: {result.id}")
    print(f"相似度: {result.score:.4f}")
    print(f"内容: {result.content}")
    print(f"元数据: {result.metadata}")
```

---

### CollectionInfo

**描述**: 集合信息数据类，包含集合的基本统计信息。

**定义**:
```python
@dataclass
class CollectionInfo:
    name: str
    count: int
    dimension: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
```

**字段**:

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | `str` | ✅ | 集合名称 |
| `count` | `int` | ✅ | 文档数量 |
| `dimension` | `Optional[int]` | ❌ | 向量维度 |
| `metadata` | `Optional[Dict[str, Any]]` | ❌ | 集合元数据 |

**使用示例**:
```python
info = await db.get_collection_info('my_collection')
print(f"集合名: {info.name}")
print(f"文档数: {info.count}")
print(f"向量维度: {info.dimension}")
```

---

## 抽象基类

### VectorDBBase

**描述**: 向量数据库抽象基类，定义了所有向量数据库实现必须遵循的接口。

#### 构造函数

```python
def __init__(self, config: Optional[Dict[str, Any]] = None)
```

**参数**:
- `config` (Optional[Dict]): 配置字典，内容因实现而异

---

### 连接管理方法

#### initialize()

**描述**: 初始化数据库连接。

```python
async def initialize() -> None
```

**异常**:
- `ConnectionError`: 连接失败时抛出

**示例**:
```python
db = ChromaDBImpl(config)
await db.initialize()
```

---

#### close()

**描述**: 关闭数据库连接，释放资源。

```python
async def close() -> None
```

**示例**:
```python
await db.close()
```

---

#### health_check()

**描述**: 检查数据库是否正常工作。

```python
async def health_check() -> bool
```

**返回值**: 
- `bool`: 数据库是否健康

**示例**:
```python
is_healthy = await db.health_check()
if not is_healthy:
    logger.error("数据库连接异常")
```

---

### 集合操作方法

#### create_collection()

**描述**: 创建新集合。

```python
async def create_collection(
    name: str,
    dimension: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> bool
```

**参数**:
- `name` (str): 集合名称
- `dimension` (Optional[int]): 向量维度
- `metadata` (Optional[Dict]): 集合元数据
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `bool`: 是否创建成功

**异常**:
- `ValueError`: 参数错误

**示例**:
```python
success = await db.create_collection(
    name='documents',
    dimension=384,
    metadata={'description': '文档集合'}
)
```

---

#### delete_collection()

**描述**: 删除集合。

```python
async def delete_collection(name: str) -> bool
```

**参数**:
- `name` (str): 集合名称

**返回值**:
- `bool`: 是否删除成功

**示例**:
```python
await db.delete_collection('old_collection')
```

---

#### list_collections()

**描述**: 列出所有集合名称。

```python
async def list_collections() -> List[str]
```

**返回值**:
- `List[str]`: 集合名称列表

**示例**:
```python
collections = await db.list_collections()
print(f"现有集合: {collections}")
```

---

#### get_collection_info()

**描述**: 获取集合的详细信息。

```python
async def get_collection_info(name: str) -> Optional[CollectionInfo]
```

**参数**:
- `name` (str): 集合名称

**返回值**:
- `Optional[CollectionInfo]`: 集合信息，不存在时返回 None

**示例**:
```python
info = await db.get_collection_info('documents')
if info:
    print(f"文档数量: {info.count}")
```

---

#### collection_exists()

**描述**: 检查集合是否存在。

```python
async def collection_exists(name: str) -> bool
```

**参数**:
- `name` (str): 集合名称

**返回值**:
- `bool`: 集合是否存在

**示例**:
```python
if not await db.collection_exists('documents'):
    await db.create_collection('documents')
```

---

### 文档操作方法

#### add_documents()

**描述**: 向集合添加文档。

```python
async def add_documents(
    collection_name: str,
    documents: List[VectorDocument],
    **kwargs
) -> bool
```

**参数**:
- `collection_name` (str): 集合名称
- `documents` (List[VectorDocument]): 文档列表
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `bool`: 是否添加成功

**异常**:
- `ValueError`: 参数错误
- `KeyError`: 集合不存在

**示例**:
```python
documents = [
    VectorDocument(id='1', content='文档1', vector=[...]),
    VectorDocument(id='2', content='文档2', vector=[...])
]
await db.add_documents('documents', documents)
```

---

#### update_documents()

**描述**: 更新集合中的文档。

```python
async def update_documents(
    collection_name: str,
    documents: List[VectorDocument],
    **kwargs
) -> bool
```

**参数**:
- `collection_name` (str): 集合名称
- `documents` (List[VectorDocument]): 更新的文档列表
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `bool`: 是否更新成功

**异常**:
- `ValueError`: 参数错误
- `KeyError`: 集合不存在

**示例**:
```python
updated_docs = [
    VectorDocument(id='1', content='更新后的内容', vector=[...])
]
await db.update_documents('documents', updated_docs)
```

---

#### delete_documents()

**描述**: 从集合中删除文档。

```python
async def delete_documents(
    collection_name: str,
    document_ids: List[str],
    **kwargs
) -> bool
```

**参数**:
- `collection_name` (str): 集合名称
- `document_ids` (List[str]): 要删除的文档ID列表
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `bool`: 是否删除成功

**异常**:
- `KeyError`: 集合不存在

**示例**:
```python
await db.delete_documents('documents', ['doc1', 'doc2', 'doc3'])
```

---

#### get_document()

**描述**: 获取单个文档。

```python
async def get_document(
    collection_name: str,
    document_id: str,
    **kwargs
) -> Optional[VectorDocument]
```

**参数**:
- `collection_name` (str): 集合名称
- `document_id` (str): 文档ID
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `Optional[VectorDocument]`: 文档对象，不存在时返回 None

**异常**:
- `KeyError`: 集合不存在

**示例**:
```python
doc = await db.get_document('documents', 'doc1')
if doc:
    print(f"内容: {doc.content}")
```

---

### 查询操作方法

#### query_similar()

**描述**: 查询相似文档。

```python
async def query_similar(
    collection_name: str,
    query_vector: Optional[List[float]] = None,
    query_text: Optional[str] = None,
    top_k: int = 10,
    filter_metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[QueryResult]
```

**参数**:
- `collection_name` (str): 集合名称
- `query_vector` (Optional[List[float]]): 查询向量
- `query_text` (Optional[str]): 查询文本（需要嵌入函数）
- `top_k` (int): 返回结果数量，默认10
- `filter_metadata` (Optional[Dict]): 元数据过滤条件
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `List[QueryResult]`: 查询结果列表，按相似度降序排列

**异常**:
- `ValueError`: 参数错误（query_vector 和 query_text 必须提供其一）
- `KeyError`: 集合不存在

**示例**:
```python
# 使用向量查询
results = await db.query_similar(
    collection_name='documents',
    query_vector=[0.1, 0.2, ...],
    top_k=5
)

# 使用文本查询（需要嵌入函数）
results = await db.query_similar(
    collection_name='documents',
    query_text='人工智能',
    top_k=5,
    filter_metadata={'category': 'tech'}
)
```

---

#### batch_query_similar()

**描述**: 批量查询相似文档。

```python
async def batch_query_similar(
    collection_name: str,
    query_vectors: Optional[List[List[float]]] = None,
    query_texts: Optional[List[str]] = None,
    top_k: int = 10,
    filter_metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[List[QueryResult]]
```

**参数**:
- `collection_name` (str): 集合名称
- `query_vectors` (Optional[List[List[float]]]): 查询向量列表
- `query_texts` (Optional[List[str]]): 查询文本列表
- `top_k` (int): 每个查询返回的结果数量
- `filter_metadata` (Optional[Dict]): 元数据过滤条件
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `List[List[QueryResult]]`: 查询结果列表的列表

**异常**:
- `ValueError`: 参数错误
- `KeyError`: 集合不存在

**示例**:
```python
queries = [[0.1, 0.2, ...], [0.3, 0.4, ...]]
batch_results = await db.batch_query_similar(
    collection_name='documents',
    query_vectors=queries,
    top_k=5
)

for i, results in enumerate(batch_results):
    print(f"查询 {i+1} 的结果:")
    for result in results:
        print(f"  - {result.id}: {result.score}")
```

---

### 统计操作方法

#### count_documents()

**描述**: 统计集合中的文档数量。

```python
async def count_documents(
    collection_name: str,
    filter_metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> int
```

**参数**:
- `collection_name` (str): 集合名称
- `filter_metadata` (Optional[Dict]): 元数据过滤条件
- `**kwargs`: 实现特定的额外参数

**返回值**:
- `int`: 文档数量

**异常**:
- `KeyError`: 集合不存在

**示例**:
```python
# 统计总数
total = await db.count_documents('documents')

# 带过滤条件统计
tech_count = await db.count_documents(
    'documents',
    filter_metadata={'category': 'tech'}
)
```

---

## ChromaDB 实现

### ChromaDBImpl

**描述**: 基于 ChromaDB 的向量数据库实现。

#### 构造函数

```python
def __init__(self, config: Optional[Dict[str, Any]] = None)
```

**配置参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `client_type` | str | `'persistent'` | 客户端类型：'persistent', 'ephemeral', 'http' |
| `persist_directory` | str | None | 持久化目录路径 |
| `host` | str | `'localhost'` | HTTP客户端主机地址 |
| `port` | int | `8000` | HTTP客户端端口 |
| `embedding_function` | Callable | None | 自定义嵌入函数 |

**配置示例**:

```python
# Persistent 客户端
config = {
    'client_type': 'persistent',
    'persist_directory': './data/chroma'
}

# Ephemeral 客户端
config = {
    'client_type': 'ephemeral'
}

# HTTP 客户端
config = {
    'client_type': 'http',
    'host': 'localhost',
    'port': 8000
}

# 带嵌入函数
config = {
    'client_type': 'persistent',
    'persist_directory': './data/chroma',
    'embedding_function': my_embedding_function
}
```

#### 特殊说明

**嵌入函数格式**:
```python
def embedding_function(texts: Union[str, List[str]]) -> List[List[float]]:
    """
    将文本转换为向量
    
    Args:
        texts: 单个文本字符串或文本列表
    
    Returns:
        向量列表
    """
    pass
```

**相似度分数转换**:
ChromaDB 返回的是距离（distance），实现会自动转换为相似度分数：
```python
score = 1.0 - distance
```

---

## 工厂函数

### create_vector_db()

**描述**: 创建向量数据库实例（同步）。

```python
def create_vector_db(
    db_type: VectorDBType = 'chromadb',
    config: Optional[Dict[str, Any]] = None,
    auto_initialize: bool = True
) -> VectorDBBase
```

**参数**:
- `db_type` (VectorDBType): 数据库类型
- `config` (Optional[Dict]): 配置字典
- `auto_initialize` (bool): 是否自动初始化

**返回值**:
- `VectorDBBase`: 向量数据库实例

**异常**:
- `ValueError`: 不支持的数据库类型
- `ImportError`: 缺少必要的依赖

**示例**:
```python
# 自动初始化
db = create_vector_db('chromadb', {'persist_directory': './data'})

# 手动初始化
db = create_vector_db('chromadb', config, auto_initialize=False)
await db.initialize()
```

---

### create_vector_db_async()

**描述**: 异步创建并初始化向量数据库实例（推荐）。

```python
async def create_vector_db_async(
    db_type: VectorDBType = 'chromadb',
    config: Optional[Dict[str, Any]] = None
) -> VectorDBBase
```

**参数**:
- `db_type` (VectorDBType): 数据库类型
- `config` (Optional[Dict]): 配置字典

**返回值**:
- `VectorDBBase`: 已初始化的向量数据库实例

**异常**:
- `ValueError`: 不支持的数据库类型
- `ImportError`: 缺少必要的依赖

**示例**:
```python
db = await create_vector_db_async(
    db_type='chromadb',
    config={'persist_directory': './data/chroma'}
)
# 实例已初始化，可以直接使用
await db.create_collection('my_collection')
```

---

## 工具函数

### register_vector_db()

**描述**: 注册自定义向量数据库实现。

```python
def register_vector_db(name: str, db_class: type) -> None
```

**参数**:
- `name` (str): 数据库类型名称
- `db_class` (type): 数据库实现类（必须继承 VectorDBBase）

**异常**:
- `TypeError`: db_class 不是 VectorDBBase 的子类

**示例**:
```python
class MyVectorDB(VectorDBBase):
    # 实现所有抽象方法
    pass

register_vector_db('myvectordb', MyVectorDB)
db = await create_vector_db_async('myvectordb')
```

---

### list_supported_databases()

**描述**: 列出所有支持的向量数据库类型。

```python
def list_supported_databases() -> list
```

**返回值**:
- `list`: 支持的数据库类型列表

**示例**:
```python
supported = list_supported_databases()
print(f"支持的数据库: {supported}")  # ['chromadb']
```

---

## 类型定义

### VectorDBType

**描述**: 向量数据库类型字面量。

```python
VectorDBType = Literal['chromadb']
```

当前支持的类型：
- `'chromadb'`: ChromaDB 向量数据库

---

## 完整使用示例

### 基础工作流

```python
from kernel.vector_db import (
    create_vector_db_async,
    VectorDocument,
    QueryResult
)

# 1. 创建数据库实例
db = await create_vector_db_async(
    db_type='chromadb',
    config={'persist_directory': './data/chroma'}
)

# 2. 创建集合
await db.create_collection('articles')

# 3. 准备文档
documents = [
    VectorDocument(
        id='article_1',
        content='深度学习是机器学习的一个分支',
        vector=[0.1, 0.2, 0.3, ...],
        metadata={'category': 'AI', 'author': 'Zhang'}
    ),
    VectorDocument(
        id='article_2',
        content='神经网络模拟人脑的工作方式',
        vector=[0.15, 0.25, 0.35, ...],
        metadata={'category': 'AI', 'author': 'Li'}
    )
]

# 4. 添加文档
await db.add_documents('articles', documents)

# 5. 查询相似文档
results = await db.query_similar(
    collection_name='articles',
    query_vector=[0.12, 0.22, 0.32, ...],
    top_k=10,
    filter_metadata={'category': 'AI'}
)

# 6. 处理结果
for result in results:
    print(f"文章: {result.id}")
    print(f"相似度: {result.score:.4f}")
    print(f"内容: {result.content}")
    print(f"作者: {result.metadata['author']}")
    print("-" * 50)

# 7. 清理
await db.close()
```

### 高级工作流

```python
# 使用自定义嵌入函数
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

db = await create_vector_db_async(
    db_type='chromadb',
    config={
        'persist_directory': './data/chroma',
        'embedding_function': lambda texts: model.encode(texts).tolist()
    }
)

# 创建集合
await db.create_collection('semantic_search')

# 添加文档（自动生成向量）
documents = [
    VectorDocument(
        id=f'doc_{i}',
        content=text,
        metadata={'source': 'wikipedia'}
    )
    for i, text in enumerate(article_texts)
]
await db.add_documents('semantic_search', documents)

# 使用文本查询（自动转换为向量）
results = await db.query_similar(
    collection_name='semantic_search',
    query_text='什么是人工智能？',  # 自动嵌入
    top_k=5
)

# 批量查询
queries = ['机器学习', '深度学习', '神经网络']
batch_results = await db.batch_query_similar(
    collection_name='semantic_search',
    query_texts=queries,
    top_k=3
)
```
