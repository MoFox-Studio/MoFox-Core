"""
Storage 存储模块使用示例

展示各种JSON存储功能的使用方法
"""

from kernel.storage import (
    JSONStore,
    DictJSONStore,
    ListJSONStore,
    LogStore,
    JSONStoreError,
)
from datetime import datetime


def basic_json_store_example():
    """基本JSON存储示例"""
    print("\n=== 基本JSON存储示例 ===")
    
    # 创建存储器
    store = JSONStore("data/config.json")
    
    # 写入数据
    config = {
        "app_name": "MoFox",
        "version": "1.0.0",
        "settings": {
            "theme": "dark",
            "language": "zh-CN"
        }
    }
    store.write(config)
    print("✓ 数据已写入")
    
    # 读取数据
    loaded_config = store.read()
    print(f"✓ 读取数据: {loaded_config}")
    
    # 更新数据
    def update_version(data):
        data["version"] = "1.1.0"
        data["updated_at"] = datetime.now().isoformat()
        return data
    
    store.update(update_version)
    print("✓ 数据已更新")
    
    # 检查文件信息
    print(f"✓ 文件大小: {store.get_size()} 字节")
    print(f"✓ 文件存在: {store.exists()}")


def dict_store_example():
    """字典存储示例"""
    print("\n=== 字典存储示例 ===")
    
    # 创建字典存储器
    settings = DictJSONStore("data/settings.json")
    
    # 设置键值对
    settings.set("theme", "dark")
    settings.set("font_size", 14)
    settings.set("auto_save", True)
    print("✓ 设置已保存")
    
    # 获取值
    theme = settings.get("theme")
    font_size = settings.get("font_size")
    print(f"✓ 主题: {theme}, 字体大小: {font_size}")
    
    # 检查键是否存在
    if settings.has_key("theme"):
        print("✓ 主题设置存在")
    
    # 获取所有键
    all_keys = settings.keys()
    print(f"✓ 所有设置项: {all_keys}")
    
    # 合并数据
    new_settings = {
        "show_line_numbers": True,
        "word_wrap": False
    }
    settings.merge(new_settings)
    print("✓ 设置已合并")
    
    # 删除键
    settings.delete_key("font_size")
    print("✓ 已删除 font_size 设置")


def list_store_example():
    """列表存储示例"""
    print("\n=== 列表存储示例 ===")
    
    # 创建列表存储器
    tasks = ListJSONStore("data/tasks.json")
    
    # 清空列表（如果存在）
    tasks.clear()
    
    # 添加项目
    tasks.append({"id": 1, "title": "完成文档", "done": False})
    tasks.append({"id": 2, "title": "修复bug", "done": False})
    tasks.append({"id": 3, "title": "代码审查", "done": True})
    print("✓ 任务已添加")
    
    # 批量添加
    more_tasks = [
        {"id": 4, "title": "单元测试", "done": False},
        {"id": 5, "title": "性能优化", "done": False}
    ]
    tasks.extend(more_tasks)
    print("✓ 批量任务已添加")
    
    # 获取列表长度
    count = tasks.length()
    print(f"✓ 任务总数: {count}")
    
    # 获取指定项
    first_task = tasks.get_at(0)
    print(f"✓ 第一个任务: {first_task}")
    
    # 过滤已完成的任务
    tasks.filter(lambda task: not task.get("done", False))
    print("✓ 已过滤完成的任务")
    
    # 移除指定索引
    removed = tasks.remove_at(0)
    print(f"✓ 已移除任务: {removed}")


def log_store_example():
    """日志存储示例"""
    print("\n=== 日志存储示例 ===")
    
    # 创建日志存储器
    log_store = LogStore(
        directory="data/logs",
        prefix="app",
        max_entries_per_file=100
    )
    
    # 添加日志记录
    log_store.add_log({
        "level": "INFO",
        "message": "应用启动",
        "module": "main"
    })
    
    log_store.add_log({
        "level": "DEBUG",
        "message": "初始化配置",
        "module": "config"
    })
    
    log_store.add_log({
        "level": "WARNING",
        "message": "内存使用率较高",
        "module": "monitor",
        "memory_percent": 85
    })
    
    log_store.add_log({
        "level": "ERROR",
        "message": "数据库连接失败",
        "module": "database",
        "error": "Connection timeout"
    })
    
    print("✓ 日志记录已添加")
    
    # 获取所有日志
    all_logs = log_store.get_logs()
    print(f"✓ 日志总数: {len(all_logs)}")
    
    # 过滤特定级别的日志
    error_logs = log_store.get_logs(
        filter_func=lambda log: log.get("level") == "ERROR"
    )
    print(f"✓ 错误日志数: {len(error_logs)}")


