"""inkfox.video submodule type stubs"""
from __future__ import annotations
from typing import Any, Dict, List, Sequence, Tuple

class PyVideoFrame:
    frame_number: int
    width: int
    height: int
    def __init__(self, frame_number: int, width: int, height: int, data: bytes | bytearray | memoryview | list[int]): ...
    def get_data(self) -> bytes: ...
    def calculate_difference(self, other: "PyVideoFrame") -> float: ...
    def calculate_difference_simd(self, other: "PyVideoFrame", block_size: int | None = None) -> float: ...

class PyPerformanceResult:
    test_name: str
    video_file: str
    total_time_ms: float
    frame_extraction_time_ms: float
    keyframe_analysis_time_ms: float
    total_frames: int
    keyframes_extracted: int
    keyframe_ratio: float
    processing_fps: float
    max_keyframes_requested: int
    optimization_type: str
    simd_enabled: bool
    threads_used: int
    timestamp: str
    def to_dict(self) -> dict[str, Any]: ...

class VideoKeyframeExtractor:
    def __init__(self, ffmpeg_path: str = ..., threads: int = 0, verbose: bool = False) -> None: ...
    def extract_frames(self, video_path: str, max_frames: int | None = None) -> tuple[list[PyVideoFrame], int, int]: ...
    def extract_keyframes(self, frames: Sequence[PyVideoFrame], max_keyframes: int, use_simd: bool | None = None, block_size: int | None = None) -> list[int]: ...
    def save_keyframes(self, video_path: str, keyframe_indices: Sequence[int], output_dir: str, max_save: int | None = None) -> int: ...
    def benchmark(self, video_path: str, max_keyframes: int, test_name: str, use_simd: bool | None = None, block_size: int | None = None) -> PyPerformanceResult: ...
    def process_video(self, video_path: str, output_dir: str, max_keyframes: int, max_save: int | None = None, use_simd: bool | None = None, block_size: int | None = None) -> PyPerformanceResult: ...
    def get_cpu_features(self) -> dict[str, bool]: ...
    def get_thread_count(self) -> int: ...
    def get_configured_threads(self) -> int: ...
    def get_actual_thread_count(self) -> int: ...

# Re-export convenience functions (top-level also provides these)

def extract_keyframes_from_video(
    video_path: str,
    output_dir: str,
    max_keyframes: int,
    max_save: int | None = None,
    ffmpeg_path: str | None = None,
    use_simd: bool | None = None,
    threads: int | None = None,
    verbose: bool | None = None,
    block_size: int | None = None,
): ...

def get_system_info() -> dict[str, Any]: ...

__all__ = [
    "PyVideoFrame",
    "PyPerformanceResult",
    "VideoKeyframeExtractor",
    "extract_keyframes_from_video",
    "get_system_info",
]
