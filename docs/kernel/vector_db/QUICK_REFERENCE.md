# Vector DB 快速参考

## 一分钟快速上手

```python
from kernel.vector_db import create_vector_db_async, VectorDocument

# 创建数据库
db = await create_vector_db_async('chromadb', {
    'persist_directory': './data/chroma'
})

# 创建集合
await db.create_collection('docs')

# 添加文档
await db.add_documents('docs', [
    VectorDocument(id='1', content='文本', vector=[0.1, 0.2, ...])
])

# 查询
results = await db.query_similar('docs', query_vector=[0.1, 0.2, ...], top_k=5)
```

---

## 常用操作速查

### 初始化

```python
# 方式1: 异步（推荐）
db = await create_vector_db_async('chromadb', config)

# 方式2: 同步
db = create_vector_db('chromadb', config, auto_initialize=True)
```

### 集合管理

```python
# 创建集合
await db.create_collection('my_collection')

# 检查存在
exists = await db.collection_exists('my_collection')

# 列出所有集合
collections = await db.list_collections()

# 获取集合信息
info = await db.get_collection_info('my_collection')

# 删除集合
await db.delete_collection('my_collection')
```

### 文档操作

```python
# 添加文档
doc = VectorDocument(id='1', content='文本', vector=[...], metadata={...})
await db.add_documents('collection', [doc])

# 更新文档
await db.update_documents('collection', [doc])

# 获取文档
doc = await db.get_document('collection', 'doc_id')

# 删除文档
await db.delete_documents('collection', ['id1', 'id2'])

# 统计数量
count = await db.count_documents('collection')
```

### 查询

```python
# 向量查询
results = await db.query_similar(
    collection_name='docs',
    query_vector=[0.1, 0.2, ...],
    top_k=10
)

# 文本查询（需要嵌入函数）
results = await db.query_similar(
    collection_name='docs',
    query_text='搜索内容',
    top_k=10
)

# 带过滤的查询
results = await db.query_similar(
    collection_name='docs',
    query_vector=[...],
    top_k=10,
    filter_metadata={'category': 'tech'}
)

# 批量查询
batch_results = await db.batch_query_similar(
    collection_name='docs',
    query_vectors=[[...], [...]],
    top_k=5
)
```

---

## 配置速查

### ChromaDB 配置

```python
# Persistent（持久化）
config = {
    'client_type': 'persistent',
    'persist_directory': './data/chroma'
}

# Ephemeral（内存）
config = {
    'client_type': 'ephemeral'
}

# HTTP（远程）
config = {
    'client_type': 'http',
    'host': 'localhost',
    'port': 8000
}

# 带嵌入函数
config = {
    'client_type': 'persistent',
    'persist_directory': './data/chroma',
    'embedding_function': lambda texts: model.encode(texts).tolist()
}
```

---

## 安装与依赖

- 使用 ChromaDB 后端需要安装可选依赖：

```bash
py -3.11 -m pip install chromadb
```

- Windows 终端编码提示：如遇 `gbk` 解码错误，先执行：

```bash
chcp 65001
```

- VS Code 解释器提示：若编辑器显示“无法解析导入 chromadb”，请选择与运行一致的 Python 解释器（建议 3.11），或在工作区设置中配置 `python.defaultInterpreterPath`。


## 数据类速查

### VectorDocument

```python
VectorDocument(
    id='doc_001',                    # 必需：文档ID
    vector=[0.1, 0.2, ...],         # 可选：向量
    content='文档内容',              # 可选：文本内容
    metadata={'key': 'value'}       # 可选：元数据
)
```

### QueryResult

```python
result.id         # 文档ID
result.score      # 相似度分数（0-1）
result.content    # 文档内容
result.metadata   # 元数据
result.vector     # 向量
```

### CollectionInfo

```python
info.name         # 集合名称
info.count        # 文档数量
info.dimension    # 向量维度
info.metadata     # 集合元数据
```

---

## 错误处理

```python
try:
    await db.create_collection('my_collection')
except ValueError as e:
    # 参数错误
    logger.error(f"参数错误: {e}")
except KeyError as e:
    # 集合不存在
    logger.error(f"集合不存在: {e}")
except ConnectionError as e:
    # 连接失败
    logger.error(f"连接失败: {e}")
```

---

## 性能优化技巧

```python
# ✅ 批量操作
await db.add_documents('collection', documents_list)

# ✅ 使用元数据过滤
await db.query_similar(..., filter_metadata={'status': 'active'})

# ✅ 合理设置 top_k
await db.query_similar(..., top_k=5)  # 根据需要设置

# ✅ 批量查询
await db.batch_query_similar(...)
```

---

## 常见模式

### 初始化模式

```python
async def init_vector_db():
    """初始化向量数据库"""
    db = await create_vector_db_async('chromadb', config)
    
    # 创建必要的集合
    if not await db.collection_exists('documents'):
        await db.create_collection('documents')
    
    return db
```

### 查询模式

