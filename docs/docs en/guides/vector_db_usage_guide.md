# Unified Vector Database Service Usage Guide

This document explains how to use the newly integrated unified vector database service in the `mmc` project. The service provides a standardized interface for interacting with the underlying vector database (currently ChromaDB) while ensuring code decoupling and future extensibility.

## Core Design Principles

1. **Unified Entry Point**: All operations on the vector database should go through the global singleton `vector_db_service`.
2. **Abstract Interface**: The service follows the interface defined by the `VectorDBBase` abstract base class, making it easy to switch to other vector databases (such as Milvus, FAISS) in the future without modifying business code.
3. **Singleton Pattern**: The entire application shares a single database client instance, avoiding resource waste and management confusion.
4. **Data Isolation**: Use different `collection` names to isolate data from different business modules (such as semantic cache, transient memory). Within a `collection`, use the `metadata` field (such as `chat_id`) to isolate data from different users or sessions.

## How to Use

### 1. Import Service

In any file that needs to use the vector database, simply import the global service instance:

```python
from src.common.vector_db import vector_db_service
```

### 2. Main Operations

The `vector_db_service` object provides all the methods you need, which are all defined in `VectorDBBase`.

#### a. Get or Create Collection

Before operating on data, you need to specify a collection first. If the collection doesn't exist, it will be automatically created.

```python
# Create a collection for semantic cache
vector_db_service.get_or_create_collection(name="semantic_cache")

# Create a collection for instant memory
vector_db_service.get_or_create_collection(
    name="instant_memory",
    metadata={"hnsw:space": "cosine"}  # Can pass implementation-specific parameters
)
```

#### b. Add Data

Use the `add` method to add vectors, documents, and metadata to the specified collection.

```python
collection_name = "instant_memory"
chat_id = "user_123"
message_id = "msg_abc"
embedding_vector = [0.1, 0.2, 0.3, ...]  # Your embedding vector
content = "Hello, this is a test message"

vector_db_service.add(
    collection_name=collection_name,
    embeddings=[embedding_vector],
    documents=[content],
    metadatas=[{
        "chat_id": chat_id,
        "timestamp": 1678886400.0,
        "sender": "user"
    }],
    ids=[message_id]
)
```

#### c. Query Data

Use the `query` method to find similar vectors. You can use `where` clause to filter metadata.

```python
query_vector = [0.11, 0.22, 0.33, ...]  # Vector for querying
collection_name = "instant_memory"
chat_id_to_query = "user_123"

results = vector_db_service.query(
    collection_name=collection_name,
    query_embeddings=[query_vector],
    n_results=5,  # Return top 5 most similar results
    where={"chat_id": chat_id_to_query}  # **Important**: Use where to isolate data from different chats
)

# Structure of results:
# {
#     'ids': [['msg_abc']],
#     'distances': [[0.0123]],
#     'metadatas': [[{'chat_id': 'user_123', ...}]],
#     'embeddings': None,
#     'documents': [['Hello, this is a test message']]
# }
print(results)
```

#### d. Delete Data

You can delete data by `id` or `where` condition.

```python
# Delete by ID
vector_db_service.delete(
    collection_name="instant_memory",
    ids=["msg_abc"]
)

# Delete by where condition (e.g., delete all memories of a user)
vector_db_service.delete(
    collection_name="instant_memory",
    where={"chat_id": "user_123"}
)
```

#### e. Get Collection Count

Use the `count` method to get the total number of entries in a collection.

```python
count = vector_db_service.count(collection_name="semantic_cache")
print(f"Semantic cache collection has {count} entries.")
```

**Note**: The `count` method currently returns the total number of entries in the entire collection and won't filter based on `where` conditions.

### 3. Code Locations

- **Abstract Base Class**: [`src/common/vector_db/base.py`](src/common/vector_db/base.py)
- **ChromaDB Implementation**: [`src/common/vector_db/chromadb_impl.py`](src/common/vector_db/chromadb_impl.py)
- **Service Entry Point**: [`src/common/vector_db/__init__.py`](src/common/vector_db/__init__.py)

---

This comprehensive documentation should help you and other team members use the new vector database service correctly. If you have any questions, please feel free to ask.
