"""
模型发现服务测试

测试模型发现、定价匹配、分页等功能
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from decimal import Decimal
from httpx import TimeoutException

from services.model_discovery import (
    ModelDiscoveryService,
    DiscoveryResult,
    UnsupportedDiscoveryError,
    DiscoveryUpstreamError
)
from services.model_pricing_defaults import is_chat_model, get_default_pricing
from models.model_catalog import ModelCatalog, ModelStatus, ModelSource
from models.provider import Provider, ApiFormat
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus


# ─────────────────────────────────────────────────────────────────────
# is_chat_model 测试
# ─────────────────────────────────────────────────────────────────────

class TestChatModelFilter:
    """测试 Chat 模型过滤"""

    def test_gpt_models_are_chat_models(self):
        """GPT 模型应该是 Chat 模型"""
        assert is_chat_model("gpt-4o") == True
        assert is_chat_model("gpt-4o-mini") == True
        assert is_chat_model("gpt-3.5-turbo") == True

    def test_claude_models_are_chat_models(self):
        """Claude 模型应该是 Chat 模型"""
        assert is_chat_model("claude-sonnet-4-20250514") == True
        assert is_chat_model("claude-opus-4-20250514") == True
        assert is_chat_model("claude-haiku-4-5-20251001") == True

    def test_embedding_models_not_chat_models(self):
        """Embedding 模型不是 Chat 模型"""
        assert is_chat_model("text-embedding-3-small") == False
        assert is_chat_model("text-embedding-ada-002") == False

    def test_tts_models_not_chat_models(self):
        """TTS 模型不是 Chat 模型"""
        assert is_chat_model("tts-1") == False
        assert is_chat_model("tts-1-hd") == False

    def test_whisper_models_not_chat_models(self):
        """Whisper 模型不是 Chat 模型"""
        assert is_chat_model("whisper-1") == False

    def test_dalle_models_not_chat_models(self):
        """DALL-E 模型不是 Chat 模型"""
        assert is_chat_model("dall-e-3") == False
        assert is_chat_model("dall-e-2") == False

    def test_moderation_models_not_chat_models(self):
        """Moderation 模型不是 Chat 模型"""
        assert is_chat_model("text-moderation-latest") == False

    def test_glm_models_are_chat_models(self):
        """GLM 模型应该是 Chat 模型"""
        assert is_chat_model("glm-5") == True
        assert is_chat_model("glm-4-plus") == True

    def test_unknown_model_not_chat_model(self):
        """未知前缀的模型不是 Chat 模型"""
        assert is_chat_model("some-random-model") == False


# ─────────────────────────────────────────────────────────────────────
# ModelDiscoveryService 测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestModelDiscovery:
    """测试模型发现"""

    @pytest.fixture
    def discovery_service(self):
        """创建模型发现服务实例"""
        return ModelDiscoveryService(timeout=10)

    @pytest.fixture
    def mock_provider(self):
        """创建 Mock 供应商"""
        provider = MagicMock(spec=Provider)
        provider.id = "test-provider-id"
        provider.name = "test-provider"
        provider.base_url = "https://api.test.com"
        provider.api_format = ApiFormat.OPENAI
        return provider

    @pytest.fixture
    def mock_api_key(self):
        """创建 Mock API Key"""
        api_key = MagicMock(spec=ProviderApiKey)
        api_key.encrypted_key = "encrypted-key"
        api_key.status = ProviderKeyStatus.ACTIVE
        return api_key

    async def test_discover_openai_models(self, discovery_service, mock_provider, mock_api_key):
        """测试 OpenAI 模型发现"""
        mock_db = AsyncMock()

        # Mock 解密函数
        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            # Mock httpx 请求
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "gpt-4o", "owned_by": "openai"},
                    {"id": "gpt-4o-mini", "owned_by": "openai"},
                    {"id": "text-embedding-3-small", "owned_by": "openai"},  # 应该被过滤
                    {"id": "whisper-1", "owned_by": "openai"},  # 应该被过滤
                ]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

                # Mock 数据库查询 - 模型不存在
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_db.execute = AsyncMock(return_value=mock_result)

                # 捕获添加的模型
                added_models = []
                mock_db.add = lambda m: added_models.append(m)
                mock_db.commit = AsyncMock()

                result = await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

                assert result.discovered == 2  # 只有 gpt-4o 和 gpt-4o-mini
                assert result.new_models == 2

    async def test_discover_anthropic_models(self, discovery_service, mock_provider, mock_api_key):
        """测试 Anthropic 模型发现"""
        mock_provider.api_format = ApiFormat.ANTHROPIC

        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"},
                    {"id": "claude-opus-4-20250514", "display_name": "Claude Opus 4"},
                ],
                "has_more": False
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

                # Mock 数据库查询 - 模型不存在
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_db.execute = AsyncMock(return_value=mock_result)

                added_models = []
                mock_db.add = lambda m: added_models.append(m)
                mock_db.commit = AsyncMock()

                result = await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

                assert result.discovered == 2
                assert result.new_models == 2

    async def test_discover_anthropic_pagination(self, discovery_service, mock_provider, mock_api_key):
        """测试 Anthropic 分页发现"""
        mock_provider.api_format = ApiFormat.ANTHROPIC

        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            # 第一次请求返回 has_more=true
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {
                "data": [
                    {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"},
                ],
                "has_more": True
            }

            # 第二次请求返回 has_more=false
            mock_response2 = MagicMock()
            mock_response2.status_code = 200
            mock_response2.json.return_value = {
                "data": [
                    {"id": "claude-opus-4-20250514", "display_name": "Claude Opus 4"},
                ],
                "has_more": False
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_get = AsyncMock(side_effect=[mock_response1, mock_response2])
                mock_client.return_value.__aenter__.return_value.get = mock_get

                # Mock 数据库查询 - 模型不存在
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_db.execute = AsyncMock(return_value=mock_result)

                added_models = []
                mock_db.add = lambda m: added_models.append(m)
                mock_db.commit = AsyncMock()

                result = await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

                assert result.discovered == 2
                assert mock_get.call_count == 2

    async def test_merge_with_builtin_pricing(self, discovery_service, mock_provider, mock_api_key):
        """测试合并内置定价"""
        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "claude-sonnet-4-20250514", "owned_by": "anthropic"},
                ]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

                # Mock 数据库查询 - 模型不存在
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_db.execute = AsyncMock(return_value=mock_result)

                # 捕获添加的模型
                added_models = []
                mock_db.add = lambda model: added_models.append(model)
                mock_db.commit = AsyncMock()

                result = await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

                assert result.pricing_matched == 1
                assert len(added_models) == 1
                assert added_models[0].is_pricing_confirmed == True
                assert added_models[0].source == ModelSource.BUILTIN_DEFAULT

    async def test_unknown_model_pricing_pending(self, discovery_service, mock_provider, mock_api_key):
        """测试未知模型定价待确认"""
        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    # 使用一个符合 chat 模型前缀但不在定价表中的模型 ID
                    {"id": "gpt-new-experimental", "owned_by": "openai"},
                ]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

                # Mock 数据库查询 - 模型不存在
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_db.execute = AsyncMock(return_value=mock_result)

                added_models = []
                mock_db.add = lambda m: added_models.append(m)
                mock_db.commit = AsyncMock()

                result = await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

                assert result.pricing_pending == 1
                assert len(added_models) == 1
                assert added_models[0].is_pricing_confirmed == False
                assert added_models[0].input_price == Decimal("0")

    async def test_skip_existing_models(self, discovery_service, mock_provider, mock_api_key):
        """测试跳过已存在的模型"""
        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "gpt-4o", "owned_by": "openai"},
                ]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

                # 模型已存在
                mock_db.execute = AsyncMock()
                mock_db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

                result = await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

                assert result.new_models == 0
                assert result.discovered == 1

    async def test_discovery_upstream_error(self, discovery_service, mock_provider, mock_api_key):
        """测试上游错误"""
        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            mock_response = MagicMock()
            mock_response.status_code = 500

            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

                with pytest.raises(DiscoveryUpstreamError):
                    await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

    async def test_discovery_timeout(self, discovery_service, mock_provider, mock_api_key):
        """测试超时"""
        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=TimeoutException("timeout")
                )

                with pytest.raises(DiscoveryUpstreamError):
                    await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)

    async def test_unsupported_provider(self, discovery_service, mock_provider, mock_api_key):
        """测试不支持的供应商"""
        mock_provider.api_format = "unknown_format"
        mock_db = AsyncMock()

        with patch('services.model_discovery.decrypt', return_value='decrypted-key'):
            with pytest.raises(UnsupportedDiscoveryError):
                await discovery_service.discover_models(mock_provider, mock_api_key, mock_db)


# ─────────────────────────────────────────────────────────────────────
# 自动发现触发测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAutoDiscoveryTrigger:
    """测试添加 Key 时的自动发现触发"""

    async def test_coding_plan_key_skips_discovery(self, client, test_admin, admin_token):
        """添加 coding_plan Key 时不触发自动发现"""
        # TODO: 需要先创建供应商
        pass

    async def test_standard_key_triggers_discovery(self, client, test_admin, admin_token):
        """添加第一个 standard Key 时触发自动发现"""
        # TODO: 需要先创建供应商
        pass
