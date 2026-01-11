# Storage 存储模块文档

## 概览

Storage 模块提供统一的JSON本地持久化操作，是 MoFox kernel 层的核心存储组件。该模块提供了安全、高效、易用的JSON文件存储方案，支持CRUD操作、原子写入、自动备份、数据压缩等企业级特性。

### 设计理念

- **原子性**: 使用临时文件+重命名机制保证写入原子性
- **安全性**: 线程安全的并发操作、自动备份、数据验证
- **易用性**: 面向对象的API设计、类型特化、链式操作
- **可靠性**: 异常处理完善、备份恢复机制、压缩归档支持

### 核心特性

✨ **原子写入**: 先写临时文件再重命名，避免数据损坏  
🔒 **线程安全**: 内置锁机制，支持并发读写  
💾 **自动备份**: 写入前自动备份，最多保留N个历史版本  
🗜️ **数据压缩**: 支持gzip压缩，节省存储空间  
✅ **数据验证**: 可自定义验证函数，确保数据完整性  
📦 **类型特化**: 提供字典、列表、日志专用存储器  
🔄 **原子更新**: 读取-修改-写入的原子操作  

---

## 快速开始

### 基础使用

```python
from kernel.storage import JSONStore

# 创建存储器
store = JSONStore('data.json', auto_create=True, auto_backup=True)

# 写入数据
store.write({'name': 'MoFox', 'version': '1.0'})

# 读取数据
data = store.read()
print(data)  # {'name': 'MoFox', 'version': '1.0'}

# 更新数据
store.update(lambda data: {**data, 'updated': True})

# 检查文件信息
print(f"文件大小: {store.get_size()} bytes")
print(f"文件存在: {store.exists()}")
```

### 字典存储器

```python
from kernel.storage import DictJSONStore

# 创建字典存储器
config = DictJSONStore('config.json')

# 键值操作
config.set('database', 'postgresql')
config.set('port', 5432)
config.set('debug', True)

# 读取值
db = config.get('database')  # 'postgresql'
timeout = config.get('timeout', 30)  # 使用默认值

# 检查键
if config.has_key('debug'):
    print("Debug mode enabled")

# 遍历
for key, value in config.items():
    print(f"{key}: {value}")

# 合并配置
config.merge({'host': 'localhost', 'port': 3306}, overwrite=False)

# 删除键
config.delete_key('debug')

# 清空
config.clear()
```

### 列表存储器

```python
from kernel.storage import ListJSONStore

# 创建列表存储器
tasks = ListJSONStore('tasks.json')

# 添加项目
tasks.append({'id': 1, 'title': '学习Python', 'done': False})
tasks.append({'id': 2, 'title': '写代码', 'done': True})

# 批量添加
tasks.extend([
    {'id': 3, 'title': '测试', 'done': False},
    {'id': 4, 'title': '部署', 'done': False}
])

# 获取项目
first_task = tasks.get_at(0)
print(f"列表长度: {tasks.length()}")

# 过滤未完成任务
tasks.filter(lambda task: not task['done'])

# 移除项目
tasks.remove_at(0)

# 清空列表
tasks.clear()
```

### 日志存储器

```python
from kernel.storage import LogStore
from datetime import datetime, timedelta

# 创建日志存储器
logger = LogStore(
    directory='logs',
    prefix='app',
    max_entries_per_file=1000,
    auto_rotate=True
)

# 添加日志
logger.add_log({
    'level': 'INFO',
    'message': '应用启动',
    'user': 'admin'
})

logger.add_log({
    'level': 'ERROR',
    'message': '连接失败',
    'error': 'Connection timeout'
})

# 查询日志
# 获取最近7天的日志
start = datetime.now() - timedelta(days=7)
logs = logger.get_logs(start_date=start)

# 使用过滤器
error_logs = logger.get_logs(
    filter_func=lambda log: log.get('level') == 'ERROR'
)

# 清理30天前的日志
deleted = logger.clear_old_logs(days=30)
print(f"删除了 {deleted} 个旧日志文件")
```

---

## 架构设计

### 类层次结构

```
JSONStore (基础存储器)
├── DictJSONStore (字典存储器)
├── ListJSONStore (列表存储器)
└── LogStore (日志存储器)
```

### 核心组件

#### 1. JSONStore - 基础存储器

通用JSON文件存储器，提供底层的读写、备份、压缩等功能。

