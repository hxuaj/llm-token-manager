"""
用户相关路由

提供：
- GET /api/user/usage: 获取用户用量统计
- GET /api/user/me: 获取当前用户信息
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from middleware.auth import get_current_active_user
from services.quota import get_monthly_usage_for_quota

router = APIRouter()


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
