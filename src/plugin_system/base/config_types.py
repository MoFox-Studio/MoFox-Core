"""
插件系统配置类型定义
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConfigField:
    """配置字段定义

    支持以下特性 (参考 Neo-MoFox):
    - 类型定义和验证
    - 默认值
    - 字段描述 (用于文档和 WebUI)
    - 示例值
    - 可选值约束
    - 弃用标记
    - 标签 (用于 WebUI 分组)
    - 依赖字段 (字段 A 显示取决于字段 B 的值)

    基础属性：
        type: 字段类型 (str, int, float, bool, list, dict)
        default: 默认值
        description: 字段描述
        example: 示例值
        required: 是否必需
        choices: 可选值列表

    UI 属性（可选，用于 WebUI Schema 编辑器）：
        input_type: 强制指定输入控件类型
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
        deprecated: 是否已弃用
        deprecated_message: 弃用说明

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
    deprecated: bool = False  # 是否已弃用
    deprecated_message: str = ""  # 弃用说明

    # ==================== 条件显示 ====================
    group: str | None = None  # 分组名称
    depends_on: str | None = None  # 依赖字段名
    depends_value: Any = None  # 依赖期望值

    # ==================== 列表专用 ====================
    item_type: str | None = None  # 列表项类型
    item_fields: dict[str, Any] | None = None  # 列表项字段定义
    min_items: int | None = None  # 最小项数
    max_items: int | None = None  # 最大项数

    def __post_init__(self):
        if self.choices is None:
            self.choices = []

    def to_toml_value(self) -> str:
        """将默认值转换为 TOML 兼容的字符串表示。

        处理 Python None → TOML 空字符串的转换，
        避免生成无效的 TOML 文件。

        Returns:
            str: TOML 兼容的值字符串。
        """
        if self.default is None:
            if self.type is str:
                return '""'
            if self.type is bool:
                return "false"
            if self.type is int:
                return "0"
            if self.type is float:
                return "0.0"
            return '""'
        if self.type is str:
            escaped = str(self.default).replace('"', '\\"')
            return f'"{escaped}"'
        if self.type is bool:
            return "true" if self.default else "false"
        return str(self.default)

    def get_field_signature(self) -> dict[str, Any]:
        """获取字段签名 (用于配置自动更新检测)。

        Returns:
            dict: 字段签名信息，包含类型、默认值等。
        """
        sig = {
            "type": self.type.__name__,
            "default": self.default,
            "description": self.description,
            "required": self.required,
        }
        if self.choices:
            sig["choices"] = self.choices
        if self.deprecated:
            sig["deprecated"] = True
            sig["deprecated_message"] = self.deprecated_message
        return sig


def compare_config_sections(
    schema: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, list[str]]:
    """比较配置 schema 与当前配置，检测变更。

    参考 Neo-MoFox 的 auto_update 机制，检测：
    - 新增字段
    - 移除/弃用字段
    - 默认值变更

    Args:
        schema: 配置 schema 定义 (ConfigField 的 dict)。
        current: 当前配置文件内容。

    Returns:
        dict: {"added": [...], "removed": [...], "changed": [...], "deprecated": [...]}
    """
    result: dict[str, list[str]] = {
        "added": [],
        "removed": [],
        "changed": [],
        "deprecated": [],
    }

    for section_name, fields in schema.items():
        current_section = current.get(section_name, {})

        for field_name, field_def in fields.items():
            if isinstance(field_def, ConfigField):
                if field_def.deprecated:
                    result["deprecated"].append(f"{section_name}.{field_name}")
                    continue

                if field_name not in current_section:
                    result["added"].append(f"{section_name}.{field_name}")

        for field_name in current_section:
            if field_name not in fields:
                result["removed"].append(f"{section_name}.{field_name}")

    return result

>>>>>>> 1d4fa4595 (feat: 修复关键bug + 移植Neo-MoFox组件)
