"""
Kokoro Flow Chatter - 配置

可以通过 TOML 配置文件覆盖默认值

支持两种工作模式：
- unified: 统一模式，单次 LLM 调用完成思考和回复生成（类似旧版架构）
- split: 分离模式，Planner + Replyer 两次 LLM 调用（推荐，更精细的控制）
"""

from dataclasses import dataclass, field
from enum import Enum


class KFCMode(str, Enum):
    """KFC 工作模式"""

    # 统一模式：单次 LLM 调用，生成思考 + 回复（类似旧版架构）
    UNIFIED = "unified"

    # 分离模式：Planner 生成规划，Replyer 生成回复（推荐）
    SPLIT = "split"

    @classmethod
    def from_str(cls, value: str) -> "KFCMode":
        """从字符串创建模式"""
        value = value.lower().strip()
        if value == "unified":
            return cls.UNIFIED
        elif value == "split":
            return cls.SPLIT
        else:
            # 默认使用统一模式
            return cls.UNIFIED


@dataclass
class WaitingDefaults:
    """等待配置默认值"""

    # 默认最大等待时间（秒）
    default_max_wait_seconds: int = 300

    # 最小等待时间
    min_wait_seconds: int = 30

    # 最大等待时间
    max_wait_seconds: int = 1800

    # 等待时长倍率（>1 放大等待时间，<1 缩短）
    wait_duration_multiplier: float = 1.0

    # 连续等待超时上限（达到后不再继续等待，0 表示不限制）
    max_consecutive_timeouts: int = 3


@dataclass
class ProactiveConfig:
    """主动思考配置"""

    # 是否启用主动思考
    enabled: bool = True

    # 沉默阈值（秒），超过此时间考虑主动发起
    silence_threshold_seconds: int = 7200

    # 两次主动发起最小间隔（秒）
    min_interval_between_proactive: int = 1800

    # 勿扰时段开始（HH:MM 格式）
    quiet_hours_start: str = "23:00"

    # 勿扰时段结束
    quiet_hours_end: str = "07:00"

    # 主动发起概率（0.0 ~ 1.0）
    trigger_probability: float = 0.3

    # 关系门槛：最低好感度，达到此值才会主动关心
    min_affinity_for_proactive: float = 0.3


@dataclass
class PromptConfig:
    """提示词配置"""

    # 活动记录保留条数
    max_activity_entries: int = 30

    # 每条记录最大字符数
    max_entry_length: int = 500

    # 活动流格式：narrative（线性叙事）/ table（结构化表格）/ both（两者都给）
    # - narrative: 更自然，但信息密度较低，长时更容易丢细节
    # - table: 更高信息密度，便于模型对齐字段、检索与对比
    # - both: 调试/对照用，token 更高
    activity_stream_format: str = "narrative"

    # 是否包含人物关系信息
    include_relation: bool = True

    # 是否包含记忆信息
    include_memory: bool = True


@dataclass
class SessionConfig:
    """会话配置"""

    # Session 持久化目录（相对于 data/）
    session_dir: str = "kokoro_flow_chatter/sessions"

    # Session 自动过期时间（秒），超过此时间未活动自动清理
    session_expire_seconds: int = 86400 * 7  # 7 天

    # 活动记录保留上限
    max_mental_log_entries: int = 100


@dataclass
class LLMConfig:
    """LLM 配置"""

    # 模型名称（空则使用默认）
    model_name: str = ""

    # Temperature
    temperature: float = 0.8

    # 最大 Token
    max_tokens: int = 1024

    # 请求超时（秒）
    timeout: float = 60.0


@dataclass
class KokoroFlowChatterConfig:
    """Kokoro Flow Chatter 总配置"""

    # 是否启用
    enabled: bool = True

    # 工作模式：unified（统一模式）或 split（分离模式）
    # - unified: 单次 LLM 调用完成思考和回复生成（类似旧版架构，更简洁）
    # - split: Planner + Replyer 两次 LLM 调用（更精细的控制，推荐）
    mode: KFCMode = KFCMode.UNIFIED

    # 启用的消息源类型（空列表表示全部）
    enabled_stream_types: list[str] = field(default_factory=lambda: ["private"])

    # 等待配置
    waiting: WaitingDefaults = field(default_factory=WaitingDefaults)

    # 主动思考配置
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)

    # 提示词配置
    prompt: PromptConfig = field(default_factory=PromptConfig)

    # 会话配置
    session: SessionConfig = field(default_factory=SessionConfig)

    # LLM 配置
    llm: LLMConfig = field(default_factory=LLMConfig)

    # 自定义决策提示词
    custom_decision_prompt: str = ""

    # 极速模式配置
    fast_mode_enabled: bool = False

    # 调试模式
    debug: bool = False


# 全局配置单例
_config: KokoroFlowChatterConfig | None = None


