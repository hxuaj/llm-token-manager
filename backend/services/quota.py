"""
额度与限流服务

提供：
- 额度检查
- RPM 限流检查
- 模型白名单检查
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from models.user import User
from models.request_log import RequestLog, RequestStatus
from models.monthly_usage import MonthlyUsage


class QuotaExceededError(Exception):
    """额度超限异常"""
    def __init__(self, used: Decimal, limit: Decimal, resets_at: str):
        self.used = used
        self.limit = limit
        self.resets_at = resets_at
        super().__init__(f"Quota exceeded: ${used}/${limit}")


class RateLimitedError(Exception):
    """请求频率超限异常"""
    def __init__(self, rpm: int, limit: int):
        self.rpm = rpm
        self.limit = limit
        super().__init__(f"Rate limited: {rpm}/{limit} RPM")


async def get_monthly_usage_for_quota(
    user_id: uuid.UUID,
    db: AsyncSession
) -> Tuple[Decimal, int, int]:
    """
    获取用户当月用量

    Args:
        user_id: 用户 ID
        db: 数据库 session

    Returns:
        (total_cost_usd, total_tokens, request_count)
    """
    year_month = datetime.utcnow().strftime("%Y-%m")

    result = await db.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.year_month == year_month
        )
    )
    usage = result.scalar_one_or_none()

    if usage:
        return usage.total_cost_usd, usage.total_tokens, usage.request_count

    return Decimal("0"), 0, 0


async def get_monthly_usage(
    user_id: uuid.UUID,
    db: AsyncSession
) -> Decimal:
    """
    获取用户当月已用费用

    Args:
        user_id: 用户 ID
        db: 数据库 session

    Returns:
        已用费用（USD）
    """
    cost, _, _ = await get_monthly_usage_for_quota(user_id, db)
    return cost


async def check_quota(
    user: User,
    db: AsyncSession
) -> Tuple[bool, Decimal, Decimal]:
    """
    检查用户额度是否足够

    Args:
        user: 用户对象
        db: 数据库 session

    Returns:
        (是否足够, 已使用额度, 额度上限)

    Raises:
        QuotaExceededError: 额度已用尽
    """
    # 获取当月用量
    used_cost, _, _ = await get_monthly_usage_for_quota(user.id, db)

    # 获取额度上限
    limit = Decimal(str(user.monthly_quota_usd))

    if used_cost >= limit:
        # 计算下月重置时间
        now = datetime.utcnow()
        if now.month == 12:
            resets_at = datetime(now.year + 1, 1, 1, 0, 0, 0)
        else:
            resets_at = datetime(now.year, now.month + 1, 1, 0, 0, 0)

        raise QuotaExceededError(
            used=used_cost,
            limit=limit,
            resets_at=resets_at.isoformat() + "Z"
        )

    return True, used_cost, limit


async def check_rpm(
    user: User,
    db: AsyncSession
) -> Tuple[bool, int, int]:
    """
    检查用户 RPM 是否超限

    Args:
        user: 用户对象
        db: 数据库 session

    Returns:
        (是否在限制内, 当前 RPM, RPM 限制)

    Raises:
        RateLimitedError: RPM 超限
    """
    rpm_limit = user.rpm_limit

    if rpm_limit <= 0:
        # 0 表示不限制
        return True, 0, rpm_limit

    # 查询最近 1 分钟内的请求数
    from datetime import timedelta

    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)

    result = await db.execute(
        select(func.count(RequestLog.id)).where(
            RequestLog.user_id == user.id,
            RequestLog.created_at >= one_minute_ago
        )
    )
    current_rpm = result.scalar() or 0

    if current_rpm >= rpm_limit:
        raise RateLimitedError(rpm=current_rpm, limit=rpm_limit)

    return True, current_rpm, rpm_limit


async def check_model_access(
    model: str,
    user: User
) -> bool:
    """
    检查用户是否有权访问该模型

    Args:
        model: 模型名称
        user: 用户对象

    Returns:
        是否有权访问
    """
    import json

    allowed_models = user.allowed_models

    if allowed_models is None:
        # None 表示不限制
        return True

    try:
        models_list = json.loads(allowed_models)
        return model in models_list
    except (json.JSONDecodeError, TypeError):
        # 解析失败时不限制
        return True


async def check_all_limits(
    user: User,
    model: str,
    db: AsyncSession
) -> Tuple[bool, dict]:
    """
    检查所有限制

    Args:
        user: 用户对象
        model: 请求的模型
        db: 数据库 session

    Returns:
        (是否通过, 限制状态字典)

    Raises:
        QuotaExceededError: 额度超限
        RateLimitedError: RPM 超限
        ValueError: 模型无权访问
    """
    # 检查模型白名单
    if not await check_model_access(model, user):
        raise ValueError(f"You don't have access to model: {model}")

    # 检查 RPM
    rpm_ok, current_rpm, rpm_limit = await check_rpm(user, db)

    # 检查额度
    quota_ok, used_cost, quota_limit = await check_quota(user, db)

    return True, {
        "rpm": {
            "current": current_rpm,
            "limit": rpm_limit
        },
        "quota": {
            "used": float(used_cost),
            "limit": float(quota_limit)
        }
    }
