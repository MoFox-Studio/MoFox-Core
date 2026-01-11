"""
标准 Prompt 模板

提供常用的系统提示词和提示词模板
"""

from typing import Dict, Any, Optional, List
from string import Template


class SystemPrompts:
    """系统提示词集合"""
    
    # 基础助手
    BASIC_ASSISTANT = """你是一个有帮助的AI助手。请根据用户的问题提供准确、有用的回答。"""
    
    # 专业助手
    PROFESSIONAL_ASSISTANT = """你是一个专业的AI助手。请：
1. 提供准确、详细的信息
2. 使用专业术语时进行解释
3. 在不确定时明确说明
4. 保持客观和中立的立场"""
    
    # 编程助手
    CODING_ASSISTANT = """你是一个专业的编程助手。请：
1. 提供清晰、可运行的代码示例
2. 遵循最佳实践和代码规范
3. 解释代码的关键部分
4. 考虑性能和安全性
5. 在适当时提供多种解决方案"""
    
    # 数据分析助手
    DATA_ANALYSIS_ASSISTANT = """你是一个数据分析专家。请：
1. 使用统计方法分析数据
2. 提供可视化建议
3. 解释分析结果的含义
4. 指出数据中的模式和趋势
5. 提供可操作的建议"""
    
    # 文本创作助手
    CREATIVE_WRITING_ASSISTANT = """你是一个创意写作助手。请：
1. 保持创造性和原创性
2. 注意语言的流畅性和美感
3. 根据要求调整写作风格和语气
4. 确保内容连贯且引人入胜
5. 在适当时提供多个创意方向"""
    
    # 翻译助手
    TRANSLATION_ASSISTANT = """你是一个专业的翻译助手。请：
1. 准确传达原文的意思
2. 保持原文的语气和风格
3. 考虑文化差异进行适当调整
4. 使用地道的目标语言表达
5. 对专业术语保持一致性"""
    
    # 教育助手
    EDUCATION_ASSISTANT = """你是一个教育助手。请：
1. 使用简单易懂的语言解释概念
2. 提供具体的例子帮助理解
3. 循序渐进地讲解复杂内容
4. 鼓励思考和提问
5. 根据理解程度调整解释深度"""
    
    # 客服助手
    CUSTOMER_SERVICE_ASSISTANT = """你是一个客户服务助手。请：
1. 保持礼貌和专业的态度
2. 快速准确地理解客户需求
3. 提供清晰的解决方案
4. 在无法解决时提供替代方案
5. 确保客户满意度"""
    
    # JSON 模式
    JSON_MODE = """你需要以JSON格式返回响应。请确保：
1. 输出是有效的JSON格式
2. 不包含任何注释或额外文本
3. 使用适当的数据类型
4. 保持结构清晰易读"""
    
    # 函数调用模式
    FUNCTION_CALLING_MODE = """你可以调用提供的函数来获取信息或执行操作。请：
1. 仔细阅读函数描述和参数要求
2. 根据用户需求选择合适的函数
3. 提供正确的参数值
4. 在必要时进行多次函数调用
5. 基于函数结果给出最终答复"""


class PromptTemplates:
    """提示词模板集合"""
    
    # 问答模板
    QA_TEMPLATE = Template("""基于以下上下文回答问题：

上下文：
$context

问题：$question

请提供准确、详细的回答。""")
    
    # 总结模板
    SUMMARY_TEMPLATE = Template("""请总结以下内容：

$content

要求：
- 保留关键信息
- 长度控制在 $max_length 字以内
- 使用简洁明了的语言""")
    
    # 翻译模板
    TRANSLATION_TEMPLATE = Template("""请将以下 $source_lang 文本翻译成 $target_lang：

$text

要求：
- 准确传达原意
- 使用地道的表达
- 保持原文的语气和风格""")
    
    # 代码生成模板
    CODE_GENERATION_TEMPLATE = Template("""请用 $language 编写代码完成以下任务：

任务描述：
$description

要求：
- 提供完整的代码实现
- 添加必要的注释
- 遵循最佳实践
- 考虑边界情况""")
    
    # 代码审查模板
    CODE_REVIEW_TEMPLATE = Template("""请审查以下 $language 代码：

```$language
$code
```

请从以下方面进行评估：
1. 代码质量和可读性
2. 潜在的bug和问题
3. 性能优化建议
4. 安全性考虑
5. 最佳实践遵循情况""")
    
    # 数据分析模板
    DATA_ANALYSIS_TEMPLATE = Template("""请分析以下数据：

$data

分析要求：
$requirements

请提供：
1. 数据概览和统计特征
2. 关键发现和趋势
3. 可视化建议
4. 可操作的建议""")
    
    # 文本分类模板
    TEXT_CLASSIFICATION_TEMPLATE = Template("""请将以下文本分类到合适的类别中：

文本：
$text

可选类别：
$categories

请返回最合适的类别及其置信度。""")
    
    # 情感分析模板
    SENTIMENT_ANALYSIS_TEMPLATE = Template("""请分析以下文本的情感倾向：

$text

请判断情感类型（积极/中性/消极）并说明理由。""")
    
    # 关键词提取模板
    KEYWORD_EXTRACTION_TEMPLATE = Template("""请从以下文本中提取关键词：

$text

要求：
- 提取 $num_keywords 个关键词
- 按重要性排序
- 解释选择理由""")