def backup_and_compress_example():
    """备份和压缩示例"""
    print("\n=== 备份和压缩示例 ===")
    
    # 创建存储器（启用自动备份）
    store = JSONStore(
        "data/important.json",
        auto_backup=True,
        max_backups=3
    )
    
    # 写入数据（会自动创建备份）
    for i in range(5):
        store.write({"version": i, "data": f"update_{i}"})
        print(f"✓ 第 {i+1} 次更新完成")
    
    # 压缩文件
    compressed_path = store.compress()
    print(f"✓ 文件已压缩到: {compressed_path}")


def error_handling_example():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")
    
    try:
        # 尝试读取不存在的文件
        store = JSONStore("data/nonexistent.json", auto_create=False)
        data = store.read()
    except JSONStoreError as e:
        print(f"✓ 捕获到错误: {e}")
    
    # 使用默认值避免错误
    store = JSONStore("data/optional.json", auto_create=False)
    data = store.read(default={"status": "not_found"})
    print(f"✓ 使用默认值: {data}")


def data_validation_example():
    """数据验证示例"""
    print("\n=== 数据验证示例 ===")
    
    # 定义验证函数
    def validate_user(data):
        """验证用户数据"""
        if not isinstance(data, dict):
            return False
        required_fields = ["username", "email"]
        return all(field in data for field in required_fields)
    
    # 创建带验证的存储器
    store = JSONStore(
        "data/user.json",
        validate_func=validate_user
    )
    
    # 有效数据
    valid_user = {
        "username": "mofox",
        "email": "mofox@example.com",
        "age": 25
    }
    store.write(valid_user, validate=True)
    print("✓ 有效数据已写入")
    
    # 无效数据
    try:
        invalid_user = {"username": "test"}  # 缺少email
        store.write(invalid_user, validate=True)
    except JSONStoreError as e:
        print(f"✓ 验证失败（预期行为）: {e}")


def atomic_write_example():
    """原子写入示例"""
    print("\n=== 原子写入示例 ===")
    
    store = JSONStore("data/atomic.json")
    
    # 模拟并发更新
    import threading
    
    def update_counter():
        for _ in range(10):
            def increment(data):
                count = data.get("counter", 0)
                data["counter"] = count + 1
                return data
            store.update(increment)
    
    # 启动多个线程
    threads = [threading.Thread(target=update_counter) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    
    # 检查结果
    result = store.read()
    print(f"✓ 最终计数: {result.get('counter')} (应该是 30)")


def complex_data_example():
    """复杂数据结构示例"""
    print("\n=== 复杂数据结构示例 ===")
    
    store = JSONStore("data/complex.json")
    
    # 复杂的嵌套数据
    complex_data = {
        "users": [
            {
                "id": 1,
                "name": "Alice",
                "roles": ["admin", "user"],
                "metadata": {
                    "last_login": datetime.now().isoformat(),
                    "preferences": {
                        "theme": "dark",
                        "notifications": True
                    }
                }
            },
            {
                "id": 2,
                "name": "Bob",
                "roles": ["user"],
                "metadata": {
                    "last_login": datetime.now().isoformat(),
                    "preferences": {
                        "theme": "light",
                        "notifications": False
                    }
                }
            }
        ],
        "settings": {
            "max_users": 100,
            "features": ["auth", "logging", "api"],
            "versions": {
                "current": "1.0.0",
                "supported": ["1.0.0", "0.9.0"]
            }
        }
    }
    
    store.write(complex_data)
    print("✓ 复杂数据已保存")
    
    # 读取并操作
    data = store.read()
    user_count = len(data["users"])
    admin_count = sum(1 for u in data["users"] if "admin" in u["roles"])
    
    print(f"✓ 用户总数: {user_count}")
    print(f"✓ 管理员数: {admin_count}")


if __name__ == "__main__":
    # 确保数据目录存在
    import os
    os.makedirs("data/logs", exist_ok=True)
    
    print("MoFox Storage 使用示例")
    print("=" * 50)
    
    basic_json_store_example()
    dict_store_example()
    list_store_example()
    log_store_example()
    backup_and_compress_example()
    error_handling_example()
    data_validation_example()
    atomic_write_example()
    complex_data_example()
    
    print("\n" + "=" * 50)
    print("示例运行完成！")
    print("生成的文件位于 data/ 目录")
