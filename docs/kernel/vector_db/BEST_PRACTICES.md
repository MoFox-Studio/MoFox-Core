# Vector DB 最佳实践指南

## 目录

- [集合设计](#集合设计)
- [文档管理](#文档管理)
- [查询优化](#查询优化)
- [性能优化](#性能优化)
- [错误处理](#错误处理)
- [安全实践](#安全实践)
- [生产环境建议](#生产环境建议)

---

## 集合设计

### 命名规范

✅ **推荐做法**:

```python
# 使用清晰、描述性的名称
await db.create_collection('user_chat_history')
await db.create_collection('product_embeddings')
await db.create_collection('document_knowledge_base')
await db.create_collection('customer_feedback_2026')

# 使用下划线分隔单词
await db.create_collection('ai_model_outputs')

# 包含上下文信息
await db.create_collection('support_tickets_embeddings')
```

❌ **避免**:

```python
# 过于简短或模糊
await db.create_collection('data')
await db.create_collection('temp')
await db.create_collection('collection1')

# 使用特殊字符
await db.create_collection('user-data')  # 使用下划线而非连字符
await db.create_collection('user.data')  # 避免点号
```

### 集合粒度

**按用途分离**:

```python
# 不同用途使用不同集合
await db.create_collection('product_descriptions')  # 产品信息
await db.create_collection('user_queries')          # 用户查询
await db.create_collection('support_articles')      # 支持文档
```

**避免过度拆分**:

```python
# ❌ 过度拆分
await db.create_collection('product_descriptions_electronics')
await db.create_collection('product_descriptions_clothing')
await db.create_collection('product_descriptions_food')

# ✅ 使用元数据过滤
await db.create_collection('product_descriptions')
# 添加文档时使用 metadata={'category': 'electronics'}
```

### 集合生命周期管理

```python
async def setup_collections(db):
    """初始化应用所需的集合"""
    collections = {
        'documents': {'dimension': 384},
        'user_embeddings': {'dimension': 768},
        'knowledge_base': {'dimension': 384}
    }
    
    for name, config in collections.items():
        if not await db.collection_exists(name):
            await db.create_collection(name, **config)
            logger.info(f"创建集合: {name}")
        else:
            logger.info(f"集合已存在: {name}")

async def cleanup_old_collections(db, prefix='temp_'):
    """清理临时集合"""
    all_collections = await db.list_collections()
    temp_collections = [c for c in all_collections if c.startswith(prefix)]
    
    for collection in temp_collections:
        await db.delete_collection(collection)
        logger.info(f"删除临时集合: {collection}")
```

---

## 文档管理

### 文档ID设计

**使用有意义的ID**:

```python
# ✅ 推荐：使用有意义的ID
VectorDocument(
    id='user_12345_query_20260106_001',
    content='...'
)

VectorDocument(
    id='article_ai_basics_v1',
    content='...'
)

VectorDocument(
    id=f'doc_{timestamp}_{uuid.uuid4().hex[:8]}',
    content='...'
)
```

**确保ID唯一性**:

```python
import uuid
from datetime import datetime

def generate_document_id(prefix='doc'):
    """生成唯一文档ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    unique_id = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{unique_id}"

doc = VectorDocument(
    id=generate_document_id('article'),
    content='...'
)
```

### 元数据设计

**结构化元数据**:

```python
# ✅ 良好的元数据设计
VectorDocument(
    id='doc_001',
    content='人工智能技术发展',
    vector=[...],
    metadata={
        # 分类信息
        'category': 'technology',
        'subcategory': 'ai',
        'tags': ['machine-learning', 'neural-networks'],
        
        # 来源信息
        'source': 'wikipedia',
        'url': 'https://example.com/ai',
        'author': 'Zhang San',
        
        # 时间信息
        'created_at': '2026-01-06T10:00:00Z',
        'updated_at': '2026-01-06T15:30:00Z',
        
        # 质量指标
        'quality_score': 0.95,
        'verified': True,
        
        # 访问控制
        'visibility': 'public',
        'user_id': 'user_12345',
        
        # 语言和区域
        'language': 'zh',
        'region': 'CN'
    }
)
```

**元数据类型注意事项**:

```python
# ✅ 使用基本类型
metadata = {
    'count': 42,              # int
    'score': 0.95,            # float
    'is_active': True,        # bool
    'name': 'document',       # str
    'tags': ['ai', 'ml']      # list of str
}

# ❌ 避免复杂对象
metadata = {
    'created_at': datetime.now(),  # 使用 ISO 字符串
    'user': User(),                # 使用 user_id 字符串
    'config': {'nested': {...}}    # 扁平化结构
}
```

### 批量操作

**批量添加文档**:

```python
# ✅ 推荐：批量操作
documents = [
    VectorDocument(id=f'doc_{i}', content=text, vector=vec)
    for i, (text, vec) in enumerate(data)
]
await db.add_documents('collection', documents)

# ❌ 避免：逐个添加
for doc in documents:
    await db.add_documents('collection', [doc])  # 效率低
```

**分批处理大量文档**:

```python
async def add_documents_in_batches(
    db, collection_name, documents, batch_size=100
):
    """分批添加文档"""
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        await db.add_documents(collection_name, batch)
        logger.info(f"已添加 {i + len(batch)}/{len(documents)} 个文档")
        
        # 可选：短暂延迟避免过载
        await asyncio.sleep(0.1)

# 使用示例
documents = [...]  # 10000个文档
await add_documents_in_batches(db, 'large_collection', documents)
```

### 文档更新策略

```python
async def update_or_add_document(db, collection_name, doc):
    """更新文档，如果不存在则添加"""
    existing = await db.get_document(collection_name, doc.id)
    
    if existing:
        await db.update_documents(collection_name, [doc])
        logger.info(f"更新文档: {doc.id}")
    else:
        await db.add_documents(collection_name, [doc])
        logger.info(f"添加文档: {doc.id}")

async def bulk_upsert(db, collection_name, documents):
    """批量更新或插入"""
    # 检查哪些文档已存在
    existing_ids = set()
    for doc in documents:
        if await db.get_document(collection_name, doc.id):
            existing_ids.add(doc.id)
    
    # 分别处理更新和插入
    to_update = [d for d in documents if d.id in existing_ids]
    to_add = [d for d in documents if d.id not in existing_ids]
    
    if to_update:
        await db.update_documents(collection_name, to_update)
    if to_add:
        await db.add_documents(collection_name, to_add)
    
    logger.info(f"更新 {len(to_update)} 个, 添加 {len(to_add)} 个文档")
```

---

## 查询优化

### 选择合适的 top_k

```python
# ✅ 根据用途选择合适的 top_k
# 精确匹配：较小的 top_k
results = await db.query_similar(
    collection_name='products',
    query_vector=vec,
    top_k=3  # 只需要最相关的几个
)

# 推荐系统：适中的 top_k
recommendations = await db.query_similar(
    collection_name='items',
    query_vector=user_vec,
    top_k=20  # 需要一定数量的候选
)

# 搜索引擎：较大的 top_k
search_results = await db.query_similar(
    collection_name='documents',
    query_text=query,
    top_k=100  # 后续会进行重排序
)
```

### 使用元数据过滤

```python
# ✅ 先过滤再查询，提升效率
results = await db.query_similar(
    collection_name='articles',
    query_vector=vec,
    top_k=10,
    filter_metadata={
        'language': 'zh',
        'published': True,
        'category': 'technology'
    }
)

# 组合过滤条件
results = await db.query_similar(
    collection_name='products',
    query_vector=vec,
    top_k=10,
    filter_metadata={
        'in_stock': True,
        'price_range': 'medium',
        'brand': 'Apple'
    }
)
```

### 批量查询

```python
# ✅ 使用批量查询处理多个请求
user_queries = [query1_vec, query2_vec, query3_vec]
batch_results = await db.batch_query_similar(
    collection_name='knowledge_base',
    query_vectors=user_queries,
    top_k=5
)

# 处理结果
for i, results in enumerate(batch_results):
    print(f"查询 {i+1} 的结果:")
    for result in results:
        print(f"  {result.id}: {result.score}")
```

### 结果后处理

```python
async def query_with_score_threshold(
    db, collection_name, query_vector, top_k=10, min_score=0.7
):
    """查询并过滤低分结果"""
    results = await db.query_similar(
        collection_name=collection_name,
        query_vector=query_vector,
        top_k=top_k
    )
    
    # 过滤低分结果
    filtered = [r for r in results if r.score >= min_score]
    return filtered

async def query_with_diversity(
    db, collection_name, query_vector, top_k=10, diversity_threshold=0.8
):
    """查询并确保结果多样性"""
    results = await db.query_similar(
        collection_name=collection_name,
        query_vector=query_vector,
        top_k=top_k * 2  # 获取更多候选
    )
    
    # 去重：移除过于相似的结果
    diverse_results = []
    for result in results:
        is_diverse = True
        for existing in diverse_results:
            if result.score - existing.score < diversity_threshold:
                is_diverse = False
                break
        if is_diverse:
            diverse_results.append(result)
        if len(diverse_results) >= top_k:
            break
    
    return diverse_results
```

---

## 性能优化

### 向量维度选择

```python
# 不同任务选择合适的向量维度
embedding_models = {
    'lightweight': {  # 适用于移动端、实时系统
        'model': 'all-MiniLM-L6-v2',
        'dimension': 384
    },
    'balanced': {     # 适用于一般应用
        'model': 'all-mpnet-base-v2',
        'dimension': 768
    },
    'high_quality': { # 适用于高精度需求
        'model': 'all-mpnet-large-v2',
        'dimension': 1024
    }
}
```

### 缓存策略

```python
from functools import lru_cache
import hashlib

class VectorDBCache:
    """向量数据库查询缓存"""
    
    def __init__(self, db, cache_size=1000):
        self.db = db
        self.cache = {}
        self.cache_size = cache_size
    
    def _make_cache_key(self, collection, query_vector, top_k, metadata):
        """生成缓存键"""
        key_data = f"{collection}_{query_vector}_{top_k}_{metadata}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def query_similar_cached(
        self, collection_name, query_vector, top_k=10, 
        filter_metadata=None, cache_ttl=300
    ):
        """带缓存的查询"""
        cache_key = self._make_cache_key(
            collection_name, str(query_vector), top_k, filter_metadata
        )
        
        # 检查缓存
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if time.time() - timestamp < cache_ttl:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_result
        
        # 查询数据库
        results = await self.db.query_similar(
            collection_name=collection_name,
            query_vector=query_vector,
            top_k=top_k,
            filter_metadata=filter_metadata
        )
        
        # 更新缓存
        self.cache[cache_key] = (results, time.time())
        
        # 限制缓存大小
        if len(self.cache) > self.cache_size:
            # 删除最旧的条目
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        return results
```

### 连接池管理

```python
class VectorDBPool:
    """向量数据库连接池"""
    
    def __init__(self, config, pool_size=5):
        self.config = config
        self.pool_size = pool_size
        self.connections = []
        self.available = asyncio.Queue()
    
    async def initialize(self):
        """初始化连接池"""
        for _ in range(self.pool_size):
            db = await create_vector_db_async('chromadb', self.config)
            self.connections.append(db)
            await self.available.put(db)
    
    async def acquire(self):
        """获取连接"""
        return await self.available.get()
    
    async def release(self, db):
        """释放连接"""
        await self.available.put(db)
    
    async def close_all(self):
        """关闭所有连接"""
        for db in self.connections:
            await db.close()
    
    async def execute(self, func, *args, **kwargs):
        """执行操作"""
        db = await self.acquire()
        try:
            return await func(db, *args, **kwargs)
        finally:
            await self.release(db)

# 使用示例
pool = VectorDBPool(config, pool_size=10)
await pool.initialize()

# 并发查询
results = await asyncio.gather(*[
    pool.execute(
        lambda db: db.query_similar('docs', vec, top_k=5)
    )
    for vec in query_vectors
])
```

### 定期维护

```python
async def maintenance_routine(db, collection_name):
    """定期维护任务"""
    # 1. 清理过期文档
    all_docs = await db.count_documents(collection_name)
    logger.info(f"集合 {collection_name} 共有 {all_docs} 个文档")
    
    # 2. 检查集合健康状态
    info = await db.get_collection_info(collection_name)
    if info:
        logger.info(f"集合信息: {info}")
    
    # 3. 定期优化（如果支持）
    # 某些数据库可能需要定期重建索引
    pass

# 使用 APScheduler 定时执行
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(
    maintenance_routine,
    'interval',
    hours=24,
    args=[db, 'main_collection']
)
scheduler.start()
```

---

## 错误处理

### 完善的异常处理

```python
from kernel.vector_db import create_vector_db_async

async def safe_database_operation():
    """安全的数据库操作"""
    db = None
    try:
        # 初始化
        db = await create_vector_db_async('chromadb', config)
        
        # 检查健康状态
        if not await db.health_check():
            logger.error("数据库健康检查失败")
            return None
        
        # 执行操作
        results = await db.query_similar(...)
        return results
        
    except ConnectionError as e:
        logger.error(f"数据库连接失败: {e}")
        # 尝试重连
        await asyncio.sleep(1)
        return await safe_database_operation()
        
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        raise
        
    except KeyError as e:
        logger.error(f"集合不存在: {e}")
        # 尝试创建集合
        await db.create_collection(collection_name)
        
    except Exception as e:
        logger.exception(f"未知错误: {e}")
        raise
        
    finally:
        if db:
            await db.close()
```

### 重试机制

```python
import asyncio
from functools import wraps

def retry_on_failure(max_retries=3, delay=1, backoff=2):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (ConnectionError, TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"操作失败 (尝试 {attempt + 1}/{max_retries}), "
                            f"等待 {current_delay}秒后重试: {e}"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"操作最终失败: {e}")
            
            raise last_exception
        return wrapper
    return decorator

# 使用示例
@retry_on_failure(max_retries=3, delay=1, backoff=2)
async def query_with_retry(db, collection, query_vec):
    """带重试的查询"""
    return await db.query_similar(
        collection_name=collection,
        query_vector=query_vec,
        top_k=10
    )
```

### 优雅降级

```python
async def query_with_fallback(
    db, collection_name, query_vector, top_k=10
):
    """带降级策略的查询"""
    try:
        # 尝试向量查询
        results = await db.query_similar(
            collection_name=collection_name,
            query_vector=query_vector,
            top_k=top_k
        )
        return results
        
    except ConnectionError:
        logger.warning("向量数据库不可用，使用缓存结果")
        # 降级到缓存
        return get_cached_results(query_vector)
        
    except Exception as e:
        logger.error(f"查询失败: {e}, 返回默认结果")
        # 返回默认结果
        return get_default_results()
```

---

## 安全实践

### 输入验证

```python
def validate_document(doc: VectorDocument) -> bool:
    """验证文档数据"""
    # 检查ID
    if not doc.id or not isinstance(doc.id, str):
        raise ValueError("文档ID必须是非空字符串")
    
    # 检查向量
    if doc.vector:
        if not isinstance(doc.vector, list):
            raise ValueError("向量必须是列表")
        if not all(isinstance(x, (int, float)) for x in doc.vector):
            raise ValueError("向量元素必须是数字")
        if len(doc.vector) == 0:
            raise ValueError("向量不能为空")
    
    # 检查内容
    if doc.content and not isinstance(doc.content, str):
        raise ValueError("内容必须是字符串")
    
    # 检查元数据
    if doc.metadata and not isinstance(doc.metadata, dict):
        raise ValueError("元数据必须是字典")
    
    return True

async def safe_add_documents(db, collection_name, documents):
    """安全地添加文档"""
    # 验证所有文档
    for doc in documents:
        validate_document(doc)
    
    # 添加文档
    return await db.add_documents(collection_name, documents)
```

### 访问控制

```python
class SecureVectorDB:
    """带访问控制的向量数据库包装器"""
    
    def __init__(self, db, user_permissions):
        self.db = db
        self.user_permissions = user_permissions
    
    def _check_permission(self, user_id, collection_name, action):
        """检查权限"""
        perms = self.user_permissions.get(user_id, {})
        collection_perms = perms.get(collection_name, [])
        return action in collection_perms
    
    async def query_similar(
        self, user_id, collection_name, **kwargs
    ):
        """带权限检查的查询"""
        if not self._check_permission(user_id, collection_name, 'read'):
            raise PermissionError(
                f"用户 {user_id} 无权读取集合 {collection_name}"
            )
        
        results = await self.db.query_similar(
            collection_name=collection_name,
            **kwargs
        )
        
        # 过滤结果（基于用户权限）
        return self._filter_results(user_id, results)
    
    def _filter_results(self, user_id, results):
        """过滤结果"""
        # 根据用户权限过滤结果中的敏感数据
        filtered = []
        for result in results:
            if result.metadata.get('visibility') == 'public':
                filtered.append(result)
            elif result.metadata.get('owner_id') == user_id:
                filtered.append(result)
        return filtered
```

### 数据脱敏

```python
def sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """清理元数据中的敏感信息"""
    sensitive_keys = ['password', 'token', 'api_key', 'secret']
    
    sanitized = {}
    for key, value in metadata.items():
        if any(sk in key.lower() for sk in sensitive_keys):
            sanitized[key] = '***REDACTED***'
        else:
            sanitized[key] = value
    
    return sanitized

async def add_documents_safely(db, collection_name, documents):
    """安全添加文档（自动脱敏）"""
    safe_documents = []
    for doc in documents:
        safe_doc = VectorDocument(
            id=doc.id,
            content=doc.content,
            vector=doc.vector,
            metadata=sanitize_metadata(doc.metadata) if doc.metadata else None
        )
        safe_documents.append(safe_doc)
    
    return await db.add_documents(collection_name, safe_documents)
```

---

## 生产环境建议

### 配置管理

```python
# config/vector_db.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class VectorDBConfig:
    """向量数据库配置"""
    db_type: str = 'chromadb'
    client_type: str = 'persistent'
    persist_directory: Optional[str] = None
    host: str = 'localhost'
    port: int = 8000
    
    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        import os
        return cls(
            db_type=os.getenv('VECTOR_DB_TYPE', 'chromadb'),
            client_type=os.getenv('VECTOR_DB_CLIENT_TYPE', 'persistent'),
            persist_directory=os.getenv('VECTOR_DB_PATH', './data/chroma'),
            host=os.getenv('VECTOR_DB_HOST', 'localhost'),
            port=int(os.getenv('VECTOR_DB_PORT', '8000'))
        )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'client_type': self.client_type,
            'persist_directory': self.persist_directory,
            'host': self.host,
            'port': self.port
        }

# 使用
config = VectorDBConfig.from_env()
db = await create_vector_db_async(config.db_type, config.to_dict())
```

### 监控和日志

```python
import time
from functools import wraps

class VectorDBMonitor:
    """向量数据库监控器"""
    
    def __init__(self, db):
        self.db = db
        self.metrics = {
            'query_count': 0,
            'query_total_time': 0,
            'add_count': 0,
            'error_count': 0
        }
    
    def track_operation(self, operation_name):
        """跟踪操作性能"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    self.metrics[f'{operation_name}_count'] += 1
                    elapsed = time.time() - start_time
                    self.metrics[f'{operation_name}_total_time'] = \
                        self.metrics.get(f'{operation_name}_total_time', 0) + elapsed
                    
                    logger.info(
                        f"{operation_name} 完成，耗时: {elapsed:.3f}秒"
                    )
                    return result
                except Exception as e:
                    self.metrics['error_count'] += 1
                    logger.error(f"{operation_name} 失败: {e}")
                    raise
            return wrapper
        return decorator
    
    async def query_similar(self, *args, **kwargs):
        """监控查询操作"""
        @self.track_operation('query')
        async def _query():
            return await self.db.query_similar(*args, **kwargs)
        return await _query()
    
    def get_metrics(self):
        """获取性能指标"""
        metrics = self.metrics.copy()
        if metrics['query_count'] > 0:
            metrics['avg_query_time'] = \
                metrics['query_total_time'] / metrics['query_count']
        return metrics

# 使用
monitored_db = VectorDBMonitor(db)
results = await monitored_db.query_similar(...)
print(monitored_db.get_metrics())
```

### 备份和恢复

```python
import shutil
from datetime import datetime
from pathlib import Path

class VectorDBBackup:
    """向量数据库备份管理"""
    
    def __init__(self, persist_directory, backup_directory):
        self.persist_dir = Path(persist_directory)
        self.backup_dir = Path(backup_directory)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def create_backup(self):
        """创建备份"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.backup_dir / f"chroma_backup_{timestamp}"
        
        logger.info(f"开始备份到 {backup_path}")
        shutil.copytree(self.persist_dir, backup_path)
        logger.info("备份完成")
        
        return backup_path
    
    def restore_backup(self, backup_name):
        """恢复备份"""
        backup_path = self.backup_dir / backup_name
        
        if not backup_path.exists():
            raise FileNotFoundError(f"备份不存在: {backup_path}")
        
        logger.info(f"开始从 {backup_path} 恢复")
        
        # 删除当前数据
        if self.persist_dir.exists():
            shutil.rmtree(self.persist_dir)
        
        # 恢复备份
        shutil.copytree(backup_path, self.persist_dir)
        logger.info("恢复完成")
    
    def list_backups(self):
        """列出所有备份"""
        backups = sorted(
            [d.name for d in self.backup_dir.iterdir() if d.is_dir()],
            reverse=True
        )
        return backups
    
    def cleanup_old_backups(self, keep_count=5):
        """清理旧备份"""
        backups = self.list_backups()
        
        for backup in backups[keep_count:]:
            backup_path = self.backup_dir / backup
            shutil.rmtree(backup_path)
            logger.info(f"删除旧备份: {backup}")

# 使用
backup_manager = VectorDBBackup(
    persist_directory='./data/chroma',
    backup_directory='./backups/chroma'
)

# 定期备份
backup_manager.create_backup()
backup_manager.cleanup_old_backups(keep_count=5)
```

### 健康检查端点

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/health/vector-db")
async def check_vector_db_health():
    """向量数据库健康检查端点"""
    try:
        is_healthy = await db.health_check()
        
        if is_healthy:
            collections = await db.list_collections()
            collection_info = {}
            
            for collection_name in collections:
                info = await db.get_collection_info(collection_name)
                if info:
                    collection_info[collection_name] = {
                        'count': info.count,
                        'dimension': info.dimension
                    }
            
            return {
                'status': 'healthy',
                'collections': collection_info,
                'timestamp': datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=503, detail="数据库不健康")
            
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(status_code=503, detail=str(e))
```

---

## 总结

遵循以上最佳实践，可以确保：

✅ **性能优化**: 批量操作、缓存、连接池  
✅ **可靠性**: 错误处理、重试机制、健康检查  
✅ **安全性**: 输入验证、访问控制、数据脱敏  
✅ **可维护性**: 监控日志、备份恢复、配置管理  
✅ **可扩展性**: 良好的设计模式和架构选择  
