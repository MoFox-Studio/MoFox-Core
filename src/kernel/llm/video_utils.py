"""
视频处理工具

使用 inkfox 提供视频关键帧提取和处理功能
"""

import os
from typing import Dict, Optional, Any
from kernel.logger import get_logger

logger = get_logger(__name__)

# 尝试导入 inkfox
try:
    from kernel.llm.inkfox import video  # type: ignore
    INKFOX_AVAILABLE = True
    logger.info("inkfox 视频处理模块已加载")
except ImportError as e:
    INKFOX_AVAILABLE = False
    logger.warning("inkfox 视频处理模块不可用: %s", e)
    video = None  # type: ignore


class VideoKeyframeExtractor:
    """视频关键帧提取器（inkfox 封装）"""
    
    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        threads: int = 0,
        verbose: bool = False
    ):
        """初始化视频关键帧提取器
        
        Args:
            ffmpeg_path: FFmpeg 可执行文件路径（None 则自动查找）
            threads: 线程数（0=自动）
            verbose: 是否输出详细日志
            
        Raises:
            RuntimeError: inkfox 不可用时抛出
        """
        if not INKFOX_AVAILABLE:
            raise RuntimeError(
                "inkfox 视频处理模块不可用，请安装 inkfox: "
                "pip install inkfox"
            )
        
        self._extractor = video.VideoKeyframeExtractor(  # type: ignore
            ffmpeg_path=ffmpeg_path or "",
            threads=threads,
            verbose=verbose
        )
        
        logger.info(
            "视频关键帧提取器初始化完成 (线程数=%d)",
            self._extractor.get_configured_threads()
        )
    
    def extract_keyframes(
        self,
        video_path: str,
        output_dir: str,
        max_keyframes: int = 10,
        max_save: Optional[int] = None,
        use_simd: Optional[bool] = None,
        block_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """提取视频关键帧
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            max_keyframes: 最大关键帧数量
            max_save: 最大保存数量（None=全部保存）
            use_simd: 是否使用 SIMD 加速（None=自动）
            block_size: SIMD 块大小（None=自动）
            
        Returns:
            dict: 包含提取结果和性能信息
            
        Raises:
            FileNotFoundError: 视频文件不存在
            RuntimeError: 提取失败
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            logger.info("开始提取视频关键帧: %s", video_path)
            logger.debug(
                "参数: max_keyframes=%d, max_save=%s, use_simd=%s",
                max_keyframes, max_save, use_simd
            )
            
            # 调用 inkfox 提取关键帧
            result = self._extractor.process_video(
                video_path=video_path,
                output_dir=output_dir,
                max_keyframes=max_keyframes,
                max_save=max_save,
                use_simd=use_simd,
                block_size=block_size
            )
            
            # 转换结果为字典
            result_dict = result.to_dict()
            
            logger.info(
                "关键帧提取完成: 总帧数=%d, 关键帧数=%d, 处理速度=%.2f FPS",
                result_dict['total_frames'],
                result_dict['keyframes_extracted'],
                result_dict['processing_fps']
            )
            
            return result_dict
            
        except Exception as e:
            logger.error("关键帧提取失败: %s", e)
            raise RuntimeError(f"Failed to extract keyframes: {e}") from e
    
    def benchmark(
        self,
        video_path: str,
        max_keyframes: int = 10,
        test_name: str = "default",
        use_simd: Optional[bool] = None,
        block_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """性能基准测试
        
        Args:
            video_path: 视频文件路径
            max_keyframes: 最大关键帧数量
            test_name: 测试名称
            use_simd: 是否使用 SIMD
            block_size: SIMD 块大小
            
        Returns:
            dict: 性能测试结果
        """
        try:
            logger.info("开始性能测试: %s", test_name)
            
            result = self._extractor.benchmark(
                video_path=video_path,
                max_keyframes=max_keyframes,
                test_name=test_name,
                use_simd=use_simd,
                block_size=block_size
            )
            
            result_dict = result.to_dict()
            
            logger.info(
                "性能测试完成: %s, 总耗时=%.2fms, FPS=%.2f",
                test_name,
                result_dict['total_time_ms'],
                result_dict['processing_fps']
            )
            
            return result_dict
            
        except Exception as e:
            logger.error("性能测试失败: %s", e)
            raise RuntimeError(f"Benchmark failed: {e}") from e
    
    def get_cpu_features(self) -> Dict[str, bool]:
        """获取 CPU 特性支持情况
        
        Returns:
            dict: CPU 特性字典（如 {'avx2': True, 'sse4.1': True}）
        """
        return self._extractor.get_cpu_features()
    
    def get_thread_count(self) -> int:
        """获取实际使用的线程数
        
        Returns:
            int: 线程数
        """
        return self._extractor.get_actual_thread_count()


def extract_keyframes_from_video(
    video_path: str,
    output_dir: str,
    max_keyframes: int = 10,
    max_save: Optional[int] = None,
    ffmpeg_path: Optional[str] = None,
    use_simd: Optional[bool] = None,
    threads: Optional[int] = None,
    verbose: bool = False,
    block_size: Optional[int] = None
) -> Dict[str, Any]:
    """快捷函数：从视频中提取关键帧
    
    这是一个便捷的封装函数，用于快速提取视频关键帧。
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        max_keyframes: 最大关键帧数量（默认 10）
        max_save: 最大保存数量（None=全部保存）
        ffmpeg_path: FFmpeg 路径（None=自动查找）
        use_simd: 是否使用 SIMD 加速（None=自动检测）
        threads: 线程数（None=自动）
        verbose: 是否输出详细日志
        block_size: SIMD 块大小（None=自动）
        
    Returns:
        dict: 提取结果，包含：
            - test_name: 测试名称
            - video_file: 视频文件路径
            - total_time_ms: 总耗时（毫秒）
            - frame_extraction_time_ms: 帧提取耗时
            - keyframe_analysis_time_ms: 关键帧分析耗时
            - total_frames: 总帧数
            - keyframes_extracted: 提取的关键帧数
            - keyframe_ratio: 关键帧比例
            - processing_fps: 处理速度（FPS）
            - optimization_type: 优化类型
            - simd_enabled: 是否启用 SIMD
            - threads_used: 使用的线程数
            - timestamp: 时间戳
            
    Example:
        >>> result = extract_keyframes_from_video(
        ...     video_path="video.mp4",
        ...     output_dir="./keyframes",
        ...     max_keyframes=15
        ... )
        >>> print(f"提取了 {result['keyframes_extracted']} 个关键帧")
        
    Raises:
        RuntimeError: inkfox 不可用或提取失败
        FileNotFoundError: 视频文件不存在
    """
    if not INKFOX_AVAILABLE:
        raise RuntimeError(
            "inkfox 视频处理模块不可用，请安装 inkfox: "
            "pip install inkfox"
        )
    
    try:
        result = video.extract_keyframes_from_video(  # type: ignore
            video_path=video_path,
            output_dir=output_dir,
            max_keyframes=max_keyframes,
            max_save=max_save,
            ffmpeg_path=ffmpeg_path,
            use_simd=use_simd,
            threads=threads,
            verbose=verbose,
            block_size=block_size
        )
        
        return result.to_dict()
        
    except Exception as e:
        logger.error("快捷提取关键帧失败: %s", e)
        raise


def get_system_info() -> Dict[str, Any]:
    """获取系统信息
    
    Returns:
        dict: 系统信息，包括 CPU 特性等
        
    Raises:
        RuntimeError: inkfox 不可用
    """
    if not INKFOX_AVAILABLE:
        raise RuntimeError("inkfox 视频处理模块不可用")
    
    return video.get_system_info()  # type: ignore


def check_inkfox_available() -> bool:
    """检查 inkfox 是否可用
    
    Returns:
        bool: True 表示可用，False 表示不可用
    """
    return INKFOX_AVAILABLE


__all__ = [
    'VideoKeyframeExtractor',
    'extract_keyframes_from_video',
    'get_system_info',
    'check_inkfox_available',
    'INKFOX_AVAILABLE',
]
