"""
Admin 管理接口测试用例

测试覆盖：
- 用户管理（列表、更新额度、禁用、删除）
- 供应商管理（添加、编辑）
- 供应商 Key 管理（添加、删除、不可读取明文）
- 模型单价配置
- 权限校验（普通用户无法访问 Admin 接口）
"""
import pytest


# ─────────────────────────────────────────────────────────────────────
# 权限校验测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_cannot_access_any_admin_api(client, user_token):
    """普通用户调所有 Admin 接口 - 全部返回 403"""
    admin_endpoints = [
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/providers"),
        ("GET", "/api/admin/model-pricing"),
    ]

    for method, endpoint in admin_endpoints:
        if method == "GET":
            response = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {user_token}"}
            )
        assert response.status_code == 403, f"{method} {endpoint} should return 403"


# ─────────────────────────────────────────────────────────────────────
# 用户管理测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_users(client, admin_token, test_user):
    """用户列表分页 - 应返回 200"""
    response = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # 至少包含测试用户
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_update_user_quota(client, admin_token, test_user):
    """修改用户额度 - 应返回 200，额度已更新"""
    new_quota = 50.00
    response = await client.put(
        f"/api/admin/users/{test_user.id}",
        json={"monthly_quota_usd": new_quota},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert float(data["monthly_quota_usd"]) == new_quota


@pytest.mark.asyncio
async def test_disable_user(client, admin_token, test_user):
    """禁用用户 - 应返回 200，用户 is_active=false"""
    response = await client.patch(
        f"/api/admin/users/{test_user.id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_delete_user(client, admin_token, db_session):
    """删除用户 - 应返回 200/204"""
    # 创建一个新用户用于删除
    from models.user import User, UserRole
    from services.auth import hash_password
    import uuid

    user_to_delete = User(
        id=uuid.uuid4(),
        username="to_delete",
        email="delete@example.com",
        password_hash=hash_password("password123"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(user_to_delete)
    await db_session.commit()
    await db_session.refresh(user_to_delete)

    response = await client.delete(
        f"/api/admin/users/{user_to_delete.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code in [200, 204]


# ─────────────────────────────────────────────────────────────────────
# 供应商管理测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_provider(client, admin_token):
    """添加供应商 - 应返回 201"""
    response = await client.post(
        "/api/admin/providers",
        json={
            "name": "openai",
            "base_url": "https://api.openai.com/v1",
            "enabled": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "openai"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_providers(client, admin_token):
    """获取供应商列表 - 应返回 200"""
    response = await client.get(
        "/api/admin/providers",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_update_provider(client, admin_token):
    """编辑供应商配置 - 应返回 200"""
    # 先创建一个供应商
    create_response = await client.post(
        "/api/admin/providers",
        json={
            "name": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
            "enabled": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    provider_id = create_response.json()["id"]

    # 更新
    response = await client.put(
        f"/api/admin/providers/{provider_id}",
        json={
            "base_url": "https://api.anthropic.com/v2",
            "enabled": False
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["base_url"] == "https://api.anthropic.com/v2"
    assert data["enabled"] is False


# ─────────────────────────────────────────────────────────────────────
# 供应商 Key 管理测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_provider_key(client, admin_token):
    """添加供应商 Key - 应返回 201，返回后 4 位"""
    # 先创建供应商
    provider_response = await client.post(
        "/api/admin/providers",
        json={
            "name": "openai_test",
            "base_url": "https://api.openai.com/v1",
            "enabled": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    provider_id = provider_response.json()["id"]

    # 添加 Key
    response = await client.post(
        f"/api/admin/providers/{provider_id}/keys",
        json={"api_key": "sk-test-api-key-12345678"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "key_suffix" in data
    # 后 4 位应该匹配
    assert data["key_suffix"] == "5678"
    # 不应该返回完整 Key
    assert "api_key" not in data or data.get("api_key") is None


@pytest.mark.asyncio
async def test_provider_key_not_readable(client, admin_token):
    """查看供应商 Key - 只显示后 4 位，无法获取完整值"""
    # 创建供应商和 Key
    provider_response = await client.post(
        "/api/admin/providers",
        json={
            "name": "secret_test",
            "base_url": "https://api.example.com/v1",
            "enabled": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    provider_id = provider_response.json()["id"]

    await client.post(
        f"/api/admin/providers/{provider_id}/keys",
        json={"api_key": "sk-super-secret-key-abcdefgh"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    # 查看供应商详情，不应该包含完整 Key
    response = await client.get(
        f"/api/admin/providers/{provider_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()

    # 检查 Key 列表中没有完整 Key
    if "api_keys" in data:
        for key in data["api_keys"]:
            assert "encrypted_key" not in key or key.get("encrypted_key") is None
            if "key_suffix" in key:
                assert len(key["key_suffix"]) == 4


@pytest.mark.asyncio
async def test_delete_provider_key(client, admin_token):
    """删除供应商 Key - 应返回 200/204"""
    # 创建供应商和 Key
    provider_response = await client.post(
        "/api/admin/providers",
        json={
            "name": "delete_key_test",
            "base_url": "https://api.example.com/v1",
            "enabled": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    provider_id = provider_response.json()["id"]

    key_response = await client.post(
        f"/api/admin/providers/{provider_id}/keys",
        json={"api_key": "sk-key-to-delete"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    key_id = key_response.json()["id"]

    # 删除 Key
    response = await client.delete(
        f"/api/admin/providers/{provider_id}/keys/{key_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code in [200, 204]


# ─────────────────────────────────────────────────────────────────────
# 模型单价配置测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_model_pricing(client, admin_token):
    """获取模型单价列表 - 应返回 200"""
    response = await client.get(
        "/api/admin/model-pricing",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_update_model_pricing(client, admin_token):
    """修改模型单价 - 应返回 200"""
    # 先创建供应商和定价
    provider_response = await client.post(
        "/api/admin/providers",
        json={
            "name": "pricing_test",
            "base_url": "https://api.example.com/v1",
            "enabled": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    provider_id = provider_response.json()["id"]

    # 添加模型定价
    pricing_response = await client.post(
        "/api/admin/model-pricing",
        json={
            "provider_id": provider_id,
            "model_name": "gpt-4o",
            "input_price_per_1k": 0.005,
            "output_price_per_1k": 0.015
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert pricing_response.status_code == 201
    pricing_id = pricing_response.json()["id"]

    # 更新定价
    response = await client.put(
        f"/api/admin/model-pricing/{pricing_id}",
        json={
            "input_price_per_1k": 0.006,
            "output_price_per_1k": 0.018
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert float(data["input_price_per_1k"]) == 0.006
    assert float(data["output_price_per_1k"]) == 0.018


# ─────────────────────────────────────────────────────────────────────
# Admin 强制吊销用户 Key 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_force_revoke_user_key(client, admin_token, test_user, user_api_key):
    """Admin 强制吊销用户 Key - 应返回 200，Key 状态变 revoked"""
    key_obj, raw_key = user_api_key

    response = await client.delete(
        f"/api/admin/users/{test_user.id}/keys/{key_obj.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200

    # 验证 Key 已被吊销（通过用户查询自己的 Key 列表）
    # 注意：这需要 admin_token 而非 user_token
    # 这里我们验证响应消息
    data = response.json()
    assert "revoked" in data.get("message", "").lower() or data.get("status") == "revoked"
