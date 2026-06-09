from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InjectionType(Enum):
    """Prompt注入类型枚举"""

    PREPEND = "prepend"  # 在开头添加
    APPEND = "append"  # 在末尾添加
    REPLACE = "replace"  # 替换指定内容
    REMOVE = "remove"  # 删除指定内容
    INSERT_AFTER = "insert_after"  # 在指定内容之后插入

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True)
class InjectionRule:
    """Prompt注入规则"""

    target_prompt: str  # 目标Prompt的名称
    injection_type: InjectionType = InjectionType.PREPEND  # 注入类型
    priority: int = 100  # 优先级，数字越小越先执行
    target_content: str | None = None  # 用于REPLACE、REMOVE和INSERT_AFTER操作的目标内容（支持正则表达式）

    def __post_init__(self):
        if self.injection_type in [
            InjectionType.REPLACE,
            InjectionType.REMOVE,
            InjectionType.INSERT_AFTER,
        ] and self.target_content is None:
            raise ValueError(f"'{self.injection_type.value}'类型的注入规则必须提供 'target_content'。")

from src.llm_models.payload_content.tool_option import ToolCall as ToolCall
from src.llm_models.payload_content.tool_option import ToolParamType as ToolParamType


# 组件类型枚举
class ComponentType(Enum):
    """组件类型枚举"""

    ACTION = "action"  # 动作组件
    COMMAND = "command"  # 命令组件
    PLUS_COMMAND = "plus_command"  # 增强命令组件
    TOOL = "tool"  # 工具组件
    SCHEDULER = "scheduler"  # 定时任务组件（预留）
    EVENT_HANDLER = "event_handler"  # 事件处理组件
    CHATTER = "chatter"  # 聊天处理器组件
    PROMPT = "prompt"  # Prompt组件
    ROUTER = "router"  # 路由组件
    SERVICE = "service"  # 服务组件（插件间服务调用）
    ADAPTER = "adapter"  # 适配器组件

    def __str__(self) -> str:
        return self.value


# 动作激活类型枚举
class ActionActivationType(Enum):
    """动作激活类型枚举"""

    NEVER = "never"  # 从不激活（默认关闭）
    ALWAYS = "always"  # 默认参与到planner
    LLM_JUDGE = "llm_judge"  # LLM判定是否启动该action到planner
    RANDOM = "random"  # 随机启用action到planner
    KEYWORD = "keyword"  # 关键词触发启用action到planner

    def __str__(self):
        return self.value


# 聊天模式枚举
class ChatMode(Enum):
    """聊天模式枚举"""

    FOCUS = "focus"  # 专注模式
    NORMAL = "normal"  # Normal聊天模式
    PROACTIVE = "proactive"  # 主动思考模式
    PRIORITY = "priority"  # 优先级聊天模式
    ALL = "all"  # 所有聊天模式

    def __str__(self):
        return self.value


# 聊天类型枚举
class ChatType(Enum):
    """聊天类型枚举，用于限制插件在不同聊天环境中的使用"""

    PRIVATE = "private"  # 仅私聊可用
    GROUP = "group"  # 仅群聊可用
    ALL = "all"  # 群聊和私聊都可用

    def __str__(self):
        return self.value


# 事件类型枚举
class EventType(Enum):
    """
    事件类型枚举类
    """

    ON_START = "on_start"  # 启动事件，用于调用按时任务
    ON_STOP = "on_stop"
    ON_MESSAGE = "on_message"
    ON_NOTICE_RECEIVED = "on_notice_received"  # Notice 消息事件（戳一戳、禁言等）
    ON_PLAN = "on_plan"
    POST_LLM = "post_llm"
    AFTER_LLM = "after_llm"
    POST_SEND = "post_send"
    AFTER_SEND = "after_send"
    UNKNOWN = "unknown"  # 未知事件类型

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True)
class PythonDependency:
    """Python包依赖信息"""

    package_name: str  # 包名称
    version: str = ""  # 版本要求，例如: ">=1.0.0", "==2.1.3", ""表示任意版本
    optional: bool = False  # 是否为可选依赖
    description: str = ""  # 依赖描述
    install_name: str = ""  # 安装时的包名（如果与import名不同）

    def __post_init__(self):
        if not self.install_name:
            self.install_name = self.package_name

    def get_pip_requirement(self) -> str:
        """获取pip安装格式的依赖字符串"""
        if self.version:
            return f"{self.install_name}{self.version}"
        return self.install_name


@dataclass(slots=True)
class PermissionNodeField:
    """权限节点声明字段"""

    node_name: str  # 节点名称 (例如 "manage" 或 "view")
    description: str  # 权限描述


