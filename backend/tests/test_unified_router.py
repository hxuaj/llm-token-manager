"""
统一路由服务测试

测试用例：
- 解析模型字符串（隐式前缀、显式 provider/model）
- 检查端点支持
- 获取适配器（OpenAI 兼容、Anthropic 转换、Anthropic 透传）
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid

from services.unified_router import UnifiedRouterService, RouteRule


class TestUnifiedRouterParseModel:
    """测试模型解析"""

    def test_parse_model_implicit_prefix_openai(self):
        """测试隐式前缀 - OpenAI 模型"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("gpt-4o")
        assert provider == "openai"
        assert model == "gpt-4o"

    def test_parse_model_implicit_prefix_anthropic(self):
        """测试隐式前缀 - Anthropic 模型"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("claude-sonnet-4-20250514")
        assert provider == "anthropic"
        assert model == "claude-sonnet-4-20250514"

    def test_parse_model_implicit_prefix_zhipu(self):
        """测试隐式前缀 - 智谱模型"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("glm-4-plus")
        assert provider == "zhipu"
        assert model == "glm-4-plus"

    def test_parse_model_implicit_prefix_minimax(self):
        """测试隐式前缀 - MiniMax 模型"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("minimax-m2.5")
        assert provider == "minimax"
        assert model == "minimax-m2.5"

    def test_parse_model_implicit_prefix_minimax_uppercase(self):
        """测试隐式前缀 - MiniMax 大写"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("MiniMax-M2.5")
        assert provider == "minimax"
        assert model == "MiniMax-M2.5"

    def test_parse_model_explicit_provider(self):
        """测试显式 provider/model 格式"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("openai/gpt-4o")
        assert provider == "openai"
        assert model == "gpt-4o"

    def test_parse_model_explicit_provider_anthropic(self):
        """测试显式格式 - Anthropic"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("anthropic/claude-sonnet-4")
        assert provider == "anthropic"
        assert model == "claude-sonnet-4"

    def test_parse_model_explicit_provider_zhipu(self):
        """测试显式格式 - 智谱"""
        router = UnifiedRouterService()

        provider, model = router.parse_model_string("zhipu/glm-4")
        assert provider == "zhipu"
        assert model == "glm-4"

    def test_parse_model_openrouter_format(self):
        """测试 OpenRouter 格式"""
        router = UnifiedRouterService()

        # OpenRouter 格式: provider/model
        provider, model = router.parse_model_string("anthropic/claude-sonnet-4")
        # 由于 anthropic/ 前缀匹配，会被路由到 openrouter
        # 但如果显式指定 provider，则使用显式值
        assert provider == "anthropic"
        assert model == "claude-sonnet-4"

    def test_parse_model_unknown(self):
        """测试未知模型"""
        router = UnifiedRouterService()

        with pytest.raises(ValueError, match="Unknown model"):
            router.parse_model_string("unknown-model-xyz")


class TestUnifiedRouterEndpointSupport:
    """测试端点支持检查"""

    def test_supports_endpoint_openai_gpt(self):
        """测试 OpenAI 支持 OpenAI 端点"""
        router = UnifiedRouterService()

        assert router.supports_endpoint("openai", "openai") is True
        assert router.supports_endpoint("openai", "anthropic") is False

    def test_supports_endpoint_anthropic(self):
        """测试 Anthropic 支持两种端点"""
        router = UnifiedRouterService()

        assert router.supports_endpoint("anthropic", "openai") is True
        assert router.supports_endpoint("anthropic", "anthropic") is True

    def test_supports_endpoint_zhipu(self):
        """测试智谱支持两种端点"""
        router = UnifiedRouterService()

        assert router.supports_endpoint("zhipu", "openai") is True
        assert router.supports_endpoint("zhipu", "anthropic") is True

    def test_supports_endpoint_minimax(self):
        """测试 MiniMax 支持两种端点"""
        router = UnifiedRouterService()

        assert router.supports_endpoint("minimax", "openai") is True
        assert router.supports_endpoint("minimax", "anthropic") is True

    def test_supports_endpoint_unknown_provider(self):
        """测试未知供应商"""
        router = UnifiedRouterService()

        assert router.supports_endpoint("unknown", "openai") is False


