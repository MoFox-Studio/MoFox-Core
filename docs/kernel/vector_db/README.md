# Vector DB 向量数据库模块文档

## 概述

Vector DB 模块提供统一的向量数据库接口，是 MoFox kernel 层的核心向量存储组件。该模块通过抽象基类定义标准接口，支持多种向量数据库后端，为上层应用提供向量存储、相似度检索等能力。

### 设计理念

- **抽象统一**: 统一的接口设计，屏蔽不同向量数据库的差异
- **异步优先**: 所有操作均为异步，提升并发性能
- **易于扩展**: 通过继承基类轻松支持新的向量数据库
- **类型安全**: 使用数据类确保类型安全和代码可读性

### 核心特性

🎯 **统一接口**: 抽象基类定义标准API，支持任意向量数据库  
🚀 **异步操作**: 全异步设计，高效处理并发请求  
📦 **数据类封装**: 使用 dataclass 确保类型安全  
🔌 **插件化架构**: 支持注册自定义向量数据库实现  
🏭 **工厂模式**: 提供工厂函数简化实例创建  
💾 **多种后端**: 目前支持 ChromaDB，易于扩展  

---

## 快速开始

### 安装与依赖

- `chromadb` 为可选依赖，仅在使用 ChromaDB 后端时需要安装：

```bash
py -3.11 -m pip install chromadb
```

- Windows 终端编码提示：如遇 `pip` 读取文件出现 `UnicodeDecodeError: 'gbk'`，可先切换到 UTF-8 再安装：

```bash
chcp 65001
py -3.11 -m pip install chromadb
```

- 编辑器导入提示：若 VS Code 显示“无法解析导入 chromadb”，请选择与运行一致的 Python 解释器（建议 3.11），或在工作区设置中配置 `python.defaultInterpreterPath`。

### 基础使用

```python
from kernel.vector_db import create_vector_db_async, VectorDocument

# 创建向量数据库实例
db = await create_vector_db_async(
    db_type='chromadb',
    config={'persist_directory': './data/chroma'}
)

# 创建集合
await db.create_collection('documents')

# 添加文档
documents = [
    VectorDocument(
        id='doc1',
        content='人工智能的发展',
        vector=[0.1, 0.2, 0.3, ...],  # 向量嵌入
        metadata={'category': 'AI', 'date': '2026-01-06'}
    ),
    VectorDocument(
        id='doc2',
        content='机器学习基础',
        vector=[0.2, 0.3, 0.4, ...],
        metadata={'category': 'ML', 'date': '2026-01-05'}
    )
]
await db.add_documents('documents', documents)

# 查询相似文档
results = await db.query_similar(
    collection_name='documents',
    query_vector=[0.15, 0.25, 0.35, ...],
    top_k=5
)

for result in results:
    print(f"ID: {result.id}, Score: {result.score}")
    print(f"Content: {result.content}")
    print(f"Metadata: {result.metadata}")
```

### 使用文本查询（需要嵌入函数）

```python
# 配置嵌入函数
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

db = await create_vector_db_async(
    db_type='chromadb',
    config={
        'persist_directory': './data/chroma',
        'embedding_function': lambda texts: model.encode(texts).tolist()
    }
)

# 使用文本查询
results = await db.query_similar(
    collection_name='documents',
    query_text='什么是人工智能',
    top_k=3
)
```

### 元数据过滤

```python
# 添加带元数据的文档
documents = [
    VectorDocument(
        id='doc1',
        content='Python 教程',
        vector=[...],
        metadata={'language': 'python', 'level': 'beginner'}
    ),
    VectorDocument(
        id='doc2',
        content='Python 高级特性',
        vector=[...],
        metadata={'language': 'python', 'level': 'advanced'}
    ),
    VectorDocument(
        id='doc3',
        content='JavaScript 入门',
        vector=[...],
        metadata={'language': 'javascript', 'level': 'beginner'}
    )
]
await db.add_documents('tutorials', documents)

# 查询时过滤
results = await db.query_similar(
    collection_name='tutorials',
    query_vector=[...],
    top_k=10,
    filter_metadata={'language': 'python', 'level': 'beginner'}
)
```

---

## API 参考

### 数据类

#### VectorDocument

文档数据类，表示一个向量文档。

```python
@dataclass
class VectorDocument:
    id: str                              # 文档唯一标识
    vector: Optional[List[float]]        # 向量表示
    content: Optional[str]               # 文档内容
    metadata: Optional[Dict[str, Any]]   # 元数据
```

#### QueryResult

查询结果数据类。

