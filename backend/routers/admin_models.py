"""
Admin 模型管理路由

提供：
- 获取供应商下的模型列表
- 手动触发模型发现
- 更新模型状态
- 更新模型定价
- 手动添加模型
- 批量启用模型
"""
import uuid
import logging
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

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
from services.model_catalog_service import ModelCatalogService
from services.model_discovery import get_discovery_service, UnsupportedDiscoveryError, DiscoveryUpstreamError
from services.key_selector import KeySelector

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型（请求/响应）
# ─────────────────────────────────────────────────────────────────────

class ModelResponse(BaseModel):
    """模型响应"""
    id: str
    model_id: str
    display_name: str
    provider_id: str
    input_price: float
    output_price: float
    cache_write_price: Optional[float] = None
    cache_read_price: Optional[float] = None
    context_window: Optional[int] = None
    max_output: Optional[int] = None
    supports_vision: bool
    supports_tools: bool
    supports_streaming: bool
    status: str
    is_pricing_confirmed: bool
    source: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ProviderModelsResponse(BaseModel):
    """供应商模型列表响应"""
    provider_id: str
    provider_name: str
    models: List[ModelResponse]
    summary: dict


class ModelStatusUpdate(BaseModel):
    """更新模型状态"""
    status: str = Field(..., pattern="^(pending|active|inactive)$")


class ModelPricingUpdate(BaseModel):
    """更新模型定价"""
    input_price: float = Field(..., ge=0)
    output_price: float = Field(..., ge=0)
    reason: Optional[str] = None


class ModelCreate(BaseModel):
    """手动添加模型"""
    model_id: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    provider_id: str
    input_price: float = Field(default=0, ge=0)
    output_price: float = Field(default=0, ge=0)
    context_window: Optional[int] = None
    max_output: Optional[int] = None
    supports_vision: bool = False
    supports_tools: bool = True
    status: str = Field(default="pending", pattern="^(pending|active|inactive)$")


class BatchActivateRequest(BaseModel):
    """批量启用请求"""
    activate_all_priced: bool = False
    model_ids: Optional[List[str]] = None


class DiscoveryResponse(BaseModel):
    """模型发现响应"""
    discovered: int
    new_models: int
    pricing_matched: int
    pricing_pending: int
    details: List[dict]


# ─────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────

def model_to_response(model: ModelCatalog) -> ModelResponse:
    """转换模型对象为响应"""
    return ModelResponse(
        id=str(model.id),
        model_id=model.model_id,
        display_name=model.display_name,
        provider_id=str(model.provider_id),
        input_price=float(model.input_price),
        output_price=float(model.output_price),
        cache_write_price=float(model.cache_write_price) if model.cache_write_price else None,
        cache_read_price=float(model.cache_read_price) if model.cache_read_price else None,
        context_window=model.context_window,
        max_output=model.max_output,
        supports_vision=model.supports_vision,
        supports_tools=model.supports_tools,
        supports_streaming=model.supports_streaming,
        status=model.status,
        is_pricing_confirmed=model.is_pricing_confirmed,
        source=model.source,
        created_at=model.created_at.isoformat(),
        updated_at=model.updated_at.isoformat()
    )


# ─────────────────────────────────────────────────────────────────────
# API 路由
# ─────────────────────────────────────────────────────────────────────

@router.get("/providers/{provider_id}/models", response_model=ProviderModelsResponse)
async def list_provider_models(
    provider_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取供应商下的所有模型

    包含模型列表和统计摘要
    """
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    # 检查供应商是否存在
    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 获取模型列表
    models = await ModelCatalogService.get_provider_models(db, provider_uuid)

    # 获取统计摘要
    summary = await ModelCatalogService.get_provider_models_summary(db, provider_uuid)

    return ProviderModelsResponse(
        provider_id=str(provider_uuid),
        provider_name=provider.name,
        models=[model_to_response(m) for m in models],
        summary=summary
    )


@router.post("/providers/{provider_id}/discover-models", response_model=DiscoveryResponse)
async def trigger_discovery(
    provider_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    手动触发模型发现

    从供应商 API 拉取可用模型列表
    """
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    # 检查供应商是否存在
    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 获取一个活跃的 API Key
    api_key = await KeySelector.get_any_active_key(provider, db)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No active API key available for this provider"
        )

    # 触发模型发现
    try:
        discovery_service = get_discovery_service()
        result = await discovery_service.discover_models(provider, api_key, db)
        return DiscoveryResponse(**result.to_dict())
    except UnsupportedDiscoveryError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Model discovery not supported for this provider: {str(e)}"
        )
    except DiscoveryUpstreamError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream error during discovery: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Discovery error for provider {provider.name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error during discovery: {str(e)}"
        )


@router.put("/models/{model_id}/status", response_model=ModelResponse)
async def update_model_status(
    model_id: str,
    data: ModelStatusUpdate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新模型状态

    状态可选值：pending（待审核）、active（已启用）、inactive（已禁用）
    """
    model = await ModelCatalogService.update_model_status(db, model_id, data.status)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    return model_to_response(model)


@router.put("/models/{model_id}/pricing", response_model=ModelResponse)
async def update_model_pricing(
    model_id: str,
    data: ModelPricingUpdate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新模型定价

    修改模型的输入/输出单价
    """
    model = await ModelCatalogService.update_model_pricing(
        db,
        model_id,
        Decimal(str(data.input_price)),
        Decimal(str(data.output_price)),
        changed_by_id=admin_user.id,
        reason=data.reason
    )
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    return model_to_response(model)


@router.post("/models", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    data: ModelCreate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    手动添加模型

    当自动发现无法获取时，可手动添加模型
    """
    try:
        provider_uuid = uuid.UUID(data.provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    # 检查供应商是否存在
    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")

    # 检查模型是否已存在
    existing = await ModelCatalogService.get_model_by_id(db, data.model_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Model '{data.model_id}' already exists"
        )

    # 创建模型
    model = await ModelCatalogService.create_model(
        db,
        model_id=data.model_id,
        display_name=data.display_name,
        provider_id=provider_uuid,
        input_price=Decimal(str(data.input_price)),
        output_price=Decimal(str(data.output_price)),
        context_window=data.context_window,
        max_output=data.max_output,
        supports_vision=data.supports_vision,
        supports_tools=data.supports_tools,
        status=data.status,
        source=ModelSource.MANUAL,
        is_pricing_confirmed=data.input_price > 0
    )

    return model_to_response(model)


@router.post("/providers/{provider_id}/models/batch-activate")
async def batch_activate_models(
    provider_id: str,
    data: BatchActivateRequest,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    批量启用模型

    支持两种模式：
    1. activate_all_priced: 启用所有已确认定价的待审核模型
    2. model_ids: 启用指定的模型列表
    """
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    # 检查供应商是否存在
    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")

    activated_count = 0

    if data.activate_all_priced:
        # 启用所有已确认定价的待审核模型
        activated_count = await ModelCatalogService.batch_activate_priced_models(db, provider_uuid)
    elif data.model_ids:
        # 启用指定模型
        for model_id in data.model_ids:
            model = await ModelCatalogService.update_model_status(db, model_id, ModelStatus.ACTIVE)
            if model:
                activated_count += 1
    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'activate_all_priced' or 'model_ids' must be provided"
        )

    return {
        "message": f"Activated {activated_count} models",
        "activated_count": activated_count
    }
