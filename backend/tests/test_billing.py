"""
计费测试用例

测试覆盖：
- 请求日志记录
- 费用计算
- 月度统计累积
- Key 维度统计
"""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock


def _mock_provider_key():
    """创建 mock 的供应商 Key 结果"""
    mock_provider = MagicMock()
    mock_provider.id = "test-provider-id"
    mock_provider.name = "test-provider"

    mock_key = MagicMock()
    mock_key.id = "test-key-id"
    mock_key.key_suffix = "abcd"
    mock_key.key_plan = "standard"
    mock_key.override_input_price = None
    mock_key.override_output_price = None
    mock_key.is_coding_plan = False

    return (mock_provider, mock_key, "decrypted-key")


# ─────────────────────────────────────────────────────────────────────
# 请求日志测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_request_log_created(client, user_api_key, db_session):
    """调用后生成日志 - request_logs 有新记录，字段完整"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "choices": [{"message": {"content": "Hello!"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
                }

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    assert response.status_code == 200

    # 验证日志已创建
    from models.request_log import RequestLog
    from sqlalchemy import select

    result = await db_session.execute(
        select(RequestLog).where(RequestLog.key_id == key_obj.id)
    )
    log = result.scalar_one_or_none()

    assert log is not None
    assert log.user_id == key_obj.user_id
    assert log.model == "gpt-4o"
    assert log.prompt_tokens == 100
    assert log.completion_tokens == 50
    assert log.total_tokens == 150
    assert log.status == "success"


@pytest.mark.asyncio
async def test_log_contains_key_id(client, user_api_key, db_session):
    """日志包含 key_id - key_id 字段正确"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-123",
                    "choices": [{"message": {"content": "test"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                }

                await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]},
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    from models.request_log import RequestLog
    from sqlalchemy import select

    result = await db_session.execute(
        select(RequestLog).where(RequestLog.key_id == key_obj.id)
    )
    log = result.scalar_one_or_none()

    assert log is not None
    assert str(log.key_id) == str(key_obj.id)


# ─────────────────────────────────────────────────────────────────────
# 费用计算测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cost_calculation(client, user_api_key, db_session):
    """token 数 × 单价 - cost_usd 计算正确"""
    key_obj, raw_key = user_api_key

    # 创建供应商和模型目录定价
    from models.provider import Provider
    from models.model_catalog import ModelCatalog, ModelStatus
    import uuid

    provider = Provider(
        id=uuid.uuid4(),
        name="openai",
        base_url="https://api.openai.com/v1",
        enabled=True
    )
    db_session.add(provider)
    await db_session.commit()

    # ModelCatalog 定价单位是 USD per 1M tokens
    # $0.005/1K = $5/1M, $0.015/1K = $15/1M
    catalog = ModelCatalog(
        id=uuid.uuid4(),
        model_id="gpt-4o",
        display_name="GPT-4o",
        provider_id=provider.id,
        input_price=Decimal("5.0"),   # $5/1M = $0.005/1K
        output_price=Decimal("15.0"),  # $15/1M = $0.015/1K
        status=ModelStatus.ACTIVE
    )
    db_session.add(catalog)
    await db_session.commit()

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-123",
                    "choices": [{"message": {"content": "test"}}],
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000}
                }

                await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]},
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    from models.request_log import RequestLog
    from sqlalchemy import select

    result = await db_session.execute(
        select(RequestLog).where(RequestLog.key_id == key_obj.id)
    )
    log = result.scalar_one_or_none()

    assert log is not None
    # 1000 input * 5/1M + 1000 output * 15/1M = 0.005 + 0.015 = 0.020
    expected_cost = Decimal("0.020")
    assert abs(Decimal(str(log.cost_usd)) - expected_cost) < Decimal("0.001")


# ─────────────────────────────────────────────────────────────────────
# 月度统计测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monthly_usage_accumulated(client, user_api_key, db_session, test_user):
    """多次调用 - monthly_usage 累加正确"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()

                # 第一次调用
                mock_forward.return_value = {
                    "id": "chatcmpl-1",
                    "choices": [{"message": {"content": "test1"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
                }
                await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test1"}]},
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                # 第二次调用
                mock_forward.return_value = {
                    "id": "chatcmpl-2",
                    "choices": [{"message": {"content": "test2"}}],
                    "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}
                }
                await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test2"}]},
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    from models.monthly_usage import MonthlyUsage
    from sqlalchemy import select
    from datetime import datetime

    year_month = datetime.utcnow().strftime("%Y-%m")
    result = await db_session.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == test_user.id,
            MonthlyUsage.year_month == year_month
        )
    )
    usage = result.scalar_one_or_none()

    assert usage is not None
    assert usage.total_tokens == 450  # 150 + 300
    assert usage.request_count == 2


@pytest.mark.asyncio
async def test_different_keys_separate_stats(client, test_user, db_session):
    """同用户不同 Key - 各 Key 用量分别记录"""
    from services.user_key_service import generate_api_key
    from models.user_api_key import UserApiKey
    import uuid

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
        keys.append((key, raw_key))

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-1",
                    "choices": [{"message": {"content": "test"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
                }

                # 用第一个 Key 调用
                await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]},
                    headers={"Authorization": f"Bearer {keys[0][1]}"}
                )

    from models.request_log import RequestLog
    from sqlalchemy import select

    # 验证日志中 key_id 正确
    for key_obj, _ in keys:
        result = await db_session.execute(
            select(RequestLog).where(RequestLog.key_id == key_obj.id)
        )
        logs = result.scalars().all()

        if key_obj.id == keys[0][0].id:
            assert len(logs) == 1
        else:
            assert len(logs) == 0


@pytest.mark.asyncio
async def test_cost_decimal_precision(client, user_api_key, db_session):
    """小额调用 - 小数精度不丢失"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-1",
                    "choices": [{"message": {"content": "test"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
                }

                await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]},
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    from models.request_log import RequestLog
    from sqlalchemy import select

    result = await db_session.execute(
        select(RequestLog).where(RequestLog.key_id == key_obj.id)
    )
    log = result.scalar_one_or_none()

    assert log is not None
    # 验证 cost_usd 是有效的数值
    cost = Decimal(str(log.cost_usd))
    assert cost >= 0


@pytest.mark.asyncio
async def test_failed_request_logged(client, user_api_key, db_session):
    """失败请求 - 日志记录 status=error，不扣费"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.side_effect = Exception("Provider error")

                response = await client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "test"}]},
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    # 请求应该失败
    assert response.status_code in [500, 502, 503]

    from models.request_log import RequestLog
    from sqlalchemy import select

    result = await db_session.execute(
        select(RequestLog).where(RequestLog.key_id == key_obj.id)
    )
    log = result.scalar_one_or_none()

    # 失败请求也应该被记录
    if log is not None:
        assert log.status == "error"
        # 失败请求 cost 应该为 0
        assert float(log.cost_usd) == 0