```python
@dataclass
class QueryResult:
    id: str                              # 文档ID
    score: float                         # 相似度分数
    content: Optional[str]               # 文档内容
    metadata: Optional[Dict[str, Any]]   # 元数据
    vector: Optional[List[float]]        # 向量
```

#### CollectionInfo

集合信息数据类。

```python
@dataclass
class CollectionInfo:
    name: str                            # 集合名称
    count: int                           # 文档数量
    dimension: Optional[int]             # 向量维度
    metadata: Optional[Dict[str, Any]]   # 集合元数据
```

### 基类接口

#### VectorDBBase

所有向量数据库实现的抽象基类。

##### 连接管理

```python
async def initialize() -> None
    """初始化数据库连接"""

async def close() -> None
    """关闭数据库连接"""

async def health_check() -> bool
    """健康检查"""
```

##### 集合操作

```python
async def create_collection(
    name: str,
    dimension: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> bool
    """创建集合"""

async def delete_collection(name: str) -> bool
    """删除集合"""

async def list_collections() -> List[str]
    """列出所有集合名称"""

async def get_collection_info(name: str) -> Optional[CollectionInfo]
    """获取集合信息"""

async def collection_exists(name: str) -> bool
    """检查集合是否存在"""
```

##### 文档操作

```python
async def add_documents(
    collection_name: str,
    documents: List[VectorDocument],
    **kwargs
) -> bool
    """添加文档到集合"""

async def update_documents(
    collection_name: str,
    documents: List[VectorDocument],
    **kwargs
) -> bool
    """更新集合中的文档"""

async def delete_documents(
    collection_name: str,
    document_ids: List[str],
    **kwargs
) -> bool
    """从集合中删除文档"""

async def get_document(
    collection_name: str,
    document_id: str,
    **kwargs
) -> Optional[VectorDocument]
    """获取单个文档"""
```

##### 查询操作

```python
async def query_similar(
    collection_name: str,
    query_vector: Optional[List[float]] = None,
    query_text: Optional[str] = None,
    top_k: int = 10,
    filter_metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[QueryResult]
    """查询相似文档"""

async def batch_query_similar(
    collection_name: str,
    query_vectors: Optional[List[List[float]]] = None,
    query_texts: Optional[List[str]] = None,
    top_k: int = 10,
    filter_metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[List[QueryResult]]
    """批量查询相似文档"""
```

##### 统计操作

```python
async def count_documents(
    collection_name: str,
    filter_metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> int
    """统计集合中的文档数量"""
```

### 工厂函数

#### create_vector_db

同步创建向量数据库实例。

```python
def create_vector_db(
    db_type: VectorDBType = 'chromadb',
    config: Optional[Dict[str, Any]] = None,
    auto_initialize: bool = True
) -> VectorDBBase
```

**参数：**
- `db_type`: 数据库类型，目前支持 `'chromadb'`
- `config`: 配置字典
- `auto_initialize`: 是否自动初始化

**示例：**
```python
db = create_vector_db(
    db_type='chromadb',
    config={'persist_directory': './data/chroma'}
)
```

#### create_vector_db_async

异步创建并初始化向量数据库实例（推荐）。

```python
async def create_vector_db_async(
    db_type: VectorDBType = 'chromadb',
    config: Optional[Dict[str, Any]] = None
) -> VectorDBBase
```

**参数：**
- `db_type`: 数据库类型
- `config`: 配置字典

**示例：**
```python
db = await create_vector_db_async(
    db_type='chromadb',
    config={'persist_directory': './data/chroma'}
)
# db 已经初始化，可以直接使用
```

### 工具函数

#### register_vector_db

注册自定义向量数据库实现。

```python
def register_vector_db(name: str, db_class: type) -> None
```

**示例：**
```python
class MyVectorDB(VectorDBBase):
    # 实现所有抽象方法
    pass

register_vector_db('myvectordb', MyVectorDB)
db = await create_vector_db_async('myvectordb')
```

#### list_supported_databases

列出所有支持的向量数据库类型。

```python
def list_supported_databases() -> list
```

---

## ChromaDB 实现

### 配置选项

```python
config = {
    # 客户端类型
    'client_type': 'persistent',  # 'persistent', 'ephemeral', 'http'
    
    # 持久化目录（persistent 类型）
    'persist_directory': './data/chroma',
    
    # HTTP 客户端配置（http 类型）
    'host': 'localhost',
    'port': 8000,
    
    # 自定义嵌入函数
    'embedding_function': None,  # 或自定义函数
}
```

### 客户端类型

#### Persistent（持久化）

数据持久化到磁盘，推荐用于生产环境。

```python
db = await create_vector_db_async(
    db_type='chromadb',
    config={
        'client_type': 'persistent',
        'persist_directory': './data/chroma'
    }
)
```

