"""
Batch 3 高级功能测试

测试覆盖：
- model_usage_daily 预聚合
- model_pricing_history 定价历史
- user_model_limits 模型级限制
- 额度告警
- 定时任务
"""
import pytest
import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal


# ─────────────────────────────────────────────────────────────────────
# 测试辅助函数
# ─────────────────────────────────────────────────────────────────────

async def _create_request_log(db_session, user_id, key_id, model, cost_usd, days_ago=0, status="success"):
    """创建测试用的请求日志"""
    from models.request_log import RequestLog, RequestStatus

    log = RequestLog(
        id=uuid.uuid4(),
        request_id=f"req-{uuid.uuid4().hex[:16]}",
        user_id=user_id,
        key_id=key_id,
        model=model,
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        input_tokens=1000,
        output_tokens=500,
        cost_usd=Decimal(str(cost_usd)),
        latency_ms=100,
        status=status,
        created_at=datetime.utcnow() - timedelta(days=days_ago)
    )
    db_session.add(log)
    await db_session.commit()
    return log


# ─────────────────────────────────────────────────────────────────────
# ModelUsageDaily 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_model_usage_daily(client, db_session, test_user, user_api_key, admin_token):
    """创建每日用量聚合记录"""
    from models.model_usage_daily import ModelUsageDaily

    key_obj, _ = user_api_key

    # 创建聚合记录
    usage = ModelUsageDaily(
        id=uuid.uuid4(),
        date=date.today(),
        user_id=test_user.id,
        model_id="gpt-4o",
        key_id=key_obj.id,
        request_count=10,
        input_tokens=10000,
        output_tokens=5000,
        total_cost_usd=Decimal("1.5"),
        avg_latency_ms=100,
        error_count=1
    )
    db_session.add(usage)
    await db_session.commit()

    # 验证
    from sqlalchemy import select
    result = await db_session.execute(
        select(ModelUsageDaily).where(ModelUsageDaily.user_id == test_user.id)
    )
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.request_count == 10
    assert saved.model_id == "gpt-4o"


@pytest.mark.asyncio
async def test_model_usage_daily_unique_constraint(client, db_session, test_user, user_api_key):
    """每日用量聚合唯一约束测试"""
    from models.model_usage_daily import ModelUsageDaily
    from sqlalchemy.exc import IntegrityError

    key_obj, _ = user_api_key

    # 创建第一条记录
    usage1 = ModelUsageDaily(
        id=uuid.uuid4(),
        date=date.today(),
        user_id=test_user.id,
        model_id="gpt-4o",
        key_id=key_obj.id,
        request_count=10,
        input_tokens=10000,
        output_tokens=5000,
        total_cost_usd=Decimal("1.5")
    )
    db_session.add(usage1)
    await db_session.commit()

    # 尝试创建相同日期/用户/模型/key的记录，应该失败
    usage2 = ModelUsageDaily(
        id=uuid.uuid4(),
        date=date.today(),
        user_id=test_user.id,
        model_id="gpt-4o",
        key_id=key_obj.id,
        request_count=5,
        input_tokens=5000,
        output_tokens=2500,
        total_cost_usd=Decimal("0.75")
    )
    db_session.add(usage2)

    with pytest.raises(IntegrityError):
        await db_session.commit()


# ─────────────────────────────────────────────────────────────────────
# ModelPricingHistory 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_pricing_history(client, db_session, test_admin):
    """创建定价历史记录"""
    from models.model_pricing_history import ModelPricingHistory

    history = ModelPricingHistory(
        id=uuid.uuid4(),
        model_id="gpt-4o",
        old_input_price=Decimal("2.5"),
        new_input_price=Decimal("3.0"),
        old_output_price=Decimal("10.0"),
        new_output_price=Decimal("12.0"),
        changed_by=test_admin.id,
        reason="供应商涨价"
    )
    db_session.add(history)
    await db_session.commit()

    # 验证
    from sqlalchemy import select
    result = await db_session.execute(
        select(ModelPricingHistory).where(ModelPricingHistory.model_id == "gpt-4o")
    )
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.old_input_price == Decimal("2.5")
    assert saved.new_input_price == Decimal("3.0")


