"""
用户相关路由

提供：
- GET /api/user/me: 获取当前用户信息
- GET /api/user/usage: 获取用户用量统计
- GET /api/user/primary-keys: 获取用户的 Primary Key 绑定
"""
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from middleware.auth import get_current_active_user
from services.quota import get_monthly_usage_for_quota

router = APIRouter()


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    id: str
    username: str
    email: str
    real_name: str
    role: str
    is_active: bool
    monthly_quota_usd: float
    rpm_limit: int
    max_keys: int
    created_at: str

    class Config:
        from_attributes = True


class UserUsageResponse(BaseModel):
    """用户用量统计响应"""
    user_id: str
    year_month: str
    total_requests: int
    total_tokens: int
    total_cost_usd: float
    quota_used: float
    quota_limit: float
    rpm_limit: int

    class Config:
        from_attributes = True


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    获取当前用户信息

    返回当前登录用户的详细信息
    """
    role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    return UserInfoResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        real_name=current_user.real_name,
        role=role,
        is_active=current_user.is_active,
        monthly_quota_usd=float(current_user.monthly_quota_usd),
        rpm_limit=current_user.rpm_limit,
        max_keys=current_user.max_keys,
        created_at=current_user.created_at.isoformat()
    )


@router.get("/usage", response_model=UserUsageResponse)
async def get_user_usage(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的用量统计

    - 包含本月请求数、Token 数、费用
    - 包含额度使用情况
    """
    # 获取本月用量
    used_cost, total_tokens, request_count = await get_monthly_usage_for_quota(
        current_user.id, db
    )

    return UserUsageResponse(
        user_id=str(current_user.id),
        year_month=datetime.utcnow().strftime("%Y-%m"),
        total_requests=request_count,
        total_tokens=total_tokens,
        total_cost_usd=float(used_cost),
        quota_used=float(used_cost),
        quota_limit=float(current_user.monthly_quota_usd),
        rpm_limit=current_user.rpm_limit
    )


class PrimaryKeyInfo(BaseModel):
    """Primary Key 信息"""
    key_id: str
    key_suffix: str
    rpm_limit: int


class PrimaryKeysResponse(BaseModel):
    """Primary Keys 响应"""
    user_id: str
    primary_keys: Dict[str, Optional[PrimaryKeyInfo]]


@router.get("/primary-keys", response_model=PrimaryKeysResponse)
async def get_primary_keys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的 Primary Key 绑定

    返回每个供应商上绑定的主 Key 信息
    """
    from services.key_assignment import KeyAssignmentService

    primary_keys = await KeyAssignmentService.get_user_primary_keys(
        current_user.id, db
    )

    # 转换为响应格式
    result = {}
    for provider_name, key_info in primary_keys.items():
        if key_info:
            result[provider_name] = PrimaryKeyInfo(
                key_id=key_info["key_id"],
                key_suffix=key_info["key_suffix"],
                rpm_limit=key_info["rpm_limit"]
            )
        else:
            result[provider_name] = None

    return PrimaryKeysResponse(
        user_id=str(current_user.id),
        primary_keys=result
    )
