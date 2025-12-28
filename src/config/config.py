import os
import shutil
import sys
import types
import typing
from datetime import datetime
from pathlib import Path
from typing import Any, get_args, get_origin

import tomlkit
from pydantic import BaseModel, Field, PrivateAttr
from rich.traceback import install
from tomlkit import TOMLDocument
from tomlkit.items import KeyType, Table

from src.common.logger import get_logger
from src.config.config_base import ValidatedConfigBase
from src.config.official_configs import (
    AffinityFlowConfig,
    BotConfig,
    ChatConfig,
    ChineseTypoConfig,
    CommandConfig,
    CrossContextConfig,
    CustomPromptConfig,
    DatabaseConfig,
    DebugConfig,
    DependencyManagementConfig,
    EmojiConfig,
    ExperimentalConfig,
    ExpressionConfig,
    InnerConfig,
    KokoroFlowChatterConfig,
    LogConfig,
    LPMMKnowledgeConfig,
    MemoryConfig,
    MessageBusConfig,
    MessageReceiveConfig,
    MoodConfig,
    NoticeConfig,
    PermissionConfig,
    PersonalityConfig,
    PlanningSystemConfig,
    PluginHttpSystemConfig,
    ProactiveThinkingConfig,
    ReactionConfig,
    ResponsePostProcessConfig,
    ResponseSplitterConfig,
    ToolConfig,
    VideoAnalysisConfig,
    VoiceConfig,
    WebSearchConfig,
)

from .api_ada_configs import (
    APIProvider,
    ModelInfo,
    ModelTaskConfig,
)

install(extra_lines=3)


# 配置主程序日志格式
logger = get_logger("config")

# 获取当前文件所在目录的父目录的父目录（即MoFox-Bot项目根目录）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "template")

# 考虑到，实际上配置文件中的mai_version是不会自动更新的,所以采用硬编码
# 对该字段的更新，请严格参照语义化版本规范：https://semver.org/lang/zh-CN/
MMC_VERSION = "0.13.1-alpha.2"

# 全局配置变量
_CONFIG_INITIALIZED = False
global_config: "Config | None" = None
model_config: "APIAdapterConfig | None" = None


def get_key_comment(toml_table, key):
    # 获取key的注释（如果有）
    if hasattr(toml_table, "trivia") and hasattr(toml_table.trivia, "comment"):
        return toml_table.trivia.comment
    if hasattr(toml_table, "value") and isinstance(toml_table.value, dict):
        item = toml_table.value.get(key)
        if item is not None and hasattr(item, "trivia"):
            return item.trivia.comment
    if hasattr(toml_table, "keys"):
        for k in toml_table.keys():
            if isinstance(k, KeyType) and k.key == key:  # type: ignore
                return k.trivia.comment  # type: ignore
    return None


def compare_dicts(new, old, path=None, logs=None):
    # 递归比较两个dict，找出新增和删减项，收集注释
    if path is None:
        path = []
    if logs is None:
        logs = []
    # 新增项
    for key in new:
        if key == "version":
            continue
        if key not in old:
            comment = get_key_comment(new, key)
            logs.append(f"新增: {'.'.join([*path, str(key)])}  注释: {comment or '无'}")
        elif isinstance(new[key], dict | Table) and isinstance(old.get(key), dict | Table):
            compare_dicts(new[key], old[key], [*path, str(key)], logs)
    # 删减项
    for key in old:
        if key == "version":
            continue
        if key not in new:
            comment = get_key_comment(old, key)
            logs.append(f"删减: {'.'.join([*path, str(key)])}  注释: {comment or '无'}")
    return logs


def get_value_by_path(d, path):
    for k in path:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return None
    return d


def set_value_by_path(d, path, value):
    for k in path[:-1]:
        if k not in d or not isinstance(d[k], dict):
            d[k] = {}
        d = d[k]
    d[path[-1]] = value


def compare_default_values(new, old, path=None, logs=None, changes=None):
    # 递归比较两个dict，找出默认值变化项
    if path is None:
        path = []
    if logs is None:
        logs = []
    if changes is None:
        changes = []
    for key in new:
        if key == "version":
            continue
        if key in old:
            if isinstance(new[key], dict | Table) and isinstance(old[key], dict | Table):
                compare_default_values(new[key], old[key], [*path, str(key)], logs, changes)
            elif new[key] != old[key]:
                logs.append(f"默认值变化: {'.'.join([*path, str(key)])}  旧默认值: {old[key]}  新默认值: {new[key]}")
                changes.append(([*path, str(key)], old[key], new[key]))
    return logs, changes


