"""
Admin 用量统计 API 测试用例

测试覆盖：
- Admin 用量概览 (overview)
- Admin 按模型统计 (by-model)
- Admin 按用户统计 (by-user)
- Admin 导出 CSV (export)
- 权限校验（普通用户 403）
"""
import pytest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from models.request_log import RequestLog, RequestStatus
from models.user_api_key import UserApiKey
from models.user import User
from models.provider import Provider
from models.model_catalog import ModelCatalog, ModelStatus


# ─────────────────────────────────────────────────────────────────────
# 测试辅助函数
# ─────────────────────────────────────────────────────────────────────

async def _create_test_data(db_session):
    """
    创建测试数据：用户、供应商、Key、日志
    返回 (users, provider, keys)
    """
    from services.auth import hash_password
    from services.user_key_service import generate_api_key

    # 创建供应商
    provider = Provider(
        id=uuid.uuid4(),
        name="openai",
        base_url="https://api.openai.com/v1",
        api_format="openai",
        enabled=True
    )
    db_session.add(provider)
    await db_session.commit()

    # 创建模型目录
    models = [
        ("gpt-4o", "GPT-4o", Decimal("2.5"), Decimal("10.0")),
        ("gpt-4o-mini", "GPT-4o Mini", Decimal("0.15"), Decimal("0.6")),
    ]
    for model_id, display_name, input_price, output_price in models:
        catalog = ModelCatalog(
            id=uuid.uuid4(),
            model_id=model_id,
            display_name=display_name,
            provider_id=provider.id,
            input_price=input_price,
            output_price=output_price,
            status=ModelStatus.ACTIVE,
            is_pricing_confirmed=True
        )
        db_session.add(catalog)
    await db_session.commit()

    # 创建用户
    users = []
    for i in range(3):
        user = User(
            id=uuid.uuid4(),
            username=f"user{i}",
            email=f"user{i}@example.com",
            password_hash=hash_password("password123"),
            role="user",
            is_active=True
        )
        db_session.add(user)
        users.append(user)
    await db_session.commit()

    # 为每个用户创建 Key 和日志
    keys = []
    for i, user in enumerate(users):
        raw_key, key_hash, key_suffix = generate_api_key()
        key = UserApiKey(
            id=uuid.uuid4(),
            user_id=user.id,
            name=f"Key-{i}",
            key_hash=key_hash,
            key_suffix=key_suffix,
            status="active"
        )
        db_session.add(key)
        await db_session.commit()
        keys.append(key)

        # 创建日志
        for j in range(2):
            log = RequestLog(
                id=uuid.uuid4(),
                request_id=f"req-{uuid.uuid4().hex[:16]}",
                user_id=user.id,
                key_id=key.id,
                model="gpt-4o" if j == 0 else "gpt-4o-mini",
                prompt_tokens=1000 * (i + 1),
                completion_tokens=500 * (i + 1),
                total_tokens=1500 * (i + 1),
                input_tokens=1000 * (i + 1),
                output_tokens=500 * (i + 1),
                cost_usd=Decimal(str(0.01 * (i + 1))),
                status=RequestStatus.SUCCESS,
                created_at=datetime.utcnow() - timedelta(days=j)
            )
            db_session.add(log)
    await db_session.commit()

    return users, provider, keys


# ─────────────────────────────────────────────────────────────────────
# Admin 用量概览测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_usage_overview(client, db_session, admin_token):
    """Admin 用量概览 - 返回全局统计数据"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/overview",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 验证响应结构
    assert "period" in data
    assert "total_cost_usd" in data
    assert "total_requests" in data
    assert "active_users" in data
    assert "top_models" in data
    assert "top_users" in data

    # 验证数据
    assert data["total_requests"] == 6  # 3 users * 2 requests
    assert data["active_users"] == 3
    assert len(data["top_models"]) > 0
    assert len(data["top_users"]) > 0


@pytest.mark.asyncio
async def test_admin_usage_overview_period_filter(client, db_session, admin_token):
    """Admin 用量概览 - 时间段过滤"""
    users, provider, keys = await _create_test_data(db_session)

    # 查询今天
    response = await client.get(
        "/api/admin/usage/overview?period=day",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 只应该包含今天的数据（3 条）
    assert data["total_requests"] == 3


@pytest.mark.asyncio
async def test_admin_usage_overview_user_forbidden(client, user_token):
    """Admin 用量概览 - 普通用户访问返回 403"""
    response = await client.get(
        "/api/admin/usage/overview",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# Admin 按模型统计测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_usage_by_model(client, db_session, admin_token):
    """Admin 按模型统计 - 返回全局模型聚合数据"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/by-model",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 验证响应结构
    assert "models" in data
    assert len(data["models"]) == 2  # gpt-4o 和 gpt-4o-mini

    # 验证模型数据包含占比
    for model in data["models"]:
        assert "model_id" in model
        assert "display_name" in model
        assert "request_count" in model
        assert "input_tokens" in model
        assert "output_tokens" in model
        assert "cost_usd" in model
        assert "percentage" in model


