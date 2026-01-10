import asyncio
import random
import re
import string
import time
from collections import Counter
from typing import Any

import numpy as np
import rjieba

from src.common.data_models.database_data_model import DatabaseUserInfo

# MessageRecv 已被移除，现在使用 DatabaseMessages
from src.common.logger import get_logger
from src.common.message_repository import count_and_length_messages, find_messages
from src.config.config import global_config, model_config
from src.llm_models.utils_model import LLMRequest
from src.person_info.person_info import PersonInfoManager, get_person_info_manager

from .typo_generator import get_typo_generator

logger = get_logger("chat_utils")


def is_english_letter(char: str) -> bool:
    """检查字符是否为英文字母（忽略大小写）"""
    return "a" <= char.lower() <= "z"


def db_message_to_str(message_dict: dict) -> str:
    logger.debug(f"message_dict: {message_dict}")
    time_str = time.strftime("%m-%d %H:%M:%S", time.localtime(message_dict["time"]))
    try:
        name = f"[({message_dict['user_id']}){message_dict.get('user_nickname', '')}]{message_dict.get('user_cardname', '')}"
    except Exception:
        name = message_dict.get("user_nickname", "") or f"用户{message_dict['user_id']}"
    content = message_dict.get("processed_plain_text", "")
    result = f"[{time_str}] {name}: {content}\n"
    logger.debug(f"result: {result}")
    return result


def is_mentioned_bot_in_message(message) -> tuple[bool, float]:
    """检查消息是否提到了机器人

    Args:
        message: DatabaseMessages 消息对象

    Returns:
        tuple[bool, float]: (是否提及, 提及类型)
        提及类型: 0=未提及, 1=弱提及（文本匹配）, 2=强提及（@/回复/私聊）
    """
    assert global_config is not None
    nicknames = global_config.bot.alias_names
    mention_type = 0  # 0=未提及, 1=弱提及, 2=强提及

    # 检查 is_mentioned 属性（保持向后兼容）
    mentioned_attr = getattr(message, "is_mentioned", None)
    if mentioned_attr is not None:
        try:
            # 如果已有 is_mentioned，直接返回（假设是强提及）
            return bool(mentioned_attr), 2.0 if mentioned_attr else 0.0
        except (ValueError, TypeError):
            pass

    # 检查 additional_config（保持向后兼容）
    additional_config = None

    # DatabaseMessages: additional_config 是 JSON 字符串
    if message.additional_config:
        try:
            import orjson
            additional_config = orjson.loads(message.additional_config)
        except Exception:
            pass

    if additional_config and additional_config.get("is_mentioned") is not None:
        try:
            mentioned_value = float(additional_config.get("is_mentioned"))  # type: ignore
            # 如果配置中有提及值，假设是强提及
            return True, 2.0 if mentioned_value > 0 else 0.0
        except Exception as e:
            logger.warning(str(e))
            logger.warning(
                f"消息中包含不合理的设置 is_mentioned: {additional_config.get('is_mentioned')}"
            )

    processed_text = message.processed_plain_text or ""

    # 1. 判断是否为私聊（强提及）
    group_info = getattr(message, "group_info", None)
    if not group_info or not getattr(group_info, "group_id", None):
        mention_type = 2
        logger.debug("检测到私聊消息 - 强提及")

    # 2. 判断是否被@（强提及）
    if re.search(rf"@<(.+?):{global_config.bot.qq_account}>", processed_text):
        mention_type = 2
        logger.debug("检测到@提及 - 强提及")

    # 3. 判断是否被回复（强提及）
    if re.match(
        rf"\[回复 (.+?)\({global_config.bot.qq_account!s}\)：(.+?)\]，说：", processed_text
    ) or re.match(
        rf"\[回复<(.+?)(?=:{global_config.bot.qq_account!s}>)\:{global_config.bot.qq_account!s}>：(.+?)\]，说：",
        processed_text,
    ):
        mention_type = 2
        logger.debug("检测到回复消息 - 强提及")

    # 4. 判断文本中是否提及bot名字或别名（弱提及）
    if mention_type == 0:  # 只有在没有强提及时才检查弱提及
        # 移除@和回复标记后再检查
        message_content = re.sub(r"@(.+?)（(\d+)）", "", processed_text)
        message_content = re.sub(r"@<(.+?)(?=:(\d+))\:(\d+)>", "", message_content)
        message_content = re.sub(r"\[回复 (.+?)\(((\d+)|未知id)\)：(.+?)\]，说：", "", message_content)
        message_content = re.sub(r"\[回复<(.+?)(?=:(\d+))\:(\d+)>：(.+?)\]，说：", "", message_content)

        # 检查bot主名字
        if global_config.bot.nickname in message_content:
            mention_type = 1
            logger.debug(f"检测到文本提及bot主名字 '{global_config.bot.nickname}' - 弱提及")
        # 如果主名字没匹配，再检查别名
        elif nicknames:
            for alias_name in nicknames:
                if alias_name in message_content:
                    mention_type = 1
                    logger.debug(f"检测到文本提及bot别名 '{alias_name}' - 弱提及")
                    break

    # 返回结果
    is_mentioned = mention_type > 0
    return is_mentioned, float(mention_type)

