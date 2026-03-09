"""
管理员 - 供应商预设配置路由

提供供应商预设、验证和快捷创建功能。
注意：这个路由文件需要注册在 admin.router 之前，
否则 /providers/presets 会被 /providers/{provider_id} 匹配。

核心原则：
- 本地 ModelCatalog 是模型数据的单一真相来源（SSOT）
- 本地无数据时，实时从 models.dev 获取
- API 发现作为可选补充方法
"""
import uuid
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.user import User
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from models.model_catalog import ModelCatalog, ModelStatus, ModelSource
from middleware.auth import get_current_admin_user
from services.encryption import encrypt, extract_key_suffix
from services.model_catalog_service import ModelCatalogService

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ModelsDevModel:
    """从 models.dev 获取的模型信息"""
    model_id: str
    display_name: str
    input_price: Decimal
    output_price: Decimal
    cache_read_price: Optional[Decimal] = None
    cache_write_price: Optional[Decimal] = None
    context_window: Optional[int] = None
    max_output: Optional[int] = None
    supports_vision: bool = False
    supports_tools: bool = True
    supports_reasoning: bool = False


async def fetch_models_from_models_dev(provider_id: str) -> List[ModelsDevModel]:
    """
    直接从 models.dev 获取供应商的模型列表（实时查询，不走本地缓存）

    Args:
        provider_id: 供应商在 models.dev 中的 ID（如 "openai", "anthropic", "minimax"）

    Returns:
        模型列表
    """
    from services.models_dev_service import get_models_dev_service

    models_dev = get_models_dev_service()

    try:
        provider_data = await models_dev.get_provider(provider_id)
        if not provider_data:
            return []

        models = []
        for model_id, model_data in provider_data.get("models", {}).items():
            cost = model_data.get("cost", {})
            limit = model_data.get("limit", {})
            capabilities = model_data.get("capabilities", {})

            # 解析价格
            input_price = Decimal(str(cost.get("input", 0))) if cost.get("input") else Decimal("0")
            output_price = Decimal(str(cost.get("output", 0))) if cost.get("output") else Decimal("0")
            cache_read_price = Decimal(str(cost.get("cache_read"))) if cost.get("cache_read") else None
            cache_write_price = Decimal(str(cost.get("cache_write"))) if cost.get("cache_write") else None

            models.append(ModelsDevModel(
                model_id=model_id,
                display_name=model_data.get("name", model_id),
                input_price=input_price,
                output_price=output_price,
                cache_read_price=cache_read_price,
                cache_write_price=cache_write_price,
                context_window=limit.get("context"),
                max_output=limit.get("output"),
                supports_vision=capabilities.get("input", {}).get("image", capabilities.get("vision", False)),
                supports_tools=capabilities.get("toolcall", capabilities.get("tools", True)),
                supports_reasoning=capabilities.get("reasoning", False),
            ))

        return models

    except Exception as e:
        logger.error(f"Failed to fetch models from models.dev for {provider_id}: {e}")
        return []


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
    validate_api: bool = False  # 是否验证 API Key（默认不验证）
    discover_from_api: bool = False  # 是否从 API 发现模型（默认不从 API 发现）


class DiscoveredModel(BaseModel):
    """发现的模型"""
    model_id: str
    display_name: str
    input_price: float
    output_price: float
    cache_read_price: Optional[float] = None
    cache_write_price: Optional[float] = None
    pricing_source: str  # "catalog", "models_dev", "api"
    is_pricing_confirmed: bool = False  # 定价是否已确认（有有效定价数据）
    context_window: Optional[int] = None
    supports_vision: bool = False
    supports_tools: bool = True
    supports_reasoning: bool = False
    from_api: bool = False  # 是否来自 API 发现


