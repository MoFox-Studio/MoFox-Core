import hashlib
import os
import time
from datetime import datetime
from typing import Any

import aiofiles
import orjson
from sqlalchemy import select

from src.chat.message_receive.chat_stream import get_chat_manager
from src.chat.utils.chat_message_builder import build_anonymous_messages, get_raw_msg_by_timestamp_with_chat_inclusive
from src.common.database.api.crud import CRUDBase
from src.common.database.compatibility import get_db_session
from src.common.database.core.models import Expression
from src.common.database.utils.decorators import cached
from src.common.logger import get_logger
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest

# 导入 StyleLearner 管理器
from .style_learner import style_learner_manager

MAX_EXPRESSION_COUNT = 300
DECAY_DAYS = 30  # 30天衰减到0.01
DECAY_MIN = 0.01  # 最小衰减值

logger = get_logger("expressor")


def format_create_date(timestamp: float) -> str:
    """
    将时间戳格式化为可读的日期字符串
    """
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return "未知时间"


def init_prompt() -> None:
    from src.chat.utils.prompt import Prompt  # noqa: F811 - 延迟导入以打破循环依赖

    learn_style_prompt = """
{chat_str}

请从上面这段群聊中概括除了人名为"SELF"之外的人的语言风格
1. 只考虑文字，不要考虑表情包和图片
2. 不要涉及具体的人名，只考虑语言风格
3. 语言风格包含特殊内容和情感
4. 思考有没有特殊的梗，一并总结成语言风格
5. 例子仅供参考，请严格根据群聊内容总结!!!

**重要：必须严格按照以下格式输出，每行一条规律：**
当"xxx"时，使用"xxx"

格式说明：
- 必须以"当"开头
- 场景描述用双引号包裹，不超过20个字
- 必须包含"使用"或"可以"
- 表达风格用双引号包裹，不超过20个字
- 每条规律独占一行

例如：
当"对某件事表示十分惊叹，有些意外"时，使用"我嘞个xxxx"
当"表示讽刺的赞同，不想讲道理"时，使用"对对对"
当"想说明某个具体的事实观点，但懒得明说，或者不便明说，或表达一种默契"时，使用"懂的都懂"
当"涉及游戏相关时，表示意外的夸赞，略带戏谑意味"时，使用"这么强！"

注意：
1. 不要总结你自己（SELF）的发言
2. 如果聊天内容中没有明显的特殊风格，请只输出1-2条最明显的特点
3. 不要输出其他解释性文字，只输出符合格式的规律

现在请你概括：
"""
    Prompt(learn_style_prompt, "learn_style_prompt")

    learn_grammar_prompt = """
{chat_str}

请从上面这段群聊中概括除了人名为"SELF"之外的人的语法和句法特点，只考虑纯文字，不要考虑表情包和图片
1.不要总结【图片】，【动画表情】，[图片]，[动画表情]，不总结 表情符号 at @ 回复 和[回复]
2.不要涉及具体的人名，只考虑语法和句法特点,
3.语法和句法特点要包括，句子长短（具体字数），有何种语病，如何拆分句子。
4. 例子仅供参考，请严格根据群聊内容总结!!!

**重要：必须严格按照以下格式输出，每行一条规律：**
当"xxx"时，使用"xxx"

格式说明：
- 必须以"当"开头
- 场景描述用双引号包裹
- 必须包含"使用"或"可以"
- 句法特点用双引号包裹
- 每条规律独占一行

例如：
当"表达观点较复杂"时，使用"省略主语(3-6个字)"的句法
当"不用详细说明的一般表达"时，使用"非常简洁的句子"的句法
当"需要单纯简单的确认"时，使用"单字或几个字的肯定(1-2个字)"的句法

注意：
1. 不要总结你自己（SELF）的发言
2. 如果聊天内容中没有明显的句法特点，请只输出1-2条最明显的特点
3. 不要输出其他解释性文字，只输出符合格式的规律

现在请你概括：
"""
    Prompt(learn_grammar_prompt, "learn_grammar_prompt")


