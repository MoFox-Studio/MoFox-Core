# Person API - User and Relationship Information

```python
from src.plugin_system.apis import person_api
```

## Functions
- `get_person_info(person_id, platform="qq")` - Get user information
- `get_relationship(user_id, target_id, platform="qq")` - Get relationship info
- `update_relationship(user_id, target_id, intimacy_value, platform="qq")` - Update intimacy
- `get_all_relationships(user_id, platform="qq")` - Get all relationships
- `add_relationship(user_id, target_id, platform="qq")` - Create new relationship

## Example
```python
# Get user info
user = person_api.get_person_info("123456")
# Returns: {user_id, name, platform, avatar, ...}

# Get relationship
rel = person_api.get_relationship("user1", "user2")
# Returns: {intimacy, last_interaction, ...}

# Update intimacy
person_api.update_relationship("user1", "user2", intimacy_value=0.8)
```
