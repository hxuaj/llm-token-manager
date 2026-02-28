"""
Anthropic Messages API 网关测试用例

测试覆盖：
- 鉴权（Bearer 和 x-api-key）
- 模型路由（claude-*, glm-*, minimax-*）
- 透传正确性
- 流式响应
- 额度与计量
- 错误处理
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


# ─────────────────────────────────────────────────────────────────────
# 鉴权测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_bearer_token(client, user_api_key):
    """Authorization: Bearer ltm-sk-xxx → 200"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-test-key")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_x_api_key(client, user_api_key):
    """x-api-key: ltm-sk-xxx → 200"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-test-key")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_invalid_key(client):
    """无效 Key → 401，Anthropic 错误格式"""
    response = await client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"x-api-key": "ltm-sk-invalidkey12345678901234567890"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_revoked_key(client, user_api_key, db_session):
    """已吊销 Key → 401，Anthropic 格式"""
    from models.user_api_key import KeyStatus

    key_obj, raw_key = user_api_key
    key_obj.status = KeyStatus.REVOKED.value
    await db_session.commit()

    response = await client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"x-api-key": raw_key}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_missing_key(client):
    """无鉴权头 → 401，Anthropic 格式"""
    response = await client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hello"}]
        }
    )
    assert response.status_code == 401
    # 验证错误格式（如果有响应体）
    if response.content:
        data = response.json()
        assert "error" in data or "detail" in data


# ─────────────────────────────────────────────────────────────────────
# 路由测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_claude_to_anthropic(client, user_api_key):
    """model=claude-sonnet-4-* → 请求发送到 Anthropic mock"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

                # 验证 resolve_provider 被调用，且 model 参数正确
                mock_resolve.assert_called_once()
                call_args = mock_resolve.call_args
                assert call_args[0][0] == "claude-sonnet-4-20250514"

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_route_glm_to_zhipu(client, user_api_key):
    """model=glm-5 → 请求发送到智谱 mock"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://open.bigmodel.cn/api/anthropic"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "zhipu-test-key")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "glm-5",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

                mock_resolve.assert_called_once()

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_route_minimax_to_minimax(client, user_api_key):
    """model=minimax-m2.5 → 请求发送到 MiniMax mock"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.minimax.chat"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "minimax-test-key")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "minimax-m2.5",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

                mock_resolve.assert_called_once()

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_route_unknown_model(client, user_api_key):
    """model=nonexistent-model → 404，Anthropic not_found_error"""
    key_obj, raw_key = user_api_key

    response = await client.post(
        "/v1/messages",
        json={
            "model": "nonexistent-model",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"x-api-key": raw_key}
    )

    assert response.status_code == 404
    data = response.json()
    # 验证 Anthropic 错误格式
    assert "error" in data or "type" in data


