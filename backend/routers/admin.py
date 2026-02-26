"""
Admin 管理路由

提供管理员专用的接口：
- 用户管理
- 供应商管理
- 供应商 Key 管理
- 模型单价配置
"""
import uuid
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database import get_db
from models.user import User, UserRole
from models.user_api_key import UserApiKey, KeyStatus
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from models.model_pricing import ModelPricing
from middleware.auth import get_current_admin_user
from services.encryption import encrypt, decrypt, extract_key_suffix

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型（请求/响应）
# ─────────────────────────────────────────────────────────────────────

# 用户管理
class UserListItem(BaseModel):
    """用户列表项"""
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    monthly_quota_usd: float
    created_at: str

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """用户更新请求"""
    monthly_quota_usd: Optional[float] = None
    rpm_limit: Optional[int] = None
    max_keys: Optional[int] = None
    is_active: Optional[bool] = None


class UserStatusUpdate(BaseModel):
    """用户状态更新"""
    is_active: bool


# 供应商管理
class ProviderCreate(BaseModel):
    """创建供应商"""
    name: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field(..., max_length=255)
    enabled: bool = True
    config: Optional[str] = None


class ProviderUpdate(BaseModel):
    """更新供应商"""
    base_url: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[str] = None


class ProviderResponse(BaseModel):
    """供应商响应"""
    id: str
    name: str
    base_url: str
    enabled: bool
    config: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class ProviderDetail(ProviderResponse):
    """供应商详情（包含 Key 列表）"""
    api_keys: List[dict]
    model_pricing: List[dict]


class ProviderKeyCreate(BaseModel):
    """创建供应商 Key"""
    api_key: str
    rpm_limit: int = 60


class ProviderKeyResponse(BaseModel):
    """供应商 Key 响应"""
    id: str
    provider_id: str
    key_suffix: str
    rpm_limit: int
    status: str
    created_at: str

    class Config:
        from_attributes = True


# 模型定价
class ModelPricingCreate(BaseModel):
    """创建模型定价"""
    provider_id: str
    model_name: str
    input_price_per_1k: float = 0.0
    output_price_per_1k: float = 0.0


class ModelPricingResponse(BaseModel):
    """模型定价响应"""
    id: str
    provider_id: str
    provider_name: Optional[str]
    model_name: str
    input_price_per_1k: float
    output_price_per_1k: float
    created_at: str

    class Config:
        from_attributes = True


class ModelPricingUpdate(BaseModel):
    """更新模型定价"""
    input_price_per_1k: Optional[float] = None
    output_price_per_1k: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────

def user_to_list_item(user: User) -> UserListItem:
    """转换用户模型为列表项"""
    role = user.role.value if hasattr(user.role, 'value') else user.role
    return UserListItem(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=role,
        is_active=user.is_active,
        monthly_quota_usd=float(user.monthly_quota_usd),
        created_at=user.created_at.isoformat()
    )


def provider_to_response(provider: Provider) -> ProviderResponse:
    """转换供应商模型为响应"""
    return ProviderResponse(
        id=str(provider.id),
        name=provider.name,
        base_url=provider.base_url,
        enabled=provider.enabled,
        config=provider.config,
        created_at=provider.created_at.isoformat()
    )


def provider_to_detail(provider: Provider) -> ProviderDetail:
    """转换供应商模型为详情响应"""
    api_keys = [
        {
            "id": str(k.id),
            "key_suffix": k.key_suffix,
            "rpm_limit": k.rpm_limit,
            "status": k.status.value if hasattr(k.status, 'value') else k.status,
            "created_at": k.created_at.isoformat()
        }
        for k in provider.api_keys
    ]
    model_pricing = [
        {
            "id": str(p.id),
            "model_name": p.model_name,
            "input_price_per_1k": float(p.input_price_per_1k),
            "output_price_per_1k": float(p.output_price_per_1k)
        }
        for p in provider.model_pricing
    ]
    return ProviderDetail(
        id=str(provider.id),
        name=provider.name,
        base_url=provider.base_url,
        enabled=provider.enabled,
        config=provider.config,
        created_at=provider.created_at.isoformat(),
        api_keys=api_keys,
        model_pricing=model_pricing
    )


