"""
JSON 存储模块

提供统一的JSON本地持久化操作，支持CRUD、原子写入、备份、压缩等功能
"""
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime
from threading import Lock
import gzip


class JSONStoreError(Exception):
    """JSON存储异常基类"""
    pass


class FileNotFoundError(JSONStoreError):
    """文件不存在异常"""
    pass


class ValidationError(JSONStoreError):
    """数据验证异常"""
    pass


class JSONStore:
    """JSON存储器 - 提供安全的JSON文件读写操作"""
    
    def __init__(
        self,
        file_path: Union[str, Path],
        auto_create: bool = True,
        auto_backup: bool = True,
        max_backups: int = 5,
        indent: Optional[int] = 2,
        encoding: str = 'utf-8',
        validate_func: Optional[Callable[[Any], bool]] = None
    ):
        """
        初始化JSON存储器
        
        Args:
            file_path: JSON文件路径
            auto_create: 文件不存在时是否自动创建
            auto_backup: 写入前是否自动备份
            max_backups: 最大备份数量
            indent: JSON缩进级别
            encoding: 文件编码
            validate_func: 数据验证函数
        """
        self.file_path = Path(file_path)
        self.auto_create = auto_create
        self.auto_backup = auto_backup
        self.max_backups = max_backups
        self.indent = indent
        self.encoding = encoding
        self.validate_func = validate_func
        self._lock = Lock()
        
        # 确保目录存在
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果文件不存在且允许自动创建，创建空文件
        if not self.file_path.exists() and auto_create:
            self._write_data({})
    
    def read(self, default: Any = None) -> Any:
        """
        读取JSON数据
        
        Args:
            default: 文件不存在时返回的默认值
            
        Returns:
            解析后的JSON数据
            
        Raises:
            JSONStoreError: 读取或解析失败
        """
        with self._lock:
            try:
                if not self.file_path.exists():
                    if default is not None:
                        return default
                    raise FileNotFoundError(f"文件不存在: {self.file_path}")
                
                with open(self.file_path, 'r', encoding=self.encoding) as f:
                    data = json.load(f)
                
                return data
            
            except json.JSONDecodeError as e:
                raise JSONStoreError(f"JSON解析失败: {e}")
            except Exception as e:
                raise JSONStoreError(f"读取文件失败: {e}")
    
    def write(self, data: Any, validate: bool = True) -> None:
        """
        写入JSON数据（原子写入）
        
        Args:
            data: 要写入的数据
            validate: 是否验证数据
            
        Raises:
            ValidationError: 数据验证失败
            JSONStoreError: 写入失败
        """
        with self._lock:
            # 验证数据
            if validate and self.validate_func:
                if not self.validate_func(data):
                    raise ValidationError("数据验证失败")
            
            # 备份旧文件
            if self.auto_backup and self.file_path.exists():
                self._create_backup()
            
            # 原子写入
            self._write_data(data)
    
    def _write_data(self, data: Any) -> None:
        """
        原子写入数据（先写临时文件再重命名）
        
        Args:
            data: 要写入的数据
        """
        try:
            # 写入临时文件
            temp_file = self.file_path.with_suffix('.tmp')
            with open(temp_file, 'w', encoding=self.encoding) as f:
                json.dump(data, f, indent=self.indent, ensure_ascii=False)
            
            # 原子重命名
            temp_file.replace(self.file_path)
        
        except Exception as e:
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
            raise JSONStoreError(f"写入文件失败: {e}")
    
    def update(self, update_func: Callable[[Any], Any]) -> Any:
        """
        更新数据（读取-修改-写入）
        
        Args:
            update_func: 更新函数，接收当前数据并返回新数据
            
        Returns:
            更新后的数据
        """
        with self._lock:
            # 读取当前数据
            data = self.read(default={})
            
            # 应用更新
            new_data = update_func(data)
            
            # 写入新数据
            self.write(new_data, validate=True)
            
            return new_data
    
    def delete(self, create_backup: bool = True) -> bool:
        """
        删除JSON文件
        
        Args:
            create_backup: 删除前是否备份
            
        Returns:
            是否成功删除
        """
        with self._lock:
            try:
                if not self.file_path.exists():
                    return False
                
                if create_backup:
                    self._create_backup()
                
                self.file_path.unlink()
                return True
            
            except Exception as e:
                raise JSONStoreError(f"删除文件失败: {e}")
    
    def exists(self) -> bool:
        """检查文件是否存在"""
        return self.file_path.exists()
    
    def get_size(self) -> int:
        """
        获取文件大小
        
        Returns:
            文件大小（字节）
        """
        if not self.file_path.exists():
            return 0
        return self.file_path.stat().st_size
    
    def _create_backup(self) -> Path:
        """
        创建备份文件
        
        Returns:
            备份文件路径
        """
        if not self.file_path.exists():
            return None
        
        # 生成备份文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{self.file_path.stem}_backup_{timestamp}{self.file_path.suffix}"
        backup_path = self.file_path.parent / backup_name
        
        # 复制文件
        shutil.copy2(self.file_path, backup_path)
        
        # 清理旧备份
        self._cleanup_old_backups()
        
        return backup_path
    
    def _cleanup_old_backups(self) -> None:
        """清理旧备份文件"""
        pattern = f"{self.file_path.stem}_backup_*{self.file_path.suffix}"
        backups = sorted(
            self.file_path.parent.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # 删除超过最大数量的备份
        for backup in backups[self.max_backups:]:
            try:
                backup.unlink()
            except Exception:
                pass
    
    def compress(self, output_path: Optional[Union[str, Path]] = None) -> Path:
        """
        压缩JSON文件
        
        Args:
            output_path: 输出路径，默认为原文件名+.gz
            
        Returns:
            压缩文件路径
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")
        
        if output_path is None:
            output_path = self.file_path.with_suffix(self.file_path.suffix + '.gz')
        else:
            output_path = Path(output_path)
        
        with open(self.file_path, 'rb') as f_in:
            with gzip.open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return output_path
    
    def decompress(self, compressed_path: Union[str, Path]) -> None:
        """
        解压缩到当前文件
        
        Args:
            compressed_path: 压缩文件路径
        """
        compressed_path = Path(compressed_path)
        
        if not compressed_path.exists():
            raise FileNotFoundError(f"压缩文件不存在: {compressed_path}")
        
        with gzip.open(compressed_path, 'rb') as f_in:
            with open(self.file_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)


class DictJSONStore(JSONStore):
    """字典型JSON存储器 - 专门处理字典数据"""
    
    def __init__(self, file_path: Union[str, Path], **kwargs):
        """初始化字典存储器"""
        super().__init__(file_path, **kwargs)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取指定键的值
        
        Args:
            key: 键名
            default: 默认值
            
        Returns:
            键对应的值
        """
        data = self.read(default={})
        return data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        设置键值对
        
        Args:
            key: 键名
            value: 值
        """
        def update(data):
            if not isinstance(data, dict):
                data = {}
            data[key] = value
            return data
        
        self.update(update)
    
    def delete_key(self, key: str) -> bool:
        """
        删除指定键
        
        Args:
            key: 键名
            
        Returns:
            是否成功删除
        """
        def update(data):
            if isinstance(data, dict) and key in data:
                del data[key]
            return data
        
        self.update(update)
        return True
    
    def has_key(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 键名
            
        Returns:
            键是否存在
        """
        data = self.read(default={})
        return isinstance(data, dict) and key in data
    
    def keys(self) -> List[str]:
        """
        获取所有键
        
        Returns:
            键列表
        """
        data = self.read(default={})
        if isinstance(data, dict):
            return list(data.keys())
        return []
    
    def values(self) -> List[Any]:
        """
        获取所有值
        
        Returns:
            值列表
        """
        data = self.read(default={})
        if isinstance(data, dict):
            return list(data.values())
        return []
    
    def items(self) -> List[tuple]:
        """
        获取所有键值对
        
        Returns:
            键值对列表
        """
        data = self.read(default={})
        if isinstance(data, dict):
            return list(data.items())
        return []
    
    def clear(self) -> None:
        """清空所有数据"""
        self.write({})
    
    def merge(self, other: Dict[str, Any], overwrite: bool = True) -> None:
        """
        合并字典数据
        
        Args:
            other: 要合并的字典
            overwrite: 是否覆盖已存在的键
        """
        def update(data):
            if not isinstance(data, dict):
                data = {}
            
            if overwrite:
                data.update(other)
            else:
                for key, value in other.items():
                    if key not in data:
                        data[key] = value
            
            return data
        
        self.update(update)


class ListJSONStore(JSONStore):
    """列表型JSON存储器 - 专门处理列表数据"""
    
    def __init__(self, file_path: Union[str, Path], **kwargs):
        """初始化列表存储器"""
        super().__init__(file_path, **kwargs)
    
    def append(self, item: Any) -> None:
        """
        追加项目
        
        Args:
            item: 要追加的项目
        """
        def update(data):
            if not isinstance(data, list):
                data = []
            data.append(item)
            return data
        
        self.update(update)
    
    def extend(self, items: List[Any]) -> None:
        """
        扩展列表
        
        Args:
            items: 要添加的项目列表
        """
        def update(data):
            if not isinstance(data, list):
                data = []
            data.extend(items)
            return data
        
        self.update(update)
    
    def remove(self, item: Any) -> bool:
        """
        移除项目
        
        Args:
            item: 要移除的项目
            
        Returns:
            是否成功移除
        """
        def update(data):
            if isinstance(data, list) and item in data:
                data.remove(item)
            return data
        
        self.update(update)
        return True
    
    def remove_at(self, index: int) -> Any:
        """
        移除指定索引的项目
        
        Args:
            index: 索引
            
        Returns:
            被移除的项目
        """
        removed_item = None
        
        def update(data):
            nonlocal removed_item
            if isinstance(data, list) and 0 <= index < len(data):
                removed_item = data.pop(index)
            return data
        
        self.update(update)
        return removed_item
    
    def get_at(self, index: int, default: Any = None) -> Any:
        """
        获取指定索引的项目
        
        Args:
            index: 索引
            default: 默认值
            
        Returns:
            项目
        """
        data = self.read(default=[])
        if isinstance(data, list) and 0 <= index < len(data):
            return data[index]
        return default
    
    def length(self) -> int:
        """
        获取列表长度
        
        Returns:
            列表长度
        """
        data = self.read(default=[])
        if isinstance(data, list):
            return len(data)
        return 0
    
    def clear(self) -> None:
        """清空列表"""
        self.write([])
    
    def filter(self, filter_func: Callable[[Any], bool]) -> None:
        """
        过滤列表项
        
        Args:
            filter_func: 过滤函数
        """
        def update(data):
            if isinstance(data, list):
                return [item for item in data if filter_func(item)]
            return data
        
        self.update(update)


class LogStore:
    """日志存储器 - 专门用于存储日志记录"""
    
    def __init__(
        self,
        directory: Union[str, Path],
        prefix: str = "log",
        max_entries_per_file: int = 1000,
        auto_rotate: bool = True
    ):
        """
        初始化日志存储器
        
        Args:
            directory: 日志存储目录
            prefix: 文件名前缀
            max_entries_per_file: 每个文件最大日志条目数
            auto_rotate: 是否自动轮转
        """
        self.directory = Path(directory)
        self.prefix = prefix
        self.max_entries_per_file = max_entries_per_file
        self.auto_rotate = auto_rotate
        self.directory.mkdir(parents=True, exist_ok=True)
        
        self._current_store: Optional[ListJSONStore] = None
    
    def _get_current_file_path(self) -> Path:
        """获取当前日志文件路径"""
        timestamp = datetime.now().strftime('%Y%m%d')
        return self.directory / f"{self.prefix}_{timestamp}.json"
    
    def _get_current_store(self) -> ListJSONStore:
        """获取当前存储器"""
        file_path = self._get_current_file_path()
        
        if self._current_store is None or self._current_store.file_path != file_path:
            self._current_store = ListJSONStore(file_path)
        
        # 检查是否需要轮转
        if self.auto_rotate:
            length = self._current_store.length()
            if length >= self.max_entries_per_file:
                self._rotate()
        
        return self._current_store
    
    def _rotate(self) -> None:
        """轮转日志文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_path = self.directory / f"{self.prefix}_{timestamp}.json"
        self._current_store = ListJSONStore(new_path)
    
    def add_log(self, log_entry: Dict[str, Any]) -> None:
        """
        添加日志条目
        
        Args:
            log_entry: 日志条目（字典格式）
        """
        # 自动添加时间戳
        if 'timestamp' not in log_entry:
            log_entry['timestamp'] = datetime.now().isoformat()
        
        store = self._get_current_store()
        store.append(log_entry)
    
    def get_logs(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        filter_func: Optional[Callable[[Dict], bool]] = None
    ) -> List[Dict[str, Any]]:
        """
        获取日志记录
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            filter_func: 过滤函数
            
        Returns:
            日志记录列表
        """
        logs = []
        
        # 获取所有日志文件
        pattern = f"{self.prefix}_*.json"
        for file_path in sorted(self.directory.glob(pattern)):
            store = ListJSONStore(file_path)
            file_logs = store.read(default=[])
            
            if isinstance(file_logs, list):
                logs.extend(file_logs)
        
        # 按时间过滤
        if start_date or end_date:
            filtered_logs = []
            for log in logs:
                if 'timestamp' in log:
                    log_time = datetime.fromisoformat(log['timestamp'])
                    if start_date and log_time < start_date:
                        continue
                    if end_date and log_time > end_date:
                        continue
                filtered_logs.append(log)
            logs = filtered_logs
        
        # 自定义过滤
        if filter_func:
            logs = [log for log in logs if filter_func(log)]
        
        return logs
    
    def clear_old_logs(self, days: int = 30) -> int:
        """
        清理旧日志
        
        Args:
            days: 保留天数
            
        Returns:
            删除的文件数量
        """
        cutoff_date = datetime.now().timestamp() - (days * 24 * 3600)
        deleted_count = 0
        
        pattern = f"{self.prefix}_*.json"
        for file_path in self.directory.glob(pattern):
            if file_path.stat().st_mtime < cutoff_date:
                try:
                    file_path.unlink()
                    deleted_count += 1
                except Exception:
                    pass
        
        return deleted_count


__all__ = [
    'JSONStore',
    'DictJSONStore',
    'ListJSONStore',
    'LogStore',
    'JSONStoreError',
    'FileNotFoundError',
    'ValidationError',
]
