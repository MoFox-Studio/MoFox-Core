"""
LLM 工具函数

提供图片压缩、格式转换等基本工具
"""

import base64
import io
from pathlib import Path
from typing import Any, Tuple, Union

from PIL import Image
from kernel.logger import get_logger

logger = get_logger(__name__)


def _load_image(image_source: Union[str, Path, bytes, bytearray, memoryview, Image.Image]) -> Image.Image:
    """将多种图片输入统一加载为 PIL Image。"""
    if isinstance(image_source, Image.Image):
        return image_source
    if isinstance(image_source, (str, Path)):
        return Image.open(image_source)
    if isinstance(image_source, (bytes, bytearray, memoryview)):
        return Image.open(io.BytesIO(image_source))
    raise ValueError(f"Unsupported image source type: {type(image_source)}")


def compress_image(
    image_source: Union[str, Path, bytes, bytearray, memoryview, Image.Image],
    max_size: Tuple[int, int] = (1024, 1024),
    quality: int = 85,
    image_format: str = 'JPEG'
) -> bytes:
    """压缩图片
    
    Args:
        image_source: 图片源（文件路径、字节数据或 PIL Image 对象）
        max_size: 最大尺寸 (width, height)
        quality: JPEG 质量 (1-100)
        image_format: 输出格式 ('JPEG', 'PNG', 'WEBP')
        
    Returns:
        bytes: 压缩后的图片字节数据
        
    Raises:
        ValueError: 参数错误
        IOError: 图片处理失败
    """
    try:
        img = _load_image(image_source)

        # 转换为 RGB（JPEG 不支持透明度）
        if image_format.upper() == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # 调整大小（保持宽高比）
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 保存到字节流
        output = io.BytesIO()
        save_kwargs: dict[str, Any] = {'format': image_format.upper()}
        
        if image_format.upper() == 'JPEG':
            save_kwargs['quality'] = quality
            save_kwargs['optimize'] = True
        elif image_format.upper() == 'PNG':
            save_kwargs['optimize'] = True
        elif image_format.upper() == 'WEBP':
            save_kwargs['quality'] = quality
        
        img.save(output, **save_kwargs)
        compressed_data = output.getvalue()
        
        logger.debug(
            "图片压缩完成: 原始尺寸=%s, 压缩后大小=%s bytes",
            img.size,
            len(compressed_data),
        )
        
        return compressed_data
        
    except Exception as e:
        logger.error("图片压缩失败: %s", e)
        raise IOError(f"Failed to compress image: {e}") from e


def image_to_base64(
    image_source: Union[str, Path, bytes, bytearray, memoryview, Image.Image],
    compress: bool = True,
    max_size: Tuple[int, int] = (1024, 1024),
    quality: int = 85,
    image_format: str = 'JPEG'
) -> str:
    """将图片转换为 Base64 编码字符串
    
    Args:
        image_source: 图片源
        compress: 是否压缩
        max_size: 压缩时的最大尺寸
        quality: 压缩质量
        format: 输出格式
        
    Returns:
        str: Base64 编码的字符串
    """
    try:
        # 如果需要压缩
        if compress:
            image_bytes = compress_image(image_source, max_size, quality, image_format)
        else:
            # 直接读取字节
            if isinstance(image_source, (bytes, bytearray, memoryview)):
                image_bytes = bytes(image_source)
            elif isinstance(image_source, (str, Path)):
                with open(image_source, 'rb') as f:
                    image_bytes = f.read()
            elif isinstance(image_source, Image.Image):
                output = io.BytesIO()
                image_source.save(output, format=image_format)
                image_bytes = output.getvalue()
            else:
                raise ValueError(f"Unsupported image source type: {type(image_source)}")
        
        # 编码为 Base64
        base64_str = base64.b64encode(image_bytes).decode('utf-8')
        
        logger.debug("图片转换为 Base64: 长度=%s", len(base64_str))
        
        return base64_str
        
    except Exception as e:
        logger.error("图片转 Base64 失败: %s", e)
        raise


