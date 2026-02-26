"""
用户 API Key 管理路由

提供：
- POST /api/user/keys: 创建新 Key
- GET /api/user/keys: 获取 Key 列表
- DELETE /api/user/keys/{id}: 吊销 Key
- GET /api/user/keys/{id}/stats: 获取 Key 统计
"""
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models.user import User
from models.user_api_key import UserApiKey, KeyStatus
from middleware.auth import get_current_active_user
from services.user_key_service import generate_api_key
from services.billing import get_user_stats, get_key_stats as get_key_stats_from_db
from services.quota import get_monthly_usage_for_quota

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型（请求/响应）
# ─────────────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    """创建 Key 请求"""
    name: str = Field(..., min_length=1, max_length=50, description="Key 名称")


class KeyResponse(BaseModel):
    """Key 创建响应（包含完整 Key，仅创建时返回一次）"""
    id: str
    name: str
    key: str  # 完整 Key，仅此一次显示
    key_suffix: str
    status: str
    created_at: str

    class Config:
        from_attributes = True


class KeyListItem(BaseModel):
    """Key 列表项（不包含完整 Key）"""
    id: str
    name: str
    key_suffix: str
    status: str
    last_used_at: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class KeyStats(BaseModel):
    """Key 统计信息"""
    key_id: str
    key_name: str
    total_requests: int
    total_tokens: int
    total_cost_usd: float

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


# ─────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────

def key_to_response(key: UserApiKey, raw_key: str) -> KeyResponse:
    """将 UserApiKey 模型转换为创建响应"""
    return KeyResponse(
        id=str(key.id),
        name=key.name,
        key=raw_key,
        key_suffix=key.key_suffix,
        status=key.status.value if hasattr(key.status, 'value') else key.status,
        created_at=key.created_at.isoformat()
    )


def key_to_list_item(key: UserApiKey) -> KeyListItem:
    """将 UserApiKey 模型转换为列表项"""
    return KeyListItem(
        id=str(key.id),
        name=key.name,
        key_suffix=key.key_suffix,
        status=key.status.value if hasattr(key.status, 'value') else key.status,
        last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
        created_at=key.created_at.isoformat()
    )


# ─────────────────────────────────────────────────────────────────────
# 路由端点
# ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=KeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    request: CreateKeyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    创建新的平台 Key

    - Key 格式: ltm-sk-{32位随机字符}
    - 完整 Key 仅在创建时返回一次，请妥善保存
    """
    # 检查用户的 Key 数量是否已达上限
    result = await db.execute(
        select(func.count()).where(
            UserApiKey.user_id == current_user.id,
            UserApiKey.status == KeyStatus.ACTIVE.value
        )
    )
    active_key_count = result.scalar()

    if active_key_count >= current_user.max_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum number of keys ({current_user.max_keys}) reached"
        )

    # 生成新 Key
    raw_key, key_hash, key_suffix = generate_api_key()

    # 创建数据库记录
    new_key = UserApiKey(
        user_id=current_user.id,
        name=request.name,
        key_hash=key_hash,
        key_prefix="ltm-sk-",
        key_suffix=key_suffix,
        status=KeyStatus.ACTIVE.value,
    )

    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    return key_to_response(new_key, raw_key)


@router.get("", response_model=List[KeyListItem])
async def list_keys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的所有 Key 列表

    - 不返回完整 Key，只显示后 4 位
    """
    result = await db.execute(
        select(UserApiKey)
        .where(UserApiKey.user_id == current_user.id)
        .order_by(UserApiKey.created_at.desc())
    )
    keys = result.scalars().all()

    return [key_to_list_item(key) for key in keys]


@router.delete("/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_key(
    key_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    吊销（删除）指定的 Key

    - 吊销后 Key 立即失效
    - 只能吊销自己的 Key
    """
    # 查找 Key
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid key ID format"
        )

    result = await db.execute(
        select(UserApiKey).where(UserApiKey.id == key_uuid)
    )
    key = result.scalar_one_or_none()

    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found"
        )

    # 验证所有权
    if key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found"
        )

    # 吊销 Key
    key.status = KeyStatus.REVOKED.value
    key.revoked_at = datetime.utcnow()

    await db.commit()

    return {"message": "Key revoked successfully", "id": str(key.id)}


@router.get("/{key_id}/stats", response_model=KeyStats)
async def get_key_stats(
    key_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定 Key 的用量统计

    - 只能查看自己的 Key
    """
    # 查找 Key
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid key ID format"
        )

    result = await db.execute(
        select(UserApiKey).where(UserApiKey.id == key_uuid)
    )
    key = result.scalar_one_or_none()

    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found"
        )

    # 验证所有权
    if key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found"
        )

    # TODO: Step 6 实现后，从 request_logs 表查询实际统计数据
    # 目前返回空统计
    stats = await get_key_stats_from_db(key.id, db)

    return KeyStats(
        key_id=str(key.id),
        key_name=key.name,
        total_requests=stats.get("total_requests", 0),
        total_tokens=stats.get("total_tokens", 0),
        total_cost_usd=stats.get("total_cost_usd", 0.0)
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
    from datetime import datetime

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
