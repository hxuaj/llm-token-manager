"""
网关代理服务

提供：
- 模型路由（根据 model 前缀）
- 供应商 Key 选择
- 请求转发
- 响应转换
"""
import json
from typing import Dict, Any, AsyncGenerator, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from models.model_pricing import ModelPricing
from services.encryption import decrypt
from services.providers.base import BaseAdapter
from services.providers.openai_adapter import OpenAIAdapter
from services.providers.anthropic_adapter import AnthropicAdapter
from services.providers.qwen_adapter import QwenAdapter
from services.providers.openrouter_adapter import OpenRouterAdapter


# 模型前缀到供应商的映射
MODEL_PREFIX_TO_PROVIDER = {
    "gpt-": "openai",
    "o1-": "openai",
    "o3-": "openai",
    "claude-": "anthropic",
    "qwen-": "qwen",
    "ernie-": "ernie",
    # OpenRouter 模型格式: provider/model-name
    "openai/": "openrouter",
    "anthropic/": "openrouter",
    "google/": "openrouter",
    "meta-llama/": "openrouter",
    "deepseek/": "openrouter",
    "mistralai/": "openrouter",
    "qwen/": "openrouter",
    "01-ai/": "openrouter",
    "phind/": "openrouter",
    "codellama/": "openrouter",
    "nousresearch/": "openrouter",
    "x-ai/": "openrouter",
    "perplexity/": "openrouter",
}


def get_provider_name_by_model(model: str) -> Optional[str]:
    """
    根据模型名称确定供应商

    Args:
        model: 模型名称

    Returns:
        供应商名称，如果无法确定则返回 None
    """
    for prefix, provider in MODEL_PREFIX_TO_PROVIDER.items():
        if model.startswith(prefix):
            return provider
    return None


def create_adapter(provider_name: str, base_url: str, api_key: str) -> BaseAdapter:
    """
    创建供应商适配器

    Args:
        provider_name: 供应商名称
        base_url: API 基础 URL
        api_key: API Key

    Returns:
        适配器实例
    """
    adapters = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "qwen": QwenAdapter,
        "openrouter": OpenRouterAdapter,
    }

    adapter_class = adapters.get(provider_name, OpenAIAdapter)
    return adapter_class(base_url, api_key)


async def get_provider_and_key(
    provider_name: str,
    db: AsyncSession
) -> Optional[Tuple[Provider, ProviderApiKey, str]]:
    """
    获取供应商和可用的 API Key

    Args:
        provider_name: 供应商名称
        db: 数据库 session

    Returns:
        (Provider, ProviderApiKey, decrypted_key) 或 None
    """
    # 查询供应商
    result = await db.execute(
        select(Provider).where(
            Provider.name == provider_name,
            Provider.enabled == True
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        return None

    # 查询可用的 API Key
    result = await db.execute(
        select(ProviderApiKey).where(
            ProviderApiKey.provider_id == provider.id,
            ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
        ).order_by(ProviderApiKey.created_at)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None

    # 解密 Key
    decrypted_key = decrypt(api_key.encrypted_key)

    return provider, api_key, decrypted_key


async def forward_request(
    model: str,
    request: Dict[str, Any],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    转发请求到对应的供应商

    Args:
        model: 模型名称
        request: OpenAI 格式请求
        db: 数据库 session

    Returns:
        OpenAI 格式响应

    Raises:
        ValueError: 无法确定供应商或没有可用 Key
        Exception: 供应商返回错误
    """
    # 确定供应商
    provider_name = get_provider_name_by_model(model)
    if not provider_name:
        raise ValueError(f"Unknown model: {model}")

    # 获取供应商和 Key
    result = await get_provider_and_key(provider_name, db)
    if not result:
        raise ValueError(f"Provider '{provider_name}' not configured or no active keys")

    provider, api_key_record, decrypted_key = result

    # 创建适配器
    adapter = create_adapter(provider_name, provider.base_url, decrypted_key)

    # 转换请求（OpenAI 适配器会直接返回原请求）
    provider_request = adapter.convert_request(request)

    # 转发请求
    stream = request.get("stream", False)
    response = await adapter.forward_request(provider_request, stream)

    # 转换响应
    openai_response = adapter.convert_response(response, model)

    return openai_response


async def forward_request_stream(
    model: str,
    request: Dict[str, Any],
    db: AsyncSession
) -> AsyncGenerator[bytes, None]:
    """
    转发流式请求到对应的供应商

    Args:
        model: 模型名称
        request: OpenAI 格式请求
        db: 数据库 session

    Yields:
        SSE 格式的数据块

    Raises:
        ValueError: 无法确定供应商或没有可用 Key
    """
    # 确定供应商
    provider_name = get_provider_name_by_model(model)
    if not provider_name:
        raise ValueError(f"Unknown model: {model}")

    # 获取供应商和 Key
    result = await get_provider_and_key(provider_name, db)
    if not result:
        raise ValueError(f"Provider '{provider_name}' not configured or no active keys")

    provider, api_key_record, decrypted_key = result

    # 创建适配器
    adapter = create_adapter(provider_name, provider.base_url, decrypted_key)

    # 转换请求
    provider_request = adapter.convert_request(request)

    # 转发流式请求
    async for chunk in adapter.forward_stream(provider_request):
        yield chunk


async def check_model_access(
    model: str,
    allowed_models: Optional[str]
) -> bool:
    """
    检查用户是否有权访问该模型

    Args:
        model: 模型名称
        allowed_models: 用户允许的模型列表（JSON 字符串），None 表示不限制

    Returns:
        是否有权访问
    """
    if allowed_models is None:
        return True

    try:
        models_list = json.loads(allowed_models)
        return model in models_list
    except (json.JSONDecodeError, TypeError):
        return True  # 解析失败时不限制


async def get_available_models(db: AsyncSession) -> list:
    """
    获取所有可用的模型列表

    Args:
        db: 数据库 session

    Returns:
        模型列表
    """
    result = await db.execute(
        select(ModelPricing, Provider)
        .join(Provider, ModelPricing.provider_id == Provider.id)
        .where(Provider.enabled == True)
    )
    rows = result.all()

    models = []
    for pricing, provider in rows:
        models.append({
            "id": pricing.model_name,
            "object": "model",
            "created": int(pricing.created_at.timestamp()),
            "owned_by": provider.name
        })

    return models
