"""
Admin 模型定价历史路由

提供模型定价变更历史的查询接口
"""
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database import get_db
from models.user import User
from models.model_pricing_history import ModelPricingHistory
from middleware.auth import get_current_admin_user


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型
# ─────────────────────────────────────────────────────────────────────

class PricingHistoryItem(BaseModel):
    """定价历史项"""
    id: str
    model_id: str
    old_input_price: Optional[float] = None
    new_input_price: float
    old_output_price: Optional[float] = None
    new_output_price: float
    changed_by: str
    changed_at: datetime
    reason: Optional[str] = None


class PricingHistoryResponse(BaseModel):
    """定价历史响应"""
    model_id: str
    history: List[PricingHistoryItem]


# ─────────────────────────────────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────────────────────────────────

@router.get("/models/{model_id}/pricing-history", response_model=PricingHistoryResponse)
async def get_model_pricing_history(
    model_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取模型的定价变更历史

    Args:
        model_id: 模型 ID
        limit: 返回记录数量限制
    """
    # 查询定价历史
    result = await db.execute(
        select(ModelPricingHistory)
        .where(ModelPricingHistory.model_id == model_id)
        .order_by(desc(ModelPricingHistory.changed_at))
        .limit(limit)
    )
    history_records = result.scalars().all()

    # 获取变更用户名
    user_ids = [str(r.changed_by) for r in history_records if r.changed_by]
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        user_map = {str(u.id): u.username for u in users_result.scalars().all()}
    else:
        user_map = {}

    return PricingHistoryResponse(
        model_id=model_id,
        history=[
            PricingHistoryItem(
                id=str(r.id),
                model_id=r.model_id,
                old_input_price=float(r.old_input_price) if r.old_input_price else None,
                new_input_price=float(r.new_input_price),
                old_output_price=float(r.old_output_price) if r.old_output_price else None,
                new_output_price=float(r.new_output_price),
                changed_by=user_map.get(str(r.changed_by), "unknown"),
                changed_at=r.changed_at,
                reason=r.reason
            )
            for r in history_records
        ]
    )
