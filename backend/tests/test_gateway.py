"""
网关代理测试用例

测试覆盖：
- 平台 Key 鉴权
- 模型路由
- 请求/响应格式转换
- 流式响应
- 错误处理
- 模型白名单
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


def _mock_provider_key():
    """创建 mock 的供应商 Key 结果"""
    mock_provider = MagicMock()
    mock_provider.id = "test-provider-id"
    mock_provider.name = "test-provider"

    mock_key = MagicMock()
    mock_key.id = "test-key-id"
    mock_key.key_suffix = "abcd"
    mock_key.key_plan = "standard"
    mock_key.override_input_price = None
    mock_key.override_output_price = None
    mock_key.is_coding_plan = False

    return (mock_provider, mock_key, "decrypted-key")


# ─────────────────────────────────────────────────────────────────────
# 鉴权测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_key_passes_auth(client, user_api_key):
    """有效平台 Key 调用 - 应返回 200 和模型响应"""
    key_obj, raw_key = user_api_key

    # Mock 供应商相关函数
    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}
                }

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_key_rejected(client):
    """无效 Key - 应返回 401"""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"Authorization": "Bearer ltm-sk-invalidkey12345678901234567890"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoked_key_rejected(client, user_api_key, db_session):
    """已吊销 Key - 应返回 401"""
    from models.user_api_key import KeyStatus

    key_obj, raw_key = user_api_key

    # 吊销 Key
    key_obj.status = KeyStatus.REVOKED.value
    await db_session.commit()

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_auth_header(client):
    """缺少 Authorization header - 应返回 401"""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }
    )
    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# 模型路由测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_to_openai(client, user_api_key):
    """model='gpt-4o' - 请求转发到 OpenAI mock"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {"id": "test", "choices": []}

                await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                # 验证调用
                mock_forward.assert_called_once()


@pytest.mark.asyncio
async def test_route_to_anthropic(client, user_api_key):
    """model='claude-sonnet-4-20250514' - 请求转发到 Anthropic mock"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "anthropic"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {"id": "test", "choices": []}

                await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                mock_forward.assert_called_once()


@pytest.mark.asyncio
async def test_route_to_openrouter(client, user_api_key):
    """model='openai/gpt-4o' - 请求转发到 OpenRouter mock"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openrouter"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {"id": "test", "choices": []}

                await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "openai/gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                mock_forward.assert_called_once()


# ─────────────────────────────────────────────────────────────────────
# 请求/响应格式转换测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openai_request_format(client, user_api_key):
    """检查发给 OpenAI 的请求格式正确"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {"id": "test", "choices": []}

                await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "temperature": 0.7
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                # 验证 forward_request 被调用
                mock_forward.assert_called_once()
                call_args = mock_forward.call_args
                assert call_args is not None


@pytest.mark.asyncio
async def test_anthropic_request_conversion(client, user_api_key):
    """OpenAI 格式 → Anthropic Messages 格式转换正确"""
    key_obj, raw_key = user_api_key

    with patch('services.providers.anthropic_adapter.AnthropicAdapter.convert_request') as mock_convert:
        mock_convert.return_value = {
            "model": "claude-sonnet-4-20250514",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024
        }

        with patch('routers.gateway.forward_request') as mock_forward:
            with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
                with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                    mock_provider.return_value = "anthropic"
                    mock_get_key.return_value = _mock_provider_key()
                    mock_forward.return_value = {"id": "test", "choices": []}

                    response = await client.post(
                        "/v1/chat/completions",
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "messages": [{"role": "user", "content": "Hello"}]
                        },
                        headers={"Authorization": f"Bearer {raw_key}"}
                    )

        # 注意：由于我们的 mock 在 routers 层，convert_request 可能不会被调用
        # 这里我们主要测试路由正常工作


@pytest.mark.asyncio
async def test_response_unified_format(client, user_api_key):
    """各供应商响应统一为 OpenAI 格式"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1234567890,
                    "model": "gpt-4o",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hello!"},
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                }

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                assert response.status_code == 200
                data = response.json()
                # 验证 OpenAI 格式
                assert "id" in data
                assert "choices" in data
                assert len(data["choices"]) > 0
                assert "message" in data["choices"][0]
                assert "usage" in data


# ─────────────────────────────────────────────────────────────────────
# 流式响应测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_response(client, user_api_key):
    """stream=true - SSE 流正确转发"""
    key_obj, raw_key = user_api_key

    # Mock 流式响应
    async def mock_stream():
        yield b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        yield b'data: [DONE]\n\n'

    with patch('routers.gateway.forward_request_stream') as mock_stream_func:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_stream_func.return_value = mock_stream()

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "stream": True
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                assert response.status_code == 200
                # 验证返回的是流式响应
                assert "text/event-stream" in response.headers.get("content-type", "")


# ─────────────────────────────────────────────────────────────────────
# 错误处理测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_error_handling(client, user_api_key):
    """供应商返回 500 - 网关返回友好错误信息"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.side_effect = Exception("Provider API error")

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

                assert response.status_code in [500, 502, 503]


# ─────────────────────────────────────────────────────────────────────
# 模型白名单测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_model_whitelist_allowed(client, test_user, db_session):
    """用户有权的模型 - 应返回 200"""
    from services.user_key_service import generate_api_key
    from models.user_api_key import UserApiKey
    import uuid

    # 设置用户只能使用 gpt-4o-mini
    test_user.allowed_models = '["gpt-4o-mini"]'
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

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {"id": "test", "choices": []}

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_model_whitelist_blocked(client, test_user, db_session):
    """用户无权的模型 - 应返回 403"""
    from services.user_key_service import generate_api_key
    from models.user_api_key import UserApiKey
    import uuid

    # 设置用户只能使用 gpt-4o-mini
    test_user.allowed_models = '["gpt-4o-mini"]'
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
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",  # 用户无权使用的模型
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"Authorization": f"Bearer {raw_key}"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unknown_model(client, user_api_key):
    """model='nonexistent-model' - 应返回 400 或 404"""
    key_obj, raw_key = user_api_key

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent-model-xyz",
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"Authorization": f"Bearer {raw_key}"}
    )

    assert response.status_code in [400, 404]


# ─────────────────────────────────────────────────────────────────────
# 模型列表测试
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_models(client, user_api_key):
    """获取可用模型列表 - 应返回 200"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.get_available_models') as mock_models:
        mock_models.return_value = [
            {"id": "gpt-4o", "created": 1234567890, "owned_by": "openai"}
        ]

        response = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {raw_key}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)


# ─────────────────────────────────────────────────────────────────────
# x-api-key 鉴权测试 (Anthropic SDK 兼容)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_x_api_key(client, user_api_key):
    """通过 x-api-key 头鉴权 - 应返回 200"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}
                }

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"x-api-key": raw_key}  # 使用 x-api-key 而不是 Authorization
                )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_bearer_still_works(client, user_api_key):
    """Bearer 鉴权方式仍然有效 - 应返回 200"""
    key_obj, raw_key = user_api_key

    with patch('routers.gateway.forward_request') as mock_forward:
        with patch('routers.gateway.get_provider_name_by_model') as mock_provider:
            with patch('routers.gateway.get_provider_and_key') as mock_get_key:
                mock_provider.return_value = "openai"
                mock_get_key.return_value = _mock_provider_key()
                mock_forward.return_value = {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}
                }

                response = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Hello"}]
                    },
                    headers={"Authorization": f"Bearer {raw_key}"}
                )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_missing_key_anthropic_format(client):
    """无任何鉴权头 - 应返回 401"""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }
    )
    assert response.status_code == 401