#### Ephemeral（临时）

数据仅保存在内存中，适用于测试和临时任务。

```python
db = await create_vector_db_async(
    db_type='chromadb',
    config={'client_type': 'ephemeral'}
)
```

#### HTTP（远程）

连接到远程 ChromaDB 服务器。

```python
db = await create_vector_db_async(
    db_type='chromadb',
    config={
        'client_type': 'http',
        'host': 'remote-server.com',
        'port': 8000
    }
)
```

> 依赖说明：未安装 `chromadb` 时调用 ChromaDB 实现会抛出 `ImportError`。这是预期行为；请先安装依赖或选择其他后端实现。

### 嵌入函数

ChromaDB 可以配置自定义嵌入函数，将文本转换为向量。

```python
from sentence_transformers import SentenceTransformer

# 创建嵌入模型
model = SentenceTransformer('all-MiniLM-L6-v2')

def embedding_function(texts):
    """自定义嵌入函数"""
    if isinstance(texts, str):
        texts = [texts]
    return model.encode(texts).tolist()

# 配置数据库
db = await create_vector_db_async(
    db_type='chromadb',
    config={
        'persist_directory': './data/chroma',
        'embedding_function': embedding_function
    }
)

# 现在可以使用文本查询
results = await db.query_similar(
    collection_name='docs',
    query_text='人工智能',  # 自动转换为向量
    top_k=5
)
```

---

## 使用场景

### 场景1：语义搜索

```python
# 初始化
db = await create_vector_db_async('chromadb', {
    'persist_directory': './data/search',
    'embedding_function': embedding_fn
})

# 创建文档集合
await db.create_collection('articles')

# 添加文章
articles = [
    VectorDocument(
        id=f'article_{i}',
        content=article_text,
        metadata={'author': author, 'date': date}
    )
    for i, (article_text, author, date) in enumerate(articles_data)
]
await db.add_documents('articles', articles)

# 语义搜索
query = "如何学习机器学习"
results = await db.query_similar(
    collection_name='articles',
    query_text=query,
    top_k=10
)
```

### 场景2：推荐系统

```python
# 基于用户历史行为推荐相似内容
user_preference_vector = get_user_vector(user_id)

recommendations = await db.query_similar(
    collection_name='products',
    query_vector=user_preference_vector,
    top_k=20,
    filter_metadata={'in_stock': True, 'category': 'electronics'}
)
```

### 场景3：问答系统

```python
# 存储知识库
await db.create_collection('knowledge_base')
await db.add_documents('knowledge_base', knowledge_docs)

# 查找相关知识
user_question = "MoFox 如何配置日志系统？"
relevant_docs = await db.query_similar(
    collection_name='knowledge_base',
    query_text=user_question,
    top_k=3
)

# 将相关文档作为上下文传递给 LLM
context = "\n".join([doc.content for doc in relevant_docs])
answer = await llm.generate(question=user_question, context=context)
```

### 场景4：重复检测

```python
# 检测新文档是否与现有文档重复
new_doc_vector = embed(new_document)

similar_docs = await db.query_similar(
    collection_name='documents',
    query_vector=new_doc_vector,
    top_k=1
)

if similar_docs and similar_docs[0].score > 0.95:
    print(f"检测到重复文档: {similar_docs[0].id}")
else:
    await db.add_documents('documents', [new_document])
```

---

## 最佳实践

### 1. 集合命名

使用清晰、描述性的集合名称：

```python
# 推荐
await db.create_collection('user_chat_history')
await db.create_collection('product_embeddings')

# 不推荐
await db.create_collection('data')
await db.create_collection('collection1')
```

### 2. 元数据设计

合理使用元数据进行过滤和分类：

```python
VectorDocument(
    id='doc1',
    content='...',
    vector=[...],
    metadata={
        'type': 'article',
        'language': 'zh',
        'category': 'technology',
        'tags': ['ai', 'ml'],
        'created_at': '2026-01-06',
        'author_id': 'user123',
        'is_public': True
    }
)
```

### 3. 批量操作

优先使用批量操作提升性能：

```python
# 推荐：批量添加
documents = [VectorDocument(...) for _ in range(1000)]
await db.add_documents('collection', documents)

# 不推荐：逐个添加
for doc in documents:
    await db.add_documents('collection', [doc])
```

### 4. 错误处理

```python
try:
    await db.create_collection('my_collection')
except ValueError as e:
    logger.error(f"创建集合失败: {e}")
except KeyError as e:
    logger.error(f"集合不存在: {e}")
except ConnectionError as e:
    logger.error(f"数据库连接失败: {e}")
```

### 5. 资源清理

确保正确关闭数据库连接：