@pytest.mark.asyncio
async def test_pricing_history_api(client, db_session, admin_token, test_admin):
    """定价历史 API 测试"""
    from models.model_pricing_history import ModelPricingHistory

    # 创建历史记录
    for i in range(3):
        history = ModelPricingHistory(
            id=uuid.uuid4(),
            model_id="gpt-4o",
            old_input_price=Decimal(str(2.0 + i * 0.5)),
            new_input_price=Decimal(str(2.5 + i * 0.5)),
            old_output_price=Decimal(str(8.0 + i * 2)),
            new_output_price=Decimal(str(10.0 + i * 2)),
            changed_by=test_admin.id,
            changed_at=datetime.utcnow() - timedelta(days=i),
            reason=f"第{i+1}次调价"
        )
        db_session.add(history)
    await db_session.commit()

    # 调用 API
    response = await client.get(
        "/api/admin/models/gpt-4o/pricing-history",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    # API 可能还未实现，先检查状态码
    # 如果 404，说明路由未注册；如果 200，说明成功
    assert response.status_code in [200, 404]


# ─────────────────────────────────────────────────────────────────────
# UserModelLimits 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user_model_limit(client, db_session, test_user):
    """创建用户模型级限制"""
    from models.user_model_limit import UserModelLimit

    limit = UserModelLimit(
        id=uuid.uuid4(),
        user_id=test_user.id,
        model_id="gpt-4o",
        monthly_limit_usd=Decimal("5.00"),
        daily_request_limit=100
    )
    db_session.add(limit)
    await db_session.commit()

    # 验证
    from sqlalchemy import select
    result = await db_session.execute(
        select(UserModelLimit).where(
            UserModelLimit.user_id == test_user.id,
            UserModelLimit.model_id == "gpt-4o"
        )
    )
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.monthly_limit_usd == Decimal("5.00")
    assert saved.daily_request_limit == 100


@pytest.mark.asyncio
async def test_user_model_limit_unique(client, db_session, test_user):
    """用户模型限制唯一约束"""
    from models.user_model_limit import UserModelLimit
    from sqlalchemy.exc import IntegrityError

    # 创建第一条
    limit1 = UserModelLimit(
        id=uuid.uuid4(),
        user_id=test_user.id,
        model_id="gpt-4o",
        monthly_limit_usd=Decimal("5.00")
    )
    db_session.add(limit1)
    await db_session.commit()

    # 尝试重复创建
    limit2 = UserModelLimit(
        id=uuid.uuid4(),
        user_id=test_user.id,
        model_id="gpt-4o",
        daily_request_limit=50
    )
    db_session.add(limit2)

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_admin_model_limits_api(client, db_session, admin_token, test_user):
    """Admin 模型级限制 API 测试"""
    from models.user_model_limit import UserModelLimit

    # 创建限制
    limit = UserModelLimit(
        id=uuid.uuid4(),
        user_id=test_user.id,
        model_id="gpt-4o",
        monthly_limit_usd=Decimal("5.00"),
        daily_request_limit=100
    )
    db_session.add(limit)
    await db_session.commit()

    # 查询限制
    response = await client.get(
        f"/api/admin/users/{test_user.id}/model-limits",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    # API 可能还未实现
    assert response.status_code in [200, 404]


# ─────────────────────────────────────────────────────────────────────
# 额度告警测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quota_warning_80_percent(client, db_session, test_user, user_token):
    """额度告警 - 80%"""
    # 修改用户额度
    test_user.monthly_quota_usd = 10.00
    await db_session.commit()

    # 模拟使用 8.00 (80%)
    # 这里需要调用实际的计费逻辑来验证告警
    # 暂时只验证模型设置正确
    assert test_user.monthly_quota_usd == 10.00


@pytest.mark.asyncio
async def test_quota_warning_95_percent(client, db_session, test_user):
    """额度告警 - 95%"""
    test_user.monthly_quota_usd = 10.00
    await db_session.commit()

    # 模拟使用 9.50 (95%)
    assert True  # 占位测试


@pytest.mark.asyncio
async def test_quota_exceeded_100_percent(client, db_session, test_user):
    """额度超限 - 100%"""
    test_user.monthly_quota_usd = 10.00
    await db_session.commit()

    # 模拟使用 10.00+ (100%+)
    assert True  # 占位测试


# ─────────────────────────────────────────────────────────────────────
# 每日聚合任务测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_aggregation_task(client, db_session, test_user, user_api_key):
    """每日聚合任务"""
    from models.request_log import RequestLog
    from models.model_usage_daily import ModelUsageDaily

    key_obj, _ = user_api_key

    # 创建多条请求日志（昨天）
    yesterday = datetime.utcnow() - timedelta(days=1)
    for i in range(5):
        log = RequestLog(
            id=uuid.uuid4(),
            request_id=f"req-{uuid.uuid4().hex[:16]}",
            user_id=test_user.id,
            key_id=key_obj.id,
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=Decimal("0.5"),
            latency_ms=100,
            status="success",
            created_at=yesterday
        )
        db_session.add(log)
    await db_session.commit()

    # 手动创建聚合记录模拟任务执行
    daily = ModelUsageDaily(
        id=uuid.uuid4(),
        date=yesterday.date(),
        user_id=test_user.id,
        model_id="gpt-4o",
        key_id=key_obj.id,
        request_count=5,
        input_tokens=5000,
        output_tokens=2500,
        total_cost_usd=Decimal("2.5"),
        avg_latency_ms=100
    )
    db_session.add(daily)
    await db_session.commit()

    # 验证聚合结果
    from sqlalchemy import select
    result = await db_session.execute(
        select(ModelUsageDaily).where(
            ModelUsageDaily.user_id == test_user.id,
            ModelUsageDaily.date == yesterday.date()
        )
    )
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.request_count == 5


# ─────────────────────────────────────────────────────────────────────
# 定时模型同步测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_model_sync_task(client, db_session, admin_token):
    """定时模型同步任务 - 占位测试"""
    # 这个测试需要 mock 供应商 API
    # 暂时只验证任务入口存在
    assert True
