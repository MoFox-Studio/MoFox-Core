"""
插件系统配置类型定义
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConfigField:
    """配置字段定义

    基础属性：
        type: 字段类型 (str, int, float, bool, list, dict)
        default: 默认值
        description: 字段描述
        example: 示例值
        required: 是否必需
        choices: 可选值列表

    UI 属性（可选，用于 WebUI Schema 编辑器）：
        input_type: 强制指定输入控件类型
            - text: 单行文本
            - password: 密码输入
            - textarea: 多行文本
            - number: 数字输入
            - slider: 滑块
            - switch: 开关
            - select: 下拉选择
            - list: 列表编辑
            - json: JSON 编辑器
            - color: 颜色选择
            - file: 文件路径
        label: 显示标签（默认使用字段名）
        placeholder: 输入占位符
        hint: 帮助提示文本
        icon: Material 图标名称
        hidden: 是否在 UI 中隐藏
        disabled: 是否禁用编辑
        order: 显示顺序（数字越小越靠前）
        rows: textarea 行数

    验证属性（可选）：
        min: 最小值（数字）或最小长度（字符串）
        max: 最大值（数字）或最大长度（字符串）
        step: 数字步进值
        pattern: 正则验证模式
        min_length: 最小字符长度
        max_length: 最大字符长度

    条件显示（可选）：
        group: 分组名称
        depends_on: 依赖的字段名
        depends_value: 依赖字段的期望值

    列表专用（可选）：
        item_type: 列表项类型
        item_fields: 列表项为对象时的字段定义
        min_items: 最小项数
        max_items: 最大项数

    使用示例：
        # 基础用法
        ConfigField(type=str, default="hello", description="问候语")

        # 带 UI 增强
        ConfigField(
            type=int,
            default=50,
            description="音量大小",
            input_type="slider",
            min=0,
            max=100,
            step=5
        )

        # 条件显示
        ConfigField(
            type=str,
            default="",
            description="代理地址",
            depends_on="use_proxy",
            depends_value=True
        )
    """

    # ==================== 基础属性 ====================
    type: type  # 字段类型
    default: Any  # 默认值
    description: str  # 字段描述
    example: str | None = None  # 示例值
    required: bool = False  # 是否必需
    choices: list[Any] | None = field(default_factory=list)  # 可选值列表

    # ==================== UI 属性 ====================
    input_type: str | None = None  # 强制指定输入控件类型
    label: str | None = None  # 显示标签
    placeholder: str | None = None  # 输入占位符
    hint: str | None = None  # 帮助提示
    icon: str | None = None  # Material 图标名称
    hidden: bool = False  # 是否隐藏
    disabled: bool = False  # 是否禁用
    order: int = 0  # 显示顺序
    rows: int | None = None  # textarea 行数

    # ==================== 验证属性 ====================
    min: int | float | None = None  # 最小值
    max: int | float | None = None  # 最大值
    step: int | float | None = None  # 步进值
    pattern: str | None = None  # 正则验证
    min_length: int | None = None  # 最小长度
    max_length: int | None = None  # 最大长度

    # ==================== 条件显示 ====================
    group: str | None = None  # 分组名称
    depends_on: str | None = None  # 依赖字段名
    depends_value: Any = None  # 依赖期望值

    # ==================== 列表专用 ====================
    item_type: str | None = None  # 列表项类型
    item_fields: dict[str, Any] | None = None  # 列表项字段定义
    min_items: int | None = None  # 最小项数
    max_items: int | None = None  # 最大项数
