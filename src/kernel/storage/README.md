# MoFox Storage 存储模块

统一的JSON本地持久化存储系统，提供安全、高效、易用的数据存储功能。

## 特性

- 🔒 **原子写入**：先写临时文件再重命名，保证数据完整性
- 💾 **自动备份**：写入前自动备份，支持多版本保留
- 🔄 **线程安全**：内置锁机制，支持多线程并发访问
- ✅ **数据验证**：支持自定义验证函数
- 📦 **压缩支持**：内置gzip压缩功能
- 🎯 **类型专用**：针对字典、列表、日志等不同场景的专用存储器
- 🛡️ **异常处理**：完善的异常体系，便于错误处理
- 📝 **Logger 集成**：与 Logger 模块无缝集成，日志直接存储为 JSON

## 安装

```python
# 已集成在 MoFox kernel 层
from kernel.storage import JSONStore, DictJSONStore, ListJSONStore, LogStore
from kernel.logger.storage_integration import LoggerWithStorage  # Logger 集成
```

## 🎯 新功能：与 Logger 集成（推荐）

Storage 模块现已与 Logger 模块深度集成！应用程序的所有日志都可以自动存储为 JSON 格式：

```python
from kernel.logger.storage_integration import LoggerWithStorage

# 一行代码启动 Logger + Storage 集成
logger_system = LoggerWithStorage(app_name="myapp")

# 获取日志器
logger = logger_system.get_logger("app.main")

# 记录日志（自动保存到 JSON）
logger.info("应用启动")
logger.error("发生错误")

# 查询日志
stats = logger_system.get_logs(days=1)
errors = logger_system.get_error_logs(days=7)
```

**集成优势：**
- ✅ 日志自动存储为 JSON 格式
- ✅ 自动元数据提取（request_id, session_id, user_id）
- ✅ 完整的异常堆栈跟踪
- ✅ 灵活的日志查询和过滤
- ✅ 同时支持控制台和文件存储

**查看更多：**
- 📖 [Logger-Storage 集成指南](../../docs/kernel/logger/LOGGER_STORAGE_INTEGRATION.md)
- 🚀 [快速参考](../../docs/kernel/logger/QUICK_REFERENCE.md)
- 💻 [集成示例](../logger/storage_integration.py)

---

## 快速开始

### 1. 基本JSON存储

```python
from kernel.storage import JSONStore

# 创建存储器
store = JSONStore("data/config.json")

# 写入数据
config = {
    "app_name": "MoFox",
    "version": "1.0.0",
    "settings": {"theme": "dark"}
}
store.write(config)

# 读取数据
data = store.read()
print(data)

# 更新数据
def update_version(data):
    data["version"] = "1.1.0"
    return data

store.update(update_version)
```

### 2. 字典存储

```python
from kernel.storage import DictJSONStore

# 创建字典存储器
settings = DictJSONStore("data/settings.json")

# 设置键值对
settings.set("theme", "dark")
settings.set("font_size", 14)

# 获取值
theme = settings.get("theme")
font_size = settings.get("font_size", default=12)

# 检查键是否存在
if settings.has_key("theme"):
    print("主题已设置")

# 获取所有键
keys = settings.keys()
values = settings.values()
items = settings.items()

# 删除键
settings.delete_key("font_size")

# 合并数据
settings.merge({"new_key": "new_value"})
```

### 3. 列表存储

```python
from kernel.storage import ListJSONStore

# 创建列表存储器
tasks = ListJSONStore("data/tasks.json")

# 添加项目
tasks.append({"id": 1, "title": "完成文档", "done": False})

# 批量添加
tasks.extend([
    {"id": 2, "title": "修复bug", "done": False},
    {"id": 3, "title": "代码审查", "done": True}
])

# 获取列表长度
count = tasks.length()

# 获取指定项
first_task = tasks.get_at(0)

# 移除项目
tasks.remove({"id": 1, "title": "完成文档", "done": False})
tasks.remove_at(0)  # 按索引移除

# 过滤
tasks.filter(lambda task: not task["done"])

# 清空列表
tasks.clear()
```

### 4. 日志存储

