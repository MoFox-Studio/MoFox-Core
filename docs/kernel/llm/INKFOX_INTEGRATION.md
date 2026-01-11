# inkfox 视频处理集成指南

## 概述

inkfox 是一个高性能的 Rust 视频处理库，提供视频关键帧提取功能。已集成到 MoFox 的 LLM 模块中。

## 功能特性

- ✅ 视频关键帧提取
- ✅ SIMD 加速（AVX2/SSE4.1）
- ✅ 多线程并行处理
- ✅ 自动 FFmpeg 集成
- ✅ 性能基准测试
- ✅ CPU 特性检测

## 安装

```bash
pip install inkfox
```

**要求:**
- Python >= 3.11
- FFmpeg（系统路径或手动指定）

## 快速开始

### 方式 1: 使用便捷函数

```python
from kernel.llm import extract_keyframes_from_video

# 提取关键帧
result = extract_keyframes_from_video(
    video_path="video.mp4",
    output_dir="./keyframes",
    max_keyframes=10,
    max_save=10
)

print(f"提取了 {result['keyframes_extracted']} 个关键帧")
print(f"处理速度: {result['processing_fps']:.2f} FPS")
```

### 方式 2: 使用类接口

```python
from kernel.llm import VideoKeyframeExtractor

# 创建提取器
extractor = VideoKeyframeExtractor(
    threads=4,
    verbose=True
)

# 获取 CPU 特性
cpu_features = extractor.get_cpu_features()
print(f"SIMD 支持: {cpu_features}")

# 提取关键帧
result = extractor.extract_keyframes(
    video_path="video.mp4",
    output_dir="./keyframes",
    max_keyframes=15,
    use_simd=True
)
```

## API 参考

### extract_keyframes_from_video()

快捷函数，用于提取视频关键帧。

**参数:**
- `video_path` (str): 视频文件路径
- `output_dir` (str): 输出目录
- `max_keyframes` (int): 最大关键帧数量，默认 10
- `max_save` (int | None): 最大保存数量，None=全部保存
- `ffmpeg_path` (str | None): FFmpeg 路径，None=自动查找
- `use_simd` (bool | None): 是否使用 SIMD，None=自动检测
- `threads` (int | None): 线程数，None=自动
- `verbose` (bool): 是否输出详细日志，默认 False
- `block_size` (int | None): SIMD 块大小，None=自动

**返回:** `Dict[str, Any]` - 包含提取结果和性能信息

**返回字段:**
```python
{
    'test_name': str,              # 测试名称
    'video_file': str,             # 视频文件路径
    'total_time_ms': float,        # 总耗时（毫秒）
    'frame_extraction_time_ms': float,   # 帧提取耗时
    'keyframe_analysis_time_ms': float,  # 关键帧分析耗时
    'total_frames': int,           # 总帧数
    'keyframes_extracted': int,    # 提取的关键帧数
    'keyframe_ratio': float,       # 关键帧比例
    'processing_fps': float,       # 处理速度（FPS）
    'optimization_type': str,      # 优化类型
    'simd_enabled': bool,          # 是否启用 SIMD
    'threads_used': int,           # 使用的线程数
    'timestamp': str               # 时间戳
}
```

### VideoKeyframeExtractor

关键帧提取器类。

**初始化参数:**
```python
VideoKeyframeExtractor(
    ffmpeg_path: Optional[str] = None,
    threads: int = 0,
    verbose: bool = False
)
```

**方法:**

#### extract_keyframes()
提取视频关键帧。

```python
extractor.extract_keyframes(
    video_path: str,
    output_dir: str,
    max_keyframes: int = 10,
    max_save: Optional[int] = None,
    use_simd: Optional[bool] = None,
    block_size: Optional[int] = None
) -> Dict[str, Any]
```

#### benchmark()
性能基准测试。

```python
extractor.benchmark(
    video_path: str,
    max_keyframes: int = 10,
    test_name: str = "default",
    use_simd: Optional[bool] = None,
    block_size: Optional[int] = None
) -> Dict[str, Any]
```

#### get_cpu_features()
获取 CPU 特性支持情况。

```python
cpu_features = extractor.get_cpu_features()
# 返回: {'avx2': True, 'sse4.1': True, ...}
```

#### get_thread_count()
获取实际使用的线程数。

```python
thread_count = extractor.get_thread_count()
```

### check_inkfox_available()

检查 inkfox 是否可用。

```python
from kernel.llm import check_inkfox_available

if check_inkfox_available():
    print("inkfox 可用")
else:
    print("inkfox 不可用，请安装: pip install inkfox")
```

