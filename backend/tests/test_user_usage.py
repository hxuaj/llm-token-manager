"""
用户用量统计 API 测试用例

测试覆盖：
- 按模型统计 (by-model)
- 按 Key 统计 (by-key)
- 时间线统计 (timeline)
- 时间段过滤
- 用户只能看到自己的用量
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

async def _create_request_logs(db_session, user_id, key_id, logs_data):
    """
    创建测试用的请求日志

    Args:
        db_session: 数据库 session
        user_id: 用户 ID
        key_id: API Key ID
        logs_data: 日志数据列表，每个元素为 (model, input_tokens, output_tokens, cost_usd, days_ago) 元组
    """
    for model, input_tokens, output_tokens, cost_usd, days_ago in logs_data:
        created_at = datetime.utcnow() - timedelta(days=days_ago)
        log = RequestLog(
            id=uuid.uuid4(),
            request_id=f"req-{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            key_id=key_id,
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=Decimal(str(cost_usd)),
            status=RequestStatus.SUCCESS,
            created_at=created_at
        )
        db_session.add(log)
    await db_session.commit()


async def _create_model_catalog(db_session, provider_id):
    """创建测试用的模型目录"""
    models = [
        ("gpt-4o", "GPT-4o", Decimal("2.5"), Decimal("10.0")),
        ("gpt-4o-mini", "GPT-4o Mini", Decimal("0.15"), Decimal("0.6")),
        ("claude-sonnet-4-20250514", "Claude Sonnet 4", Decimal("3.0"), Decimal("15.0")),
    ]
    catalog_entries = []
    for model_id, display_name, input_price, output_price in models:
        catalog = ModelCatalog(
            id=uuid.uuid4(),
            model_id=model_id,
            display_name=display_name,
            provider_id=provider_id,
            input_price=input_price,
            output_price=output_price,
            status=ModelStatus.ACTIVE,
            is_pricing_confirmed=True
        )
        db_session.add(catalog)
        catalog_entries.append(catalog)
    await db_session.commit()
    return catalog_entries


# ─────────────────────────────────────────────────────────────────────
# 按模型统计测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_by_model_basic(client, user_api_key, db_session, test_user, user_token):
    """按模型统计 - 基本查询返回正确聚合数据"""
    key_obj, raw_key = user_api_key

    # 创建供应商和模型目录
    provider = Provider(
        id=uuid.uuid4(),
        name="openai",
        base_url="https://api.openai.com/v1",
        api_format="openai",
        enabled=True
    )
    db_session.add(provider)
    await db_session.commit()
    await _create_model_catalog(db_session, provider.id)

    # 创建测试日志
    logs_data = [
        ("gpt-4o", 1000, 500, 0.0075, 0),      # 今天
        ("gpt-4o", 2000, 1000, 0.015, 1),      # 昨天
        ("gpt-4o-mini", 500, 200, 0.00195, 0), # 今天
        ("claude-sonnet-4-20250514", 3000, 1500, 0.0315, 2),  # 2天前
    ]
    await _create_request_logs(db_session, test_user.id, key_obj.id, logs_data)

    # 调用 API
    response = await client.get(
        "/api/user/usage/by-model",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 验证响应结构
    assert "period" in data
    assert "total_cost_usd" in data
    assert "total_requests" in data
    assert "models" in data

    # 验证聚合数据
    assert data["total_requests"] == 4
    assert abs(data["total_cost_usd"] - 0.05595) < 0.001

    # 验证模型列表
    assert len(data["models"]) == 3

    # 验证 gpt-4o 的聚合
    gpt4o = next((m for m in data["models"] if m["model_id"] == "gpt-4o"), None)
    assert gpt4o is not None
    assert gpt4o["request_count"] == 2
    assert gpt4o["input_tokens"] == 3000
    assert gpt4o["output_tokens"] == 1500
    assert abs(gpt4o["cost_usd"] - 0.0225) < 0.001


@pytest.mark.asyncio
async def test_usage_by_model_period_filter(client, user_api_key, db_session, test_user, user_token):
    """按模型统计 - 时间段过滤正确"""
    key_obj, raw_key = user_api_key

    # 创建测试日志
    logs_data = [
        ("gpt-4o", 1000, 500, 0.0075, 0),   # 今天
        ("gpt-4o", 2000, 1000, 0.015, 5),   # 5天前
        ("gpt-4o", 1500, 750, 0.01125, 10), # 10天前
    ]
    await _create_request_logs(db_session, test_user.id, key_obj.id, logs_data)

    # 查询最近 3 天
    response = await client.get(
        "/api/user/usage/by-model?period=week",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 只应该包含最近 7 天的数据（今天 + 5天前）
    assert data["total_requests"] == 2


@pytest.mark.asyncio
async def test_usage_by_model_date_range(client, user_api_key, db_session, test_user, user_token):
    """按模型统计 - 自定义日期范围过滤"""
    key_obj, raw_key = user_api_key

    # 创建测试日志
    logs_data = [
        ("gpt-4o", 1000, 500, 0.0075, 0),   # 今天
        ("gpt-4o", 2000, 1000, 0.015, 3),   # 3天前
        ("gpt-4o", 1500, 750, 0.01125, 7),  # 7天前
    ]
    await _create_request_logs(db_session, test_user.id, key_obj.id, logs_data)

    # 查询指定日期范围
    start_date = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    response = await client.get(
        f"/api/user/usage/by-model?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 只应该包含最近 5 天的数据（今天 + 3天前）
    assert data["total_requests"] == 2


@pytest.mark.asyncio
async def test_usage_by_model_only_own_data(client, db_session, test_user, user_token):
    """按模型统计 - 用户只能看到自己的数据"""
    # 创建另一个用户
    from services.auth import hash_password
    other_user = User(
        id=uuid.uuid4(),
        username="otheruser",
        email="other@example.com",
        password_hash=hash_password("password123"),
        real_name="其他用户",
        role="user",
        is_active=True
    )
    db_session.add(other_user)
    await db_session.commit()

    # 为其他用户创建 Key
    from services.user_key_service import generate_api_key
    raw_key, key_hash, key_suffix = generate_api_key()
    other_key = UserApiKey(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="Other Key",
        key_hash=key_hash,
        key_suffix=key_suffix,
        status="active"
    )
    db_session.add(other_key)
    await db_session.commit()

    # 为当前用户创建 Key
    raw_key2, key_hash2, key_suffix2 = generate_api_key()
    my_key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="My Key",
        key_hash=key_hash2,
        key_suffix=key_suffix2,
        status="active"
    )
    db_session.add(my_key)
    await db_session.commit()

    # 创建日志：其他用户的数据
    await _create_request_logs(db_session, other_user.id, other_key.id, [
        ("gpt-4o", 5000, 2000, 0.05, 0),
    ])

    # 创建日志：当前用户的数据
    await _create_request_logs(db_session, test_user.id, my_key.id, [
        ("gpt-4o", 1000, 500, 0.01, 0),
    ])

    # 查询
    response = await client.get(
        "/api/user/usage/by-model",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 只应该看到自己的数据
    assert data["total_requests"] == 1
    assert abs(data["total_cost_usd"] - 0.01) < 0.001


# ─────────────────────────────────────────────────────────────────────
# 按 Key 统计测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_by_key_basic(client, db_session, test_user, user_token):
    """按 Key 统计 - 基本查询返回正确聚合数据"""
    from services.user_key_service import generate_api_key

    # 创建两个 Key
    keys = []
    for i in range(2):
        raw_key, key_hash, key_suffix = generate_api_key()
        key = UserApiKey(
            id=uuid.uuid4(),
            user_id=test_user.id,
            name=f"Key-{i}",
            key_hash=key_hash,
            key_suffix=key_suffix,
            status="active"
        )
        db_session.add(key)
        await db_session.commit()
        await db_session.refresh(key)
        keys.append(key)

    # 为每个 Key 创建日志
    await _create_request_logs(db_session, test_user.id, keys[0].id, [
        ("gpt-4o", 1000, 500, 0.01, 0),
        ("gpt-4o-mini", 500, 200, 0.005, 0),
    ])
    await _create_request_logs(db_session, test_user.id, keys[1].id, [
        ("gpt-4o", 2000, 1000, 0.02, 0),
    ])

    # 调用 API
    response = await client.get(
        "/api/user/usage/by-key",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 验证响应结构
    assert "keys" in data
    assert len(data["keys"]) == 2

    # 验证每个 Key 的数据
    key0_data = next((k for k in data["keys"] if k["key_suffix"] == keys[0].key_suffix), None)
    assert key0_data is not None
    assert key0_data["key_name"] == "Key-0"
    assert abs(key0_data["total_cost_usd"] - 0.015) < 0.001
    assert len(key0_data["models"]) == 2

    key1_data = next((k for k in data["keys"] if k["key_suffix"] == keys[1].key_suffix), None)
    assert key1_data is not None
    assert abs(key1_data["total_cost_usd"] - 0.02) < 0.001


@pytest.mark.asyncio
async def test_usage_by_key_model_breakdown(client, db_session, test_user, user_token):
    """按 Key 统计 - 每个 Key 下按模型拆分"""
    from services.user_key_service import generate_api_key

    raw_key, key_hash, key_suffix = generate_api_key()
    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test Key",
        key_hash=key_hash,
        key_suffix=key_suffix,
        status="active"
    )
    db_session.add(key)
    await db_session.commit()

    # 创建多个模型的日志
    await _create_request_logs(db_session, test_user.id, key.id, [
        ("gpt-4o", 1000, 500, 0.01, 0),
        ("gpt-4o", 500, 200, 0.005, 0),
        ("gpt-4o-mini", 300, 100, 0.002, 0),
    ])

    response = await client.get(
        "/api/user/usage/by-key",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data["keys"]) == 1
    key_data = data["keys"][0]

    # 验证模型拆分
    assert len(key_data["models"]) == 2

    gpt4o = next((m for m in key_data["models"] if m["model_id"] == "gpt-4o"), None)
    assert gpt4o is not None
    assert gpt4o["request_count"] == 2
    assert abs(gpt4o["cost_usd"] - 0.015) < 0.001


@pytest.mark.asyncio
async def test_usage_by_key_only_own_keys(client, db_session, test_user, user_token):
    """按 Key 统计 - 只能看到自己的 Key"""
    from services.auth import hash_password
    from services.user_key_service import generate_api_key

    # 创建其他用户和 Key
    other_user = User(
        id=uuid.uuid4(),
        username="otheruser2",
        email="other2@example.com",
        password_hash=hash_password("password123"),
        real_name="其他用户2",
        role="user",
        is_active=True
    )
    db_session.add(other_user)
    await db_session.commit()

    raw_key, key_hash, key_suffix = generate_api_key()
    other_key = UserApiKey(
        id=uuid.uuid4(),
        user_id=other_user.id,
        name="Other Key",
        key_hash=key_hash,
        key_suffix=key_suffix,
        status="active"
    )
    db_session.add(other_key)
    await db_session.commit()

    # 为其他用户创建日志
    await _create_request_logs(db_session, other_user.id, other_key.id, [
        ("gpt-4o", 5000, 2000, 0.05, 0),
    ])

    # 为当前用户创建 Key 和日志
    raw_key2, key_hash2, key_suffix2 = generate_api_key()
    my_key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="My Key",
        key_hash=key_hash2,
        key_suffix=key_suffix2,
        status="active"
    )
    db_session.add(my_key)
    await db_session.commit()

    await _create_request_logs(db_session, test_user.id, my_key.id, [
        ("gpt-4o", 1000, 500, 0.01, 0),
    ])

    response = await client.get(
        "/api/user/usage/by-key",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 只应该看到自己的 Key
    assert len(data["keys"]) == 1
    assert data["keys"][0]["key_suffix"] == my_key.key_suffix


# ─────────────────────────────────────────────────────────────────────
# 时间线统计测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_timeline_daily(client, db_session, test_user, user_token):
    """时间线统计 - 按天聚合"""
    from services.user_key_service import generate_api_key

    raw_key, key_hash, key_suffix = generate_api_key()
    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test Key",
        key_hash=key_hash,
        key_suffix=key_suffix,
        status="active"
    )
    db_session.add(key)
    await db_session.commit()

    # 创建不同天的日志
    await _create_request_logs(db_session, test_user.id, key.id, [
        ("gpt-4o", 1000, 500, 0.01, 0),   # 今天
        ("gpt-4o", 500, 200, 0.005, 0),   # 今天
        ("gpt-4o", 2000, 1000, 0.02, 1),  # 昨天
        ("gpt-4o", 1500, 750, 0.015, 2),  # 2天前
    ])

    response = await client.get(
        "/api/user/usage/timeline?granularity=day",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["granularity"] == "day"
    assert "data" in data
    assert len(data["data"]) == 3  # 3 天

    # 验证今天的聚合
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    today_data = next((d for d in data["data"] if d["date"] == today_str), None)
    assert today_data is not None
    assert today_data["requests"] == 2
    assert abs(today_data["cost_usd"] - 0.015) < 0.001
    assert today_data["input_tokens"] == 1500
    assert today_data["output_tokens"] == 700


@pytest.mark.asyncio
async def test_usage_timeline_hourly(client, db_session, test_user, user_token):
    """时间线统计 - 按小时聚合"""
    from services.user_key_service import generate_api_key

    raw_key, key_hash, key_suffix = generate_api_key()
    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test Key",
        key_hash=key_hash,
        key_suffix=key_suffix,
        status="active"
    )
    db_session.add(key)
    await db_session.commit()

    # 创建日志
    await _create_request_logs(db_session, test_user.id, key.id, [
        ("gpt-4o", 1000, 500, 0.01, 0),
        ("gpt-4o", 500, 200, 0.005, 0),
    ])

    response = await client.get(
        "/api/user/usage/timeline?granularity=hour",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["granularity"] == "hour"
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_usage_timeline_model_filter(client, db_session, test_user, user_token):
    """时间线统计 - 按模型过滤"""
    from services.user_key_service import generate_api_key

    raw_key, key_hash, key_suffix = generate_api_key()
    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test Key",
        key_hash=key_hash,
        key_suffix=key_suffix,
        status="active"
    )
    db_session.add(key)
    await db_session.commit()

    # 创建多个模型的日志
    await _create_request_logs(db_session, test_user.id, key.id, [
        ("gpt-4o", 1000, 500, 0.01, 0),
        ("gpt-4o-mini", 500, 200, 0.005, 0),
    ])

    response = await client.get(
        "/api/user/usage/timeline?granularity=day&model_id=gpt-4o",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # 只应该有 gpt-4o 的数据
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    today_data = next((d for d in data["data"] if d["date"] == today_str), None)
    assert today_data is not None
    assert today_data["requests"] == 1
    assert abs(today_data["cost_usd"] - 0.01) < 0.001


# ─────────────────────────────────────────────────────────────────────
# 认证测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_unauthorized(client):
    """未认证访问 - 返回 401"""
    response = await client.get("/api/user/usage/by-model")
    assert response.status_code == 401

    response = await client.get("/api/user/usage/by-key")
    assert response.status_code == 401

    response = await client.get("/api/user/usage/timeline")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_usage_empty_data(client, user_token):
    """无数据时 - 返回空结果"""
    response = await client.get(
        "/api/user/usage/by-model",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_requests"] == 0
    assert data["total_cost_usd"] == 0
    assert len(data["models"]) == 0
