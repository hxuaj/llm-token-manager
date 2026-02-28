"""
Admin 模型管理 API 测试

测试模型管理、状态更新、定价更新等功能
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
async def test_provider_key(db_session, test_provider):
    """创建测试供应商 Key"""
    from services.encryption import encrypt

    api_key = ProviderApiKey(
        provider_id=test_provider.id,
        encrypted_key=encrypt("test-api-key"),
        key_suffix="abcd",
        rpm_limit=60,
        status=ProviderKeyStatus.ACTIVE.value,
        key_plan=KeyPlan.STANDARD.value
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
        status=ModelStatus.PENDING,
        is_pricing_confirmed=True,
        source=ModelSource.MANUAL
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


# ─────────────────────────────────────────────────────────────────────
# 模型管理 API 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAdminModelsAPI:
    """测试 Admin 模型管理 API"""

    async def test_list_provider_models(self, client, test_admin, admin_token, test_provider, test_model):
        """测试获取供应商模型列表"""
        response = await client.get(
            f"/api/admin/providers/{test_provider.id}/models",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["provider_id"] == str(test_provider.id)
        assert data["provider_name"] == test_provider.name
        assert len(data["models"]) >= 1
        assert "summary" in data
        assert "total" in data["summary"]
        assert "active" in data["summary"]
        assert "pending" in data["summary"]

    async def test_activate_model(self, client, test_admin, admin_token, test_model):
        """测试激活模型"""
        response = await client.put(
            f"/api/admin/models/{test_model.model_id}/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "active"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

    async def test_deactivate_model(self, client, test_admin, admin_token, test_model):
        """测试停用模型"""
        # 先激活
        await client.put(
            f"/api/admin/models/{test_model.model_id}/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "active"}
        )

        # 再停用
        response = await client.put(
            f"/api/admin/models/{test_model.model_id}/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "inactive"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inactive"

    async def test_update_model_pricing(self, client, test_admin, admin_token, test_model):
        """测试更新模型定价"""
        response = await client.put(
            f"/api/admin/models/{test_model.model_id}/pricing",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "input_price": 5.0,
                "output_price": 20.0,
                "reason": "Price increase"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert float(data["input_price"]) == 5.0
        assert float(data["output_price"]) == 20.0
        assert data["is_pricing_confirmed"] == True

    async def test_manual_add_model(self, client, test_admin, admin_token, test_provider):
        """测试手动添加模型"""
        response = await client.post(
            "/api/admin/models",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "model_id": "manual-model-1",
                "display_name": "Manual Model 1",
                "provider_id": str(test_provider.id),
                "input_price": 1.0,
                "output_price": 2.0,
                "status": "pending"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["model_id"] == "manual-model-1"
        assert data["source"] == "manual"

    async def test_batch_activate(self, client, test_admin, admin_token, test_provider, db_session):
        """测试批量激活已定价模型"""
        # 创建多个模型
        for i in range(3):
            model = ModelCatalog(
                model_id=f"batch-model-{i}",
                display_name=f"Batch Model {i}",
                provider_id=test_provider.id,
                input_price=Decimal("1.0"),
                output_price=Decimal("2.0"),
                status=ModelStatus.PENDING,
                is_pricing_confirmed=True,
                source=ModelSource.MANUAL
            )
            db_session.add(model)
        await db_session.commit()

        response = await client.post(
            f"/api/admin/providers/{test_provider.id}/models/batch-activate",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"activate_all_priced": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["activated_count"] >= 3

    async def test_trigger_discovery(self, client, test_admin, admin_token, test_provider, test_provider_key):
        """测试手动触发模型发现"""
        # Mock 整个发现服务
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "discovered": 5,
            "new_models": 3,
            "pricing_matched": 2,
            "pricing_pending": 1,
            "details": []
        }

        with patch('routers.admin_models.get_discovery_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.discover_models = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await client.post(
                f"/api/admin/providers/{test_provider.id}/discover-models",
                headers={"Authorization": f"Bearer {admin_token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["discovered"] == 5
            assert data["new_models"] == 3

    async def test_user_cannot_manage_models(self, client, test_user, user_token, test_provider):
        """测试普通用户不能访问模型管理 API"""
        response = await client.get(
            f"/api/admin/providers/{test_provider.id}/models",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 403

    async def test_v1_models_only_active(self, client, test_user, user_token, test_provider, user_api_key, db_session):
        """测试 GET /v1/models 只返回 active 模型"""
        # 创建 active 和 pending 模型
        active_model = ModelCatalog(
            model_id="active-model",
            display_name="Active Model",
            provider_id=test_provider.id,
            input_price=Decimal("1.0"),
            output_price=Decimal("2.0"),
            status=ModelStatus.ACTIVE,
            source=ModelSource.MANUAL
        )
        pending_model = ModelCatalog(
            model_id="pending-model",
            display_name="Pending Model",
            provider_id=test_provider.id,
            input_price=Decimal("1.0"),
            output_price=Decimal("2.0"),
            status=ModelStatus.PENDING,
            source=ModelSource.MANUAL
        )
        db_session.add(active_model)
        db_session.add(pending_model)
        await db_session.commit()

        _, raw_key = user_api_key
        response = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {raw_key}"}
        )

        assert response.status_code == 200
        data = response.json()
        model_ids = [m["id"] for m in data["data"]]
        assert "active-model" in model_ids
        assert "pending-model" not in model_ids

    async def test_v1_models_user_allowed_filter(self, client, test_user, user_token, test_provider, user_api_key, db_session):
        """测试用户 allowed_models 过滤"""
        # 设置用户允许的模型
        test_user.allowed_models = json.dumps(["allowed-model"])
        await db_session.commit()

        # 创建模型
        allowed_model = ModelCatalog(
            model_id="allowed-model",
            display_name="Allowed Model",
            provider_id=test_provider.id,
            input_price=Decimal("1.0"),
            output_price=Decimal("2.0"),
            status=ModelStatus.ACTIVE,
            source=ModelSource.MANUAL
        )
        other_model = ModelCatalog(
            model_id="other-model",
            display_name="Other Model",
            provider_id=test_provider.id,
            input_price=Decimal("1.0"),
            output_price=Decimal("2.0"),
            status=ModelStatus.ACTIVE,
            source=ModelSource.MANUAL
        )
        db_session.add(allowed_model)
        db_session.add(other_model)
        await db_session.commit()

        _, raw_key = user_api_key
        response = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {raw_key}"}
        )

        assert response.status_code == 200
        data = response.json()
        model_ids = [m["id"] for m in data["data"]]
        assert "allowed-model" in model_ids
        assert "other-model" not in model_ids

    async def test_auto_discover_on_first_key(self, client, test_admin, admin_token, test_provider):
        """测试添加第一个 standard Key 时触发自动发现"""
        # 创建一个返回 mock 结果
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "discovered": 5,
            "new_models": 5,
            "pricing_matched": 3,
            "pricing_pending": 2,
            "details": []
        }

        with patch('routers.admin.get_discovery_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.discover_models = AsyncMock(return_value=mock_result)
            mock_get_service.return_value = mock_service

            response = await client.post(
                f"/api/admin/providers/{test_provider.id}/keys",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "api_key": "sk-test-key-1234567890",
                    "rpm_limit": 60,
                    "key_plan": "standard"
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["discovery"] is not None
            assert data["discovery"]["discovered"] == 5

    async def test_no_discover_on_subsequent_key(self, client, test_admin, admin_token, test_provider, test_provider_key):
        """测试添加第二个 standard Key 时不触发自动发现"""
        response = await client.post(
            f"/api/admin/providers/{test_provider.id}/keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "api_key": "sk-test-key-0987654321",
                "rpm_limit": 60,
                "key_plan": "standard"
            }
        )

        assert response.status_code == 201
        data = response.json()
        # 第二个 Key 不应该触发发现
        assert data["discovery"] is None
