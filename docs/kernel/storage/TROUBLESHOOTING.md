# Storage 故障排查指南

本文档帮助您诊断和解决 Storage 模块使用过程中可能遇到的问题。

---

## 目录

- [常见问题](#常见问题)
- [文件操作问题](#文件操作问题)
- [数据完整性问题](#数据完整性问题)
- [性能问题](#性能问题)
- [并发问题](#并发问题)
- [备份和恢复](#备份和恢复)
- [调试技巧](#调试技巧)
- [错误信息解析](#错误信息解析)

---

## 常见问题

### Q1: FileNotFoundError - 文件不存在

**症状**:
```python
FileNotFoundError: 文件不存在: data.json
```

**原因**:
- 文件确实不存在
- `auto_create=False` 时尝试读取不存在的文件
- 文件路径错误

**解决方案**:

```python
from kernel.storage import JSONStore, FileNotFoundError

# 方案1: 启用自动创建
store = JSONStore('data.json', auto_create=True)

# 方案2: 使用默认值
try:
    data = store.read()
except FileNotFoundError:
    data = store.read(default={})

# 方案3: 检查文件是否存在
if store.exists():
    data = store.read()
else:
    store.write({})
    data = {}
```

---

### Q2: ValidationError - 数据验证失败

**症状**:
```python
ValidationError: 数据验证失败
```

**原因**:
- 写入的数据不符合验证函数的要求
- 数据类型错误
- 缺少必需字段

**诊断步骤**:

```python
from kernel.storage import DictJSONStore, ValidationError

# 1. 检查验证函数
def validate(data):
    print(f"验证数据: {data}")
    print(f"数据类型: {type(data)}")
    
    # 详细检查
    if not isinstance(data, dict):
        print("错误: 数据不是字典")
        return False
    
    required = ['name', 'version']
    for key in required:
        if key not in data:
            print(f"错误: 缺少必需字段 '{key}'")
            return False
    
    return True

store = DictJSONStore('config.json', validate_func=validate)

# 2. 测试验证
try:
    store.write({'name': 'MoFox'})  # 缺少version
except ValidationError as e:
    print(f"验证失败: {e}")
    # 查看上面的输出了解具体原因

# 3. 修正数据
store.write({'name': 'MoFox', 'version': '1.0'})
```

**解决方案**:

```python
# 方案1: 修正数据格式
correct_data = {
    'name': 'MoFox',
    'version': '1.0',
    'debug': False
}
store.write(correct_data)

# 方案2: 临时跳过验证（不推荐）
store.write(data, validate=False)

# 方案3: 修改验证函数使其更宽松
def lenient_validate(data):
    return isinstance(data, dict)  # 只检查类型

store = DictJSONStore('config.json', validate_func=lenient_validate)
```

---

### Q3: JSONDecodeError - JSON解析失败

**症状**:
```python
JSONStoreError: JSON解析失败: Expecting property name enclosed in double quotes
```

**原因**:
- JSON文件损坏
- 文件不是有效的JSON格式
- 手动编辑导致语法错误

**诊断步骤**:

```python
from kernel.storage import JSONStore
import json

store = JSONStore('data.json')

# 1. 检查文件内容
try:
    with open(store.file_path, 'r') as f:
        content = f.read()
        print(f"文件内容: {content[:200]}")  # 显示前200个字符
except Exception as e:
    print(f"读取文件失败: {e}")

# 2. 尝试手动解析
try:
    with open(store.file_path, 'r') as f:
        data = json.load(f)
        print("JSON解析成功")
except json.JSONDecodeError as e:
    print(f"JSON解析失败: {e}")
    print(f"错误位置: 行 {e.lineno}, 列 {e.colno}")
```

**解决方案**:

```python
# 方案1: 从备份恢复
import shutil
from pathlib import Path

backup_files = list(Path('.').glob('data_backup_*.json'))
if backup_files:
    latest_backup = max(backup_files, key=lambda p: p.stat().st_mtime)
    print(f"从备份恢复: {latest_backup}")
    shutil.copy(latest_backup, 'data.json')

# 方案2: 重新创建文件
store.delete(create_backup=True)
store.write({})

# 方案3: 手动修复（谨慎使用）
import json

with open('data.json', 'r') as f:
    content = f.read()

# 尝试修复常见问题
content = content.replace("'", '"')  # 单引号改双引号
content = content.replace('True', 'true')  # Python布尔值改JSON格式
content = content.replace('False', 'false')
content = content.replace('None', 'null')

try:
    data = json.loads(content)
    store.write(data)
    print("修复成功")
except json.JSONDecodeError:
    print("修复失败，建议从备份恢复")
```

---

### Q4: PermissionError - 权限不足

**症状**:
```python
PermissionError: [Errno 13] Permission denied: 'data.json'
```

**原因**:
- 文件权限不足
- 文件被其他进程占用
- 目录权限问题

**诊断步骤**:

```python
from pathlib import Path
import os

file_path = Path('data.json')

# 1. 检查文件权限
if file_path.exists():
    stat = file_path.stat()
    print(f"文件权限: {oct(stat.st_mode)}")
    print(f"文件所有者: {stat.st_uid}")
    print(f"当前用户: {os.getuid()}")

# 2. 检查目录权限
dir_path = file_path.parent
if dir_path.exists():
    stat = dir_path.stat()
    print(f"目录权限: {oct(stat.st_mode)}")

# 3. 检查文件是否被占用
try:
    with open(file_path, 'a'):
        print("文件可写入")
except PermissionError:
    print("文件被占用或权限不足")
```

**解决方案**:

```python
from pathlib import Path
import os

file_path = Path('data.json')

# 方案1: 修改文件权限（Unix/Linux）
if os.name != 'nt':  # 非Windows
    file_path.chmod(0o644)  # rw-r--r--

# 方案2: 使用其他文件
alternative_store = JSONStore('data_alternative.json')

# 方案3: 使用临时目录
import tempfile
temp_dir = Path(tempfile.gettempdir())
temp_store = JSONStore(temp_dir / 'data.json')

# 方案4: 以管理员权限运行（Windows）
# 或使用sudo（Unix/Linux）
```

---

## 文件操作问题

### 问题: 写入操作很慢

**症状**: 写入数据耗时较长

**诊断**:

```python
import time
from kernel.storage import JSONStore

store = JSONStore('data.json')

# 测量写入时间
start = time.time()
store.write({'large': 'data' * 10000})
elapsed = time.time() - start
print(f"写入耗时: {elapsed:.3f}秒")

# 检查文件大小
size = store.get_size()
print(f"文件大小: {size / 1024:.2f} KB")
```

**可能原因**:

1. **文件过大**
   ```python
   # 解决方案: 分片存储
   from kernel.storage import DictJSONStore
   
   # 不要把所有数据放在一个文件
   # ❌ 不好
   big_store = JSONStore('all_data.json')
   big_store.write(huge_data)
   
   # ✅ 更好
   for category in data_categories:
       store = DictJSONStore(f'data_{category}.json')
       store.write(data_by_category[category])
   ```

2. **备份开销**
   ```python
   # 解决方案: 关闭自动备份或减少备份数量
   
   # ❌ 高频写入启用备份
   store = JSONStore('metrics.json', auto_backup=True)
   for i in range(1000):
       store.write({'count': i})  # 每次都备份，很慢
   
   # ✅ 关闭备份或批量操作
   store = JSONStore('metrics.json', auto_backup=False)
   # 或使用update一次性完成
   store.update(lambda d: {'count': 1000})
   ```

3. **JSON格式化开销**
   ```python
   # 解决方案: 使用紧凑格式
   
   # ❌ 大文件使用缩进
   store = JSONStore('large.json', indent=2)
   
   # ✅ 使用紧凑格式
   store = JSONStore('large.json', indent=None)
   ```

4. **磁盘I/O慢**
   ```python
   # 解决方案: 批量写入
   from kernel.storage import ListJSONStore
   
   # ❌ 多次写入
   store = ListJSONStore('tasks.json')
   for task in tasks:
       store.append(task)  # N次I/O
   
   # ✅ 一次写入
   store.extend(tasks)  # 1次I/O
   ```

---

### 问题: 文件损坏

**症状**: JSON解析失败，数据不完整

**诊断**:

```python
from kernel.storage import JSONStore
import json

def check_file_integrity(file_path):
    """检查文件完整性"""
    try:
        # 1. 检查文件大小
        size = Path(file_path).stat().st_size
        print(f"文件大小: {size} bytes")
        if size == 0:
            print("警告: 文件为空")
            return False
        
        # 2. 尝试解析JSON
        with open(file_path, 'r') as f:
            data = json.load(f)
        print(f"JSON解析成功，数据类型: {type(data)}")
        
        # 3. 检查数据结构
        if isinstance(data, dict):
            print(f"字典包含 {len(data)} 个键")
        elif isinstance(data, list):
            print(f"列表包含 {len(data)} 个项目")
        
        return True
        
    except Exception as e:
        print(f"完整性检查失败: {e}")
        return False

# 使用
if not check_file_integrity('data.json'):
    print("文件已损坏，尝试恢复")
    # 从备份恢复...
```

**恢复步骤**:

```python
from pathlib import Path
import shutil

def recover_from_backup(file_path):
    """从备份恢复"""
    file_path = Path(file_path)
    
    # 1. 查找备份文件
    pattern = f"{file_path.stem}_backup_*{file_path.suffix}"
    backups = sorted(
        file_path.parent.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    if not backups:
        print("没有找到备份文件")
        return False
    
    # 2. 尝试从最新备份恢复
    for backup in backups:
        print(f"尝试恢复: {backup}")
        
        # 检查备份完整性
        if check_file_integrity(backup):
            # 备份当前损坏的文件
            damaged = file_path.with_suffix('.damaged')
            shutil.move(file_path, damaged)
            
            # 恢复备份
            shutil.copy(backup, file_path)
            print(f"恢复成功，损坏文件保存为: {damaged}")
            return True
    
    print("所有备份文件也已损坏")
    return False

# 使用
if not recover_from_backup('data.json'):
    # 重新初始化
    store = JSONStore('data.json')
    store.write({})
```

---

## 数据完整性问题

### 问题: 数据丢失

**症状**: 之前写入的数据不见了

**可能原因和解决方案**:

1. **并发写入冲突**
   ```python
   import threading
   from kernel.storage import DictJSONStore
   
   # 问题代码
   store = DictJSONStore('shared.json')
   
   def worker(worker_id):
       for i in range(100):
           # 可能发生竞态条件
           data = store.read()
           data[f'worker_{worker_id}'] = i
           store.write(data)
   
   # 解决方案: 使用原子更新
   def worker_fixed(worker_id):
       for i in range(100):
           store.set(f'worker_{worker_id}', i)  # 原子操作
   ```

2. **验证失败静默回滚**
   ```python
   from kernel.storage import DictJSONStore, ValidationError
   from kernel.logger import get_logger
   
   logger = get_logger(__name__)
   
   store = DictJSONStore('config.json', validate_func=strict_validate)
   
   try:
       store.set('key', 'value')
   except ValidationError as e:
       logger.error(f"数据未保存，验证失败: {e}")
       # 不要静默失败！
   ```

3. **程序崩溃导致部分写入**
   ```python
   # Storage模块使用原子写入机制，但可以验证
   from kernel.storage import JSONStore
   
   store = JSONStore('data.json')
   
   # 写入前检查
   if store.exists():
       original_data = store.read()
   
   # 写入
   store.write(new_data)
   
   # 写入后验证
   saved_data = store.read()
   assert saved_data == new_data, "数据写入不完整"
   ```

---

### 问题: 数据不一致

**症状**: 读取的数据与预期不符

**诊断工具**:

```python
from kernel.storage import DictJSONStore
from datetime import datetime
import hashlib
import json

class VersionedStore:
    """带版本控制的存储器"""
    def __init__(self, file_path):
        self.store = DictJSONStore(file_path)
    
    def write_versioned(self, data):
        """写入带版本信息的数据"""
        versioned_data = {
            'data': data,
            'version': self._next_version(),
            'timestamp': datetime.now().isoformat(),
            'checksum': self._checksum(data)
        }
        self.store.write(versioned_data)
    
    def read_versioned(self):
        """读取并验证数据"""
        versioned_data = self.store.read()
        
        data = versioned_data.get('data')
        stored_checksum = versioned_data.get('checksum')
        calculated_checksum = self._checksum(data)
        
        if stored_checksum != calculated_checksum:
            print(f"警告: 数据校验失败")
            print(f"存储的校验和: {stored_checksum}")
            print(f"计算的校验和: {calculated_checksum}")
            raise ValueError("数据完整性验证失败")
        
        return data
    
    def _checksum(self, data):
        """计算数据校验和"""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def _next_version(self):
        """获取下一个版本号"""
        try:
            current = self.store.get('version', 0)
            return current + 1
        except:
            return 1

# 使用
versioned = VersionedStore('data.json')
versioned.write_versioned({'key': 'value'})

try:
    data = versioned.read_versioned()
    print(f"数据验证通过: {data}")
except ValueError as e:
    print(f"数据完整性问题: {e}")
```

---

## 性能问题

### 问题: 读取操作慢

**诊断**:

```python
import time
from kernel.storage import JSONStore

def benchmark_read(file_path, iterations=100):
    """测试读取性能"""
    store = JSONStore(file_path)
    
    times = []
    for i in range(iterations):
        start = time.time()
        data = store.read()
        elapsed = time.time() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    print(f"平均读取时间: {avg_time*1000:.2f}ms")
    print(f"最慢读取: {max(times)*1000:.2f}ms")
    print(f"最快读取: {min(times)*1000:.2f}ms")
    
    size = store.get_size()
    print(f"文件大小: {size/1024:.2f}KB")
    print(f"读取速度: {size/1024/avg_time:.2f}KB/s")

benchmark_read('data.json')
```

**优化方案**:

1. **添加缓存层**
   ```python
   from functools import lru_cache
   import time
   
   class CachedStore:
       def __init__(self, store, cache_ttl=60):
           self.store = store
           self.cache_ttl = cache_ttl
           self._cache = None
           self._cache_time = 0
       
       def read(self):
           now = time.time()
           if self._cache is None or now - self._cache_time > self.cache_ttl:
               self._cache = self.store.read()
               self._cache_time = now
           return self._cache
       
       def write(self, data):
           self.store.write(data)
           # 更新缓存
           self._cache = data
           self._cache_time = time.time()
   
   # 使用
   base_store = JSONStore('data.json')
   cached = CachedStore(base_store, cache_ttl=300)
   
   # 第一次读取从文件
   data1 = cached.read()
   
   # 后续读取从缓存
   data2 = cached.read()  # 快很多
   ```

2. **减小文件大小**
   ```python
   # 分割大文件
   from kernel.storage import DictJSONStore
   
   # ❌ 单个大文件
   big_store = DictJSONStore('all_users.json')
   
   # ✅ 按类别分割
   def get_user_store(user_id):
       # 使用user_id的第一个字符分片
       shard = user_id[0].lower()
       return DictJSONStore(f'users_{shard}.json')
   
   user_store = get_user_store('alice_123')
   ```

3. **延迟加载**
   ```python
   class LazyStore:
       """延迟加载存储器"""
       def __init__(self, file_path):
           self.file_path = file_path
           self._store = None
       
       @property
       def store(self):
           if self._store is None:
               from kernel.storage import DictJSONStore
               self._store = DictJSONStore(self.file_path)
           return self._store
       
       def get(self, key, default=None):
           return self.store.get(key, default)
   
   # 只在实际使用时才加载
   lazy = LazyStore('config.json')
   # 此时还没有读取文件
   
   value = lazy.get('key')  # 现在才读取文件
   ```

---

### 问题: 内存占用高

**诊断**:

```python
import sys
from kernel.storage import JSONStore

store = JSONStore('large_file.json')
data = store.read()

# 检查数据大小
size = sys.getsizeof(data)
print(f"数据占用内存: {size / 1024 / 1024:.2f}MB")

# 如果是字典或列表，检查元素数量
if isinstance(data, dict):
    print(f"字典包含 {len(data)} 个键")
elif isinstance(data, list):
    print(f"列表包含 {len(data)} 个元素")
```

**解决方案**:

1. **流式处理（对于日志）**
   ```python
   from kernel.storage import LogStore
   from datetime import datetime, timedelta
   
   logger = LogStore(directory='logs', prefix='app')
   
   # ❌ 一次性加载所有日志
   all_logs = logger.get_logs()  # 可能很大
   
   # ✅ 按时间范围分批处理
   end_date = datetime.now()
   for i in range(30):  # 每次处理一天
       start_date = end_date - timedelta(days=1)
       daily_logs = logger.get_logs(start_date=start_date, end_date=end_date)
       
       # 处理当天日志
       process_logs(daily_logs)
       
       end_date = start_date
   ```

2. **数据压缩**
   ```python
   from kernel.storage import JSONStore
   
   store = JSONStore('large_data.json')
   
   # 定期压缩旧数据
   compressed_path = store.compress('archive/data.json.gz')
   print(f"压缩后: {compressed_path}")
   
   # 删除原文件节省空间
   store.delete()
   ```

3. **分页加载**
   ```python
   from kernel.storage import ListJSONStore
   
   class PaginatedStore:
       """分页存储器"""
       def __init__(self, file_path, page_size=100):
           self.store = ListJSONStore(file_path)
           self.page_size = page_size
       
       def get_page(self, page_num):
           """获取指定页的数据"""
           all_data = self.store.read(default=[])
           start = page_num * self.page_size
           end = start + self.page_size
           return all_data[start:end]
       
       def get_total_pages(self):
           """获取总页数"""
           length = self.store.length()
           return (length + self.page_size - 1) // self.page_size
   
   # 使用
   paginated = PaginatedStore('large_list.json', page_size=100)
   
   # 只加载需要的页
   page_data = paginated.get_page(0)
   ```

---

## 并发问题

### 问题: 多进程/多线程竞态条件

**症状**: 数据被意外覆盖，更新丢失

**诊断**:

```python
import threading
from kernel.storage import DictJSONStore

def test_concurrent_writes():
    """测试并发写入"""
    store = DictJSONStore('concurrent_test.json')
    store.clear()
    
    def worker(worker_id, iterations=100):
        for i in range(iterations):
            store.set(f'worker_{worker_id}_{i}', i)
    
    # 启动多个线程
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # 检查结果
    expected = 10 * 100  # 10个线程，每个100次
    actual = len(store.keys())
    print(f"预期键数: {expected}")
    print(f"实际键数: {actual}")
    
    if actual != expected:
        print(f"警告: 丢失了 {expected - actual} 个更新")

test_concurrent_writes()
```

**解决方案**:

Storage模块内置了线程安全机制，但多进程需要额外处理：

```python
from multiprocessing import Process, Lock
from kernel.storage import DictJSONStore
import fcntl  # Unix/Linux 文件锁

class ProcessSafeStore:
    """进程安全的存储器"""
    def __init__(self, file_path):
        self.file_path = file_path
        self.lock_path = f"{file_path}.lock"
    
    def _acquire_lock(self):
        """获取文件锁"""
        self.lock_file = open(self.lock_path, 'w')
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
    
    def _release_lock(self):
        """释放文件锁"""
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
        self.lock_file.close()
    
    def set(self, key, value):
        """进程安全的set操作"""
        self._acquire_lock()
        try:
            store = DictJSONStore(self.file_path)
            store.set(key, value)
        finally:
            self._release_lock()
    
    def get(self, key, default=None):
        """进程安全的get操作"""
        self._acquire_lock()
        try:
            store = DictJSONStore(self.file_path)
            return store.get(key, default)
        finally:
            self._release_lock()

# 使用（仅Unix/Linux）
if os.name != 'nt':
    safe_store = ProcessSafeStore('shared.json')
    
    def worker(worker_id):
        for i in range(100):
            safe_store.set(f'worker_{worker_id}_{i}', i)
    
    processes = [Process(target=worker, args=(i,)) for i in range(5)]
    for p in processes:
        p.start()
    for p in processes:
        p.join()
```

---

## 备份和恢复

### 问题: 备份文件过多

**症状**: 备份文件占用大量磁盘空间

**解决方案**:

```python
from pathlib import Path
from kernel.storage import JSONStore

def cleanup_old_backups(file_path, keep_count=5):
    """清理旧备份"""
    file_path = Path(file_path)
    
    # 查找所有备份
    pattern = f"{file_path.stem}_backup_*{file_path.suffix}"
    backups = sorted(
        file_path.parent.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    print(f"找到 {len(backups)} 个备份文件")
    
    # 删除多余的备份
    deleted = 0
    for backup in backups[keep_count:]:
        try:
            backup.unlink()
            deleted += 1
            print(f"删除: {backup}")
        except Exception as e:
            print(f"删除失败 {backup}: {e}")
    
    print(f"清理了 {deleted} 个备份文件")

# 定期清理
cleanup_old_backups('data.json', keep_count=5)
```

---

### 问题: 如何恢复到特定版本

**解决方案**:

```python
from pathlib import Path
from datetime import datetime
import shutil

def list_backups(file_path):
    """列出所有备份及其时间"""
    file_path = Path(file_path)
    pattern = f"{file_path.stem}_backup_*{file_path.suffix}"
    
    backups = []
    for backup in file_path.parent.glob(pattern):
        # 从文件名提取时间戳
        timestamp_str = backup.stem.split('_backup_')[1]
        timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
        
        backups.append({
            'path': backup,
            'timestamp': timestamp,
            'size': backup.stat().st_size
        })
    
    # 按时间排序
    backups.sort(key=lambda x: x['timestamp'], reverse=True)
    return backups

def restore_backup(file_path, backup_time=None):
    """恢复指定时间的备份"""
    backups = list_backups(file_path)
    
    if not backups:
        print("没有可用的备份")
        return False
    
    # 选择备份
    if backup_time is None:
        # 恢复最新备份
        selected = backups[0]
    else:
        # 查找最接近的备份
        selected = min(backups, key=lambda b: abs((b['timestamp'] - backup_time).total_seconds()))
    
    print(f"恢复备份: {selected['path']}")
    print(f"备份时间: {selected['timestamp']}")
    print(f"备份大小: {selected['size']} bytes")
    
    # 备份当前文件
    current = Path(file_path)
    if current.exists():
        damaged = current.with_suffix('.before_restore')
        shutil.copy(current, damaged)
        print(f"当前文件已备份到: {damaged}")
    
    # 恢复
    shutil.copy(selected['path'], current)
    print("恢复成功")
    return True

# 使用
# 列出所有备份
backups = list_backups('data.json')
for backup in backups:
    print(f"{backup['timestamp']}: {backup['path']}")

# 恢复最新备份
restore_backup('data.json')

# 恢复到特定时间
target_time = datetime(2026, 1, 6, 12, 0, 0)
restore_backup('data.json', backup_time=target_time)
```

---

## 调试技巧

### 1. 启用详细日志

```python
from kernel.logger import setup_logger
from kernel.storage import DictJSONStore

# 设置详细日志
logger = setup_logger('storage_debug', level='DEBUG')

# 包装存储器添加日志
class DebugStore:
    def __init__(self, store):
        self.store = store
    
    def get(self, key, default=None):
        logger.debug(f"读取: {key}")
        value = self.store.get(key, default)
        logger.debug(f"结果: {key} = {value}")
        return value
    
    def set(self, key, value):
        logger.debug(f"写入: {key} = {value}")
        self.store.set(key, value)
        logger.debug(f"写入成功: {key}")

# 使用
base = DictJSONStore('config.json')
debug_store = DebugStore(base)

debug_store.set('test', 'value')
value = debug_store.get('test')
```

### 2. 监控文件变化

```python
import time
from pathlib import Path

def watch_file(file_path, interval=1):
    """监控文件变化"""
    file_path = Path(file_path)
    last_mtime = None
    last_size = None
    
    print(f"开始监控: {file_path}")
    
    while True:
        try:
            if file_path.exists():
                stat = file_path.stat()
                mtime = stat.st_mtime
                size = stat.st_size
                
                if mtime != last_mtime or size != last_size:
                    print(f"[{datetime.now()}] 文件已变化")
                    print(f"  大小: {size} bytes")
                    print(f"  修改时间: {datetime.fromtimestamp(mtime)}")
                    
                    last_mtime = mtime
                    last_size = size
            else:
                print(f"[{datetime.now()}] 文件不存在")
            
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n监控已停止")
            break

# 在单独的线程中运行
import threading
watcher = threading.Thread(target=watch_file, args=('data.json', 1))
watcher.daemon = True
watcher.start()

# 继续其他操作...
```

### 3. 数据完整性检查

```python
from kernel.storage import JSONStore
import json

def health_check(file_path):
    """健康检查"""
    print(f"\n=== 健康检查: {file_path} ===\n")
    
    file_path = Path(file_path)
    
    # 1. 文件存在性
    print(f"文件存在: {file_path.exists()}")
    if not file_path.exists():
        return False
    
    # 2. 文件大小
    size = file_path.stat().st_size
    print(f"文件大小: {size} bytes ({size/1024:.2f} KB)")
    
    # 3. 文件权限
    print(f"文件权限: {oct(file_path.stat().st_mode)}")
    
    # 4. JSON有效性
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        print(f"JSON有效: ✓")
        print(f"数据类型: {type(data).__name__}")
        
        if isinstance(data, dict):
            print(f"字典键数: {len(data)}")
        elif isinstance(data, list):
            print(f"列表长度: {len(data)}")
    except json.JSONDecodeError as e:
        print(f"JSON无效: ✗")
        print(f"错误: {e}")
        return False
    
    # 5. 备份检查
    pattern = f"{file_path.stem}_backup_*{file_path.suffix}"
    backups = list(file_path.parent.glob(pattern))
    print(f"备份文件: {len(backups)} 个")
    
    print(f"\n健康检查: 通过 ✓")
    return True

# 使用
health_check('data.json')
```

---

## 错误信息解析

### 常见错误及含义

| 错误类型 | 含义 | 常见原因 |
|---------|------|----------|
| `FileNotFoundError` | 文件不存在 | 文件未创建、路径错误、auto_create=False |
| `PermissionError` | 权限不足 | 文件权限、目录权限、文件被占用 |
| `JSONDecodeError` | JSON解析失败 | 文件损坏、格式错误、手动编辑错误 |
| `ValidationError` | 数据验证失败 | 数据格式不符、缺少必需字段 |
| `JSONStoreError` | 通用存储错误 | 各种存储操作失败 |
| `OSError: [Errno 28]` | 磁盘空间不足 | 磁盘已满 |
| `OSError: [Errno 24]` | 打开文件过多 | 文件描述符泄露 |

---

## 总结

### 故障排查清单

遇到问题时，按以下顺序检查：

- [ ] 文件是否存在
- [ ] 文件权限是否正确
- [ ] JSON格式是否有效
- [ ] 磁盘空间是否充足
- [ ] 是否有并发冲突
- [ ] 数据验证是否正确
- [ ] 是否有备份可用
- [ ] 日志中是否有错误信息

### 预防措施

- ✅ 始终启用自动备份（重要数据）
- ✅ 使用数据验证
- ✅ 正确处理异常
- ✅ 定期清理旧文件
- ✅ 监控磁盘空间
- ✅ 记录详细日志
- ✅ 定期测试备份恢复

### 获取帮助

如果问题仍未解决：

1. 查看[API参考](./API_REFERENCE.md)确认正确用法
2. 查看[最佳实践](./BEST_PRACTICES.md)学习推荐模式
3. 启用DEBUG日志查看详细信息
4. 检查备份文件是否可恢复
5. 提交问题报告（包含错误日志、最小复现代码）