def base64_to_image(base64_str: str) -> Image.Image:
    """将 Base64 字符串转换为 PIL Image 对象
    
    Args:
        base64_str: Base64 编码的字符串
        
    Returns:
        Image.Image: PIL Image 对象
    """
    try:
        # 移除可能的 data URL 前缀
        if ',' in base64_str:
            base64_str = base64_str.split(',', 1)[1]
        
        # 解码
        image_bytes = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(image_bytes))
        
        logger.debug("Base64 转换为图片: 尺寸=%s, 模式=%s", img.size, img.mode)
        
        return img
        
    except Exception as e:
        logger.error("Base64 转图片失败: %s", e)
        raise ValueError(f"Failed to decode base64 image: {e}") from e


def get_image_mime_type(image_format: str) -> str:
    """获取图片格式对应的 MIME 类型"""
    mime_types = {
        'JPEG': 'image/jpeg',
        'JPG': 'image/jpeg',
        'PNG': 'image/png',
        'WEBP': 'image/webp',
        'GIF': 'image/gif',
        'BMP': 'image/bmp'
    }
    return mime_types.get(image_format.upper(), 'image/jpeg')


def create_data_url(
    image_source: Union[str, Path, bytes, bytearray, memoryview, Image.Image],
    compress: bool = True,
    image_format: str = 'JPEG',
    **compress_kwargs
) -> str:
    """创建 data URL 格式的图片字符串
    
    Args:
        image_source: 图片源
        compress: 是否压缩
        image_format: 图片格式
        **compress_kwargs: 压缩参数
        
    Returns:
        str: data URL 格式字符串 (data:image/jpeg;base64,...)
    """
    base64_str = image_to_base64(
        image_source,
        compress=compress,
        image_format=image_format,
        **compress_kwargs
    )
    
    mime_type = get_image_mime_type(image_format)
    data_url = f"data:{mime_type};base64,{base64_str}"
    
    return data_url


def estimate_tokens(
    text: str,
    method: str = 'approximate'
) -> int:
    """估算文本的 token 数量
    
    Args:
        text: 输入文本
        method: 估算方法 ('approximate', 'chars')
            - 'approximate': 粗略估算（英文约4字符=1token，中文约2字符=1token）
            - 'chars': 按字符数估算
            
    Returns:
        int: 估算的 token 数量
        
    Note:
        这只是粗略估算，实际 token 数量取决于具体的 tokenizer
    """
    if not text:
        return 0
    
    if method == 'approximate':
        # 简单的启发式估算
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        # 中文约 2 字符/token，英文约 4 字符/token
        estimated = (chinese_chars / 2) + (other_chars / 4)
        return int(estimated)
    
    elif method == 'chars':
        return len(text)
    
    else:
        raise ValueError(f"Unknown estimation method: {method}")


def truncate_text(
    text: str,
    max_tokens: int,
    method: str = 'approximate',
    suffix: str = '...'
) -> str:
    """截断文本以不超过指定的 token 数量
    
    Args:
        text: 输入文本
        max_tokens: 最大 token 数量
        method: token 估算方法
        suffix: 截断后添加的后缀
        
    Returns:
        str: 截断后的文本
    """
    if estimate_tokens(text, method) <= max_tokens:
        return text
    
    # 二分查找合适的截断位置
    left, right = 0, len(text)
    
    while left < right:
        mid = (left + right + 1) // 2
        truncated = text[:mid] + suffix
        
        if estimate_tokens(truncated, method) <= max_tokens:
            left = mid
        else:
            right = mid - 1
    
    return text[:left] + suffix if left < len(text) else text


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小
    
    Args:
        size_bytes: 字节数
        
    Returns:
        str: 格式化后的字符串 (如 '1.5 MB')
    """
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