class ValidateKeyResponse(BaseModel):
    """验证 Key 响应"""
    valid: bool
    provider_preset: Optional[str] = None
    auto_config: Optional[dict] = None
    discovered_models: Optional[List[DiscoveredModel]] = None
    models_source: Optional[str] = None  # "catalog", "api", "catalog+api"
    api_validation: Optional[dict] = None  # API 验证结果
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
    validate_api: bool = False  # 是否验证 API Key
    discover_from_api: bool = False  # 是否从 API 发现模型


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
    验证 API Key 并获取可用模型

    数据获取优先级：
    1. 本地 ModelCatalog
    2. models.dev 实时获取（本地无数据时）
    3. API 发现（可选，作为补充）

    Args:
        data: 请求参数
            - provider_preset: 供应商预设 ID
            - api_key: API Key
            - custom_base_url: 自定义 base URL
            - validate_api: 是否验证 API Key（默认 False）
            - discover_from_api: 是否从 API 发现模型（默认 False）
    """
    from services.provider_presets import get_preset, get_models_dev_id
    from services.api_validator import validate_api_key
    from services.api_discovery import discover_models_from_api

    # 1. 获取预设
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

    # 2. 从本地 ModelCatalog 获取模型
    catalog_models = await ModelCatalogService.get_models_by_provider_models_dev_id(
        db, models_dev_provider_id
    )

    # 转换为响应格式
    discovered_models = []
    catalog_model_ids = set()
    pricing_confirmed = 0
    pricing_pending = 0
    models_source = "none"  # 默认无数据

    # 2.1 如果本地有数据，使用本地数据
    if catalog_models:
        models_source = "catalog"
        for model in catalog_models:
            catalog_model_ids.add(model.model_id)
            is_pricing_confirmed = model.is_pricing_confirmed and model.input_price > 0

            if is_pricing_confirmed:
                pricing_confirmed += 1
            else:
                pricing_pending += 1

            discovered_models.append(DiscoveredModel(
                model_id=model.model_id,
                display_name=model.display_name,
                input_price=float(model.input_price),
                output_price=float(model.output_price),
                cache_read_price=float(model.cache_read_price) if model.cache_read_price else None,
                cache_write_price=float(model.cache_write_price) if model.cache_write_price else None,
                pricing_source="catalog",
                is_pricing_confirmed=is_pricing_confirmed,
                context_window=model.context_window,
                supports_vision=model.supports_vision,
                supports_tools=model.supports_tools,
                supports_reasoning=model.supports_reasoning,
                from_api=False,
            ))
    else:
        # 2.2 本地无数据，从 models.dev 实时获取
        models_dev_models = await fetch_models_from_models_dev(models_dev_provider_id)

        if models_dev_models:
            models_source = "models_dev"
            for model in models_dev_models:
                catalog_model_ids.add(model.model_id)
                is_pricing_confirmed = model.input_price > 0

                if is_pricing_confirmed:
                    pricing_confirmed += 1
                else:
                    pricing_pending += 1

                discovered_models.append(DiscoveredModel(
                    model_id=model.model_id,
                    display_name=model.display_name,
                    input_price=float(model.input_price),
                    output_price=float(model.output_price),
                    cache_read_price=float(model.cache_read_price) if model.cache_read_price else None,
                    cache_write_price=float(model.cache_write_price) if model.cache_write_price else None,
                    pricing_source="models_dev",
                    is_pricing_confirmed=is_pricing_confirmed,
                    context_window=model.context_window,
                    supports_vision=model.supports_vision,
                    supports_tools=model.supports_tools,
                    supports_reasoning=model.supports_reasoning,
                    from_api=False,
                ))

    api_validation_result = None

    # 3. 可选：验证 API Key
    if data.validate_api:
        validation_result = await validate_api_key(preset, data.api_key, base_url)
        api_validation_result = {
            "performed": True,
            "valid": validation_result.valid,
            "error_type": validation_result.error_type,
            "error_message": validation_result.error_message,
        }

    # 4. 可选：从 API 发现补充模型
    if data.discover_from_api:
        discovery_result = await discover_models_from_api(preset, data.api_key, base_url)

        if discovery_result.success and discovery_result.models:
            for api_model in discovery_result.models:
                if api_model.model_id not in catalog_model_ids:
                    # 新模型，添加到列表
                    pricing_pending += 1
                    discovered_models.append(DiscoveredModel(
                        model_id=api_model.model_id,
                        display_name=api_model.display_name,
                        input_price=float(api_model.input_price),
                        output_price=float(api_model.output_price),
                        cache_read_price=float(api_model.cache_read_price) if api_model.cache_read_price else None,
                        cache_write_price=float(api_model.cache_write_price) if api_model.cache_write_price else None,
                        pricing_source="api",
                        is_pricing_confirmed=False,  # API 发现的模型默认未确认定价
                        context_window=api_model.context_window,
                        supports_vision=api_model.supports_vision,
                        supports_tools=api_model.supports_tools,
                        supports_reasoning=api_model.supports_reasoning,
                        from_api=True,
                    ))
                else:
                    # 已存在，标记为合并来源
                    for dm in discovered_models:
                        if dm.model_id == api_model.model_id:
                            dm.pricing_source = "catalog+api" if models_source == "catalog" else "models_dev+api"
                            break

            # 更新来源标识
            if models_source != "none":
                models_source = f"{models_source}+api" if discovered_models else "api"
            else:
                models_source = "api"
        else:
            logger.warning(f"API discovery failed: {discovery_result.error_message}")

    return ValidateKeyResponse(
        valid=True,
        provider_preset=data.provider_preset,
        auto_config={
            "base_url": base_url,
            "api_format": preset.api_format,
            "supported_endpoints": preset.supported_endpoints,
        },
        discovered_models=discovered_models,
        models_source=models_source if discovered_models else "none",
        api_validation=api_validation_result,
        summary={
            "total_models": len(discovered_models),
            "catalog_models": len(catalog_models),
            "pricing_confirmed": pricing_confirmed,
            "pricing_pending": pricing_pending,
        }
    )


@router.post("/providers/quick-create", response_model=QuickCreateResponse, status_code=status.HTTP_201_CREATED)
async def quick_create_provider(
    data: QuickCreateRequest,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    一键创建供应商

    数据获取优先级：
    1. 本地 ModelCatalog
    2. models.dev 实时获取（本地无数据时）
    3. API 发现（可选，作为补充）

    Args:
        data: 请求参数
            - provider_preset: 供应商预设 ID
            - api_key: API Key
            - key_plan: Key 计划类型
            - rpm_limit: RPM 限制
            - custom_base_url: 自定义 base URL
            - auto_activate_models: 是否自动激活模型
            - validate_api: 是否验证 API Key
            - discover_from_api: 是否从 API 发现模型
    """
    from services.provider_presets import get_preset, get_models_dev_id
    from services.api_discovery import discover_models_from_api

    # 1. 获取预设
    preset = get_preset(data.provider_preset)
    if not preset:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {data.provider_preset}")

    # 获取 models.dev 供应商 ID
    models_dev_provider_id = get_models_dev_id(preset)

    # 2. 检查供应商是否已存在
    result = await db.execute(select(Provider).where(Provider.name == preset.name))
    existing_provider = result.scalar_one_or_none()
    if existing_provider:
        raise HTTPException(status_code=409, detail=f"Provider '{preset.name}' already exists")

    # 确定使用的 base_url
    base_url = data.custom_base_url or preset.default_base_url

    # 3. 创建供应商
    provider = Provider(
        name=preset.name,
        display_name=preset.display_name,
        base_url=base_url,
        api_format=preset.api_format,
        enabled=True,
        source="preset",
        models_dev_id=models_dev_provider_id,  # 设置 models_dev_id 以便查询
        supported_endpoints=preset.supported_endpoints,
    )
    db.add(provider)
    await db.flush()  # 获取 provider.id

    # 4. 创建 API Key
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

    # 5. 获取模型（优先级：本地 > models.dev > API）
    total_models = 0
    activated_models = 0
    pricing_confirmed = 0
    models_source = "none"
    created_model_ids = set()

    # 5.1 从本地 ModelCatalog 获取该供应商的模型
    catalog_models = await ModelCatalogService.get_models_by_provider_models_dev_id(
        db, models_dev_provider_id
    )

    if catalog_models:
        models_source = "catalog"
        for model in catalog_models:
            # 检查是否已存在（避免重复）
            existing = await db.execute(
                select(ModelCatalog).where(ModelCatalog.model_id == model.model_id)
            )
            if existing.scalar_one_or_none():
                continue

            new_model = ModelCatalog(
                model_id=model.model_id,
                display_name=model.display_name,
                provider_id=provider.id,
                input_price=model.input_price,
                output_price=model.output_price,
                cache_read_price=model.cache_read_price,
                cache_write_price=model.cache_write_price,
                context_window=model.context_window,
                max_output=model.max_output,
                supports_vision=model.supports_vision,
                supports_tools=model.supports_tools,
                supports_reasoning=model.supports_reasoning,
                status=ModelStatus.ACTIVE if data.auto_activate_models else ModelStatus.PENDING,
                source=ModelSource.MODELS_DEV,
                models_dev_id=model.model_id,
                is_pricing_confirmed=model.is_pricing_confirmed,
            )
            db.add(new_model)
            created_model_ids.add(model.model_id)
            total_models += 1
            if data.auto_activate_models:
                activated_models += 1
            if model.is_pricing_confirmed:
                pricing_confirmed += 1
    else:
        # 5.2 本地无数据，从 models.dev 实时获取
        models_dev_models = await fetch_models_from_models_dev(models_dev_provider_id)

        if models_dev_models:
            models_source = "models_dev"
            for model in models_dev_models:
                # 检查是否已存在
                existing = await db.execute(
                    select(ModelCatalog).where(ModelCatalog.model_id == model.model_id)
                )
                if existing.scalar_one_or_none():
                    continue

                is_pricing_confirmed = model.input_price > 0

                new_model = ModelCatalog(
                    model_id=model.model_id,
                    display_name=model.display_name,
                    provider_id=provider.id,
                    input_price=model.input_price,
                    output_price=model.output_price,
                    cache_read_price=model.cache_read_price,
                    cache_write_price=model.cache_write_price,
                    context_window=model.context_window,
                    max_output=model.max_output,
                    supports_vision=model.supports_vision,
                    supports_tools=model.supports_tools,
                    supports_reasoning=model.supports_reasoning,
                    status=ModelStatus.ACTIVE if data.auto_activate_models else ModelStatus.PENDING,
                    source=ModelSource.MODELS_DEV,
                    models_dev_id=model.model_id,
                    is_pricing_confirmed=is_pricing_confirmed,
                )
                db.add(new_model)
                created_model_ids.add(model.model_id)
                total_models += 1
                if data.auto_activate_models:
                    activated_models += 1
                if is_pricing_confirmed:
                    pricing_confirmed += 1

    # 5.3 可选：从 API 发现补充模型
    if data.discover_from_api:
        discovery_result = await discover_models_from_api(preset, data.api_key, base_url)

        if discovery_result.success:
            for api_model in discovery_result.models:
                # 跳过已创建的模型
                if api_model.model_id in created_model_ids:
                    continue

                # 检查是否已存在
                existing = await db.execute(
                    select(ModelCatalog).where(ModelCatalog.model_id == api_model.model_id)
                )
                if existing.scalar_one_or_none():
                    continue

                new_model = ModelCatalog(
                    model_id=api_model.model_id,
                    display_name=api_model.display_name,
                    provider_id=provider.id,
                    input_price=api_model.input_price,
                    output_price=api_model.output_price,
                    cache_read_price=api_model.cache_read_price,
                    cache_write_price=api_model.cache_write_price,
                    context_window=api_model.context_window,
                    supports_vision=api_model.supports_vision,
                    supports_tools=api_model.supports_tools,
                    supports_reasoning=api_model.supports_reasoning,
                    status=ModelStatus.ACTIVE if data.auto_activate_models else ModelStatus.PENDING,
                    source=ModelSource.AUTO_DISCOVERED,
                    models_dev_id=api_model.model_id,
                    is_pricing_confirmed=False,  # API 发现的模型默认未确认定价
                )
                db.add(new_model)
                created_model_ids.add(api_model.model_id)
                total_models += 1
                if data.auto_activate_models:
                    activated_models += 1

            if discovery_result.models and total_models > 0:
                models_source = f"{models_source}+api" if models_source != "none" else "api"
        else:
            logger.warning(f"API discovery failed during quick-create: {discovery_result.error_message}")

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
            "models_source": models_source,
        }
    )
