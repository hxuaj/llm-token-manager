"""
供应商预设服务

提供标准供应商的配置预设，简化供应商创建流程。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProviderPreset:
    """供应商预设"""
    id: str
    name: str
    display_name: str
    api_format: str  # "openai", "anthropic", "openai_compatible"
    default_base_url: str
    supported_endpoints: List[str]  # ["openai"], ["openai", "anthropic"]
    supports_cache_pricing: bool = False
    description: str = ""
    # Coding Plan 相关配置
    is_coding_plan: bool = False  # 是否为 Coding Plan 类型
    coding_plan_models: List[str] = field(default_factory=list)  # Coding Plan 支持的模型列表
    # models.dev 中的供应商 ID（用于获取定价信息）
    # 如果为 None，则使用 name 字段
    models_dev_id: Optional[str] = None


# 供应商预设列表（精简为 5 个常用供应商）
PROVIDER_PRESETS: Dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        id="openai",
        name="openai",
        display_name="OpenAI",
        api_format="openai",
        default_base_url="https://api.openai.com/v1",
        supported_endpoints=["openai"],
        supports_cache_pricing=True,
        description="GPT-4, GPT-4o, o1 等模型",
    ),
    "anthropic": ProviderPreset(
        id="anthropic",
        name="anthropic",
        display_name="Anthropic",
        api_format="anthropic",
        default_base_url="https://api.anthropic.com",
        supported_endpoints=["openai", "anthropic"],
        supports_cache_pricing=True,
        description="Claude 系列模型",
    ),
    "zhipuai-coding-plan": ProviderPreset(
        id="zhipuai-coding-plan",
        name="zhipu",
        display_name="Zhipu AI Coding Plan",
        api_format="openai_compatible",
        default_base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        supported_endpoints=["openai", "anthropic"],
        supports_cache_pricing=True,
        description="智谱 AI Coding Plan 订阅，包含 GLM-5, GLM-4.7, GLM-4.6 等模型",
        is_coding_plan=True,
        coding_plan_models=[
            "glm-5",
            "glm-4.7",
            "glm-4.6",
            "glm-4.5",
            "glm-4.5-air",
            "glm-4.5-flash",
            "glm-4.6v",
            "glm-4.6v-flash",
            "glm-4.5v",
        ],
        # Coding Plan 定价在 models.dev 中是 0，使用标准定价作为参考
        models_dev_id="zhipuai",
    ),
    "minimax-cn-coding-plan": ProviderPreset(
        id="minimax-cn-coding-plan",
        name="minimax",
        display_name="MiniMax Coding Plan (minimaxi.com)",
        api_format="openai_compatible",
        default_base_url="https://api.minimaxi.com/anthropic/v1",
        supported_endpoints=["openai", "anthropic"],
        supports_cache_pricing=True,
        description="MiniMax Coding Plan 订阅（中国区），包含 MiniMax-M2.5, MiniMax-M2.1 等模型",
        is_coding_plan=True,
        coding_plan_models=[
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2",
        ],
    ),
    "openrouter": ProviderPreset(
        id="openrouter",
        name="openrouter",
        display_name="OpenRouter",
        api_format="openai_compatible",
        default_base_url="https://openrouter.ai/api/v1",
        supported_endpoints=["openai"],
        supports_cache_pricing=False,
        description="聚合平台，支持多种模型",
    ),
}


def get_preset(preset_id: str) -> Optional[ProviderPreset]:
    """获取供应商预设"""
    return PROVIDER_PRESETS.get(preset_id)


def get_all_presets() -> List[ProviderPreset]:
    """获取所有供应商预设"""
    return list(PROVIDER_PRESETS.values())


def preset_to_dict(preset: ProviderPreset) -> dict:
    """将预设转换为字典"""
    return {
        "id": preset.id,
        "name": preset.name,
        "display_name": preset.display_name,
        "api_format": preset.api_format,
        "default_base_url": preset.default_base_url,
        "supported_endpoints": preset.supported_endpoints,
        "supports_anthropic": "anthropic" in preset.supported_endpoints,
        "supports_cache_pricing": preset.supports_cache_pricing,
        "description": preset.description,
        "is_coding_plan": preset.is_coding_plan,
        "coding_plan_models": preset.coding_plan_models,
        "models_dev_id": preset.models_dev_id or preset.name,
    }


def get_models_dev_id(preset: ProviderPreset) -> str:
    """获取预设对应的 models.dev 供应商 ID"""
    return preset.models_dev_id or preset.name
