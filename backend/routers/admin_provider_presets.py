"""
管理员 - 供应商预设配置路由

提供供应商预设、验证和快捷创建功能。
注意：这个路由文件需要注册在 admin.router 之前，
否则 /providers/presets 会被 /providers/{provider_id} 匹配。
"""
import uuid
import logging
from decimal import Decimal
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.user import User
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from middleware.auth import get_current_admin_user
from services.encryption import encrypt, extract_key_suffix
from services.model_discovery import UnsupportedDiscoveryError, DiscoveryUpstreamError

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型
# ─────────────────────────────────────────────────────────────────────

class ProviderPresetResponse(BaseModel):
    """供应商预设响应"""
    id: str
    name: str
    display_name: str
    api_format: str
    default_base_url: str
    supported_endpoints: List[str]
    supports_anthropic: bool
    supports_cache_pricing: bool
    description: str


class ValidateKeyRequest(BaseModel):
    """验证 Key 请求"""
    provider_preset: str
    api_key: str
    custom_base_url: Optional[str] = None


class DiscoveredModel(BaseModel):
    """发现的模型"""
    model_id: str
    display_name: str
    input_price: float
    output_price: float
    cache_read_price: Optional[float] = None
    cache_write_price: Optional[float] = None
    pricing_source: str  # "models_dev", "builtin", "unknown"
    context_window: Optional[int] = None
    supports_vision: bool = False
    supports_tools: bool = True
    supports_reasoning: bool = False


class ValidateKeyResponse(BaseModel):
    """验证 Key 响应"""
    valid: bool
    provider_preset: Optional[str] = None
    auto_config: Optional[dict] = None
    discovered_models: Optional[List[DiscoveredModel]] = None
    summary: Optional[dict] = None
    error: Optional[dict] = None


class QuickCreateRequest(BaseModel):
    """一键创建请求"""
    provider_preset: str
    api_key: str
    key_plan: str = "standard"
    rpm_limit: Optional[int] = None
    custom_base_url: Optional[str] = None
    auto_activate_models: bool = True


class QuickCreateResponse(BaseModel):
    """一键创建响应"""
    provider: dict
    api_key: dict
    discovery_result: dict


# ─────────────────────────────────────────────────────────────────────
# API 接口
# ─────────────────────────────────────────────────────────────────────

@router.get("/providers/presets")
async def list_provider_presets(
    admin_user: User = Depends(get_current_admin_user)
):
    """获取供应商预设列表"""
    from services.provider_presets import get_all_presets, preset_to_dict

    presets = get_all_presets()
    return {
        "presets": [preset_to_dict(p) for p in presets]
    }