@pytest.mark.asyncio
async def test_admin_usage_by_model_sort_by_cost(client, db_session, admin_token):
    """Admin 按模型统计 - 按费用排序"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/by-model?sort_by=cost_usd&sort_order=desc",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 验证按费用降序排列
    costs = [m["cost_usd"] for m in data["models"]]
    assert costs == sorted(costs, reverse=True)


@pytest.mark.asyncio
async def test_admin_usage_by_model_user_forbidden(client, user_token):
    """Admin 按模型统计 - 普通用户访问返回 403"""
    response = await client.get(
        "/api/admin/usage/by-model",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# Admin 按用户统计测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_usage_by_user(client, db_session, admin_token):
    """Admin 按用户统计 - 返回用户聚合数据"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/by-user",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 验证响应结构
    assert "users" in data
    assert len(data["users"]) == 3

    # 验证用户数据
    for user_data in data["users"]:
        assert "user_id" in user_data
        assert "username" in user_data
        assert "request_count" in user_data
        assert "cost_usd" in user_data
        assert "models" in user_data


@pytest.mark.asyncio
async def test_admin_usage_by_user_expand_models(client, db_session, admin_token):
    """Admin 按用户统计 - 展开模型维度"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/by-user?expand_models=true",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 验证每个用户的模型展开
    for user_data in data["users"]:
        assert len(user_data["models"]) == 2  # 每个用户用了 2 个模型


@pytest.mark.asyncio
async def test_admin_usage_by_user_user_forbidden(client, user_token):
    """Admin 按用户统计 - 普通用户访问返回 403"""
    response = await client.get(
        "/api/admin/usage/by-user",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# Admin 导出 CSV 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_usage_export_csv_by_model(client, db_session, admin_token):
    """Admin 导出 CSV - 按模型分组"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/export?format=csv&group_by=model",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]

    # 验证 CSV 内容
    content = response.text
    lines = content.strip().split("\n")

    # 验证表头
    assert "model_id" in lines[0].lower()
    assert "request_count" in lines[0].lower() or "requests" in lines[0].lower()
    assert "cost_usd" in lines[0].lower() or "cost" in lines[0].lower()

    # 验证数据行
    assert len(lines) >= 2  # 表头 + 至少一行数据


@pytest.mark.asyncio
async def test_admin_usage_export_csv_by_user(client, db_session, admin_token):
    """Admin 导出 CSV - 按用户分组"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/export?format=csv&group_by=user",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

    content = response.text
    lines = content.strip().split("\n")

    # 验证表头
    assert "user" in lines[0].lower()
    assert "request" in lines[0].lower() or "requests" in lines[0].lower()


@pytest.mark.asyncio
async def test_admin_usage_export_csv_by_key(client, db_session, admin_token):
    """Admin 导出 CSV - 按 Key 分组"""
    users, provider, keys = await _create_test_data(db_session)

    response = await client.get(
        "/api/admin/usage/export?format=csv&group_by=key",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

    content = response.text
    lines = content.strip().split("\n")

    # 验证表头
    assert "key" in lines[0].lower()


@pytest.mark.asyncio
async def test_admin_usage_export_date_range(client, db_session, admin_token):
    """Admin 导出 CSV - 日期范围过滤"""
    users, provider, keys = await _create_test_data(db_session)

    start_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    response = await client.get(
        f"/api/admin/usage/export?format=csv&group_by=model&start_date={start_date}&end_date={end_date}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_admin_usage_export_user_forbidden(client, user_token):
    """Admin 导出 CSV - 普通用户访问返回 403"""
    response = await client.get(
        "/api/admin/usage/export?format=csv&group_by=model",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# 空数据测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_usage_overview_empty(client, admin_token):
    """Admin 用量概览 - 无数据时返回空结果"""
    response = await client.get(
        "/api/admin/usage/overview",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_requests"] == 0
    assert data["total_cost_usd"] == 0
    assert data["active_users"] == 0
    assert len(data["top_models"]) == 0
    assert len(data["top_users"]) == 0


@pytest.mark.asyncio
async def test_admin_usage_by_model_empty(client, admin_token):
    """Admin 按模型统计 - 无数据时返回空结果"""
    response = await client.get(
        "/api/admin/usage/by-model",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data["models"]) == 0


@pytest.mark.asyncio
async def test_admin_usage_by_user_empty(client, admin_token):
    """Admin 按用户统计 - 无数据时返回空结果"""
    response = await client.get(
        "/api/admin/usage/by-user",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data["users"]) == 0