def _get_version_from_toml(toml_path) -> str | None:
    """从TOML文件中获取版本号"""
    if not os.path.exists(toml_path):
        return None
    with open(toml_path, encoding="utf-8") as f:
        doc = tomlkit.load(f)
    if "inner" in doc and "version" in doc["inner"]:  # type: ignore
        return doc["inner"]["version"]  # type: ignore
    return None


def _version_tuple(v):
    """将版本字符串转换为元组以便比较"""
    if v is None:
        return (0,)
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).replace("v", "").split("-")[0].split("."))


def _remove_obsolete_keys(target: TOMLDocument | dict | Table, reference: TOMLDocument | dict | Table):
    """
    递归地从目标字典中移除所有不存在于参考字典中的键。
    """
    # 使用 list() 创建键的副本，以便在迭代期间安全地修改字典
    for key in list(target.keys()):
        if key not in reference:
            del target[key]
        elif isinstance(target.get(key), dict | Table) and isinstance(reference.get(key), dict | Table):
            _remove_obsolete_keys(target[key], reference[key])  # type: ignore


def _prune_unknown_keys_by_schema(
    target: TOMLDocument | Table, schema_model: type[BaseModel], path: list[str] | None = None
):
    """
    基于 Pydantic Schema 递归移除未知配置键（含可重复的 AoT 表）

    这个函数的作用是清理配置文件中已废弃或不被Schema认可的配置项。
    在版本升级时，有些配置项可能被移除或重命名，这个函数会自动清理它们。

    工作原理：
    1. 根据Pydantic模型的字段定义，构建允许的键集合
    2. 遍历配置文件，删除不在允许集合中的键
    3. 对于嵌套结构（字典、AoT），递归执行相同的清理过程

    特殊处理：
    - list[BaseModel] 字段（TOML 的 [[...]]）：会遍历每个元素并递归清理
    - dict[str, Any] 等自由结构字段：不做键级裁剪，保持原样
    - 支持字段别名（alias）：如果字段定义了别名，别名也会被认为是合法的

    Args:
        target: 要清理的配置字典（会被直接修改）
        schema_model: Pydantic模型类，定义了合法的配置结构
        path: 当前路径（用于调试，递归时累积）

    示例：
        如果Schema中删除了 old_feature 字段，这个函数会自动删除配置中的：
        [section]
        old_feature = true  # 这一行会被删除
        new_feature = true  # 这一行会保留
    """
    if path is None:
        path = []  # 初始化路径追踪列表

    def _strip_optional(annotation: Any) -> Any:
        """
        剥离类型注解中的 Optional 包装

        将 Optional[str] 或 str | None 转换为 str
        这样我们可以获取真实的类型进行判断

        Args:
            annotation: 类型注解，如 Optional[str], str | None, list[int]

        Returns:
            剥离Optional后的类型，如 str, list[int]
        """
        origin = get_origin(annotation)
        if origin is None:
            return annotation  # 不是泛型类型，直接返回

        # 兼容两种Optional写法：Optional[T] 和 T | None
        union_type = getattr(types, "UnionType", None)  # Python 3.10+ 的 | 语法
        if origin is union_type or origin is typing.Union:
            # 过滤掉 None，只保留实际类型
            args = [a for a in get_args(annotation) if a is not type(None)]
            if len(args) == 1:
                return args[0]  # 只有一个非None类型，返回它
        return annotation  # 无法简化，返回原类型

    def _is_model_type(annotation: Any) -> bool:
        """
        判断一个类型注解是否为 Pydantic BaseModel 子类

        Args:
            annotation: 类型注解

        Returns:
            如果是BaseModel子类返回True，否则False
        """
        return isinstance(annotation, type) and issubclass(annotation, BaseModel)

    def _prune_table(table: TOMLDocument | Table, model: type[BaseModel], current_path: list[str]):
        """
        递归清理一个配置表格

        Args:
            table: 要清理的配置表格
            model: 对应的Pydantic模型
            current_path: 当前路径（用于调试）
        """
        # === 第一步：构建允许的键集合 ===
        name_by_key: dict[str, str] = {}  # 键名 -> 字段名的映射（处理别名）
        allowed_keys: set[str] = set()  # 所有允许的键名集合

        # 遍历模型的所有字段定义
        for field_name, field_info in model.model_fields.items():
            # 字段名本身肯定是允许的
            allowed_keys.add(field_name)
            name_by_key[field_name] = field_name

            # 如果字段定义了别名，别名也是允许的
            # 例如：Field(alias="old_name") 可以让配置文件使用 old_name
            alias = getattr(field_info, "alias", None)
            if isinstance(alias, str) and alias:
                allowed_keys.add(alias)
                name_by_key[alias] = field_name

        # === 第二步：遍历配置，删除不允许的键 ===
        for key in list(table.keys()):  # 使用list()创建副本，避免迭代时修改
            # 如果键不在允许列表中，直接删除
            if key not in allowed_keys:
                del table[key]
                continue  # 处理下一个键

            # === 第三步：对允许的键，检查是否需要递归清理 ===
            field_name = name_by_key[key]  # 获取字段的真实名称
            field_info = model.model_fields[field_name]
            annotation = _strip_optional(getattr(field_info, "annotation", Any))

            value = table.get(key)
            if value is None:
                continue  # 值为空，跳过

            # 子情况3.1：值是BaseModel类型（嵌套的配置对象）
            if _is_model_type(annotation) and isinstance(value, (TOMLDocument, Table)):
                # 递归清理嵌套的配置表格
                # 例如：[memory] 下的各个子配置项
                _prune_table(value, annotation, current_path + [str(key)])
                continue

            # 子情况3.2：值是列表类型
            origin = get_origin(annotation)
            if origin is list:
                args = get_args(annotation)  # 获取列表元素的类型
                elem_ann = _strip_optional(args[0]) if args else Any

                # 特别处理：list[BaseModel] 对应 TOML 的 AoT（[[...]]）
                # 例如：[[expression.rules]] 会被解析为 list[RuleConfig]
                if _is_model_type(elem_ann) and hasattr(value, "__iter__"):
                    # 遍历列表中的每个元素（每个都是一个配置对象）
                    for item in value:
                        if isinstance(item, (TOMLDocument, Table)):
                            # 递归清理列表中的每个配置对象
                            _prune_table(item, elem_ann, current_path + [str(key)])

    # 开始递归清理过程
    _prune_table(target, schema_model, path)