async def get_embedding(text, request_type="embedding") -> list[float] | None:
    """获取文本的embedding向量"""
    assert model_config is not None
    # 每次都创建新的LLMRequest实例以避免事件循环冲突
    llm = LLMRequest(model_set=model_config.model_task_config.embedding, request_type=request_type)
    try:
        embedding, _ = await llm.get_embedding(text)
    except Exception as e:
        logger.error(f"获取embedding失败: {e!s}")
        embedding = None
    return embedding  # type: ignore


async def get_recent_group_speaker(chat_stream_id: str, sender, limit: int = 12) -> list:
    # 获取当前群聊记录内发言的人
    assert global_config is not None
    filter_query = {"chat_id": chat_stream_id}
    sort_order = [("time", -1)]
    recent_messages = await find_messages(message_filter=filter_query, sort=sort_order, limit=limit)

    if not recent_messages:
        return []

    who_chat_in_group = []
    for msg_db_data in recent_messages:
        user_info = DatabaseUserInfo.from_dict(
            {
                "platform": msg_db_data["user_platform"],
                "user_id": msg_db_data["user_id"],
                "user_nickname": msg_db_data["user_nickname"],
                "user_cardname": msg_db_data.get("user_cardname", ""),
            }
        )
        if (
            (user_info.platform, user_info.user_id) != sender
            and user_info.user_id != str(global_config.bot.qq_account)
            and (user_info.platform, user_info.user_id, user_info.user_nickname) not in who_chat_in_group
            and len(who_chat_in_group) < 5
        ):  # 排除重复，排除消息发送者，排除bot，限制加载的关系数目
            who_chat_in_group.append((user_info.platform, user_info.user_id, user_info.user_nickname))

    return who_chat_in_group


