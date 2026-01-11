# Storage 配置指南

本文档详细介绍 Storage 模块的所有配置参数、使用方法和最佳实践。

---

## 目录

- [JSONStore 配置](#jsonstore-配置)
- [DictJSONStore 配置](#dictjsonstore-配置)
- [ListJSONStore 配置](#listjsonstore-配置)
- [LogStore 配置](#logstore-配置)
- [配置模式](#配置模式)
- [环境特定配置](#环境特定配置)
- [配置验证](#配置验证)

---

## JSONStore 配置

### 基础配置参数

#### file_path
- **类型**: `str | Path`
- **必需**: ✅ 是
- **描述**: JSON文件的存储路径
- **示例**:
  ```python
  store = JSONStore('data.json')
  store = JSONStore(Path('config/app.json'))
  store = JSONStore('/absolute/path/data.json')
  ```

#### auto_create
- **类型**: `bool`
- **默认值**: `True`
- **描述**: 文件不存在时是否自动创建
- **示例**:
  ```python
  # 自动创建（默认）
  store = JSONStore('data.json', auto_create=True)
  
  # 不自动创建，文件不存在时抛出异常
  store = JSONStore('data.json', auto_create=False)
  ```
- **使用建议**:
  - 开发环境：推荐 `True`，方便快速启动
  - 生产环境：根据需求设置，严格模式可设为 `False`

#### auto_backup
- **类型**: `bool`
- **默认值**: `True`
- **描述**: 写入数据前是否自动创建备份
- **示例**:
  ```python
  # 启用自动备份（推荐）
  store = JSONStore('important.json', auto_backup=True)
  
  # 关闭自动备份（适合临时数据或高频写入）
  store = JSONStore('cache.json', auto_backup=False)
  ```
- **备份文件格式**: `{原文件名}_backup_{时间戳}.{扩展名}`
- **使用建议**:
  - 重要数据：必须启用
  - 缓存数据：可以关闭以提升性能
  - 高频写入：考虑关闭或增大备份间隔

#### max_backups
- **类型**: `int`
- **默认值**: `5`
- **描述**: 保留的最大备份文件数量
- **示例**:
  ```python
  # 保留最近10个备份
  store = JSONStore('data.json', max_backups=10)
  
  # 只保留1个备份
  store = JSONStore('data.json', max_backups=1)
  
  # 无限备份（不推荐）
  store = JSONStore('data.json', max_backups=999999)
  ```
- **使用建议**:
  - 普通应用：5-10个备份
  - 关键数据：10-20个备份
  - 存储受限：1-3个备份
  - 注意定期清理旧备份

#### indent
- **类型**: `int | None`
- **默认值**: `2`
- **描述**: JSON格式化缩进空格数，`None`表示紧凑格式
- **示例**:
  ```python
  # 2空格缩进（推荐，易读）
  store = JSONStore('data.json', indent=2)
  
  # 4空格缩进
  store = JSONStore('data.json', indent=4)
  
  # 紧凑格式（节省空间）
  store = JSONStore('data.json', indent=None)
  ```
- **对比**:
  ```json
  // indent=2
  {
    "name": "MoFox",
    "version": "1.0"
  }
  
  // indent=None
  {"name":"MoFox","version":"1.0"}
  ```
- **使用建议**:
  - 开发环境：使用缩进（2或4）
  - 生产环境：根据需求选择
  - 大文件：考虑紧凑格式
  - 需要版本控制：使用缩进

#### encoding
- **类型**: `str`
- **默认值**: `'utf-8'`
- **描述**: 文件编码格式
- **示例**:
  ```python
  # UTF-8编码（推荐）
  store = JSONStore('data.json', encoding='utf-8')
  
  # GBK编码（Windows中文环境）
  store = JSONStore('data.json', encoding='gbk')
  
  # ASCII编码
  store = JSONStore('data.json', encoding='ascii')
  ```
- **使用建议**:
  - 默认使用 `utf-8`
  - 有中文数据必须使用 `utf-8`
  - 跨平台兼容性：`utf-8`

#### validate_func
- **类型**: `Callable[[Any], bool] | None`
- **默认值**: `None`
- **描述**: 自定义数据验证函数
- **示例**:
  ```python
  # 验证配置必须包含特定键
  def validate_config(data):
      required_keys = ['host', 'port', 'database']
      return isinstance(data, dict) and all(k in data for k in required_keys)
  
  store = JSONStore('config.json', validate_func=validate_config)
  
  # 验证列表项格式
  def validate_tasks(data):
      if not isinstance(data, list):
          return False
      return all(
          isinstance(item, dict) and 'id' in item and 'title' in item
          for item in data
      )
  
  store = JSONStore('tasks.json', validate_func=validate_tasks)
  
  # 验证数据范围
  def validate_settings(data):
      if not isinstance(data, dict):
          return False
      port = data.get('port', 0)
      return 1024 <= port <= 65535
  
  store = JSONStore('settings.json', validate_func=validate_settings)
  ```
- **使用建议**:
  - 关键配置必须验证
  - 验证函数应该快速执行
  - 返回布尔值，不要抛出异常
  - 验证失败时抛出 `ValidationError`

### 完整配置示例

```python
from pathlib import Path
from kernel.storage import JSONStore

# 开发环境配置
dev_store = JSONStore(
    file_path='dev_data.json',
    auto_create=True,        # 自动创建
    auto_backup=True,        # 启用备份
    max_backups=10,          # 保留10个备份
    indent=2,                # 易读格式
    encoding='utf-8',        # UTF-8编码
    validate_func=None       # 无验证
)

# 生产环境配置
prod_store = JSONStore(
    file_path=Path('/var/app/data.json'),
    auto_create=False,       # 不自动创建
    auto_backup=True,        # 必须备份
    max_backups=20,          # 保留20个备份
    indent=None,             # 紧凑格式
    encoding='utf-8',        # UTF-8编码
    validate_func=lambda d: isinstance(d, dict)  # 验证数据类型
)

# 高性能缓存配置
cache_store = JSONStore(
    file_path='cache.json',
    auto_create=True,        # 自动创建
    auto_backup=False,       # 不备份（提升性能）
    max_backups=0,           # 无备份
    indent=None,             # 紧凑格式
    encoding='utf-8',        # UTF-8编码
    validate_func=None       # 无验证
)
```

---

## DictJSONStore 配置

`DictJSONStore` 继承所有 `JSONStore` 的配置参数，并针对字典操作进行了优化。

### 基础使用

```python
from kernel.storage import DictJSONStore

# 使用默认配置
config = DictJSONStore('config.json')

# 完整配置
config = DictJSONStore(
    file_path='config.json',
    auto_create=True,
    auto_backup=True,
    max_backups=5,
    indent=2,
    encoding='utf-8',
    validate_func=lambda d: isinstance(d, dict)  # 确保是字典类型
)
```

### 推荐配置模式

#### 应用配置

```python
app_config = DictJSONStore(
    'config/app.json',
    auto_create=True,
    auto_backup=True,
    max_backups=10,
    indent=2,
    validate_func=lambda d: isinstance(d, dict) and 'app_name' in d
)
```

#### 用户设置

```python
user_settings = DictJSONStore(
    'user_settings.json',
    auto_create=True,
    auto_backup=True,
    max_backups=5,
    indent=2,
    validate_func=lambda d: isinstance(d, dict)
)
```

#### 缓存数据

```python
cache = DictJSONStore(
    'cache.json',
    auto_create=True,
    auto_backup=False,  # 缓存不需要备份
    indent=None,        # 紧凑格式
)
```

---

## ListJSONStore 配置

`ListJSONStore` 继承所有 `JSONStore` 的配置参数，并针对列表操作进行了优化。

### 基础使用

```python
from kernel.storage import ListJSONStore

# 使用默认配置
tasks = ListJSONStore('tasks.json')

# 完整配置
tasks = ListJSONStore(
    file_path='tasks.json',
    auto_create=True,
    auto_backup=True,
    max_backups=5,
    indent=2,
    encoding='utf-8',
    validate_func=lambda d: isinstance(d, list)  # 确保是列表类型
)
```

### 推荐配置模式

#### 任务队列

```python
def validate_task(data):
    if not isinstance(data, list):
        return False
    return all(isinstance(item, dict) and 'id' in item for item in data)

task_queue = ListJSONStore(
    'tasks.json',
    auto_create=True,
    auto_backup=True,
    max_backups=5,
    indent=2,
    validate_func=validate_task
)
```

#### 历史记录

```python
history = ListJSONStore(
    'history.json',
    auto_create=True,
    auto_backup=False,  # 历史记录可以不备份
    max_backups=0,
    indent=2
)
```

#### 数据列表

```python
data_list = ListJSONStore(
    'data.json',
    auto_create=True,
    auto_backup=True,
    max_backups=10,
    indent=2,
    validate_func=lambda d: isinstance(d, list) and len(d) <= 10000
)
```

---

## LogStore 配置

`LogStore` 专门用于日志存储，有独特的配置参数。

### 配置参数

#### directory
- **类型**: `str | Path`
- **必需**: ✅ 是
- **描述**: 日志文件存储目录
- **示例**:
  ```python
  logger = LogStore(directory='logs')
  logger = LogStore(directory=Path('/var/log/app'))
  ```

#### prefix
- **类型**: `str`
- **默认值**: `"log"`
- **描述**: 日志文件名前缀
- **示例**:
  ```python
  # 应用日志
  app_logger = LogStore(directory='logs', prefix='app')
  # 文件: logs/app_20260106.json
  
  # 访问日志
  access_logger = LogStore(directory='logs', prefix='access')
  # 文件: logs/access_20260106.json
  
  # 错误日志
  error_logger = LogStore(directory='logs', prefix='error')
  # 文件: logs/error_20260106.json
  ```

#### max_entries_per_file
- **类型**: `int`
- **默认值**: `1000`
- **描述**: 每个日志文件的最大条目数
- **示例**:
  ```python
  # 小文件（快速轮转）
  logger = LogStore(directory='logs', max_entries_per_file=100)
  
  # 中等文件（推荐）
  logger = LogStore(directory='logs', max_entries_per_file=1000)
  
  # 大文件（减少文件数量）
  logger = LogStore(directory='logs', max_entries_per_file=10000)
  ```
- **使用建议**:
  - 高频日志：100-500
  - 普通日志：1000-5000
  - 低频日志：5000-10000
  - 考虑磁盘I/O和查询性能

#### auto_rotate
- **类型**: `bool`
- **默认值**: `True`
- **描述**: 达到最大条目数时是否自动轮转
- **示例**:
  ```python
  # 自动轮转（推荐）
  logger = LogStore(directory='logs', auto_rotate=True)
  
  # 不自动轮转
  logger = LogStore(directory='logs', auto_rotate=False)
  ```
- **使用建议**:
  - 生产环境：必须启用
  - 避免单个文件过大
  - 便于日志管理和归档

### 完整配置示例

```python
from kernel.storage import LogStore

# 应用日志配置
app_logger = LogStore(
    directory='logs/app',
    prefix='app',
    max_entries_per_file=5000,
    auto_rotate=True
)

# 访问日志配置
access_logger = LogStore(
    directory='logs/access',
    prefix='access',
    max_entries_per_file=10000,  # 访问日志量大
    auto_rotate=True
)

# 错误日志配置
error_logger = LogStore(
    directory='logs/error',
    prefix='error',
    max_entries_per_file=1000,   # 错误日志较少
    auto_rotate=True
)

# 调试日志配置
debug_logger = LogStore(
    directory='logs/debug',
    prefix='debug',
    max_entries_per_file=500,    # 频繁轮转
    auto_rotate=True
)
```

---

## 配置模式

### 开发环境配置

```python
from kernel.storage import JSONStore, DictJSONStore, ListJSONStore, LogStore

# 通用存储
dev_store = JSONStore(
    'dev_data.json',
    auto_create=True,      # 自动创建
    auto_backup=True,      # 启用备份
    max_backups=5,         # 保留5个备份
    indent=2,              # 易读格式
    encoding='utf-8'
)

# 配置存储
dev_config = DictJSONStore(
    'dev_config.json',
    auto_create=True,
    auto_backup=True,
    max_backups=5,
    indent=2
)

# 任务存储
dev_tasks = ListJSONStore(
    'dev_tasks.json',
    auto_create=True,
    auto_backup=True,
    max_backups=5,
    indent=2
)

# 日志存储
dev_logger = LogStore(
    directory='logs/dev',
    prefix='dev',
    max_entries_per_file=100,   # 小文件便于调试
    auto_rotate=True
)
```

### 生产环境配置

```python
from pathlib import Path

# 通用存储
prod_store = JSONStore(
    Path('/var/app/data/data.json'),
    auto_create=False,     # 不自动创建
    auto_backup=True,      # 必须备份
    max_backups=20,        # 保留20个备份
    indent=None,           # 紧凑格式
    encoding='utf-8',
    validate_func=lambda d: isinstance(d, (dict, list))
)

# 配置存储
prod_config = DictJSONStore(
    Path('/etc/app/config.json'),
    auto_create=False,
    auto_backup=True,
    max_backups=10,
    indent=2,              # 配置文件保持易读
    validate_func=lambda d: isinstance(d, dict) and 'version' in d
)

# 任务存储
prod_tasks = ListJSONStore(
    Path('/var/app/data/tasks.json'),
    auto_create=True,
    auto_backup=True,
    max_backups=10,
    indent=None,
    validate_func=lambda d: isinstance(d, list)
)

# 日志存储
prod_logger = LogStore(
    directory=Path('/var/log/app'),
    prefix='app',
    max_entries_per_file=5000,
    auto_rotate=True
)
```

### 测试环境配置

```python
import tempfile
from pathlib import Path

# 使用临时目录
temp_dir = Path(tempfile.mkdtemp())

# 通用存储
test_store = JSONStore(
    temp_dir / 'test_data.json',
    auto_create=True,
    auto_backup=False,     # 测试不需要备份
    max_backups=0,
    indent=2,
    encoding='utf-8'
)

# 配置存储
test_config = DictJSONStore(
    temp_dir / 'test_config.json',
    auto_create=True,
    auto_backup=False,
    indent=2
)

# 日志存储
test_logger = LogStore(
    directory=temp_dir / 'logs',
    prefix='test',
    max_entries_per_file=10,  # 小文件便于测试
    auto_rotate=True
)
```

---

## 环境特定配置

### 使用环境变量

```python
import os
from pathlib import Path
from kernel.storage import JSONStore, LogStore

# 从环境变量读取配置
ENV = os.getenv('APP_ENV', 'development')
DATA_DIR = Path(os.getenv('DATA_DIR', './data'))
LOG_DIR = Path(os.getenv('LOG_DIR', './logs'))

# 根据环境选择配置
if ENV == 'production':
    store = JSONStore(
        DATA_DIR / 'data.json',
        auto_create=False,
        auto_backup=True,
        max_backups=20,
        indent=None
    )
elif ENV == 'development':
    store = JSONStore(
        DATA_DIR / 'data.json',
        auto_create=True,
        auto_backup=True,
        max_backups=5,
        indent=2
    )
else:  # testing
    store = JSONStore(
        DATA_DIR / 'data.json',
        auto_create=True,
        auto_backup=False,
        max_backups=0,
        indent=2
    )

# 日志配置
logger = LogStore(
    directory=LOG_DIR,
    prefix=ENV,
    max_entries_per_file=1000 if ENV == 'production' else 100,
    auto_rotate=True
)
```

### 配置工厂模式

```python
from typing import Literal
from kernel.storage import JSONStore, DictJSONStore, LogStore

Environment = Literal['development', 'production', 'testing']

class StorageConfig:
    @staticmethod
    def create_store(env: Environment, file_path: str) -> JSONStore:
        configs = {
            'development': {
                'auto_create': True,
                'auto_backup': True,
                'max_backups': 5,
                'indent': 2,
            },
            'production': {
                'auto_create': False,
                'auto_backup': True,
                'max_backups': 20,
                'indent': None,
            },
            'testing': {
                'auto_create': True,
                'auto_backup': False,
                'max_backups': 0,
                'indent': 2,
            }
        }
        return JSONStore(file_path, **configs[env])
    
    @staticmethod
    def create_logger(env: Environment, directory: str) -> LogStore:
        configs = {
            'development': {
                'max_entries_per_file': 100,
            },
            'production': {
                'max_entries_per_file': 5000,
            },
            'testing': {
                'max_entries_per_file': 10,
            }
        }
        return LogStore(
            directory=directory,
            prefix=env,
            auto_rotate=True,
            **configs[env]
        )

# 使用
store = StorageConfig.create_store('production', 'data.json')
logger = StorageConfig.create_logger('production', 'logs')
```

---

## 配置验证

### 配置数据结构

```python
from kernel.storage import DictJSONStore, ValidationError

def validate_app_config(data):
    """验证应用配置"""
    if not isinstance(data, dict):
        return False
    
    # 必需字段
    required = ['app_name', 'version', 'debug']
    if not all(key in data for key in required):
        return False
    
    # 类型检查
    if not isinstance(data['app_name'], str):
        return False
    if not isinstance(data['version'], str):
        return False
    if not isinstance(data['debug'], bool):
        return False
    
    # 值范围检查
    if 'port' in data:
        if not (1024 <= data['port'] <= 65535):
            return False
    
    return True

store = DictJSONStore(
    'config.json',
    validate_func=validate_app_config
)

try:
    store.write({
        'app_name': 'MoFox',
        'version': '1.0.0',
        'debug': True,
        'port': 8000
    })
except ValidationError as e:
    print(f"配置验证失败: {e}")
```

### 复杂验证示例

```python
def validate_database_config(data):
    """验证数据库配置"""
    if not isinstance(data, dict):
        return False
    
    # 数据库类型
    valid_types = ['mysql', 'postgresql', 'sqlite']
    if data.get('type') not in valid_types:
        return False
    
    # SQLite特殊处理
    if data['type'] == 'sqlite':
        return 'path' in data
    
    # MySQL/PostgreSQL需要的字段
    required = ['host', 'port', 'database', 'user', 'password']
    if not all(key in data for key in required):
        return False
    
    # 端口范围
    if not (1 <= data['port'] <= 65535):
        return False
    
    return True

def validate_user_list(data):
    """验证用户列表"""
    if not isinstance(data, list):
        return False
    
    for user in data:
        if not isinstance(user, dict):
            return False
        
        # 必需字段
        if not all(key in user for key in ['id', 'name', 'email']):
            return False
        
        # 邮箱格式简单验证
        if '@' not in user['email']:
            return False
    
    return True
```

### 使用Schema验证（推荐）

```python
# 可以结合第三方库如pydantic进行验证
from pydantic import BaseModel, ValidationError as PydanticValidationError
from typing import List

class UserModel(BaseModel):
    id: int
    name: str
    email: str
    age: int = 0

def validate_with_pydantic(data):
    try:
        # 验证单个对象
        if isinstance(data, dict):
            UserModel(**data)
            return True
        # 验证列表
        elif isinstance(data, list):
            for item in data:
                UserModel(**item)
            return True
        return False
    except PydanticValidationError:
        return False

store = JSONStore('users.json', validate_func=validate_with_pydantic)
```

---

## 配置最佳实践

### 1. 分离配置文件

```python
# 不推荐：所有配置在一个文件
config = DictJSONStore('config.json')

# 推荐：按功能分离
app_config = DictJSONStore('config/app.json')
db_config = DictJSONStore('config/database.json')
cache_config = DictJSONStore('config/cache.json')
```

### 2. 使用类型特化存储器

```python
# 不推荐：用通用存储器
store = JSONStore('config.json')
data = store.read()
data['key'] = 'value'
store.write(data)

# 推荐：使用字典存储器
store = DictJSONStore('config.json')
store.set('key', 'value')
```

### 3. 合理设置备份

```python
# 重要配置：多备份
prod_config = DictJSONStore(
    'config.json',
    auto_backup=True,
    max_backups=20
)

# 缓存数据：不备份
cache = DictJSONStore(
    'cache.json',
    auto_backup=False
)

# 临时数据：不备份
temp = DictJSONStore(
    'temp.json',
    auto_backup=False
)
```

### 4. 启用数据验证

```python
# 关键配置必须验证
config = DictJSONStore(
    'config.json',
    validate_func=lambda d: isinstance(d, dict) and 'version' in d
)

# 用户数据必须验证
users = ListJSONStore(
    'users.json',
    validate_func=lambda d: isinstance(d, list)
)
```

### 5. 环境隔离

```python
import os

ENV = os.getenv('ENV', 'development')

# 使用环境特定的配置文件
config = DictJSONStore(f'config.{ENV}.json')

# 或使用环境特定的目录
logger = LogStore(directory=f'logs/{ENV}', prefix='app')
```

---

## 总结

### 配置检查清单

在配置 Storage 模块时，请检查以下项：

- [ ] 选择合适的存储器类型（JSONStore/DictJSONStore/ListJSONStore/LogStore）
- [ ] 设置正确的文件路径
- [ ] 根据环境配置 `auto_create`
- [ ] 重要数据启用 `auto_backup`
- [ ] 设置合理的 `max_backups` 数量
- [ ] 选择合适的 `indent`（易读 vs 紧凑）
- [ ] 使用 UTF-8 编码
- [ ] 为关键数据添加 `validate_func`
- [ ] 日志存储设置合理的 `max_entries_per_file`
- [ ] 启用 `auto_rotate` 避免文件过大

### 快速参考

| 配置项 | 开发环境 | 生产环境 | 测试环境 |
|--------|----------|----------|----------|
| auto_create | True | False | True |
| auto_backup | True | True | False |
| max_backups | 5 | 20 | 0 |
| indent | 2 | None/2 | 2 |
| validate_func | 可选 | 推荐 | 可选 |
| max_entries_per_file | 100 | 5000 | 10 |

### 下一步

- 查看 [API参考](./API_REFERENCE.md) 了解详细的方法说明
- 查看 [最佳实践](./BEST_PRACTICES.md) 学习使用模式
- 查看 [故障排查](./TROUBLESHOOTING.md) 解决常见问题