def _create_multiline_array(value: list) -> Any:
    """
    创建一个多行格式的 tomlkit 数组
    用于保持配置文件中数组的可读性（每个元素单独一行）
    """
    arr = tomlkit.array()
    if value:
        arr.multiline(True)
        for item in value:
            arr.append(item)
    return arr


def _is_aot(value) -> bool:
    """
    检查一个值是否是 Array of Tables (AoT)

    AoT 是 TOML 中的特殊数组格式，每个元素都是一个表（字典）
    例如在TOML中：
        [[expression.rules]]  # 第一个规则
        chat_stream_id = ""
        rule_type = "keyword"

        [[expression.rules]]  # 第二个规则
        chat_stream_id = "qq:123:group"
        rule_type = "regex"

    在Python中会被解析为：
        [{"chat_stream_id": "", "rule_type": "keyword"},
         {"chat_stream_id": "qq:123:group", "rule_type": "regex"}]

    注意：AoT 不能用 _create_multiline_array() 转换，否则会破坏TOML格式！

    Args:
        value: 要检查的值

    Returns:
        bool: 如果是AoT返回True，否则返回False
    """
    # 首先必须是列表
    if not isinstance(value, list):
        return False
    # 空列表不是AoT
    if len(value) == 0:
        return False
    # AoT的特征：列表中的每个元素都必须是字典或Table
    # 如果有任何一个元素不是字典，那就是普通数组（如 ["a", "b", "c"]）
    return all(isinstance(item, (dict, Table)) for item in value)


