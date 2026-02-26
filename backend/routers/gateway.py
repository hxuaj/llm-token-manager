"""
网关代理路由

提供：
- POST /v1/chat/completions: 核心代理接口
- GET /v1/models: 可用模型列表
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from models.user_api_key import UserApiKey
from middleware.auth import get_user_by_api_key
from services.proxy import (
    forward_request,
    forward_request_stream,
    check_model_access,
    get_available_models,
    get_provider_name_by_model
)
from services.user_key_service import hash_key

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
    """
    user, api_key = user_key

    # 检查模型是否可用
    provider_name = get_provider_name_by_model(request.model)
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown model: {request.model}"
        )

    # 检查模型白名单
    if not await check_model_access(request.model, user.allowed_models):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have access to model: {request.model}"
        )

    # 构建请求字典
    request_dict = request.model_dump(exclude_none=True)

    try:
        if request.stream:
            # 流式响应
            return StreamingResponse(
                stream_response_generator(request.model, request_dict, db),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # 非流式响应
            response = await forward_request(request.model, request_dict, db)
            return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # 记录错误但不暴露内部细节
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider error: {str(e)[:100]}"
        )


async def stream_response_generator(
    model: str,
    request: Dict[str, Any],
    db: AsyncSession
):
    """
    流式响应生成器

    Args:
        model: 模型名称
        request: 请求字典
        db: 数据库 session

    Yields:
        SSE 格式的数据块
    """
    try:
        async for chunk in forward_request_stream(model, request, db):
            yield chunk
    except Exception as e:
        # 流式响应中的错误处理
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "proxy_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n".encode()
        yield b"data: [DONE]\n\n"


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

    返回所有配置了定价的可用模型

    认证：使用平台 Key（Bearer Token）
    """
    user, api_key = user_key

    models = await get_available_models(db)

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

    return ModelInfo(
        id=model["id"],
        created=model["created"],
        owned_by=model["owned_by"]
    )
