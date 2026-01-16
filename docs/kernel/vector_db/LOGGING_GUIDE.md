# Vector DB 日志集成说明

## 概述

Vector DB 模块已完全集成 MoFox 的日志系统（`kernel.logger`），提供详细的操作日志记录，便于调试、监控和问题排查。

## 日志级别

Vector DB 使用以下日志级别：

- **DEBUG**: 详细的操作信息（查询结果数量、批量操作详情等）
- **INFO**: 关键操作信息（初始化、集合创建、文档添加等）
- **WARNING**: 警告信息（集合已存在、删除失败等）
- **ERROR**: 错误信息（连接失败、操作异常等）

## 已记录的操作

### 初始化和连接

```python
from kernel.vector_db import create_vector_db_async
from kernel.logger import setup_logger

# 设置日志
setup_logger()

# 创建实例时会记录：
# INFO: 创建向量数据库实例: chromadb
# INFO: 初始化 ChromaDB 实例，配置: {...}
# INFO: 开始初始化 ChromaDB 连接，客户端类型: persistent
# INFO: ChromaDB 连接初始化成功，客户端类型: persistent
db = await create_vector_db_async('chromadb', config)
```

### 集合操作

```python
# 创建集合
# INFO: 创建集合成功: my_collection
await db.create_collection('my_collection')

# 删除集合
# INFO: 删除集合成功: my_collection
await db.delete_collection('my_collection')

# 集合已存在时
# WARNING: 集合已存在: my_collection
await db.create_collection('existing_collection')
```

### 文档操作

```python
# 添加文档
# INFO: 添加 10 个文档到集合 'my_collection'
await db.add_documents('my_collection', documents)

# 更新文档
# INFO: 更新 5 个文档在集合 'my_collection'
await db.update_documents('my_collection', updated_docs)

# 删除文档
# INFO: 删除 3 个文档从集合 'my_collection'
await db.delete_documents('my_collection', ['id1', 'id2', 'id3'])
```

### 查询操作

```python
# 查询相似文档
# DEBUG: 查询集合 'my_collection' 返回 5 个结果
results = await db.query_similar('my_collection', query_vector=vec, top_k=5)

# 批量查询
# DEBUG: 批量查询集合 'my_collection'，3 个查询返回共 15 个结果
batch_results = await db.batch_query_similar('my_collection', query_vectors=vecs)
```

### 健康检查

```python
# 健康检查成功
# DEBUG: 数据库健康检查通过
is_healthy = await db.health_check()

# 健康检查失败
# WARNING: 数据库健康检查失败: Connection refused
is_healthy = await db.health_check()
```

### 关闭连接

```python
# INFO: 关闭 ChromaDB 连接
# DEBUG: ChromaDB 连接已关闭
await db.close()
```

### 错误记录

```python
# 操作失败时的错误日志
# ERROR: 创建集合失败 'my_collection': Permission denied
# ERROR: 添加文档失败 'my_collection': Invalid vector dimension
# ERROR: 查询失败 'my_collection': Collection not found
```

## 配置日志输出

### 基础配置

```python
from kernel.logger import setup_logger

# 使用默认配置
setup_logger()
```

### 自定义配置

```python
from kernel.logger import setup_logger, LoggerConfig

config = LoggerConfig(
    name="vector_db_app",
    level="DEBUG",  # 显示所有日志
    console_enabled=True,
    console_colors=True,  # 彩色输出
    file_enabled=True,
    file_path="logs/vector_db.log",
    file_format="json"  # JSON 格式便于分析
)

setup_logger(config)
```

### 仅控制台输出

```python
config = LoggerConfig(
    level="INFO",
    console_enabled=True,
    console_colors=True,
    file_enabled=False
)
setup_logger(config)
```

### 仅文件输出

```python
config = LoggerConfig(
    level="DEBUG",
    console_enabled=False,
    file_enabled=True,
    file_path="logs/vector_db_detailed.log"
)
setup_logger(config)
```

## 日志输出示例

### 控制台输出（彩色）

```
2026-01-06 10:30:45 [INFO] kernel.vector_db: 创建向量数据库实例: chromadb
2026-01-06 10:30:45 [INFO] kernel.vector_db.chromadb_impl.ChromaDBImpl: 初始化 ChromaDB 实例，配置: {'client_type': 'persistent', 'persist_directory': './data/chroma'}
2026-01-06 10:30:45 [INFO] kernel.vector_db.chromadb_impl.ChromaDBImpl: 开始初始化 ChromaDB 连接，客户端类型: persistent
2026-01-06 10:30:46 [INFO] kernel.vector_db.chromadb_impl.ChromaDBImpl: ChromaDB 连接初始化成功，客户端类型: persistent
2026-01-06 10:30:46 [INFO] kernel.vector_db: 向量数据库实例已初始化: chromadb
2026-01-06 10:30:47 [INFO] kernel.vector_db.chromadb_impl.ChromaDBImpl: 创建集合成功: documents
2026-01-06 10:30:48 [INFO] kernel.vector_db.chromadb_impl.ChromaDBImpl: 添加 100 个文档到集合 'documents'
2026-01-06 10:30:49 [DEBUG] kernel.vector_db.chromadb_impl.ChromaDBImpl: 查询集合 'documents' 返回 10 个结果
```