def _update_dict(target: TOMLDocument | dict | Table, source: TOMLDocument | dict, path: list[str] | None = None):
    """
    递归合并配置字典：将source（旧配置）的值更新到target（新模板）中

    这个函数的核心作用是在配置文件版本升级时，保留用户的自定义配置值。

    工作流程：
    1. 遍历source（旧配置）的每个键值对
    2. 如果target（新模板）中已有该键，则用source的值覆盖
    3. 如果target中没有该键，则从source添加到target（保留已废弃的配置）
    4. 特别处理AoT格式，避免破坏TOML结构

    Args:
        target: 目标字典（新模板配置，会被修改）
        source: 源字典（旧用户配置，只读）
        path: 当前路径（用于调试，递归时累积）

    注意：
        - version字段会被跳过，不会从旧配置恢复
        - AoT（如[[rules]]）必须直接赋值，不能用_create_multiline_array转换
        - 普通数组（如["a", "b"]）可以转换为多行格式增强可读性
    """
    if path is None:
        path = []  # 初始化路径追踪列表

    # 遍历source（旧配置）中的每个键值对
    for key, value in source.items():
        # 跳过version字段：版本号应该使用新模板的，不应该从旧配置恢复
        if key == "version":
            continue

        current_path = [*path, str(key)]  # 构建当前配置项的完整路径（用于调试）
        path_str = ".".join(current_path)  # 例如："expression.rules"

        # === 情况1：target中已存在该键，需要更新值 ===
        if key in target:
            target_value = target[key]  # 获取target中的当前值

            # 检查source和target的值是否为AoT格式
            # 这很重要！AoT需要特殊处理，不能随意转换格式
            is_source_aot = _is_aot(value)
            is_target_aot = _is_aot(target_value)

            # 子情况1.1：两边都是字典类型，需要递归合并
            if isinstance(value, dict) and isinstance(target_value, dict | Table):
                # 递归处理嵌套的配置项，例如 [expression] 下的各个子键
                _update_dict(target_value, value, current_path)

            # 子情况1.2：source或target是AoT格式
            elif is_source_aot or is_target_aot:
                # AoT必须直接赋值！
                # 如果使用_create_multiline_array转换，会把：
                #   [[rules]]
                #   key = "value"
                # 错误地转换为：
                #   rules = [
                #       {key = "value"}  # 这是错误的TOML语法！
                #   ]
                target[key] = value

            # 子情况1.3：其他类型的值更新
            else:
                try:
                    # 对普通数组（如 ["a", "b", "c"]）使用多行格式，提高可读性：
                    # ban_words = [
                    #     "word1",
                    #     "word2",
                    # ]
                    if isinstance(value, list):
                        target[key] = _create_multiline_array(value)
                    else:
                        # 其他类型（字符串、数字、布尔值等）使用tomlkit.item包装
                        # 这样可以保留TOML的注释和格式
                        target[key] = tomlkit.item(value)
                except (TypeError, ValueError):
                    # 如果tomlkit转换失败（极少见），直接赋值
                    target[key] = value

        # === 情况2：target中不存在该键，需要添加新键 ===
        else:
            is_source_aot = _is_aot(value)  # 检查要添加的值是否为AoT

            try:
                # 子情况2.1：添加字典类型
                if isinstance(value, dict):
                    # 创建新的TOML表格，然后递归填充内容
                    new_table = tomlkit.table()
                    _update_dict(new_table, value, current_path)
                    target[key] = new_table

                # 子情况2.2：添加AoT格式
                elif is_source_aot:
                    # AoT直接赋值，不转换！（原因同上）
                    target[key] = value

                # 子情况2.3：添加普通数组
                elif isinstance(value, list):
                    # 转换为多行格式，提高可读性
                    target[key] = _create_multiline_array(value)

                # 子情况2.4：添加其他类型
                else:
                    # 使用tomlkit.item包装，保留格式
                    target[key] = tomlkit.item(value)
            except (TypeError, ValueError):
                # 如果tomlkit转换失败，直接赋值作为后备方案
                target[key] = value