def smart_split_text(text: str, max_sentence_num: int) -> list[str]:
    """智能文本分割算法
    1. 句子内部标点完全保留。
    2. 采用“全局最小代价合并”算法，优先合并空格和逗号，保护句号。
    3. 引入动态阈值和随机扰动，保留长文本能力与灵动感。
    4. 仅在最终分割点移除冗余标点（含换行符）。
    """
    if not text:
        return []

    # --- 1. 预处理与保护 ---
    url_pattern = r'https?://[^\s，。！？”）》]+'
    urls = re.findall(url_pattern, text)
    for idx, url in enumerate(urls):
        text = text.replace(url, f"__URL_PROTECT_{idx}__")

    pair_pattern = r'([（\(《「].*?[）\)》」])'
    pairs = re.findall(pair_pattern, text)
    for idx, pair in enumerate(pairs):
        text = text.replace(pair, f"__PAIR_PROTECT_{idx}__")

    # --- 2. 初始切分 ---
    # 匹配所有标点作为潜在分割点
    punct_pattern = r'([。，,！!？?；;\n\r\t\s~～♪…]+)'
    raw_parts = re.split(punct_pattern, text)
    
    segments = []
    for i in range(0, len(raw_parts) - 1, 2):
        content = raw_parts[i]
        punct = raw_parts[i+1]
        if content or punct:
            segments.append(content + punct)
    if len(raw_parts) % 2 != 0 and raw_parts[-1]:
        segments.append(raw_parts[-1])

    if not segments:
        return [text]

    # --- 3. 全局最小代价合并 ---
    def get_merge_info(segment: str, total_len: int) -> tuple[float, float]:
        """返回 (阻力系数, 合并概率)
        阻力系数：用于全局排序，越大越不容易合并。
        合并概率：用于随机决策，越小越倾向于断开。
        """
        s = segment.strip()
        if not s: return 1.0, 1.0
        
        # 基础合并概率：全文越长，合并概率越低（倾向于多发几条）
        base_prob = max(0.2, min(0.8, 1.0 - (total_len / 500)))
        
        # 换行符：绝对的分割点，阻力最高，合并概率最低
        if any(c in s for c in "\n\r\t"):
            return 50.0, 0.01
            
        # 强标点（句号、分号）：用户认为“不好看”，优先作为分割点（即不合并）
        if s.endswith(("。", "；", ";")):
            return 20.0, base_prob * 0.1  # 极高阻力，极低合并率
            
        # 情感标点（问号、感叹号）：虽然也是强断句，但比句号更有保留价值
        if s.endswith(("！", "!", "？", "?")):
            return 15.0, base_prob * 0.2
            
        # 弱标点（逗号、波浪号、♪）：合并后观感好，阻力小，合并率高
        if s.endswith(("，", ",", "~", "～", "♪", "…")):
            return 2.0, base_prob * 0.8
            
        # 无标点或空格：最优先合并
        return 1.1, 0.95

    # 尝试进行概率合并
    # 我们进行多轮尝试，直到无法再合并或达到上限
    changed = True
    while changed and len(segments) > 1:
        changed = False
        # 计算所有缝隙的合并代价
        gap_scores = []
        for i in range(len(segments) - 1):
            res, prob = get_merge_info(segments[i], len(text))
            # 长度修正：如果当前片段太短，强制提升合并概率
            if len(segments[i].strip()) < 8: prob = max(prob, 0.9)
            
            score = (len(segments[i]) + len(segments[i+1])) * res
            gap_scores.append({'idx': i, 'score': score, 'prob': prob})
        
        # 按代价从小到大排序，优先尝试合并代价小的
        gap_scores.sort(key=lambda x: x['score'])
        
        for gap in gap_scores:
            # 如果条数已经没超限，且随机合并没通过，则保留这个断句
            if len(segments) <= max_sentence_num and random.random() > gap['prob']:
                continue
            
            # 执行合并
            idx = gap['idx']
            segments[idx] += segments[idx+1]
            del segments[idx+1]
            changed = True
            break # 每次合并后重新计算全局代价，保证最优性

    # 硬上限兜底：如果随机合并后依然超限，强制按代价合并
    while len(segments) > max_sentence_num:
        min_score = float('inf')
        merge_idx = -1
        for i in range(len(segments) - 1):
            res, _ = get_merge_info(segments[i], len(text))
            score = (len(segments[i]) + len(segments[i+1])) * res
            if score < min_score:
                min_score = score
                merge_idx = i
        if merge_idx != -1:
            segments[merge_idx] += segments[merge_idx+1]
            del segments[merge_idx+1]
        else:
            break

    # --- 4. 恢复保护内容与分割点清理 ---
    def final_clean(s: str, is_last: bool) -> str:
        for idx, url in enumerate(urls):
            s = s.replace(f"__URL_PROTECT_{idx}__", url)
        for idx, pair in enumerate(pairs):
            s = s.replace(f"__PAIR_PROTECT_{idx}__", pair)
        
        s = s.strip()
        if not is_last:
            # 仅在分割点移除冗余标点（含换行符）
            s = re.sub(r'[，,。；;\n\r\t]+$', '', s)
        return s

    result = []
    for i, seg in enumerate(segments):
        cleaned = final_clean(seg, i == len(segments) - 1)
        if cleaned:
            result.append(cleaned)

    return result


def random_remove_punctuation(text: str) -> str:
    """随机处理标点符号，模拟人类打字习惯

    Args:
        text: 要处理的文本

    Returns:
        str: 处理后的文本
    """
    result = ""
    text_len = len(text)

    for i, char in enumerate(text):
        if char == "。" and i == text_len - 1:  # 结尾的句号
            if random.random() > 0.1:  # 90%概率删除结尾句号
                continue
        elif char == "，":
            rand = random.random()
            if rand < 0.05:  # 5%概率删除逗号
                continue
            elif rand < 0.25:  # 20%概率把逗号变成空格
                result += " "
                continue
        result += char
    return result