### get_system_info()

获取系统信息。

```python
from kernel.llm import get_system_info

info = get_system_info()
print(info)
```

## 高级用法

### 性能优化

```python
from kernel.llm import VideoKeyframeExtractor

extractor = VideoKeyframeExtractor(threads=8, verbose=True)

# 使用 SIMD 加速
result = extractor.extract_keyframes(
    video_path="video.mp4",
    output_dir="./output",
    max_keyframes=20,
    use_simd=True,
    block_size=16  # 自定义块大小
)
```

### 性能基准测试

```python
# 对比不同配置的性能
configs = [
    ("无 SIMD", {"use_simd": False}),
    ("启用 SIMD", {"use_simd": True}),
    ("SIMD + 大块", {"use_simd": True, "block_size": 16}),
]

for test_name, config in configs:
    result = extractor.benchmark(
        video_path="video.mp4",
        max_keyframes=10,
        test_name=test_name,
        **config
    )
    print(f"{test_name}: {result['processing_fps']:.2f} FPS")
```

### 与 LLM 结合使用

```python
from kernel.llm import (
    extract_keyframes_from_video,
    compress_image,
    image_to_base64
)
from pathlib import Path

# 1. 提取关键帧
result = extract_keyframes_from_video(
    video_path="video.mp4",
    output_dir="./keyframes",
    max_keyframes=5
)

# 2. 处理关键帧图片
keyframe_files = sorted(Path("./keyframes").glob("keyframe_*.jpg"))
processed_images = []

for frame_path in keyframe_files:
    # 压缩并转换为 Base64
    base64_str = image_to_base64(
        str(frame_path),
        compress=True,
        max_size=(512, 512),
        quality=85
    )
    processed_images.append(base64_str)

# 3. 发送给 LLM 进行分析
# from kernel.llm import generate
# response = generate(
#     model="gpt-4-vision",
#     messages=[{
#         "role": "user",
#         "content": [
#             {"type": "text", "text": "请分析这些视频关键帧"},
#             *[{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}} 
#               for img in processed_images]
#         ]
#     }]
# )
```

## 错误处理

```python
from kernel.llm import (
    extract_keyframes_from_video,
    check_inkfox_available
)

# 检查可用性
if not check_inkfox_available():
    raise RuntimeError("inkfox 不可用，请安装: pip install inkfox")

try:
    result = extract_keyframes_from_video(
        video_path="video.mp4",
        output_dir="./keyframes",
        max_keyframes=10
    )
except FileNotFoundError as e:
    print(f"视频文件不存在: {e}")
except RuntimeError as e:
    print(f"提取失败: {e}")
```

## 示例代码

运行完整示例：

```bash
python examples/video_keyframe_demo.py
```

示例包含：
1. ✅ 检查 inkfox 可用性
2. ✅ 快速提取关键帧
3. ✅ 使用类接口
4. ✅ 性能基准测试
5. ✅ 与 LLM 结合使用

## 常见问题

### Q: inkfox 导入失败
**A:** 确保已安装 inkfox 且 Python 版本 >= 3.11
```bash
pip install inkfox
python --version  # 应该 >= 3.11
```

### Q: FFmpeg 找不到
**A:** 安装 FFmpeg 或指定路径
```python
extractor = VideoKeyframeExtractor(ffmpeg_path="/path/to/ffmpeg")
```

### Q: 如何提高性能
**A:** 
1. 启用 SIMD: `use_simd=True`
2. 增加线程数: `threads=8`
3. 调整块大小: `block_size=16`

### Q: 支持哪些视频格式
**A:** 所有 FFmpeg 支持的格式（MP4, AVI, MOV, MKV 等）

## 性能特性

- **SIMD 加速**: 支持 AVX2/SSE4.1 指令集
- **多线程**: 自动利用多核 CPU
- **高效处理**: 典型速度 100-500 FPS
- **内存优化**: 流式处理，内存占用低

## 与其他模块的集成

inkfox 已集成到 `kernel.llm` 模块，可以与其他 LLM 功能无缝配合：

```python
from kernel.llm import (
    # 视频处理
    extract_keyframes_from_video,
    VideoKeyframeExtractor,
    
    # 图像处理
    compress_image,
    image_to_base64,
    
    # LLM 请求
    generate,
    stream_generate
)
```

## 相关资源

- [inkfox GitHub](https://github.com/MoFox-Studio/inkfox)
- [API 文档](docs/kernel/llm/API_REFERENCE.md)
- [示例代码](examples/video_keyframe_demo.py)

## 许可证

inkfox 使用 MIT 许可证。
