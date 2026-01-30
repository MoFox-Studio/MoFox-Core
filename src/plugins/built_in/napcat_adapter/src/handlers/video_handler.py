#!/usr/bin/env python3
"""
视频下载和处理模块
用于从QQ消息中下载视频并转发给Bot进行分析
"""

import asyncio
from pathlib import Path
from typing import Any

import aiohttp

from src.common.logger import get_logger

logger = get_logger("video_handler")


class VideoDownloader:
    def __init__(self, max_size_mb: int = 100, download_timeout: int = 60):
        self.max_size_mb = max_size_mb
        self.download_timeout = download_timeout
        self.supported_formats = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v"}

    def is_video_url(self, url: str) -> bool:
        """检查URL是否为视频文件"""
        try:
            # QQ视频URL可能没有扩展名，所以先检查Content-Type
            # 对于QQ视频，我们先假设是视频，稍后通过Content-Type验证

            # 检查URL中是否包含视频相关的关键字
            video_keywords = ["video", "mp4", "avi", "mov", "mkv", "flv", "wmv", "webm", "m4v"]
            url_lower = url.lower()

            # 如果URL包含视频关键字，认为是视频
            if any(keyword in url_lower for keyword in video_keywords):
                return True

            # 检查文件扩展名(传统方法)
            path = Path(url.split("?")[0])  # 移除查询参数
            if path.suffix.lower() in self.supported_formats:
                return True

            # 对于QQ等特殊平台,URL可能没有扩展名
            # 我们允许这些URL通过,稍后通过HTTP头Content-Type验证
            qq_domains = ["qpic.cn", "gtimg.cn", "qq.com", "tencent.com"]
            if any(domain in url_lower for domain in qq_domains):
                return True

            return False
        except Exception:
            # 如果解析失败,默认允许尝试下载(稍后验证)
            return True

    def check_file_size(self, content_length: str | None) -> bool:
        """检查文件大小是否在允许范围内"""
        if content_length is None:
            return True  # 无法获取大小时允许下载

        try:
            size_bytes = int(content_length)
            size_mb = size_bytes / (1024 * 1024)
            return size_mb <= self.max_size_mb
        except Exception:
            return True

    async def download_video(self, url: str, filename: str | None = None) -> dict[str, Any]:
        """
        下载视频文件

        Args:
            url: 视频URL
            filename: 可选的文件名

        Returns:
            dict: 下载结果，包含success、data、filename、error等字段
        """
        try:
            logger.info(f"开始下载视频: {url}")

            # 检查URL格式
            if not self.is_video_url(url):
                logger.warning(f"URL格式检查失败: {url}")
                return {"success": False, "error": "不支持的视频格式", "url": url}

            async with aiohttp.ClientSession() as session:
                # 先发送HEAD请求检查文件大小
                try:
                    async with session.head(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status != 200:
                            logger.warning(f"HEAD请求失败，状态码: {response.status}")
                        else:
                            content_length = response.headers.get("Content-Length")
                            if not self.check_file_size(content_length):
                                return {
                                    "success": False,
                                    "error": f"视频文件过大，超过{self.max_size_mb}MB限制",
                                    "url": url,
                                }
                except Exception as e:
                    logger.warning(f"HEAD请求失败: {e}，继续尝试下载")

                # 下载文件
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.download_timeout)) as response:
                    if response.status != 200:
                        return {"success": False, "error": f"下载失败，HTTP状态码: {response.status}", "url": url}

                    # 检查Content-Type是否为视频
                    content_type = response.headers.get("Content-Type", "").lower()
                    if content_type:
                        # 检查是否为视频类型
                        video_mime_types = [
                            "video/",
                            "application/octet-stream",
                            "application/x-msvideo",
                            "video/x-msvideo",
                        ]
                        is_video_content = any(mime in content_type for mime in video_mime_types)

                        if not is_video_content:
                            logger.warning(f"Content-Type不是视频格式: {content_type}")
                            # 如果不是明确的视频类型，但可能是QQ的特殊格式，继续尝试
                            if "text/" in content_type or "application/json" in content_type:
                                return {
                                    "success": False,
                                    "error": f"URL返回的不是视频内容，Content-Type: {content_type}",
                                    "url": url,
                                }

                    # 再次检查Content-Length
                    content_length = response.headers.get("Content-Length")
                    if not self.check_file_size(content_length):
                        return {"success": False, "error": f"视频文件过大，超过{self.max_size_mb}MB限制", "url": url}

                    # 读取文件内容
                    video_data = await response.read()

                    # 检查实际文件大小
                    actual_size_mb = len(video_data) / (1024 * 1024)
                    if actual_size_mb > self.max_size_mb:
                        return {
                            "success": False,
                            "error": f"视频文件过大，实际大小: {actual_size_mb:.2f}MB",
                            "url": url,
                        }

                    # 确定文件名
                    if filename is None:
                        filename = Path(url.split("?")[0]).name
                        if not filename or "." not in filename:
                            filename = "video.mp4"

                    logger.info(f"视频下载成功: {filename}, 大小: {actual_size_mb:.2f}MB")

                    return {
                        "success": True,
                        "data": video_data,
                        "filename": filename,
                        "size_mb": actual_size_mb,
                        "url": url,
                    }

        except asyncio.TimeoutError:
            return {"success": False, "error": "下载超时", "url": url}
        except Exception as e:
            logger.error(f"下载视频时出错: {e}")
            return {"success": False, "error": str(e), "url": url}


# 全局实例
_video_downloader = None


def get_video_downloader(max_size_mb: int = 100, download_timeout: int = 60) -> VideoDownloader:
    """获取视频下载器实例"""
    global _video_downloader
    if _video_downloader is None:
        _video_downloader = VideoDownloader(max_size_mb, download_timeout)
    return _video_downloader