def protect_special_blocks(text: str) -> tuple[str, dict[str, str]]:
    """识别并保护数学公式和代码块，返回处理后的文本和映射"""
    placeholder_map = {}

    # 第一层防护：优先保护标准Markdown格式
    # 使用 re.S 来让 . 匹配换行符
    markdown_patterns = {
        "code": r"```.*?```",
        "math": r"\$\$.*?\$\$",
    }

    placeholder_idx = 0
    for block_type, pattern in markdown_patterns.items():
        matches = re.findall(pattern, text, re.S)
        for match in matches:
            placeholder = f"__SPECIAL_{block_type.upper()}_{placeholder_idx}__"
            text = text.replace(match, placeholder, 1)
            placeholder_map[placeholder] = match
            placeholder_idx += 1

    # 第二层防护：保护非标准的、可能是公式或代码的片段
    # 这个正则表达式寻找连续5个以上的、主要由非中文字符组成的片段
    general_pattern = r"(?:[a-zA-Z0-9\s.,;:(){}\[\]_+\-*/=<>^|&%?!'\"√²³ⁿ∑∫≠≥≤]){5,}"

    # 为了避免与已保护的占位符冲突，我们在剩余的文本上进行查找
    # 这是一个简化的处理，更稳妥的方式是分段查找，但目前这样足以应对多数情况
    try:
        matches = re.findall(general_pattern, text)
        for match in matches:
            # 避免将包含占位符的片段再次保护
            if "__SPECIAL_" in match:
                continue

            placeholder = f"__SPECIAL_GENERAL_{placeholder_idx}__"
            text = text.replace(match, placeholder, 1)
            placeholder_map[placeholder] = match
            placeholder_idx += 1
    except re.error as e:
        logger.error(f"特殊区域防护正则表达式错误: {e}")

    return text, placeholder_map

def recover_special_blocks(sentences: list[str], placeholder_map: dict[str, str]) -> list[str]:
    """恢复被保护的特殊块"""
    recovered_sentences = []
    for sentence in sentences:
        for placeholder, original_block in placeholder_map.items():
            sentence = sentence.replace(placeholder, original_block)
        recovered_sentences.append(sentence)
    return recovered_sentences


def protect_quoted_content(text: str) -> tuple[str, dict[str, str]]:
    """识别并保护句子中被引号包裹的内容，返回处理后的文本和映射"""
    placeholder_map = {}
    # 匹配中英文单双引号，使用非贪婪模式
    quote_pattern = re.compile(r'(".*?")|(\'.*?\')|(“.*?”)|(‘.*?’)')

    matches = quote_pattern.finditer(text)

    # 为了避免替换时索引错乱，我们从后往前替换
    # finditer 找到的是 match 对象，我们需要转换为 list 来反转
    match_list = list(matches)

    for idx, match in enumerate(reversed(match_list)):
        original_quoted_text = match.group(0)
        placeholder = f"__QUOTE_{len(match_list) - 1 - idx}__"

        # 直接在原始文本上操作，替换 match 对象的 span
        start, end = match.span()
        text = text[:start] + placeholder + text[end:]

        placeholder_map[placeholder] = original_quoted_text

    return text, placeholder_map


def recover_quoted_content(sentences: list[str], placeholder_map: dict[str, str]) -> list[str]:
    """恢复被保护的引号内容"""
    recovered_sentences = []
    for sentence in sentences:
        for placeholder, original_block in placeholder_map.items():
            sentence = sentence.replace(placeholder, original_block)
        recovered_sentences.append(sentence)
    return recovered_sentences

