"""
供应商预设服务

提供标准供应商的配置预设，简化供应商创建流程。
"""
from dataclasses import dataclass
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


# 供应商预设列表
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
    "zhipu": ProviderPreset(
        id="zhipu",
        name="zhipu",
        display_name="智谱 AI",
        api_format="openai_compatible",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        supported_endpoints=["openai", "anthropic"],
        supports_cache_pricing=False,
        description="GLM 系列模型",
    ),
    "deepseek": ProviderPreset(
        id="deepseek",
        name="deepseek",
        display_name="DeepSeek",
        api_format="openai_compatible",
        default_base_url="https://api.deepseek.com",
        supported_endpoints=["openai"],
        supports_cache_pricing=True,
        description="DeepSeek 系列，支持缓存 Token",
    ),
    "minimax": ProviderPreset(
        id="minimax",
        name="minimax",
        display_name="MiniMax",
        api_format="openai_compatible",
        default_base_url="https://api.minimax.chat/v1",
        supported_endpoints=["openai", "anthropic"],
        supports_cache_pricing=False,
        description="MiniMax 系列模型",
    ),
    "moonshot": ProviderPreset(
        id="moonshot",
        name="moonshot",
        display_name="Moonshot",
        api_format="openai_compatible",
        default_base_url="https://api.moonshot.cn/v1",
        supported_endpoints=["openai"],
        supports_cache_pricing=False,
        description="Kimi 系列模型",
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
    "qwen": ProviderPreset(
        id="qwen",
        name="qwen",
        display_name="通义千问",
        api_format="openai_compatible",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        supported_endpoints=["openai"],
        supports_cache_pricing=False,
        description="阿里云通义千问系列",
    ),
    "google": ProviderPreset(
        id="google",
        name="google",
        display_name="Google AI",
        api_format="openai_compatible",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        supported_endpoints=["openai"],
        supports_cache_pricing=False,
        description="Gemini 系列模型",
    ),
    "mistral": ProviderPreset(
        id="mistral",
        name="mistral",
        display_name="Mistral",
        api_format="openai_compatible",
        default_base_url="https://api.mistral.ai/v1",
        supported_endpoints=["openai"],
        supports_cache_pricing=False,
        description="Mistral 系列模型",
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
    }