def _update_config_generic(config_name: str, template_name: str, schema_model: type[BaseModel] | None = None):
    """
    通用的配置文件更新函数（自动版本升级和配置迁移）

    这是配置系统的核心函数，负责在版本升级时自动迁移用户配置。

    完整工作流程：
    1. **检查配置文件是否存在**
       - 不存在：从模板创建新配置，提示用户填写，然后退出程序
       - 存在：继续后续步骤

    2. **版本检测**
       - 比较旧配置版本号与新模板版本号
       - 版本相同：跳过更新
       - 版本不同：执行更新流程

    3. **默认值变动检测**（可选）
       - 如果存在compare模板（上次的模板快照），检测默认值是否变化
       - 如果用户使用的是旧默认值，自动更新为新默认值
       - 这样可以避免用户因为没有修改过某个配置项而错过重要的默认值更新

    4. **配置合并**
       - 创建新配置文件（基于新模板）
       - 将旧配置的所有值合并到新配置中（保留用户自定义）
       - 特别处理AoT格式，避免破坏TOML结构

    5. **配置裁剪**
       - 根据Schema移除已废弃的配置项
       - 清理不再使用的字段，避免配置文件膨胀

    6. **保存结果**
       - 备份旧配置到 config/old/ 目录
       - 保存新配置（保留注释和格式）
       - 更新compare模板快照

    Args:
        config_name: 配置文件名（不含扩展名）
            例如：'bot_config' 或 'model_config'
        template_name: 模板文件名（不含扩展名）
            例如：'bot_config_template' 或 'model_config_template'
        schema_model: 用于裁剪未知键的 Pydantic 模型（可选）
            例如：Config 或 APIAdapterConfig
            如果提供，会使用Schema精确裁剪；否则使用模板进行简单对比

    文件路径说明：
        - template/xxx_template.toml: 最新的配置模板（开发者维护）
        - config/xxx.toml: 用户的配置文件
        - config/old/xxx_YYYYMMDD_HHMMSS.toml: 备份的旧配置
        - template/compare/xxx_template.toml: 上次更新时的模板快照（用于检测默认值变动）

    注意事项：
        - version字段不会从旧配置恢复，始终使用新模板的版本号
        - 如果是全新安装（配置文件不存在），会创建配置后退出，要求用户填写
        - 备份文件会带时间戳，方便用户回滚
    """
    # === 准备工作：初始化路径和目录 ===
    old_config_dir = os.path.join(CONFIG_DIR, "old")  # 旧配置备份目录
    compare_dir = os.path.join(TEMPLATE_DIR, "compare")  # 模板快照目录

    # 定义关键文件路径
    template_path = os.path.join(TEMPLATE_DIR, f"{template_name}.toml")  # 最新模板
    old_config_path = os.path.join(CONFIG_DIR, f"{config_name}.toml")  # 用户配置（旧）
    new_config_path = os.path.join(CONFIG_DIR, f"{config_name}.toml")  # 用户配置（新，会覆盖旧的）
    compare_path = os.path.join(compare_dir, f"{template_name}.toml")  # 模板快照（上次的模板）

    # 确保compare目录存在
    os.makedirs(compare_dir, exist_ok=True)

    # 读取版本号（用于版本比对）
    template_version = _get_version_from_toml(template_path)  # 新模板的版本
    compare_version = _get_version_from_toml(compare_path)  # 上次快照的版本

    # === 第一步：检查配置文件是否存在 ===
    if not os.path.exists(old_config_path):
        # 配置文件不存在，说明是首次运行
        logger.info(f"{config_name}.toml配置文件不存在，从模板创建新配置")

        # 确保配置目录存在
        os.makedirs(CONFIG_DIR, exist_ok=True)

        # 从模板复制一份全新的配置文件
        shutil.copy2(template_path, old_config_path)

        logger.info(f"已创建新{config_name}配置文件，请填写后重新运行: {old_config_path}")

        # 退出程序，让用户先填写配置
        # 这是合理的，因为很多配置项（如API密钥）必须由用户填写才能正常工作
        sys.exit(0)

    # 初始化配置变量
    compare_config = None  # 上次的模板快照
    new_config = None  # 当前最新的模板
    old_config = None  # 用户的旧配置

    # === 第二步（可选）：默认值变动检测 ===
    # 如果存在模板快照，可以检测默认值是否发生变化
    # 这个功能很有用：如果开发者修改了某个配置项的默认值，
    # 而用户之前使用的就是旧默认值（没有自定义），
    # 那么应该自动更新为新默认值，而不是保留旧的。
    if os.path.exists(compare_path):
        with open(compare_path, encoding="utf-8") as f:
            compare_config = tomlkit.load(f)  # 加载上次的模板快照

    # 读取当前最新的模板
    with open(template_path, encoding="utf-8") as f:
        new_config = tomlkit.load(f)

    # 检查默认值变化并自动更新（只有存在compare快照时才执行）
    if compare_config:
        # 读取用户的旧配置
        with open(old_config_path, encoding="utf-8") as f:
            old_config = tomlkit.load(f)

        # 比对新旧模板，找出默认值变化的配置项
        logs, changes = compare_default_values(new_config, compare_config)

        if logs:
            logger.info(f"检测到{config_name}模板默认值变动如下：")
            for log in logs:
                logger.info(log)

            # 对于每个默认值变化的配置项
            for path, old_default, new_default in changes:
                old_value = get_value_by_path(old_config, path)

                # 如果用户的值等于旧默认值（说明用户没有自定义）
                if old_value == old_default:
                    # 自动更新为新默认值
                    set_value_by_path(old_config, path, new_default)
                    logger.info(
                        f"已自动将{config_name}配置 {'.'.join(path)} 的值从旧默认值 {old_default} 更新为新默认值 {new_default}"
                    )
                # 如果用户的值不等于旧默认值，说明用户自定义过，保留用户的值
        else:
            logger.info(f"未检测到{config_name}模板默认值变动")

    # === 更新compare模板快照 ===
    # compare目录存储的是上次更新时使用的模板
    # 用于下次更新时检测默认值变动

    # 情况1：compare目录下没有这个模板的快照
    if not os.path.exists(compare_path):
        # 复制当前模板作为快照
        shutil.copy2(template_path, compare_path)
        logger.info(f"已将{config_name}模板文件复制到: {compare_path}")

    # 情况2：compare目录下有快照，但版本低于当前模板
    elif _version_tuple(template_version) > _version_tuple(compare_version):
        # 更新快照为当前模板
        shutil.copy2(template_path, compare_path)
        logger.info(f"{config_name}模板版本较新，已替换compare下的模板: {compare_path}")

    # 情况3：compare快照版本不低于当前模板（或相同）
    else:
        # 无需更新快照
        logger.debug(f"compare下的{config_name}模板版本不低于当前模板，无需替换: {compare_path}")

    # 确保old_config已经加载
    # （如果前面因为没有compare快照而跳过了默认值检测，old_config可能还是None）
    if old_config is None:
        with open(old_config_path, encoding="utf-8") as f:
            old_config = tomlkit.load(f)
    # new_config 在前面已经读取过了，这里不需要再读

    # === 第三步：版本检查 ===
    # 比较旧配置和新模板的版本号，决定是否需要更新
    if old_config and "inner" in old_config and "inner" in new_config:
        old_version = old_config["inner"].get("version")  # type: ignore
        new_version = new_config["inner"].get("version")  # type: ignore

        # 版本号相同，跳过更新
        if old_version and new_version and old_version == new_version:
            logger.info(f"检测到{config_name}配置文件版本号相同 (v{old_version})，跳过更新")
            return  # 直接返回，不执行后续更新流程
        else:
            # 版本号不同，需要更新
            logger.info(
                f"\n----------------------------------------\n"
                f"检测到{config_name}版本号不同: 旧版本 v{old_version} -> 新版本 v{new_version}\n"
                f"----------------------------------------"
            )
    else:
        # 配置文件中没有版本号字段，可能是很旧的版本
        logger.info(f"已有{config_name}配置文件未检测到版本号，可能是旧版本。将进行更新")

    # === 第四步：备份旧配置 ===
    # 确保备份目录存在
    os.makedirs(old_config_dir, exist_ok=True)

    # 生成带时间戳的备份文件名，避免覆盖之前的备份
    # 格式：bot_config_20231227_143025.toml
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_backup_path = os.path.join(old_config_dir, f"{config_name}_{timestamp}.toml")

    # 移动（而不是复制）旧配置到备份目录
    # 这样原位置就空出来了，可以放新配置
    shutil.move(old_config_path, old_backup_path)
    logger.info(f"已备份旧{config_name}配置文件到: {old_backup_path}")

    # === 第五步：创建新配置（基于模板）===
    # 从模板复制一份全新的配置文件
    shutil.copy2(template_path, new_config_path)
    logger.info(f"已创建新{config_name}配置文件: {new_config_path}")

    # === 第六步：比对配置项变动 ===
    # 输出新增和删减的配置项，帮助用户了解变化
    if old_config:
        logger.info(f"{config_name}配置项变动如下：\n----------------------------------------")
        if logs := compare_dicts(new_config, old_config):
            for log in logs:
                logger.info(log)
        else:
            logger.info("无新增或删减项")

    # === 第七步：合并配置 ===
    # 这是核心步骤：将旧配置的所有值合并到新配置中
    # 这样用户的自定义设置就被保留下来了
    logger.info(f"开始合并{config_name}新旧配置...")
    _update_dict(new_config, old_config)

    # === 第八步：移除废弃的配置项 ===
    # 合并后的配置可能包含一些已经不再使用的旧配置项
    # 这一步会根据Schema清理它们，避免配置文件越来越臃肿
    logger.info(f"开始移除{config_name}中已废弃的配置项...")

    if schema_model is not None:
        # 方式1：使用Pydantic Schema精确裁剪（推荐）
        # 这种方式更准确，因为它知道每个字段的确切类型和结构
        _prune_unknown_keys_by_schema(new_config, schema_model)
    else:
        # 方式2：使用模板文件简单对比裁剪（后备方案）
        # 只保留模板中存在的键，删除模板中没有的键
        with open(template_path, encoding="utf-8") as f:
            template_doc = tomlkit.load(f)
        _remove_obsolete_keys(new_config, template_doc)

    logger.info(f"已移除{config_name}中已废弃的配置项")

    # === 第九步：保存最终配置 ===
    # 使用tomlkit保存，可以保留注释和格式
    # 这很重要，因为配置文件中的注释对用户理解配置项很有帮助
    with open(new_config_path, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(new_config))

    logger.info(f"{config_name}配置文件更新完成，建议检查新配置文件中的内容，以免丢失重要信息")


