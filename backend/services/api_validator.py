"""
API Key 验证服务

独立的 API Key 验证功能，与模型发现分离。
用于验证供应商 API Key 是否有效。
"""
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from services.provider_presets import ProviderPreset


logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """API Key 验证结果"""
    valid: bool
    error_type: Optional[str] = None  # "invalid_key", "network_error", "timeout", "unsupported"
    error_message: Optional[str] = None


async def validate_api_key(
    preset: ProviderPreset,
    api_key: str,
    base_url: str,
    timeout: float = 10.0
) -> ValidationResult:
    """
    验证 API Key 是否有效

    通过轻量级 API 调用验证 Key 有效性。
    对于不支持验证的供应商，返回 valid=True（跳过验证）。

    Args:
        preset: 供应商预设
        api_key: API Key
        base_url: API 基础 URL
        timeout: 请求超时时间（秒）

    Returns:
        ValidationResult: 验证结果
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if preset.api_format == "anthropic":
                # Anthropic 格式 - 使用 /v1/models 端点
                response = await client.get(
                    f"{base_url.rstrip('/')}/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01"
                    }
                )
            else:
                # OpenAI 格式 - 使用 /models 端点
                response = await client.get(
                    f"{base_url.rstrip('/')}/models",
                    headers={
                        "Authorization": f"Bearer {api_key}"
                    }
                )

            if response.status_code == 200:
                return ValidationResult(valid=True)

            if response.status_code == 401:
                return ValidationResult(
                    valid=False,
                    error_type="invalid_key",
                    error_message="API Key 无效或已过期"
                )

            if response.status_code == 403:
                return ValidationResult(
                    valid=False,
                    error_type="invalid_key",
                    error_message="API Key 权限不足"
                )

            if response.status_code == 404:
                # /models 端点不存在，但 Key 可能仍然有效
                # 这种情况下我们假设 Key 是有效的
                logger.info(f"Provider {preset.name} does not support /models endpoint, skipping validation")
                return ValidationResult(valid=True)

            # 其他错误
            return ValidationResult(
                valid=False,
                error_type="api_error",
                error_message=f"API 返回错误: {response.status_code}"
            )

    except httpx.TimeoutException:
        return ValidationResult(
            valid=False,
            error_type="timeout",
            error_message="请求超时"
        )
    except httpx.ConnectError as e:
        return ValidationResult(
            valid=False,
            error_type="network_error",
            error_message=f"无法连接到服务器: {str(e)}"
        )
    except httpx.HTTPError as e:
        logger.error(f"API validation error: {e}")
        return ValidationResult(
            valid=False,
            error_type="network_error",
            error_message=f"网络错误: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during API validation: {e}")
        return ValidationResult(
            valid=False,
            error_type="unknown",
            error_message=f"未知错误: {str(e)}"
        )