@dataclass(slots=True)
class AdapterInfo:
    """适配器组件信息"""

    name: str  # 适配器名称
    component_type: ComponentType = field(default=ComponentType.ADAPTER, init=False)
    plugin_name: str = ""  # �����������
    version: str = "1.0.0"  # 适配器版本
    platform: str = "unknown"  # 平台名称
    description: str = ""  # 适配器描述
    enabled: bool = True  # 是否启用
    run_in_subprocess: bool = False  # 是否在子进程中运行
    subprocess_entry: str | None = None  # 子进程入口脚本


@dataclass
class ComponentInfo:
    """组件信息"""

    name: str  # 组件名称
    component_type: ComponentType  # 组件类型
    description: str = ""  # 组件描述
    enabled: bool = True  # 是否启用
    plugin_name: str = ""  # 所属插件名称
    is_built_in: bool = False  # 是否为内置组件
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ActionInfo(ComponentInfo):
    """动作组件信息

    注意：激活类型相关字段已废弃，推荐使用 Action 类的 go_activate() 方法来自定义激活逻辑。
    这些字段将继续保留以提供向后兼容性，BaseAction.go_activate() 的默认实现会使用这些字段。
    """

    action_parameters: dict[str, str] = field(
        default_factory=dict
    )  # 动作参数与描述，例如 {"param1": "描述1", "param2": "描述2"}
    action_require: list[str] = field(default_factory=list)  # 动作需求说明
    associated_types: list[str] = field(default_factory=list)  # 关联的消息类型

    # ==================================================================================
    # 激活类型相关字段（已废弃，建议使用 go_activate() 方法）
    # 保留这些字段是为了向后兼容，BaseAction.go_activate() 的默认实现会使用这些字段
    # ==================================================================================
    focus_activation_type: ActionActivationType = ActionActivationType.ALWAYS  # 已废弃
    normal_activation_type: ActionActivationType = ActionActivationType.ALWAYS  # 已废弃
    activation_type: ActionActivationType = ActionActivationType.ALWAYS  # 已废弃
    random_activation_probability: float = 0.0  # 已废弃，建议在 go_activate() 中使用 _random_activation()
    llm_judge_prompt: str = ""  # 已废弃，建议在 go_activate() 中使用 _llm_judge_activation()
    activation_keywords: list[str] = field(default_factory=list)  # 已废弃，建议在 go_activate() 中使用 _keyword_match()
    keyword_case_sensitive: bool = False  # 已废弃

    # 模式和并行设置
    mode_enable: ChatMode = ChatMode.ALL
    parallel_action: bool = False
    chat_type_allow: ChatType = ChatType.ALL  # 允许的聊天类型
    chatter_allow: list[str] = field(default_factory=list)  # 允许的 Chatter 列表，空则允许所有
    # 二步Action相关属性
    is_two_step_action: bool = False  # 是否为二步Action
    step_one_description: str = ""  # 第一步的描述
    sub_actions: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)  # 子Action列表

    def __post_init__(self):
        super().__post_init__()
        if self.activation_keywords is None:
            self.activation_keywords = []
        if self.action_parameters is None:
            self.action_parameters = {}
        if self.action_require is None:
            self.action_require = []
        if self.associated_types is None:
            self.associated_types = []
        if self.sub_actions is None:
            self.sub_actions = []
        if self.chatter_allow is None:
            self.chatter_allow = []
        self.component_type = ComponentType.ACTION


@dataclass
class CommandInfo(ComponentInfo):
    """命令组件信息"""

    command_pattern: str = ""  # 命令匹配模式（正则表达式）
    chat_type_allow: ChatType = ChatType.ALL  # 允许的聊天类型

    def __post_init__(self):
        super().__post_init__()
        self.component_type = ComponentType.COMMAND


@dataclass
class PlusCommandInfo(ComponentInfo):
    """增强命令组件信息"""

    command_aliases: list[str] = field(default_factory=list)  # 命令别名列表
    priority: int = 0  # 命令优先级
    chat_type_allow: ChatType = ChatType.ALL  # 允许的聊天类型
    intercept_message: bool = False  # 是否拦截消息

    def __post_init__(self):
        super().__post_init__()
        if self.command_aliases is None:
            self.command_aliases = []
        self.component_type = ComponentType.PLUS_COMMAND