class ExpressionLearner:
    def __init__(self, chat_id: str) -> None:
        if model_config is None:
            raise RuntimeError("Model config is not initialized")
        self.express_learn_model: LLMRequest = LLMRequest(
            model_set=model_config.model_task_config.replyer, request_type="expressor.learner"
        )
        self.chat_id = chat_id
        self.chat_name = chat_id  # 初始化时使用chat_id，稍后异步更新

        # 维护每个chat的上次学习时间
        self.last_learning_time: float = time.time()

        # 学习参数
        self.min_messages_for_learning = 25  # 触发学习所需的最少消息数
        self.min_learning_interval = 300  # 最短学习时间间隔（秒）
        self._chat_name_initialized = False

    @staticmethod
    def _parse_stream_config_to_chat_id(stream_config_str: str) -> str | None:
        """解析'platform:id:type'为chat_id（与get_stream_id一致）"""
        try:
            parts = stream_config_str.split(":")
            if len(parts) != 3:
                return None
            platform = parts[0]
            id_str = parts[1]
            stream_type = parts[2]
            is_group = stream_type == "group"
            if is_group:
                components = [platform, str(id_str)]
            else:
                components = [platform, str(id_str), "private"]
            key = "_".join(components)
            return hashlib.md5(key.encode()).hexdigest()
        except Exception:
            return None

    def get_related_chat_ids(self) -> list[str]:
        """根据expression.rules配置，获取与当前chat_id相关的所有chat_id（包括自身）

        用于共享组功能：同一共享组内的聊天流可以共享学习到的表达方式
        """
        if global_config is None:
            return [self.chat_id]
        rules = global_config.expression.rules
        current_group = None

        # 找到当前chat_id所在的组
        for rule in rules:
            if rule.chat_stream_id and self._parse_stream_config_to_chat_id(rule.chat_stream_id) == self.chat_id:
                current_group = rule.group
                break

        # 始终包含当前 chat_id（确保至少能查到自己的数据）
        related_chat_ids = [self.chat_id]

        if current_group:
            # 找出同一组的所有chat_id
            for rule in rules:
                if rule.group == current_group and rule.chat_stream_id:
                    if chat_id_candidate := self._parse_stream_config_to_chat_id(rule.chat_stream_id):
                        if chat_id_candidate not in related_chat_ids:
                            related_chat_ids.append(chat_id_candidate)

        return related_chat_ids

    async def _initialize_chat_name(self):
        """异步初始化chat_name"""
        if not self._chat_name_initialized:
            stream_name = await get_chat_manager().get_stream_name(self.chat_id)
            self.chat_name = stream_name or self.chat_id
            self._chat_name_initialized = True

    async def cleanup_expired_expressions(self, expiration_days: int | None = None) -> int:
        """
        清理过期的表达方式

        Args:
            expiration_days: 过期天数，超过此天数未激活的表达方式将被删除（不指定则从配置读取）

        Returns:
            int: 删除的表达方式数量
        """
        # 从配置读取过期天数
        if expiration_days is None:
            if global_config is None:
                expiration_days = 30  # Default value if config is missing
            else:
                expiration_days = global_config.expression.expiration_days

        current_time = time.time()
        expiration_threshold = current_time - (expiration_days * 24 * 3600)

        try:
            deleted_count = 0
            async with get_db_session() as session:
                # 查询过期的表达方式（只清理当前chat_id的）
                query = await session.execute(
                    select(Expression).where(
                        (Expression.chat_id == self.chat_id)
                        & (Expression.last_active_time < expiration_threshold)
                    )
                )
                expired_expressions = list(query.scalars())

                if expired_expressions:
                    for expr in expired_expressions:
                        await session.delete(expr)
                        deleted_count += 1

                    await session.commit()
                    logger.info(f"清理了 {deleted_count} 个过期表达方式（超过 {expiration_days} 天未使用）")

                    # 清除缓存
                    from src.common.database.optimization.cache_manager import get_cache
                    from src.common.database.utils.decorators import generate_cache_key
                    cache = await get_cache()
                    await cache.delete(generate_cache_key("chat_expressions", self.chat_id))
                else:
                    logger.debug(f"没有发现过期的表达方式（阈值：{expiration_days} 天）")

            return deleted_count
        except Exception as e:
            logger.error(f"清理过期表达方式失败: {e}")
            return 0

    def can_learn_for_chat(self) -> bool:
        """
        检查指定聊天流是否允许学习表达

        Args:
            chat_id: 聊天流ID

        Returns:
            bool: 是否允许学习
        """
        try:
            if global_config is None:
                return False
            _use_expression, enable_learning, _ = global_config.expression.get_expression_config_for_chat(self.chat_id)
            return enable_learning
        except Exception as e:
            logger.error(f"检查学习权限失败: {e}")
            return False

    async def should_trigger_learning(self) -> bool:
        """
        检查是否应该触发学习

        Args:
            chat_id: 聊天流ID

        Returns:
            bool: 是否应该触发学习
        """
        current_time = time.time()

        # 获取该聊天流的学习强度
        try:
            if global_config is None:
                return False
            _use_expression, enable_learning, learning_intensity = (
                global_config.expression.get_expression_config_for_chat(self.chat_id)
            )
        except Exception as e:
            logger.error(f"获取聊天流 {self.chat_id} 的学习配置失败: {e}")
            return False

        # 检查是否允许学习
        if not enable_learning:
            return False

        # 根据学习强度计算最短学习时间间隔
        min_interval = self.min_learning_interval / learning_intensity

        # 检查时间间隔
        time_diff = current_time - self.last_learning_time
        if time_diff < min_interval:
            return False

        # 检查消息数量（只检查指定聊天流的消息，排除机器人自己的消息）
        recent_messages = await get_raw_msg_by_timestamp_with_chat_inclusive(
            chat_id=self.chat_id,
            timestamp_start=self.last_learning_time,
            timestamp_end=time.time(),
            filter_bot=True,  # 过滤掉机器人自己的消息
        )

        if not recent_messages or len(recent_messages) < self.min_messages_for_learning:
            return False

        return True

    async def trigger_learning_for_chat(self) -> bool:
        """
        为指定聊天流触发学习

        Args:
            chat_id: 聊天流ID

        Returns:
            bool: 是否成功触发学习
        """
        # 初始化chat_name
        await self._initialize_chat_name()

        if not await self.should_trigger_learning():
            return False

        try:
            logger.info(f"为聊天流 {self.chat_name} 触发表达学习")

            # 🔥 改进3：在学习前清理过期的表达方式
            await self.cleanup_expired_expressions()

            # 学习语言风格
            learnt_style = await self.learn_and_store(type="style", num=25)

            # 学习句法特点
            learnt_grammar = await self.learn_and_store(type="grammar", num=10)

            # 更新学习时间
            self.last_learning_time = time.time()

            if learnt_style or learnt_grammar:
                logger.info(f"聊天流 {self.chat_name} 表达学习完成")
                return True
            else:
                logger.warning(f"聊天流 {self.chat_name} 表达学习未获得有效结果")
                return False

        except Exception as e:
            logger.error(f"为聊天流 {self.chat_name} 触发学习失败: {e}")
            return False

    async def get_expression_by_chat_id(self) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
        """
        获取指定chat_id的style和grammar表达方式（带10分钟缓存）
        返回的每个表达方式字典中都包含了source_id, 用于后续的更新操作

        优化: 使用CRUD和缓存，减少数据库访问
        """
        # 使用静态方法以正确处理缓存键
        return await self._get_expressions_by_chat_id_cached(self.chat_id)

    @staticmethod
    @cached(ttl=600, key_prefix="chat_expressions")
    async def _get_expressions_by_chat_id_cached(chat_id: str) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
        """内部方法：从数据库获取表达方式（带缓存）
        
        🔥 优化：使用列表推导式和更高效的数据处理
        """
        learnt_style_expressions = []
        learnt_grammar_expressions = []

        # 使用CRUD查询
        crud = CRUDBase(Expression)
        all_expressions = await crud.get_multi(chat_id=chat_id, limit=10000)

        # 🔥 优化：使用列表推导式批量处理，减少循环开销
        for expr in all_expressions:
            # 确保create_date存在，如果不存在则使用last_active_time
            create_date = expr.create_date if expr.create_date is not None else expr.last_active_time

            expr_data = {
                "situation": expr.situation,
                "style": expr.style,
                "count": expr.count,
                "last_active_time": expr.last_active_time,
                "source_id": chat_id,
                "type": expr.type,
                "create_date": create_date,
            }

            # 根据类型分类（避免多次类型检查）
            if expr.type == "style":
                learnt_style_expressions.append(expr_data)
            elif expr.type == "grammar":
                learnt_grammar_expressions.append(expr_data)

        logger.debug(f"已加载 {len(learnt_style_expressions)} 个style和 {len(learnt_grammar_expressions)} 个grammar表达方式 (chat_id={chat_id})")
        return learnt_style_expressions, learnt_grammar_expressions

    async def _apply_global_decay_to_database(self, current_time: float) -> None:
        """
        对数据库中的所有表达方式应用全局衰减

        优化: 使用分批处理和原生 SQL 操作提升性能
        """
        try:
            BATCH_SIZE = 1000  # 分批处理，避免一次性加载过多数据
            updated_count = 0
            deleted_count = 0
            offset = 0

            while True:
                async with get_db_session() as session:
                    # 分批查询表达方式
                    batch_result = await session.execute(
                        select(Expression)
                        .order_by(Expression.id)
                        .limit(BATCH_SIZE)
                        .offset(offset)
                    )
                    batch_expressions = list(batch_result.scalars())

                    if not batch_expressions:
                        break  # 没有更多数据

                    # 批量处理当前批次
                    to_delete = []
                    for expr in batch_expressions:
                        # 计算时间差
                        time_diff_days = (current_time - expr.last_active_time) / (24 * 3600)

                        # 计算衰减值
                        decay_value = self.calculate_decay_factor(time_diff_days)
                        new_count = max(0.01, expr.count - decay_value)

                        if new_count <= 0.01:
                            # 标记删除
                            to_delete.append(expr)
                        else:
                            # 更新count
                            expr.count = new_count
                            updated_count += 1

                    # 批量删除
                    if to_delete:
                        for expr in to_delete:
                            await session.delete(expr)
                        deleted_count += len(to_delete)

                    # 提交当前批次
                    await session.commit()

                    # 如果批次不满，说明已经处理完所有数据
                    if len(batch_expressions) < BATCH_SIZE:
                        break

                    offset += BATCH_SIZE

            if updated_count > 0 or deleted_count > 0:
                logger.info(f"全局衰减完成：更新了 {updated_count} 个表达方式，删除了 {deleted_count} 个表达方式")

        except Exception as e:
            logger.error(f"数据库全局衰减失败: {e}")

    @staticmethod
    def calculate_decay_factor(time_diff_days: float) -> float:
        """
        计算衰减值
        当时间差为0天时，衰减值为0（最近活跃的不衰减）
        当时间差为7天时，衰减值为0.002（中等衰减）
        当时间差为30天或更长时，衰减值为0.01（高衰减）
        使用二次函数进行曲线插值
        """
        if time_diff_days <= 0:
            return 0.0  # 刚激活的表达式不衰减

        if time_diff_days >= DECAY_DAYS:
            return 0.01  # 长时间未活跃的表达式大幅衰减

        # 使用二次函数插值：在0-30天之间从0衰减到0.01
        # 使用简单的二次函数：y = a * x^2
        # 当x=30时，y=0.01，所以 a = 0.01 / (30^2) = 0.01 / 900
        a = 0.01 / (DECAY_DAYS**2)
        decay = a * (time_diff_days**2)

        return min(0.01, decay)

    async def learn_and_store(self, type: str, num: int = 10) -> None | list[Any] | list[tuple[str, str, str]]:
        # sourcery skip: use-join
        """
        学习并存储表达方式
        type: "style" or "grammar"
        """
        if type == "style":
            type_str = "语言风格"
        elif type == "grammar":
            type_str = "句法特点"
        else:
            raise ValueError(f"Invalid type: {type}")

        # 检查是否允许在此聊天流中学习（在函数最前面检查）
        if not self.can_learn_for_chat():
            logger.debug(f"聊天流 {self.chat_name} 不允许学习表达，跳过学习")
            return []

        res = await self.learn_expression(type, num)

        if res is None:
            return []
        learnt_expressions, chat_id = res

        chat_stream = await get_chat_manager().get_stream(chat_id)
        if chat_stream is None:
            group_name = f"聊天流 {chat_id}"
        elif chat_stream.group_info:
            group_name = chat_stream.group_info.group_name
        elif chat_stream.user_info and chat_stream.user_info.user_nickname:
            group_name = f"{chat_stream.user_info.user_nickname}的私聊"
        else:
            group_name = f"聊天流 {chat_id}"
        learnt_expressions_str = ""
        for _chat_id, situation, style in learnt_expressions:
            learnt_expressions_str += f"{situation}->{style}\n"
        logger.info(f"在 {group_name} 学习到{type_str}:\n{learnt_expressions_str}")

        if not learnt_expressions:
            logger.info(f"没有学习到{type_str}")
            return []

        # 按chat_id分组
        chat_dict: dict[str, list[dict[str, Any]]] = {}
        for chat_id, situation, style in learnt_expressions:
            if chat_id not in chat_dict:
                chat_dict[chat_id] = []
            chat_dict[chat_id].append({"situation": situation, "style": style})

        current_time = time.time()

        # 存储到数据库 Expression 表
        CRUDBase(Expression)
        for chat_id, expr_list in chat_dict.items():
            async with get_db_session() as session:
                # 🔥 优化：批量查询所有现有表达方式，避免N次数据库查询
                existing_exprs_result = await session.execute(
                    select(Expression).where(
                        (Expression.chat_id == chat_id)
                        & (Expression.type == type)
                    )
                )
                existing_exprs = list(existing_exprs_result.scalars())

                # 构建快速查找索引
                exact_match_map = {}  # (situation, style) -> Expression
                situation_map = {}    # situation -> Expression
                style_map = {}        # style -> Expression

                for expr in existing_exprs:
                    key = (expr.situation, expr.style)
                    exact_match_map[key] = expr
                    # 只保留第一个匹配（优先级：完全匹配 > 情景匹配 > 表达匹配）
                    if expr.situation not in situation_map:
                        situation_map[expr.situation] = expr
                    if expr.style not in style_map:
                        style_map[expr.style] = expr

                # 批量处理所有新表达方式
                for new_expr in expr_list:
                    situation = new_expr["situation"]
                    style_val = new_expr["style"]
                    exact_key = (situation, style_val)

                    # 优先处理完全匹配的情况
                    if exact_key in exact_match_map:
                        # 完全相同：增加count，更新时间
                        expr_obj = exact_match_map[exact_key]
                        expr_obj.count = expr_obj.count + 1
                        expr_obj.last_active_time = current_time
                        logger.debug(f"完全匹配：更新count {expr_obj.count}")
                    elif situation in situation_map:
                        # 相同情景，不同表达：覆盖旧的表达
                        same_situation_expr = situation_map[situation]
                        logger.info(f"相同情景覆盖：'{same_situation_expr.situation}' 的表达从 '{same_situation_expr.style}' 更新为 '{style_val}'")
                        # 更新映射
                        old_key = (same_situation_expr.situation, same_situation_expr.style)
                        exact_match_map.pop(old_key, None)
                        same_situation_expr.style = style_val
                        same_situation_expr.count = same_situation_expr.count + 1
                        same_situation_expr.last_active_time = current_time
                        # 更新新的完全匹配映射
                        exact_match_map[exact_key] = same_situation_expr
                    elif style_val in style_map:
                        # 相同表达，不同情景：覆盖旧的情景
                        same_style_expr = style_map[style_val]
                        logger.info(f"相同表达覆盖：'{same_style_expr.style}' 的情景从 '{same_style_expr.situation}' 更新为 '{situation}'")
                        # 更新映射
                        old_key = (same_style_expr.situation, same_style_expr.style)
                        exact_match_map.pop(old_key, None)
                        same_style_expr.situation = situation
                        same_style_expr.count = same_style_expr.count + 1
                        same_style_expr.last_active_time = current_time
                        # 更新新的完全匹配映射
                        exact_match_map[exact_key] = same_style_expr
                        situation_map[situation] = same_style_expr
                    else:
                        # 完全新的表达方式：创建新记录
                        new_expression = Expression(
                            situation=situation,
                            style=style_val,
                            count=1,
                            last_active_time=current_time,
                            chat_id=chat_id,
                            type=type,
                            create_date=current_time,
                        )
                        session.add(new_expression)
                        # 更新映射
                        exact_match_map[exact_key] = new_expression
                        situation_map[situation] = new_expression
                        style_map[style_val] = new_expression
                        logger.debug(f"新增表达方式：{situation} -> {style_val}")

                # 🔥 优化：限制最大数量 - 使用已加载的数据避免重复查询
                # existing_exprs 已包含该 chat_id 和 type 的所有表达方式
                all_current_exprs = list(exact_match_map.values())
                if len(all_current_exprs) > MAX_EXPRESSION_COUNT:
                    # 按 count 排序，删除 count 最小的多余表达方式
                    sorted_exprs = sorted(all_current_exprs, key=lambda e: e.count)
                    for expr in sorted_exprs[: len(all_current_exprs) - MAX_EXPRESSION_COUNT]:
                        await session.delete(expr)
                        # 从映射中移除
                        key = (expr.situation, expr.style)
                        exact_match_map.pop(key, None)
                    logger.debug(f"已删除 {len(all_current_exprs) - MAX_EXPRESSION_COUNT} 个低频表达方式")

                # 提交数据库更改
                await session.commit()

        # 🔥 优化：只在实际有更新时才清除缓存（移到外层，避免重复清除）
        if chat_dict:  # 只有当有数据更新时才清除缓存
            from src.common.database.optimization.cache_manager import get_cache
            from src.common.database.utils.decorators import generate_cache_key
            cache = await get_cache()

            # 获取共享组内所有 chat_id 并清除其缓存
            related_chat_ids = self.get_related_chat_ids()
            for related_id in related_chat_ids:
                await cache.delete(generate_cache_key("chat_expressions", related_id))
            if len(related_chat_ids) > 1:
                logger.debug(f"已清除共享组内 {len(related_chat_ids)} 个 chat_id 的表达方式缓存")

        # 🔥 训练 StyleLearner（支持共享组）
        # 只对 style 类型的表达方式进行训练（grammar 不需要训练到模型）
        if type == "style" and chat_dict:
            try:
                related_chat_ids = self.get_related_chat_ids()
                total_samples = sum(len(expr_list) for expr_list in chat_dict.values())
                logger.debug(f"开始训练 StyleLearner: 共享组包含 {len(related_chat_ids)} 个chat_id, 总样本数={total_samples}")

                # 为每个共享组内的 chat_id 训练其 StyleLearner
                for target_chat_id in related_chat_ids:
                    learner = style_learner_manager.get_learner(target_chat_id)

                    # 收集该 target_chat_id 对应的所有表达方式
                    # 如果是源 chat_id，使用 chat_dict 中的数据；否则也要训练（共享组特性）
                    total_success = 0
                    total_samples = 0

                    for source_chat_id, expr_list in chat_dict.items():
                        # 为每个学习到的表达方式训练模型
                        # 使用 situation 作为输入，style 作为目标
                        for expr in expr_list:
                            situation = expr["situation"]
                            style = expr["style"]

                            # 训练映射关系: situation -> style
                            if learner.learn_mapping(situation, style):
                                total_success += 1
                            total_samples += 1

                    # 保存模型
                    if total_samples > 0:
                        if learner.save(style_learner_manager.model_save_path):
                            logger.debug(f"StyleLearner 模型保存成功: {target_chat_id}")
                        else:
                            logger.error(f"StyleLearner 模型保存失败: {target_chat_id}")

                        if target_chat_id == self.chat_id:
                            # 只为当前 chat_id 记录详细日志
                            logger.info(
                                f"StyleLearner 训练完成: {total_success}/{total_samples} 成功, "
                                f"当前风格总数={len(learner.get_all_styles())}, "
                                f"总样本数={learner.learning_stats['total_samples']}"
                            )
                        else:
                            logger.debug(
                                f"StyleLearner 训练完成 (共享组成员 {target_chat_id}): {total_success}/{total_samples} 成功"
                            )

                if len(related_chat_ids) > 1:
                    logger.info(f"共享组内共 {len(related_chat_ids)} 个 StyleLearner 已同步训练")

            except Exception as e:
                logger.error(f"训练 StyleLearner 失败: {e}")

            return learnt_expressions
        return None

    async def learn_expression(self, type: str, num: int = 10) -> tuple[list[tuple[str, str, str]], str] | None:
        """从指定聊天流学习表达方式

        Args:
            type: "style" or "grammar"
        """
        if type == "style":
            type_str = "语言风格"
            prompt = "learn_style_prompt"
        elif type == "grammar":
            type_str = "句法特点"
            prompt = "learn_grammar_prompt"
        else:
            raise ValueError(f"Invalid type: {type}")

        current_time = time.time()

        # 获取上次学习时间，过滤掉机器人自己的消息和无意义消息
        random_msg: list[dict[str, Any]] | None = await get_raw_msg_by_timestamp_with_chat_inclusive(
            chat_id=self.chat_id,
            timestamp_start=self.last_learning_time,
            timestamp_end=current_time,
            limit=num,
            filter_bot=True,  # 过滤掉机器人自己的消息，防止学习自己的表达方式
            filter_meaningless=True,  # 🔥 过滤掉表情包、通知等无意义消息
        )

        # print(random_msg)
        if not random_msg or random_msg == []:
            return None
        # 转化成str
        chat_id: str = random_msg[0]["chat_id"]
        # random_msg_str: str = build_readable_messages(random_msg, timestamp_mode="normal")
        # 🔥 启用表达学习场景的过滤，过滤掉纯回复、纯@、纯图片等无意义内容
        random_msg_str: str = await build_anonymous_messages(random_msg, filter_for_learning=True)
        # print(f"random_msg_str:{random_msg_str}")

        # 🔥 检查过滤后是否还有足够的内容
        if not random_msg_str or len(random_msg_str.strip()) < 20:
            logger.debug(f"过滤后消息内容不足，跳过本次{type_str}学习")
            return None

        prompt: str = await global_prompt_manager.format_prompt(
            prompt,
            chat_str=random_msg_str,
        )

        logger.debug(f"学习{type_str}的prompt: {prompt}")

        try:
            response, _ = await self.express_learn_model.generate_response_async(prompt, temperature=0.3)
        except Exception as e:
            logger.error(f"学习{type_str}失败: {e}")
            return None

        if not response or not response.strip():
            logger.warning(f"LLM返回空响应，无法学习{type_str}")
            return None

        logger.debug(f"学习{type_str}的response: {response}")

        expressions: list[tuple[str, str, str]] = self.parse_expression_response(response, chat_id)

        if not expressions:
            logger.warning(f"从LLM响应中未能解析出任何{type_str}。请检查LLM输出格式是否正确。")
            logger.info(f"LLM完整响应:\n{response}")

        return expressions, chat_id

    @staticmethod
    def parse_expression_response(response: str, chat_id: str) -> list[tuple[str, str, str]]:
        """
        解析LLM返回的表达风格总结，每一行提取"当"和"使用"之间的内容，存储为(situation, style)元组
        支持多种引号格式："" 和 ""
        """
        expressions: list[tuple[str, str, str]] = []
        failed_lines = []

        for line_num, line in enumerate(response.splitlines(), 1):
            line = line.strip()
            if not line:
                continue

            # 替换中文引号为英文引号，便于统一处理
            line_normalized = line.replace('"', '"').replace('"', '"').replace("'", '"').replace("'", '"')

            # 查找"当"和下一个引号
            idx_when = line_normalized.find('当"')
            if idx_when == -1:
                # 尝试不带引号的格式: 当xxx时
                idx_when = line_normalized.find("当")
                if idx_when == -1:
                    failed_lines.append((line_num, line, "找不到'当'关键字"))
                    continue

                # 提取"当"和"时"之间的内容
                idx_shi = line_normalized.find("时", idx_when)
                if idx_shi == -1:
                    failed_lines.append((line_num, line, "找不到'时'关键字"))
                    continue
                situation = line_normalized[idx_when + 1:idx_shi].strip('"\'""')
                search_start = idx_shi
            else:
                idx_quote1 = idx_when + 1
                idx_quote2 = line_normalized.find('"', idx_quote1 + 1)
                if idx_quote2 == -1:
                    failed_lines.append((line_num, line, "situation部分引号不匹配"))
                    continue
                situation = line_normalized[idx_quote1 + 1 : idx_quote2]
                search_start = idx_quote2

            # 查找"使用"或"可以"
            idx_use = line_normalized.find('使用"', search_start)
            if idx_use == -1:
                idx_use = line_normalized.find('可以"', search_start)
                if idx_use == -1:
                    # 尝试不带引号的格式
                    idx_use = line_normalized.find("使用", search_start)
                    if idx_use == -1:
                        idx_use = line_normalized.find("可以", search_start)
                        if idx_use == -1:
                            failed_lines.append((line_num, line, "找不到'使用'或'可以'关键字"))
                            continue

                    # 提取剩余部分作为style
                    style = line_normalized[idx_use + 2:].strip('"\'""，。')
                    if not style:
                        failed_lines.append((line_num, line, "style部分为空"))
                        continue
                else:
                    idx_quote3 = idx_use + 2
                    idx_quote4 = line_normalized.find('"', idx_quote3 + 1)
                    if idx_quote4 == -1:
                        # 如果没有结束引号，取到行尾
                        style = line_normalized[idx_quote3 + 1:].strip('"\'""')
                    else:
                        style = line_normalized[idx_quote3 + 1 : idx_quote4]
            else:
                idx_quote3 = idx_use + 2
                idx_quote4 = line_normalized.find('"', idx_quote3 + 1)
                if idx_quote4 == -1:
                    # 如果没有结束引号，取到行尾
                    style = line_normalized[idx_quote3 + 1:].strip('"\'""')
                else:
                    style = line_normalized[idx_quote3 + 1 : idx_quote4]

            # 清理并验证
            situation = situation.strip()
            style = style.strip()

            if not situation or not style:
                failed_lines.append((line_num, line, f"situation或style为空: situation='{situation}', style='{style}'"))
                continue

            expressions.append((chat_id, situation, style))

        # 记录解析失败的行
        if failed_lines:
            logger.warning(f"解析表达方式时有 {len(failed_lines)} 行失败:")
            for line_num, line, reason in failed_lines[:5]:  # 只显示前5个
                logger.warning(f"  行{line_num}: {reason}")
                logger.debug(f"    原文: {line}")

        if not expressions:
            logger.warning(f"LLM返回了内容但无法解析任何表达方式。响应预览:\n{response[:500]}")
        else:
            logger.debug(f"成功解析 {len(expressions)} 个表达方式")
        return expressions