**主要方法**:
- `read(default)` - 读取数据
- `write(data)` - 写入数据（原子操作）
- `update(update_func)` - 原子更新
- `delete()` - 删除文件
- `compress()` - 压缩文件
- `decompress()` - 解压文件

#### 2. DictJSONStore - 字典存储器

专门处理字典类型数据，提供键值对操作接口。

**主要方法**:
- `get(key, default)` - 获取值
- `set(key, value)` - 设置值
- `delete_key(key)` - 删除键
- `has_key(key)` - 检查键是否存在
- `keys()` / `values()` / `items()` - 遍历操作
- `merge(other)` - 合并字典
- `clear()` - 清空数据

#### 3. ListJSONStore - 列表存储器

专门处理列表类型数据，提供列表操作接口。

**主要方法**:
- `append(item)` - 追加项目
- `extend(items)` - 扩展列表
- `remove(item)` - 移除项目
- `remove_at(index)` - 按索引移除
- `get_at(index)` - 按索引获取
- `length()` - 获取长度
- `filter(filter_func)` - 过滤项目
- `clear()` - 清空列表

#### 4. LogStore - 日志存储器

专门用于存储日志记录，支持自动轮转、时间范围查询。

**主要方法**:
- `add_log(log_entry)` - 添加日志
- `get_logs(start_date, end_date, filter_func)` - 查询日志
- `clear_old_logs(days)` - 清理旧日志

---

## 高级特性

### 1. 原子写入机制

Storage模块使用"临时文件+原子重命名"机制确保数据完整性：

```python
def _write_data(self, data: Any) -> None:
    # 1. 写入临时文件
    temp_file = self.file_path.with_suffix('.tmp')
    with open(temp_file, 'w', encoding=self.encoding) as f:
        json.dump(data, f, indent=self.indent)
    
    # 2. 原子重命名（操作系统级别保证）
    temp_file.replace(self.file_path)
```

**优势**:
- 避免写入过程中程序崩溃导致数据损坏
- 操作系统级别的原子性保证
- 读写操作互不影响

### 2. 自动备份系统

每次写入前自动创建带时间戳的备份：

```python
store = JSONStore(
    'config.json',
    auto_backup=True,      # 启用自动备份
    max_backups=5          # 保留最近5个备份
)

store.write(data)
# 自动创建: config_backup_20260106_143022.json
```

**备份文件命名规则**: `{原文件名}_backup_{时间戳}.{扩展名}`

### 3. 数据验证

可自定义验证函数确保数据有效性：

```python
def validate_config(data):
    """验证配置数据"""
    if not isinstance(data, dict):
        return False
    required_keys = ['host', 'port', 'database']
    return all(key in data for key in required_keys)

store = JSONStore(
    'config.json',
    validate_func=validate_config
)

try:
    store.write({'host': 'localhost'})  # 验证失败
except ValidationError as e:
    print(f"验证失败: {e}")
```

### 4. 线程安全

所有操作都使用 `threading.Lock` 保护：

```python
import threading

store = DictJSONStore('shared.json')

def worker(worker_id):
    for i in range(100):
        store.set(f'worker_{worker_id}_{i}', {'value': i})

# 多线程并发写入
threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

# 数据完整性得到保证
```

### 5. 原子更新操作

读取-修改-写入过程是原子的：

```python
store = DictJSONStore('counter.json')

# 线程安全的计数器递增
def increment_counter():
    store.update(lambda data: {
        **data,
        'count': data.get('count', 0) + 1
    })

# 多线程环境下计数准确
```

### 6. 数据压缩

支持gzip压缩以节省空间：

```python
store = JSONStore('large_data.json')

# 压缩到默认位置 (large_data.json.gz)
compressed_path = store.compress()

# 压缩到指定位置
compressed_path = store.compress('backup/data.gz')

# 解压
store.decompress('backup/data.gz')
```

---

## 使用场景

### 场景1: 应用配置管理

```python
from kernel.storage import DictJSONStore

class ConfigManager:
    def __init__(self, config_file='config.json'):
        self.store = DictJSONStore(config_file, auto_backup=True)
    
    def get_database_config(self):
        return {
            'host': self.store.get('db_host', 'localhost'),
            'port': self.store.get('db_port', 5432),
            'database': self.store.get('db_name', 'myapp'),
            'user': self.store.get('db_user', 'admin'),
        }
    
    def update_setting(self, key, value):
        self.store.set(key, value)
    
    def reset_to_defaults(self):
        defaults = {
            'db_host': 'localhost',
            'db_port': 5432,
            'theme': 'dark',
            'language': 'zh-CN'
        }
        self.store.write(defaults)

# 使用
config = ConfigManager()
config.update_setting('theme', 'light')
db_config = config.get_database_config()
```