def process_llm_response(text: str, enable_splitter: bool = True, enable_chinese_typo: bool = True) -> list[str]:
    assert global_config is not None

    normalized_text = text.strip() if isinstance(text, str) else ""
    if normalized_text.upper() == "PASS":
        logger.info("[回复内容过滤器] 检测到PASS信号，跳过发送。")
        return []

    if not global_config.response_post_process.enable_response_post_process:
        return [text]

    # --- 三层防护系统 ---
    # --- 三层防护系统 ---
    # 第一层：保护颜文字
    protected_text, kaomoji_mapping = protect_kaomoji(text) if global_config.response_splitter.enable_kaomoji_protection else (text, {})

    # 第二层：保护引号内容
    protected_text, quote_mapping = protect_quoted_content(protected_text)

    # 第三层：保护数学公式和代码块
    protected_text, special_blocks_mapping = protect_special_blocks(protected_text)

    # 提取被 () 或 [] 或 （）包裹且包含中文的内容
    pattern = re.compile(r"[(\[（](?=.*[一-鿿]).+?[)\]）]")
    _extracted_contents = pattern.findall(protected_text)
    cleaned_text = pattern.sub("", protected_text)

    if cleaned_text.strip() == "":
        # 如果清理后只剩下特殊块，直接恢复并返回
        if special_blocks_mapping:
             recovered = recover_special_blocks([protected_text], special_blocks_mapping)
             return recover_kaomoji(recovered, kaomoji_mapping)
        return ["呃呃"]

    logger.debug(f"{text}去除括号处理后的文本: {cleaned_text}")

    # 对清理后的文本进行进一步处理
    max_sentence_num = global_config.response_splitter.max_sentence_num

    # --- 移除总长度检查 ---
    # 原有的总长度检查会导致长回复被直接丢弃，现已移除，由后续的智能合并逻辑处理。
    # max_length = global_config.response_splitter.max_length * 2
    # if get_western_ratio(cleaned_text) < 0.1 and len(cleaned_text) > max_length:
    #     logger.warning(f"回复过长 ({len(cleaned_text)} 字符)，返回默认回复")
    #     return ["懒得说"]

    # 🔧 内存优化：使用单例工厂函数，避免重复创建拼音字典
    typo_generator = get_typo_generator(
        error_rate=global_config.chinese_typo.error_rate,
        min_freq=global_config.chinese_typo.min_freq,
        tone_error_rate=global_config.chinese_typo.tone_error_rate,
        word_replace_rate=global_config.chinese_typo.word_replace_rate,
    )

    if global_config.response_splitter.enable and enable_splitter:
        logger.info(f"回复分割器已启用，模式: {global_config.response_splitter.split_mode}。")

        if "[SPLIT]" in cleaned_text:
            logger.debug("检测到 [SPLIT] 标记，使用 LLM 自定义分割。")
            split_sentences_raw = cleaned_text.split("[SPLIT]")
            split_sentences = [s.strip() for s in split_sentences_raw if s.strip()]
        else:
            logger.debug("使用智能标点模式进行分割。")
            split_sentences = smart_split_text(cleaned_text, max_sentence_num)
    else:
        logger.debug("回复分割器已禁用。")
        split_sentences = [cleaned_text]

    sentences = []
    for sentence in split_sentences:
        # 清除开头可能存在的空行
        sentence = sentence.lstrip("\n").rstrip()
        if global_config.chinese_typo.enable and enable_chinese_typo:
            typoed_text, typo_corrections = typo_generator.create_typo_sentence(sentence)
            sentences.append(typoed_text)
            if typo_corrections:
                sentences.append(typo_corrections)
        else:
            sentences.append(sentence)

    # 移除冗余的二次合并逻辑，因为 smart_split_text 已经处理了数量限制

    # if extracted_contents:
    #     for content in extracted_contents:
    #         sentences.append(content)

    # --- 恢复所有被保护的内容 ---
    sentences = recover_special_blocks(sentences, special_blocks_mapping)
    sentences = recover_quoted_content(sentences, quote_mapping)
    if global_config.response_splitter.enable_kaomoji_protection:
        sentences = recover_kaomoji(sentences, kaomoji_mapping)

    return sentences


def calculate_typing_time(
    input_string: str,
    thinking_start_time: float,
    chinese_time: float = 0.2,
    english_time: float = 0.1,
    is_emoji: bool = False,
) -> float:
    """
    计算输入字符串所需的时间，中文和英文字符有不同的输入时间
        input_string (str): 输入的字符串
        chinese_time (float): 中文字符的输入时间，默认为0.2秒
        english_time (float): 英文字符的输入时间，默认为0.1秒
        is_emoji (bool): 是否为emoji，默认为False

    特殊情况：
    - 如果只有一个中文字符，将使用3倍的中文输入时间
    - 在所有输入结束后，额外加上回车时间0.3秒
    - 如果is_emoji为True，将使用固定1秒的输入时间
    """
    # # 将0-1的唤醒度映射到-1到1
    # mood_arousal = mood_manager.current_mood.arousal
    # # 映射到0.5到2倍的速度系数
    # typing_speed_multiplier = 1.5**mood_arousal  # 唤醒度为1时速度翻倍,为-1时速度减半
    # chinese_time *= 1 / typing_speed_multiplier
    # english_time *= 1 / typing_speed_multiplier
    # 计算中文字符数
    chinese_chars = sum("\u4e00" <= char <= "\u9fff" for char in input_string)

    # 如果只有一个中文字符，使用3倍时间
    if chinese_chars == 1 and len(input_string.strip()) == 1:
        return chinese_time * 3 + 0.3  # 加上回车时间

    # 正常计算所有字符的输入时间
    total_time = 0.0
    for char in input_string:
        total_time += chinese_time if "\u4e00" <= char <= "\u9fff" else english_time
    if is_emoji:
        total_time = 1

    if time.time() - thinking_start_time > 10:
        total_time = 1

    # print(f"thinking_start_time:{thinking_start_time}")
    # print(f"nowtime:{time.time()}")
    # print(f"nowtime - thinking_start_time:{time.time() - thinking_start_time}")
    # print(f"{total_time}")

    return total_time  # 加上回车时间


def cosine_similarity(v1, v2):
    """计算余弦相似度"""
    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    return 0 if norm1 == 0 or norm2 == 0 else dot_product / (norm1 * norm2)


