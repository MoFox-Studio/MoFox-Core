from threading import Lock
from typing import Any, Literal

from pydantic import Field, PrivateAttr

from src.config.config_base import ValidatedConfigBase
from src.config.official_configs import InnerConfig


class APIProvider(ValidatedConfigBase):
    """API提供商配置类"""

    name: str = Field(..., min_length=1, description="API提供商名称")
    base_url: str = Field(..., description="API基础URL")
    api_key: str | list[str] = Field(..., min_length=1, description="API密钥，支持单个密钥或密钥列表轮询")
    client_type: Literal["openai", "gemini", "aiohttp_gemini", "bedrock"] = Field(
        default="openai", description="客户端类型（如openai/google/bedrock等，默认为openai）"
    )
    max_retry: int = Field(default=2, ge=0, description="最大重试次数（单个模型API调用失败，最多重试的次数）")
    timeout: int = Field(
        default=10, ge=1, description="API调用的超时时长（超过这个时长，本次请求将被视为'请求超时'，单位：秒）"
    )
    retry_interval: int = Field(default=10, ge=0, description="重试间隔（如果API调用失败，重试的间隔时间，单位：秒）")

    _api_key_lock: Lock = PrivateAttr(default_factory=Lock)
    _api_key_index: int = PrivateAttr(default=0)

    @classmethod
    def validate_base_url(cls, v):
        """验证base_url，确保URL格式正确"""
        if v and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url必须以http://或https://开头")
        return v

    @classmethod
    def validate_api_key(cls, v):
        """验证API密钥不能为空"""
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("API密钥不能为空")
        elif isinstance(v, list):
            if not v:
                raise ValueError("API密钥列表不能为空")
            for key in v:
                if not isinstance(key, str) or not key.strip():
                    raise ValueError("API密钥列表中的密钥不能为空")
        else:
            raise ValueError("API密钥必须是字符串或字符串列表")
        return v

    def get_api_key(self) -> str:
        with self._api_key_lock:
            if isinstance(self.api_key, str):
                return self.api_key
            if not self.api_key:
                raise ValueError("API密钥列表为空")
            key = self.api_key[self._api_key_index]
            self._api_key_index = (self._api_key_index + 1) % len(self.api_key)
            return key


class ModelInfo(ValidatedConfigBase):
    """单个模型信息配置类"""

    model_identifier: str = Field(..., min_length=1, description="模型标识符（用于URL调用）")
    name: str = Field(..., min_length=1, description="模型名称（用于模块调用）")
    api_provider: str = Field(..., min_length=1, description="API提供商（如OpenAI、Azure等）")
    price_in: float = Field(default=0.0, ge=0, description="每M token输入价格")
    price_out: float = Field(default=0.0, ge=0, description="每M token输出价格")
    force_stream_mode: bool = Field(default=False, description="是否强制使用流式输出模式")
    extra_params: dict[str, Any] = Field(default_factory=dict, description="额外参数（用于API调用时的额外配置）")
    anti_truncation: bool = Field(default=False, alias="use_anti_truncation", description="是否启用反截断功能，防止模型输出被截断")
    enable_prompt_perturbation: bool = Field(default=False, description="是否启用提示词扰动（合并了内容混淆和注意力优化）")
    perturbation_strength: Literal["light", "medium", "heavy"] = Field(
        default="light", description="扰动强度（light/medium/heavy）"
    )
    enable_semantic_variants: bool = Field(default=False, description="是否启用语义变体作为扰动策略")
    @classmethod
    def validate_prices(cls, v):
        """验证价格必须为非负数"""
        if v < 0:
            raise ValueError("价格不能为负数")
        return v

    @classmethod
    def validate_model_identifier(cls, v):
        """验证模型标识符不能为空且不能包含特殊字符"""
        if not v or not v.strip():
            raise ValueError("模型标识符不能为空")
        # 检查是否包含危险字符
        if any(char in v for char in [" ", "\n", "\t", "\r"]):
            raise ValueError("模型标识符不能包含空格或换行符")
        return v

    @classmethod
    def validate_name(cls, v):
        """验证模型名称不能为空"""
        if not v or not v.strip():
            raise ValueError("模型名称不能为空")
        return v


class TaskConfig(ValidatedConfigBase):
    """任务配置类"""

    model_list: list[str] = Field(..., description="任务使用的模型列表")
    max_tokens: int = Field(default=800, description="任务最大输出token数")
    temperature: float = Field(default=0.7, description="模型温度")
    concurrency_count: int = Field(default=1, description="并发请求数量")
    embedding_dimension: int | None = Field(
        default=None,
        description="嵌入模型输出向量维度，仅在嵌入任务中使用",
        ge=1,
    )

    @classmethod
    def validate_model_list(cls, v):
        """验证模型列表不能为空"""
        if not v:
            raise ValueError("模型列表不能为空")
        if len(v) != len(set(v)):
            raise ValueError("模型列表中不能有重复的模型")
        return v