@router.post("/providers/validate-key", response_model=ValidateKeyResponse)
async def validate_provider_key(
    data: ValidateKeyRequest,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    验证 API Key 并发现可用模型

    1. 验证预设是否存在
    2. 调用供应商的 /models 端点获取模型列表
    3. 从 models.dev 获取定价信息（如果可用）
    """
    from services.provider_presets import get_preset, get_models_dev_id
    from services.models_dev_service import get_models_dev_service

    # 获取预设
    preset = get_preset(data.provider_preset)
    if not preset:
        return ValidateKeyResponse(
            valid=False,
            error={"type": "invalid_preset", "message": f"Unknown preset: {data.provider_preset}"}
        )

    # 获取 models.dev 供应商 ID
    models_dev_provider_id = get_models_dev_id(preset)

    # 确定使用的 base_url
    base_url = data.custom_base_url or preset.default_base_url

    try:
        # 直接调用供应商的 /models 端点获取模型列表
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            if preset.api_format == "anthropic":
                # Anthropic 格式
                response = await client.get(
                    f"{base_url}/v1/models",
                    headers={
                        "x-api-key": data.api_key,
                        "anthropic-version": "2023-06-01"
                    }
                )
            else:
                # OpenAI 格式
                response = await client.get(
                    f"{base_url}/models",
                    headers={
                        "Authorization": f"Bearer {data.api_key}"
                    }
                )

            response.raise_for_status()
            result = response.json()

        # 解析模型列表
        raw_models = result.get("data", result.get("models", []))
        if isinstance(raw_models, dict):
            raw_models = [{"id": k, **v} for k, v in raw_models.items()]

        models = []
        for m in raw_models:
            model_id = m.get("id", m.get("model_id", ""))
            if model_id:
                models.append({
                    "model_id": model_id,
                    "display_name": m.get("name", m.get("display_name", model_id)),
                })

        # 获取 models.dev 定价信息
        models_dev = get_models_dev_service()
        discovered_models = []
        pricing_confirmed = 0
        pricing_pending = 0

        for model in models:
            model_id = model.get("model_id", model.get("id", ""))

            # 尝试从 models.dev 获取定价
            pricing_source = "unknown"
            input_price = model.get("input_price", 0)
            output_price = model.get("output_price", 0)
            cache_read_price = model.get("cache_read_price")
            cache_write_price = model.get("cache_write_price")

            try:
                dev_model = await models_dev.get_model(models_dev_provider_id, model_id)
                if dev_model:
                    cost = dev_model.get("cost", {})
                    if cost:
                        input_price = cost.get("input", input_price)
                        output_price = cost.get("output", output_price)
                        cache_read_price = cost.get("cache_read", cache_read_price)
                        cache_write_price = cost.get("cache_write", cache_write_price)
                        pricing_source = "models_dev"
                        pricing_confirmed += 1
            except Exception:
                pass

            if pricing_source == "unknown":
                pricing_pending += 1

            discovered_models.append(DiscoveredModel(
                model_id=model_id,
                display_name=model.get("display_name", model_id),
                input_price=input_price,
                output_price=output_price,
                cache_read_price=cache_read_price,
                cache_write_price=cache_write_price,
                pricing_source=pricing_source,
                context_window=model.get("context_window"),
                supports_vision=model.get("supports_vision", False),
                supports_tools=model.get("supports_tools", True),
                supports_reasoning=model.get("supports_reasoning", False),
            ))

        return ValidateKeyResponse(
            valid=True,
            provider_preset=data.provider_preset,
            auto_config={
                "base_url": base_url,
                "api_format": preset.api_format,
                "supported_endpoints": preset.supported_endpoints,
            },
            discovered_models=discovered_models,
            summary={
                "total_models": len(discovered_models),
                "pricing_confirmed": pricing_confirmed,
                "pricing_pending": pricing_pending,
            }
        )

    except UnsupportedDiscoveryError as e:
        return ValidateKeyResponse(
            valid=False,
            error={"type": "unsupported", "message": str(e)}
        )
    except DiscoveryUpstreamError as e:
        return ValidateKeyResponse(
            valid=False,
            error={"type": "invalid_api_key", "message": "API Key 无效或已过期"}
        )
    except Exception as e:
        logger.error(f"Key validation failed: {e}")
        return ValidateKeyResponse(
            valid=False,
            error={"type": "validation_error", "message": str(e)[:200]}
        )


@router.post("/providers/quick-create", response_model=QuickCreateResponse, status_code=status.HTTP_201_CREATED)
async def quick_create_provider(
    data: QuickCreateRequest,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    一键创建供应商

    1. 创建供应商记录
    2. 添加 API Key
    3. 发现并激活模型
    """
    from services.provider_presets import get_preset, get_models_dev_id
    from services.models_dev_service import get_models_dev_service

    # 获取预设
    preset = get_preset(data.provider_preset)
    if not preset:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {data.provider_preset}")

    # 获取 models.dev 供应商 ID
    models_dev_provider_id = get_models_dev_id(preset)

    # 检查供应商是否已存在
    result = await db.execute(select(Provider).where(Provider.name == preset.name))
    existing_provider = result.scalar_one_or_none()
    if existing_provider:
        raise HTTPException(status_code=409, detail=f"Provider '{preset.name}' already exists")

    # 确定使用的 base_url
    base_url = data.custom_base_url or preset.default_base_url

    # 创建供应商
    provider = Provider(
        name=preset.name,
        display_name=preset.display_name,
        base_url=base_url,
        api_format=preset.api_format,
        enabled=True,
        source="preset",
        models_dev_id=preset.name,
        supported_endpoints=preset.supported_endpoints,
    )
    db.add(provider)
    await db.flush()  # 获取 provider.id

    # 创建 API Key
    encrypted_key = encrypt(data.api_key)
    key_suffix = extract_key_suffix(data.api_key)

    provider_key = ProviderApiKey(
        provider_id=provider.id,
        encrypted_key=encrypted_key,
        key_suffix=key_suffix,
        status=ProviderKeyStatus.ACTIVE.value,
        key_plan=data.key_plan,
        rpm_limit=data.rpm_limit or 0,
    )
    db.add(provider_key)
    await db.flush()

    # 发现模型
    total_models = 0
    activated_models = 0
    pricing_confirmed = 0

    try:
        # 直接调用供应商 API 获取模型列表
        async with httpx.AsyncClient(timeout=30.0) as client:
            if preset.api_format == "anthropic":
                response = await client.get(
                    f"{base_url}/v1/models",
                    headers={
                        "x-api-key": data.api_key,
                        "anthropic-version": "2023-06-01"
                    }
                )
            else:
                response = await client.get(
                    f"{base_url}/models",
                    headers={
                        "Authorization": f"Bearer {data.api_key}"
                    }
                )

            response.raise_for_status()
            result = response.json()

        # 解析模型列表
        raw_models = result.get("data", result.get("models", []))
        if isinstance(raw_models, dict):
            raw_models = [{"id": k, **v} for k, v in raw_models.items()]

        total_models = len(raw_models)
        models_dev = get_models_dev_service()

        for m in raw_models:
            model_id = m.get("id", m.get("model_id", ""))
            if not model_id:
                continue

            display_name = m.get("name", m.get("display_name", model_id))

            # 获取定价（从 models.dev）
            input_price = Decimal("0")
            output_price = Decimal("0")
            cache_read_price = None
            cache_write_price = None
            is_pricing_confirmed = False

            try:
                dev_model = await models_dev.get_model(models_dev_provider_id, model_id)
                if dev_model:
                    cost = dev_model.get("cost", {})
                    if cost and (cost.get("input", 0) > 0 or cost.get("output", 0) > 0):
                        input_price = Decimal(str(cost.get("input", 0)))
                        output_price = Decimal(str(cost.get("output", 0)))
                        if cost.get("cache_read"):
                            cache_read_price = Decimal(str(cost["cache_read"]))
                        if cost.get("cache_write"):
                            cache_write_price = Decimal(str(cost["cache_write"]))
                        is_pricing_confirmed = True
                        pricing_confirmed += 1
            except Exception:
                pass

            # 创建模型目录记录（如果自动激活）
            if data.auto_activate_models:
                from models.model_catalog import ModelCatalog, ModelStatus, ModelSource

                catalog = ModelCatalog(
                    model_id=model_id,
                    display_name=display_name,
                    provider_id=provider.id,
                    input_price=input_price,
                    output_price=output_price,
                    cache_read_price=cache_read_price,
                    cache_write_price=cache_write_price,
                    context_window=m.get("context_window"),
                    supports_vision=m.get("supports_vision", False),
                    supports_tools=m.get("supports_tools", True),
                    status=ModelStatus.ACTIVE,
                    source=ModelSource.AUTO_DISCOVERED,
                    models_dev_id=model_id,
                    is_pricing_confirmed=is_pricing_confirmed,
                )
                db.add(catalog)
                activated_models += 1

    except Exception as e:
        logger.warning(f"Model discovery failed: {e}")

    await db.commit()
    await db.refresh(provider)

    return QuickCreateResponse(
        provider={
            "id": str(provider.id),
            "name": provider.name,
            "display_name": provider.display_name,
            "base_url": provider.base_url,
            "api_format": provider.api_format,
            "supported_endpoints": provider.supported_endpoints or [],
        },
        api_key={
            "id": str(provider_key.id),
            "key_suffix": provider_key.key_suffix,
            "status": provider_key.status,
        },
        discovery_result={
            "total_models": total_models,
            "activated_models": activated_models,
            "pricing_confirmed": pricing_confirmed,
        }
    )
