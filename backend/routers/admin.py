"""
Admin 管理路由

提供管理员专用的接口：
- 用户管理
- 供应商管理
- 供应商 Key 管理
- 模型单价配置
"""
import uuid
import json
import logging
from typing import List, Optional, Dict
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database import get_db
from models.user import User, UserRole
from models.user_api_key import UserApiKey, KeyStatus
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus, KeyPlan
from models.model_pricing import ModelPricing
from middleware.auth import get_current_admin_user
from services.encryption import encrypt, decrypt, extract_key_suffix
from services.key_selector import KeySelector
from services.model_discovery import get_discovery_service, UnsupportedDiscoveryError, DiscoveryUpstreamError

router = APIRouter()
logger = logging.getLogger(__name__)


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
    rpm_limit: int
    max_keys: int
    key_count: int = 0
    created_at: str

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """用户更新请求"""
    monthly_quota_usd: Optional[float] = None
    rpm_limit: Optional[int] = None
    max_keys: Optional[int] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


class UserStatusUpdate(BaseModel):
    """用户状态更新"""
    is_active: bool


# 供应商管理
class ProviderCreate(BaseModel):
    """创建供应商"""
    name: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field(..., max_length=255)
    api_format: str = Field(default="openai", pattern="^(openai|anthropic)$")
    enabled: bool = True
    config: Optional[str] = None


class ProviderUpdate(BaseModel):
    """更新供应商"""
    base_url: Optional[str] = None
    api_format: Optional[str] = Field(default=None, pattern="^(openai|anthropic)$")
    enabled: Optional[bool] = None
    config: Optional[str] = None


class ProviderResponse(BaseModel):
    """供应商响应"""
    id: str
    name: str
    display_name: Optional[str] = None
    base_url: str
    api_format: str
    enabled: bool
    config: Optional[str]
    source: Optional[str] = None
    supported_endpoints: List[str] = []
    key_count: int = 0
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
    key_plan: str = Field(default="standard", pattern="^(standard|coding_plan)$")
    plan_models: Optional[List[str]] = None  # coding_plan 时必填
    plan_description: Optional[str] = None
    override_input_price: Optional[float] = None
    override_output_price: Optional[float] = None

    @field_validator('plan_models')
    @classmethod
    def validate_plan_models(cls, v, info):
        """验证 coding_plan 时必须提供 plan_models"""
        if info.data.get('key_plan') == 'coding_plan' and (not v or len(v) == 0):
            raise ValueError('plan_models is required when key_plan is "coding_plan"')
        return v


class ProviderKeyResponse(BaseModel):
    """供应商 Key 响应"""
    id: str
    provider_id: str
    key_suffix: str
    rpm_limit: int
    status: str
    key_plan: str = "standard"
    plan_models: Optional[List[str]] = None
    plan_description: Optional[str] = None
    created_at: str
    discovery: Optional[dict] = None  # 模型发现结果（仅首次添加 standard Key 时）

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
        rpm_limit=user.rpm_limit,
        max_keys=user.max_keys,
        key_count=0,  # 暂时返回 0，实际数量在 list_users 中计算
        created_at=user.created_at.isoformat()
    )


def provider_to_response(provider: Provider, key_count: int = 0) -> ProviderResponse:
    """转换供应商模型为响应"""
    return ProviderResponse(
        id=str(provider.id),
        name=provider.name,
        display_name=provider.display_name,
        base_url=provider.base_url,
        api_format=provider.api_format,
        enabled=provider.enabled,
        config=provider.config,
        source=provider.source,
        supported_endpoints=provider.supported_endpoints or [],
        key_count=key_count,
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
        api_format=provider.api_format,
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
    from models.user_api_key import UserApiKey

    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    # 获取每个用户的 Key 数量
    user_list = []
    for user in users:
        role = user.role.value if hasattr(user.role, 'value') else user.role

        # 查询用户的 Key 数量
        key_count_result = await db.execute(
            select(func.count()).where(UserApiKey.user_id == user.id)
        )
        key_count = key_count_result.scalar() or 0

        user_list.append({
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": role,
            "is_active": user.is_active,
            "monthly_quota_usd": float(user.monthly_quota_usd),
            "rpm_limit": user.rpm_limit,
            "max_keys": user.max_keys,
            "key_count": key_count,
            "created_at": user.created_at.isoformat()
        })

    return user_list


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
    if update_data.role is not None:
        user.role = UserRole.ADMIN if update_data.role == "admin" else UserRole.USER

    await db.commit()
    await db.refresh(user)

    # 返回更新后的用户信息
    role = user.role.value if hasattr(user.role, 'value') else user.role

    # 查询用户的 Key 数量
    key_count_result = await db.execute(
        select(func.count()).where(UserApiKey.user_id == user.id)
    )
    key_count = key_count_result.scalar() or 0

    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": role,
        "is_active": user.is_active,
        "monthly_quota_usd": float(user.monthly_quota_usd),
        "rpm_limit": user.rpm_limit,
        "max_keys": user.max_keys,
        "key_count": key_count,
        "created_at": user.created_at.isoformat()
    }


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


