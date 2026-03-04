"""
API 模型发现服务

从供应商 API 发现模型，作为本地 ModelCatalog 的可选补充。

主要用途：
1. 验证 API Key 有效性
2. 发现 models.dev 未收录的模型

注意：此服务作为补充方法，本地 ModelCatalog 才是模型数据的单一真相来源（SSOT）。
"""
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

import httpx

from services.provider_presets import ProviderPreset


logger = logging.getLogger(__name__)


class UnsupportedDiscoveryError(Exception):
    """不支持模型发现的供应商"""
    pass


class DiscoveryUpstreamError(Exception):
    """上游供应商 API 错误"""
    pass


@dataclass
class DiscoveredModelInfo:
    """发现的模型信息"""
    model_id: str
    display_name: str
    input_price: Decimal = Decimal("0")
    output_price: Decimal = Decimal("0")
    cache_read_price: Optional[Decimal] = None
    cache_write_price: Optional[Decimal] = None
    context_window: Optional[int] = None
    max_output: Optional[int] = None
    supports_vision: bool = False
    supports_tools: bool = True
    supports_reasoning: bool = False
    # 来源标识
    from_api: bool = True  # 标记来自 API 发现


@dataclass
class DiscoveryResult:
    """模型发现结果"""
    success: bool
    models: List[DiscoveredModelInfo] = field(default_factory=list)
    total_count: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None


async def discover_models_from_api(
    preset: ProviderPreset,
    api_key: str,
    base_url: str,
    timeout: float = 30.0
) -> DiscoveryResult:
    """
    从供应商 API 发现模型（可选补充方法）

    用于：
    1. 验证 API Key 是否有效
    2. 发现 models.dev 未收录的模型

    Args:
        preset: 供应商预设
        api_key: API Key
        base_url: API 基础 URL
        timeout: 请求超时时间（秒）

    Returns:
        DiscoveryResult: 发现结果，包含模型列表和错误信息
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if preset.api_format == "anthropic":
                models = await _fetch_anthropic_models(client, base_url, api_key)
            else:
                # OpenAI 兼容格式
                models = await _fetch_openai_models(client, base_url, api_key)

            return DiscoveryResult(
                success=True,
                models=models,
                total_count=len(models)
            )

    except httpx.TimeoutException:
        return DiscoveryResult(
            success=False,
            error_type="timeout",
            error_message="请求超时"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            return DiscoveryResult(
                success=False,
                error_type="invalid_key",
                error_message="API Key 无效或已过期"
            )
        return DiscoveryResult(
            success=False,
            error_type="api_error",
            error_message=f"API 错误: {e.response.status_code}"
        )
    except httpx.HTTPError as e:
        logger.error(f"Discovery HTTP error: {e}")
        return DiscoveryResult(
            success=False,
            error_type="network_error",
            error_message=f"网络错误: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during model discovery: {e}")
        return DiscoveryResult(
            success=False,
            error_type="unknown",
            error_message=f"未知错误: {str(e)}"
        )


async def _fetch_openai_models(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str
) -> List[DiscoveredModelInfo]:
    """
    从 OpenAI 兼容 API 获取模型列表

    Args:
        client: HTTP 客户端
        base_url: API 基础 URL
        api_key: API Key

    Returns:
        模型列表

    Raises:
        httpx.HTTPStatusError: API 错误
    """
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    response = await client.get(url, headers=headers)
    response.raise_for_status()

    data = response.json()
    raw_models = data.get("data", [])

    # 处理某些 API 返回字典格式的情况
    if isinstance(raw_models, dict):
        raw_models = [{"id": k, **v} for k, v in raw_models.items()]

    models = []
    for m in raw_models:
        model_id = m.get("id", m.get("model_id", ""))
        if not model_id:
            continue

        # 过滤掉非 chat 模型（简化处理）
        # 实际的 chat 模型判断可以在后续处理
        models.append(DiscoveredModelInfo(
            model_id=model_id,
            display_name=m.get("name", m.get("display_name", model_id)),
            context_window=m.get("context_window"),
            supports_vision=m.get("supports_vision", False),
            supports_tools=m.get("supports_tools", True),
        ))

    return models


async def _fetch_anthropic_models(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str
) -> List[DiscoveredModelInfo]:
    """
    从 Anthropic API 获取模型列表（支持分页）

    Args:
        client: HTTP 客户端
        base_url: API 基础 URL
        api_key: API Key

    Returns:
        模型列表

    Raises:
        httpx.HTTPStatusError: API 错误
    """
    url = f"{base_url.rstrip('/')}/v1/models"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }

    all_models = []
    after_id = None

    while True:
        params = {}
        if after_id:
            params["after"] = after_id
            params["limit"] = 100

        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        models = data.get("data", [])

        for model in models:
            model_id = model.get("id", "")
            if model_id:
                all_models.append(DiscoveredModelInfo(
                    model_id=model_id,
                    display_name=model.get("display_name", model_id),
                ))

        # 检查是否还有更多数据
        has_more = data.get("has_more", False)
        if has_more and models:
            after_id = models[-1].get("id")
            if not after_id:
                break
        else:
            break

    return all_models


def discovered_model_to_dict(model: DiscoveredModelInfo) -> dict:
    """将发现的模型转换为字典格式"""
    return {
        "model_id": model.model_id,
        "display_name": model.display_name,
        "input_price": float(model.input_price),
        "output_price": float(model.output_price),
        "cache_read_price": float(model.cache_read_price) if model.cache_read_price else None,
        "cache_write_price": float(model.cache_write_price) if model.cache_write_price else None,
        "context_window": model.context_window,
        "supports_vision": model.supports_vision,
        "supports_tools": model.supports_tools,
        "supports_reasoning": model.supports_reasoning,
        "from_api": model.from_api,
    }
