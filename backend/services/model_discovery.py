"""
模型发现服务

从供应商 API 自动发现可用模型
"""
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from models.provider import Provider, ApiFormat
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from models.model_catalog import ModelCatalog, ModelStatus, ModelSource
from services.encryption import decrypt
from services.model_pricing_defaults import (
    get_default_pricing,
    has_confirmed_pricing,
    is_chat_model
)


class UnsupportedDiscoveryError(Exception):
    """不支持模型发现的供应商"""
    pass


class DiscoveryUpstreamError(Exception):
    """上游供应商 API 错误"""
    pass


@dataclass
class DiscoveryResult:
    """模型发现结果"""
    discovered: int = 0      # 发现的模型总数
    new_models: int = 0      # 新增的模型数（之前不在 catalog 中）
    pricing_matched: int = 0 # 匹配到内置定价的模型数
    pricing_pending: int = 0 # 待确认定价的模型数
    details: list = field(default_factory=list)  # 详细信息列表

    def to_dict(self):
        return asdict(self)


class ModelDiscoveryService:
    """模型发现服务"""

    def __init__(self, timeout: int = 10):
        """
        初始化

        Args:
            timeout: HTTP 请求超时时间（秒）
        """
        self.timeout = timeout

    async def discover_models(
        self,
        provider: Provider,
        api_key: ProviderApiKey,
        db: AsyncSession
    ) -> DiscoveryResult:
        """
        从供应商发现模型

        Args:
            provider: 供应商对象
            api_key: 供应商 API Key 对象
            db: 数据库 session

        Returns:
            DiscoveryResult 发现结果

        Raises:
            UnsupportedDiscoveryError: 不支持模型发现
            DiscoveryUpstreamError: 上游 API 错误
        """
        # 解密 API Key
        decrypted_key = decrypt(api_key.encrypted_key)

        # 根据供应商 API 格式选择发现方法
        if provider.api_format == ApiFormat.OPENAI:
            models = await self._fetch_openai_models(provider.base_url, decrypted_key)
        elif provider.api_format == ApiFormat.ANTHROPIC:
            models = await self._fetch_anthropic_models(provider.base_url, decrypted_key)
        else:
            raise UnsupportedDiscoveryError(
                f"Provider '{provider.name}' with api_format '{provider.api_format}' "
                f"does not support model discovery"
            )

        # 合并到模型目录
        return await self._merge_into_catalog(models, provider, db)

    async def _fetch_openai_models(
        self,
        base_url: str,
        api_key: str
    ) -> List[Dict[str, Any]]:
        """
        从 OpenAI 兼容 API 获取模型列表

        Args:
            base_url: API 基础 URL
            api_key: API Key

        Returns:
            模型列表

        Raises:
            DiscoveryUpstreamError: 上游 API 错误
        """
        url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)

                if response.status_code >= 500:
                    raise DiscoveryUpstreamError(
                        f"Upstream error: {response.status_code}"
                    )
                if response.status_code >= 400:
                    raise DiscoveryUpstreamError(
                        f"Upstream error: {response.status_code}"
                    )

                data = response.json()
                models = data.get("data", [])

                # 过滤出 Chat 模型
                chat_models = []
                for model in models:
                    model_id = model.get("id", "")
                    if is_chat_model(model_id):
                        chat_models.append({
                            "model_id": model_id,
                            "display_name": model.get("id", model_id),
                            "owned_by": model.get("owned_by", "unknown"),
                        })

                return chat_models

            except httpx.TimeoutException:
                raise DiscoveryUpstreamError("Upstream timeout")
            except httpx.HTTPError as e:
                raise DiscoveryUpstreamError(f"HTTP error: {str(e)}")

    async def _fetch_anthropic_models(
        self,
        base_url: str,
        api_key: str
    ) -> List[Dict[str, Any]]:
        """
        从 Anthropic API 获取模型列表（支持分页）

        Args:
            base_url: API 基础 URL
            api_key: API Key

        Returns:
            模型列表

        Raises:
            DiscoveryUpstreamError: 上游 API 错误
        """
        url = f"{base_url.rstrip('/')}/v1/models"
        headers = {"x-api-key": api_key}

        all_models = []
        after_id = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while True:
                try:
                    params = {}
                    if after_id:
                        params["after"] = after_id
                        params["limit"] = 100

                    response = await client.get(url, headers=headers, params=params)

                    if response.status_code >= 500:
                        raise DiscoveryUpstreamError(
                            f"Upstream error: {response.status_code}"
                        )
                    if response.status_code >= 400:
                        raise DiscoveryUpstreamError(
                            f"Upstream error: {response.status_code}"
                        )

                    data = response.json()
                    models = data.get("data", [])

                    for model in models:
                        model_id = model.get("id", "")
                        if is_chat_model(model_id):
                            all_models.append({
                                "model_id": model_id,
                                "display_name": model.get("display_name", model_id),
                                "owned_by": "anthropic",
                            })

                    # 检查是否还有更多数据
                    has_more = data.get("has_more", False)
                    if has_more and models:
                        after_id = models[-1].get("id")
                        if not after_id:
                            break
                    else:
                        break

                except httpx.TimeoutException:
                    raise DiscoveryUpstreamError("Upstream timeout")
                except httpx.HTTPError as e:
                    raise DiscoveryUpstreamError(f"HTTP error: {str(e)}")

        return all_models

    async def _merge_into_catalog(
        self,
        models: List[Dict[str, Any]],
        provider: Provider,
        db: AsyncSession
    ) -> DiscoveryResult:
        """
        将发现的模型合并到模型目录

        Args:
            models: 发现的模型列表
            provider: 供应商对象
            db: 数据库 session

        Returns:
            DiscoveryResult 合并结果
        """
        result = DiscoveryResult(discovered=len(models))

        for model_info in models:
            model_id = model_info["model_id"]
            display_name = model_info.get("display_name", model_id)

            # 检查模型是否已存在
            existing = await db.execute(
                select(ModelCatalog).where(ModelCatalog.model_id == model_id)
            )
            if existing.scalar_one_or_none():
                result.details.append({
                    "model_id": model_id,
                    "status": "skipped",
                    "reason": "already_exists"
                })
                continue

            # 获取默认定价
            default_pricing = get_default_pricing(model_id)
            pricing_confirmed = has_confirmed_pricing(model_id)

            # 创建模型目录条目
            # 自动发现的模型直接激活，无需管理员审核
            if default_pricing:
                catalog_entry = ModelCatalog(
                    model_id=model_id,
                    display_name=default_pricing.get("display_name", display_name),
                    provider_id=provider.id,
                    input_price=Decimal(str(default_pricing.get("input_price", 0))),
                    output_price=Decimal(str(default_pricing.get("output_price", 0))),
                    context_window=default_pricing.get("context_window"),
                    max_output=default_pricing.get("max_output"),
                    supports_vision=default_pricing.get("supports_vision", False),
                    supports_tools=default_pricing.get("supports_tools", True),
                    status=ModelStatus.ACTIVE,  # 自动激活
                    is_pricing_confirmed=pricing_confirmed,
                    source=ModelSource.BUILTIN_DEFAULT if pricing_confirmed else ModelSource.AUTO_DISCOVERED,
                )
                if pricing_confirmed:
                    result.pricing_matched += 1
                else:
                    result.pricing_pending += 1
            else:
                catalog_entry = ModelCatalog(
                    model_id=model_id,
                    display_name=display_name,
                    provider_id=provider.id,
                    input_price=Decimal("0"),
                    output_price=Decimal("0"),
                    status=ModelStatus.ACTIVE,  # 自动激活
                    is_pricing_confirmed=False,
                    source=ModelSource.AUTO_DISCOVERED,
                )
                result.pricing_pending += 1

            db.add(catalog_entry)
            result.new_models += 1
            result.details.append({
                "model_id": model_id,
                "status": "added",
                "pricing_confirmed": pricing_confirmed
            })

        await db.commit()
        return result


# 单例服务实例
_discovery_service: Optional[ModelDiscoveryService] = None


def get_discovery_service() -> ModelDiscoveryService:
    """获取模型发现服务单例"""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = ModelDiscoveryService()
    return _discovery_service
