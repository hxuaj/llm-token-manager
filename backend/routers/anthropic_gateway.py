"""
Anthropic Messages API 网关路由

提供：
- POST /v1/messages: Anthropic Messages API 兼容端点
"""
import json
import time
from typing import Dict, Any
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.user_api_key import UserApiKey
from models.request_log import RequestStatus
from middleware.auth import get_user_by_api_key
from services.anthropic_proxy import (
    build_upstream_headers,
    proxy_request_non_stream,
    proxy_request_stream,
    extract_usage_from_response,
    extract_usage_from_sse_event,
    make_anthropic_error,
    resolve_provider,
    get_provider_key,
)
from services.unified_router import get_unified_router
from services.quota import (
    check_all_limits,
    QuotaExceededError,
    RateLimitedError
)
from services.billing import log_request
from services.model_status import check_model_deprecation

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Anthropic Messages API 端点
# ─────────────────────────────────────────────────────────────────────

@router.post("/messages")
async def anthropic_messages(
    request: Request,
    user_key: tuple = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Anthropic Messages API 代理端点

    兼容 Anthropic Messages API 格式，支持透传到 Anthropic、智谱 GLM、MiniMax 等
    支持 Bearer 和 x-api-key 两种鉴权方式

    Pipeline:
    1. extract_platform_key(request)        → 提取平台 Key
    2. authenticate_key(key)                → 验证 Key 有效性
    3. check_quota(user_id)                 → 检查额度
    4. check_rpm(user_id)                   → 检查 RPM
    5. parse body → extract model name
    6. resolve_provider(model)              → 路由到供应商
    7. decrypt_vendor_key(provider)
    8. build_upstream_url(provider)
    9. build_upstream_headers(...)
    10. if stream: proxy_request_stream
        else:      proxy_request_non_stream
    """
    user, api_key = user_key
    start_time = time.time()

    # 读取原始请求体（字节级别，避免二次序列化）
    body_bytes = await request.body()

    try:
        body = json.loads(body_bytes)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=make_anthropic_error(
                "invalid_request_error",
                "Invalid JSON in request body"
            )
        )

    # 提取 model 字段
    model = body.get("model")
    if not model:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=make_anthropic_error(
                "invalid_request_error",
                "Missing required field: model"
            )
        )

    # 检查所有限制（额度、RPM、模型白名单）
    try:
        await check_all_limits(user, model, db)
    except QuotaExceededError as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=make_anthropic_error(
                "rate_limit_error",
                f"Monthly quota exceeded. Used: ${e.used:.2f}, Limit: ${e.limit:.2f}. Resets at {e.resets_at}"
            )
        )
    except RateLimitedError as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=make_anthropic_error(
                "rate_limit_error",
                f"Rate limit exceeded. Current: {e.rpm} RPM, Limit: {e.limit} RPM"
            )
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=make_anthropic_error(
                "permission_error",
                str(e)
            )
        )

    # 使用统一路由服务解析模型
    router = get_unified_router()

    # 解析模型和供应商
    try:
        provider_name, model_id = router.parse_model_string(model)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_anthropic_error(
                "not_found_error",
                str(e)
            )
        )

    # 检查供应商是否支持 Anthropic 端点
    if not router.supports_endpoint(provider_name, "anthropic"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=make_anthropic_error(
                "invalid_request_error",
                f"Provider '{provider_name}' does not support Anthropic format"
            )
        )

    # 获取供应商（使用 resolve_provider 保持向后兼容）
    try:
        provider = await resolve_provider(model, db)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_anthropic_error(
                "not_found_error",
                str(e)
            )
        )

    # 获取供应商 Key
    try:
        _, decrypted_key = await get_provider_key(provider, db)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=make_anthropic_error(
                "api_error",
                str(e)
            )
        )

    # 构造上游 URL
    upstream_url = f"{provider.base_url.rstrip('/')}/v1/messages"

    # 构造上游请求头
    headers = dict(request.headers)
    upstream_headers = build_upstream_headers(headers, decrypted_key)

    # 判断是否流式请求
    is_stream = body.get("stream", False)

    # 检查模型是否废弃
    is_deprecated = await check_model_deprecation(model, db)

    try:
        if is_stream:
            # 流式响应
            stream_headers = {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
            if is_deprecated:
                stream_headers["X-Model-Deprecated"] = "true"

            return StreamingResponse(
                stream_response_generator(
                    upstream_url, upstream_headers, body_bytes,
                    user, api_key, model, db, start_time
                ),
                media_type="text/event-stream",
                headers=stream_headers
            )
        else:
            # 非流式响应
            response, response_body = await proxy_request_non_stream(
                upstream_url, upstream_headers, body_bytes
            )

            # 提取 token 使用量
            input_tokens, output_tokens = extract_usage_from_response(response_body)

            # 计算延迟
            latency_ms = int((time.time() - start_time) * 1000)

            # 记录请求日志
            await log_request(
                user_id=user.id,
                key_id=api_key.id,
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                latency_ms=latency_ms,
                status=RequestStatus.SUCCESS,
                db=db
            )

            # 构建响应头
            response_headers = {}
            if is_deprecated:
                response_headers["X-Model-Deprecated"] = "true"

            return JSONResponse(
                status_code=response.status_code,
                content=response_body,
                headers=response_headers if response_headers else None
            )

    except Exception as e:
        # 记录失败请求
        latency_ms = int((time.time() - start_time) * 1000)
        await log_request(
            user_id=user.id,
            key_id=api_key.id,
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            status=RequestStatus.ERROR,
            error_message=str(e)[:500],
            db=db
        )

        # 判断错误类型
        error_str = str(e).lower()
        if "timeout" in error_str:
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content=make_anthropic_error(
                    "api_error",
                    "Upstream provider timeout"
                )
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content=make_anthropic_error(
                    "api_error",
                    f"Provider error: {str(e)[:100]}"
                )
            )


async def stream_response_generator(
    upstream_url: str,
    headers: Dict[str, str],
    body: bytes,
    user: User,
    api_key: UserApiKey,
    model: str,
    db: AsyncSession,
    start_time: float
):
    """
    流式响应生成器

    Args:
        upstream_url: 上游 URL
        headers: 请求头
        body: 请求体
        user: 用户对象
        api_key: API Key 对象
        model: 模型名称
        db: 数据库 session
        start_time: 请求开始时间

    Yields:
        SSE 格式的数据块
    """
    total_input_tokens = 0
    total_output_tokens = 0
    error_occurred = False
    error_message = None

    try:
        async for chunk in proxy_request_stream(upstream_url, headers, body):
            yield chunk

            # 尝试从 chunk 中解析 usage 信息
            try:
                if isinstance(chunk, bytes):
                    chunk_str = chunk.decode('utf-8')
                    # SSE 格式: "event: xxx\ndata: {...}\n\n"
                    for line in chunk_str.split('\n'):
                        if line.startswith('data: '):
                            event_data = line[6:]
                            if event_data and event_data != '[DONE]':
                                input_tokens, output_tokens = extract_usage_from_sse_event(event_data)
                                total_input_tokens += input_tokens
                                total_output_tokens += output_tokens
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    except Exception as e:
        error_occurred = True
        error_message = str(e)
        # 发送错误事件
        error_event = {
            "type": "error",
            "error": {
                "type": "api_error",
                "message": str(e)
            }
        }
        yield f"event: error\ndata: {json.dumps(error_event)}\n\n".encode()

    finally:
        # 计算延迟并记录日志
        latency_ms = int((time.time() - start_time) * 1000)

        await log_request(
            user_id=user.id,
            key_id=api_key.id,
            model=model,
            prompt_tokens=total_input_tokens,
            completion_tokens=total_output_tokens,
            latency_ms=latency_ms,
            status=RequestStatus.ERROR if error_occurred else RequestStatus.SUCCESS,
            error_message=error_message,
            db=db
        )
