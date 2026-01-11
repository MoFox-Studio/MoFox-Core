# Storage 最佳实践

本文档提供 Storage 模块的使用最佳实践、常见模式、性能优化建议和安全注意事项。

---

## 目录

- [设计模式](#设计模式)
- [常见使用模式](#常见使用模式)
- [性能优化](#性能优化)
- [安全考虑](#安全考虑)
- [错误处理](#错误处理)
- [测试建议](#测试建议)
- [反模式](#反模式)

---

## 设计模式

### 1. 单例存储器

为应用提供全局唯一的配置存储实例。

```python
from kernel.storage import DictJSONStore
from typing import Optional

class ConfigStore:
    _instance: Optional[DictJSONStore] = None
    _initialized: bool = False
    
    @classmethod
    def get_instance(cls) -> DictJSONStore:
        if cls._instance is None:
            cls._instance = DictJSONStore(
                'config.json',
                auto_backup=True,
                max_backups=10
            )
            cls._initialized = True
        return cls._instance
    
    @classmethod
    def reset(cls):
        """重置实例（主要用于测试）"""
        cls._instance = None
        cls._initialized = False

# 使用
config = ConfigStore.get_instance()
config.set('api_key', 'xxx')

# 其他地方也能访问相同实例
config2 = ConfigStore.get_instance()
assert config is config2  # 同一个实例
```

### 2. 工厂模式

根据不同条件创建不同配置的存储器。

```python
from kernel.storage import JSONStore, DictJSONStore, LogStore
from typing import Literal

Environment = Literal['development', 'production', 'testing']

class StorageFactory:
    @staticmethod
    def create_config_store(env: Environment) -> DictJSONStore:
        """创建配置存储器"""
        if env == 'production':
            return DictJSONStore(
                '/etc/app/config.json',
                auto_create=False,
                auto_backup=True,
                max_backups=20,
                indent=None
            )
        elif env == 'testing':
            import tempfile
            return DictJSONStore(
                f'{tempfile.gettempdir()}/test_config.json',
                auto_backup=False
            )
        else:  # development
            return DictJSONStore(
                'config.json',
                auto_backup=True,
                max_backups=5,
                indent=2
            )
    
    @staticmethod
    def create_logger(env: Environment, log_type: str) -> LogStore:
        """创建日志存储器"""
        configs = {
            'production': {'max_entries': 10000},
            'development': {'max_entries': 100},
            'testing': {'max_entries': 10}
        }
        
        return LogStore(
            directory=f'logs/{env}',
            prefix=log_type,
            max_entries_per_file=configs[env]['max_entries'],
            auto_rotate=True
        )

# 使用
import os
env = os.getenv('ENV', 'development')

config = StorageFactory.create_config_store(env)
app_logger = StorageFactory.create_logger(env, 'app')
error_logger = StorageFactory.create_logger(env, 'error')
```

### 3. 仓储模式（Repository Pattern）

封装数据访问逻辑，提供领域对象的CRUD操作。

```python
from kernel.storage import ListJSONStore
from typing import List, Optional
from dataclasses import dataclass, asdict
import uuid

@dataclass
class User:
    id: str
    name: str
    email: str
    active: bool = True
    
    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        return cls(**data)
    
    def to_dict(self) -> dict:
        return asdict(self)

class UserRepository:
    def __init__(self, storage_file='users.json'):
        self.store = ListJSONStore(storage_file, auto_backup=True)
    
    def create(self, name: str, email: str) -> User:
        """创建用户"""
        user = User(
            id=str(uuid.uuid4()),
            name=name,
            email=email
        )
        self.store.append(user.to_dict())
        return user
    
    def find_by_id(self, user_id: str) -> Optional[User]:
        """根据ID查找用户"""
        users = self.store.read(default=[])
        for user_data in users:
            if user_data.get('id') == user_id:
                return User.from_dict(user_data)
        return None
    
    def find_by_email(self, email: str) -> Optional[User]:
        """根据邮箱查找用户"""
        users = self.store.read(default=[])
        for user_data in users:
            if user_data.get('email') == email:
                return User.from_dict(user_data)
        return None
    
    def find_all(self, active_only: bool = False) -> List[User]:
        """查找所有用户"""
        users = self.store.read(default=[])
        if active_only:
            users = [u for u in users if u.get('active', True)]
        return [User.from_dict(u) for u in users]
    
    def update(self, user: User) -> bool:
        """更新用户"""
        def update_user(users):
            for i, user_data in enumerate(users):
                if user_data.get('id') == user.id:
                    users[i] = user.to_dict()
                    return users
            return users
        
        self.store.update(update_user)
        return True
    
    def delete(self, user_id: str) -> bool:
        """删除用户"""
        def delete_user(users):
            return [u for u in users if u.get('id') != user_id]
        
        self.store.update(delete_user)
        return True

# 使用
repo = UserRepository()

# 创建
user = repo.create('Alice', 'alice@example.com')

# 查询
found = repo.find_by_email('alice@example.com')
all_users = repo.find_all(active_only=True)

# 更新
user.name = 'Alice Smith'
repo.update(user)

# 删除
repo.delete(user.id)
```

### 4. 装饰器模式

为存储器添加额外功能（如缓存、日志、监控）。

```python
from kernel.storage import DictJSONStore
from kernel.logger import get_logger
from functools import wraps
from typing import Any
import time

logger = get_logger(__name__)

class CachedStore:
    """带缓存的存储器装饰器"""
    def __init__(self, store: DictJSONStore, cache_ttl: int = 60):
        self.store = store
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = cache_ttl
    
    def get(self, key: str, default: Any = None) -> Any:
        # 检查缓存
        if key in self.cache:
            if time.time() - self.cache_time[key] < self.cache_ttl:
                logger.debug(f"缓存命中: {key}")
                return self.cache[key]
        
        # 缓存未命中，从存储读取
        logger.debug(f"缓存未命中: {key}")
        value = self.store.get(key, default)
        self.cache[key] = value
        self.cache_time[key] = time.time()
        return value
    
    def set(self, key: str, value: Any) -> None:
        self.store.set(key, value)
        # 更新缓存
        self.cache[key] = value
        self.cache_time[key] = time.time()
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.cache_time.clear()

class LoggedStore:
    """带日志的存储器装饰器"""
    def __init__(self, store: DictJSONStore):
        self.store = store
    
    def get(self, key: str, default: Any = None) -> Any:
        logger.debug(f"读取配置: {key}")
        value = self.store.get(key, default)
        logger.debug(f"读取结果: {key} = {value}")
        return value
    
    def set(self, key: str, value: Any) -> None:
        logger.info(f"更新配置: {key} = {value}")
        try:
            self.store.set(key, value)
            logger.info(f"更新成功: {key}")
        except Exception as e:
            logger.error(f"更新失败: {key}, 错误: {e}")
            raise

# 使用
base_store = DictJSONStore('config.json')
cached_store = CachedStore(base_store, cache_ttl=300)
logged_cached_store = LoggedStore(cached_store)

# 带缓存和日志的配置访问
value = logged_cached_store.get('api_key')
logged_cached_store.set('api_key', 'new_key')
```

---

## 常见使用模式

### 1. 配置管理

```python
from kernel.storage import DictJSONStore
from typing import Any, Dict

class AppConfig:
    """应用配置管理"""
    def __init__(self, config_file='config.json'):
        self.store = DictJSONStore(
            config_file,
            auto_backup=True,
            max_backups=10
        )
        self._load_defaults()
    
    def _load_defaults(self):
        """加载默认配置"""
        defaults = {
            'app_name': 'MoFox',
            'version': '1.0.0',
            'debug': False,
            'log_level': 'INFO',
            'database': {
                'host': 'localhost',
                'port': 5432,
                'name': 'myapp'
            },
            'cache': {
                'enabled': True,
                'ttl': 300
            }
        }
        # 只添加不存在的配置
        self.store.merge(defaults, overwrite=False)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持嵌套键（如 'database.host'）"""
        if '.' in key:
            keys = key.split('.')
            value = self.store.get(keys[0], {})
            for k in keys[1:]:
                if isinstance(value, dict):
                    value = value.get(k, default)
                else:
                    return default
            return value
        return self.store.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        if '.' in key:
            # 嵌套键设置
            keys = key.split('.')
            def update(data):
                current = data
                for k in keys[:-1]:
                    if k not in current or not isinstance(current[k], dict):
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value
                return data
            self.store.update(update)
        else:
            self.store.set(key, value)
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """获取配置节"""
        return self.store.get(section, {})

# 使用
config = AppConfig()

# 简单访问
debug = config.get('debug')

# 嵌套访问
db_host = config.get('database.host')
cache_ttl = config.get('cache.ttl', 300)

# 设置值
config.set('debug', True)
config.set('database.port', 3306)

# 获取配置节
db_config = config.get_section('database')
```

### 2. 任务队列

```python
from kernel.storage import ListJSONStore
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid

class TaskStatus:
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'

class TaskQueue:
    """简单的任务队列"""
    def __init__(self, queue_file='tasks.json'):
        self.store = ListJSONStore(queue_file, auto_backup=True)
    
    def enqueue(self, task_type: str, data: Dict[str, Any], 
                priority: int = 0) -> str:
        """添加任务到队列"""
        task = {
            'id': str(uuid.uuid4()),
            'type': task_type,
            'data': data,
            'priority': priority,
            'status': TaskStatus.PENDING,
            'created_at': datetime.now().isoformat(),
            'attempts': 0,
            'max_attempts': 3
        }
        self.store.append(task)
        return task['id']
    
    def dequeue(self) -> Optional[Dict[str, Any]]:
        """从队列获取下一个待处理任务（按优先级）"""
        tasks = self.store.read(default=[])
        
        # 筛选待处理任务
        pending = [t for t in tasks if t.get('status') == TaskStatus.PENDING]
        
        if not pending:
            return None
        
        # 按优先级排序（优先级高的在前）
        pending.sort(key=lambda t: t.get('priority', 0), reverse=True)
        
        # 获取第一个任务并标记为运行中
        task = pending[0]
        self.update_status(task['id'], TaskStatus.RUNNING)
        
        return task
    
    def update_status(self, task_id: str, status: str, 
                      error: Optional[str] = None):
        """更新任务状态"""
        def update(tasks):
            for task in tasks:
                if task.get('id') == task_id:
                    task['status'] = status
                    task['updated_at'] = datetime.now().isoformat()
                    if error:
                        task['error'] = error
                    if status == TaskStatus.FAILED:
                        task['attempts'] = task.get('attempts', 0) + 1
                    break
            return tasks
        
        self.store.update(update)
    
    def retry_failed(self):
        """重试失败的任务（未超过最大尝试次数）"""
        def retry(tasks):
            for task in tasks:
                if task.get('status') == TaskStatus.FAILED:
                    if task.get('attempts', 0) < task.get('max_attempts', 3):
                        task['status'] = TaskStatus.PENDING
            return tasks
        
        self.store.update(retry)
    
    def cleanup_completed(self, days: int = 7):
        """清理已完成的任务"""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        def cleanup(tasks):
            return [
                t for t in tasks
                if not (
                    t.get('status') == TaskStatus.COMPLETED and
                    t.get('updated_at', '') < cutoff
                )
            ]
        
        self.store.update(cleanup)
    
    def get_stats(self) -> Dict[str, int]:
        """获取队列统计信息"""
        tasks = self.store.read(default=[])
        return {
            'total': len(tasks),
            'pending': sum(1 for t in tasks if t.get('status') == TaskStatus.PENDING),
            'running': sum(1 for t in tasks if t.get('status') == TaskStatus.RUNNING),
            'completed': sum(1 for t in tasks if t.get('status') == TaskStatus.COMPLETED),
            'failed': sum(1 for t in tasks if t.get('status') == TaskStatus.FAILED)
        }

# 使用
queue = TaskQueue()

# 添加任务
task_id = queue.enqueue('send_email', {
    'to': 'user@example.com',
    'subject': 'Hello',
    'body': 'Test message'
}, priority=5)

# 处理任务
task = queue.dequeue()
if task:
    try:
        # 处理任务逻辑
        result = process_task(task)
        queue.update_status(task['id'], TaskStatus.COMPLETED)
    except Exception as e:
        queue.update_status(task['id'], TaskStatus.FAILED, error=str(e))

# 统计
stats = queue.get_stats()
print(f"待处理: {stats['pending']}, 已完成: {stats['completed']}")

# 定期清理
queue.cleanup_completed(days=7)
```

### 3. 用户会话管理

```python
from kernel.storage import DictJSONStore
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets

class SessionManager:
    """用户会话管理"""
    def __init__(self, session_file='sessions.json', ttl_minutes: int = 30):
        self.store = DictJSONStore(session_file, auto_backup=False)
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def create_session(self, user_id: str, user_data: Dict[str, Any]) -> str:
        """创建新会话"""
        session_id = secrets.token_urlsafe(32)
        session = {
            'user_id': user_id,
            'user_data': user_data,
            'created_at': datetime.now().isoformat(),
            'last_accessed': datetime.now().isoformat()
        }
        self.store.set(session_id, session)
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话（自动更新访问时间）"""
        session = self.store.get(session_id)
        
        if not session:
            return None
        
        # 检查是否过期
        last_accessed = datetime.fromisoformat(session['last_accessed'])
        if datetime.now() - last_accessed > self.ttl:
            self.delete_session(session_id)
            return None
        
        # 更新最后访问时间
        session['last_accessed'] = datetime.now().isoformat()
        self.store.set(session_id, session)
        
        return session
    
    def delete_session(self, session_id: str):
        """删除会话"""
        self.store.delete_key(session_id)
    
    def cleanup_expired(self) -> int:
        """清理过期会话"""
        now = datetime.now()
        deleted_count = 0
        
        for session_id, session in self.store.items():
            last_accessed = datetime.fromisoformat(session['last_accessed'])
            if now - last_accessed > self.ttl:
                self.delete_session(session_id)
                deleted_count += 1
        
        return deleted_count
    
    def get_user_sessions(self, user_id: str) -> List[str]:
        """获取用户的所有活跃会话"""
        sessions = []
        for session_id, session in self.store.items():
            if session.get('user_id') == user_id:
                # 检查是否过期
                last_accessed = datetime.fromisoformat(session['last_accessed'])
                if datetime.now() - last_accessed <= self.ttl:
                    sessions.append(session_id)
        return sessions
    
    def delete_user_sessions(self, user_id: str) -> int:
        """删除用户的所有会话（用于登出或注销）"""
        sessions = self.get_user_sessions(user_id)
        for session_id in sessions:
            self.delete_session(session_id)
        return len(sessions)

# 使用
sessions = SessionManager(ttl_minutes=30)

# 用户登录，创建会话
session_id = sessions.create_session('user_001', {
    'name': 'Alice',
    'email': 'alice@example.com',
    'role': 'admin'
})

# 验证会话
session = sessions.get_session(session_id)
if session:
    print(f"用户: {session['user_data']['name']}")

# 用户登出
sessions.delete_session(session_id)

# 定期清理过期会话
expired_count = sessions.cleanup_expired()
```

### 4. 审计日志

```python
from kernel.storage import LogStore
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import hashlib

class AuditLogger:
    """审计日志系统"""
    def __init__(self, log_dir='audit_logs'):
        self.store = LogStore(
            directory=log_dir,
            prefix='audit',
            max_entries_per_file=5000,
            auto_rotate=True
        )
    
    def log(self, action: str, resource: str, user_id: str,
            details: Optional[Dict[str, Any]] = None,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None):
        """记录审计日志"""
        entry = {
            'action': action,
            'resource': resource,
            'user_id': user_id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'details': details or {}
        }
        
        # 添加校验和以防篡改
        entry['checksum'] = self._calculate_checksum(entry)
        
        self.store.add_log(entry)
    
    def _calculate_checksum(self, entry: Dict[str, Any]) -> str:
        """计算日志条目的校验和"""
        # 排除checksum字段本身
        data = {k: v for k, v in entry.items() if k != 'checksum'}
        data_str = str(sorted(data.items()))
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def verify_integrity(self, entry: Dict[str, Any]) -> bool:
        """验证日志条目的完整性"""
        if 'checksum' not in entry:
            return False
        
        stored_checksum = entry['checksum']
        calculated_checksum = self._calculate_checksum(entry)
        return stored_checksum == calculated_checksum
    
    def get_user_activity(self, user_id: str, days: int = 7) -> List[Dict]:
        """获取用户活动记录"""
        start = datetime.now() - timedelta(days=days)
        return self.store.get_logs(
            start_date=start,
            filter_func=lambda log: log.get('user_id') == user_id
        )
    
    def get_resource_history(self, resource: str, days: int = 30) -> List[Dict]:
        """获取资源操作历史"""
        start = datetime.now() - timedelta(days=days)
        return self.store.get_logs(
            start_date=start,
            filter_func=lambda log: log.get('resource') == resource
        )
    
    def get_security_events(self, days: int = 7) -> List[Dict]:
        """获取安全事件"""
        critical_actions = [
            'login_failed',
            'permission_denied',
            'data_deleted',
            'config_changed',
            'privilege_escalation'
        ]
        
        start = datetime.now() - timedelta(days=days)
        return self.store.get_logs(
            start_date=start,
            filter_func=lambda log: log.get('action') in critical_actions
        )
    
    def get_failed_logins(self, hours: int = 24) -> Dict[str, int]:
        """获取失败登录统计"""
        start = datetime.now() - timedelta(hours=hours)
        logs = self.store.get_logs(
            start_date=start,
            filter_func=lambda log: log.get('action') == 'login_failed'
        )
        
        # 按用户统计
        stats = {}
        for log in logs:
            user_id = log.get('user_id', 'unknown')
            stats[user_id] = stats.get(user_id, 0) + 1
        
        return stats
    
    def cleanup(self, days: int = 90):
        """清理旧日志"""
        return self.store.clear_old_logs(days)

# 使用
audit = AuditLogger()

# 记录操作
audit.log(
    action='login',
    resource='/api/auth',
    user_id='user_001',
    ip_address='192.168.1.100',
    user_agent='Mozilla/5.0'
)

audit.log(
    action='data_updated',
    resource='/api/users/123',
    user_id='user_001',
    details={'fields': ['email', 'phone']}
)

# 查询
user_activity = audit.get_user_activity('user_001', days=7)
security_events = audit.get_security_events(days=7)
failed_logins = audit.get_failed_logins(hours=24)

# 验证完整性
for log in user_activity:
    if not audit.verify_integrity(log):
        print(f"警告: 日志可能被篡改 - {log}")

# 定期清理
audit.cleanup(days=90)
```

---

## 性能优化

### 1. 批量操作

✅ **推荐**: 批量写入

```python
from kernel.storage import ListJSONStore

store = ListJSONStore('data.json')

# ✅ 推荐：批量添加
items = [f'item_{i}' for i in range(1000)]
store.extend(items)  # 1次文件操作
```

❌ **不推荐**: 逐个写入

```python
# ❌ 不推荐：多次写入
for i in range(1000):
    store.append(f'item_{i}')  # 1000次文件操作
```

### 2. 使用合适的存储器类型

✅ **推荐**: 使用类型特化存储器

```python
from kernel.storage import DictJSONStore

# ✅ 推荐：使用字典存储器
config = DictJSONStore('config.json')
config.set('key', 'value')  # 优化的字典操作
```

❌ **不推荐**: 用通用存储器处理特定类型

```python
from kernel.storage import JSONStore

# ❌ 不推荐：手动处理字典
store = JSONStore('config.json')
data = store.read()
data['key'] = 'value'
store.write(data)
```

### 3. 合理配置备份

```python
from kernel.storage import JSONStore

# 重要数据：启用备份
important_store = JSONStore(
    'important.json',
    auto_backup=True,
    max_backups=20
)

# 临时数据：关闭备份
cache_store = JSONStore(
    'cache.json',
    auto_backup=False
)

# 高频写入：关闭备份或减少备份数量
metrics_store = JSONStore(
    'metrics.json',
    auto_backup=False
)
```

### 4. 使用紧凑格式

```python
# 大文件使用紧凑格式
large_store = JSONStore(
    'large_data.json',
    indent=None  # 紧凑格式，节省空间
)

# 配置文件保持可读性
config_store = JSONStore(
    'config.json',
    indent=2  # 易读格式
)
```

### 5. 定期清理和压缩

```python
from kernel.storage import LogStore
import schedule

logger = LogStore(directory='logs', prefix='app')

def maintenance():
    # 清理旧日志
    deleted = logger.clear_old_logs(days=30)
    print(f"清理了 {deleted} 个旧日志文件")
    
    # 压缩归档
    # (在实际应用中，可能需要遍历日志文件进行压缩)

# 每天凌晨3点执行维护
schedule.every().day.at("03:00").do(maintenance)
```

### 6. 避免频繁的完整读取

✅ **推荐**: 使用专用方法

```python
from kernel.storage import DictJSONStore

config = DictJSONStore('config.json')

# ✅ 推荐：直接获取值
value = config.get('key')
```

❌ **不推荐**: 每次都完整读取

```python
# ❌ 不推荐：完整读取后再访问
data = config.read()
value = data.get('key')
```

---

## 安全考虑

### 1. 文件权限

```python
from pathlib import Path
from kernel.storage import JSONStore

# 创建存储器
store = JSONStore('sensitive.json')

# 设置文件权限（仅所有者可读写）
store.file_path.chmod(0o600)

# 验证权限
stat = store.file_path.stat()
print(f"文件权限: {oct(stat.st_mode)}")
```

### 2. 敏感数据加密

```python
from kernel.storage import DictJSONStore
import base64
from cryptography.fernet import Fernet

class EncryptedStore:
    """加密存储器"""
    def __init__(self, file_path: str, encryption_key: bytes):
        self.store = DictJSONStore(file_path)
        self.cipher = Fernet(encryption_key)
    
    def set_secure(self, key: str, value: str):
        """加密存储"""
        encrypted = self.cipher.encrypt(value.encode())
        self.store.set(key, base64.b64encode(encrypted).decode())
    
    def get_secure(self, key: str) -> str:
        """解密读取"""
        encrypted_b64 = self.store.get(key)
        if not encrypted_b64:
            return None
        encrypted = base64.b64decode(encrypted_b64)
        return self.cipher.decrypt(encrypted).decode()

# 使用
key = Fernet.generate_key()
secure_store = EncryptedStore('secrets.json', key)

secure_store.set_secure('api_key', 'secret_api_key_12345')
api_key = secure_store.get_secure('api_key')
```

### 3. 数据验证

```python
from kernel.storage import DictJSONStore, ValidationError

def validate_user_data(data):
    """验证用户数据"""
    if not isinstance(data, dict):
        return False
    
    # 必需字段
    required = ['id', 'name', 'email']
    if not all(key in data for key in required):
        return False
    
    # 邮箱格式
    email = data.get('email', '')
    if '@' not in email or '.' not in email:
        return False
    
    # ID格式
    if not isinstance(data['id'], (int, str)):
        return False
    
    return True

store = DictJSONStore(
    'users.json',
    validate_func=validate_user_data
)

try:
    store.write({
        'id': 1,
        'name': 'Alice',
        'email': 'alice@example.com'
    })
except ValidationError:
    print("数据验证失败")
```

### 4. 防止路径遍历

```python
from pathlib import Path
from kernel.storage import JSONStore

def safe_store(base_dir: str, filename: str) -> JSONStore:
    """安全地创建存储器，防止路径遍历"""
    base_path = Path(base_dir).resolve()
    file_path = (base_path / filename).resolve()
    
    # 确保文件路径在基础目录内
    if not str(file_path).startswith(str(base_path)):
        raise ValueError("非法的文件路径")
    
    return JSONStore(file_path)

# 使用
try:
    store = safe_store('data', '../../../etc/passwd')  # 会被拒绝
except ValueError as e:
    print(f"安全检查失败: {e}")

store = safe_store('data', 'config.json')  # 安全
```

### 5. 审计日志

```python
from kernel.storage import DictJSONStore, LogStore
from kernel.logger import get_logger

logger = get_logger(__name__)
audit = LogStore(directory='audit_logs', prefix='storage')

class AuditedStore:
    """带审计的存储器"""
    def __init__(self, store: DictJSONStore, user_id: str):
        self.store = store
        self.user_id = user_id
    
    def get(self, key: str, default=None):
        value = self.store.get(key, default)
        audit.add_log({
            'action': 'read',
            'key': key,
            'user_id': self.user_id
        })
        return value
    
    def set(self, key: str, value):
        old_value = self.store.get(key)
        self.store.set(key, value)
        audit.add_log({
            'action': 'write',
            'key': key,
            'old_value': old_value,
            'new_value': value,
            'user_id': self.user_id
        })

# 使用
base_store = DictJSONStore('config.json')
audited = AuditedStore(base_store, user_id='admin')

audited.set('api_key', 'new_key')  # 自动记录审计日志
```

---

## 错误处理

### 1. 推荐的异常处理模式

```python
from kernel.storage import (
    DictJSONStore,
    JSONStoreError,
    FileNotFoundError,
    ValidationError
)
from kernel.logger import get_logger

logger = get_logger(__name__)

def safe_config_operation():
    """安全的配置操作"""
    store = DictJSONStore('config.json')
    
    try:
        # 读取操作
        value = store.get('key')
        
        # 写入操作
        store.set('key', 'new_value')
        
    except FileNotFoundError:
        logger.warning("配置文件不存在，使用默认配置")
        store.write({'key': 'default_value'})
        
    except ValidationError as e:
        logger.error(f"数据验证失败: {e}")
        # 回滚到备份或使用默认值
        
    except JSONStoreError as e:
        logger.error(f"存储操作失败: {e}", exc_info=True)
        # 通知管理员或使用降级方案
        
    except Exception as e:
        logger.critical(f"未预期的错误: {e}", exc_info=True)
        raise
```

### 2. 重试机制

```python
from kernel.storage import JSONStore, JSONStoreError
import time
from typing import Callable, Any

def retry_on_error(func: Callable, max_attempts: int = 3, 
                   delay: float = 1.0) -> Any:
    """重试装饰器"""
    for attempt in range(max_attempts):
        try:
            return func()
        except JSONStoreError as e:
            if attempt == max_attempts - 1:
                raise
            logger.warning(f"操作失败，{delay}秒后重试 ({attempt + 1}/{max_attempts}): {e}")
            time.sleep(delay)

# 使用
store = JSONStore('data.json')

def write_data():
    store.write({'data': 'value'})

retry_on_error(write_data, max_attempts=3, delay=1.0)
```

### 3. 降级处理

```python
from kernel.storage import DictJSONStore, JSONStoreError

class ResilientConfig:
    """具有降级能力的配置"""
    def __init__(self, primary_file: str, fallback_file: str):
        self.primary = DictJSONStore(primary_file)
        self.fallback = DictJSONStore(fallback_file)
        self.defaults = {'timeout': 30, 'retry': 3}
    
    def get(self, key: str, default=None):
        # 1. 尝试主配置
        try:
            return self.primary.get(key, default)
        except JSONStoreError:
            logger.warning("主配置读取失败，使用备用配置")
        
        # 2. 尝试备用配置
        try:
            return self.fallback.get(key, default)
        except JSONStoreError:
            logger.warning("备用配置读取失败，使用默认值")
        
        # 3. 使用默认值
        return self.defaults.get(key, default)

# 使用
config = ResilientConfig('config.json', 'config.backup.json')
timeout = config.get('timeout')  # 多层降级
```

---

## 测试建议

### 1. 使用临时文件

```python
import tempfile
from pathlib import Path
from kernel.storage import DictJSONStore

def test_config_operations():
    """测试配置操作"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DictJSONStore(Path(tmpdir) / 'test.json')
        
        # 测试写入
        store.set('key', 'value')
        
        # 测试读取
        assert store.get('key') == 'value'
        
        # 测试删除
        store.delete_key('key')
        assert not store.has_key('key')
        
        # 临时目录会自动清理
```

### 2. Mock存储器

```python
from unittest.mock import Mock
from kernel.storage import DictJSONStore

class MockStore:
    """模拟存储器用于测试"""
    def __init__(self):
        self.data = {}
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def set(self, key, value):
        self.data[key] = value
    
    def has_key(self, key):
        return key in self.data

# 在测试中使用
def test_with_mock():
    store = MockStore()
    store.set('key', 'value')
    assert store.get('key') == 'value'
```

### 3. 测试备份恢复

```python
from kernel.storage import JSONStore
import tempfile
from pathlib import Path

def test_backup_restore():
    """测试备份和恢复"""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / 'data.json'
        store = JSONStore(file_path, auto_backup=True, max_backups=3)
        
        # 写入初始数据
        store.write({'version': 1})
        
        # 多次更新（生成备份）
        store.write({'version': 2})
        store.write({'version': 3})
        
        # 检查备份文件
        backups = list(Path(tmpdir).glob('data_backup_*.json'))
        assert len(backups) > 0
        
        # 模拟数据损坏，从备份恢复
        latest_backup = max(backups, key=lambda p: p.stat().st_mtime)
        backup_store = JSONStore(latest_backup)
        backup_data = backup_store.read()
        
        # 恢复数据
        store.write(backup_data)
```

---

## 反模式

### ❌ 反模式 1: 频繁的完整读写

```python
# ❌ 不推荐
for i in range(100):
    data = store.read()
    data['count'] = i
    store.write(data)
```

✅ **改进方案**:

```python
# ✅ 使用update方法
store.update(lambda data: {**data, 'count': 100})

# 或使用DictJSONStore
config = DictJSONStore('data.json')
config.set('count', 100)
```

### ❌ 反模式 2: 忽略异常

```python
# ❌ 不推荐
try:
    store.write(data)
except:
    pass  # 静默失败
```

✅ **改进方案**:

```python
# ✅ 正确处理异常
from kernel.logger import get_logger

logger = get_logger(__name__)

try:
    store.write(data)
except ValidationError as e:
    logger.error(f"数据验证失败: {e}")
    # 使用默认值或通知用户
except JSONStoreError as e:
    logger.error(f"存储失败: {e}", exc_info=True)
    # 重试或使用降级方案
```

### ❌ 反模式 3: 硬编码文件路径

```python
# ❌ 不推荐
store = JSONStore('/home/user/app/config.json')
```

✅ **改进方案**:

```python
# ✅ 使用环境变量或配置
import os
from pathlib import Path

DATA_DIR = Path(os.getenv('DATA_DIR', './data'))
store = JSONStore(DATA_DIR / 'config.json')
```

### ❌ 反模式 4: 在循环中创建存储器

```python
# ❌ 不推荐
for user_id in users:
    store = DictJSONStore(f'user_{user_id}.json')
    data = store.read()
    # ...
```

✅ **改进方案**:

```python
# ✅ 重用存储器或使用工厂
class UserStore:
    def __init__(self, data_dir='users'):
        self.data_dir = Path(data_dir)
        self._stores = {}
    
    def get_store(self, user_id):
        if user_id not in self._stores:
            self._stores[user_id] = DictJSONStore(
                self.data_dir / f'user_{user_id}.json'
            )
        return self._stores[user_id]

user_store = UserStore()
for user_id in users:
    store = user_store.get_store(user_id)
    data = store.read()
```

### ❌ 反模式 5: 不使用数据验证

```python
# ❌ 不推荐
store = JSONStore('config.json')
store.write(untrusted_data)  # 可能导致数据损坏
```

✅ **改进方案**:

```python
# ✅ 使用验证函数
def validate(data):
    # 验证数据结构和内容
    return isinstance(data, dict) and all_keys_valid(data)

store = JSONStore('config.json', validate_func=validate)

try:
    store.write(untrusted_data)
except ValidationError:
    logger.error("数据验证失败")
```

---

## 总结

### 核心原则

1. **选择合适的存储器类型** - DictJSONStore用于字典，ListJSONStore用于列表
2. **批量操作** - 使用extend而不是多次append
3. **合理配置备份** - 重要数据启用，临时数据关闭
4. **使用数据验证** - 防止无效数据写入
5. **正确处理异常** - 不要静默失败
6. **定期维护** - 清理旧文件，压缩归档
7. **安全第一** - 文件权限、敏感数据加密、审计日志
8. **测试充分** - 使用临时文件，测试备份恢复

### 检查清单

在使用 Storage 模块时，请检查：

- [ ] 选择了合适的存储器类型
- [ ] 配置了适当的备份策略
- [ ] 添加了数据验证函数（如果需要）
- [ ] 正确处理了异常
- [ ] 使用了批量操作而不是循环写入
- [ ] 设置了合理的文件权限
- [ ] 实现了日志审计（如果需要）
- [ ] 编写了单元测试
- [ ] 实现了定期维护任务

### 下一步

- 查看 [API参考](./API_REFERENCE.md) 了解详细的方法说明
- 查看 [配置指南](./CONFIGURATION_GUIDE.md) 了解配置参数
- 查看 [故障排查](./TROUBLESHOOTING.md) 解决常见问题