def update_config():
    """更新bot_config.toml配置文件"""
    _update_config_generic("bot_config", "bot_config_template", schema_model=Config)


def update_model_config():
    """更新model_config.toml配置文件"""
    _update_config_generic("model_config", "model_config_template", schema_model=APIAdapterConfig)


class Config(ValidatedConfigBase):
    """总配置类"""

    inner: InnerConfig = Field(..., description="配置元信息")

    database: DatabaseConfig = Field(..., description="数据库配置")
    bot: BotConfig = Field(..., description="机器人基本配置")
    personality: PersonalityConfig = Field(..., description="个性配置")
    chat: ChatConfig = Field(..., description="聊天配置")
    message_receive: MessageReceiveConfig = Field(..., description="消息接收配置")
    notice: NoticeConfig = Field(..., description="Notice消息配置")
    emoji: EmojiConfig = Field(..., description="表情配置")
    expression: ExpressionConfig = Field(..., description="表达配置")
    memory: MemoryConfig | None = Field(default=None, description="记忆配置")
    mood: MoodConfig = Field(..., description="情绪配置")
    reaction: ReactionConfig = Field(default_factory=ReactionConfig, description="反应规则配置")
    chinese_typo: ChineseTypoConfig = Field(..., description="中文错别字配置")
    response_post_process: ResponsePostProcessConfig = Field(..., description="响应后处理配置")
    response_splitter: ResponseSplitterConfig = Field(..., description="响应分割配置")
    log: LogConfig = Field(..., description="日志配置")
    experimental: ExperimentalConfig = Field(default_factory=lambda: ExperimentalConfig(), description="实验性功能配置")
    message_bus: MessageBusConfig = Field(..., description="消息总线配置")
    lpmm_knowledge: LPMMKnowledgeConfig = Field(..., description="LPMM知识配置")
    tool: ToolConfig = Field(..., description="工具配置")
    debug: DebugConfig = Field(..., description="调试配置")
    custom_prompt: CustomPromptConfig = Field(..., description="自定义提示配置")

    voice: VoiceConfig = Field(..., description="语音配置")
    permission: PermissionConfig = Field(..., description="权限配置")
    command: CommandConfig = Field(..., description="命令系统配置")

    # 有默认值的字段放在后面
    video_analysis: VideoAnalysisConfig = Field(
        default_factory=lambda: VideoAnalysisConfig(), description="视频分析配置"
    )
    dependency_management: DependencyManagementConfig = Field(
        default_factory=lambda: DependencyManagementConfig(), description="依赖管理配置"
    )
    web_search: WebSearchConfig = Field(default_factory=lambda: WebSearchConfig(), description="网络搜索配置")
    planning_system: PlanningSystemConfig = Field(
        default_factory=lambda: PlanningSystemConfig(), description="规划系统配置"
    )
    cross_context: CrossContextConfig = Field(
        default_factory=lambda: CrossContextConfig(), description="跨群聊上下文共享配置"
    )
    affinity_flow: AffinityFlowConfig = Field(default_factory=lambda: AffinityFlowConfig(), description="亲和流配置")
    proactive_thinking: ProactiveThinkingConfig = Field(
        default_factory=lambda: ProactiveThinkingConfig(), description="主动思考配置"
    )
    kokoro_flow_chatter: KokoroFlowChatterConfig = Field(
        default_factory=lambda: KokoroFlowChatterConfig(), description="心流对话系统配置（私聊专用）"
    )
    plugin_http_system: PluginHttpSystemConfig = Field(
        default_factory=lambda: PluginHttpSystemConfig(), description="插件HTTP端点系统配置"
    )

    @property
    def MMC_VERSION(self) -> str:
        return MMC_VERSION