init_prompt()


class ExpressionLearnerManager:
    def __init__(self):
        self.expression_learners = {}

        self._ensure_expression_directories()

    async def get_expression_learner(self, chat_id: str) -> ExpressionLearner:
        await self._auto_migrate_json_to_db()
        await self._migrate_old_data_create_date()

        if chat_id not in self.expression_learners:
            self.expression_learners[chat_id] = ExpressionLearner(chat_id)
        return self.expression_learners[chat_id]

    @staticmethod
    def _ensure_expression_directories():
        """
        确保表达方式相关的目录结构存在
        """
        base_dir = os.path.join("data", "expression")
        directories_to_create = [
            base_dir,
            os.path.join(base_dir, "learnt_style"),
            os.path.join(base_dir, "learnt_grammar"),
        ]

        for directory in directories_to_create:
            try:
                os.makedirs(directory, exist_ok=True)
                logger.debug(f"确保目录存在: {directory}")
            except Exception as e:
                logger.error(f"创建目录失败 {directory}: {e}")

    @staticmethod
    async def _auto_migrate_json_to_db():
        """
        自动将/data/expression/learnt_style 和 learnt_grammar 下所有expressions.json迁移到数据库。
        迁移完成后在/data/expression/done.done写入标记文件，存在则跳过。
        """
        base_dir = os.path.join("data", "expression")
        done_flag = os.path.join(base_dir, "done.done")

        # 确保基础目录存在
        try:
            os.makedirs(base_dir, exist_ok=True)
            logger.debug(f"确保目录存在: {base_dir}")
        except Exception as e:
            logger.error(f"创建表达方式目录失败: {e}")
            return

        if os.path.exists(done_flag):
            logger.debug("表达方式JSON已迁移，无需重复迁移。")
            return

        logger.info("开始迁移表达方式JSON到数据库...")
        migrated_count = 0

        for type in ["learnt_style", "learnt_grammar"]:
            type_str = "style" if type == "learnt_style" else "grammar"
            type_dir = os.path.join(base_dir, type)
            if not os.path.exists(type_dir):
                logger.debug(f"目录不存在，跳过: {type_dir}")
                continue

            try:
                chat_ids = os.listdir(type_dir)
                logger.debug(f"在 {type_dir} 中找到 {len(chat_ids)} 个聊天ID目录")
            except Exception as e:
                logger.error(f"读取目录失败 {type_dir}: {e}")
                continue

            for chat_id in chat_ids:
                expr_file = os.path.join(type_dir, chat_id, "expressions.json")
                if not os.path.exists(expr_file):
                    continue
                try:
                    async with aiofiles.open(expr_file, encoding="utf-8") as f:
                        content = await f.read()
                        expressions = orjson.loads(content)

                    if not isinstance(expressions, list):
                        logger.warning(f"表达方式文件格式错误，跳过: {expr_file}")
                        continue

                    for expr in expressions:
                        if not isinstance(expr, dict):
                            continue

                        situation = expr.get("situation")
                        style_val = expr.get("style")
                        count = expr.get("count", 1)
                        last_active_time = expr.get("last_active_time", time.time())

                        if not situation or not style_val:
                            logger.warning(f"表达方式缺少必要字段，跳过: {expr}")
                            continue

                        # 查重：同chat_id+type+situation+style
                        async with get_db_session() as session:
                            query = await session.execute(
                                select(Expression).where(
                                    (Expression.chat_id == chat_id)
                                    & (Expression.type == type_str)
                                    & (Expression.situation == situation)
                                    & (Expression.style == style_val)
                                )
                            )
                            existing_expr = query.scalar()
                            if existing_expr:
                                expr_obj = existing_expr
                                expr_obj.count = max(expr_obj.count, count)
                                expr_obj.last_active_time = max(expr_obj.last_active_time, last_active_time)
                            else:
                                new_expression = Expression(
                                    situation=situation,
                                    style=style_val,
                                    count=count,
                                    last_active_time=last_active_time,
                                    chat_id=chat_id,
                                    type=type_str,
                                    create_date=last_active_time,  # 迁移时使用last_active_time作为创建时间
                                )
                                session.add(new_expression)

                                migrated_count += 1
                    logger.info(f"已迁移 {expr_file} 到数据库，包含 {len(expressions)} 个表达方式")
                except orjson.JSONDecodeError as e:
                    logger.error(f"JSON解析失败 {expr_file}: {e}")
                except Exception as e:
                    logger.error(f"迁移表达方式 {expr_file} 失败: {e}")

        # 标记迁移完成
        try:
            # 确保done.done文件的父目录存在
            done_parent_dir = os.path.dirname(done_flag)
            if not os.path.exists(done_parent_dir):
                os.makedirs(done_parent_dir, exist_ok=True)
                logger.debug(f"为done.done创建父目录: {done_parent_dir}")

            async with aiofiles.open(done_flag, "w", encoding="utf-8") as f:
                await f.write("done\n")
            logger.info(f"表达方式JSON迁移已完成，共迁移 {migrated_count} 个表达方式，已写入done.done标记文件")
        except PermissionError as e:
            logger.error(f"权限不足，无法写入done.done标记文件: {e}")
        except OSError as e:
            logger.error(f"文件系统错误，无法写入done.done标记文件: {e}")
        except Exception as e:
            logger.error(f"写入done.done标记文件失败: {e}")

    @staticmethod
    async def _migrate_old_data_create_date():
        """
        为没有create_date的老数据设置创建日期
        使用last_active_time作为create_date的默认值
        """
        try:
            async with get_db_session() as session:
                # 查找所有create_date为空的表达方式
                old_expressions_result = await session.execute(
                    select(Expression).where(Expression.create_date.is_(None))
                )
                old_expressions = old_expressions_result.scalars().all()
                updated_count = 0

                for expr in old_expressions:
                    # 使用last_active_time作为create_date
                    expr.create_date = expr.last_active_time
                    updated_count += 1

                if updated_count > 0:
                    logger.info(f"已为 {updated_count} 个老的表达方式设置创建日期")
        except Exception as e:
            logger.error(f"迁移老数据创建日期失败: {e}")


expression_learner_manager = ExpressionLearnerManager()
