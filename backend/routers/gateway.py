"""
网关代理路由

提供：
- POST /v1/chat/completions: 核心代理接口
- GET /v1/models: 可用模型列表
"""
import json
import time
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.user import User
from models.user_api_key import UserApiKey
from models.request_log import RequestStatus
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from middleware.auth import get_user_by_api_key
from services.proxy import (
    forward_request,
    forward_request_stream,
    get_provider_name_by_model,
    get_available_models,
    get_provider_and_key,
    calculate_request_cost
)
from services.quota import (
    check_all_limits,
    QuotaExceededError,
    RateLimitedError,
    get_monthly_usage
)
from services.billing import log_request
from services.key_selector import select_provider_key, NoAvailableKeyError

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型（请求/响应）
# ─────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """Chat Completions 请求"""
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    user: Optional[str] = None

    class Config:
        extra = "allow"  # 允许额外字段


class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelListResponse(BaseModel):
    """模型列表响应"""
    object: str = "list"
    data: List[ModelInfo]


class QuotaExceededResponse(BaseModel):
    """额度超限响应"""
    error: Dict[str, Any]


# ─────────────────────────────────────────────────────────────────────
# 核心代理接口
# ─────────────────────────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    user_key: tuple = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Chat Completions 代理接口

    兼容 OpenAI Chat Completions API 格式

    认证：使用平台 Key（Bearer Token）

    响应中新增 x_ltm 字段，包含费用和额度信息
    """
    user, api_key = user_key
    start_time = time.time()

    # 检查模型是否可用
    provider_name = get_provider_name_by_model(request.model)
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown model: {request.model}"
        )

    # 检查所有限制（额度、RPM、模型白名单）
    try:
        await check_all_limits(user, request.model, db)
    except QuotaExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "type": "quota_exceeded",
                "message": "Your monthly quota has been exceeded. Please contact admin.",
                "quota_used": float(e.used),
                "quota_limit": float(e.limit),
                "resets_at": e.resets_at
            }
        )
    except RateLimitedError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "type": "rate_limited",
                "message": f"Rate limit exceeded. Current: {e.rpm}, Limit: {e.limit} RPM"
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

    # 构建请求字典
    request_dict = request.model_dump(exclude_none=True)

    try:
        # 获取供应商和 Key（用于费用计算）
        result = await get_provider_and_key(provider_name, request.model, db)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"No available API key for provider '{provider_name}'"
            )
        provider, provider_api_key, _ = result

        if request.stream:
            # 流式响应
            return StreamingResponse(
                stream_response_generator(
                    request.model, request_dict, user, api_key, provider, provider_api_key, db, start_time
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # 非流式响应
            response = await forward_request(request.model, request_dict, db)

            # 计算延迟
            latency_ms = int((time.time() - start_time) * 1000)

            # 提取 token 使用量
            usage = response.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)

            # 计算费用
            cost_usd = await calculate_request_cost(
                input_tokens, output_tokens, request.model, provider_api_key, db
            )

            # 记录请求日志（包含新的字段）
            await log_request(
                user_id=user.id,
                key_id=api_key.id,
                model=request.model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                latency_ms=latency_ms,
                status=RequestStatus.SUCCESS,
                cost_usd=cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                key_plan=provider_api_key.key_plan,
                db=db
            )

            # 计算剩余额度
            from services.quota import get_monthly_usage
            monthly_used = await get_monthly_usage(user.id, db)
            remaining_quota = float(user.monthly_quota_usd) - float(monthly_used)

            # 添加 x_ltm 字段到响应
            response["x_ltm"] = {
                "cost_usd": float(cost_usd),
                "remaining_quota_usd": round(remaining_quota, 4),
                "key_id_suffix": f"...{provider_api_key.key_suffix}"
            }

            return response

    except ValueError as e:
        # 记录失败请求
        latency_ms = int((time.time() - start_time) * 1000)
        await log_request(
            user_id=user.id,
            key_id=api_key.id,
            model=request.model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            status=RequestStatus.ERROR,
            error_message=str(e),
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except NoAvailableKeyError as e:
        # 没有可用的 Key
        latency_ms = int((time.time() - start_time) * 1000)
        await log_request(
            user_id=user.id,
            key_id=api_key.id,
            model=request.model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            status=RequestStatus.ERROR,
            error_message=str(e),
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        # 记录失败请求
        latency_ms = int((time.time() - start_time) * 1000)
        await log_request(
            user_id=user.id,
            key_id=api_key.id,
            model=request.model,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=latency_ms,
            status=RequestStatus.ERROR,
            error_message=str(e)[:500],
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider error: {str(e)[:100]}"
        )


async def stream_response_generator(
    model: str,
    request: Dict[str, Any],
    user: User,
    api_key: UserApiKey,
    provider: Provider,
    provider_api_key: ProviderApiKey,
    db: AsyncSession,
    start_time: float
):
    """
    流式响应生成器

    Args:
        model: 模型名称
        request: 请求字典
        user: 用户对象
        api_key: 用户 API Key 对象
        provider: 供应商对象
        provider_api_key: 供应商 API Key 对象
        db: 数据库 session
        start_time: 请求开始时间

    Yields:
        SSE 格式的数据块
    """
    total_prompt_tokens = 0
    total_completion_tokens = 0
    error_occurred = False
    error_message = None

    try:
        async for chunk in forward_request_stream(model, request, db):
            yield chunk

            # 尝试从 chunk 中解析 usage 信息
            try:
                if isinstance(chunk, bytes):
                    chunk_str = chunk.decode('utf-8')
                    if chunk_str.startswith('data: ') and not chunk_str.startswith('data: [DONE]'):
                        data = json.loads(chunk_str[6:])
                        usage = data.get('usage', {})
                        if usage:
                            total_prompt_tokens = usage.get('prompt_tokens', 0)
                            total_completion_tokens = usage.get('completion_tokens', 0)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    except Exception as e:
        error_occurred = True
        error_message = str(e)
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "proxy_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    finally:
        # 计算延迟并记录日志
        latency_ms = int((time.time() - start_time) * 1000)

        # 计算费用
        cost_usd = Decimal("0")
        if not error_occurred:
            cost_usd = await calculate_request_cost(
                total_prompt_tokens, total_completion_tokens, model, provider_api_key, db
            )

        await log_request(
            user_id=user.id,
            key_id=api_key.id,
            model=model,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            latency_ms=latency_ms,
            status=RequestStatus.ERROR if error_occurred else RequestStatus.SUCCESS,
            error_message=error_message,
            cost_usd=cost_usd,
            input_tokens=total_prompt_tokens,
            output_tokens=total_completion_tokens,
            key_plan=provider_api_key.key_plan,
            db=db
        )


# ─────────────────────────────────────────────────────────────────────
# 模型列表接口
# ─────────────────────────────────────────────────────────────────────

@router.get("/models", response_model=ModelListResponse)
async def list_models(
    user_key: tuple = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取可用模型列表

    返回 model_catalog 中 status='active' 的模型。
    如果用户有 allowed_models 限制，则进一步过滤。

    认证：使用平台 Key（Bearer Token）
    """
    user, api_key = user_key

    models = await get_available_models(db)

    # 如果用户有 allowed_models 限制，进行过滤
    if user.allowed_models:
        try:
            allowed_list = json.loads(user.allowed_models)
            if isinstance(allowed_list, list) and len(allowed_list) > 0:
                models = [m for m in models if m["id"] in allowed_list]
        except (json.JSONDecodeError, TypeError):
            pass  # 解析失败时不限制

    return ModelListResponse(
        data=[
            ModelInfo(
                id=m["id"],
                created=m["created"],
                owned_by=m["owned_by"]
            )
            for m in models
        ]
    )


@router.get("/models/{model_id}")
async def get_model(
    model_id: str,
    user_key: tuple = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定模型信息

    认证：使用平台 Key（Bearer Token）
    """
    user, api_key = user_key

    models = await get_available_models(db)
    model = next((m for m in models if m["id"] == model_id), None)

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model not found: {model_id}"
        )

    # 如果用户有 allowed_models 限制，检查权限
    if user.allowed_models:
        try:
            allowed_list = json.loads(user.allowed_models)
            if isinstance(allowed_list, list) and len(allowed_list) > 0:
                if model_id not in allowed_list:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Access denied to model: {model_id}"
                    )
        except (json.JSONDecodeError, TypeError):
            pass  # 解析失败时不限制

    return ModelInfo(
        id=model["id"],
        created=model["created"],
        owned_by=model["owned_by"]
    )
