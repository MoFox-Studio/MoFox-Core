# Logger 最佳实践

本文档提供 MoFox Logger 的最佳使用实践和建议。

## 目录

- [基础最佳实践](#基础最佳实践)
- [日志级别使用](#日志级别使用)
- [元数据使用](#元数据使用)
- [性能优化](#性能优化)
- [日志管理](#日志管理)
- [安全考虑](#安全考虑)
- [环境配置](#环境配置)
- [常见模式](#常见模式)

## 基础最佳实践

### 1. 在模块级别获取日志器

✅ **推荐:**
```python
from kernel.logger import get_logger

# 模块顶部
logger = get_logger(__name__)

def my_function():
    logger.info("函数执行")
```

❌ **不推荐:**
```python
def my_function():
    # 每次调用都创建日志器
    logger = get_logger(__name__)
    logger.info("函数执行")
```

**原因**: 日志器是单例的，在模块级别获取一次即可，避免重复创建。

### 2. 使用 `__name__` 作为日志器名称

✅ **推荐:**
```python
logger = get_logger(__name__)
```

❌ **不推荐:**
```python
logger = get_logger("mylogger")  # 硬编码名称
```

**原因**: `__name__` 自动提供模块的完整路径，便于定位日志来源。

### 3. 应用启动时初始化日志系统

✅ **推荐:**
```python
# main.py
from kernel.logger import setup_logger, create_production_config

def main():
    # 第一件事：设置日志
    config = create_production_config()
    setup_logger(config)
    
    # 然后才是应用逻辑
    app.run()

if __name__ == "__main__":
    main()
```

### 4. 应用退出时关闭日志系统

✅ **推荐:**
```python
from kernel.logger import shutdown
import atexit

# 注册退出处理
atexit.register(shutdown)

# 或在 finally 块中
try:
    app.run()
finally:
    shutdown()
```

## 日志级别使用

### 日志级别指南

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| DEBUG | 详细的调试信息 | 变量值、函数调用、循环迭代 |
| INFO | 一般信息记录 | 应用启动、用户操作、重要状态变化 |
| WARNING | 警告但不影响运行 | 配置缺失使用默认值、API即将废弃 |
| ERROR | 错误但程序可继续 | 请求失败、数据验证错误 |
| CRITICAL | 严重错误需要立即处理 | 数据库不可用、系统资源耗尽 |

### DEBUG 级别

✅ **适当使用:**
```python
logger.debug(f"处理数据: {data_id}")
logger.debug(f"查询参数: {params}")
logger.debug(f"API响应时间: {elapsed_time}ms")
```

❌ **过度使用:**
```python
# 避免在循环中大量DEBUG日志
for item in large_list:  # 100万条
    logger.debug(f"处理项目: {item}")  # 会产生100万条日志
```

**改进:**
```python
logger.info(f"开始处理 {len(large_list)} 个项目")
for i, item in enumerate(large_list):
    if i % 10000 == 0:  # 每1万条记录一次
        logger.debug(f"进度: {i}/{len(large_list)}")
```

### INFO 级别

✅ **推荐:**
```python
logger.info("应用启动成功")
logger.info(f"用户 {user_id} 登录")
logger.info(f"处理完成，耗时 {duration}秒")
```

### WARNING 级别

✅ **推荐:**
```python
logger.warning("配置项缺失，使用默认值")
logger.warning(f"API调用耗时过长: {duration}秒")
logger.warning(f"内存使用率: {memory_percent}%")
```

### ERROR 级别

✅ **推荐:**
```python
try:
    process_data()
except ValidationError as e:
    logger.error(f"数据验证失败: {e}")
```

### 异常日志

✅ **推荐 - 使用 exception():**
```python
try:
    risky_operation()
except Exception as e:
    logger.exception("操作失败")  # 自动记录堆栈
```

❌ **不推荐:**
```python
try:
    risky_operation()
except Exception as e:
    logger.error(f"操作失败: {e}")  # 缺少堆栈信息
```

## 元数据使用

### 请求追踪

✅ **推荐模式:**
```python
from kernel.logger import get_logger, with_metadata, LogMetadata
import uuid

logger = get_logger(__name__)

async def handle_request(request):
    # 生成请求ID
    request_id = LogMetadata.set_request_id()
    
    # 使用上下文管理器
    with with_metadata(
        user_id=request.user.id,
        ip=request.client.host,
        path=request.url.path
    ):
        logger.info("开始处理请求")
        
        try:
            result = await process(request)
            logger.info("请求处理成功")
            return result
        except Exception:
            logger.exception("请求处理失败")
            raise
```

### 会话追踪

✅ **推荐:**
```python
class SessionManager:
    def __init__(self, session_id):
        self.session_id = session_id
        LogMetadata.set_session_id(session_id)
    
    def process(self):
        logger.info("会话处理")  # 自动包含session_id
```

### 清理元数据

✅ **推荐:**
```python
def background_task():
    LogMetadata.set_custom("task_id", "task_123")
    
    try:
        # 任务逻辑
        pass
    finally:
        LogMetadata.clear()  # 清理元数据
```

## 性能优化

### 1. 使用合适的日志级别

生产环境使用 INFO 或更高级别：

```python
from kernel.logger import create_production_config

config = create_production_config()
config.level = "INFO"  # 不记录DEBUG
```

### 2. 启用异步日志

高并发场景启用异步：

```python
config = LoggerConfig(
    async_logging=True,
    async_queue_size=5000
)
```

**性能对比:**
- 同步日志: ~1000 日志/秒
- 异步日志: ~50000+ 日志/秒

### 3. 延迟字符串格式化

✅ **推荐 - 使用占位符:**
```python
logger.debug("用户 %s 执行操作 %s", user_id, action)
```

❌ **不推荐 - 使用 f-string:**
```python
logger.debug(f"用户 {user_id} 执行操作 {action}")
```

**原因**: 使用占位符时，如果日志级别不够，字符串不会被格式化，节省CPU。

### 4. 条件日志记录

```python
if logger.isEnabledFor(logging.DEBUG):
    # 只在DEBUG级别时才执行复杂计算
    expensive_data = compute_expensive_data()
    logger.debug(f"数据: {expensive_data}")
```

### 5. 批量操作

❌ **不推荐:**
```python
for item in items:
    logger.info(f"处理: {item}")
```

✅ **推荐:**
```python
logger.info(f"开始批量处理 {len(items)} 项")
# 批量处理
logger.info("批量处理完成")
```

## 日志管理

### 文件轮转

✅ **推荐配置:**
```python
config = LoggerConfig(
    file_max_bytes=50 * 1024 * 1024,  # 50MB
    file_backup_count=10,              # 保留10个
    timed_file_enabled=True,           # 时间轮转
    timed_file_when="midnight"         # 每天轮转
)
```

### 自动清理

✅ **推荐 - 定期清理:**
```python
from kernel.logger import create_auto_cleaner
import schedule

cleaner = create_auto_cleaner(
    log_directory="logs",
    max_age_days=30,
    max_size_mb=1000,
    compress_after_days=7
)

# 每天凌晨3点执行
schedule.every().day.at("03:00").do(cleaner.run)
```

### 日志压缩

```python
from kernel.logger import LogCleaner

cleaner = LogCleaner("logs")

# 压缩7天前的日志
cleaner.compress_logs(pattern="*.log.*")
```

## 安全考虑

### 1. 避免记录敏感信息

❌ **不要这样:**
```python
logger.info(f"用户登录: password={password}")
logger.debug(f"信用卡: {credit_card}")
logger.info(f"Token: {access_token}")
```

✅ **应该这样:**
```python
logger.info(f"用户登录: user_id={user_id}")
logger.debug("信用卡号已验证")  # 不记录具体数字
logger.info("Token已生成")  # 不记录token值

# 或者脱敏
logger.info(f"信用卡: ****{credit_card[-4:]}")
```

### 2. 脱敏工具函数

```python
def mask_sensitive_data(data: str, show_last: int = 4) -> str:
    """脱敏敏感数据"""
    if len(data) <= show_last:
        return "*" * len(data)
    return "*" * (len(data) - show_last) + data[-show_last:]

# 使用
logger.info(f"手机号: {mask_sensitive_data(phone)}")
```

### 3. 限制日志文件权限

```python
import os
from pathlib import Path

log_file = Path("logs/app.log")
if log_file.exists():
    os.chmod(log_file, 0o600)  # 仅所有者可读写
```

## 环境配置

### 开发环境

```python
from kernel.logger import create_development_config, setup_logger

if os.getenv("ENV") == "development":
    config = create_development_config()
    config.level = "DEBUG"
    config.console_colors = True
    setup_logger(config)
```

### 生产环境

```python
from kernel.logger import create_production_config, setup_logger

if os.getenv("ENV") == "production":
    config = create_production_config()
    config.level = "INFO"
    config.file_format = "json"  # 便于日志分析
    config.async_logging = True  # 高性能
    config.console_enabled = False  # 禁用控制台
    setup_logger(config)
```

### 测试环境

```python
from kernel.logger import create_testing_config, setup_logger

if os.getenv("ENV") == "testing":
    config = create_testing_config()
    config.level = "WARNING"  # 减少噪音
    config.file_enabled = False
    setup_logger(config)
```

## 常见模式

### Web 应用模式

```python
from fastapi import FastAPI, Request
from kernel.logger import get_logger, with_metadata, LogMetadata
import time

app = FastAPI()
logger = get_logger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 生成请求ID
    request_id = LogMetadata.set_request_id()
    
    # 记录请求
    with with_metadata(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host
    ):
        logger.info("收到请求")
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            logger.info(
                f"请求完成",
                extra={"duration": duration, "status": response.status_code}
            )
            
            return response
        except Exception:
            logger.exception("请求处理异常")
            raise
        finally:
            LogMetadata.clear()
```

### 数据库操作模式

```python
from kernel.logger import get_logger, with_metadata
import time

logger = get_logger(__name__)

class Database:
    def query(self, sql, params=None):
        with with_metadata(operation="db_query"):
            start = time.time()
            logger.debug(f"执行SQL: {sql}")
            
            try:
                result = self._execute(sql, params)
                duration = time.time() - start
                logger.info(f"查询完成，耗时 {duration:.3f}秒")
                return result
            except Exception as e:
                logger.error(f"查询失败: {e}")
                raise
```

### 异步任务模式

```python
from kernel.logger import get_logger, LogMetadata
import asyncio

logger = get_logger(__name__)

async def async_task(task_id: str):
    LogMetadata.set_custom("task_id", task_id)
    
    try:
        logger.info("任务开始")
        
        # 任务逻辑
        await process()
        
        logger.info("任务完成")
    except Exception:
        logger.exception("任务失败")
        raise
    finally:
        LogMetadata.clear()
```

### 长时间运行的任务

```python
from kernel.logger import get_logger
import time

logger = get_logger(__name__)

def long_running_task(items):
    total = len(items)
    logger.info(f"开始处理 {total} 项")
    
    start_time = time.time()
    processed = 0
    
    for i, item in enumerate(items, 1):
        try:
            process_item(item)
            processed += 1
            
            # 每处理10%报告一次
            if i % (total // 10) == 0:
                progress = (i / total) * 100
                elapsed = time.time() - start_time
                eta = (elapsed / i) * (total - i)
                logger.info(
                    f"进度: {progress:.0f}%, "
                    f"已处理: {processed}, "
                    f"预计剩余: {eta:.0f}秒"
                )
        except Exception as e:
            logger.error(f"处理项目 {i} 失败: {e}")
    
    total_time = time.time() - start_time
    logger.info(f"任务完成，总耗时: {total_time:.2f}秒，成功: {processed}/{total}")
```

## 测试日志

### 测试中验证日志

```python
import logging
from kernel.logger import setup_logger, get_logger

def test_logging(caplog):
    """使用 pytest 的 caplog fixture"""
    setup_logger()
    logger = get_logger(__name__)
    
    with caplog.at_level(logging.INFO):
        logger.info("测试消息")
    
    assert "测试消息" in caplog.text
```

### Mock 日志器

```python
from unittest.mock import Mock
from kernel.logger import get_logger

def test_with_mock():
    logger = Mock()
    # 测试逻辑
    logger.info.assert_called_once()
```

## 避免的反模式

### ❌ 反模式1: 过度日志

```python
# 不要这样
logger.debug("进入函数")
logger.debug(f"参数: {arg1}, {arg2}")
logger.debug("调用API")
logger.debug("API返回")
logger.debug("退出函数")
```

### ❌ 反模式2: 日志即调试

```python
# 不要用日志代替调试器
logger.debug(f"变量1: {var1}")
logger.debug(f"变量2: {var2}")
logger.debug(f"变量3: {var3}")
# ... 100行日志
```

### ❌ 反模式3: 异常吞没

```python
# 不要这样
try:
    operation()
except Exception:
    logger.error("出错了")  # 没有上下文，无法追踪
    pass  # 吞没异常
```

✅ **正确做法:**
```python
try:
    operation()
except Exception:
    logger.exception("操作失败，详细信息")  # 包含堆栈
    raise  # 重新抛出或适当处理
```

## 总结

1. **在模块级别获取日志器**
2. **合理使用日志级别**
3. **生产环境使用INFO级别**
4. **使用元数据追踪请求**
5. **定期清理日志文件**
6. **不要记录敏感信息**
7. **使用异步日志提高性能**
8. **记录异常使用 exception()**
9. **使用占位符而非f-string**
10. **应用启动时初始化日志**

## 相关文档

- [配置指南](./CONFIGURATION_GUIDE.md)
- [API 参考](./API_REFERENCE.md)
- [故障排查](./TROUBLESHOOTING.md)