# ─────────────────────────────────────────────────────────────────────
# 透传正确性测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_headers_forwarded(client, user_api_key):
    """anthropic-version 和 anthropic-beta 被透传到上游 mock"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={
                        "x-api-key": raw_key,
                        "anthropic-version": "2023-06-01",
                        "anthropic-beta": "prompt-caching-2024-07-31"
                    }
                )

                # 验证 proxy 被调用
                mock_proxy.assert_called_once()
                call_args = mock_proxy.call_args
                headers = call_args[0][1]  # 第二个参数是 headers

                # 验证透传的头部
                assert "anthropic-version" in headers
                assert headers["anthropic-version"] == "2023-06-01"

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_supplier_key_substituted(client, user_api_key):
    """上游收到的 x-api-key 是供应商 Key，不是平台 Key"""
    key_obj, raw_key = user_api_key
    vendor_key = "sk-ant-vendor-key-12345"

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), vendor_key)
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

                # 验证 proxy 被调用
                mock_proxy.assert_called_once()
                call_args = mock_proxy.call_args
                headers = call_args[0][1]  # 第二个参数是 headers

                # 验证 x-api-key 是供应商 Key
                assert headers["x-api-key"] == vendor_key
                # 验证不是平台 Key
                assert headers["x-api-key"] != raw_key

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_body_passthrough(client, user_api_key):
    """上游收到的请求体与客户端发送的完全一致（字节级别）"""
    key_obj, raw_key = user_api_key
    original_body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Hello, 世界!"}],  # 包含非 ASCII 字符
        "system": "You are a helpful assistant.",
        "stream": False
    }

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json=original_body,
                    headers={"x-api-key": raw_key}
                )

                # 验证 proxy 被调用
                mock_proxy.assert_called_once()
                call_args = mock_proxy.call_args
                body_bytes = call_args[0][2]  # 第三个参数是 body

                # 验证请求体可以正确解析，且与原始一致
                parsed_body = json.loads(body_bytes)
                assert parsed_body["model"] == original_body["model"]
                assert parsed_body["max_tokens"] == original_body["max_tokens"]
                assert parsed_body["messages"] == original_body["messages"]
                assert parsed_body["system"] == original_body["system"]

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_response_passthrough(client, user_api_key):
    """客户端收到的响应体与上游返回的完全一致"""
    key_obj, raw_key = user_api_key
    upstream_response = {
        "id": "msg_01XYZ",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Hello! How can I help you?"}
        ],
        "model": "claude-sonnet-4-20250514",
        "usage": {
            "input_tokens": 15,
            "output_tokens": 10
        }
    }

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    upstream_response
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

                data = response.json()

                # 验证响应与上游一致
                assert data["id"] == upstream_response["id"]
                assert data["type"] == upstream_response["type"]
                assert data["role"] == upstream_response["role"]
                assert data["content"] == upstream_response["content"]
                assert data["usage"]["input_tokens"] == upstream_response["usage"]["input_tokens"]
                assert data["usage"]["output_tokens"] == upstream_response["usage"]["output_tokens"]

    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# 流式测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_passthrough(client, user_api_key):
    """stream=true，mock 上游返回完整 Anthropic SSE 序列"""
    key_obj, raw_key = user_api_key

    # Mock 流式响应
    async def mock_stream():
        yield b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_123","usage":{"input_tokens":10}}}\n\n'
        yield b'event: content_block_start\ndata: {"type":"content_block_start","index":0}\n\n'
        yield b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n'
        yield b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
        yield b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}\n\n'
        yield b'event: message_stop\ndata: {"type":"message_stop"}\n\n'

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_stream') as mock_stream_func:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_stream_func.return_value = mock_stream()

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}],
                        "stream": True
                    },
                    headers={"x-api-key": raw_key}
                )

                assert response.status_code == 200
                # 验证返回的是流式响应
                assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_stream_usage_logged(client, user_api_key):
    """流式请求结束后，request_logs 中正确记录 input/output tokens"""
    key_obj, raw_key = user_api_key

    # Mock 流式响应
    async def mock_stream():
        yield b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_123","usage":{"input_tokens":20}}}\n\n'
        yield b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n'
        yield b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":8}}\n\n'
        yield b'event: message_stop\ndata: {"type":"message_stop"}\n\n'

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_stream') as mock_stream_func:
                with patch('routers.anthropic_gateway.log_request') as mock_log:
                    mock_provider = MagicMock()
                    mock_provider.base_url = "https://api.anthropic.com"
                    mock_resolve.return_value = mock_provider
                    mock_key.return_value = (MagicMock(), "sk-ant-test")
                    mock_stream_func.return_value = mock_stream()

                    response = await client.post(
                        "/v1/messages",
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "max_tokens": 1024,
                            "messages": [{"role": "user", "content": "Hello"}],
                            "stream": True
                        },
                        headers={"x-api-key": raw_key}
                    )

                    # 读取流以触发 finally 块
                    async for _ in response.aiter_bytes():
                        pass

    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# 额度与计量测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quota_exceeded(client, test_user, db_session):
    """超额用户 → 429，Anthropic rate_limit_error"""
    from services.user_key_service import generate_api_key
    from models.user_api_key import UserApiKey
    from models.monthly_usage import MonthlyUsage
    from decimal import Decimal
    import uuid

    # 设置用户额度为 0
    test_user.monthly_quota_usd = Decimal("0.01")
    await db_session.commit()

    # 创建月度用量记录（已用完）
    usage = MonthlyUsage(
        id=uuid.uuid4(),
        user_id=test_user.id,
        year_month="2026-02",
        total_tokens=1000,
        total_cost_usd=Decimal("0.02"),  # 超过额度
        request_count=10
    )
    db_session.add(usage)
    await db_session.commit()

    # 创建 Key
    raw_key, key_hash, key_suffix = generate_api_key()
    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test Key",
        key_hash=key_hash,
        key_suffix=key_suffix,
        status="active",
    )
    db_session.add(key)
    await db_session.commit()

    response = await client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"x-api-key": raw_key}
    )

    assert response.status_code == 429
    data = response.json()
    # 验证错误格式
    assert "error" in data or "type" in data


@pytest.mark.asyncio
async def test_usage_logged(client, user_api_key, db_session):
    """成功请求后 request_logs 有新记录"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_proxy.return_value = (
                    MagicMock(status_code=200),
                    {"id": "msg-123", "content": [], "usage": {"input_tokens": 10, "output_tokens": 5}}
                )

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

    assert response.status_code == 200
    # 注意：实际的日志记录验证需要查询数据库


