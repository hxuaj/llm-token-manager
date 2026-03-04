"""
供应商预设 API 测试

测试用例：
- 获取预设列表
- 验证 API Key
- 一键创建供应商
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid


class TestProviderPresets:
    """测试预设列表接口"""

    @pytest.mark.asyncio
    async def test_get_presets_list(self, client, admin_token):
        """获取预设列表"""
        response = await client.get(
            "/api/admin/providers/presets",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "presets" in data
        assert len(data["presets"]) > 0

        # 验证预设结构
        preset = data["presets"][0]
        assert "id" in preset
        assert "name" in preset
        assert "display_name" in preset
        assert "api_format" in preset
        assert "default_base_url" in preset
        assert "supported_endpoints" in preset

    @pytest.mark.asyncio
    async def test_get_presets_includes_standard_providers(self, client, admin_token):
        """预设包含主要供应商"""
        response = await client.get(
            "/api/admin/providers/presets",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        preset_ids = [p["id"] for p in data["presets"]]

        # 验证包含主要供应商（精简为 5 个）
        assert "openai" in preset_ids
        assert "anthropic" in preset_ids
        assert "zhipuai-coding-plan" in preset_ids
        assert "minimax-cn-coding-plan" in preset_ids
        assert "openrouter" in preset_ids

    @pytest.mark.asyncio
    async def test_get_presets_unauthorized(self, client):
        """未授权访问"""
        response = await client.get("/api/admin/providers/presets")
        assert response.status_code == 401


class TestValidateApiKey:
    """测试 API Key 验证接口"""

    @pytest.mark.asyncio
    async def test_validate_key_success(self, client, admin_token):
        """验证 Key 成功"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": "gpt-4o", "name": "GPT-4o"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini"}
                ]
            }
            mock_response.raise_for_status = MagicMock()

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response
            mock_client.return_value = mock_instance

            response = await client.post(
                "/api/admin/providers/validate-key",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "provider_preset": "openai",
                    "api_key": "sk-test-key-12345"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "discovered_models" in data
        assert len(data["discovered_models"]) > 0

    @pytest.mark.asyncio
    async def test_validate_key_invalid(self, client, admin_token):
        """验证无效 Key"""
        import httpx

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401)
            )
            mock_client.return_value = mock_instance

            response = await client.post(
                "/api/admin/providers/validate-key",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "provider_preset": "openai",
                    "api_key": "sk-invalid-key"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "error" in data

    @pytest.mark.asyncio
    async def test_validate_key_with_custom_base_url(self, client, admin_token):
        """验证自定义 base_url"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": []}
            mock_response.raise_for_status = MagicMock()

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response
            mock_client.return_value = mock_instance

            response = await client.post(
                "/api/admin/providers/validate-key",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "provider_preset": "openai",
                    "api_key": "sk-test-key",
                    "custom_base_url": "https://custom.api.com/v1"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["auto_config"]["base_url"] == "https://custom.api.com/v1"


class TestQuickCreateProvider:
    """测试一键创建供应商接口"""

    @pytest.mark.asyncio
    async def test_quick_create_success(self, client, admin_token, db_session):
        """一键创建供应商成功"""
        with patch('routers.admin.get_discovery_service') as mock_discovery:
            mock_service = AsyncMock()
            mock_service.discover_models.return_value = [
                {
                    "model_id": "gpt-4o-mini",
                    "display_name": "GPT-4o Mini",
                    "input_price": 0.15,
                    "output_price": 0.6,
                    "context_window": 128000,
                    "supports_vision": True,
                    "supports_tools": True,
                }
            ]
            mock_discovery.return_value = mock_service

            response = await client.post(
                "/api/admin/providers/quick-create",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "provider_preset": "openai",
                    "api_key": "sk-test-key-12345678"
                }
            )

        assert response.status_code == 201
        data = response.json()
        assert "provider" in data
        assert "api_key" in data
        assert "discovery_result" in data
        assert data["provider"]["name"] == "openai"

    @pytest.mark.asyncio
    async def test_quick_create_provider_already_exists(self, client, admin_token, db_session):
        """供应商已存在"""
        from models.provider import Provider

        # 先创建一个 openai 供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="openai",
            base_url="https://api.openai.com/v1",
            api_format="openai",
            enabled=True
        )
        db_session.add(provider)
        await db_session.commit()

        response = await client.post(
            "/api/admin/providers/quick-create",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider_preset": "openai",
                "api_key": "sk-test-key"
            }
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_quick_create_invalid_preset(self, client, admin_token):
        """无效预设 ID"""
        response = await client.post(
            "/api/admin/providers/quick-create",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider_preset": "nonexistent",
                "api_key": "sk-test-key"
            }
        )

        assert response.status_code == 400
