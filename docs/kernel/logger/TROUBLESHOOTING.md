# Logger 故障排查指南

本文档提供 MoFox Logger 常见问题的排查和解决方案。

## 目录

- [日志未输出](#日志未输出)
- [性能问题](#性能问题)
- [文件问题](#文件问题)
- [格式问题](#格式问题)
- [元数据问题](#元数据问题)
- [清理问题](#清理问题)
- [常见错误](#常见错误)

## 日志未输出

### 问题1: 日志完全不输出

**症状**: 调用 `logger.info()` 等方法，但看不到任何输出。

**可能原因:**

1. **日志系统未初始化**

```python
# 检查是否调用了 setup_logger()
from kernel.logger import setup_logger

setup_logger()  # 必须先调用
```

2. **日志级别设置过高**

```python
# 检查配置
from kernel.logger.config import ConfigManager

manager = ConfigManager()
config = manager.get_config()
print(f"当前级别: {config.level}")  # 如果是 ERROR，INFO 不会输出

# 降低级别
from kernel.logger import set_level
set_level("DEBUG")
```

3. **所有处理器都被禁用**

```python
config = LoggerConfig(
    console_enabled=False,  # 控制台禁用
    file_enabled=False      # 文件也禁用
)
# 至少启用一个
config.console_enabled = True
```

**解决方案:**
```python
from kernel.logger import setup_logger, get_logger, LoggerConfig

# 使用最简单的配置
config = LoggerConfig(
    level="DEBUG",
    console_enabled=True
)
setup_logger(config)

logger = get_logger(__name__)
logger.info("测试消息")  # 现在应该可见
```

### 问题2: 只有错误日志输出

**症状**: ERROR 级别的日志能看到，但 INFO、DEBUG 看不到。

**原因**: 日志级别设置为 ERROR

**解决方案:**
```python
from kernel.logger import set_level

set_level("INFO")  # 或 "DEBUG"
```

### 问题3: 特定模块的日志不输出

**症状**: 某些模块的日志不输出，其他模块正常。

**检查:**
```python
import logging

# 检查特定日志器的级别
logger = logging.getLogger("my_module")
print(f"日志器级别: {logger.level}")
print(f"有效级别: {logger.getEffectiveLevel()}")

# 重置级别
logger.setLevel(logging.DEBUG)
```

## 性能问题

### 问题1: 日志记录导致应用变慢

**症状**: 启用日志后，应用性能明显下降。

**诊断:**
```python
import time
from kernel.logger import get_logger

logger = get_logger(__name__)

start = time.time()
for i in range(10000):
    logger.debug(f"消息 {i}")
elapsed = time.time() - start

print(f"10000条日志耗时: {elapsed:.2f}秒")
# 如果 > 1秒，说明有性能问题
```

**解决方案:**

1. **降低日志级别**
```python
from kernel.logger import LoggerConfig, setup_logger

config = LoggerConfig(
    level="INFO"  # 不记录 DEBUG
)
setup_logger(config)
```

2. **启用异步日志**
```python
config = LoggerConfig(
    async_logging=True,
    async_queue_size=5000
)
setup_logger(config)
```

3. **使用占位符而非f-string**
```python
# ❌ 慢 - 总是格式化
logger.debug(f"值: {expensive_calculation()}")

# ✅ 快 - 只在需要时格式化
logger.debug("值: %s", expensive_calculation())
```

4. **条件日志**
```python
if logger.isEnabledFor(logging.DEBUG):
    expensive_data = compute_data()
    logger.debug(f"数据: {expensive_data}")
```

### 问题2: 高并发时日志丢失

**症状**: 高并发场景下，部分日志未记录。

**原因**: 异步队列满了

**解决方案:**
```python
config = LoggerConfig(
    async_logging=True,
    async_queue_size=10000  # 增大队列
)
```

### 问题3: 磁盘IO过高

**症状**: 磁盘IO使用率很高。

**检查:**
```python
import os
import psutil

# 监控磁盘IO
disk_io = psutil.disk_io_counters()
print(f"写入字节: {disk_io.write_bytes}")
```

**解决方案:**

1. **启用异步日志**（减少同步写入）
2. **减少日志量**（提高日志级别）
3. **增大缓冲区**
```python
# 创建自定义处理器时
handler = FileHandler(
    filename="logs/app.log",
    encoding='utf-8'
)
handler.stream.buffer_size = 8192  # 增大缓冲
```

## 文件问题

### 问题1: 日志文件未创建

**症状**: 配置了文件输出，但文件不存在。

**检查:**
```python
from pathlib import Path

log_file = Path("logs/app.log")
print(f"文件存在: {log_file.exists()}")
print(f"父目录存在: {log_file.parent.exists()}")

# 检查权限
import os
if log_file.parent.exists():
    print(f"可写: {os.access(log_file.parent, os.W_OK)}")
```

**解决方案:**
```python
# 确保目录存在
from pathlib import Path

log_dir = Path("logs")
log_dir.mkdir(parents=True, exist_ok=True)

# 检查权限
import os
os.chmod(log_dir, 0o755)
```

### 问题2: 权限被拒绝

**错误信息**: `PermissionError: [Errno 13] Permission denied: 'logs/app.log'`

**解决方案:**

1. **检查文件权限**
```bash
# Linux/Mac
ls -l logs/
chmod 644 logs/app.log

# Windows (PowerShell)
icacls logs\app.log
```

2. **使用有权限的目录**
```python
import os
from pathlib import Path

# 使用用户目录
home = Path.home()
log_dir = home / ".mofox" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

config = LoggerConfig(
    file_path=str(log_dir / "app.log")
)
```

### 问题3: 日志文件未轮转

**症状**: 日志文件超过配置的大小，但没有创建新文件。

**检查:**
```python
from pathlib import Path

log_file = Path("logs/app.log")
file_size = log_file.stat().st_size
print(f"文件大小: {file_size / (1024*1024):.2f} MB")

# 检查配置
from kernel.logger.config import ConfigManager
config = ConfigManager().get_config()
print(f"最大大小: {config.file_max_bytes / (1024*1024):.2f} MB")
```

**可能原因:**
- 使用了多个进程写同一个文件
- 文件被其他程序锁定

**解决方案:**
```python
# 每个进程使用独立的日志文件
import os

config = LoggerConfig(
    file_path=f"logs/app_{os.getpid()}.log"
)
```

### 问题4: 日志文件过大占满磁盘

**症状**: 磁盘空间不足。

**检查磁盘使用:**
```python
import shutil

total, used, free = shutil.disk_usage("/")
print(f"总空间: {total // (2**30)} GB")
print(f"已用: {used // (2**30)} GB")
print(f"可用: {free // (2**30)} GB")

# 检查日志目录大小
from pathlib import Path

log_dir = Path("logs")
total_size = sum(f.stat().st_size for f in log_dir.rglob('*') if f.is_file())
print(f"日志目录大小: {total_size // (2**20)} MB")
```

**解决方案:**
```python
from kernel.logger import create_auto_cleaner

# 设置自动清理
cleaner = create_auto_cleaner(
    log_directory="logs",
    max_age_days=7,      # 只保留7天
    max_size_mb=1000,    # 限制1GB
    compress_after_days=1 # 1天后压缩
)

# 立即执行清理
results = cleaner.run()
print(f"删除了 {results['deleted_old']} 个文件")
print(f"压缩了 {results['compressed']} 个文件")
```

## 格式问题

### 问题1: JSON 格式不正确

**症状**: JSON 日志无法被解析。

**检查:**
```python
import json
from pathlib import Path

log_file = Path("logs/app.log")
with open(log_file) as f:
    for i, line in enumerate(f, 1):
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            print(f"第 {i} 行格式错误: {e}")
```

**解决方案:**
```python
# 确保使用 JSON 格式
config = LoggerConfig(
    file_format="json",
    file_path="logs/app.json"
)
```

### 问题2: 彩色输出不工作

**症状**: 控制台没有颜色显示。

**原因:**
- 终端不支持 ANSI 颜色
- 在 Windows CMD 中

**解决方案:**

1. **Windows 10+ 启用 ANSI**
```python
import os
os.system("")  # 启用 ANSI 支持
```

2. **使用 Windows Terminal**

3. **禁用颜色**
```python
config = LoggerConfig(
    console_colors=False
)
```

### 问题3: 中文乱码

**症状**: 日志中的中文显示为乱码。

**解决方案:**
```python
# 确保使用 UTF-8 编码
config = LoggerConfig(
    file_path="logs/app.log"
)

# FileHandler 默认使用 UTF-8
# 如果仍有问题，检查终端编码
import sys
print(f"默认编码: {sys.getdefaultencoding()}")
print(f"终端编码: {sys.stdout.encoding}")
```

## 元数据问题

### 问题1: 元数据未出现在日志中

**症状**: 设置了元数据，但日志中没有。

**检查:**
```python
from kernel.logger import LogMetadata

# 检查元数据
print(f"请求ID: {LogMetadata.get_request_id()}")
print(f"所有元数据: {LogMetadata.get_all()}")

# 检查配置
from kernel.logger.config import ConfigManager
config = ConfigManager().get_config()
print(f"包含元数据: {config.include_metadata}")
```

**解决方案:**
```python
# 确保启用元数据
config = LoggerConfig(
    include_metadata=True
)
setup_logger(config)

# 确保设置了元数据
from kernel.logger import LogMetadata, get_logger

LogMetadata.set_request_id("req_123")
logger = get_logger(__name__)
logger.info("测试")  # 应该包含 request_id
```

### 问题2: 元数据泄露到其他请求

**症状**: 不同请求看到了其他请求的元数据。

**原因**: 使用了全局状态，未正确清理

**解决方案:**
```python
from kernel.logger import with_metadata, LogMetadata

# ✅ 推荐 - 使用上下文管理器
def handle_request(request_id):
    with with_metadata(request_id=request_id):
        # 处理请求
        pass
    # 自动清理

# ❌ 不推荐 - 手动管理需要确保清理
def handle_request(request_id):
    LogMetadata.set_request_id(request_id)
    try:
        # 处理请求
        pass
    finally:
        LogMetadata.clear()  # 必须清理
```

## 清理问题

### 问题1: 自动清理不工作

**症状**: 设置了自动清理，但旧日志仍然存在。

**检查:**
```python
from kernel.logger import LogCleaner

cleaner = LogCleaner("logs")
stats = cleaner.get_statistics()
print(f"日志文件数: {stats['total_files']}")
print(f"最旧文件: {stats['oldest_file']}")

# 手动测试清理
deleted = cleaner.delete_old_logs(max_age_days=30)
print(f"删除了 {deleted} 个文件")
```

**解决方案:**

1. **确保定期调用清理**
```python
from kernel.logger import create_auto_cleaner
import schedule

cleaner = create_auto_cleaner()

# 设置定时任务
schedule.every().day.at("03:00").do(cleaner.run)

# 在主循环中
while True:
    schedule.run_pending()
    time.sleep(60)
```

2. **检查文件修改时间**
```python
from pathlib import Path
import datetime

for log_file in Path("logs").glob("*.log"):
    mtime = datetime.datetime.fromtimestamp(log_file.stat().st_mtime)
    age = (datetime.datetime.now() - mtime).days
    print(f"{log_file.name}: {age} 天前")
```

### 问题2: 压缩失败

**症状**: `compress_logs()` 失败或产生损坏的文件。

**检查:**
```python
import gzip

# 验证压缩文件
try:
    with gzip.open("logs/app.log.gz", 'rt') as f:
        f.read()
    print("压缩文件正常")
except Exception as e:
    print(f"压缩文件损坏: {e}")
```

**解决方案:**
```python
from kernel.logger import LogCleaner

cleaner = LogCleaner("logs")

# 手动压缩并检查
try:
    compressed_count = cleaner.compress_logs(keep_original=True)
    print(f"压缩了 {compressed_count} 个文件")
except Exception as e:
    print(f"压缩失败: {e}")
```

## 常见错误

### 错误1: AttributeError: module 'kernel.logger' has no attribute 'xxx'

**原因**: 导入错误或函数名拼写错误

**解决方案:**
```python
# 检查导入
from kernel.logger import setup_logger  # 正确
from kernel.logger import setup_logging  # 错误，应该是 setup_logger

# 查看可用的函数
import kernel.logger
print(dir(kernel.logger))
```

### 错误2: TypeError: __init__() got an unexpected keyword argument

**原因**: 配置参数名称错误

**解决方案:**
```python
# 检查配置参数
from kernel.logger import LoggerConfig
import inspect

sig = inspect.signature(LoggerConfig.__init__)
print("可用参数:", list(sig.parameters.keys()))

# 使用正确的参数名
config = LoggerConfig(
    level="INFO",  # 正确
    # log_level="INFO"  # 错误
)
```

### 错误3: 循环导入

**症状**: `ImportError: cannot import name 'xxx' from partially initialized module`

**原因**: 循环导入

**解决方案:**
```python
# ❌ 错误 - 在模块顶部
from kernel.logger import get_logger
logger = get_logger(__name__)

# 如果这会导致循环导入，改为：

# ✅ 正确 - 在函数内部
def my_function():
    from kernel.logger import get_logger
    logger = get_logger(__name__)
    logger.info("消息")
```

## 调试技巧

### 1. 启用详细日志

```python
import logging

# 启用所有模块的 DEBUG 日志
logging.basicConfig(level=logging.DEBUG)

# 或只启用特定模块
logging.getLogger("kernel.logger").setLevel(logging.DEBUG)
```

### 2. 检查处理器

```python
import logging

root = logging.getLogger()
print(f"处理器数量: {len(root.handlers)}")
for i, handler in enumerate(root.handlers):
    print(f"处理器 {i}: {type(handler).__name__}")
    print(f"  级别: {handler.level}")
    print(f"  格式化器: {type(handler.formatter).__name__}")
```

### 3. 测试日志配置

```python
from kernel.logger import setup_logger, get_logger, LoggerConfig

# 最简单的配置
config = LoggerConfig(
    level="DEBUG",
    console_enabled=True,
    file_enabled=False  # 暂时禁用文件
)
setup_logger(config)

logger = get_logger(__name__)
logger.debug("DEBUG消息")
logger.info("INFO消息")
logger.warning("WARNING消息")
logger.error("ERROR消息")
```

### 4. 日志健康检查

```python
def check_logger_health():
    """检查日志系统健康状态"""
    from kernel.logger.config import ConfigManager
    from pathlib import Path
    import logging
    
    print("=== 日志系统健康检查 ===\n")
    
    # 1. 检查配置
    manager = ConfigManager()
    config = manager.get_config()
    if config:
        print(f"✓ 配置已加载: {config.name}")
        print(f"  级别: {config.level}")
    else:
        print("✗ 配置未加载")
        return False
    
    # 2. 检查处理器
    root = logging.getLogger()
    if root.handlers:
        print(f"✓ 处理器数量: {len(root.handlers)}")
    else:
        print("✗ 没有处理器")
        return False
    
    # 3. 检查文件
    if config.file_enabled:
        log_file = Path(config.file_path)
        if log_file.exists():
            print(f"✓ 日志文件存在: {log_file}")
        else:
            print(f"✗ 日志文件不存在: {log_file}")
    
    # 4. 测试写入
    try:
        logger = logging.getLogger("health_check")
        logger.info("健康检查测试消息")
        print("✓ 日志写入测试成功")
    except Exception as e:
        print(f"✗ 日志写入失败: {e}")
        return False
    
    print("\n=== 健康检查完成 ===")
    return True

# 运行检查
check_logger_health()
```

## 获取帮助

如果问题仍未解决：

1. **查看示例代码**: `src/kernel/logger/example.py`
2. **查看测试**: `tests/kernel/logger/`
3. **查看文档**: `docs/kernel/logger/`
4. **提交Issue**: GitHub Issues

## 相关文档

- [配置指南](./CONFIGURATION_GUIDE.md)
- [API 参考](./API_REFERENCE.md)
- [最佳实践](./BEST_PRACTICES.md)