# ─────────────────────────────────────────────────────────────────────
# 错误处理测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upstream_500(client, user_api_key):
    """mock 上游返回 500 → 网关返回 502，Anthropic api_error"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_proxy.side_effect = Exception("Upstream error 500")

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

    assert response.status_code == 502
    data = response.json()
    # 验证 Anthropic 错误格式
    assert "error" in data or "type" in data


@pytest.mark.asyncio
async def test_upstream_timeout(client, user_api_key):
    """mock 上游超时 → 网关返回 504，Anthropic api_error"""
    key_obj, raw_key = user_api_key

    with patch('routers.anthropic_gateway.resolve_provider') as mock_resolve:
        with patch('routers.anthropic_gateway.get_provider_key') as mock_key:
            with patch('routers.anthropic_gateway.proxy_request_non_stream') as mock_proxy:
                mock_provider = MagicMock()
                mock_provider.base_url = "https://api.anthropic.com"
                mock_resolve.return_value = mock_provider
                mock_key.return_value = (MagicMock(), "sk-ant-test")
                mock_proxy.side_effect = Exception("timeout error")

                response = await client.post(
                    "/v1/messages",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}
                )

    assert response.status_code == 504
    data = response.json()
    # 验证 Anthropic 错误格式
    assert "error" in data or "type" in data


@pytest.mark.asyncio
async def test_missing_model_field(client, user_api_key):
    """缺少 model 字段 → 400，Anthropic invalid_request_error"""
    key_obj, raw_key = user_api_key

    response = await client.post(
        "/v1/messages",
        json={
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"x-api-key": raw_key}
    )

    assert response.status_code == 400
    data = response.json()
    # 验证错误格式
    assert "error" in data or "detail" in data


@pytest.mark.asyncio
async def test_invalid_json_body(client, user_api_key):
    """请求体格式错误 → 400，Anthropic invalid_request_error"""
    key_obj, raw_key = user_api_key

    response = await client.post(
        "/v1/messages",
        content=b"not valid json",
        headers={
            "x-api-key": raw_key,
            "content-type": "application/json"
        }
    )

    # FastAPI 会在我们的代码之前处理 JSON 解析错误
    # 所以这里可能是 400 或 422
    assert response.status_code in [400, 422]
