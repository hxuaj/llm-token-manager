"""
Provider Loaders 测试

测试用例：
- AnthropicLoader 认证头
- AnthropicLoader beta 功能头
- OpenRouterLoader referer 头
- loader 注册和获取
"""
import pytest


class TestProviderLoaderRegistry:
    """测试 loader 注册机制"""

    def test_get_loader_anthropic(self):
        """获取 Anthropic loader"""
        from services.provider_loaders import get_loader
        from services.provider_loaders.builtin import AnthropicLoader

        loader = get_loader("anthropic")
        assert loader is not None
        assert isinstance(loader, AnthropicLoader)

    def test_get_loader_openrouter(self):
        """获取 OpenRouter loader"""
        from services.provider_loaders import get_loader
        from services.provider_loaders.builtin import OpenRouterLoader

        loader = get_loader("openrouter")
        assert loader is not None
        assert isinstance(loader, OpenRouterLoader)

    def test_get_loader_nonexistent(self):
        """获取不存在的 loader 返回 None"""
        from services.provider_loaders import get_loader

        loader = get_loader("nonexistent_provider")
        assert loader is None

    def test_get_all_loaders(self):
        """获取所有已注册的 loaders"""
        from services.provider_loaders import get_all_loaders

        loaders = get_all_loaders()
        assert "anthropic" in loaders
        assert "openrouter" in loaders
        assert "zhipu" in loaders
        assert "deepseek" in loaders
        assert "qwen" in loaders


class TestAnthropicLoader:
    """测试 Anthropic Loader"""

    def test_provider_name(self):
        """验证 provider 名称"""
        from services.provider_loaders import get_loader

        loader = get_loader("anthropic")
        assert loader.provider_name == "anthropic"

    def test_auth_headers(self):
        """测试认证头格式"""
        from services.provider_loaders import get_loader

        loader = get_loader("anthropic")
        headers = loader.get_auth_headers("sk-ant-test123")

        assert headers["x-api-key"] == "sk-ant-test123"
        assert headers["anthropic-version"] == "2023-06-01"
        # 不应包含 Bearer token
        assert "Authorization" not in headers

    def test_extra_headers_without_cache(self):
        """无缓存控制时不添加 beta 头"""
        from services.provider_loaders import get_loader

        loader = get_loader("anthropic")
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        headers = loader.get_extra_headers({}, request_data)

        assert "anthropic-beta" not in headers

    def test_extra_headers_with_cache_control_in_message(self):
        """消息中有缓存控制时添加 beta 头"""
        from services.provider_loaders import get_loader

        loader = get_loader("anthropic")
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Hello"},
                        {"type": "text", "text": "cached", "cache_control": {"type": "ephemeral"}}
                    ]
                }
            ]
        }
        headers = loader.get_extra_headers({}, request_data)

        assert "anthropic-beta" in headers
        assert "prompt-caching-2024-07-31" in headers["anthropic-beta"]

    def test_extra_headers_with_cache_control_in_system(self):
        """system 中有缓存控制时添加 beta 头"""
        from services.provider_loaders import get_loader

        loader = get_loader("anthropic")
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "system": {
                "type": "text",
                "text": "You are a helpful assistant.",
                "cache_control": {"type": "ephemeral"}
            },
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        headers = loader.get_extra_headers({}, request_data)

        assert "anthropic-beta" in headers


class TestOpenRouterLoader:
    """测试 OpenRouter Loader"""

    def test_provider_name(self):
        """验证 provider 名称"""
        from services.provider_loaders import get_loader

        loader = get_loader("openrouter")
        assert loader.provider_name == "openrouter"

    def test_auth_headers_uses_bearer(self):
        """测试认证头使用 Bearer token"""
        from services.provider_loaders import get_loader

        loader = get_loader("openrouter")
        headers = loader.get_auth_headers("sk-or-test123")

        assert headers["Authorization"] == "Bearer sk-or-test123"

    def test_extra_headers_includes_referer(self):
        """测试包含 referer 头"""
        from services.provider_loaders import get_loader

        loader = get_loader("openrouter")
        headers = loader.get_extra_headers({}, None)

        assert "HTTP-Referer" in headers
        assert "X-Title" in headers
        assert headers["HTTP-Referer"] == "https://llm-token-manager.local"
        assert headers["X-Title"] == "LLM Token Manager"


class TestZhipuLoader:
    """测试智谱 AI Loader"""

    def test_provider_name(self):
        """验证 provider 名称"""
        from services.provider_loaders import get_loader

        loader = get_loader("zhipu")
        assert loader.provider_name == "zhipu"

    def test_auth_headers_uses_bearer(self):
        """测试认证头使用 Bearer token"""
        from services.provider_loaders import get_loader

        loader = get_loader("zhipu")
        headers = loader.get_auth_headers("zhipu-api-key")

        assert headers["Authorization"] == "Bearer zhipu-api-key"


class TestDeepSeekLoader:
    """测试 DeepSeek Loader"""

    def test_provider_name(self):
        """验证 provider 名称"""
        from services.provider_loaders import get_loader

        loader = get_loader("deepseek")
        assert loader.provider_name == "deepseek"


class TestQwenLoader:
    """测试通义千问 Loader"""

    def test_provider_name(self):
        """验证 provider 名称"""
        from services.provider_loaders import get_loader

        loader = get_loader("qwen")
        assert loader.provider_name == "qwen"


class TestBaseProviderLoader:
    """测试基类默认行为"""

    def test_default_modify_request_body(self):
        """默认不修改请求体"""
        from services.provider_loaders import get_loader

        loader = get_loader("deepseek")  # 使用一个没有特殊处理的 loader
        original_body = {"model": "deepseek-chat", "messages": []}
        modified_body = loader.modify_request_body(original_body)

        assert modified_body == original_body

    def test_default_get_extra_headers(self):
        """默认返回空字典"""
        from services.provider_loaders import get_loader

        loader = get_loader("deepseek")
        headers = loader.get_extra_headers({}, None)

        assert headers == {}
