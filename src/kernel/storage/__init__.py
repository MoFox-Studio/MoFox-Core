"""
MoFox Storage - 本地持久化存储模块

提供统一的JSON本地持久化操作，支持字典、列表、日志等多种存储方式

基本使用：
    from kernel.storage import JSONStore, DictJSONStore, ListJSONStore
    
    # 通用JSON存储
    store = JSONStore("data/config.json")
    data = store.read()
    store.write({"key": "value"})
    
    # 字典存储
    dict_store = DictJSONStore("data/settings.json")
    dict_store.set("theme", "dark")
    theme = dict_store.get("theme")
    
    # 列表存储
    list_store = ListJSONStore("data/items.json")
    list_store.append({"id": 1, "name": "Item 1"})
    
    # 日志存储
    log_store = LogStore("logs/app_logs")
    log_store.add_log({"level": "INFO", "message": "Application started"})
"""

from .json_store import (
    # 核心类
    JSONStore,
    DictJSONStore,
    ListJSONStore,
    LogStore,
    
    # 异常类
    JSONStoreError,
    FileNotFoundError,
    ValidationError,
)


__all__ = [
    # 存储类
    'JSONStore',
    'DictJSONStore',
    'ListJSONStore',
    'LogStore',
    
    # 异常
    'JSONStoreError',
    'FileNotFoundError',
    'ValidationError',
]


__version__ = '1.0.0'
__author__ = 'MoFox Team'
