"""
Anthropic 格式透传代理服务

提供：
- 构造上游请求头
- 非流式请求透传
- 流式请求透传
- Token 使用量提取
"""
import json
from typing import Dict, Any, AsyncGenerator, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from models.provider import Provider, ApiFormat
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from services.encryption import decrypt


# 需要透传的请求头
FORWARD_HEADERS = [
    "anthropic-version",
    "anthropic-beta",
    "content-type",
]

# 需要删除的逐跳头
HOP_BY_HOP_HEADERS = [
    "host",
    "connection",
    "transfer-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
]


# Anthropic 模型前缀到供应商的映射
ANTHROPIC_MODEL_ROUTE_RULES = [
    ("claude-", "anthropic"),    # claude-sonnet-4-*, claude-opus-* 等
    ("glm-", "zhipu"),           # glm-5, glm-4.* 等
    ("minimax-", "minimax"),     # minimax-m2.5 等
]


async def resolve_provider(model: str, db: AsyncSession) -> Provider:
    """
    根据模型名称前缀查找对应的 Anthropic 兼容供应商

    Args:
        model: 模型名称
        db: 数据库 session

    Returns:
        Provider 对象

    Raises:
        ValueError: 找不到匹配的供应商
    """
    for prefix, provider_name in ANTHROPIC_MODEL_ROUTE_RULES:
        if model.startswith(prefix):
            result = await db.execute(
                select(Provider).where(
                    Provider.name == provider_name,
                    Provider.enabled == True
                )
            )
            provider = result.scalar_one_or_none()
            if provider:
                return provider

    raise ValueError(f"Model '{model}' not found or not enabled")


async def get_provider_key(
    provider: Provider,
    db: AsyncSession
) -> Tuple[ProviderApiKey, str]:
    """
    获取供应商的可用 API Key

    Args:
        provider: 供应商对象
        db: 数据库 session

    Returns:
        (ProviderApiKey, decrypted_key)

    Raises:
        ValueError: 没有可用的 API Key
    """
    result = await db.execute(
        select(ProviderApiKey).where(
            ProviderApiKey.provider_id == provider.id,
            ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
        ).order_by(ProviderApiKey.created_at)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise ValueError(f"No active API key for provider '{provider.name}'")

    decrypted_key = decrypt(api_key.encrypted_key)
    return api_key, decrypted_key


def build_upstream_headers(
    request_headers: Dict[str, str],
    vendor_key: str
) -> Dict[str, str]:
    """
    构造转发给上游的请求头

    - 删除原始的 authorization / x-api-key（平台 Key）
    - 新增 x-api-key: {vendor_key}（解密后的供应商 Key）
    - 透传：anthropic-version、anthropic-beta、content-type

    Args:
        request_headers: 原始请求头
        vendor_key: 解密后的供应商 API Key

    Returns:
        构造好的上游请求头
    """
    headers = {}

    # 透传需要的头部
    for header_name in FORWARD_HEADERS:
        # 头部名大小写不敏感
        for key, value in request_headers.items():
            if key.lower() == header_name.lower():
                headers[header_name] = value
                break

    # 设置供应商 Key（Anthropic 格式使用 x-api-key）
    headers["x-api-key"] = vendor_key

    return headers


def extract_usage_from_response(response_body: dict) -> Tuple[int, int]:
    """
    从非流式 Anthropic 响应提取 token 使用量

    Args:
        response_body: Anthropic 格式的响应体

    Returns:
        (input_tokens, output_tokens)
    """
    usage = response_body.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    return input_tokens, output_tokens


def extract_usage_from_sse_event(event_data: str) -> Tuple[int, int]:
    """
    从 SSE 事件数据提取 token 使用量

    - message_start 事件包含 input_tokens
    - message_delta 事件包含 output_tokens

    Args:
        event_data: SSE 事件的 data 部分（JSON 字符串）

    Returns:
        (input_tokens, output_tokens) - 如果该事件不包含 usage，返回 (0, 0)
    """
    try:
        data = json.loads(event_data)

        if data.get("type") == "message_start":
            message = data.get("message", {})
            usage = message.get("usage", {})
            return usage.get("input_tokens", 0), 0

        elif data.get("type") == "message_delta":
            usage = data.get("usage", {})
            return 0, usage.get("output_tokens", 0)

    except (json.JSONDecodeError, TypeError):
        pass

    return 0, 0


async def proxy_request_non_stream(
    upstream_url: str,
    headers: Dict[str, str],
    body: bytes
) -> Tuple[httpx.Response, Dict[str, Any]]:
    """
    非流式请求透传

    Args:
        upstream_url: 上游 URL
        headers: 请求头
        body: 请求体（原始字节）

    Returns:
        (httpx.Response, parsed_body)

    Raises:
        httpx.TimeoutException: 请求超时
        httpx.HTTPStatusError: 上游返回错误
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            upstream_url,
            headers=headers,
            content=body
        )
        response.raise_for_status()
        return response, response.json()


async def proxy_request_stream(
    upstream_url: str,
    headers: Dict[str, str],
    body: bytes
) -> AsyncGenerator[bytes, None]:
    """
    流式请求透传

    Args:
        upstream_url: 上游 URL
        headers: 请求头
        body: 请求体（原始字节）

    Yields:
        SSE 格式的数据块
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            upstream_url,
            headers=headers,
            content=body
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk


def make_anthropic_error(
    error_type: str,
    message: str
) -> Dict[str, Any]:
    """
    构造 Anthropic 格式的错误响应

    Args:
        error_type: 错误类型
        message: 错误信息

    Returns:
        Anthropic 格式的错误响应字典
    """
    return {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message
        }
    }