### JSON 格式输出

```json
{
  "timestamp": "2026-01-06T10:30:45.123456",
  "level": "INFO",
  "logger": "kernel.vector_db",
  "message": "创建向量数据库实例: chromadb",
  "metadata": {}
}
{
  "timestamp": "2026-01-06T10:30:48.456789",
  "level": "INFO",
  "logger": "kernel.vector_db.chromadb_impl.ChromaDBImpl",
  "message": "添加 100 个文档到集合 'documents'",
  "metadata": {}
}
```

## 使用日志进行调试

### 1. 追踪操作流程

通过日志了解操作的执行顺序和状态：

```python
# 设置 DEBUG 级别查看详细信息
config = LoggerConfig(level="DEBUG", console_enabled=True)
setup_logger(config)

db = await create_vector_db_async('chromadb', config)
# 可以看到初始化的详细过程

await db.add_documents('collection', documents)
# 可以看到添加了多少文档

results = await db.query_similar('collection', query_vector=vec)
# 可以看到返回了多少结果
```

### 2. 诊断性能问题

查看操作耗时（如果配置了时间戳）：

```python
# 检查日志时间戳，分析哪些操作耗时较长
2026-01-06 10:30:45.000 [INFO] 开始添加文档...
2026-01-06 10:30:48.500 [INFO] 添加 1000 个文档成功
# 耗时 3.5 秒
```

### 3. 错误排查

当操作失败时，查看错误日志：

```python
try:
    await db.create_collection('my_collection')
except Exception as e:
    # 日志会显示：
    # ERROR: 创建集合失败 'my_collection': Collection already exists
    pass
```

## 与元数据集成

使用日志元数据追踪请求：

```python
from kernel.logger import with_metadata, get_logger

# 添加上下文元数据
with with_metadata(user_id="user123", session_id="sess456"):
    db = await create_vector_db_async('chromadb', config)
    await db.add_documents('user_docs', documents)
    # 日志会包含 user_id 和 session_id
```

## 生产环境建议

### 1. 日志级别

```python
# 开发环境：DEBUG
config = LoggerConfig(level="DEBUG")

# 生产环境：INFO
config = LoggerConfig(level="INFO")

# 高负载环境：WARNING（仅记录警告和错误）
config = LoggerConfig(level="WARNING")
```

### 2. 日志轮转

```python
config = LoggerConfig(
    file_enabled=True,
    file_path="logs/vector_db.log",
    rotation="10 MB",  # 每 10MB 轮转一次
    retention=7  # 保留 7 天
)
```

### 3. 日志分析

使用 JSON 格式便于日志分析工具处理：

```python
config = LoggerConfig(
    file_format="json",
    file_path="logs/vector_db.json"
)
```

然后可以使用工具分析：

```bash
# 统计各类操作数量
cat logs/vector_db.json | jq -r '.message' | sort | uniq -c

# 查找错误日志
cat logs/vector_db.json | jq 'select(.level == "ERROR")'

# 分析查询性能
cat logs/vector_db.json | jq 'select(.message | contains("查询"))'
```

## 示例代码

完整的日志集成示例见：
- [examples/vector_db_logging_demo.py](../../examples/vector_db_logging_demo.py)
- [tests/kernel/vector_db/test_vector_db_logging.py](../../tests/kernel/vector_db/test_vector_db_logging.py)

## 常见问题

### Q: 如何禁用 Vector DB 的日志？

```python
from kernel.logger import get_logger
import logging

# 将 Vector DB 的日志级别设置为 CRITICAL（仅记录严重错误）
logger = get_logger('kernel.vector_db')
logger.setLevel(logging.CRITICAL)
```

### Q: 如何仅记录错误日志？

```python
config = LoggerConfig(level="ERROR")
setup_logger(config)
```

### Q: 日志文件太大怎么办？

```python
config = LoggerConfig(
    file_enabled=True,
    rotation="5 MB",  # 减小轮转大小
    retention=3,      # 减少保留天数
    compression="zip"  # 启用压缩
)
```

## 相关文档

- [Logger 模块文档](../logger/README.md)
- [Vector DB 主文档](README.md)
- [最佳实践](BEST_PRACTICES.md)
