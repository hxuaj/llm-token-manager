"""
Anthropic 透传适配器测试

测试用例：
- 端点路径
- 请求头（x-api-key, anthropic-version）
- 请求透传
- 响应透传
- 转发请求成功
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from services.providers.anthropic_passthrough import AnthropicPassthroughAdapter


class TestAnthropicPassthroughAdapterBasics:
    """测试基本功能"""

    def test_provider_name(self):
        """测试供应商名称"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key"
        )
        assert adapter.provider_name == "anthropic_passthrough"

    def test_get_endpoint(self):
        """测试端点路径"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key"
        )
        assert adapter.get_endpoint() == "https://api.anthropic.com/v1/messages"

    def test_get_endpoint_custom_base(self):
        """测试自定义 base_url"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://custom.api.com",
            api_key="test-key"
        )
        assert adapter.get_endpoint() == "https://custom.api.com/v1/messages"

    def test_convert_request_passthrough(self):
        """测试请求透传"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key"
        )

        request = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hello"}]
        }

        result = adapter.convert_request(request)
        assert result == request

    def test_convert_response_passthrough(self):
        """测试响应透传"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key"
        )

        response = {
            "id": "msg_123",
            "type": "message",
            "content": [{"type": "text", "text": "Hello!"}]
        }

        result = adapter.convert_response(response, "claude-sonnet-4-20250514")
        assert result == response


class TestAnthropicPassthroughAdapterHeaders:
    """测试请求头"""

    def test_get_headers_default(self):
        """测试默认请求头"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key"
        )

        headers = adapter.get_headers()

        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["content-type"] == "application/json"

    def test_get_headers_custom_version(self):
        """测试自定义 anthropic-version"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key",
            default_headers={"anthropic-version": "2024-01-01"}
        )

        headers = adapter.get_headers()

        assert headers["anthropic-version"] == "2024-01-01"

    def test_get_headers_with_beta(self):
        """测试添加 anthropic-beta 头"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key",
            default_headers={
                "anthropic-beta": "claude-code-20250219"
            }
        )

        headers = adapter.get_headers()

        assert headers["anthropic-beta"] == "claude-code-20250219"

    def test_get_headers_custom_headers(self):
        """测试自定义请求头合并"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key",
            default_headers={"X-Custom": "value"}
        )

        headers = adapter.get_headers()

        assert headers["x-api-key"] == "test-key"
        assert headers["X-Custom"] == "value"


class TestAnthropicPassthroughAdapterForward:
    """测试请求转发"""

    @pytest.mark.asyncio
    async def test_forward_request_success(self):
        """测试转发请求成功"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "msg_123",
            "type": "message",
            "content": [{"type": "text", "text": "Hello!"}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_response
            mock_client.return_value = mock_instance

            request = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hello"}]
            }

            result = await adapter.forward_request(request)

            assert result["id"] == "msg_123"
            mock_instance.post.assert_called_once()

            # 验证使用了正确的端点
            call_args = mock_instance.post.call_args
            assert "v1/messages" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_forward_request_with_correct_headers(self):
        """测试请求使用正确的 headers"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-api-key"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "msg_123"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_response
            mock_client.return_value = mock_instance

            request = {
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hello"}]
            }

            await adapter.forward_request(request)

            call_args = mock_instance.post.call_args
            headers = call_args.kwargs["headers"]

            assert headers["x-api-key"] == "test-api-key"
            assert headers["anthropic-version"] == "2023-06-01"

    @pytest.mark.asyncio
    async def test_forward_request_http_error(self):
        """测试 HTTP 错误"""
        adapter = AnthropicPassthroughAdapter(
            base_url="https://api.anthropic.com",
            api_key="test-key"
        )

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=MagicMock(status_code=400, text='{"error": "invalid_request"}')
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_response
            mock_client.return_value = mock_instance

            request = {"model": "claude-sonnet-4", "messages": []}

            with pytest.raises(httpx.HTTPStatusError):
                await adapter.forward_request(request)