class ModelTaskConfig(ValidatedConfigBase):
    """模型配置类"""

    # 必需配置项
    utils: TaskConfig = Field(..., description="组件模型配置")
    utils_small: TaskConfig = Field(..., description="组件小模型配置")
    replyer: TaskConfig = Field(..., description="normal_chat首要回复模型模型配置（群聊使用）")
    replyer_private: TaskConfig = Field(..., description="normal_chat首要回复模型模型配置（私聊使用）")
    maizone: TaskConfig = Field(..., description="maizone专用模型")
    emotion: TaskConfig = Field(..., description="情绪模型配置")
    mood: TaskConfig = Field(..., description="心情模型配置")
    vlm: TaskConfig = Field(..., description="视觉语言模型配置")
    voice: TaskConfig = Field(..., description="语音识别模型配置")
    tool_use: TaskConfig = Field(..., description="专注工具使用模型配置")
    planner: TaskConfig = Field(..., description="规划模型配置")
    embedding: TaskConfig = Field(..., description="嵌入模型配置")
    lpmm_entity_extract: TaskConfig = Field(..., description="LPMM实体提取模型配置")
    lpmm_rdf_build: TaskConfig = Field(..., description="LPMM RDF构建模型配置")
    lpmm_qa: TaskConfig = Field(..., description="LPMM问答模型配置")
    schedule_generator: TaskConfig = Field(..., description="日程生成模型配置")
    monthly_plan_generator: TaskConfig = Field(..., description="月层计划生成模型配置")
    emoji_vlm: TaskConfig = Field(..., description="表情包识别模型配置")
    anti_injection: TaskConfig = Field(..., description="反注入检测专用模型配置")
    relationship_tracker: TaskConfig = Field(..., description="关系追踪模型配置")
    # 处理配置文件中命名不一致的问题
    utils_video: TaskConfig = Field(..., description="视频分析模型配置（兼容配置文件中的命名）")

    # 记忆系统专用模型配置
    memory_short_term_builder: TaskConfig = Field(..., description="短期记忆构建模型配置（感知→短期格式化）")
    memory_short_term_decider: TaskConfig = Field(..., description="短期记忆决策模型配置（合并/更新/新建/丢弃）")
    memory_long_term_builder: TaskConfig = Field(..., description="长期记忆构建模型配置（短期→长期图结构）")
    memory_judge: TaskConfig = Field(..., description="记忆检索裁判模型配置（判断检索是否充足）")

    @property
    def video_analysis(self) -> TaskConfig:
        """视频分析模型配置（提供向后兼容的属性访问）"""
        return self.utils_video

    def get_task(self, task_name: str) -> TaskConfig:
        """获取指定任务的配置"""
        # 处理向后兼容性：如果请求video_analysis，返回utils_video
        if task_name == "video_analysis":
            task_name = "utils_video"

        if hasattr(self, task_name):
            config = getattr(self, task_name)
            if config is None:
                raise ValueError(f"任务 '{task_name}' 未配置")
            return config
        raise ValueError(f"任务 '{task_name}' 未找到对应的配置")


class ModelSelectorConfig(ValidatedConfigBase):
    """模型选择器配置类"""

    critical_penalty_multiplier: float = Field(
        default=5.0, ge=0, description="严重错误惩罚乘数（网络错误、服务器错误等）"
    )
    default_penalty_increment: float = Field(
        default=1.0, ge=0, description="默认惩罚增量（普通错误）"
    )
    latency_weight: float = Field(
        default=200.0, ge=0, description="延迟权重（延迟在负载均衡中的影响权重）"
    )
    penalty_weight: float = Field(
        default=300.0, ge=0, description="失败惩罚权重（失败次数在负载均衡中的影响权重）"
    )
    usage_penalty_weight: float = Field(
        default=1000.0, ge=0, description="使用惩罚权重（短期使用频率在负载均衡中的影响权重）"
    )


class APIAdapterConfig(ValidatedConfigBase):
    """API Adapter配置类"""

    inner: InnerConfig = Field(..., description="配置元信息")
    models: list[ModelInfo] = Field(..., min_length=1, description="模型列表")
    model_task_config: ModelTaskConfig = Field(..., description="模型任务配置")
    api_providers: list[APIProvider] = Field(..., min_length=1, description="API提供商列表")
    model_selector: ModelSelectorConfig = Field(
        default_factory=ModelSelectorConfig, description="模型选择器配置"
    )

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