def get_config() -> KokoroFlowChatterConfig:
    """获取全局配置"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def load_config() -> KokoroFlowChatterConfig:
    """
    加载 KFC 配置

    加载逻辑：
    1. 先从插件自身的 config.toml 加载（如果存在）
    2. 再从全局配置 global_config.kokoro_flow_chatter 加载
    3. 全局配置中的项会覆盖插件自身配置中的同名项
    """
    from src.config.config import global_config

    config = KokoroFlowChatterConfig()

    # --- 1. 从插件自身配置文件加载 ---
    try:
        from pathlib import Path

        import tomlkit

        # 插件配置目录通常在 config/plugins/kokoro_flow_chatter/config.toml
        plugin_cfg_path = Path("config/plugins/kokoro_flow_chatter/config.toml")
        if plugin_cfg_path.exists():
            with open(plugin_cfg_path, encoding="utf-8") as f:
                plugin_data = tomlkit.load(f).unwrap()

            # 简单映射插件配置文件的值到 config 对象
            # 插件基础设置
            if "plugin" in plugin_data and isinstance(plugin_data["plugin"], dict):
                p = plugin_data["plugin"]
                if "enabled" in p:
                    config.enabled = bool(p["enabled"])

            # 核心功能设置
            if "main" in plugin_data and isinstance(plugin_data["main"], dict):
                m = plugin_data["main"]
                if "mode" in m:
                    config.mode = KFCMode.from_str(str(m["mode"]))
                if "fast_mode_enabled" in m:
                    config.fast_mode_enabled = bool(m["fast_mode_enabled"])
                if "custom_decision_prompt" in m:
                    config.custom_decision_prompt = str(m["custom_decision_prompt"])

            # 等待配置
            if "waiting" in plugin_data and isinstance(plugin_data["waiting"], dict):
                w = plugin_data["waiting"]
                config.waiting.default_max_wait_seconds = w.get("default_max_wait_seconds", config.waiting.default_max_wait_seconds)
                config.waiting.min_wait_seconds = w.get("min_wait_seconds", config.waiting.min_wait_seconds)
                config.waiting.max_wait_seconds = w.get("max_wait_seconds", config.waiting.max_wait_seconds)
                config.waiting.wait_duration_multiplier = float(w.get("wait_duration_multiplier", config.waiting.wait_duration_multiplier))
                config.waiting.max_consecutive_timeouts = int(w.get("max_consecutive_timeouts", config.waiting.max_consecutive_timeouts))

            # 主动思考配置
            if "proactive" in plugin_data and isinstance(plugin_data["proactive"], dict):
                p = plugin_data["proactive"]
                config.proactive.enabled = bool(p.get("enabled", config.proactive.enabled))
                config.proactive.silence_threshold_seconds = int(p.get("silence_threshold_seconds", config.proactive.silence_threshold_seconds))
                config.proactive.min_interval_between_proactive = int(p.get("min_interval_between_proactive", config.proactive.min_interval_between_proactive))
                config.proactive.quiet_hours_start = str(p.get("quiet_hours_start", config.proactive.quiet_hours_start))
                config.proactive.quiet_hours_end = str(p.get("quiet_hours_end", config.proactive.quiet_hours_end))
                config.proactive.trigger_probability = float(p.get("trigger_probability", config.proactive.trigger_probability))
                config.proactive.min_affinity_for_proactive = float(p.get("min_affinity_for_proactive", config.proactive.min_affinity_for_proactive))

    except Exception as e:
        from src.common.logger import get_logger
        logger = get_logger("kfc_config")
        logger.warning(f"从插件配置文件加载失败: {e}")

    # --- 2. 从全局配置覆盖 ---
    if not global_config:
        return config

    try:
        if hasattr(global_config, "kokoro_flow_chatter"):
            kfc_cfg = getattr(global_config, "kokoro_flow_chatter")

            # 基础配置 - 支持 enabled 和 enable 两种写法
            if hasattr(kfc_cfg, "enable"):
                config.enabled = kfc_cfg.enable
            if hasattr(kfc_cfg, "enabled_stream_types"):
                config.enabled_stream_types = list(kfc_cfg.enabled_stream_types)
            if hasattr(kfc_cfg, "debug"):
                config.debug = kfc_cfg.debug

            # 工作模式配置
            if hasattr(kfc_cfg, "mode"):
                config.mode = KFCMode.from_str(str(kfc_cfg.mode))

            # 等待配置
            if hasattr(kfc_cfg, "waiting"):
                wait_cfg = kfc_cfg.waiting
                config.waiting = WaitingDefaults(
                    default_max_wait_seconds=getattr(wait_cfg, "default_max_wait_seconds", config.waiting.default_max_wait_seconds),
                    min_wait_seconds=getattr(wait_cfg, "min_wait_seconds", config.waiting.min_wait_seconds),
                    max_wait_seconds=getattr(wait_cfg, "max_wait_seconds", config.waiting.max_wait_seconds),
                    wait_duration_multiplier=getattr(wait_cfg, "wait_duration_multiplier", config.waiting.wait_duration_multiplier),
                    max_consecutive_timeouts=getattr(wait_cfg, "max_consecutive_timeouts", config.waiting.max_consecutive_timeouts),
                )

            # 主动思考配置 - 支持 proactive 和 proactive_thinking 两种写法
            pro_cfg = None
            if hasattr(kfc_cfg, "proactive_thinking"):
                pro_cfg = kfc_cfg.proactive_thinking

            if pro_cfg:
                config.proactive = ProactiveConfig(
                    enabled=getattr(pro_cfg, "enabled", config.proactive.enabled),
                    silence_threshold_seconds=getattr(pro_cfg, "silence_threshold_seconds", config.proactive.silence_threshold_seconds),
                    min_interval_between_proactive=getattr(pro_cfg, "min_interval_between_proactive", config.proactive.min_interval_between_proactive),
                    quiet_hours_start=getattr(pro_cfg, "quiet_hours_start", config.proactive.quiet_hours_start),
                    quiet_hours_end=getattr(pro_cfg, "quiet_hours_end", config.proactive.quiet_hours_end),
                    trigger_probability=getattr(pro_cfg, "trigger_probability", config.proactive.trigger_probability),
                    min_affinity_for_proactive=getattr(pro_cfg, "min_affinity_for_proactive", config.proactive.min_affinity_for_proactive),
                )

            # 提示词配置
            if hasattr(kfc_cfg, "prompt"):
                pmt_cfg = kfc_cfg.prompt
                config.prompt = PromptConfig(
                    max_activity_entries=getattr(pmt_cfg, "max_activity_entries", config.prompt.max_activity_entries),
                    max_entry_length=getattr(pmt_cfg, "max_entry_length", config.prompt.max_entry_length),
                    activity_stream_format=getattr(
                        pmt_cfg,
                        "activity_stream_format",
                        getattr(pmt_cfg, "activity_format", config.prompt.activity_stream_format),
                    ),
                    include_relation=getattr(pmt_cfg, "include_relation", config.prompt.include_relation),
                    include_memory=getattr(pmt_cfg, "include_memory", config.prompt.include_memory),
                )

            # 会话配置
            if hasattr(kfc_cfg, "session"):
                sess_cfg = kfc_cfg.session
                config.session = SessionConfig(
                    session_dir=getattr(sess_cfg, "session_dir", config.session.session_dir),
                    session_expire_seconds=getattr(sess_cfg, "session_expire_seconds", config.session.session_expire_seconds),
                    max_mental_log_entries=getattr(sess_cfg, "max_mental_log_entries", config.session.max_mental_log_entries),
                )

            # LLM 配置
            if hasattr(kfc_cfg, "llm"):
                llm_cfg = kfc_cfg.llm
                config.llm = LLMConfig(
                    model_name=getattr(llm_cfg, "model_name", config.llm.model_name),
                    temperature=getattr(llm_cfg, "temperature", config.llm.temperature),
                    max_tokens=getattr(llm_cfg, "max_tokens", config.llm.max_tokens),
                    timeout=getattr(llm_cfg, "timeout", config.llm.timeout),
                )

            # 自定义决策提示词配置
            if hasattr(kfc_cfg, "custom_decision_prompt"):
                config.custom_decision_prompt = str(kfc_cfg.custom_decision_prompt)

            # 极速模式配置
            if hasattr(kfc_cfg, "fast_mode_enabled"):
                config.fast_mode_enabled = bool(kfc_cfg.fast_mode_enabled)

    except Exception as e:
        from src.common.logger import get_logger
        logger = get_logger("kfc_config")
        logger.warning(f"加载 KFC 配置失败，使用默认值: {e}")

    return config


def reload_config() -> KokoroFlowChatterConfig:
    """重新加载配置"""
    global _config
    _config = load_config()
    return _config


def apply_wait_duration_rules(raw_wait_seconds: int, consecutive_timeouts: int = 0) -> int:
    """根据配置计算最终的等待时间"""
    if raw_wait_seconds <= 0:
        return 0

    waiting_cfg = get_config().waiting
    multiplier = max(waiting_cfg.wait_duration_multiplier, 0.0)
    if multiplier == 0:
        return 0

    adjusted = round(raw_wait_seconds * multiplier)

    min_wait = max(0, waiting_cfg.min_wait_seconds)
    max_wait = max(waiting_cfg.max_wait_seconds, 0)

    if max_wait > 0 and min_wait > 0 and max_wait < min_wait:
        max_wait = min_wait

    if max_wait > 0:
        adjusted = min(adjusted, max_wait)
    if min_wait > 0:
        adjusted = max(adjusted, min_wait)

    adjusted = max(adjusted, 0)

    timeout_limit = max(0, waiting_cfg.max_consecutive_timeouts)
    if timeout_limit and consecutive_timeouts >= timeout_limit:
        return 0

    return adjusted
