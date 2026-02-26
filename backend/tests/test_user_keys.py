"""
平台 Key 管理测试用例

测试覆盖：
- Key 创建（成功/失败场景）
- Key 列表查询
- Key 吊销
- Key 数量限制
- Key 统计
"""
import pytest
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────
# 创建 Key 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_key_success(client, user_token):
    """创建 Key 并命名 - 应返回 201 和完整 Key"""
    response = await client.post(
        "/api/user/keys",
        json={"name": "测试项目"},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "测试项目"
    assert "key" in data
    # 验证 Key 格式：ltm-sk- 前缀 + 32 位随机字符
    assert data["key"].startswith("ltm-sk-")
    assert len(data["key"]) == len("ltm-sk-") + 32


@pytest.mark.asyncio
async def test_create_key_name_required(client, user_token):
    """不传 name - 应返回 422 Validation Error"""
    response = await client.post(
        "/api/user/keys",
        json={},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_key_full_value_shown_once(client, user_token):
    """创建后再查列表 - 列表中只显示后 4 位"""
    # 创建 Key
    create_response = await client.post(
        "/api/user/keys",
        json={"name": "项目A"},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert create_response.status_code == 201
    full_key = create_response.json()["key"]

    # 查询列表
    list_response = await client.get(
        "/api/user/keys",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert list_response.status_code == 200
    keys = list_response.json()

    # 验证列表中不包含完整 Key
    for key_item in keys:
        assert "key" not in key_item or key_item.get("key") is None
        # 只显示后 4 位
        if "key_suffix" in key_item:
            assert len(key_item["key_suffix"]) == 4
            assert full_key.endswith(key_item["key_suffix"])


@pytest.mark.asyncio
async def test_create_key_unauthorized(client):
    """未登录创建 Key - 应返回 401"""
    response = await client.post(
        "/api/user/keys",
        json={"name": "测试项目"}
    )
    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Key 列表测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_keys_only_own(client, user_token, test_user, db_session):
    """用户 A 看不到用户 B 的 Key"""
    # 为当前用户创建 2 个 Key
    for i in range(2):
        await client.post(
            "/api/user/keys",
            json={"name": f"Key-{i}"},
            headers={"Authorization": f"Bearer {user_token}"}
        )

    # 创建另一个用户并创建 Key
    from models.user import User, UserRole
    from services.auth import hash_password

    other_user = User(
        username="otheruser",
        email="other@example.com",
        password_hash=hash_password("password123"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)

    from services.auth import create_access_token
    role = other_user.role.value if hasattr(other_user.role, 'value') else other_user.role
    other_token = create_access_token(
        data={"sub": other_user.username, "user_id": str(other_user.id), "role": role}
    )

    await client.post(
        "/api/user/keys",
        json={"name": "Other Key"},
        headers={"Authorization": f"Bearer {other_token}"}
    )

    # 当前用户查询列表，应该只有 2 个 Key
    response = await client.get(
        "/api/user/keys",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) == 2


@pytest.mark.asyncio
async def test_list_keys_empty(client, user_token):
    """新用户查询 Key 列表 - 应返回空列表"""
    response = await client.get(
        "/api/user/keys",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 200
    assert response.json() == []


# ─────────────────────────────────────────────────────────────────────
# 吊销 Key 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_key_success(client, user_token):
    """吊销自己的 Key - 应返回 200，状态变 revoked"""
    # 创建 Key
    create_response = await client.post(
        "/api/user/keys",
        json={"name": "待吊销"},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    key_id = create_response.json()["id"]

    # 吊销 Key
    revoke_response = await client.delete(
        f"/api/user/keys/{key_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert revoke_response.status_code == 200

    # 验证状态已变更
    list_response = await client.get(
        "/api/user/keys",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    keys = list_response.json()
    revoked_key = next((k for k in keys if k["id"] == key_id), None)
    assert revoked_key is not None
    assert revoked_key["status"] == "revoked"


@pytest.mark.asyncio
async def test_revoke_key_not_found(client, user_token):
    """吊销不存在的 Key - 应返回 404"""
    import uuid
    fake_id = str(uuid.uuid4())
    response = await client.delete(
        f"/api/user/keys/{fake_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_other_user_key_forbidden(client, user_token, db_session):
    """吊销其他用户的 Key - 应返回 403 或 404"""
    # 创建另一个用户和 Key
    from models.user import User, UserRole
    from models.user_api_key import UserApiKey
    from services.auth import hash_password
    from services.user_key_service import generate_api_key
    import uuid

    other_user = User(
        username="victim",
        email="victim@example.com",
        password_hash=hash_password("password123"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)

    # 为其他用户创建 Key
    raw_key, key_hash, key_suffix = generate_api_key()
    other_key = UserApiKey(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="Other Key",
        key_hash=key_hash,
        key_prefix="ltm-sk-",
        key_suffix=key_suffix,
        status="active",
    )
    db_session.add(other_key)
    await db_session.commit()
    await db_session.refresh(other_key)

    # 当前用户尝试吊销
    response = await client.delete(
        f"/api/user/keys/{other_key.id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    # 应该返回 404（找不到该 Key）或 403（无权限）
    assert response.status_code in [403, 404]


# ─────────────────────────────────────────────────────────────────────
# Key 数量限制测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_max_keys_limit(client, user_token):
    """超过 max_keys 数量 - 应返回 400 或 429"""
    # 默认 max_keys = 5，创建 5 个 Key
    for i in range(5):
        response = await client.post(
            "/api/user/keys",
            json={"name": f"Key-{i}"},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 201

    # 尝试创建第 6 个，应该失败
    response = await client.post(
        "/api/user/keys",
        json={"name": "Key-6"},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code in [400, 429]


# ─────────────────────────────────────────────────────────────────────
# Key 统计测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_key_stats(client, user_token):
    """查看某 Key 的用量统计 - 应返回 200"""
    # 创建 Key
    create_response = await client.post(
        "/api/user/keys",
        json={"name": "Stats Key"},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    key_id = create_response.json()["id"]

    # 查询统计
    response = await client.get(
        f"/api/user/keys/{key_id}/stats",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    # 统计数据应包含这些字段
    assert "key_id" in data
    assert "total_requests" in data or "request_count" in data
    assert "total_tokens" in data or "total_cost_usd" in data
