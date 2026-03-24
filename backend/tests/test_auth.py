"""
认证模块测试用例

测试覆盖：
- 用户注册（成功/失败场景）
- 用户登录（成功/失败场景）
- JWT 令牌验证
- 角色权限校验
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch


# ─────────────────────────────────────────────────────────────────────
# 注册测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(client):
    """正常注册 - 应返回 201 和用户信息"""
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "securepassword123",
            "real_name": "测试用户"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "testuser@example.com"
    assert data["real_name"] == "测试用户"
    assert "id" in data
    assert "password" not in data  # 不应返回密码
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client, test_user):
    """用户名重复 - 应返回 409 Conflict"""
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",  # 与 test_user 相同
            "email": "another@example.com",
            "password": "securepassword123",
            "real_name": "另一个用户"
        }
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_email(client, test_user):
    """邮箱重复 - 应返回 409 Conflict"""
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "anotheruser",
            "email": "testuser@example.com",  # 与 test_user 相同
            "password": "securepassword123",
            "real_name": "另一个用户"
        }
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_weak_password(client):
    """密码少于 8 位 - 应返回 422 Validation Error"""
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "short",  # 只有 5 位
            "real_name": "测试用户"
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client):
    """邮箱格式错误 - 应返回 422 Validation Error"""
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "invalid-email",  # 无效格式
            "password": "securepassword123",
            "real_name": "测试用户"
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_fields(client):
    """缺少必填字段 - 应返回 422"""
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser"
            # 缺少 email、password 和 real_name
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_real_name(client):
    """缺少真实姓名 - 应返回 422"""
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "securepassword123"
            # 缺少 real_name
        }
    )
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# 登录测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(client, test_user):
    """正确账号密码 - 应返回 200 和有效 JWT"""
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "testpassword123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_user):
    """错误密码 - 应返回 401 Unauthorized"""
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "wrongpassword"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    """不存在的用户 - 应返回 401 Unauthorized"""
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "nonexistent",
            "password": "anypassword"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_disabled_user(client):
    """被禁用的用户 - 应返回 403 Forbidden"""
    # 先注册一个用户
    await client.post(
        "/api/auth/register",
        json={
            "username": "disableduser",
            "email": "disabled@example.com",
            "password": "testpassword123",
            "real_name": "禁用用户"
        }
    )

    # 直接在数据库中禁用该用户（需要通过 admin 接口或直接操作）
    # 这里我们暂时跳过，等 admin 接口实现后再补充
    # TODO: 在 Step 4 实现后再启用此测试


# ─────────────────────────────────────────────────────────────────────
# JWT 验证测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_jwt_valid(client, user_token):
    """使用有效 JWT 访问受保护接口 - 应返回 200"""
    response = await client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_jwt_missing(client):
    """不提供 JWT - 应返回 401"""
    response = await client.get("/api/user/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_invalid(client):
    """使用伪造 JWT - 应返回 401 Unauthorized"""
    response = await client.get(
        "/api/user/me",
        headers={"Authorization": "Bearer invalid-token-here"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_expired(client):
    """使用过期 JWT - 应返回 401 Unauthorized"""
    # 生成一个已过期的 token
    from services.auth import create_access_token

    expired_token = create_access_token(
        data={"sub": "testuser", "user_id": "some-id"},
        expires_delta=timedelta(seconds=-1)  # 已过期
    )

    response = await client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# 角色权限测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_cannot_access_admin(client, user_token):
    """普通用户调 Admin 接口 - 应返回 403 Forbidden"""
    response = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_access_admin(client, admin_token):
    """Admin 用户调 Admin 接口 - 应返回 200"""
    response = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# 获取当前用户测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_current_user(client, user_token, test_user):
    """获取当前用户信息 - 应返回正确的用户数据"""
    response = await client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == test_user.username
    assert data["email"] == test_user.email
    assert data["real_name"] == test_user.real_name
    assert data["role"] == "user"
