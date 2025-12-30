# Database API

Database operations for plugins.

## Import (In Components)
```python
# Use from component
self.get_config(key, default)  # Configuration
await self.database_query(sql)  # Raw query (advanced)
```

## CRUD Operations (New API)
```python
from src.common.database.api.crud import CRUDBase

# Create
await CRUDBase.create(model_class, **data)

# Read
record = await CRUDBase.read(model_class, id)

# Update
await CRUDBase.update(model_class, id, **data)

# Delete
await CRUDBase.delete(model_class, id)

# Query multiple
records = await CRUDBase.read_all(model_class, filters={})
```

## Best Practices
✅ Use CRUDBase for new code
✅ Use batch operations for multiple records
✅ Enable caching when appropriate
❌ Don't use raw SQL
❌ Don't create direct Session objects