# ─────────────────────────────────────────────────────────────────────
# 用户管理接口
# ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserListItem])
async def list_users(
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户列表（仅管理员）"""
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [user_to_list_item(u) for u in users]


@router.put("/users/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: str,
    update_data: UserUpdate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """更新用户信息（额度、限制等）"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 更新字段
    if update_data.monthly_quota_usd is not None:
        user.monthly_quota_usd = update_data.monthly_quota_usd
    if update_data.rpm_limit is not None:
        user.rpm_limit = update_data.rpm_limit
    if update_data.max_keys is not None:
        user.max_keys = update_data.max_keys
    if update_data.is_active is not None:
        user.is_active = update_data.is_active

    await db.commit()
    await db.refresh(user)
    return user_to_list_item(user)


@router.patch("/users/{user_id}/status", response_model=UserListItem)
async def update_user_status(
    user_id: str,
    status_data: UserStatusUpdate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """更新用户状态（启用/禁用）"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = status_data.is_active
    await db.commit()
    await db.refresh(user)
    return user_to_list_item(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除用户"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 不允许删除自己
    if user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    await db.delete(user)
    await db.commit()
    return {"message": "User deleted", "id": user_id}


@router.delete("/users/{user_id}/keys/{key_id}", status_code=status.HTTP_200_OK)
async def force_revoke_user_key(
    user_id: str,
    key_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin 强制吊销用户的 Key"""
    try:
        user_uuid = uuid.UUID(user_id)
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.execute(
        select(UserApiKey).where(
            UserApiKey.id == key_uuid,
            UserApiKey.user_id == user_uuid
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    key.status = KeyStatus.REVOKED.value
    key.revoked_at = datetime.utcnow()
    await db.commit()

    return {"message": "Key revoked successfully", "id": key_id, "status": "revoked"}


# ─────────────────────────────────────────────────────────────────────
# 供应商管理接口
# ─────────────────────────────────────────────────────────────────────

@router.get("/providers", response_model=List[ProviderResponse])
async def list_providers(
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商列表"""
    result = await db.execute(select(Provider).order_by(Provider.name))
    providers = result.scalars().all()
    return [provider_to_response(p) for p in providers]


@router.get("/providers/{provider_id}", response_model=ProviderDetail)
async def get_provider(
    provider_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商详情"""
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.api_keys), selectinload(Provider.model_pricing))
        .where(Provider.id == provider_uuid)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    return provider_to_detail(provider)


@router.post("/providers", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    data: ProviderCreate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """创建供应商"""
    # 检查名称是否已存在
    result = await db.execute(select(Provider).where(Provider.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Provider name already exists")

    provider = Provider(
        name=data.name,
        base_url=data.base_url,
        enabled=data.enabled,
        config=data.config
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider_to_response(provider)


@router.put("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    data: ProviderUpdate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """更新供应商"""
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if data.base_url is not None:
        provider.base_url = data.base_url
    if data.enabled is not None:
        provider.enabled = data.enabled
    if data.config is not None:
        provider.config = data.config

    await db.commit()
    await db.refresh(provider)
    return provider_to_response(provider)


# ─────────────────────────────────────────────────────────────────────
# 供应商 Key 管理接口
# ─────────────────────────────────────────────────────────────────────

@router.post("/providers/{provider_id}/keys", response_model=ProviderKeyResponse, status_code=status.HTTP_201_CREATED)
async def add_provider_key(
    provider_id: str,
    data: ProviderKeyCreate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """添加供应商 API Key"""
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 加密存储
    encrypted_key = encrypt(data.api_key)
    key_suffix = extract_key_suffix(data.api_key)

    api_key = ProviderApiKey(
        provider_id=provider_uuid,
        encrypted_key=encrypted_key,
        key_suffix=key_suffix,
        rpm_limit=data.rpm_limit,
        status=ProviderKeyStatus.ACTIVE.value
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ProviderKeyResponse(
        id=str(api_key.id),
        provider_id=str(api_key.provider_id),
        key_suffix=api_key.key_suffix,
        rpm_limit=api_key.rpm_limit,
        status=api_key.status.value if hasattr(api_key.status, 'value') else api_key.status,
        created_at=api_key.created_at.isoformat()
    )


@router.delete("/providers/{provider_id}/keys/{key_id}", status_code=status.HTTP_200_OK)
async def delete_provider_key(
    provider_id: str,
    key_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除供应商 API Key"""
    try:
        provider_uuid = uuid.UUID(provider_id)
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.execute(
        select(ProviderApiKey).where(
            ProviderApiKey.id == key_uuid,
            ProviderApiKey.provider_id == provider_uuid
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    await db.delete(key)
    await db.commit()
    return {"message": "Key deleted", "id": key_id}


# ─────────────────────────────────────────────────────────────────────
# 模型定价管理接口
# ─────────────────────────────────────────────────────────────────────

@router.get("/model-pricing", response_model=List[ModelPricingResponse])
async def list_model_pricing(
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取模型定价列表"""
    result = await db.execute(
        select(ModelPricing).order_by(ModelPricing.model_name)
    )
    pricings = result.scalars().all()

    # 获取供应商名称映射
    provider_result = await db.execute(select(Provider))
    providers = {str(p.id): p.name for p in provider_result.scalars().all()}

    return [
        ModelPricingResponse(
            id=str(p.id),
            provider_id=str(p.provider_id),
            provider_name=providers.get(str(p.provider_id)),
            model_name=p.model_name,
            input_price_per_1k=float(p.input_price_per_1k),
            output_price_per_1k=float(p.output_price_per_1k),
            created_at=p.created_at.isoformat()
        )
        for p in pricings
    ]


@router.post("/model-pricing", response_model=ModelPricingResponse, status_code=status.HTTP_201_CREATED)
async def create_model_pricing(
    data: ModelPricingCreate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """创建模型定价"""
    try:
        provider_uuid = uuid.UUID(data.provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    pricing = ModelPricing(
        provider_id=provider_uuid,
        model_name=data.model_name,
        input_price_per_1k=Decimal(str(data.input_price_per_1k)),
        output_price_per_1k=Decimal(str(data.output_price_per_1k))
    )
    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)

    return ModelPricingResponse(
        id=str(pricing.id),
        provider_id=str(pricing.provider_id),
        provider_name=None,
        model_name=pricing.model_name,
        input_price_per_1k=float(pricing.input_price_per_1k),
        output_price_per_1k=float(pricing.output_price_per_1k),
        created_at=pricing.created_at.isoformat()
    )


@router.put("/model-pricing/{pricing_id}", response_model=ModelPricingResponse)
async def update_model_pricing(
    pricing_id: str,
    data: ModelPricingUpdate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """更新模型定价"""
    try:
        pricing_uuid = uuid.UUID(pricing_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pricing ID")

    result = await db.execute(select(ModelPricing).where(ModelPricing.id == pricing_uuid))
    pricing = result.scalar_one_or_none()
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing not found")

    if data.input_price_per_1k is not None:
        pricing.input_price_per_1k = Decimal(str(data.input_price_per_1k))
    if data.output_price_per_1k is not None:
        pricing.output_price_per_1k = Decimal(str(data.output_price_per_1k))

    await db.commit()
    await db.refresh(pricing)

    return ModelPricingResponse(
        id=str(pricing.id),
        provider_id=str(pricing.provider_id),
        provider_name=None,
        model_name=pricing.model_name,
        input_price_per_1k=float(pricing.input_price_per_1k),
        output_price_per_1k=float(pricing.output_price_per_1k),
        created_at=pricing.created_at.isoformat()
    )
