"""
插件基础类模块

提供插件开发的基础类和类型定义
"""

from .base_action import BaseAction
from .base_adapter import BaseAdapter
from .base_command import BaseCommand
from .base_events_handler import BaseEventHandler
from .base_http_component import BaseRouterComponent
from .base_plugin import BasePlugin
from .base_prompt import BasePrompt
from .base_router import BaseRouter
from .base_service import BaseService
from .base_tool import BaseTool
from .command_args import CommandArgs
from .component_types import (
    ActionActivationType,
    ActionInfo,
    AdapterInfo,
    ChatMode,
    ChatType,
    CommandInfo,
    ComponentInfo,
    ComponentSignature,
    ComponentType,
    EventHandlerInfo,
    EventType,
    InjectionRule,
    InjectionType,
    PluginInfo,
    PlusCommandInfo,
    PythonDependency,
    RouterInfo,
    ServiceInfo,
    ToolInfo,
    ToolParamType,
    build_signature,
    parse_signature,
    parse_signature_opt,
)
from .config_types import ConfigField
from .plugin_metadata import PluginMetadata
from .plus_command import PlusCommand, create_plus_command_adapter

__all__ = [
    "ActionActivationType",
    "ActionInfo",
    "AdapterInfo",
    "BaseAction",
    "BaseAdapter",
    "BaseCommand",
    "BaseEventHandler",
    "BasePlugin",
    "BasePrompt",
    "BaseRouter",
    "BaseRouterComponent",
    "BaseService",
    "BaseTool",
    "ChatMode",
    "ChatType",
    "CommandArgs",
    "CommandInfo",
    "ComponentInfo",
    "ComponentSignature",
    "ComponentType",
    "ConfigField",
    "EventHandlerInfo",
    "EventType",
    "InjectionRule",
    "InjectionType",
    "PluginInfo",
    "PluginMetadata",
    # 增强命令系统
    "PlusCommand",
    "PlusCommandInfo",
    "PythonDependency",
    "RouterInfo",
    "ServiceInfo",
    "ToolInfo",
    "ToolParamType",
    "build_signature",
    "create_plus_command_adapter",
    "parse_signature",
    "parse_signature_opt",
]