def text_to_vector(text):
    """将文本转换为词频向量"""
    # 分词
    words = rjieba.lcut(text) # type: ignore
    return Counter(words)


def find_similar_topics_simple(text: str, topics: list, top_k: int = 5) -> list:
    """使用简单的余弦相似度计算文本相似度"""
    # 将输入文本转换为词频向量
    text_vector = text_to_vector(text)

    # 计算每个主题的相似度
    similarities = []
    for topic in topics:
        topic_vector = text_to_vector(topic)
        # 获取所有唯一词
        all_words = set(text_vector.keys()) | set(topic_vector.keys())
        # 构建向量
        v1 = [text_vector.get(word, 0) for word in all_words]
        v2 = [topic_vector.get(word, 0) for word in all_words]
        # 计算相似度
        similarity = cosine_similarity(v1, v2)
        similarities.append((topic, similarity))

    # 按相似度降序排序并返回前k个
    return sorted(similarities, key=lambda x: x[1], reverse=True)[:top_k]


def truncate_message(message: str, max_length=20) -> str:
    """截断消息，使其不超过指定长度"""
    if message is None:
        return ""
    return f"{message[:max_length]}..." if len(message) > max_length else message


def protect_kaomoji(sentence):
    """ "
    识别并保护句子中的颜文字（含括号与无括号），将其替换为占位符，
    并返回替换后的句子和占位符到颜文字的映射表。
    Args:
        sentence (str): 输入的原始句子
    Returns:
        tuple: (处理后的句子, {占位符: 颜文字})
    """
    kaomoji_pattern = re.compile(
        r"("
        r"[(\[（【]"  # 左括号
        r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
        r"[^一-龥a-zA-Z0-9\s]"  # 非中文、非英文、非数字、非空格字符（必须包含至少一个）
        r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
        r"[)\]）】"  # 右括号
        r"]"
        r")"
        r"|"
        r"([▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄]{2,15})"
    )

    kaomoji_matches = kaomoji_pattern.findall(sentence)
    placeholder_to_kaomoji = {}

    for idx, match in enumerate(kaomoji_matches):
        kaomoji = match[0] or match[1]
        placeholder = f"__KAOMOJI_{idx}__"
        sentence = sentence.replace(kaomoji, placeholder, 1)
        placeholder_to_kaomoji[placeholder] = kaomoji

    return sentence, placeholder_to_kaomoji


def recover_kaomoji(sentences, placeholder_to_kaomoji):
    """
    根据映射表恢复句子中的颜文字。
    Args:
        sentences (list): 含有占位符的句子列表
        placeholder_to_kaomoji (dict): 占位符到颜文字的映射表
    Returns:
        list: 恢复颜文字后的句子列表
    """
    recovered_sentences = []
    for sentence in sentences:
        for placeholder, kaomoji in placeholder_to_kaomoji.items():
            sentence = sentence.replace(placeholder, kaomoji)
        recovered_sentences.append(sentence)
    return recovered_sentences


def get_western_ratio(paragraph):
    """计算段落中字母数字字符的西文比例
    原理：检查段落中字母数字字符的西文比例
    通过is_english_letter函数判断每个字符是否为西文
    只检查字母数字字符，忽略标点符号和空格等非字母数字字符

    Args:
        paragraph: 要检查的文本段落

    Returns:
        float: 西文字符比例(0.0-1.0)，如果没有字母数字字符则返回0.0
    """
    alnum_chars = [char for char in paragraph if char.isalnum()]
    if not alnum_chars:
        return 0.0

    western_count = sum(bool(is_english_letter(char)) for char in alnum_chars)
    return western_count / len(alnum_chars)


async def count_messages_between(start_time: float, end_time: float, stream_id: str) -> tuple[int, int]:
    """计算两个时间点之间的消息数量和文本总长度

    Args:
        start_time (float): 起始时间戳 (不包含)
        end_time (float): 结束时间戳 (包含)
        stream_id (str): 聊天流ID

    Returns:
        tuple[int, int]: (消息数量, 文本总长度)
    """
    count = 0
    total_length = 0

    # 参数校验 (可选但推荐)
    if start_time >= end_time:
        # logger.debug(f"开始时间 {start_time} 大于或等于结束时间 {end_time}，返回 0, 0")
        return 0, 0
    if not stream_id:
        logger.error("stream_id 不能为空")
        return 0, 0

    # 使用message_repository中的count_messages和find_messages函数

    # 构建查询条件
    filter_query = {"chat_id": stream_id, "time": {"$gt": start_time, "$lte": end_time}}

    try:
        # 使用聚合查询，避免一次性拉取全部消息导致内存暴涨
        return await count_and_length_messages(filter_query)

    except Exception as e:
        logger.error(f"计算消息数量时发生意外错误: {e}")
        return 0, 0