class PromptBuilder:
    """提示词构建器
    
    提供便捷的方法构建各种提示词
    """
    
    @staticmethod
    def build_system_prompt(
        role: str = "assistant",
        capabilities: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        tone: Optional[str] = None
    ) -> str:
        """构建系统提示词
        
        Args:
            role: 角色描述
            capabilities: 能力列表
            constraints: 约束条件列表
            tone: 语气风格
            
        Returns:
            str: 系统提示词
        """
        parts = [f"你是一个{role}。"]
        
        if capabilities:
            parts.append("\n你的能力包括：")
            for i, cap in enumerate(capabilities, 1):
                parts.append(f"{i}. {cap}")
        
        if constraints:
            parts.append("\n请注意以下约束：")
            for i, const in enumerate(constraints, 1):
                parts.append(f"{i}. {const}")
        
        if tone:
            parts.append(f"\n请使用{tone}的语气进行回复。")
        
        return "".join(parts)
    
    @staticmethod
    def build_few_shot_prompt(
        task_description: str,
        examples: List[Dict[str, str]],
        query: str
    ) -> str:
        """构建少样本学习提示词
        
        Args:
            task_description: 任务描述
            examples: 示例列表 [{"input": "...", "output": "..."}, ...]
            query: 实际查询
            
        Returns:
            str: 少样本提示词
        """
        parts = [task_description, "\n"]
        
        for i, example in enumerate(examples, 1):
            parts.append(f"\n示例 {i}：")
            parts.append(f"\n输入：{example['input']}")
            parts.append(f"\n输出：{example['output']}")
        
        parts.append(f"\n\n现在，请处理以下输入：\n{query}")
        
        return "".join(parts)
    
    @staticmethod
    def build_chain_of_thought_prompt(
        question: str,
        require_reasoning: bool = True
    ) -> str:
        """构建思维链提示词
        
        Args:
            question: 问题
            require_reasoning: 是否要求展示推理过程
            
        Returns:
            str: 思维链提示词
        """
        parts = [question]
        
        if require_reasoning:
            parts.append("\n\n请一步步思考并展示你的推理过程：")
        
        return "".join(parts)
    
    @staticmethod
    def build_structured_output_prompt(
        task: str,
        output_format: Dict[str, Any],
        example: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建结构化输出提示词
        
        Args:
            task: 任务描述
            output_format: 输出格式描述
            example: 示例输出
            
        Returns:
            str: 结构化输出提示词
        """
        import json
        
        parts = [task, "\n\n请以以下JSON格式输出：\n"]
        parts.append(json.dumps(output_format, indent=2, ensure_ascii=False))
        
        if example:
            parts.append("\n\n示例输出：\n")
            parts.append(json.dumps(example, indent=2, ensure_ascii=False))
        
        return "".join(parts)
    
    @staticmethod
    def build_context_prompt(
        context: str,
        question: str,
        instructions: Optional[List[str]] = None
    ) -> str:
        """构建上下文相关提示词
        
        Args:
            context: 上下文信息
            question: 问题
            instructions: 指令列表
            
        Returns:
            str: 上下文提示词
        """
        parts = ["基于以下上下文信息：\n", f"\n{context}\n"]
        
        if instructions:
            parts.append("\n请按照以下要求：\n")
            for i, inst in enumerate(instructions, 1):
                parts.append(f"{i}. {inst}\n")
        
        parts.append(f"\n问题：{question}")
        
        return "".join(parts)
    
    @staticmethod
    def apply_template(template: Template, **kwargs) -> str:
        """应用模板
        
        Args:
            template: 模板对象
            **kwargs: 模板参数
            
        Returns:
            str: 填充后的提示词
        """
        return template.substitute(**kwargs)


# 常用提示词快捷方式
def get_system_prompt(preset: str = "basic") -> str:
    """获取预设系统提示词
    
    Args:
        preset: 预设名称
            - basic: 基础助手
            - professional: 专业助手
            - coding: 编程助手
            - data_analysis: 数据分析助手
            - creative: 创意写作助手
            - translation: 翻译助手
            - education: 教育助手
            - customer_service: 客服助手
            - json: JSON模式
            - function_calling: 函数调用模式
            
    Returns:
        str: 系统提示词
    """
    prompts = {
        "basic": SystemPrompts.BASIC_ASSISTANT,
        "professional": SystemPrompts.PROFESSIONAL_ASSISTANT,
        "coding": SystemPrompts.CODING_ASSISTANT,
        "data_analysis": SystemPrompts.DATA_ANALYSIS_ASSISTANT,
        "creative": SystemPrompts.CREATIVE_WRITING_ASSISTANT,
        "translation": SystemPrompts.TRANSLATION_ASSISTANT,
        "education": SystemPrompts.EDUCATION_ASSISTANT,
        "customer_service": SystemPrompts.CUSTOMER_SERVICE_ASSISTANT,
        "json": SystemPrompts.JSON_MODE,
        "function_calling": SystemPrompts.FUNCTION_CALLING_MODE
    }
    
    return prompts.get(preset, SystemPrompts.BASIC_ASSISTANT)


def create_qa_prompt(context: str, question: str) -> str:
    """创建问答提示词"""
    return PromptTemplates.QA_TEMPLATE.substitute(
        context=context,
        question=question
    )


def create_summary_prompt(content: str, max_length: int = 200) -> str:
    """创建总结提示词"""
    return PromptTemplates.SUMMARY_TEMPLATE.substitute(
        content=content,
        max_length=max_length
    )


def create_translation_prompt(
    text: str,
    source_lang: str = "中文",
    target_lang: str = "英文"
) -> str:
    """创建翻译提示词"""
    return PromptTemplates.TRANSLATION_TEMPLATE.substitute(
        text=text,
        source_lang=source_lang,
        target_lang=target_lang
    )