### 场景2: 任务队列

```python
from kernel.storage import ListJSONStore
from datetime import datetime

class TaskQueue:
    def __init__(self, queue_file='tasks.json'):
        self.store = ListJSONStore(queue_file)
    
    def add_task(self, task_type, data):
        task = {
            'id': self._generate_id(),
            'type': task_type,
            'data': data,
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }
        self.store.append(task)
    
    def get_pending_tasks(self):
        tasks = self.store.read(default=[])
        return [t for t in tasks if t.get('status') == 'pending']
    
    def mark_completed(self, task_id):
        def update(tasks):
            for task in tasks:
                if task.get('id') == task_id:
                    task['status'] = 'completed'
                    task['completed_at'] = datetime.now().isoformat()
            return tasks
        
        self.store.update(update)
    
    def _generate_id(self):
        import uuid
        return str(uuid.uuid4())

# 使用
queue = TaskQueue()
queue.add_task('email', {'to': 'user@example.com', 'subject': 'Hello'})
pending = queue.get_pending_tasks()
```

### 场景3: 用户数据存储

```python
from kernel.storage import DictJSONStore

class UserStore:
    def __init__(self, data_dir='users'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
    
    def save_user(self, user_id, user_data):
        store = DictJSONStore(self.data_dir / f"user_{user_id}.json")
        store.write(user_data)
    
    def get_user(self, user_id):
        store = DictJSONStore(self.data_dir / f"user_{user_id}.json")
        return store.read(default=None)
    
    def update_user(self, user_id, updates):
        store = DictJSONStore(self.data_dir / f"user_{user_id}.json")
        store.merge(updates, overwrite=True)
    
    def delete_user(self, user_id):
        store = DictJSONStore(self.data_dir / f"user_{user_id}.json")
        store.delete(create_backup=True)

# 使用
users = UserStore()
users.save_user('001', {'name': 'Alice', 'email': 'alice@example.com'})
users.update_user('001', {'last_login': datetime.now().isoformat()})
user = users.get_user('001')
```

### 场景4: 操作日志审计

```python
from kernel.storage import LogStore

class AuditLogger:
    def __init__(self, log_dir='audit_logs'):
        self.log_store = LogStore(
            directory=log_dir,
            prefix='audit',
            max_entries_per_file=5000,
            auto_rotate=True
        )
    
    def log_action(self, user_id, action, resource, details=None):
        self.log_store.add_log({
            'user_id': user_id,
            'action': action,
            'resource': resource,
            'details': details,
            'ip_address': self._get_ip(),
        })
    
    def get_user_actions(self, user_id, days=7):
        start = datetime.now() - timedelta(days=days)
        return self.log_store.get_logs(
            start_date=start,
            filter_func=lambda log: log.get('user_id') == user_id
        )
    
    def get_security_events(self):
        critical_actions = ['login_failed', 'permission_denied', 'data_deleted']
        return self.log_store.get_logs(
            filter_func=lambda log: log.get('action') in critical_actions
        )
    
    def _get_ip(self):
        # 实际实现中获取真实IP
        return '127.0.0.1'

# 使用
audit = AuditLogger()
audit.log_action('user_001', 'login', '/api/auth')
audit.log_action('user_001', 'update', '/api/users/profile')
actions = audit.get_user_actions('user_001', days=7)
```

---

## 异常处理

### 异常类型

```python
from kernel.storage import JSONStoreError, FileNotFoundError, ValidationError

# JSONStoreError - 基础异常类
# FileNotFoundError - 文件不存在
# ValidationError - 数据验证失败
```

### 推荐的异常处理模式

```python
from kernel.storage import DictJSONStore, JSONStoreError, ValidationError

store = DictJSONStore('config.json')

try:
    # 读取操作
    data = store.read()
except FileNotFoundError:
    print("配置文件不存在，使用默认配置")
    data = store.read(default={})
except JSONStoreError as e:
    print(f"读取失败: {e}")
    data = {}

try:
    # 写入操作
    store.write(data)
except ValidationError as e:
    print(f"数据验证失败: {e}")
except JSONStoreError as e:
    print(f"写入失败: {e}")
```

