"""
认证中间件

提供：
- JWT 认证依赖（用于 FastAPI 路由）
- 平台 Key 认证（用于 API 网关）
- 获取当前用户
- Admin 权限校验
"""
from typing import Optional, Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.user import User, UserRole
from models.user_api_key import UserApiKey, KeyStatus
from services.auth import decode_access_token
from services.user_key_service import hash_key, KEY_PREFIX

# HTTP Bearer 认证方案
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    获取当前认证用户

    从 Authorization header 中提取 JWT，验证并返回对应的用户对象

    Raises:
        HTTPException: 401 如果 token 无效或用户不存在
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise credentials_exception

    # 从 payload 中获取用户 ID
    user_id: str = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    # 查询用户
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    获取当前活跃用户

    确保用户存在且未被禁用

    Raises:
        HTTPException: 403 如果用户已被禁用
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    获取当前管理员用户

    确保用户是管理员角色

    Raises:
        HTTPException: 403 如果用户不是管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ─────────────────────────────────────────────────────────────────────
# 平台 Key 认证（用于 API 网关）
# ─────────────────────────────────────────────────────────────────────

async def get_user_by_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Tuple[User, UserApiKey]:
    """
    通过平台 API Key 获取用户

    用于网关代理接口的认证，验证平台 Key 并返回用户和 Key 对象

    Raises:
        HTTPException: 401 如果 Key 无效、不存在或已吊销
    """
    auth_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise auth_exception

    api_key = credentials.credentials

    # 验证 Key 格式
    if not api_key.startswith(KEY_PREFIX):
        raise auth_exception

    # 计算哈希并查询
    key_hash = hash_key(api_key)

    result = await db.execute(
        select(UserApiKey).where(UserApiKey.key_hash == key_hash)
    )
    key = result.scalar_one_or_none()

    if key is None:
        raise auth_exception

    # 检查 Key 状态
    if key.status != KeyStatus.ACTIVE.value and key.status != KeyStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 获取用户
    result = await db.execute(
        select(User).where(User.id == key.user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise auth_exception

    # 检查用户状态
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    return user, key