```python
db = await create_vector_db_async('chromadb', config)
try:
    # 使用数据库
    await db.query_similar(...)
finally:
    await db.close()
```

或使用上下文管理器（如果实现）：

```python
async with create_vector_db_async('chromadb', config) as db:
    await db.query_similar(...)
```

### 6. 向量维度一致性

确保同一集合中的所有向量维度一致：

```python
# 推荐：使用相同的嵌入模型
model = SentenceTransformer('all-MiniLM-L6-v2')  # 384维

docs = [
    VectorDocument(id='1', vector=model.encode(text1).tolist()),
    VectorDocument(id='2', vector=model.encode(text2).tolist()),
]
```

---

## 扩展开发

### 实现自定义向量数据库

继承 `VectorDBBase` 并实现所有抽象方法：

```python
from kernel.vector_db import VectorDBBase, register_vector_db

class MyVectorDB(VectorDBBase):
    """自定义向量数据库实现"""
    
    async def initialize(self) -> None:
        # 实现初始化逻辑
        pass
    
    async def close(self) -> None:
        # 实现关闭逻辑
        pass
    
    async def create_collection(self, name: str, **kwargs) -> bool:
        # 实现创建集合
        pass
    
    # ... 实现其他所有抽象方法
    
# 注册自定义实现
register_vector_db('myvectordb', MyVectorDB)

# 使用
db = await create_vector_db_async('myvectordb', config)
```

### 必须实现的方法

所有继承 `VectorDBBase` 的类必须实现以下方法：

- **连接管理**: `initialize()`, `close()`
- **集合操作**: `create_collection()`, `delete_collection()`, `list_collections()`, `get_collection_info()`, `collection_exists()`
- **文档操作**: `add_documents()`, `update_documents()`, `delete_documents()`, `get_document()`
- **查询操作**: `query_similar()`, `batch_query_similar()`
- **统计操作**: `count_documents()`

---

## 故障排查

### 常见问题

#### 1. ImportError: chromadb is not installed

```bash
pip install chromadb
```

#### 2. 数据库连接失败

```python
# 检查配置
config = {
    'persist_directory': './data/chroma',  # 确保路径存在或可创建
    'client_type': 'persistent'
}

# 测试连接
db = await create_vector_db_async('chromadb', config)
is_healthy = await db.health_check()
print(f"数据库健康状态: {is_healthy}")
```

#### 3. 集合已存在错误

```python
# 检查集合是否存在
if not await db.collection_exists('my_collection'):
    await db.create_collection('my_collection')
```

#### 4. 向量维度不匹配

确保所有文档的向量维度一致，或使用相同的嵌入函数。

#### 5. 查询返回空结果

```python
# 检查集合是否有数据
count = await db.count_documents('my_collection')
print(f"文档数量: {count}")

# 检查过滤条件
results = await db.query_similar(
    collection_name='my_collection',
    query_vector=query_vec,
    top_k=10,
    filter_metadata=None  # 移除过滤条件测试
)
```

---

## 性能优化

### 1. 批量操作

```python
# 批量添加文档
await db.add_documents('collection', documents_batch)

# 批量查询
results = await db.batch_query_similar(
    collection_name='collection',
    query_vectors=query_vectors_list,
    top_k=10
)
```

### 2. 合理的 top_k

```python
# 根据实际需求设置 top_k，避免返回过多结果
results = await db.query_similar(
    collection_name='docs',
    query_vector=vec,
    top_k=5  # 仅返回最相关的5个结果
)
```

### 3. 使用元数据过滤

```python
# 先通过元数据过滤，再进行向量相似度计算
results = await db.query_similar(
    collection_name='articles',
    query_vector=vec,
    top_k=10,
    filter_metadata={'category': 'tech', 'language': 'zh'}  # 预过滤
)
```

### 4. 集合缓存

ChromaDB 实现内置了集合缓存，避免重复加载。

---

## 版本兼容性

- **Python**: 3.8+
- **ChromaDB**: 0.4.0+
- **依赖**: 
  - `chromadb` (可选，使用 ChromaDB 时需要)
  - `sentence-transformers` (可选，使用文本嵌入时需要)

---

## 相关文档

- [API Reference](API_REFERENCE.md) - 详细的 API 文档
- [Best Practices](BEST_PRACTICES.md) - 最佳实践指南
- [Configuration Guide](CONFIGURATION_GUIDE.md) - 配置指南

---

## 更新日志

### v1.0.0 (2026-01-06)
- ✨ 初始版本发布
- ✨ 实现 VectorDBBase 抽象基类
- ✨ 实现 ChromaDB 后端支持
- ✨ 提供工厂函数和注册机制
- ✨ 完整的异步 API
