"""
认证路由

提供：
- POST /api/auth/register: 用户注册
- POST /api/auth/login: 用户登录
- GET /api/user/me: 获取当前用户信息
"""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import get_settings
from database import get_db
from models.user import User, UserRole
from services.auth import hash_password, verify_password, create_access_token
from middleware.auth import get_current_active_user

router = APIRouter()
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型（请求/响应）
# ─────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    real_name: str = Field(..., min_length=1, max_length=100)


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str
    password: str


class UserResponse(BaseModel):
    """用户信息响应"""
    id: str
    username: str
    email: str
    real_name: str
    role: str
    is_active: bool
    monthly_quota_usd: float
    created_at: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT 令牌响应"""
    access_token: str
    token_type: str = "bearer"


# ─────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────

def user_to_response(user: User) -> UserResponse:
    """将 User 模型转换为响应模型"""
    role = user.role.value if hasattr(user.role, 'value') else user.role
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        real_name=user.real_name,
        role=role,
        is_active=user.is_active,
        monthly_quota_usd=float(user.monthly_quota_usd),
        created_at=user.created_at.isoformat()
    )


# ─────────────────────────────────────────────────────────────────────
# 路由端点
# ─────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """
    用户注册

    创建新用户账号，使用默认配置
    """
    # 检查用户名是否已存在
    result = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists"
        )

    # 检查邮箱是否已存在
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists"
        )

    # 创建新用户
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        real_name=user_data.real_name,
        role=UserRole.USER,
        monthly_quota_usd=settings.default_monthly_quota_usd,
        rpm_limit=settings.default_rpm_limit,
        max_keys=settings.default_max_keys,
        is_active=True
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # 自动分配 Primary Keys（软分配）
    try:
        from services.key_assignment import KeyAssignmentService
        await KeyAssignmentService.assign_primary_keys_for_new_user(
            new_user.id, db
        )
    except Exception as e:
        # 分配失败不影响注册
        import logging
        logging.getLogger(__name__).warning(
            f"Failed to assign primary keys for user {new_user.id}: {e}"
        )

    return user_to_response(new_user)


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    用户登录

    验证凭据并返回 JWT 令牌
    """
    # 查找用户
    result = await db.execute(
        select(User).where(User.username == credentials.username)
    )
    user = result.scalar_one_or_none()

    # 验证用户存在且密码正确
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否被禁用
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账号已被禁用"
        )

    # 生成 JWT 令牌
    role = user.role.value if hasattr(user.role, 'value') else user.role
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": str(user.id),
            "role": role
        }
    )

    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_active_user)
):
    """
    获取当前用户信息

    需要 JWT 认证
    """
    return user_to_response(current_user)
