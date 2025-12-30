"""
三级记忆系统提示词格式化器

根据用户需求优化三级记忆的提示词构建格式：
- 感知记忆：【时间 (聊天流名字)】+ 消息块列表
- 短期记忆：自然语言描述
- 长期记忆：[事实] 主体-主题+客体（属性1：内容， 属性2：内容）
"""

from datetime import datetime
from typing import Any

from src.memory_graph.models import Memory, MemoryBlock, ShortTermMemory


class ThreeTierMemoryFormatter:
    """三级记忆系统提示词格式化器"""

    def __init__(self):
        """初始化格式化器"""
        pass

    async def format_perceptual_memory(self, blocks: list[MemoryBlock]) -> str:
        """
        格式化感知记忆为提示词

        格式：
        - 【时间 (聊天流名字)】
        xxx: abcd
        xxx: aaaa
        xxx: dasd
        xxx: ddda
        xxx: adwd

        - 【时间 (聊天流名字)】
        xxx: abcd
        xxx: aaaa
        ...

        Args:
            blocks: 感知记忆块列表

        Returns:
            格式化后的感知记忆提示词
        """
        if not blocks:
            return ""

        lines = []

        for block in blocks:
            # 提取时间和聊天流信息
            time_str = self._extract_time_from_block(block)
            stream_name = await self._extract_stream_name_from_block(block)

            # 添加块标题
            lines.append(f"- 【{time_str} ({stream_name})】")

            # 添加消息内容
            for message in block.messages:
                sender = self._extract_sender_name(message)
                content = self._extract_message_content(message)
                if content:
                    lines.append(f"{sender}: {content}")

            # 块之间添加空行
            lines.append("")

        # 移除最后的空行并返回
        if lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def format_short_term_memory(self, memories: list[ShortTermMemory]) -> str:
        """
        格式化短期记忆为提示词

        使用自然语言描述的内容

        Args:
            memories: 短期记忆列表

        Returns:
            格式化后的短期记忆提示词
        """
        if not memories:
            return ""

        lines = []

        for memory in memories:
            # 使用content字段作为自然语言描述
            if memory.content:
                lines.append(f"- {memory.content}")

        return "\n".join(lines)

    def format_long_term_memory(self, memories: list[Memory]) -> str:
        """
        格式化长期记忆为提示词

        格式：[事实] 主体-主题+客体（属性1：内容， 属性2：内容）

        Args:
            memories: 长期记忆列表

        Returns:
            格式化后的长期记忆提示词
        """
        if not memories:
            return ""

        lines = []

        for memory in memories:
            formatted = self._format_single_long_term_memory(memory)
            if formatted:
                lines.append(f"- {formatted}")

        return "\n".join(lines)

    async def format_all_tiers(
        self,
        perceptual_blocks: list[MemoryBlock],
        short_term_memories: list[ShortTermMemory],
        long_term_memories: list[Memory]
    ) -> str:
        """
        格式化所有三级记忆为完整的提示词

        Args:
            perceptual_blocks: 感知记忆块列表
            short_term_memories: 短期记忆列表
            long_term_memories: 长期记忆列表

        Returns:
            完整的三级记忆提示词
        """
        sections = []

        # 感知记忆
        perceptual_text = await self.format_perceptual_memory(perceptual_blocks)
        if perceptual_text:
            sections.append("### 感知记忆（即时对话）")
            sections.append("*注意：以下消息来自不同的聊天流（括号内标注了来源），不一定是当前对话*")
            sections.append(perceptual_text)
            sections.append("")

        # 短期记忆
        short_term_text = self.format_short_term_memory(short_term_memories)
        if short_term_text:
            sections.append("### 短期记忆（结构化信息）")
            sections.append(short_term_text)
            sections.append("")

        # 长期记忆
        long_term_text = self.format_long_term_memory(long_term_memories)
        if long_term_text:
            sections.append("### 长期记忆（知识图谱）")
            sections.append(long_term_text)
            sections.append("")

        # 移除最后的空行
        if sections and sections[-1] == "":
            sections.pop()

        return "\n".join(sections)

    def _extract_time_from_block(self, block: MemoryBlock) -> str:
        """
        从记忆块中提取时间信息

        Args:
            block: 记忆块

        Returns:
            格式化的时间字符串
        """
        # 优先使用创建时间
        if block.created_at:
            return block.created_at.strftime("%H:%M")

        # 如果有消息，尝试从第一条消息提取时间
        if block.messages:
            first_msg = block.messages[0]
            timestamp = first_msg.get("timestamp")
            if timestamp:
                if isinstance(timestamp, datetime):
                    return timestamp.strftime("%H:%M")
                elif isinstance(timestamp, str):
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        return dt.strftime("%H:%M")
                    except:
                        pass

        return "未知时间"

    async def _extract_stream_name_from_block(self, block: MemoryBlock) -> str:
        """
        从记忆块中提取聊天流名称

        Args:
            block: 记忆块

        Returns:
            聊天流名称
        """
        stream_id = None

        # 首先尝试从元数据中获取 stream_id
        if block.metadata:
            stream_id = block.metadata.get("stream_id")

        # 如果从元数据中没找到，尝试从消息中提取
        if not stream_id and block.messages:
            first_msg = block.messages[0]
            stream_id = first_msg.get("stream_id") or first_msg.get("chat_id")

        # 如果有 stream_id，尝试获取实际的流名称
        if stream_id:
            try:
                from src.chat.message_receive.chat_stream import get_chat_manager
                chat_manager = get_chat_manager()
                actual_name = await chat_manager.get_stream_name(stream_id)
                if actual_name:
                    return actual_name
                else:
                    # 如果获取不到名称，返回 stream_id 的截断版本
                    return stream_id[:12] + "..." if len(stream_id) > 12 else stream_id
            except Exception:
                # 如果获取失败，返回 stream_id 的截断版本
                return stream_id[:12] + "..." if len(stream_id) > 12 else stream_id

        return "默认聊天"

    def _extract_sender_name(self, message: dict[str, Any]) -> str:
        """
        从消息中提取发送者名称

        Args:
            message: 消息字典

        Returns:
            发送者名称
        """
        sender = message.get("sender_name") or message.get("sender") or message.get("user_name")
        if sender:
            return str(sender)

        # 如果没有发送者信息，使用默认值
        role = message.get("role", "")
        if role == "user":
            return "用户"
        elif role == "assistant":
            return "助手"
        else:
            return "未知"

    def _extract_message_content(self, message: dict[str, Any]) -> str:
        """
        从消息中提取内容

        Args:
            message: 消息字典

        Returns:
            消息内容
        """
        content = message.get("content") or message.get("text") or message.get("message")
        if content:
            return str(content).strip()
        return ""

    def _format_single_long_term_memory(self, memory: Memory) -> str:
        """
        格式化单个长期记忆

        格式：[事实] 主体-主题+客体（属性1：内容， 属性2：内容）

        Args:
            memory: 长期记忆对象

        Returns:
            格式化后的长期记忆
        """
        try:
            # 获取记忆类型标签
            type_label = self._get_memory_type_label(memory.memory_type)

            # 获取主体节点
            subject_node = memory.get_subject_node()
            if not subject_node:
                return ""

            subject = subject_node.content

            # 查找主题节点
            topic_node = None
            for edge in memory.edges:
                edge_type = edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type)
                if edge_type == "记忆类型" and edge.source_id == memory.subject_id:
                    topic_node = memory.get_node_by_id(edge.target_id)
                    break

            if not topic_node:
                return f"[{type_label}] {subject}"

            topic = topic_node.content

            # 查找客体和属性
            objects = []
            attributes: dict[str, str] = {}
            attribute_names: dict[str, str] = {}

            for edge in memory.edges:
                edge_type = edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type)

                if edge_type == "核心关系" and edge.source_id == topic_node.id:
                    obj_node = memory.get_node_by_id(edge.target_id)
                    if obj_node:
                        relation_label = (edge.relation or "").strip()
                        obj_text = obj_node.content
                        if relation_label and relation_label not in {"未知", "核心关系"}:
                            objects.append(f"{relation_label}：{obj_text}")
                        else:
                            objects.append(obj_text)

                elif edge_type == "属性关系":
                    attr_node = memory.get_node_by_id(edge.target_id)
                    if not attr_node:
                        continue

                    if edge.source_id == topic_node.id:
                        # 记录属性节点的名称，稍后匹配对应的值节点
                        attribute_names[attr_node.id] = attr_node.content
                        continue

                    attr_name = attribute_names.get(edge.source_id)
                    if not attr_name:
                        attr_name = edge.relation.strip() if edge.relation else "属性"

                    attributes[attr_name] = attr_node.content

            # 检查节点中的属性（处理 "key=value" 格式）
            for node in memory.nodes:
                if hasattr(node, "node_type") and str(node.node_type) == "属性":
                    # 处理 "key=value" 格式的属性
                    if "=" in node.content:
                        key, value = node.content.split("=", 1)
                        attributes.setdefault(key.strip(), value.strip())
                    else:
                        attributes.setdefault("属性", node.content)

            # 构建最终格式
            result = f"[{type_label}] {subject}-{topic}"

            if objects:
                result += "-" + "-".join(objects)

            if attributes:
                # 将属性字典格式化为简洁的字符串
                attr_strs = [f"{key}：{value}" for key, value in attributes.items()]
                result += "（" + "，".join(attr_strs) + "）"

            return result

        except Exception as e:
            # 如果格式化失败，返回基本描述
            return f"[记忆] 格式化失败: {e!s}"

    def _get_memory_type_label(self, memory_type) -> str:
        """
        获取记忆类型的中文标签

        Args:
            memory_type: 记忆类型

        Returns:
            中文标签
        """
        if hasattr(memory_type, "value"):
            type_value = memory_type.value
        else:
            type_value = str(memory_type)

        type_mapping = {
            "EVENT": "事件",
            "event": "事件",
            "事件": "事件",
            "FACT": "事实",
            "fact": "事实",
            "事实": "事实",
            "RELATION": "关系",
            "relation": "关系",
            "关系": "关系",
            "OPINION": "观点",
            "opinion": "观点",
            "观点": "观点",
        }

        return type_mapping.get(type_value, "事实")

    async def format_for_context_injection(
        self,
        query: str,
        perceptual_blocks: list[MemoryBlock],
        short_term_memories: list[ShortTermMemory],
        long_term_memories: list[Memory],
        max_perceptual: int = 3,
        max_short_term: int = 5,
        max_long_term: int = 10
    ) -> str:
        """
        为上下文注入格式化记忆

        Args:
            query: 用户查询
            perceptual_blocks: 感知记忆块列表
            short_term_memories: 短期记忆列表
            long_term_memories: 长期记忆列表
            max_perceptual: 最大感知记忆数量
            max_short_term: 最大短期记忆数量
            max_long_term: 最大长期记忆数量

        Returns:
            格式化的上下文
        """
        sections = [f"## 用户查询：{query}", ""]

        # 限制数量并格式化
        limited_perceptual = perceptual_blocks[:max_perceptual]
        limited_short_term = short_term_memories[:max_short_term]
        limited_long_term = long_term_memories[:max_long_term]

        all_tiers_text = await self.format_all_tiers(
            limited_perceptual,
            limited_short_term,
            limited_long_term
        )

        if all_tiers_text:
            sections.append("## 相关记忆")
            sections.append(all_tiers_text)

        return "\n".join(sections)


# 创建全局格式化器实例
memory_formatter = ThreeTierMemoryFormatter()