class TestUnifiedRouterGetRouteRule:
    """测试获取路由规则"""

    def test_get_route_rule_openai(self):
        """测试获取 OpenAI 规则"""
        router = UnifiedRouterService()

        rule = router.get_route_rule("openai")
        assert rule is not None
        assert rule.api_format == "openai"
        assert "openai" in rule.supported_endpoints
        assert "anthropic" not in rule.supported_endpoints

    def test_get_route_rule_anthropic(self):
        """测试获取 Anthropic 规则"""
        router = UnifiedRouterService()

        rule = router.get_route_rule("anthropic")
        assert rule is not None
        assert rule.api_format == "anthropic"
        assert "openai" in rule.supported_endpoints
        assert "anthropic" in rule.supported_endpoints

    def test_get_route_rule_unknown(self):
        """测试获取未知供应商规则"""
        router = UnifiedRouterService()

        rule = router.get_route_rule("unknown")
        assert rule is None


class TestUnifiedRouterAdapter:
    """测试适配器获取"""

    @pytest.mark.asyncio
    async def test_get_adapter_openai_compatible(self, db_session):
        """测试获取 OpenAI 兼容适配器"""
        router = UnifiedRouterService()

        # 创建 mock provider
        from models.provider import Provider
        provider = Provider(
            id=uuid.uuid4(),
            name="zhipu",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_format="openai_compatible",
            supported_endpoints=["openai", "anthropic"]
        )

        adapter = router.create_adapter(provider, "test-api-key", "openai")

        from services.providers.openai_compatible import OpenAICompatibleAdapter
        assert isinstance(adapter, OpenAICompatibleAdapter)

    @pytest.mark.asyncio
    async def test_get_adapter_anthropic_for_openai_endpoint(self, db_session):
        """测试 OpenAI 端点获取 Anthropic 适配器（需要格式转换）"""
        router = UnifiedRouterService()

        from models.provider import Provider
        provider = Provider(
            id=uuid.uuid4(),
            name="anthropic",
            base_url="https://api.anthropic.com",
            api_format="anthropic",
            supported_endpoints=["openai", "anthropic"]
        )

        adapter = router.create_adapter(provider, "test-api-key", "openai")

        from services.providers.anthropic_adapter import AnthropicAdapter
        assert isinstance(adapter, AnthropicAdapter)

    @pytest.mark.asyncio
    async def test_get_adapter_anthropic_passthrough(self, db_session):
        """测试 Anthropic 端点获取 Anthropic 透传适配器"""
        router = UnifiedRouterService()

        from models.provider import Provider
        provider = Provider(
            id=uuid.uuid4(),
            name="anthropic",
            base_url="https://api.anthropic.com",
            api_format="anthropic",
            supported_endpoints=["openai", "anthropic"]
        )

        adapter = router.create_adapter(provider, "test-api-key", "anthropic")

        from services.providers.anthropic_passthrough import AnthropicPassthroughAdapter
        assert isinstance(adapter, AnthropicPassthroughAdapter)

    @pytest.mark.asyncio
    async def test_get_adapter_zhipu_anthropic_endpoint(self, db_session):
        """测试智谱供应商使用 Anthropic 端点"""
        router = UnifiedRouterService()

        from models.provider import Provider
        provider = Provider(
            id=uuid.uuid4(),
            name="zhipu",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_format="openai_compatible",
            supported_endpoints=["openai", "anthropic"]
        )

        adapter = router.create_adapter(provider, "test-api-key", "anthropic")

        from services.providers.anthropic_passthrough import AnthropicPassthroughAdapter
        assert isinstance(adapter, AnthropicPassthroughAdapter)


class TestUnifiedRouterGetProvider:
    """测试获取供应商"""

    @pytest.mark.asyncio
    async def test_get_provider_by_name(self, db_session):
        """测试通过名称获取供应商"""
        from models.provider import Provider

        # 创建测试供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="test-provider",
            base_url="https://api.test.com/v1",
            api_format="openai_compatible",
            enabled=True
        )
        db_session.add(provider)
        await db_session.commit()

        router = UnifiedRouterService()
        result = await router.get_provider_by_name("test-provider", db_session)

        assert result is not None
        assert result.name == "test-provider"

    @pytest.mark.asyncio
    async def test_get_provider_not_found(self, db_session):
        """测试供应商不存在"""
        router = UnifiedRouterService()
        result = await router.get_provider_by_name("nonexistent", db_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_provider_disabled(self, db_session):
        """测试禁用的供应商"""
        from models.provider import Provider

        provider = Provider(
            id=uuid.uuid4(),
            name="disabled-provider",
            base_url="https://api.test.com/v1",
            api_format="openai_compatible",
            enabled=False
        )
        db_session.add(provider)
        await db_session.commit()

        router = UnifiedRouterService()
        result = await router.get_provider_by_name("disabled-provider", db_session)

        # 默认只返回启用的供应商
        assert result is None
