import asyncio
import base64
import hashlib
import io
import json
import os
import random
import re
import time
import traceback
from typing import Any, Optional, cast

import json_repair
from PIL import Image
from sqlalchemy import select

from src.chat.emoji_system.emoji_constants import EMOJI_DIR, EMOJI_REGISTERED_DIR, MAX_EMOJI_FOR_PROMPT
from src.chat.emoji_system.emoji_entities import MaiEmoji
from src.chat.emoji_system.emoji_utils import (
    _emoji_objects_to_readable_list,
    _ensure_emoji_dir,
    _to_emoji_objects,
    clean_unused_emojis,
    clear_temp_emoji,
    list_image_files,
)
from src.chat.utils.utils_image import get_image_manager, image_path_to_base64
from src.common.database.api.crud import CRUDBase
from src.common.database.compatibility import get_db_session
from src.common.database.core.models import Emoji, Images
from src.common.database.utils.decorators import cached
from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest

logger = get_logger("emoji")

class EmojiManager:
    _instance = None
    _initialized: bool = False  # 显式声明，避免属性未定义错误

    def __new__(cls) -> "EmojiManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 类属性已声明，无需再次赋值
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return  # 如果已经初始化过，直接返回

        self._scan_task = None
        self._emoji_index: dict[str, MaiEmoji] = {}
        self._integrity_yield_every = 50
        self._integrity_cursor = 0
        self._integrity_batch_size = 500

        if model_config is None:
            raise RuntimeError("Model config is not initialized")
        if global_config is None:
            raise RuntimeError("Global config is not initialized")

        self.vlm = LLMRequest(model_set=model_config.model_task_config.emoji_vlm, request_type="emoji")
        self.llm_emotion_judge = LLMRequest(
            model_set=model_config.model_task_config.utils, request_type="emoji"
        )  # 更高的温度，更少的token（后续可以根据情绪来调整温度）

        self.emoji_num = 0
        self.emoji_num_max = global_config.emoji.max_reg_num
        self.emoji_num_max_reach_deletion = global_config.emoji.do_replace
        self.emoji_objects: list[MaiEmoji] = []  # 存储MaiEmoji对象的列表，使用类型注解明确列表元素类型
        _ensure_emoji_dir()
        self._initialized = True
        logger.info("启动表情包管理器")

    def shutdown(self) -> None:
        """关闭EmojiManager，取消正在运行的任务"""
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
            logger.info("表情包扫描任务已取消")

    def initialize(self) -> None:
        """初始化数据库连接和表情目录"""

    #     try:
    #         db.connect(reuse_if_open=True)
    #         if db.is_closed():
    #             raise RuntimeError("数据库连接失败")
    #         _ensure_emoji_dir()
    #         self._initialized = True  # 标记为已初始化
    #         logger.info("EmojiManager初始化成功")
    #     except Exception as e:
    #         logger.error(f"EmojiManager初始化失败: {e}")
    #         self._initialized = False
    #         raise

    # def _ensure_db(self) -> None:
    #     """确保数据库已初始化"""
    #     if not self._initialized:
    #         self.initialize()
    #     if not self._initialized:
    #         raise RuntimeError("EmojiManager not initialized")

    async def record_usage(self, emoji_hash: str) -> None:
        """记录表情使用次数"""
        try:
            async with get_db_session() as session:
                stmt = select(Emoji).where(Emoji.emoji_hash == emoji_hash)
                result = await session.execute(stmt)
                emoji_update = result.scalar_one_or_none()
                if emoji_update:
                    emoji_update.usage_count += 1
                    emoji_update.last_used_time = time.time()  # Update last used time
                    await session.commit()
                else:
                    logger.error(f"记录表情使用失败: 未找到 hash 为 {emoji_hash} 的表情包")
        except Exception as e:
            logger.error(f"记录表情使用失败: {e!s}")

    async def get_emoji_for_text(self, text_emotion: str) -> tuple[str, str, str] | None:
        """
        根据文本内容，使用LLM选择一个合适的表情包。

        Args:
            text_emotion (str): LLM希望表达的情感或意图的文本描述。

        Returns:
            Optional[Tuple[str, str, str]]: 返回一个元组，包含所选表情包的 (文件路径, 描述, 匹配的情感描述)，
                                            如果未找到合适的表情包，则返回 None。
        """
        try:
            _time_start = time.time()

            # 1. 从内存中获取所有可用的表情包对象
            all_emojis = [emoji for emoji in self.emoji_objects if not emoji.is_deleted and emoji.description]
            if not all_emojis:
                logger.warning("内存中没有任何可用的表情包对象")
                return None

            # 2. 根据全局配置决定候选表情包的数量
            if global_config is None:
                raise RuntimeError("Global config is not initialized")
            max_candidates = global_config.emoji.max_context_emojis

            # 如果配置为0或者大于等于总数，则选择所有表情包
            if max_candidates <= 0 or max_candidates >= len(all_emojis):
                candidate_emojis = all_emojis
            else:
                # 否则，从所有表情包中随机抽取指定数量
                candidate_emojis = random.sample(all_emojis, max_candidates)

            # 确保候选列表不为空
            if not candidate_emojis:
                logger.warning("未能选出任何候选表情包")
                return None

            # 3. 构建用于LLM决策的prompt
            emoji_options_str = ""
            for i, emoji in enumerate(candidate_emojis):
                # 为每个表情包创建一个编号和它的详细描述
                emoji_options_str += f"编号: {i + 1}\n描述: {emoji.description}\n\n"

            # 精心设计的prompt，引导LLM做出选择
            prompt = f"""
            你是一个聊天机器人，你需要根据你想要表达的情感，从一个表情包列表中选择最合适的一个。

            # 你的任务
            根据下面提供的“你想表达的描述”，在“表情包选项”中选择一个最符合该描述的表情包。

            # 你想表达的描述
            {text_emotion}

            # 表情包选项
            {emoji_options_str}

            # 规则
            1.  仔细阅读“你想表达的描述”和每一个“表情包选项”的详细描述。
            2.  选择一个编号，该编号对应的表情包必须最贴切地反映出你想表达的情感、内容或网络文化梗。
            3.  你的回答必须且只能是一个格式为 "选择编号：X" 的字符串，其中X是你选择的表情包编号。
            4.  不要输出任何其他解释或无关内容。

            现在，请做出你的选择：
            """

            # 4. 调用LLM进行决策
            decision, _ = await self.llm_emotion_judge.generate_response_async(prompt, temperature=0.5, max_tokens=20)
            logger.debug(f"LLM选择的描述: {text_emotion}")
            logger.debug(f"LLM决策结果: {decision}")

            # 5. 解析LLM的决策结果
            match = re.search(r"(\d+)", decision)
            if not match:
                logger.error(f"无法从LLM的决策中解析出编号: {decision}")
                return None

            selected_index = int(match.group(1)) - 1

            # 6. 验证选择的编号是否有效
            if not (0 <= selected_index < len(candidate_emojis)):
                logger.error(f"LLM返回了无效的表情包编号: {selected_index + 1}")
                return None

            # 7. 获取选中的表情包并更新使用记录
            selected_emoji = candidate_emojis[selected_index]
            await self.record_usage(selected_emoji.hash)
            _time_end = time.time()

            logger.info(f"找到匹配描述的表情包: {selected_emoji.description}, 耗时: {(_time_end - _time_start):.2f}s")

            # 8. 返回选中的表情包信息
            return selected_emoji.full_path, f"[表情包：{selected_emoji.description}]", text_emotion

        except Exception as e:
            logger.error(f"使用LLM获取表情包时发生错误: {e!s}")
            logger.error(traceback.format_exc())
            return None

    async def check_emoji_file_integrity(self) -> None:
        """检查表情包文件完整性
        遍历self.emoji_objects中的所有对象，检查文件是否存在
        如果文件已被删除，则执行对象的删除方法并从列表中移除
        """
        try:
            total_count = len(self.emoji_objects)
            self.emoji_num = total_count
            removed_count = 0
            if total_count == 0:
                return

            start = self._integrity_cursor % total_count
            end = min(start + self._integrity_batch_size, total_count)
            indices: list[int] = list(range(start, end))
            if end - start < self._integrity_batch_size and total_count > 0:
                wrap_rest = self._integrity_batch_size - (end - start)
                if wrap_rest > 0:
                    indices.extend(range(0, min(wrap_rest, total_count)))

            objects_to_remove: list[MaiEmoji] = []
            processed = 0
            for idx in indices:
                if idx >= len(self.emoji_objects):
                    break
                emoji = self.emoji_objects[idx]
                try:
                    if emoji.is_deleted:
                        objects_to_remove.append(emoji)
                        continue

                    exists = await asyncio.to_thread(os.path.exists, emoji.full_path)
                    if not exists:
                        logger.warning(f"[检查] 表情包文件丢失: {emoji.full_path}")
                        await emoji.delete()
                        objects_to_remove.append(emoji)
                        self.emoji_num -= 1
                        removed_count += 1
                        continue

                    if not emoji.description:
                        logger.warning(f"[检查] 表情包描述为空，视为无效: {emoji.filename}")
                        await emoji.delete()
                        objects_to_remove.append(emoji)
                        self.emoji_num -= 1
                        removed_count += 1
                        continue

                    processed += 1
                    if processed % self._integrity_yield_every == 0:
                        await asyncio.sleep(0)

                except Exception as item_error:
                    logger.error(f"[错误] 处理表情包记录时出错 ({emoji.filename}): {item_error!s}")
                    continue

            if objects_to_remove:
                self.emoji_objects = [e for e in self.emoji_objects if e not in objects_to_remove]
                for e in objects_to_remove:
                    if e.hash in self._emoji_index:
                        self._emoji_index.pop(e.hash, None)

            self._integrity_cursor = (start + processed) % max(1, len(self.emoji_objects))

            removed_count = await clean_unused_emojis(EMOJI_REGISTERED_DIR, self.emoji_objects, removed_count)

            if removed_count > 0:
                logger.info(f"[清理] 已清理 {removed_count} 个失效/文件丢失的表情包记录")
                logger.info(f"[统计] 清理前记录数: {total_count} | 清理后有效记录数: {len(self.emoji_objects)}")
            else:
                logger.info(f"[检查] 已检查 {total_count} 个表情包记录，全部完好")

        except Exception as e:
            logger.error(f"[错误] 检查表情包完整性失败: {e!s}")
            logger.error(traceback.format_exc())

    async def start_periodic_check_register(self) -> None:
        """定期检查表情包完整性和数量"""
        if global_config is None:
            raise RuntimeError("Global config is not initialized")
        await self.get_all_emoji_from_db()
        while True:
            # logger.info("[扫描] 开始检查表情包完整性...")
            await self.check_emoji_file_integrity()
            await clear_temp_emoji()
            logger.info("[扫描] 开始扫描新表情包...")

            # 检查表情包目录是否存在
            if not await asyncio.to_thread(os.path.exists, EMOJI_DIR):
                logger.warning(f"[警告] 表情包目录不存在: {EMOJI_DIR}")
                await asyncio.to_thread(os.makedirs, EMOJI_DIR, True)
                logger.info(f"[创建] 已创建表情包目录: {EMOJI_DIR}")
                await asyncio.sleep(global_config.emoji.check_interval * 60)
                continue

            image_files, is_empty = await list_image_files(EMOJI_DIR)
            if is_empty:
                logger.warning(f"[警告] 表情包目录为空: {EMOJI_DIR}")
                await asyncio.sleep(global_config.emoji.check_interval * 60)
                continue

            if not image_files:
                await asyncio.sleep(global_config.emoji.check_interval * 60)
                continue

            # 无论steal_emoji是否开启，都检查emoji文件夹以支持手动注册
            # 只有在需要腾出空间或填充表情库时，才真正执行注册
            if (self.emoji_num > self.emoji_num_max and global_config.emoji.do_replace) or (
                self.emoji_num < self.emoji_num_max
            ):
                try:
                    for filename in image_files:
                        # 尝试注册表情包
                        success = await self.register_emoji_by_filename(filename)
                        if success:
                            # 注册成功则跳出循环，等待下一个检查周期
                            break

                        # 注册失败则删除对应文件
                        file_path = os.path.join(EMOJI_DIR, filename)
                        await asyncio.to_thread(os.remove, file_path)
                        logger.warning(f"[清理] 删除注册失败的表情包文件: {filename}")
                        await asyncio.sleep(0)
                except Exception as e:
                    logger.error(f"[错误] 扫描表情包目录失败: {e!s}")

            await asyncio.sleep(global_config.emoji.check_interval * 60)

    async def get_all_emoji_from_db(self) -> None:
        """获取所有表情包并初始化为MaiEmoji类对象，更新 self.emoji_objects"""
        try:
            # 🔧 使用 QueryBuilder 以启用数据库缓存
            from src.common.database.api.query import QueryBuilder

            logger.debug("[数据库] 开始加载所有表情包记录 ...")

            emoji_instances = await QueryBuilder(Emoji).all()
            emoji_objects, load_errors = _to_emoji_objects(emoji_instances)

            # 更新内存中的列表和数量
            self.emoji_objects = emoji_objects
            self.emoji_num = len(emoji_objects)
            self._emoji_index = {e.hash: e for e in emoji_objects if getattr(e, "hash", None)}

            logger.info(f"[数据库] 加载完成: 共加载 {self.emoji_num} 个表情包记录。")
            if load_errors > 0:
                logger.warning(f"[数据库] 加载过程中出现 {load_errors} 个错误。")

        except Exception as e:
            logger.error(f"[错误] 从数据库加载所有表情包对象失败: {e!s}")
            self.emoji_objects = []  # 加载失败则清空列表
            self.emoji_num = 0

    async def get_emoji_from_db(self, emoji_hash: str | None = None) -> list["MaiEmoji"]:
        """获取指定哈希值的表情包并初始化为MaiEmoji类对象列表 (主要用于调试或特定查找)

        参数:
            emoji_hash: 可选，如果提供则只返回指定哈希值的表情包

        返回:
            list[MaiEmoji]: 表情包对象列表
        """
        try:
            # 使用CRUD进行查询
            crud = CRUDBase(Emoji)

            if emoji_hash:
                # 查询特定hash的表情包
                emoji_record = await crud.get_by(emoji_hash=emoji_hash)
                emoji_instances = [emoji_record] if emoji_record else []
            else:
                logger.warning(
                    "[查询] 未提供 hash，将尝试加载所有表情包，建议使用 get_all_emoji_from_db 更新管理器状态。"
                )
                # 查询所有表情包
                from src.common.database.api.query import QueryBuilder
                query = QueryBuilder(Emoji)
                emoji_instances = await query.all()

            emoji_objects, load_errors = _to_emoji_objects(emoji_instances)

            if load_errors > 0:
                logger.warning(f"[查询] 加载过程中出现 {load_errors} 个错误。")
            return emoji_objects

        except Exception as e:
            logger.error(f"[错误] 从数据库获取表情包对象失败: {e!s}")
            return []

    async def get_emoji_from_manager(self, emoji_hash: str) -> Optional["MaiEmoji"]:
        # sourcery skip: use-next
        """从内存中的 emoji_objects 列表获取表情包

        参数:
            emoji_hash: 要查找的表情包哈希值
        返回:
            MaiEmoji 或 None: 如果找到则返回 MaiEmoji 对象，否则返回 None
        """
        emoji = self._emoji_index.get(emoji_hash)
        if emoji and not emoji.is_deleted:
            return emoji

        for item in self.emoji_objects:
            if not item.is_deleted and item.hash == emoji_hash:
                self._emoji_index[emoji_hash] = item
                return item
        return None

    @cached(ttl=1800, key_prefix="emoji_tag")  # 缓存30分钟
    async def get_emoji_tag_by_hash(self, emoji_hash: str) -> str | None:
        """根据哈希值获取已注册表情包的描述（带30分钟缓存）

        Args:
            emoji_hash: 表情包的哈希值

        Returns:
            Optional[str]: 表情包描述，如果未找到则返回None
        """
        try:
            # 先从内存中查找
            emoji = await self.get_emoji_from_manager(emoji_hash)
            if emoji and emoji.emotion:
                logger.debug(f"[缓存命中] 从内存获取表情包描述: {emoji.emotion}...")
                return ",".join(emoji.emotion)

            # 如果内存中没有，从数据库查找
            try:
                emoji_record = await self.get_emoji_from_db(emoji_hash)
                if emoji_record and emoji_record[0].emotion:
                    emotion_str = ",".join(emoji_record[0].emotion)
                    logger.debug(f"[缓存命中] 从数据库获取表情包描述: {emotion_str[:50]}...")
                    return emotion_str
            except Exception as e:
                logger.error(f"从数据库查询表情包描述时出错: {e}")

            return None

        except Exception as e:
            logger.error(f"获取表情包描述失败 (Hash: {emoji_hash}): {e!s}")
            return None

    @cached(ttl=1800, key_prefix="emoji_description")  # 缓存30分钟
    async def get_emoji_description_by_hash(self, emoji_hash: str) -> str | None:
        """根据哈希值获取已注册表情包的描述（带30分钟缓存）

        Args:
            emoji_hash: 表情包的哈希值

        Returns:
            Optional[str]: 表情包描述，如果未找到则返回None
        """
        try:
            # 先从内存中查找
            emoji = await self.get_emoji_from_manager(emoji_hash)
            if emoji and emoji.description:
                logger.debug(f"[缓存命中] 从内存获取表情包描述: {emoji.description[:50]}...")
                return emoji.description

            # 如果内存中没有，从数据库查找（使用 QueryBuilder 启用数据库缓存）
            try:
                from src.common.database.api.query import QueryBuilder

                emoji_record = cast(Emoji | None, await QueryBuilder(Emoji).filter(emoji_hash=emoji_hash).first())
                if emoji_record and emoji_record.description:
                    logger.debug(f"[缓存命中] 从数据库获取表情包描述: {emoji_record.description[:50]}...")
                    return emoji_record.description
            except Exception as e:
                logger.error(f"从数据库查询表情包描述时出错: {e}")

            return None

        except Exception as e:
            logger.error(f"获取表情包描述失败 (Hash: {emoji_hash}): {e!s}")
            return None

    async def delete_emoji(self, emoji_hash: str) -> bool:
        """根据哈希值删除表情包

        Args:
            emoji_hash: 表情包的哈希值

        Returns:
            bool: 是否成功删除
        """
        try:
            # 从emoji_objects中查找表情包对象
            emoji = await self.get_emoji_from_manager(emoji_hash)

            if not emoji:
                logger.warning(f"[警告] 未找到哈希值为 {emoji_hash} 的表情包")
                return False

            # 使用MaiEmoji对象的delete方法删除表情包
            success = await emoji.delete()

            if success:
                # 从emoji_objects列表中移除该对象
                self.emoji_objects = [e for e in self.emoji_objects if e.hash != emoji_hash]
                self._emoji_index.pop(emoji_hash, None)
                # 更新计数
                self.emoji_num -= 1
                logger.info(f"[统计] 当前表情包数量: {self.emoji_num}")

                return True
            else:
                logger.error(f"[错误] 删除表情包失败: {emoji_hash}")
                return False

        except Exception as e:
            logger.error(f"[错误] 删除表情包失败: {e!s}")
            logger.error(traceback.format_exc())
            return False

    async def replace_a_emoji(self, new_emoji: "MaiEmoji") -> bool:
        # sourcery skip: use-getitem-for-re-match-groups
        """替换一个表情包

        Args:
            new_emoji: 新表情包对象

        Returns:
            bool: 是否成功替换表情包
        """
        try:
            # 获取所有表情包对象
            emoji_objects = self.emoji_objects
            # 计算每个表情包的选择概率
            probabilities = [1 / (emoji.usage_count + 1) for emoji in emoji_objects]
            # 归一化概率，确保总和为1
            total_probability = sum(probabilities)
            normalized_probabilities = [p / total_probability for p in probabilities]

            # 使用概率分布选择最多20个表情包
            selected_emojis = random.choices(
                emoji_objects, weights=normalized_probabilities, k=min(MAX_EMOJI_FOR_PROMPT, len(emoji_objects))
            )

            # 将表情包信息转换为可读的字符串
            emoji_info_list = _emoji_objects_to_readable_list(selected_emojis)

            if global_config is None:
                raise RuntimeError("Global config is not initialized")

            # 构建提示词
            prompt = (
                f"{global_config.bot.nickname}的表情包存储已满({self.emoji_num}/{self.emoji_num_max})，"
                f"需要决定是否删除一个旧表情包来为新表情包腾出空间。\n\n"
                f"新表情包信息：\n"
                f"描述: {new_emoji.description}\n\n"
                f"现有表情包列表：\n" + "\n".join(emoji_info_list) + "\n\n"
                "请决定：\n"
                "1. 是否要删除某个现有表情包来为新表情包腾出空间？\n"
                "2. 如果要删除，应该删除哪一个(给出编号)？\n"
                "请只回答：'不删除'或'删除编号X'(X为表情包编号)。"
            )

            # 调用大模型进行决策
            decision, _ = await self.llm_emotion_judge.generate_response_async(prompt, temperature=0.8, max_tokens=600)
            logger.info(f"[决策] 结果: {decision}")

            # 解析决策结果
            if "不删除" in decision:
                logger.info("[决策] 不删除任何表情包")
                return False

            if match := re.search(r"删除编号(\d+)", decision):
                emoji_index = int(match.group(1)) - 1  # 转换为0-based索引

                # 检查索引是否有效
                if 0 <= emoji_index < len(selected_emojis):
                    emoji_to_delete = selected_emojis[emoji_index]

                    # 删除选定的表情包
                    logger.info(f"[决策] 删除表情包: {emoji_to_delete.description}")
                    delete_success = await self.delete_emoji(emoji_to_delete.hash)

                    if delete_success:
                        # 修复：等待异步注册完成
                        register_success = await new_emoji.register_to_db()
                        if register_success:
                            self.emoji_objects.append(new_emoji)
                            self._emoji_index[new_emoji.hash] = new_emoji
                            self.emoji_num += 1
                            logger.info(f"[成功] 注册: {new_emoji.filename}")
                            return True
                        else:
                            logger.error(f"[错误] 注册表情包到数据库失败: {new_emoji.filename}")
                            return False
                    else:
                        logger.error("[错误] 删除表情包失败，无法完成替换")
                        return False
                else:
                    logger.error(f"[错误] 无效的表情包编号: {emoji_index + 1}")
            else:
                logger.error(f"[错误] 无法从决策中提取表情包编号: {decision}")

            return False

        except Exception as e:
            logger.error(f"[错误] 替换表情包失败: {e!s}")
            logger.error(traceback.format_exc())
            return False

    async def build_emoji_description(self, image_base64: str) -> tuple[str, list[str]]:
        """
        获取表情包的详细描述和情感关键词列表。

        该函数首先使用VLM（视觉语言模型）对图片进行深入分析，生成一份包含文化、Meme内涵的详细描述。
        然后，它会调用另一个LLM，基于这份详细描述，提炼出几个核心的、简洁的情感关键词。
        最终返回详细描述和关键词列表，为后续的表情包选择提供丰富且精准的信息。

        Args:
            image_base64 (str): 图片的Base64编码字符串。

        Returns:
            Tuple[str, List[str]]: 返回一个元组，第一个元素是详细描述，第二个元素是情感关键词列表。
                                   如果处理失败，则返回空的描述和列表。
        """
        if global_config is None:
            raise RuntimeError("Global config is not initialized")
        try:
            # 1. 解码图片，计算哈希值，并获取格式
            if isinstance(image_base64, str):
                image_base64 = image_base64.encode("ascii", errors="ignore").decode("ascii")
            image_bytes = base64.b64decode(image_base64)
            image_hash = hashlib.md5(image_bytes).hexdigest()
            image_format = (Image.open(io.BytesIO(image_bytes)).format or "jpeg").lower()

            # 2. 检查数据库中是否已存在该表情包的描述，实现复用（使用 QueryBuilder 启用数据库缓存）
            existing_description = None
            try:
                from src.common.database.api.query import QueryBuilder

                existing_image = cast(Images | None, await QueryBuilder(Images).filter(emoji_hash=image_hash, type="emoji").first())
                if existing_image and existing_image.description:
                    existing_description = existing_image.description
                    logger.info(f"[复用描述] 找到已有详细描述: {existing_description[:50]}...")
            except Exception as e:
                logger.debug(f"查询已有表情包描述时出错: {e}")

            # 3. 如果没有现有描述，则调用VLM生成新的详细描述
            # 3. 如果有现有描述，则复用或解析；否则调用VLM生成新的统一描述
            if existing_description:
                # 兼容旧格式的 final_description，尝试从中解析出各个部分
                logger.info("[优化] 复用已有的描述，跳过VLM调用")
                description_match = re.search(r"Desc: (.*)", existing_description, re.DOTALL)
                keywords_match = re.search(r"Keywords: \[(.*?)\]", existing_description)
                refined_match = re.search(r"^(.*?) Keywords:", existing_description, re.DOTALL)

                description = description_match.group(1).strip() if description_match else existing_description
                emotions_text = keywords_match.group(1) if keywords_match else ""
                emotions = [e.strip() for e in emotions_text.split(",") if e.strip()]
                refined_description = refined_match.group(1).strip() if refined_match else ""
                final_description = existing_description
            else:
                logger.info("[VLM分析] 开始为新表情包生成统一描述")
                description, emotions, refined_description, is_compliant = "", [], "", False

                prompt = f"""这是一个表情包。请你作为一位互联网"梗"学家和情感分析师，对这个表情包进行全面分析，并以JSON格式返回你的分析结果。
你的分析需要包含以下四个部分：
1.  **detailed_description**: 对图片的详尽描述（不超过250字）。请遵循以下结构：
    -   概括图片主题和氛围。
    -   详细描述核心元素，宽泛描述人物外观特征（如发型、服装、颜色等），无需识别具体角色身份或出处。
    -   描述传达的核心情绪或梗。
    -   准确转述图中文字。
    -   特别注意识别网络文化特殊含义（如"滑稽"表情）。
2.  **keywords**: 提炼5到8个核心关键词或短语（数组形式），应包含：核心文字、表情动作、情绪氛围、主体或构图特点。
3.  **refined_sentence**: 生成一句自然的精炼描述，应包含：人物外观特征、核心文字，并体现核心情绪。
4.  **is_compliant**: 根据以下标准判断是否合规（布尔值true/false）：
    -   主题符合："{global_config.emoji.filtration_prompt}"。
    -   内容健康，无不良元素。
    -   必须是表情包，非普通截图。
    -   图中文字不超过5个。
请确保你的最终输出是严格的JSON对象，不要添加任何额外解释或文本。
输出格式:
```json
{{
  "detailed_description": "",
  "keywords": [],
  "refined_sentence": "",
  "is_compliant": true
}}
```
"""

                image_data_for_vlm, image_format_for_vlm = image_base64, image_format
                if image_format in ["gif", "GIF"]:
                    # 使用 asyncio.to_thread 将耗时的 GIF 处理移至线程池
                    image_base64_frames = await asyncio.to_thread(get_image_manager().transform_gif, image_base64)
                    if not image_base64_frames:
                        raise RuntimeError("GIF表情包转换失败")
                    image_data_for_vlm, image_format_for_vlm = image_base64_frames, "jpeg"
                    prompt = "这是一个GIF动图表情包的关键帧。" + prompt

                for i in range(3):
                    try:
                        logger.info(f"[VLM调用] 正在为表情包生成统一描述 (第 {i+1}/3 次)...")
                        vlm_response_str, _ = await self.vlm.generate_response_for_image(
                            prompt, image_data_for_vlm, image_format_for_vlm, temperature=0.3, max_tokens=800
                        )
                        if not vlm_response_str:
                            continue

                        vlm_response_json = self._parse_json_response(vlm_response_str)
                        if not vlm_response_json:
                            logger.warning("[VLM分析] 无法解析VLM响应为JSON")
                            continue
                        description = vlm_response_json.get("detailed_description", "")
                        emotions = vlm_response_json.get("keywords", [])
                        refined_description = vlm_response_json.get("refined_sentence", "")
                        is_compliant = vlm_response_json.get("is_compliant", False)
                        if description and emotions and refined_description:
                            logger.info("[VLM分析] 成功解析VLM返回的JSON数据。")
                            break
                        logger.warning("[VLM分析] VLM返回的JSON数据不完整或格式错误，准备重试。")
                    except (json.JSONDecodeError, AttributeError) as e:
                        logger.error(f"VLM JSON解析失败 (第 {i+1}/3 次): {e}")
                    except Exception as e:
                        # 简化日志：只显示错误类型和简短消息
                        error_brief = f"{type(e).__name__}: {str(e)[:80]}"
                        logger.error(f"VLM调用失败 (第 {i+1}/3 次): {error_brief}")

                    description, emotions, refined_description = "", [], ""  # Reset for retry
                    if i < 2:
                        await asyncio.sleep(1)

                if not description or not emotions or not refined_description:
                    logger.warning("VLM未能生成有效的统一描述，中止处理。")
                    return "", []

                if global_config.emoji.content_filtration and not is_compliant:
                    logger.warning(f"表情包审核未通过，内容: {description[:50]}...")
                    return "", []

                final_description = f"{refined_description} Keywords: [{','.join(emotions)}] Desc: {description}"

            logger.info(f"[注册分析] VLM描述: {description}")
            logger.info(f"[注册分析] 提炼出的情感标签: {emotions}")
            logger.info(f"[注册分析] 精炼后的自然语言描述: {refined_description}")
            return final_description, emotions

        except Exception as e:
            logger.error(f"构建表情包描述时发生严重错误: {e!s}")
            logger.error(traceback.format_exc())
            return "", []

    async def register_emoji_by_filename(self, filename: str) -> bool:
        """读取指定文件名的表情包图片，分析并注册到数据库

        Args:
            filename: 表情包文件名，必须位于EMOJI_DIR目录下

        Returns:
            bool: 注册是否成功
        """
        file_full_path = os.path.join(EMOJI_DIR, filename)
        if not await asyncio.to_thread(os.path.exists, file_full_path):
            logger.error(f"[注册失败] 文件不存在: {file_full_path}")
            return False

        try:
            # 1. 创建 MaiEmoji 实例并初始化哈希和格式
            new_emoji = MaiEmoji(full_path=file_full_path)
            init_result = await new_emoji.initialize_hash_format()
            if init_result is None or new_emoji.is_deleted:  # 初始化失败或文件读取错误
                logger.error(f"[注册失败] 初始化哈希和格式失败: {filename}")
                # 是否需要删除源文件？看业务需求，暂时不删
                return False

            # 2. 检查哈希是否已存在 (在内存中检查)
            if await self.get_emoji_from_manager(new_emoji.hash):
                logger.warning(f"[注册跳过] 表情包已存在 (Hash: {new_emoji.hash}): {filename}")
                # 删除重复的源文件
                try:
                    await asyncio.to_thread(os.remove, file_full_path)
                    logger.info(f"[清理] 删除重复的待注册文件: {filename}")
                except Exception as e:
                    logger.error(f"[错误] 删除重复文件失败: {e!s}")
                return False  # 返回 False 表示未注册新表情

            # 3. 构建描述和情感
            try:
                emoji_base64 = image_path_to_base64(file_full_path)
                if emoji_base64 is None:  # 再次检查读取
                    logger.error(f"[注册失败] 无法读取图片以生成描述: {filename}")
                    return False

                # 等待描述生成完成
                description, emotions = await self.build_emoji_description(emoji_base64)

                if not description:  # 检查描述是否成功生成或审核通过
                    logger.warning(f"[注册失败] 未能生成有效描述或审核未通过: {filename}")
                    # 删除未能生成描述的文件
                    try:
                        await asyncio.to_thread(os.remove, file_full_path)
                        logger.info(f"[清理] 删除描述生成失败的文件: {filename}")
                    except Exception as e:
                        logger.error(f"[错误] 删除描述生成失败文件时出错: {e!s}")
                    return False

                new_emoji.description = description
                new_emoji.emotion = emotions
            except Exception as build_desc_error:
                logger.error(f"[注册失败] 生成描述/情感时出错 ({filename}): {build_desc_error}")
                # 同样考虑删除文件
                try:
                    await asyncio.to_thread(os.remove, file_full_path)
                    logger.info(f"[清理] 删除描述生成异常的文件: {filename}")
                except Exception as e:
                    logger.error(f"[错误] 删除描述生成异常文件时出错: {e!s}")
                return False

            # 4. 检查容量并决定是否替换或直接注册
            if self.emoji_num >= self.emoji_num_max:
                logger.warning(f"表情包数量已达到上限({self.emoji_num}/{self.emoji_num_max})，尝试替换...")
                replaced = await self.replace_a_emoji(new_emoji)
                if not replaced:
                    logger.error("[注册失败] 替换表情包失败，无法完成注册")
                    # 替换失败，删除新表情包文件
                    try:
                        await asyncio.to_thread(os.remove, file_full_path)  # new_emoji 的 full_path 此时还是源路径
                        logger.info(f"[清理] 删除替换失败的新表情文件: {filename}")
                    except Exception as e:
                        logger.error(f"[错误] 删除替换失败文件时出错: {e!s}")
                    return False
                # 替换成功时，replace_a_emoji 内部已处理 new_emoji 的注册和添加到列表
                return True
            else:
                # 直接注册
                register_success = await new_emoji.register_to_db()  # 此方法会移动文件并更新 DB
                if register_success:
                    # 注册成功后，添加到内存列表
                    self.emoji_objects.append(new_emoji)
                    self._emoji_index[new_emoji.hash] = new_emoji
                    self.emoji_num += 1
                    logger.info(f"[成功] 注册新表情包: {filename} (当前: {self.emoji_num}/{self.emoji_num_max})")
                    return True
                else:
                    logger.error(f"[注册失败] 保存表情包到数据库/移动文件失败: {filename}")
                    # register_to_db 失败时，内部会尝试清理移动后的文件，源文件可能还在
                    # 是否需要删除源文件？
                    if await asyncio.to_thread(os.path.exists, file_full_path):
                        try:
                            await asyncio.to_thread(os.remove, file_full_path)
                            logger.info(f"[清理] 删除注册失败的源文件: {filename}")
                        except Exception as e:
                            logger.error(f"[错误] 删除注册失败源文件时出错: {e!s}")
                    return False

        except Exception as e:
            logger.error(f"[错误] 注册表情包时发生未预期错误 ({filename}): {e!s}")
            logger.error(traceback.format_exc())
            # 尝试删除源文件以避免循环处理
            if await asyncio.to_thread(os.path.exists, file_full_path):
                try:
                    await asyncio.to_thread(os.remove, file_full_path)
                    logger.info(f"[清理] 删除处理异常的源文件: {filename}")
                except Exception as remove_error:
                    logger.error(f"[错误] 删除异常处理文件时出错: {remove_error}")
            return False

    @classmethod
    def _parse_json_response(cls, response: str) -> dict[str, Any] | None:
        """解析 LLM 的 JSON 响应"""
        try:
            # 尝试提取 JSON 代码块
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析
                json_str = response.strip()

            # 移除可能的注释
            json_str = re.sub(r"//.*", "", json_str)
            json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)

            data = json_repair.loads(json_str)
            return data

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}, 响应: {response[:200]}")
            return None


emoji_manager = None


def get_emoji_manager():
    global emoji_manager
    if emoji_manager is None:
        emoji_manager = EmojiManager()
    return emoji_manager
