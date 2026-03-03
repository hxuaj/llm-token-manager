"""
models.dev 数据同步服务测试

测试用例：
- 成功获取数据
- 缓存命中
- 强制刷新缓存
- 配置合并（简单字段、嵌套对象、None 值删除）
- 同步到数据库（新供应商、保留本地覆盖）
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from copy import deepcopy

from services.models_dev_service import ModelsDevService, SyncResult


class TestModelsDevServiceFetch:
    """测试数据获取"""

    @pytest.mark.asyncio
    async def test_fetch_all_data_success(self):
        """成功获取数据"""
        mock_data = {
            "openai": {
                "id": "openai",
                "name": "OpenAI",
                "api": "https://api.openai.com/v1",
                "models": {
                    "gpt-4o": {
                        "name": "GPT-4o",
                        "cost": {"input": 2.5, "output": 10.0}
                    }
                }
            }
        }

        service = ModelsDevService()
        with patch.object(service, '_fetch_from_remote', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.fetch_all_data()

            assert result == mock_data
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_all_data_with_cache(self):
        """缓存命中"""
        mock_data = {"openai": {"id": "openai"}}

        service = ModelsDevService()
        service._cache = mock_data
        service._cache_expires = datetime.utcnow() + timedelta(hours=1)

        with patch.object(service, '_fetch_from_remote', new_callable=AsyncMock) as mock_fetch:
            result = await service.fetch_all_data()

            assert result == mock_data
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_all_data_force_refresh(self):
        """强制刷新缓存"""
        mock_data_old = {"openai": {"id": "openai", "version": "old"}}
        mock_data_new = {"openai": {"id": "openai", "version": "new"}}

        service = ModelsDevService()
        service._cache = mock_data_old
        service._cache_expires = datetime.utcnow() + timedelta(hours=1)

        with patch.object(service, '_fetch_from_remote', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data_new

            result = await service.fetch_all_data(force_refresh=True)

            assert result == mock_data_new
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_all_data_expired_cache(self):
        """缓存过期后重新获取"""
        mock_data_old = {"openai": {"id": "openai", "version": "old"}}
        mock_data_new = {"openai": {"id": "openai", "version": "new"}}

        service = ModelsDevService()
        service._cache = mock_data_old
        service._cache_expires = datetime.utcnow() - timedelta(hours=1)  # 已过期

        with patch.object(service, '_fetch_from_remote', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data_new

            result = await service.fetch_all_data()

            assert result == mock_data_new
            mock_fetch.assert_called_once()


class TestModelsDevServiceGetProvider:
    """测试获取供应商信息"""

    @pytest.mark.asyncio
    async def test_get_provider_success(self):
        """成功获取供应商"""
        mock_data = {
            "openai": {"id": "openai", "name": "OpenAI"},
            "anthropic": {"id": "anthropic", "name": "Anthropic"}
        }

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.get_provider("openai")

            assert result == mock_data["openai"]

    @pytest.mark.asyncio
    async def test_get_provider_not_found(self):
        """供应商不存在"""
        mock_data = {"openai": {"id": "openai"}}

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.get_provider("nonexistent")

            assert result is None


class TestModelsDevServiceGetModel:
    """测试获取模型信息"""

    @pytest.mark.asyncio
    async def test_get_model_success(self):
        """成功获取模型"""
        mock_data = {
            "openai": {
                "id": "openai",
                "models": {
                    "gpt-4o": {"name": "GPT-4o", "cost": {"input": 2.5}}
                }
            }
        }

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.get_model("openai", "gpt-4o")

            assert result == {"name": "GPT-4o", "cost": {"input": 2.5}}

    @pytest.mark.asyncio
    async def test_get_model_provider_not_found(self):
        """供应商不存在"""
        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {}

            result = await service.get_model("nonexistent", "model-id")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_model_model_not_found(self):
        """模型不存在"""
        mock_data = {
            "openai": {
                "id": "openai",
                "models": {"gpt-4o": {"name": "GPT-4o"}}
            }
        }

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.get_model("openai", "nonexistent-model")

            assert result is None


class TestModelsDevServiceMergeConfigs:
    """测试配置合并"""

    def test_merge_configs_simple(self):
        """简单字段覆盖"""
        base = {"input": 3.5, "output": 15.0, "name": "Claude 4"}
        override = {"input": 3.0}

        result = ModelsDevService.merge_configs(base, override)

        assert result == {"input": 3.0, "output": 15.0, "name": "Claude 4"}

    def test_merge_configs_nested(self):
        """嵌套对象合并"""
        base = {
            "cost": {
                "input": 3.5,
                "output": 15.0,
                "cache": {"read": 0.3, "write": 3.75}
            },
            "limit": {"context": 200000}
        }
        override = {
            "cost": {
                "input": 3.0,
                "cache": {"read": 0.25}
            }
        }

        result = ModelsDevService.merge_configs(base, override)

        assert result == {
            "cost": {
                "input": 3.0,  # 被覆盖
                "output": 15.0,  # 保留
                "cache": {
                    "read": 0.25,  # 被覆盖
                    "write": 3.75  # 保留
                }
            },
            "limit": {"context": 200000}  # 保留
        }

    def test_merge_configs_none_deletes(self):
        """None 值删除字段"""
        base = {
            "input": 3.5,
            "output": 15.0,
            "deprecated_field": "should be removed"
        }
        override = {
            "input": 3.0,
            "deprecated_field": None
        }

        result = ModelsDevService.merge_configs(base, override)

        assert result == {"input": 3.0, "output": 15.0}
        assert "deprecated_field" not in result

    def test_merge_configs_empty_override(self):
        """空覆盖返回原配置"""
        base = {"input": 3.5, "output": 15.0}
        override = {}

        result = ModelsDevService.merge_configs(base, override)

        assert result == base

    def test_merge_configs_new_fields(self):
        """添加新字段"""
        base = {"input": 3.5}
        override = {"new_field": "new_value"}

        result = ModelsDevService.merge_configs(base, override)

        assert result == {"input": 3.5, "new_field": "new_value"}

    def test_merge_configs_list_replaced(self):
        """列表类型被替换而非合并"""
        base = {
            "tags": ["tag1", "tag2"],
            "cost": {"input": 3.5}
        }
        override = {
            "tags": ["new_tag"]
        }

        result = ModelsDevService.merge_configs(base, override)

        assert result == {"tags": ["new_tag"], "cost": {"input": 3.5}}


class TestModelsDevServiceSyncToDatabase:
    """测试同步到数据库"""

    @pytest.mark.asyncio
    async def test_sync_new_provider(self, db_session):
        """同步新供应商"""
        mock_data = {
            "openai": {
                "id": "openai",
                "name": "OpenAI",
                "api": "https://api.openai.com/v1",
                "models": {}
            }
        }

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.sync_to_database(db_session)

            assert result.success is True
            assert result.providers_synced == 1
            assert result.models_synced == 0

    @pytest.mark.asyncio
    async def test_sync_new_model(self, db_session):
        """同步新模型"""
        mock_data = {
            "openai": {
                "id": "openai",
                "name": "OpenAI",
                "api": "https://api.openai.com/v1",
                "models": {
                    "gpt-4o": {
                        "name": "GPT-4o",
                        "cost": {"input": 2.5, "output": 10.0}
                    }
                }
            }
        }

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.sync_to_database(db_session)

            assert result.success is True
            assert result.providers_synced == 1
            assert result.models_synced == 1
            assert result.new_models == 1

    @pytest.mark.asyncio
    async def test_sync_preserves_local_overrides(self, db_session):
        """同步保留本地覆盖"""
        from models.provider import Provider
        from models.model_catalog import ModelCatalog, ModelSource
        import uuid

        # 先创建一个已有供应商和模型
        provider = Provider(
            id=uuid.uuid4(),
            name="openai",
            base_url="https://api.openai.com/v1",
            api_format="openai",
            source=ModelSource.AUTO_DISCOVERED,
            models_dev_id="openai",
            local_overrides={"display_name": "OpenAI (Custom)"}
        )
        db_session.add(provider)

        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="gpt-4o",
            display_name="GPT-4o (Custom)",  # 本地修改
            provider_id=provider.id,
            input_price=3.0,  # 本地覆盖价格
            output_price=12.0,
            source=ModelSource.AUTO_DISCOVERED,
            models_dev_id="gpt-4o",
            base_config={"cost": {"input": 2.5, "output": 10.0}},
            local_overrides={"input_price": 3.0, "display_name": "GPT-4o (Custom)"}
        )
        db_session.add(model)
        await db_session.commit()

        # 模拟远程数据（价格不同）
        mock_data = {
            "openai": {
                "id": "openai",
                "name": "OpenAI",
                "api": "https://api.openai.com/v1",
                "models": {
                    "gpt-4o": {
                        "name": "GPT-4o",
                        "cost": {"input": 2.5, "output": 10.0}  # 远程价格
                    }
                }
            }
        }

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.sync_to_database(db_session)

            assert result.success is True
            assert result.preserved_local >= 1  # 至少保留了一个本地覆盖

            # 验证本地价格未被覆盖
            await db_session.refresh(model)
            assert model.input_price == 3.0  # 保留本地覆盖
            assert model.display_name == "GPT-4o (Custom)"

    @pytest.mark.asyncio
    async def test_sync_specific_provider(self, db_session):
        """同步指定供应商"""
        mock_data = {
            "openai": {"id": "openai", "models": {}},
            "anthropic": {"id": "anthropic", "models": {}}
        }

        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await service.sync_to_database(db_session, provider_id="openai")

            assert result.success is True
            assert result.providers_synced == 1  # 只同步了 openai

    @pytest.mark.asyncio
    async def test_sync_handles_error(self, db_session):
        """处理同步错误"""
        service = ModelsDevService()
        with patch.object(service, 'fetch_all_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")

            result = await service.sync_to_database(db_session)

            assert result.success is False
            assert "Network error" in result.error