class APIAdapterConfig(ValidatedConfigBase):
    """API Adapter配置类"""

    inner: InnerConfig = Field(..., description="配置元信息")
    models: list[ModelInfo] = Field(..., min_length=1, description="模型列表")
    model_task_config: ModelTaskConfig = Field(..., description="模型任务配置")
    api_providers: list[APIProvider] = Field(..., min_length=1, description="API提供商列表")

    _api_providers_dict: dict[str, APIProvider] = PrivateAttr(default_factory=dict)
    _models_dict: dict[str, ModelInfo] = PrivateAttr(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        self._api_providers_dict = {provider.name: provider for provider in self.api_providers}
        self._models_dict = {model.name: model for model in self.models}

    @property
    def api_providers_dict(self) -> dict[str, APIProvider]:
        return self._api_providers_dict

    @property
    def models_dict(self) -> dict[str, ModelInfo]:
        return self._models_dict

    @classmethod
    def validate_models_list(cls, v):
        """验证模型列表"""
        if not v:
            raise ValueError("模型列表不能为空，请在配置中设置有效的模型列表。")

        # 检查模型名称是否重复
        model_names = [model.name for model in v]
        if len(model_names) != len(set(model_names)):
            raise ValueError("模型名称存在重复，请检查配置文件。")

        # 检查模型标识符是否有效
        for model in v:
            if not model.model_identifier:
                raise ValueError(f"模型 '{model.name}' 的 model_identifier 不能为空")

        return v

    @classmethod
    def validate_api_providers_list(cls, v):
        """验证API提供商列表"""
        if not v:
            raise ValueError("API提供商列表不能为空，请在配置中设置有效的API提供商列表。")

        # 检查API提供商名称是否重复
        provider_names = [provider.name for provider in v]
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("API提供商名称存在重复，请检查配置文件。")

        return v

    def get_model_info(self, model_name: str) -> ModelInfo:
        """根据模型名称获取模型信息"""
        if not model_name:
            raise ValueError("模型名称不能为空")
        if model_name not in self.models_dict:
            raise KeyError(f"模型 '{model_name}' 不存在")
        return self.models_dict[model_name]

    def get_provider(self, provider_name: str) -> APIProvider:
        """根据提供商名称获取API提供商信息"""
        if not provider_name:
            raise ValueError("API提供商名称不能为空")
        if provider_name not in self.api_providers_dict:
            raise KeyError(f"API提供商 '{provider_name}' 不存在")
        return self.api_providers_dict[provider_name]


def load_config(config_path: str) -> Config:
    """
    加载配置文件
    Args:
        config_path: 配置文件路径
    Returns:
        Config对象
    """
    # 读取配置文件（会自动删除未知/废弃配置项）
    original_text = Path(config_path).read_text(encoding="utf-8")
    config_data = tomlkit.parse(original_text)
    _prune_unknown_keys_by_schema(config_data, Config)
    new_text = tomlkit.dumps(config_data)
    if new_text != original_text:
        Path(config_path).write_text(new_text, encoding="utf-8")
        logger.warning(f"已自动移除 {config_path} 中未知/废弃配置项")

    # 将 tomlkit 对象转换为纯 Python 字典，避免 Pydantic 严格模式下的类型验证问题
    # tomlkit 返回的是特殊类型（如 Array、String 等），虽然继承自 Python 标准类型，
    # 但在 Pydantic 严格模式下可能导致类型验证失败
    config_dict = config_data.unwrap()

    # 创建Config对象（各个配置类会自动进行 Pydantic 验证）
    try:
        logger.debug("正在解析和验证配置文件...")
        config = Config.from_dict(config_dict)
        logger.debug("配置文件解析和验证完成")
        return config
    except Exception as e:
        logger.critical(f"配置文件解析失败: {e}")
        raise e


def api_ada_load_config(config_path: str) -> APIAdapterConfig:
    """
    加载API适配器配置文件
    Args:
        config_path: 配置文件路径
    Returns:
        APIAdapterConfig对象
    """
    # 读取配置文件（会自动删除未知/废弃配置项）
    original_text = Path(config_path).read_text(encoding="utf-8")
    config_data = tomlkit.parse(original_text)
    _prune_unknown_keys_by_schema(config_data, APIAdapterConfig)
    new_text = tomlkit.dumps(config_data)
    if new_text != original_text:
        Path(config_path).write_text(new_text, encoding="utf-8")
        logger.warning(f"已自动移除 {config_path} 中未知/废弃配置项")

    config_dict = config_data.unwrap()

    try:
        logger.debug("正在解析和验证API适配器配置文件...")
        config = APIAdapterConfig.from_dict(config_dict)
        logger.debug("API适配器配置文件解析和验证完成")
        return config
    except Exception as e:
        logger.critical(f"API适配器配置文件解析失败: {e}")
        raise e


# 获取配置文件路径


def initialize_configs_once() -> tuple[Config, APIAdapterConfig]:
    """
    初始化配置文件，只执行一次。
    """
    global _CONFIG_INITIALIZED, global_config, model_config

    if _CONFIG_INITIALIZED and global_config and model_config:
        logger.debug("config.py 初始化已执行，跳过重复运行")
        return global_config, model_config

    logger.debug(f"MaiCore当前版本: {MMC_VERSION}")
    update_config()
    update_model_config()

    logger.debug("正在品鉴配置文件...")
    global_config = load_config(config_path=os.path.join(CONFIG_DIR, "bot_config.toml"))
    model_config = api_ada_load_config(config_path=os.path.join(CONFIG_DIR, "model_config.toml"))

    _CONFIG_INITIALIZED = True
    return global_config, model_config


# 同一进程只执行一次初始化，避免重复生成或覆盖配置
global_config, model_config = initialize_configs_once()

logger.debug("非常的新鲜，非常的美味！")