def translate_timestamp_to_human_readable(timestamp: float, mode: str = "normal") -> str:
    # sourcery skip: merge-comparisons, merge-duplicate-blocks, switch
    """将时间戳转换为人类可读的时间格式

    Args:
        timestamp: 时间戳
        mode: 转换模式，"normal"为标准格式，"relative"为相对时间格式

    Returns:
        str: 格式化后的时间字符串
    """
    if mode == "normal":
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
    elif mode == "normal_no_YMD":
        return time.strftime("%H:%M:%S", time.localtime(timestamp))
    elif mode == "relative":
        now = time.time()
        diff = now - timestamp

        if diff < 20:
            return "刚刚"
        elif diff < 60:
            return f"{int(diff)}秒前"
        elif diff < 3600:
            return f"{int(diff / 60)}分钟前"
        elif diff < 86400:
            return f"{int(diff / 3600)}小时前"
        elif diff < 86400 * 2:
            return f"{int(diff / 86400)}天前"
        else:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)) + ":"
    else:  # mode = "lite" or unknown
        # 只返回时分秒格式
        return time.strftime("%H:%M:%S", time.localtime(timestamp))


async def get_chat_type_and_target_info(chat_id: str) -> tuple[bool, dict | None]:
    """
    获取聊天类型（是否群聊）和私聊对象信息。

    Args:
        chat_id: 聊天流ID

    Returns:
        Tuple[bool, Optional[Dict]]:
            - bool: 是否为群聊 (True 是群聊, False 是私聊或未知)
            - Optional[Dict]: 如果是私聊，包含对方信息的字典；否则为 None。
            字典包含: platform, user_id, user_nickname, person_id, person_name
    """
    is_group_chat = False  # Default to private/unknown
    chat_target_info = None

    try:
        from src.chat.message_receive.chat_stream import get_chat_manager
        if chat_stream := await get_chat_manager().get_stream(chat_id):
            if chat_stream.group_info:
                is_group_chat = True
                chat_target_info = None  # Explicitly None for group chat
            elif chat_stream.user_info:  # It's a private chat
                is_group_chat = False
                user_info = chat_stream.user_info
                platform: str = chat_stream.platform
                user_id: str = user_info.user_id  # type: ignore

                # Initialize target_info with basic info
                target_info = {
                    "platform": platform,
                    "user_id": user_id,
                    "user_nickname": user_info.user_nickname,
                    "person_id": None,
                    "person_name": None,
                }

                # Try to fetch person info
                try:
                    # Assume get_person_id is sync (as per original code), keep using to_thread
                    person_id = PersonInfoManager.get_person_id(platform, user_id)
                    person_name = None
                    if person_id:
                        person_info_manager = get_person_info_manager()
                        try:
                            # 如果没有运行的事件循环，直接 asyncio.run
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # 如果事件循环在运行，从其他线程提交并等待结果
                                try:
                                    fut = asyncio.run_coroutine_threadsafe(
                                        person_info_manager.get_value(person_id, "person_name"), loop
                                    )
                                    person_name = fut.result(timeout=2)
                                except Exception as e:
                                    # 无法在运行循环上安全等待，退回为 None
                                    logger.debug(f"无法通过运行的事件循环获取 person_name: {e}")
                                    person_name = None
                            else:
                                person_name = asyncio.run(person_info_manager.get_value(person_id, "person_name"))
                        except RuntimeError:
                            # get_event_loop 在某些上下文可能抛出 RuntimeError，退回到 asyncio.run
                            try:
                                person_name = asyncio.run(person_info_manager.get_value(person_id, "person_name"))
                            except Exception as e:
                                logger.debug(f"获取 person_name 失败: {e}")
                                person_name = None

                    target_info["person_id"] = person_id
                    target_info["person_name"] = person_name
                except Exception as person_e:
                    logger.warning(
                        f"获取 person_id 或 person_name 时出错 for {platform}:{user_id} in utils: {person_e}"
                    )

                chat_target_info = target_info
        else:
            logger.warning(f"无法获取 chat_stream for {chat_id} in utils")
    except Exception as e:
        logger.error(f"获取聊天类型和目标信息时出错 for {chat_id}: {e}")
        # Keep defaults on error

    return is_group_chat, chat_target_info