@dataclass
class ToolInfo(ComponentInfo):
    """工具组件信息"""

    tool_parameters: list[tuple[str, ToolParamType, str, bool, list[str] | None]] = field(
        default_factory=list
    )  # 工具参数定义
    tool_description: str = ""  # 工具描述

    def __post_init__(self):
        super().__post_init__()
        self.component_type = ComponentType.TOOL


@dataclass
class EventHandlerInfo(ComponentInfo):
    """事件处理器组件信息"""

    event_type: EventType = EventType.ON_MESSAGE  # 监听事件类型
    intercept_message: bool = False  # 是否拦截消息处理（默认不拦截）
    weight: int = 0  # 事件处理器权重，决定执行顺序

    def __post_init__(self):
        super().__post_init__()
        self.component_type = ComponentType.EVENT_HANDLER


@dataclass
class ChatterInfo(ComponentInfo):
    """聊天处理器组件信息"""

    chat_type_allow: ChatType = ChatType.ALL  # 允许的聊天类型

    def __post_init__(self):
        super().__post_init__()
        self.component_type = ComponentType.CHATTER


@dataclass
class EventInfo(ComponentInfo):
    """事件组件信息"""

    def __post_init__(self):
        super().__post_init__()
        self.component_type = ComponentType.EVENT_HANDLER


@dataclass
class PromptInfo(ComponentInfo):
    """Prompt组件信息"""

    injection_rules: list[InjectionRule] = field(default_factory=list)
    """定义此组件如何注入到其他Prompt中"""

    # 旧的injection_point，用于向后兼容
    injection_point: str | list[str] | None = None

    def __post_init__(self):
        super().__post_init__()
        self.component_type = ComponentType.PROMPT

        # 向后兼容逻辑：如果定义了旧的 injection_point，则自动转换为新的 injection_rules
        if self.injection_point:
            if not self.injection_rules:  # 仅当rules为空时转换
                points = []
                if isinstance(self.injection_point, str):
                    points.append(self.injection_point)
                elif isinstance(self.injection_point, list):
                    points = self.injection_point

                for point in points:
                    self.injection_rules.append(InjectionRule(target_prompt=point))
            # 转换后可以清空旧字段，避免混淆
            self.injection_point = None


@dataclass
class PluginInfo:
    """插件信息"""

    display_name: str  # 插件显示名称
    name: str  # 插件名称
    description: str  # 插件描述
    version: str = "1.0.0"  # 插件版本
    author: str = ""  # 插件作者
    enabled: bool = True  # 是否启用
    is_built_in: bool = False  # 是否为内置插件
    components: list[ComponentInfo] = field(default_factory=list)  # 包含的组件列表
    dependencies: list[str] = field(default_factory=list)  # 依赖的其他插件
    python_dependencies: list[str | PythonDependency] = field(default_factory=list)  # Python包依赖
    config_file: str = ""  # 配置文件路径
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据
    # 新增：manifest相关信息
    manifest_data: dict[str, Any] = field(default_factory=dict)  # manifest文件数据
    license: str = ""  # 插件许可证
    homepage_url: str = ""  # 插件主页
    repository_url: str = ""  # 插件仓库地址
    keywords: list[str] = field(default_factory=list)  # 插件关键词
    categories: list[str] = field(default_factory=list)  # 插件分类
    min_host_version: str = ""  # 最低主机版本要求
    max_host_version: str = ""  # 最高主机版本要求

    def __post_init__(self):
        if self.components is None:
            self.components = []
        if self.dependencies is None:
            self.dependencies = []
        if self.python_dependencies is None:
            self.python_dependencies = []
        if self.metadata is None:
            self.metadata = {}
        if self.manifest_data is None:
            self.manifest_data = {}
        if self.keywords is None:
            self.keywords = []
        if self.categories is None:
            self.categories = []

    def get_missing_packages(self) -> list[PythonDependency]:
        """检查缺失的Python包"""
        missing = []
        for dep in self.python_dependencies:
            dep_obj = dep if isinstance(dep, PythonDependency) else PythonDependency(package_name=dep)
            try:
                __import__(dep_obj.package_name)
            except ImportError:
                if not dep_obj.optional:
                    missing.append(dep_obj)
        return missing

    def get_pip_requirements(self) -> list[str]:
        """获取所有pip安装格式的依赖"""
        requirements = []
        for dep in self.python_dependencies:
            if isinstance(dep, str):
                requirements.append(dep)
            elif isinstance(dep, PythonDependency):
                requirements.append(dep.get_pip_requirement())
        return requirements


@dataclass
class RouterInfo(ComponentInfo):
    """路由组件信息"""

    def __post_init__(self):
        super().__post_init__()
        self.component_type = ComponentType.ROUTER
