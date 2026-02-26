"""
计费服务

提供：
- 请求日志记录
- 费用计算
- 月度统计更新
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.request_log import RequestLog, RequestStatus
from models.monthly_usage import MonthlyUsage
from models.model_pricing import ModelPricing
from models.provider import Provider


async def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    db: AsyncSession
) -> Decimal:
    """
    计算请求费用

    Args:
        model: 模型名称
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        db: 数据库 session

    Returns:
        费用（USD）
    """
    # 查询模型定价
    result = await db.execute(
        select(ModelPricing).where(ModelPricing.model_name == model)
    )
    pricing = result.scalar_one_or_none()

    if not pricing:
        # 没有定价信息时返回 0
        return Decimal("0")

    # 计算费用
    # cost = (prompt_tokens * input_price_per_1k / 1000) + (completion_tokens * output_price_per_1k / 1000)
    input_cost = Decimal(str(prompt_tokens)) * pricing.input_price_per_1k / Decimal("1000")
    output_cost = Decimal(str(completion_tokens)) * pricing.output_price_per_1k / Decimal("1000")

    return input_cost + output_cost


async def log_request(
    user_id: uuid.UUID,
    key_id: uuid.UUID,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str = RequestStatus.SUCCESS,
    error_message: Optional[str] = None,
    provider_id: Optional[uuid.UUID] = None,
    db: AsyncSession = None
) -> RequestLog:
    """
    记录请求日志

    Args:
        user_id: 用户 ID
        key_id: 平台 Key ID
        model: 模型名称
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        latency_ms: 响应耗时（毫秒）
        status: 请求状态
        error_message: 错误信息
        provider_id: 供应商 ID
        db: 数据库 session

    Returns:
        RequestLog 对象
    """
    # 计算费用
    cost_usd = await calculate_cost(model, prompt_tokens, completion_tokens, db)

    # 创建日志记录
    request_id = f"req_{uuid.uuid4().hex[:24]}"
    log = RequestLog(
        id=uuid.uuid4(),
        request_id=request_id,
        user_id=user_id,
        key_id=key_id,
        provider_id=provider_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
    )

    db.add(log)

    # 更新月度统计（只统计成功的请求）
    if status == RequestStatus.SUCCESS:
        await update_monthly_usage(user_id, cost_usd, prompt_tokens + completion_tokens, db)

    await db.commit()
    await db.refresh(log)

    return log


async def update_monthly_usage(
    user_id: uuid.UUID,
    cost_usd: Decimal,
    tokens: int,
    db: AsyncSession
) -> MonthlyUsage:
    """
    更新月度用量统计

    Args:
        user_id: 用户 ID
        cost_usd: 本次费用
        tokens: 本次 token 数
        db: 数据库 session

    Returns:
        MonthlyUsage 对象
    """
    year_month = datetime.utcnow().strftime("%Y-%m")

    # 查找当月记录
    result = await db.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.year_month == year_month
        )
    )
    usage = result.scalar_one_or_none()

    if usage:
        # 更新现有记录
        usage.total_cost_usd = usage.total_cost_usd + cost_usd
        usage.total_tokens = usage.total_tokens + tokens
        usage.request_count = usage.request_count + 1
        usage.updated_at = datetime.utcnow()
    else:
        # 创建新记录
        usage = MonthlyUsage(
            id=uuid.uuid4(),
            user_id=user_id,
            year_month=year_month,
            total_tokens=tokens,
            total_cost_usd=cost_usd,
            request_count=1
        )
        db.add(usage)

    return usage


async def get_monthly_usage(
    user_id: uuid.UUID,
    year_month: Optional[str] = None,
    db: AsyncSession = None
) -> Optional[MonthlyUsage]:
    """
    获取月度用量

    Args:
        user_id: 用户 ID
        year_month: 年月字符串，默认当前月
        db: 数据库 session

    Returns:
        MonthlyUsage 对象或 None
    """
    if year_month is None:
        year_month = datetime.utcnow().strftime("%Y-%m")

    result = await db.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.year_month == year_month
        )
    )
    return result.scalar_one_or_none()


async def get_key_stats(
    key_id: uuid.UUID,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    获取单个 Key 的统计信息

    Args:
        key_id: Key ID
        db: 数据库 session

    Returns:
        统计信息字典
    """
    from sqlalchemy import func

    result = await db.execute(
        select(
            func.count(RequestLog.id).label("total_requests"),
            func.sum(RequestLog.total_tokens).label("total_tokens"),
            func.sum(RequestLog.cost_usd).label("total_cost_usd")
        ).where(
            RequestLog.key_id == key_id,
            RequestLog.status == RequestStatus.SUCCESS
        )
    )
    row = result.one()

    return {
        "key_id": str(key_id),
        "total_requests": row.total_requests or 0,
        "total_tokens": row.total_tokens or 0,
        "total_cost_usd": float(row.total_cost_usd or 0)
    }


async def get_user_stats(
    user_id: uuid.UUID,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    获取用户的统计信息

    Args:
        user_id: 用户 ID
        db: 数据库 session

    Returns:
        统计信息字典
    """
    year_month = datetime.utcnow().strftime("%Y-%m")

    usage = await get_monthly_usage(user_id, year_month, db)

    if usage:
        return {
            "user_id": str(user_id),
            "year_month": usage.year_month,
            "total_requests": usage.request_count,
            "total_tokens": usage.total_tokens,
            "total_cost_usd": float(usage.total_cost_usd)
        }

    return {
        "user_id": str(user_id),
        "year_month": year_month,
        "total_requests": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0
    }