```python
from kernel.storage import LogStore
from datetime import datetime

# 创建日志存储器
log_store = LogStore(
    directory="logs/app",
    prefix="application",
    max_entries_per_file=1000,  # 每个文件最多1000条
    auto_rotate=True             # 自动轮转
)

# 添加日志（自动添加时间戳）
log_store.add_log({
    "level": "INFO",
    "message": "应用启动",
    "module": "main"
})

log_store.add_log({
    "level": "ERROR",
    "message": "数据库连接失败",
    "module": "database",
    "error": "Connection timeout"
})

# 获取所有日志
all_logs = log_store.get_logs()

# 按时间范围获取
from datetime import timedelta
start = datetime.now() - timedelta(days=7)
recent_logs = log_store.get_logs(start_date=start)

# 过滤特定级别的日志
error_logs = log_store.get_logs(
    filter_func=lambda log: log.get("level") == "ERROR"
)

# 清理旧日志（保留30天）
deleted_count = log_store.clear_old_logs(days=30)
```

## 配置选项

### JSONStore 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file_path` | str/Path | 必需 | JSON文件路径 |
| `auto_create` | bool | True | 文件不存在时自动创建 |
| `auto_backup` | bool | True | 写入前自动备份 |
| `max_backups` | int | 5 | 最大备份数量 |
| `indent` | int/None | 2 | JSON缩进级别 |
| `encoding` | str | 'utf-8' | 文件编码 |
| `validate_func` | Callable | None | 数据验证函数 |

### LogStore 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `directory` | str/Path | 必需 | 日志存储目录 |
| `prefix` | str | "log" | 文件名前缀 |
| `max_entries_per_file` | int | 1000 | 每个文件最大条目数 |
| `auto_rotate` | bool | True | 是否自动轮转 |

## 高级功能

### 原子写入

所有写操作都是原子性的，先写入临时文件，再重命名覆盖原文件：

```python
store = JSONStore("data/important.json")
store.write(data)  # 原子写入，保证数据完整性
```

### 自动备份

```python
store = JSONStore(
    "data/config.json",
    auto_backup=True,      # 启用自动备份
    max_backups=5          # 保留5个备份
)

# 每次写入都会自动创建备份
store.write(data)  # 创建 config_backup_20260106_120000.json
```

### 数据验证

```python
def validate_config(data):
    """验证配置数据"""
    required_keys = ["app_name", "version"]
    return all(key in data for key in required_keys)

store = JSONStore(
    "data/config.json",
    validate_func=validate_config
)

# 写入时自动验证
try:
    store.write({"app_name": "MoFox"})  # 缺少version，会抛出异常
except ValidationError as e:
    print(f"验证失败: {e}")
```

### 压缩和解压

```python
store = JSONStore("data/large_file.json")

# 压缩文件
compressed_path = store.compress()  # 生成 large_file.json.gz
print(f"压缩到: {compressed_path}")

# 解压文件
store.decompress("data/large_file.json.gz")
```

### 线程安全

```python
import threading

store = JSONStore("data/counter.json")

def increment():
    for _ in range(100):
        def update(data):
            data["count"] = data.get("count", 0) + 1
            return data
        store.update(update)

# 多线程并发更新，内置锁保证安全
threads = [threading.Thread(target=increment) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

result = store.read()
print(f"最终计数: {result['count']}")  # 应该是 1000
```

### 默认值处理

```python
store = JSONStore("data/optional.json", auto_create=False)

# 文件不存在时返回默认值，而不是抛出异常
data = store.read(default={"status": "not_initialized"})
```

## 异常处理

```python
from kernel.storage import JSONStoreError, FileNotFoundError, ValidationError

try:
    store = JSONStore("data/file.json", auto_create=False)
    data = store.read()
except FileNotFoundError as e:
    print(f"文件不存在: {e}")
except JSONStoreError as e:
    print(f"存储错误: {e}")
```

## 实际应用场景

### 1. 应用配置管理

```python
from kernel.storage import DictJSONStore

class Config:
    def __init__(self):
        self.store = DictJSONStore("config/app.json")
    
    def get(self, key, default=None):
        return self.store.get(key, default)
    
    def set(self, key, value):
        self.store.set(key, value)
    
    def reload(self):
        # 从文件重新加载配置
        self.store = DictJSONStore("config/app.json")

# 使用
config = Config()
config.set("database_url", "postgresql://localhost/mydb")
db_url = config.get("database_url")
```

### 2. 任务队列

