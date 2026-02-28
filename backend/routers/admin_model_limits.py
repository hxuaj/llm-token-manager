"""
Admin 用户模型级限制管理路由

允许 Admin 为特定用户设置模型级别的使用限制
"""
import uuid
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from database import get_db
from models.user import User
from models.user_model_limit import UserModelLimit
from middleware.auth import get_current_admin_user


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型
# ─────────────────────────────────────────────────────────────────────

class ModelLimitCreate(BaseModel):
    """创建/更新模型限制"""
    model_id: str
    monthly_limit_usd: Optional[Decimal] = None
    daily_request_limit: Optional[int] = None


class ModelLimitResponse(BaseModel):
    """模型限制响应"""
    id: str
    user_id: str
    model_id: str
    monthly_limit_usd: Optional[Decimal] = None
    daily_request_limit: Optional[int] = None


class ModelLimitListResponse(BaseModel):
    """模型限制列表响应"""
    limits: List[ModelLimitResponse]


# ─────────────────────────────────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/model-limits", response_model=ModelLimitListResponse)
async def get_user_model_limits(
    user_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户的模型级限制列表

    Args:
        user_id: 用户 ID
    """
    # 验证用户存在
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 查询限制
    result = await db.execute(
        select(UserModelLimit).where(UserModelLimit.user_id == user_id)
    )
    limits = result.scalars().all()

    return ModelLimitListResponse(
        limits=[
            ModelLimitResponse(
                id=str(limit.id),
                user_id=str(limit.user_id),
                model_id=limit.model_id,
                monthly_limit_usd=limit.monthly_limit_usd,
                daily_request_limit=limit.daily_request_limit
            )
            for limit in limits
        ]
    )


@router.put("/users/{user_id}/model-limits/{model_id}", response_model=ModelLimitResponse)
async def set_user_model_limit(
    user_id: str,
    model_id: str,
    data: ModelLimitCreate,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    设置或更新用户的模型级限制

    Args:
        user_id: 用户 ID
        model_id: 模型 ID
        data: 限制数据
    """
    # 验证用户存在
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 查找现有限制
    result = await db.execute(
        select(UserModelLimit).where(
            and_(
                UserModelLimit.user_id == user_id,
                UserModelLimit.model_id == model_id
            )
        )
    )
    limit = result.scalar_one_or_none()

    if limit:
        # 更新现有限制
        limit.monthly_limit_usd = data.monthly_limit_usd
        limit.daily_request_limit = data.daily_request_limit
    else:
        # 创建新限制
        limit = UserModelLimit(
            id=uuid.uuid4(),
            user_id=user_id,
            model_id=model_id,
            monthly_limit_usd=data.monthly_limit_usd,
            daily_request_limit=data.daily_request_limit
        )
        db.add(limit)

    await db.commit()
    await db.refresh(limit)

    return ModelLimitResponse(
        id=str(limit.id),
        user_id=str(limit.user_id),
        model_id=limit.model_id,
        monthly_limit_usd=limit.monthly_limit_usd,
        daily_request_limit=limit.daily_request_limit
    )


@router.delete("/users/{user_id}/model-limits/{model_id}")
async def delete_user_model_limit(
    user_id: str,
    model_id: str,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除用户的模型级限制

    Args:
        user_id: 用户 ID
        model_id: 模型 ID
    """
    # 查找限制
    result = await db.execute(
        select(UserModelLimit).where(
            and_(
                UserModelLimit.user_id == user_id,
                UserModelLimit.model_id == model_id
            )
        )
    )
    limit = result.scalar_one_or_none()

    if not limit:
        raise HTTPException(status_code=404, detail="Model limit not found")

    await db.delete(limit)
    await db.commit()

    return {"message": "Model limit deleted successfully"}