```python
async def search_documents(query_text, top_k=10):
    """搜索文档"""
    results = await db.query_similar(
        collection_name='documents',
        query_text=query_text,
        top_k=top_k,
        filter_metadata={'published': True}
    )
    
    return [
        {'id': r.id, 'content': r.content, 'score': r.score}
        for r in results
    ]
```

### 更新或插入模式

```python
async def upsert_document(doc):
    """更新或插入文档"""
    existing = await db.get_document('collection', doc.id)
    
    if existing:
        await db.update_documents('collection', [doc])
    else:
        await db.add_documents('collection', [doc])
```

---

## 调试技巧

```python
# 检查数据库健康
is_healthy = await db.health_check()
print(f"数据库健康: {is_healthy}")

# 查看所有集合
collections = await db.list_collections()
print(f"集合列表: {collections}")

# 查看集合详情
info = await db.get_collection_info('my_collection')
print(f"文档数量: {info.count}")

# 统计文档
count = await db.count_documents('my_collection')
print(f"总文档数: {count}")

# 获取单个文档
doc = await db.get_document('my_collection', 'doc_id')
print(f"文档内容: {doc.content if doc else 'Not Found'}")
```

---

## 环境变量

```bash
# .env 文件
VECTOR_DB_TYPE=chromadb
VECTOR_DB_CLIENT_TYPE=persistent
VECTOR_DB_PATH=./data/chroma
VECTOR_DB_HOST=localhost
VECTOR_DB_PORT=8000
```

```python
import os

config = {
    'client_type': os.getenv('VECTOR_DB_CLIENT_TYPE', 'persistent'),
    'persist_directory': os.getenv('VECTOR_DB_PATH', './data/chroma'),
    'host': os.getenv('VECTOR_DB_HOST', 'localhost'),
    'port': int(os.getenv('VECTOR_DB_PORT', '8000'))
}
```

---

## 依赖安装

```bash
# 基础安装
pip install chromadb

# 带文本嵌入
pip install chromadb sentence-transformers

# 完整安装
pip install chromadb sentence-transformers torch
```

---

## 导入语句

```python
# 核心导入
from kernel.vector_db import (
    create_vector_db_async,
    create_vector_db,
    VectorDBBase,
    VectorDocument,
    QueryResult,
    CollectionInfo
)

# 具体实现
from kernel.vector_db import ChromaDBImpl

# 工具函数
from kernel.vector_db import (
    register_vector_db,
    list_supported_databases
)
```

---

## 快速诊断

### 问题：无法连接数据库

```python
# 1. 检查配置
print(config)

# 2. 测试连接
try:
    db = await create_vector_db_async('chromadb', config)
    is_healthy = await db.health_check()
    print(f"健康状态: {is_healthy}")
except Exception as e:
    print(f"连接失败: {e}")
```

### 问题：查询返回空结果

```python
# 1. 检查集合是否存在
exists = await db.collection_exists('my_collection')
print(f"集合存在: {exists}")

# 2. 检查文档数量
count = await db.count_documents('my_collection')
print(f"文档数量: {count}")

# 3. 移除过滤条件测试
results = await db.query_similar(
    collection_name='my_collection',
    query_vector=vec,
    top_k=10,
    filter_metadata=None  # 移除过滤
)
print(f"结果数量: {len(results)}")
```

### 问题：向量维度不匹配

```python
# 确保使用相同的嵌入模型
model = SentenceTransformer('all-MiniLM-L6-v2')  # 固定模型

# 检查向量维度
vec = model.encode("测试文本")
print(f"向量维度: {len(vec)}")  # 应该一致
```

---

## 完整示例

```python
import asyncio
from kernel.vector_db import create_vector_db_async, VectorDocument

async def main():
    # 1. 初始化
    db = await create_vector_db_async('chromadb', {
        'persist_directory': './data/chroma'
    })
    
    # 2. 创建集合
    if not await db.collection_exists('articles'):
        await db.create_collection('articles')
        print("✓ 集合已创建")
    
    # 3. 添加文档
    documents = [
        VectorDocument(
            id=f'article_{i}',
            content=f'文章内容 {i}',
            vector=[0.1 * i, 0.2 * i, 0.3 * i],
            metadata={'category': 'tech', 'index': i}
        )
        for i in range(10)
    ]
    await db.add_documents('articles', documents)
    print(f"✓ 已添加 {len(documents)} 个文档")
    
    # 4. 查询
    results = await db.query_similar(
        collection_name='articles',
        query_vector=[0.5, 1.0, 1.5],
        top_k=3
    )
    
    print(f"✓ 查询结果:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result.id} (相似度: {result.score:.4f})")
    
    # 5. 统计
    count = await db.count_documents('articles')
    print(f"✓ 总文档数: {count}")
    
    # 6. 清理
    await db.close()
    print("✓ 数据库已关闭")

if __name__ == '__main__':
    asyncio.run(main())
```

---

## 相关链接

- [完整文档](README.md)
- [API 参考](API_REFERENCE.md)
- [最佳实践](BEST_PRACTICES.md)
- [配置指南](CONFIGURATION_GUIDE.md)