@router.get("/users/{user_id}/keys")
async def get_user_keys(
    user_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin 查看用户的所有 Key"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    # 检查用户是否存在
    result = await db.execute(
        select(User).where(User.id == user_uuid)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 查询用户的所有 Key
    result = await db.execute(
        select(UserApiKey).where(UserApiKey.user_id == user_uuid)
        .order_by(UserApiKey.created_at.desc())
    )
    keys = result.scalars().all()

    return [{
        "id": str(key.id),
        "name": key.name,
        "key_prefix": key.key_prefix,
        "key_suffix": key.key_suffix,
        "status": key.status.value if hasattr(key.status, 'value') else key.status,
        "created_at": key.created_at.isoformat(),
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
    } for key in keys]


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
    from models.provider_api_key import ProviderApiKey

    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.api_keys))
        .order_by(Provider.name)
    )
    providers = result.scalars().all()

    responses = []
    for p in providers:
        # 计算活跃的 key 数量
        active_key_count = len([k for k in p.api_keys if k.status == ProviderKeyStatus.ACTIVE.value])
        responses.append(provider_to_response(p, key_count=active_key_count))

    return responses


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
        api_format=data.api_format,
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
    if data.api_format is not None:
        provider.api_format = data.api_format
    if data.enabled is not None:
        provider.enabled = data.enabled
    if data.config is not None:
        provider.config = data.config

    await db.commit()
    await db.refresh(provider)
    return provider_to_response(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_200_OK)
