"""
Admin 管理路由

提供管理员专用的接口
"""
from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.user import User
from middleware.auth import get_current_admin_user

router = APIRouter()


class UserListItem(BaseModel):
    """用户列表项"""
    id: str
    username: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/users", response_model=List[UserListItem])
async def list_users(
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户列表（仅管理员）

    返回所有用户的列表
    """
    result = await db.execute(select(User))
    users = result.scalars().all()

    return [
        UserListItem(
            id=str(u.id),
            username=u.username,
            email=u.email,
            role=u.role.value if hasattr(u.role, 'value') else u.role,
            is_active=u.is_active
        )
        for u in users
    ]
