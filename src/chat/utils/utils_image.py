import asyncio
import base64
import hashlib
import io
import os
import time
import uuid
from typing import Any

import aiofiles
import numpy as np
from PIL import Image
from rich.traceback import install
from sqlalchemy import and_, select

from src.common.database.core import get_db_session
from src.common.database.core.models import ImageDescriptions, Images
from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest

install(extra_lines=3)

logger = get_logger("chat_image")


def is_image_message(message: dict[str, Any]) -> bool:
    """
    判断消息是否为图片消息

    Args:
        message: 消息字典

    Returns:
        bool: 是否为图片消息
    """
    return message.get("type") == "image" or (
        isinstance(message.get("content"), dict) and message["content"].get("type") == "image"
    )


class ImageManager:
    _instance = None
    IMAGE_DIR = "data"  # 图像存储根目录

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._ensure_image_dir()

            self._initialized = True
            assert model_config is not None
            self.vlm = LLMRequest(model_set=model_config.model_task_config.vlm, request_type="image")

            # try:
            #     db.connect(reuse_if_open=True)
            #     # 使用SQLAlchemy创建表已在初始化时完成
            #     logger.debug("使用SQLAlchemy进行表管理")
            # except Exception as e:
            #     logger.error(f"数据库连接失败: {e}")

    def _ensure_image_dir(self):
        """确保图像存储目录存在"""
        os.makedirs(self.IMAGE_DIR, exist_ok=True)

    @staticmethod
    async def _get_description_from_db(image_hash: str, description_type: str) -> str | None:
        """从数据库获取图片描述

        Args:
            image_hash: 图片哈希值
            description_type: 描述类型 ('emoji' 或 'image')

        Returns:
            Optional[str]: 描述文本，如果不存在则返回None
        """
        try:
            async with get_db_session() as session:
                record = (
                    await session.execute(
                        select(ImageDescriptions).where(
                            and_(
                                ImageDescriptions.image_description_hash == image_hash,
                                ImageDescriptions.type == description_type,
                            )
                        )
                    )
                ).scalar()
                return record.description if record else None
        except Exception as e:
            logger.error(f"从数据库获取描述失败 (SQLAlchemy): {e!s}")
            return None

    @staticmethod
    async def _save_description_to_db(image_hash: str, description: str, description_type: str) -> None:
        """保存图片描述到数据库

        Args:
            image_hash: 图片哈希值
            description: 描述文本
            description_type: 描述类型 ('emoji' 或 'image')
        """
        try:
            current_timestamp = time.time()
            async with get_db_session() as session:
                # 查找现有记录
                existing = (
                    await session.execute(
                        select(ImageDescriptions).where(
                            and_(
                                ImageDescriptions.image_description_hash == image_hash,
                                ImageDescriptions.type == description_type,
                            )
                        )
                    )
                ).scalar()

                if existing:
                    # 更新现有记录
                    existing.description = description
                    existing.timestamp = current_timestamp
                else:
                    # 创建新记录
                    new_desc = ImageDescriptions(
                        image_description_hash=image_hash,
                        type=description_type,
                        description=description,
                        timestamp=current_timestamp,
                    )
                    session.add(new_desc)
                await session.commit()
                #  会在上下文管理器中自动调用
        except Exception as e:
            logger.error(f"保存描述到数据库失败 (SQLAlchemy): {e!s}")

    @staticmethod
    async def get_emoji_tag(image_base64: str) -> str:
        from src.chat.emoji_system.emoji_manager import get_emoji_manager

        emoji_manager = get_emoji_manager()
        if isinstance(image_base64, str):
            image_base64 = image_base64.encode("ascii", errors="ignore").decode("ascii")
        image_bytes = base64.b64decode(image_base64)
        image_hash = hashlib.md5(image_bytes).hexdigest()
        emoji = await emoji_manager.get_emoji_from_manager(image_hash)
        if not emoji:
            return "[表情包：未知]"
        emotion_list = emoji.emotion
        tag_str = ",".join(emotion_list)
        return f"[表情包：{tag_str}]"

    async def get_emoji_description(self, image_base64: str) -> str:
        """获取表情包描述，统一使用EmojiManager中的逻辑进行处理和缓存"""
        try:
            assert global_config is not None
            from src.chat.emoji_system.emoji_manager import get_emoji_manager

            emoji_manager = get_emoji_manager()

            # 1. 计算图片哈希 - 异步处理 CPU 密集型任务
            if isinstance(image_base64, str):
                image_base64 = image_base64.encode("ascii", errors="ignore").decode("ascii")
            
            def _calculate_hash_and_bytes(b64_str: str):
                data = base64.b64decode(b64_str)
                h = hashlib.md5(data).hexdigest()
                return data, h

            image_bytes, image_hash = await asyncio.to_thread(_calculate_hash_and_bytes, image_base64)

            # 如果缓存命中，可以提前释放 image_bytes
            # 但如果需要保存表情包，则需要保留 image_bytes

            # 2. 优先查询已注册表情的缓存（Emoji表）
            if full_description := await emoji_manager.get_emoji_description_by_hash(image_hash):
                logger.info("[缓存命中] 使用已注册表情包(Emoji表)的完整描述")
                del image_bytes  # 缓存命中，不再需要
                del image_base64
                refined_part = full_description.split(" Keywords:")[0]
                return f"[表情包：{refined_part}]"

            # 3. 查询通用图片描述缓存（ImageDescriptions表）
            if cached_description := await self._get_description_from_db(image_hash, "emoji"):
                logger.info("[缓存命中] 使用通用图片缓存(ImageDescriptions表)中的描述")
                del image_bytes  # 缓存命中，不再需要
                del image_base64
                refined_part = cached_description.split(" Keywords:")[0]
                return f"[表情包：{refined_part}]"

            # 4. 如果都未命中，则调用新逻辑生成描述
            logger.info(f"[新表情识别] 表情包未注册且无缓存 (Hash: {image_hash[:8]}...)，调用新逻辑生成描述")
            full_description, _emotions = await emoji_manager.build_emoji_description(image_base64)

            if not full_description:
                logger.warning("未能通过新逻辑生成有效描述")
                return "[表情包(描述生成失败)]"

            # 4. (可选) 如果启用了“偷表情包”，则将图片和完整描述存入待注册区
            if global_config.emoji and global_config.emoji.steal_emoji:
                logger.debug(f"偷取表情包功能已开启，保存待注册表情包: {image_hash}")
                try:
                    image_format = (Image.open(io.BytesIO(image_bytes)).format or "jpeg").lower()
                    current_timestamp = time.time()
                    filename = f"{int(current_timestamp)}_{image_hash[:8]}.{image_format}"
                    emoji_dir = os.path.join(self.IMAGE_DIR, "emoji")
                    os.makedirs(emoji_dir, exist_ok=True)
                    file_path = os.path.join(emoji_dir, filename)

                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(image_bytes)
                    logger.info(f"新表情包已保存至待注册目录: {file_path}")
                except Exception as e:
                    logger.error(f"保存待注册表情包文件失败: {e!s}")

            # 5. 将新生成的完整描述存入通用缓存（ImageDescriptions表）
            await self._save_description_to_db(image_hash, full_description, "emoji")
            logger.info(f"新生成的表情包描述已存入通用缓存 (Hash: {image_hash[:8]}...)")

            # 内存优化：处理完成后主动释放大型二进制数据
            del image_bytes
            del image_base64

            # 6. 返回新生成的描述中用于显示的"精炼描述"部分
            refined_part = full_description.split(" Keywords:")[0]
            return f"[表情包：{refined_part}]"

        except Exception as e:
            logger.error(f"获取表情包描述失败: {e!s}")
            return "[表情包(处理失败)]"

    async def get_image_description(self, image_base64: str) -> str:
        """获取普通图片描述，采用同步识别+缓存策略"""
        try:
            # 1. 计算图片哈希 - 异步处理 CPU 密集型任务
            if isinstance(image_base64, str):
                image_base64 = image_base64.encode("ascii", errors="ignore").decode("ascii")
            
            def _calculate_hash_and_bytes(b64_str: str):
                data = base64.b64decode(b64_str)
                h = hashlib.md5(data).hexdigest()
                return data, h

            image_bytes, image_hash = await asyncio.to_thread(_calculate_hash_and_bytes, image_base64)

            # 1.5. 如果是GIF，先转换为JPG
            try:
                def _get_image_format(data: bytes):
                    return (Image.open(io.BytesIO(data)).format or "jpeg").lower()
                
                image_format_check = await asyncio.to_thread(_get_image_format, image_bytes)
                if image_format_check == "gif":
                    logger.info(f"检测到GIF图片 (Hash: {image_hash[:8]}...)，正在转换为JPG...")
                    # 使用 asyncio.to_thread 将耗时的 GIF 处理移至线程池
                    if transformed_b64 := await asyncio.to_thread(self.transform_gif, image_base64):
                        image_base64 = transformed_b64
                        image_bytes = base64.b64decode(image_base64)
                        logger.info("GIF转换成功，将使用转换后的图片进行描述")
                    else:
                        logger.error("GIF转换失败，无法生成描述")
                        return "[图片(GIF转换失败)]"
            except Exception as e:
                logger.warning(f"图片格式检测失败: {e!s}，将按原格式处理")


            # 2. 优先查询 Images 表缓存
            async with get_db_session() as session:
                result = await session.execute(select(Images).where(Images.emoji_hash == image_hash))
                existing_image = result.scalar()
                if existing_image and existing_image.description:
                    logger.debug(f"[缓存命中] 使用Images表中的图片描述: {existing_image.description[:50]}...")
                    # 缓存命中，释放 base64 和 image_bytes
                    del image_bytes
                    del image_base64
                    return f"[图片：{existing_image.description}]"

            # 3. 其次查询 ImageDescriptions 表缓存
            if cached_description := await self._get_description_from_db(image_hash, "image"):
                logger.debug(f"[缓存命中] 使用ImageDescriptions表中的描述: {cached_description[:50]}...")
                # 缓存命中，释放 base64 和 image_bytes
                del image_bytes
                del image_base64
                return f"[图片：{cached_description}]"

            # 4. 如果都未命中，则同步调用VLM生成新描述
            logger.info(f"[新图片识别] 无缓存 (Hash: {image_hash[:8]}...)，调用VLM生成描述")
            description = None
            assert global_config is not None
            assert global_config.custom_prompt is not None
            prompt = global_config.custom_prompt.image_prompt
            logger.info(f"[识图VLM调用] Prompt: {prompt}")
            for i in range(3):  # 重试3次
                try:
                    image_format = (Image.open(io.BytesIO(image_bytes)).format or "jpeg").lower()
                    logger.info(f"[VLM调用] 正在为图片生成描述 (第 {i+1}/3 次)...")
                    description, response_tuple = await self.vlm.generate_response_for_image(
                        prompt, image_base64, image_format, temperature=0.4, max_tokens=300
                    )
                    # response_tuple is (reasoning, model_name, tool_calls)
                    model_name_used = response_tuple[1]
                    logger.info(f"[VLM调用成功] 使用模型: {model_name_used}")
                    if description and description.strip():
                        break  # 成功获取描述则跳出循环
                except Exception as e:
                    # 简化日志：只显示错误类型和简短消息
                    error_brief = f"{type(e).__name__}: {str(e)[:80]}"
                    if i < 2:
                        logger.warning(f"VLM调用失败 (第 {i+1}/3 次): {error_brief}，1秒后重试...")
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"VLM调用失败 (第 {i+1}/3 次，已达最大重试): {error_brief}")

            if not description or not description.strip():
                logger.warning("VLM未能生成有效描述")
                return "[图片(描述生成失败)]"

            logger.info(f"[VLM完成] 图片描述生成: {description[:50]}...")

            # 5. 将新描述存入两个缓存表
            await self._save_description_to_db(image_hash, description, "image")
            async with get_db_session() as session:
                result = await session.execute(select(Images).where(Images.emoji_hash == image_hash))
                existing_image_for_update = result.scalar()
                if existing_image_for_update:
                    existing_image_for_update.description = description
                    existing_image_for_update.vlm_processed = True
                    logger.debug(f"[数据库] 为现有图片记录补充描述: {image_hash[:8]}...")
                # 注意：这里不创建新的Images记录，因为process_image会负责创建
                await session.commit()

            logger.info(f"新生成的图片描述已存入缓存 (Hash: {image_hash[:8]}...)")

            # 内存优化：处理完成后主动释放大型二进制数据
            del image_bytes
            del image_base64

            return f"[图片：{description}]"

        except Exception as e:
            logger.error(f"获取图片描述时发生严重错误: {e!s}")
            return "[图片(处理失败)]"

    @staticmethod
    def transform_gif(gif_base64: str) -> str | None:
        # sourcery skip: use-contextlib-suppress
        """将GIF转换为水平拼接的静态图像, 均匀抽取4帧。

        Args:
            gif_base64: GIF的base64编码字符串

        Returns:
            Optional[str]: 拼接后的JPG图像的base64编码字符串, 或者在失败时返回None
        """
        try:
            # 确保base64字符串只包含ASCII字符
            if isinstance(gif_base64, str):
                gif_base64 = gif_base64.encode("ascii", errors="ignore").decode("ascii")
            # 解码base64
            gif_data = base64.b64decode(gif_base64)
            gif = Image.open(io.BytesIO(gif_data))

            # 收集所有帧
            all_frames = []
            try:
                while True:
                    gif.seek(len(all_frames))
                    # 确保是RGB格式方便比较
                    frame = gif.convert("RGB")
                    all_frames.append(frame.copy())
            except EOFError:
                ...  # 读完啦

            if not all_frames:
                logger.warning("GIF中没有找到任何帧")
                return None  # 空的GIF直接返回None

            # --- 新的帧选择逻辑：均匀抽取4帧 ---
            num_frames = len(all_frames)
            if num_frames <= 4:
                # 如果总宽度小于等于4，则全部选中
                selected_frames = all_frames
                indices = list(range(num_frames))
            else:
                # 使用linspace计算4个均匀分布的索引
                indices = np.linspace(0, num_frames - 1, 4, dtype=int)
                selected_frames = [all_frames[i] for i in indices]

            logger.debug(f"GIF Frame Analysis: Total frames={num_frames}, Selected indices={indices}")
            # --- 帧选择逻辑结束 ---

            # 如果选择后连一帧都没有（比如GIF只有一帧且后续处理失败？）或者原始GIF就没帧，也返回None
            if not selected_frames:
                logger.warning("处理后没有选中任何帧")
                return None

            # logger.debug(f"总帧数: {len(all_frames)}, 选中帧数: {len(selected_frames)}")

            # 获取选中的第一帧的尺寸（假设所有帧尺寸一致）
            frame_width, frame_height = selected_frames[0].size

            # 计算目标尺寸，保持宽高比
            target_height = 200  # 固定高度
            # 防止除以零
            if frame_height == 0:
                logger.error("帧高度为0，无法计算缩放尺寸")
                return None
            target_width = int((target_height / frame_height) * frame_width)
            # 宽度也不能是0
            if target_width == 0:
                logger.warning(f"计算出的目标宽度为0 (原始尺寸 {frame_width}x{frame_height})，调整为1")
                target_width = 1

            # 调整所有选中帧的大小
            resized_frames = [
                frame.resize((target_width, target_height), Image.Resampling.LANCZOS) for frame in selected_frames
            ]

            # 创建拼接图像
            total_width = target_width * len(resized_frames)
            # 防止总宽度为0
            if total_width == 0 and resized_frames:
                logger.warning("计算出的总宽度为0，但有选中帧，可能目标宽度太小")
                # 至少给点宽度吧
                total_width = len(resized_frames)
            elif total_width == 0:
                logger.error("计算出的总宽度为0且无选中帧")
                return None

            combined_image = Image.new("RGB", (total_width, target_height))

            # 水平拼接图像
            for idx, frame in enumerate(resized_frames):
                combined_image.paste(frame, (idx * target_width, 0))

            # 转换为base64
            buffer = io.BytesIO()
            combined_image.save(buffer, format="JPEG", quality=85)  # 保存为JPEG
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except MemoryError:
            logger.error("GIF转换失败: 内存不足，可能是GIF太大或帧数太多")
            return None  # 内存不够啦
        except Exception as e:
            logger.error(f"GIF转换失败: {e!s}")  # 记录详细错误信息
            return None  # 其他错误也返回None

    async def process_image(self, image_base64: str) -> tuple[str, str]:
        """处理图片并返回图片ID和描述，采用异步识别流程"""
        try:
            if isinstance(image_base64, str):
                image_base64 = image_base64.encode("ascii", errors="ignore").decode("ascii")
            
            def _calculate_hash_and_bytes(b64_str: str):
                data = base64.b64decode(b64_str)
                h = hashlib.md5(data).hexdigest()
                return data, h

            image_bytes, image_hash = await asyncio.to_thread(_calculate_hash_and_bytes, image_base64)

            image_id = ""
            description = ""

            async with get_db_session() as session:
                result = await session.execute(select(Images).where(Images.emoji_hash == image_hash))
                existing_image = result.scalar()

                if existing_image and existing_image.image_id:
                    image_id = existing_image.image_id
                    existing_image.count += 1
                    logger.debug(f"图片记录已存在 (ID: {image_id})，使用次数 +1")

                    if existing_image.description and existing_image.description.strip():
                        description = f"[图片：{existing_image.description}]"
                        logger.debug("缓存命中，直接返回数据库中已有的完整描述")
                        return image_id, description
                    else:
                        logger.warning(f"图片记录 (ID: {image_id}) 描述为空，将同步生成")
                        description = await self.get_image_description(image_base64)
                        existing_image.description = description.replace("[图片：", "").replace("]", "")
                        existing_image.vlm_processed = True
                else:
                    logger.debug(f"新图片 (Hash: {image_hash[:8]}...)，将同步生成描述并创建新记录")
                    image_id = str(uuid.uuid4())
                    description = await self.get_image_description(image_base64)

                    # 如果描述生成失败，则不存入数据库，直接返回失败信息
                    if "(处理失败)" in description or "(描述生成失败)" in description:
                        logger.warning("图片描述生成失败，不创建数据库记录，直接返回失败信息。")
                        return "", description

                    clean_description = description.replace("[图片：", "").replace("]", "")
                    
                    def _get_image_format(data: bytes):
                        return (Image.open(io.BytesIO(data)).format or "png").lower()
                    
                    image_format = await asyncio.to_thread(_get_image_format, image_bytes)
                    filename = f"{image_id}.{image_format}"
                    image_dir = os.path.join(self.IMAGE_DIR, "images")
                    os.makedirs(image_dir, exist_ok=True)
                    file_path = os.path.join(image_dir, filename)

                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(image_bytes)

                    new_img = Images(
                        image_id=image_id,
                        emoji_hash=image_hash,
                        path=file_path,
                        type="image",
                        description=clean_description,
                        timestamp=time.time(),
                        vlm_processed=True,
                        count=1,
                    )
                    session.add(new_img)
                    logger.info(f"新图片记录已创建 (ID: {image_id})")

                await session.commit()

            # 无论是新图片还是旧图片，只要成功获取描述，就直接返回描述
            return image_id, description

        except Exception as e:
            logger.error(f"处理图片时发生严重错误: {e!s}")
            return "", "[图片(处理失败)]"


# 创建全局单例
image_manager = None


def get_image_manager() -> ImageManager:
    """获取全局图片管理器单例"""
    global image_manager
    if image_manager is None:
        image_manager = ImageManager()
    return image_manager


def image_path_to_base64(image_path: str) -> str:
    """将图片路径转换为base64编码
    Args:
        image_path: 图片文件路径
    Returns:
        str: base64编码的图片数据
    Raises:
        FileNotFoundError: 当图片文件不存在时
        IOError: 当读取图片文件失败时
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    with open(image_path, "rb") as f:
        if image_data := f.read():
            return base64.b64encode(image_data).decode("utf-8")
        else:
            raise OSError(f"读取图片文件失败: {image_path}")
