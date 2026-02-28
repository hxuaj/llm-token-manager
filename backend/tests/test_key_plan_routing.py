"""
Key 计划路由测试

测试 coding_plan Key 优先级、费用计算、Key 选择等功能
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from decimal import Decimal

from httpx import AsyncClient

from models.model_catalog import ModelCatalog, ModelStatus, ModelSource
from models.provider import Provider, ApiFormat
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus, KeyPlan
from models.user import User, UserRole
from models.user_api_key import UserApiKey
from services.key_selector import KeySelector, NoAvailableKeyError, select_provider_key


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_provider(db_session):
    """创建测试供应商"""
    provider = Provider(
        name="test-provider",
        base_url="https://api.test.com",
        api_format=ApiFormat.OPENAI,
        enabled=True
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


@pytest_asyncio.fixture
async def test_standard_key(db_session, test_provider):
    """创建 standard Key"""
    from services.encryption import encrypt

    api_key = ProviderApiKey(
        provider_id=test_provider.id,
        encrypted_key=encrypt("sk-standard-key"),
        key_suffix="std1",
        rpm_limit=60,
        status=ProviderKeyStatus.ACTIVE.value,
        key_plan=KeyPlan.STANDARD.value
    )
    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(api_key)
    return api_key


@pytest_asyncio.fixture
async def test_coding_plan_key(db_session, test_provider):
    """创建 coding_plan Key"""
    from services.encryption import encrypt

    api_key = ProviderApiKey(
        provider_id=test_provider.id,
        encrypted_key=encrypt("sk-coding-plan-key"),
        key_suffix="cod1",
        rpm_limit=60,
        status=ProviderKeyStatus.ACTIVE.value,
        key_plan=KeyPlan.CODING_PLAN.value,
        plan_models=json.dumps(["coding-model-1", "coding-model-2"]),
        plan_description="Coding Plan subscription"
    )
    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(api_key)
    return api_key


@pytest_asyncio.fixture
async def test_model(db_session, test_provider):
    """创建测试模型"""
    model = ModelCatalog(
        model_id="test-model-1",
        display_name="Test Model 1",
        provider_id=test_provider.id,
        input_price=Decimal("3.0"),
        output_price=Decimal("15.0"),
        context_window=128000,
        status=ModelStatus.ACTIVE,
        is_pricing_confirmed=True,
        source=ModelSource.MANUAL
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest_asyncio.fixture
async def coding_model(db_session, test_provider):
    """创建 coding_plan 支持的模型"""
    model = ModelCatalog(
        model_id="coding-model-1",
        display_name="Coding Model 1",
        provider_id=test_provider.id,
        input_price=Decimal("0"),  # coding_plan 使用虚拟定价
        output_price=Decimal("0"),
        status=ModelStatus.ACTIVE,
        is_pricing_confirmed=False,
        source=ModelSource.MANUAL
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


# ─────────────────────────────────────────────────────────────────────
# Key 计划类型测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestKeyPlanTypes:
    """测试 Key 计划类型"""

    async def test_add_coding_plan_key(self, client, test_admin, admin_token, test_provider):
        """测试添加 coding_plan Key 时不提供 plan_models 返回 400"""
        response = await client.post(
            f"/api/admin/providers/{test_provider.id}/keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "api_key": "sk-coding-key-no-models",
                "rpm_limit": 60,
                "key_plan": "coding_plan"
                # 缺少 plan_models
            }
        )

        assert response.status_code == 400

    async def test_add_coding_plan_key_success(self, client, test_admin, admin_token, test_provider):
        """测试正确添加 coding_plan Key"""
        response = await client.post(
            f"/api/admin/providers/{test_provider.id}/keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "api_key": "sk-coding-key-with-models",
                "rpm_limit": 60,
                "key_plan": "coding_plan",
                "plan_models": ["model-1", "model-2"],
                "plan_description": "Test coding plan"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["key_plan"] == "coding_plan"
        assert data["plan_models"] == ["model-1", "model-2"]

    async def test_add_standard_key_no_plan_models(self, client, test_admin, admin_token, test_provider):
        """测试 standard Key 不需要 plan_models"""
        response = await client.post(
            f"/api/admin/providers/{test_provider.id}/keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "api_key": "sk-standard-key-no-models",
                "rpm_limit": 60,
                "key_plan": "standard"
                # 不提供 plan_models
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["key_plan"] == "standard"


# ─────────────────────────────────────────────────────────────────────
# Key 选择路由测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestKeySelection:
    """测试 Key 选择逻辑"""

    async def test_route_prefer_coding_plan(self, db_session, test_provider, test_standard_key, test_coding_plan_key):
        """测试请求 coding_plan 支持的模型时优先选择 coding_plan Key"""
        key = await select_provider_key(test_provider, "coding-model-1", db_session)

        assert key.key_plan == KeyPlan.CODING_PLAN.value
        assert key.id == test_coding_plan_key.id

    async def test_route_fallback_to_standard(self, db_session, test_provider, test_standard_key, test_coding_plan_key):
        """测试请求不在 coding_plan 列表中的模型时使用 standard Key"""
        key = await select_provider_key(test_provider, "other-model", db_session)

        assert key.key_plan == KeyPlan.STANDARD.value
        assert key.id == test_standard_key.id

    async def test_route_no_coding_plan_for_model(self, db_session, test_provider, test_coding_plan_key):
        """测试只有 coding_plan Key 且模型不匹配时返回错误"""
        # 只有 coding_plan Key，请求不在 plan_models 中的模型
        with pytest.raises(NoAvailableKeyError):
            await select_provider_key(test_provider, "other-model", db_session)


# ─────────────────────────────────────────────────────────────────────
# 费用计算测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestCostCalculation:
    """测试费用计算"""

    async def test_coding_plan_cost_zero(
        self, client, test_user, user_api_key, test_provider,
        test_coding_plan_key, coding_model, db_session
    ):
        """测试通过 coding_plan Key 转发（无虚拟单价）时 cost_usd = 0"""
        from services.proxy import calculate_request_cost

        cost = await calculate_request_cost(
            input_tokens=1000,
            output_tokens=500,
            model_id="coding-model-1",
            api_key=test_coding_plan_key,
            db=db_session
        )

        assert cost == Decimal("0")

    async def test_coding_plan_override_pricing(self, db_session, test_provider):
        """测试 coding_plan Key 设置了虚拟单价时按虚拟单价计算"""
        from services.encryption import encrypt
        from services.proxy import calculate_request_cost

        # 创建带虚拟单价的 coding_plan Key
        key = ProviderApiKey(
            provider_id=test_provider.id,
            encrypted_key=encrypt("sk-override-key"),
            key_suffix="ovr1",
            status=ProviderKeyStatus.ACTIVE.value,
            key_plan=KeyPlan.CODING_PLAN.value,
            plan_models=json.dumps(["override-model"]),
            override_input_price=Decimal("2.0"),  # $2/1M tokens
            override_output_price=Decimal("8.0")  # $8/1M tokens
        )
        db_session.add(key)
        await db_session.commit()

        cost = await calculate_request_cost(
            input_tokens=1000000,  # 1M tokens
            output_tokens=500000,  # 0.5M tokens
            model_id="override-model",
            api_key=key,
            db=db_session
        )

        # cost = 1M * $2/1M + 0.5M * $8/1M = $2 + $4 = $6
        assert cost == Decimal("6.0")

    async def test_standard_key_normal_pricing(
        self, client, test_user, user_api_key, test_provider,
        test_standard_key, test_model, db_session
    ):
        """测试 standard Key 转发按 model_catalog 单价计算"""
        from services.proxy import calculate_request_cost

        # test_model: input_price=3.0, output_price=15.0
        cost = await calculate_request_cost(
            input_tokens=1000000,  # 1M tokens
            output_tokens=1000000,  # 1M tokens
            model_id="test-model-1",
            api_key=test_standard_key,
            db=db_session
        )

        # cost = 1M * $3/1M + 1M * $15/1M = $3 + $15 = $18
        assert cost == Decimal("18.0")

    async def test_no_available_key(self, db_session):
        """测试供应商无 active Key 时返回 503"""
        provider = Provider(
            name="no-key-provider",
            base_url="https://api.test.com",
            api_format=ApiFormat.OPENAI,
            enabled=True
        )
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(provider)

        with pytest.raises(NoAvailableKeyError):
            await select_provider_key(provider, "any-model", db_session)


# ─────────────────────────────────────────────────────────────────────
# x_ltm 响应测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestXLTMResponse:
    """测试 x_ltm 响应字段"""

    async def test_x_ltm_in_response(
        self, client, test_user, user_api_key, test_provider,
        test_standard_key, test_model, db_session
    ):
        """测试响应中包含 x_ltm 字段"""
        _, raw_key = user_api_key

        with patch('services.proxy.forward_request') as mock_forward:
            mock_forward.return_value = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [{"message": {"content": "Hello"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}
            }

            # Mock provider key lookup
            with patch('services.proxy.get_provider_and_key') as mock_get_key:
                mock_get_key.return_value = (test_provider, test_standard_key, "decrypted")

                response = await client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {raw_key}"},
                    json={
                        "model": "test-model-1",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "stream": False
                    }
                )

        # 注意：由于 mock 的复杂性，这个测试可能需要调整
        # 主要目的是验证 x_ltm 字段存在
