"""
测试配置热重载 API

测试：
- POST /api/admin/config/reload - 重载供应商配置
- POST /api/admin/models/sync - 从 models.dev 同步模型
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from services.models_dev_service import SyncResult


class TestConfigReloadAPI:
    """配置重载 API 测试"""

    @pytest.mark.asyncio
    async def test_config_reload_success(self, client, admin_token):
        """测试配置重载成功"""
        response = await client.post(
            "/api/admin/config/reload",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "providers_count" in data
        assert data["providers_count"] >= 0

    @pytest.mark.asyncio
    async def test_config_reload_unauthorized(self, client, user_token):
        """测试普通用户无法访问配置重载"""
        response = await client.post(
            "/api/admin/config/reload",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_config_reload_no_auth(self, client):
        """测试无认证访问配置重载"""
        response = await client.post("/api/admin/config/reload")
        assert response.status_code == 401


class TestModelsSyncAPI:
    """模型同步 API 测试"""

    @pytest.mark.asyncio
    async def test_models_sync_endpoint(self, client, admin_token):
        """测试从 models.dev 同步模型"""
        mock_result = SyncResult(
            success=True,
            synced_at=datetime.utcnow(),
            providers_synced=2,
            models_synced=10,
            new_models=3,
            updated_models=5,
            preserved_local=0,
            conflicts=[]
        )

        with patch("services.models_dev_service.get_models_dev_service") as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.sync_to_database = AsyncMock(return_value=mock_result)
            mock_service.return_value = mock_service_instance

            response = await client.post(
                "/api/admin/models/sync",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["models_synced"] == 10

    @pytest.mark.asyncio
    async def test_models_sync_force_refresh(self, client, admin_token):
        """测试强制刷新同步"""
        mock_result = SyncResult(
            success=True,
            synced_at=datetime.utcnow(),
            providers_synced=1,
            models_synced=10,
            new_models=0,
            updated_models=5,
            preserved_local=0,
            conflicts=[]
        )

        with patch("services.models_dev_service.get_models_dev_service") as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.sync_to_database = AsyncMock(return_value=mock_result)
            mock_service.return_value = mock_service_instance

            response = await client.post(
                "/api/admin/models/sync",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"force_refresh": True}
            )

            assert response.status_code == 200
            # 验证 force_refresh 参数被传递
            mock_service_instance.sync_to_database.assert_called_once()
            call_kwargs = mock_service_instance.sync_to_database.call_args[1]
            assert call_kwargs.get("force_refresh") is True

    @pytest.mark.asyncio
    async def test_models_sync_partial_provider(self, client, admin_token):
        """测试部分供应商同步"""
        mock_result = SyncResult(
            success=True,
            synced_at=datetime.utcnow(),
            providers_synced=1,
            models_synced=5,
            new_models=1,
            updated_models=2,
            preserved_local=0,
            conflicts=[]
        )

        with patch("services.models_dev_service.get_models_dev_service") as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.sync_to_database = AsyncMock(return_value=mock_result)
            mock_service.return_value = mock_service_instance

            response = await client.post(
                "/api/admin/models/sync",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"provider_id": "anthropic"}
            )

            assert response.status_code == 200
            # 验证 provider_id 参数被传递
            call_kwargs = mock_service_instance.sync_to_database.call_args[1]
            assert call_kwargs.get("provider_id") == "anthropic"

    @pytest.mark.asyncio
    async def test_models_sync_error(self, client, admin_token):
        """测试同步失败的情况"""
        mock_result = SyncResult(
            success=False,
            synced_at=datetime.utcnow(),
            error="Network error"
        )

        with patch("services.models_dev_service.get_models_dev_service") as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.sync_to_database = AsyncMock(return_value=mock_result)
            mock_service.return_value = mock_service_instance

            response = await client.post(
                "/api/admin/models/sync",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert data["error"] == "Network error"

    @pytest.mark.asyncio
    async def test_models_sync_unauthorized(self, client, user_token):
        """测试普通用户无法访问模型同步"""
        response = await client.post(
            "/api/admin/models/sync",
            headers={"Authorization": f"Bearer {user_token}"},
            json={}
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_models_sync_no_auth(self, client):
        """测试无认证访问模型同步"""
        response = await client.post("/api/admin/models/sync")
        assert response.status_code == 401