---

## 性能建议

### 1. 选择合适的存储器类型

```python
# ❌ 不推荐：用通用存储器处理字典
store = JSONStore('config.json')
data = store.read()
data['key'] = 'value'
store.write(data)

# ✅ 推荐：使用字典存储器
store = DictJSONStore('config.json')
store.set('key', 'value')
```

### 2. 批量操作

```python
# ❌ 不推荐：多次写入
for i in range(100):
    store.append(i)  # 100次文件操作

# ✅ 推荐：批量写入
items = list(range(100))
store.extend(items)  # 1次文件操作
```

### 3. 合理使用备份

```python
# 频繁写入场景，考虑关闭自动备份
store = JSONStore('cache.json', auto_backup=False)

# 重要数据场景，启用自动备份
store = JSONStore('user_data.json', auto_backup=True, max_backups=10)
```

### 4. 大文件处理

```python
# 对于大型日志文件，使用LogStore自动轮转
logger = LogStore(
    directory='logs',
    max_entries_per_file=1000,  # 限制单文件大小
    auto_rotate=True
)

# 定期清理旧文件
logger.clear_old_logs(days=30)
```

### 5. 避免频繁的完整读取

```python
# ❌ 不推荐：每次都读取完整数据
def get_value(key):
    data = store.read()
    return data.get(key)

# ✅ 推荐：使用字典存储器的直接访问
def get_value(key):
    return store.get(key)  # 内部优化了读取
```

---

## 与其他模块集成

### 与Logger模块集成

```python
from kernel.logger import setup_logger
from kernel.storage import DictJSONStore

logger = setup_logger('storage_demo')

store = DictJSONStore('config.json')

try:
    data = store.read()
    logger.info(f"成功读取配置: {len(data)} 项")
except Exception as e:
    logger.error(f"读取配置失败: {e}", exc_info=True)
```

### 与Config模块集成

```python
from kernel.config import Config
from kernel.storage import DictJSONStore

class PersistentConfig(Config):
    def __init__(self, config_file='config.json'):
        super().__init__()
        self.store = DictJSONStore(config_file)
        self._load_from_store()
    
    def _load_from_store(self):
        data = self.store.read(default={})
        for key, value in data.items():
            self.set(key, value)
    
    def save(self):
        data = self.to_dict()
        self.store.write(data)
```

---

## 常见问题

### Q1: 如何处理并发写入？

A: Storage模块已内置线程安全机制，多线程环境下可直接使用：

```python
import threading

store = DictJSONStore('shared.json')

def worker(worker_id):
    store.set(f'worker_{worker_id}', {'data': 'value'})

threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

### Q2: 如何恢复备份数据？

A: 备份文件是标准JSON格式，可直接使用：

```python
# 方法1: 手动读取备份文件
backup_store = JSONStore('config_backup_20260106_143022.json')
data = backup_store.read()
store.write(data)

# 方法2: 直接重命名备份文件
import shutil
shutil.copy('config_backup_20260106_143022.json', 'config.json')
```

### Q3: 如何处理大型JSON文件？

A: 考虑以下策略：

```python
# 1. 使用LogStore自动分片
logger = LogStore(directory='logs', max_entries_per_file=1000)

# 2. 分离存储
user_store = DictJSONStore('users/user_{id}.json')  # 每个用户单独文件

# 3. 定期清理和压缩
store.compress()
logger.clear_old_logs(days=30)
```

### Q4: 如何在测试中使用？

A: 使用临时文件或内存路径：

```python
import tempfile
from pathlib import Path

def test_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DictJSONStore(Path(tmpdir) / 'test.json')
        store.set('key', 'value')
        assert store.get('key') == 'value'
```

---

## 更多文档

- [配置指南](./CONFIGURATION_GUIDE.md) - 详细的配置参数说明
- [API参考](./API_REFERENCE.md) - 完整的API文档
- [最佳实践](./BEST_PRACTICES.md) - 使用模式和建议
- [故障排查](./TROUBLESHOOTING.md) - 常见问题解决

---

## 版本历史

- **v1.0.0** (2026-01-06)
  - 初始版本发布
  - 提供JSONStore、DictJSONStore、ListJSONStore、LogStore四种存储器
  - 支持原子写入、自动备份、数据压缩、线程安全等核心特性