async def delete_provider(
    provider_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除供应商（级联删除关联的 Key、定价和模型配置）"""
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 删除供应商（模型已配置级联删除，会自动删除关联的 Key、定价、模型）
    await db.delete(provider)
    await db.commit()
    return {"message": "Provider deleted", "id": provider_id}


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

    # 校验 coding_plan 必须提供 plan_models
    if data.key_plan == "coding_plan" and (not data.plan_models or len(data.plan_models) == 0):
        raise HTTPException(
            status_code=400,
            detail="plan_models is required when key_plan is 'coding_plan'"
        )

    # 加密存储
    encrypted_key = encrypt(data.api_key)
    key_suffix = extract_key_suffix(data.api_key)

    # 构建 API Key 对象
    api_key = ProviderApiKey(
        provider_id=provider_uuid,
        encrypted_key=encrypted_key,
        key_suffix=key_suffix,
        rpm_limit=data.rpm_limit,
        status=ProviderKeyStatus.ACTIVE.value,
        key_plan=data.key_plan,
        plan_models=json.dumps(data.plan_models) if data.plan_models else None,
        plan_description=data.plan_description,
        override_input_price=Decimal(str(data.override_input_price)) if data.override_input_price is not None else None,
        override_output_price=Decimal(str(data.override_output_price)) if data.override_output_price is not None else None,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    # 模型发现结果
    discovery_result = None

    # 仅当添加 standard Key 且是该供应商的首个 standard Key 时，触发模型发现
    if data.key_plan == "standard":
        try:
            standard_key_count = await KeySelector.count_standard_keys(provider, db)
            # 由于刚添加了一个，所以 standard_key_count 至少为 1
            # 我们需要检查是否是第一个（即添加前为 0）
            # 由于事务已提交，这里简化处理：只在成功添加后触发一次

            # 检查是否已有其他 standard Key（排除刚添加的）
            result = await db.execute(
                select(ProviderApiKey).where(
                    ProviderApiKey.provider_id == provider_uuid,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value,
                    ProviderApiKey.key_plan == KeyPlan.STANDARD.value,
                    ProviderApiKey.id != api_key.id
                ).limit(1)
            )
            has_other_standard = result.scalar_one_or_none() is not None

            if not has_other_standard:
                # 首个 standard Key，触发模型发现
                try:
                    discovery_service = get_discovery_service()
                    discovery_result = await discovery_service.discover_models(
                        provider, api_key, db
                    )
                    discovery_result = discovery_result.to_dict()
                except UnsupportedDiscoveryError as e:
                    logger.warning(f"Model discovery not supported for provider {provider.name}: {e}")
                    discovery_result = {"error": "discovery_not_supported", "message": str(e)}
                except DiscoveryUpstreamError as e:
                    logger.warning(f"Model discovery failed for provider {provider.name}: {e}")
                    discovery_result = {"error": "upstream_error", "message": str(e)}
                except Exception as e:
                    logger.error(f"Model discovery error for provider {provider.name}: {e}")
                    discovery_result = {"error": "internal_error", "message": str(e)}
        except Exception as e:
            logger.error(f"Error checking standard keys for discovery trigger: {e}")

    return ProviderKeyResponse(
        id=str(api_key.id),
        provider_id=str(api_key.provider_id),
        key_suffix=api_key.key_suffix,
        rpm_limit=api_key.rpm_limit,
        status=api_key.status.value if hasattr(api_key.status, 'value') else api_key.status,
        key_plan=api_key.key_plan,
        plan_models=data.plan_models,
        plan_description=api_key.plan_description,
        created_at=api_key.created_at.isoformat(),
        discovery=discovery_result
    )


@router.get("/providers/{provider_id}/keys")
async def list_provider_keys(
    provider_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商的所有 API Key"""
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    result = await db.execute(
        select(ProviderApiKey).where(ProviderApiKey.provider_id == provider_uuid)
    )
    keys = result.scalars().all()

    return [{
        "id": str(key.id),
        "key_suffix": key.key_suffix,
        "rpm_limit": key.rpm_limit,
        "status": key.status.value if hasattr(key.status, 'value') else key.status,
        "key_plan": key.key_plan,
        "plan_models": key.get_plan_models_list() if key.plan_models else None,
        "plan_description": key.plan_description,
        "created_at": key.created_at.isoformat()
    } for key in keys]


@router.get("/providers/{provider_id}/pricing")
async def list_provider_pricing(
    provider_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取供应商的模型定价列表"""
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    result = await db.execute(
        select(ModelPricing).where(ModelPricing.provider_id == provider_uuid)
    )
    pricings = result.scalars().all()

    return [{
        "id": str(p.id),
        "model_name": p.model_name,
        "input_price_per_1k": float(p.input_price_per_1k),
        "output_price_per_1k": float(p.output_price_per_1k),
        "created_at": p.created_at.isoformat()
    } for p in pricings]


@router.post("/providers/{provider_id}/pricing")
async def add_provider_pricing(
    provider_id: str,
    data: ModelPricingCreate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """添加模型定价"""
    try:
        provider_uuid = uuid.UUID(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")

    # 检查供应商是否存在
    result = await db.execute(select(Provider).where(Provider.id == provider_uuid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    pricing = ModelPricing(
        provider_id=provider_uuid,
        model_name=data.model_name,
        input_price_per_1k=Decimal(str(data.input_price_per_1k)),
        output_price_per_1k=Decimal(str(data.output_price_per_1k))
    )
    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)

    return {
        "id": str(pricing.id),
        "model_name": pricing.model_name,
        "input_price_per_1k": float(pricing.input_price_per_1k),
        "output_price_per_1k": float(pricing.output_price_per_1k),
        "created_at": pricing.created_at.isoformat()
    }


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


# ─────────────────────────────────────────────────────────────────────
# 供应商预设与快捷配置接口
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
    from services.provider_presets import get_preset
    from services.models_dev_service import get_models_dev_service

    # 获取预设
    preset = get_preset(data.provider_preset)
    if not preset:
        return ValidateKeyResponse(
            valid=False,
            error={"type": "invalid_preset", "message": f"Unknown preset: {data.provider_preset}"}
        )

    # 确定使用的 base_url
    base_url = data.custom_base_url or preset.default_base_url

    try:
        # 调用模型发现服务
        discovery_service = get_discovery_service(preset.name, base_url)
        models = await discovery_service.discover_models(data.api_key, db)

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
                dev_model = await models_dev.get_model(preset.name, model_id)
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


@router.post("/providers/quick-create", response_model=QuickCreateResponse)
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
    from services.provider_presets import get_preset
    from services.models_dev_service import get_models_dev_service

    # 获取预设
    preset = get_preset(data.provider_preset)
    if not preset:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {data.provider_preset}")

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
        discovery_service = get_discovery_service(preset.name, base_url)
        models = await discovery_service.discover_models(data.api_key, db)
        total_models = len(models)

        models_dev = get_models_dev_service()

        for model in models:
            model_id = model.get("model_id", model.get("id", ""))

            # 获取定价
            input_price = model.get("input_price", Decimal("0"))
            output_price = model.get("output_price", Decimal("0"))
            cache_read_price = model.get("cache_read_price")
            cache_write_price = model.get("cache_write_price")

            try:
                dev_model = await models_dev.get_model(preset.name, model_id)
                if dev_model:
                    cost = dev_model.get("cost", {})
                    if cost:
                        input_price = Decimal(str(cost.get("input", input_price)))
                        output_price = Decimal(str(cost.get("output", output_price)))
                        if cost.get("cache_read"):
                            cache_read_price = Decimal(str(cost["cache_read"]))
                        if cost.get("cache_write"):
                            cache_write_price = Decimal(str(cost["cache_write"]))
                        pricing_confirmed += 1
            except Exception:
                pass

            # 创建模型目录记录（如果自动激活）
            if data.auto_activate_models:
                from models.model_catalog import ModelCatalog, ModelStatus, ModelSource

                catalog = ModelCatalog(
                    model_id=model_id,
                    display_name=model.get("display_name", model_id),
                    provider_id=provider.id,
                    input_price=input_price,
                    output_price=output_price,
                    cache_read_price=cache_read_price,
                    cache_write_price=cache_write_price,
                    context_window=model.get("context_window"),
                    supports_vision=model.get("supports_vision", False),
                    supports_tools=model.get("supports_tools", True),
                    status=ModelStatus.ACTIVE,
                    source=ModelSource.AUTO_DISCOVERED,
                    models_dev_id=model_id,
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


# ─────────────────────────────────────────────────────────────────────
# 配置热重载接口
# ─────────────────────────────────────────────────────────────────────

class ConfigReloadResponse(BaseModel):
    """配置重载响应"""
    success: bool
    message: str
    providers_count: Optional[int] = None
    reloaded_at: Optional[str] = None


class ModelsSyncRequest(BaseModel):
    """模型同步请求"""
    force_refresh: bool = False
    provider_id: Optional[str] = None


class ModelsSyncResponse(BaseModel):
    """模型同步响应"""
    success: bool
    synced_at: str
    providers_synced: int = 0
    models_synced: int = 0
    new_models: int = 0
    updated_models: int = 0
    preserved_local: int = 0
    conflicts: List[dict] = []
    error: Optional[str] = None


@router.post("/config/reload", response_model=ConfigReloadResponse)
async def reload_config(
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    重载供应商配置

    触发重新加载供应商和模型配置（从数据库重新读取）
    """
    from datetime import datetime
    from services.unified_router import get_unified_router

    try:
        router = get_unified_router()

        # 统计供应商数量
        result = await db.execute(select(func.count()).select_from(Provider))
        providers_count = result.scalar() or 0

        # 清除路由器缓存（如果有）
        if hasattr(router, '_providers_cache'):
            router._providers_cache = None

        return ConfigReloadResponse(
            success=True,
            message="Configuration reloaded successfully",
            providers_count=providers_count,
            reloaded_at=datetime.utcnow().isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        return ConfigReloadResponse(
            success=False,
            message=f"Failed to reload config: {str(e)}"
        )


@router.post("/models/sync", response_model=ModelsSyncResponse)
async def sync_models_from_models_dev(
    request: ModelsSyncRequest,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    从 models.dev 同步模型数据

    支持：
    - force_refresh: 强制刷新缓存
    - provider_id: 只同步指定供应商
    """
    from datetime import datetime
    from services.models_dev_service import get_models_dev_service

    service = get_models_dev_service()

    result = await service.sync_to_database(
        db,
        provider_id=request.provider_id,
        force_refresh=request.force_refresh
    )

    return ModelsSyncResponse(
        success=result.success,
        synced_at=result.synced_at.isoformat(),
        providers_synced=result.providers_synced,
        models_synced=result.models_synced,
        new_models=result.new_models,
        updated_models=result.updated_models,
        preserved_local=result.preserved_local,
        conflicts=result.conflicts,
        error=result.error
    )
