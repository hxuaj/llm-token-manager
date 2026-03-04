"""
供应商预设 API 测试

测试用例：
- 获取预设列表
- 验证 API Key（新流程：本地 ModelCatalog > models.dev > API）
- 一键创建供应商（新流程：本地 ModelCatalog > models.dev > API）
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
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
    """测试 API Key 验证接口（新流程）"""

    @pytest.mark.asyncio
    async def test_validate_key_fallback_to_models_dev(self, client, admin_token, db_session):
        """本地无数据时，从 models.dev 获取（默认行为）"""
        # Mock models.dev 返回空数据，测试回退逻辑
        with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
            mock_fetch.return_value = []  # 模拟 models.dev 也无数据

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
        # 本地无数据，models.dev 也无数据，来源为 none
        assert data["models_source"] == "none"
        assert data["discovered_models"] == []

    @pytest.mark.asyncio
    async def test_validate_key_with_local_catalog_data(self, client, admin_token, db_session):
        """从本地 ModelCatalog 获取模型（优先级最高）"""
        from models.provider import Provider
        from models.model_catalog import ModelCatalog, ModelStatus, ModelSource

        # 创建供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="openai",
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_format="openai",
            enabled=True,
            models_dev_id="openai",
        )
        db_session.add(provider)
        await db_session.flush()

        # 创建模型
        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="gpt-4o",
            display_name="GPT-4o",
            provider_id=provider.id,
            input_price=Decimal("2.5"),
            output_price=Decimal("10.0"),
            status=ModelStatus.ACTIVE,
            source=ModelSource.MODELS_DEV,
            is_pricing_confirmed=True,
        )
        db_session.add(model)
        await db_session.commit()

        # 调用接口
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
        assert data["models_source"] == "catalog"
        assert len(data["discovered_models"]) == 1
        assert data["discovered_models"][0]["model_id"] == "gpt-4o"
        assert data["discovered_models"][0]["pricing_source"] == "catalog"
        assert data["summary"]["catalog_models"] == 1

    @pytest.mark.asyncio
    async def test_validate_key_with_api_validation(self, client, admin_token, db_session):
        """使用 validate_api=True 验证 API Key"""
        with patch('services.api_validator.validate_api_key') as mock_validate:
            mock_validate.return_value = MagicMock(
                valid=True,
                error_type=None,
                error_message=None
            )

            # Mock models.dev 返回空数据
            with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
                mock_fetch.return_value = []

                response = await client.post(
                    "/api/admin/providers/validate-key",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "provider_preset": "openai",
                        "api_key": "sk-test-key-12345",
                        "validate_api": True
                    }
                )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["api_validation"] is not None
        assert data["api_validation"]["performed"] is True
        assert data["api_validation"]["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_key_with_api_validation_failed(self, client, admin_token, db_session):
        """API 验证失败但仍然返回本地数据"""
        with patch('services.api_validator.validate_api_key') as mock_validate:
            mock_validate.return_value = MagicMock(
                valid=False,
                error_type="invalid_key",
                error_message="API Key 无效或已过期"
            )

            # Mock models.dev 返回空数据
            with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
                mock_fetch.return_value = []

                response = await client.post(
                    "/api/admin/providers/validate-key",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "provider_preset": "openai",
                        "api_key": "sk-invalid-key",
                        "validate_api": True
                    }
                )

        assert response.status_code == 200
        data = response.json()
        # 即使 API 验证失败，仍然返回 valid=True
        assert data["valid"] is True
        assert data["api_validation"]["valid"] is False
        assert data["api_validation"]["error_type"] == "invalid_key"

    @pytest.mark.asyncio
    async def test_validate_key_with_api_discovery(self, client, admin_token, db_session):
        """使用 discover_from_api=True 从 API 发现模型"""
        from services.api_discovery import DiscoveredModelInfo, DiscoveryResult

        # Mock models.dev 返回空数据
        with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
            mock_fetch.return_value = []

            with patch('services.api_discovery.discover_models_from_api') as mock_discover:
                mock_discover.return_value = DiscoveryResult(
                    success=True,
                    models=[
                        DiscoveredModelInfo(
                            model_id="gpt-4o",
                            display_name="GPT-4o",
                            input_price=Decimal("0"),
                            output_price=Decimal("0"),
                        ),
                        DiscoveredModelInfo(
                            model_id="gpt-4o-mini",
                            display_name="GPT-4o Mini",
                            input_price=Decimal("0"),
                            output_price=Decimal("0"),
                        ),
                    ],
                    total_count=2,
                )

                response = await client.post(
                    "/api/admin/providers/validate-key",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "provider_preset": "openai",
                        "api_key": "sk-test-key-12345",
                        "discover_from_api": True
                    }
                )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["models_source"] == "api"
        assert len(data["discovered_models"]) == 2
        # API 发现的模型标记 from_api=True
        assert data["discovered_models"][0]["from_api"] is True

    @pytest.mark.asyncio
    async def test_validate_key_invalid_preset(self, client, admin_token):
        """无效预设"""
        response = await client.post(
            "/api/admin/providers/validate-key",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider_preset": "nonexistent",
                "api_key": "sk-test-key"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "error" in data
        assert data["error"]["type"] == "invalid_preset"

    @pytest.mark.asyncio
    async def test_validate_key_with_custom_base_url(self, client, admin_token):
        """验证自定义 base_url"""
        # Mock models.dev 返回空数据
        with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
            mock_fetch.return_value = []

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

    @pytest.mark.asyncio
    async def test_validate_key_minimax_with_local_catalog(self, client, admin_token, db_session):
        """MiniMax 供应商从本地 ModelCatalog 获取模型"""
        from models.provider import Provider
        from models.model_catalog import ModelCatalog, ModelStatus, ModelSource

        # 创建 MiniMax 供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="minimax",
            display_name="MiniMax",
            base_url="https://api.minimaxi.com/anthropic/v1",
            api_format="openai_compatible",
            enabled=True,
            models_dev_id="minimax",
        )
        db_session.add(provider)
        await db_session.flush()

        # 创建模型
        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="MiniMax-M2.5",
            display_name="MiniMax M2.5",
            provider_id=provider.id,
            input_price=Decimal("0.5"),
            output_price=Decimal("2.0"),
            status=ModelStatus.ACTIVE,
            source=ModelSource.MODELS_DEV,
            is_pricing_confirmed=True,
        )
        db_session.add(model)
        await db_session.commit()

        # 调用接口
        response = await client.post(
            "/api/admin/providers/validate-key",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "provider_preset": "minimax-cn-coding-plan",
                "api_key": "test-minimax-key"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["models_source"] == "catalog"
        assert len(data["discovered_models"]) == 1
        assert data["discovered_models"][0]["model_id"] == "MiniMax-M2.5"


class TestQuickCreateProvider:
    """测试一键创建供应商接口（新流程）"""

    @pytest.mark.asyncio
    async def test_quick_create_from_models_dev(self, client, admin_token, db_session):
        """从 models.dev 获取模型（本地无数据时的回退）"""
        from routers.admin_provider_presets import ModelsDevModel

        # Mock models.dev 返回模型
        with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
            mock_fetch.return_value = [
                ModelsDevModel(
                    model_id="gpt-4o-mini",
                    display_name="GPT-4o Mini",
                    input_price=Decimal("0.15"),
                    output_price=Decimal("0.6"),
                    context_window=128000,
                    supports_vision=True,
                    supports_tools=True,
                ),
            ]

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
        # 从 models.dev 获取的模型
        assert data["discovery_result"]["total_models"] == 1
        assert data["discovery_result"]["models_source"] == "models_dev"

    @pytest.mark.asyncio
    async def test_quick_create_with_api_discovery(self, client, admin_token, db_session):
        """从 API 发现模型（discover_from_api=True）"""
        from services.api_discovery import DiscoveredModelInfo, DiscoveryResult

        # Mock models.dev 返回空数据
        with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
            mock_fetch.return_value = []

            with patch('services.api_discovery.discover_models_from_api') as mock_discover:
                mock_discover.return_value = DiscoveryResult(
                    success=True,
                    models=[
                        DiscoveredModelInfo(
                            model_id="gpt-4o",
                            display_name="GPT-4o",
                            input_price=Decimal("0"),
                            output_price=Decimal("0"),
                        ),
                    ],
                    total_count=1,
                )

                response = await client.post(
                    "/api/admin/providers/quick-create",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "provider_preset": "openai",
                        "api_key": "sk-test-key-12345678",
                        "discover_from_api": True
                    }
                )

        assert response.status_code == 201
        data = response.json()
        assert data["provider"]["name"] == "openai"
        assert data["discovery_result"]["total_models"] == 1
        assert data["discovery_result"]["models_source"] == "api"

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

    @pytest.mark.asyncio
    async def test_quick_create_minimax_from_models_dev(self, client, admin_token, db_session):
        """MiniMax 供应商从 models.dev 获取模型"""
        from routers.admin_provider_presets import ModelsDevModel

        # Mock models.dev 返回模型
        with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
            mock_fetch.return_value = [
                ModelsDevModel(
                    model_id="MiniMax-M2.5",
                    display_name="MiniMax M2.5",
                    input_price=Decimal("0.5"),
                    output_price=Decimal("2.0"),
                ),
            ]

            response = await client.post(
                "/api/admin/providers/quick-create",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "provider_preset": "minimax-cn-coding-plan",
                    "api_key": "test-minimax-key"
                }
            )

        assert response.status_code == 201
        data = response.json()
        assert data["provider"]["name"] == "minimax"
        assert data["discovery_result"]["models_source"] == "models_dev"
        assert data["discovery_result"]["total_models"] == 1

    @pytest.mark.asyncio
    async def test_quick_create_without_auto_activate(self, client, admin_token, db_session):
        """不自动激活模型"""
        from routers.admin_provider_presets import ModelsDevModel

        # Mock models.dev 返回模型
        with patch('routers.admin_provider_presets.fetch_models_from_models_dev') as mock_fetch:
            mock_fetch.return_value = [
                ModelsDevModel(
                    model_id="gpt-4o",
                    display_name="GPT-4o",
                    input_price=Decimal("2.5"),
                    output_price=Decimal("10.0"),
                ),
            ]

            response = await client.post(
                "/api/admin/providers/quick-create",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "provider_preset": "openai",
                    "api_key": "sk-test-key",
                    "auto_activate_models": False
                }
            )

        assert response.status_code == 201
        data = response.json()
        # 模型被发现但未激活
        assert data["discovery_result"]["total_models"] == 1
        assert data["discovery_result"]["activated_models"] == 0
