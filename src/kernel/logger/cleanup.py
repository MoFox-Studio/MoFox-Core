"""
日志清理和维护模块

提供日志文件的清理、压缩和归档功能
"""
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
import logging


logger = logging.getLogger(__name__)


class LogCleaner:
    """日志清理器"""
    
    def __init__(self, log_directory: str = "logs"):
        """
        初始化日志清理器
        
        Args:
            log_directory: 日志目录路径
        """
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)
    
    def get_log_files(self, pattern: str = "*.log*") -> List[Path]:
        """
        获取所有日志文件
        
        Args:
            pattern: 文件匹配模式
            
        Returns:
            日志文件路径列表
        """
        return sorted(self.log_directory.glob(pattern))
    
    def get_file_age(self, file_path: Path) -> timedelta:
        """
        获取文件年龄
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件年龄（时间差）
        """
        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
        return datetime.now() - file_time
    
    def delete_old_logs(self, max_age_days: int = 30, pattern: str = "*.log*") -> int:
        """
        删除过期的日志文件
        
        Args:
            max_age_days: 最大保留天数
            pattern: 文件匹配模式
            
        Returns:
            删除的文件数量
        """
        deleted_count = 0
        max_age = timedelta(days=max_age_days)
        
        for log_file in self.get_log_files(pattern):
            try:
                if self.get_file_age(log_file) > max_age:
                    log_file.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old log file: {log_file}")
            except Exception as e:
                logger.error(f"Failed to delete log file {log_file}: {e}")
        
        return deleted_count
    
    def compress_logs(
        self,
        pattern: str = "*.log.[0-9]*",
        keep_original: bool = False
    ) -> int:
        """
        压缩日志文件
        
        Args:
            pattern: 文件匹配模式
            keep_original: 是否保留原始文件
            
        Returns:
            压缩的文件数量
        """
        compressed_count = 0
        
        for log_file in self.get_log_files(pattern):
            # 跳过已压缩的文件
            if log_file.suffix == '.gz':
                continue
            
            try:
                compressed_path = log_file.with_suffix(log_file.suffix + '.gz')
                
                # 压缩文件
                with open(log_file, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                compressed_count += 1
                logger.info(f"Compressed log file: {log_file} -> {compressed_path}")
                
                # 删除原始文件
                if not keep_original:
                    log_file.unlink()
            
            except Exception as e:
                logger.error(f"Failed to compress log file {log_file}: {e}")
        
        return compressed_count
    
    def get_directory_size(self) -> int:
        """
        获取日志目录总大小
        
        Returns:
            目录大小（字节）
        """
        total_size = 0
        for file_path in self.log_directory.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size
    
    def cleanup_by_size(self, max_size_mb: int = 100) -> int:
        """
        按大小清理日志（删除最旧的文件直到满足大小限制）
        
        Args:
            max_size_mb: 最大目录大小（MB）
            
        Returns:
            删除的文件数量
        """
        max_size_bytes = max_size_mb * 1024 * 1024
        current_size = self.get_directory_size()
        
        if current_size <= max_size_bytes:
            return 0
        
        deleted_count = 0
        
        # 按修改时间排序（最旧的在前）
        log_files = sorted(
            self.get_log_files(),
            key=lambda p: p.stat().st_mtime
        )
        
        for log_file in log_files:
            # 不删除当前正在使用的日志文件
            if log_file.suffix == '.log' and not any(
                c in log_file.name for c in ['.', '-', '_']
            ):
                continue
            
            try:
                file_size = log_file.stat().st_size
                log_file.unlink()
                current_size -= file_size
                deleted_count += 1
                logger.info(f"Deleted log file to free space: {log_file}")
                
                if current_size <= max_size_bytes:
                    break
            
            except Exception as e:
                logger.error(f"Failed to delete log file {log_file}: {e}")
        
        return deleted_count
    
    def archive_logs(
        self,
        archive_path: Optional[str] = None,
        max_age_days: int = 7
    ) -> Optional[Path]:
        """
        归档日志文件
        
        Args:
            archive_path: 归档文件路径，默认为logs/archive_<timestamp>.tar.gz
            max_age_days: 归档多少天前的日志
            
        Returns:
            归档文件路径，失败返回None
        """
        import tarfile
        
        if archive_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_path = str(self.log_directory / f"archive_{timestamp}.tar.gz")
        
        archive_path = Path(archive_path)
        max_age = timedelta(days=max_age_days)
        
        try:
            with tarfile.open(archive_path, 'w:gz') as tar:
                for log_file in self.get_log_files():
                    if self.get_file_age(log_file) > max_age:
                        tar.add(log_file, arcname=log_file.name)
                        log_file.unlink()
            
            logger.info(f"Archived old logs to: {archive_path}")
            return archive_path
        
        except Exception as e:
            logger.error(f"Failed to archive logs: {e}")
            return None
    
    def get_statistics(self) -> dict:
        """
        获取日志统计信息
        
        Returns:
            统计信息字典
        """
        log_files = self.get_log_files()
        
        stats = {
            'total_files': len(log_files),
            'total_size_mb': self.get_directory_size() / (1024 * 1024),
            'oldest_file': None,
            'newest_file': None,
            'compressed_files': 0,
        }
        
        if log_files:
            # 按修改时间排序
            sorted_files = sorted(log_files, key=lambda p: p.stat().st_mtime)
            stats['oldest_file'] = str(sorted_files[0])
            stats['newest_file'] = str(sorted_files[-1])
            
            # 统计压缩文件
            stats['compressed_files'] = sum(
                1 for f in log_files if f.suffix == '.gz'
            )
        
        return stats


class AutoCleaner:
    """自动日志清理器"""
    
    def __init__(
        self,
        log_directory: str = "logs",
        max_age_days: int = 30,
        max_size_mb: int = 100,
        compress_after_days: int = 7
    ):
        """
        初始化自动清理器
        
        Args:
            log_directory: 日志目录
            max_age_days: 最大保留天数
            max_size_mb: 最大目录大小（MB）
            compress_after_days: 多少天后压缩日志
        """
        self.cleaner = LogCleaner(log_directory)
        self.max_age_days = max_age_days
        self.max_size_mb = max_size_mb
        self.compress_after_days = compress_after_days
    
    def run(self) -> dict:
        """
        执行自动清理
        
        Returns:
            清理结果统计
        """
        results = {
            'deleted_old': 0,
            'compressed': 0,
            'deleted_by_size': 0,
        }
        
        try:
            # 1. 压缩旧日志
            results['compressed'] = self.cleaner.compress_logs()
            
            # 2. 删除过期日志
            results['deleted_old'] = self.cleaner.delete_old_logs(self.max_age_days)
            
            # 3. 按大小清理
            results['deleted_by_size'] = self.cleaner.cleanup_by_size(self.max_size_mb)
            
            logger.info(f"Auto cleanup completed: {results}")
        
        except Exception as e:
            logger.error(f"Auto cleanup failed: {e}")
        
        return results