def assign_message_ids(messages: list[Any]) -> list[dict[str, Any]]:
    """
    为消息列表中的每个消息分配唯一的简短随机ID

    Args:
        messages: 消息列表

    Returns:
        包含 {'id': str, 'message': any} 格式的字典列表
    """
    result = []
    for i, message in enumerate(messages):
        # 使用简单的索引作为ID
        message_id = f"m{i + 1}"
        result.append({"id": message_id, "message": message})

    return result


def assign_message_ids_flexible(
    messages: list, prefix: str = "msg", id_length: int = 6, use_timestamp: bool = False
) -> list:
    """
    为消息列表中的每个消息分配唯一的简短随机ID（增强版）

    Args:
        messages: 消息列表
        prefix: ID前缀，默认为"msg"
        id_length: ID的总长度（不包括前缀），默认为6
        use_timestamp: 是否在ID中包含时间戳，默认为False

    Returns:
        包含 {'id': str, 'message': any} 格式的字典列表
    """
    result = []
    used_ids = set()

    for i, message in enumerate(messages):
        # 生成唯一的ID
        while True:
            if use_timestamp:
                # 使用时间戳的后几位 + 随机字符
                timestamp_suffix = str(int(time.time() * 1000))[-3:]
                remaining_length = id_length - 3
                random_chars = "".join(random.choices(string.ascii_lowercase + string.digits, k=remaining_length))
                message_id = f"{prefix}{timestamp_suffix}{random_chars}"
            else:
                # 使用索引 + 随机字符
                index_str = str(i + 1)
                remaining_length = max(1, id_length - len(index_str))
                random_chars = "".join(random.choices(string.ascii_lowercase + string.digits, k=remaining_length))
                message_id = f"{prefix}{index_str}{random_chars}"

            if message_id not in used_ids:
                used_ids.add(message_id)
                break

        result.append({"id": message_id, "message": message})

    return result


# 使用示例:
# messages = ["Hello", "World", "Test message"]
#
# # 基础版本
# result1 = assign_message_ids(messages)
# # 结果: [{'id': 'm1123', 'message': 'Hello'}, {'id': 'm2456', 'message': 'World'}, {'id': 'm3789', 'message': 'Test message'}]
#
# # 增强版本 - 自定义前缀和长度
# result2 = assign_message_ids_flexible(messages, prefix="chat", id_length=8)
# # 结果: [{'id': 'chat1abc2', 'message': 'Hello'}, {'id': 'chat2def3', 'message': 'World'}, {'id': 'chat3ghi4', 'message': 'Test message'}]
#
# # 增强版本 - 使用时间戳
# result3 = assign_message_ids_flexible(messages, prefix="ts", use_timestamp=True)
# # 结果: [{'id': 'ts123a1b', 'message': 'Hello'}, {'id': 'ts123c2d', 'message': 'World'}, {'id': 'ts123e3f', 'message': 'Test message'}]


def filter_system_format_content(content: str | None) -> str:
    """
    过滤系统格式化内容，移除回复、@、图片、表情包等系统生成的格式文本

    此方法过滤以下类型的系统格式化内容：
    1. 回复格式：[回复xxx]，说：xxx (包括深度嵌套)
    2. 表情包格式：[表情包：xxx]
    3. 图片格式：[图片:xxx]
    4. @格式：@<xxx>
    5. 错误格式：[表情包(...)]、[图片(...)]

    Args:
        content: 原始内容

    Returns:
        过滤后的纯文本内容
    """
    if not content:
        return ""

    original_content = content
    cleaned_content = content.strip()

    # 核心逻辑：优先处理最复杂的[回复...]格式，特别是嵌套格式。
    # 这种方法最稳健：如果以[回复开头，就找到最后一个]，然后切掉之前的所有内容。
    if cleaned_content.startswith("[回复"):
        last_bracket_index = cleaned_content.rfind("]")
        if last_bracket_index != -1:
            cleaned_content = cleaned_content[last_bracket_index + 1 :].strip()
            # 专门清理 "，说：" 或 "说："
            cleaned_content = re.sub(r"^(，|,)说：", "", cleaned_content).strip()

    # 在处理完回复格式后，再清理其他简单的格式
    # 新增：移除所有残余的 [...] 格式，例如 [at=...] 等
    cleaned_content = re.sub(r"\[.*?\]", "", cleaned_content)

    # 移除@格式：@<xxx>
    cleaned_content = re.sub(r"@<[^>]*>", "", cleaned_content)

    # 记录过滤操作
    if cleaned_content != original_content.strip():
        logger.info(
            f"[系统格式过滤器] 检测到并清理了系统格式化文本。"
            f"原始内容: '{original_content}', "
            f"清理后: '{cleaned_content}'"
        )

    return cleaned_content