```python
from kernel.storage import ListJSONStore

class TaskQueue:
    def __init__(self):
        self.store = ListJSONStore("data/tasks.json")
    
    def add_task(self, task):
        self.store.append(task)
    
    def get_pending_tasks(self):
        tasks = self.store.read(default=[])
        return [t for t in tasks if not t.get("completed")]
    
    def mark_completed(self, task_id):
        def update(tasks):
            for task in tasks:
                if task.get("id") == task_id:
                    task["completed"] = True
            return tasks
        self.store.update(update)

# 使用
queue = TaskQueue()
queue.add_task({"id": 1, "name": "Process data", "completed": False})
pending = queue.get_pending_tasks()
```

### 3. 应用日志持久化

```python
from kernel.storage import LogStore
from kernel.logger import get_logger

class PersistentLogger:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.store = LogStore("data/persistent_logs")
    
    def log(self, level, message, **kwargs):
        # 同时写入日志系统和持久化存储
        getattr(self.logger, level.lower())(message)
        self.store.add_log({
            "level": level,
            "message": message,
            **kwargs
        })
    
    def get_error_logs(self):
        return self.store.get_logs(
            filter_func=lambda log: log.get("level") == "ERROR"
        )

# 使用
logger = PersistentLogger()
logger.log("ERROR", "Database connection failed", error_code=500)
errors = logger.get_error_logs()
```

### 4. 用户会话管理

```python
from kernel.storage import DictJSONStore
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self):
        self.store = DictJSONStore("data/sessions.json")
    
    def create_session(self, user_id):
        session_id = f"sess_{user_id}_{int(datetime.now().timestamp())}"
        self.store.set(session_id, {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
        })
        return session_id
    
    def get_session(self, session_id):
        return self.store.get(session_id)
    
    def cleanup_expired(self):
        def filter_valid(sessions):
            now = datetime.now()
            return {
                sid: sess for sid, sess in sessions.items()
                if datetime.fromisoformat(sess["expires_at"]) > now
            }
        self.store.update(filter_valid)

# 使用
manager = SessionManager()
session_id = manager.create_session("user123")
session = manager.get_session(session_id)
```

## API 参考

### JSONStore

- `read(default=None)` - 读取数据
- `write(data, validate=True)` - 写入数据
- `update(update_func)` - 更新数据
- `delete(create_backup=True)` - 删除文件
- `exists()` - 检查文件是否存在
- `get_size()` - 获取文件大小
- `compress(output_path=None)` - 压缩文件
- `decompress(compressed_path)` - 解压文件

### DictJSONStore

继承自 JSONStore，额外提供：

- `get(key, default=None)` - 获取值
- `set(key, value)` - 设置值
- `delete_key(key)` - 删除键
- `has_key(key)` - 检查键是否存在
- `keys()` - 获取所有键
- `values()` - 获取所有值
- `items()` - 获取所有键值对
- `clear()` - 清空数据
- `merge(other, overwrite=True)` - 合并数据

### ListJSONStore

继承自 JSONStore，额外提供：

- `append(item)` - 追加项目
- `extend(items)` - 扩展列表
- `remove(item)` - 移除项目
- `remove_at(index)` - 移除指定索引
- `get_at(index, default=None)` - 获取指定项
- `length()` - 获取长度
- `clear()` - 清空列表
- `filter(filter_func)` - 过滤项目

### LogStore

- `add_log(log_entry)` - 添加日志
- `get_logs(start_date=None, end_date=None, filter_func=None)` - 获取日志
- `clear_old_logs(days=30)` - 清理旧日志

## 最佳实践

1. **使用合适的存储器类型**
   - 配置数据 → DictJSONStore
   - 列表数据 → ListJSONStore
   - 日志数据 → LogStore
   - 复杂数据 → JSONStore

2. **启用自动备份**
   ```python
   store = JSONStore("important.json", auto_backup=True, max_backups=5)
   ```

3. **使用数据验证**
   ```python
   store = JSONStore("data.json", validate_func=validate_data)
   ```

4. **处理异常**
   ```python
   try:
       data = store.read()
   except JSONStoreError as e:
       # 处理错误
       pass
   ```

5. **定期清理**
   ```python
   log_store = LogStore("logs")
   log_store.clear_old_logs(days=30)
   ```

## 性能考虑

- ✅ 小到中型数据（< 10MB）：性能优秀
- ⚠️ 大型数据（> 50MB）：考虑使用数据库
- ✅ 并发读取：线程安全，性能良好
- ⚠️ 高频写入：考虑批量操作或缓存

## 许可证

MIT License
