"""
用户用量统计路由

提供用户视角的用量统计 API：
- 按模型统计
- 按 Key 统计
- 时间线统计
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, literal_column
from sqlalchemy.orm import selectinload

from database import get_db, engine
from models.user import User
from models.request_log import RequestLog, RequestStatus
from models.user_api_key import UserApiKey
from models.model_catalog import ModelCatalog
from middleware.auth import get_current_active_user


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型（请求/响应）
# ─────────────────────────────────────────────────────────────────────

class ModelUsageItem(BaseModel):
    """按模型统计项"""
    model_id: str
    display_name: Optional[str] = None
    request_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    percentage: float = 0.0


class UsageByModelResponse(BaseModel):
    """按模型统计响应"""
    period: str
    total_cost_usd: float
    total_requests: int
    models: List[ModelUsageItem]


class KeyModelUsage(BaseModel):
    """Key 下按模型统计"""
    model_id: str
    display_name: Optional[str] = None
    request_count: int
    cost_usd: float


class KeyUsageItem(BaseModel):
    """按 Key 统计项"""
    key_suffix: str
    key_name: str
    total_cost_usd: float
    models: List[KeyModelUsage]


class UsageByKeyResponse(BaseModel):
    """按 Key 统计响应"""
    keys: List[KeyUsageItem]


class TimelineDataPoint(BaseModel):
    """时间线数据点"""
    date: str
    requests: int
    cost_usd: float
    input_tokens: int
    output_tokens: int


class UsageTimelineResponse(BaseModel):
    """时间线统计响应"""
    granularity: str
    data: List[TimelineDataPoint]


# ─────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────

def get_date_range(period: str, start_date: Optional[str], end_date: Optional[str]) -> tuple:
    """
    根据参数计算日期范围

    Args:
        period: 预定义时间段 (day, week, month)
        start_date: 自定义开始日期 (YYYY-MM-DD)
        end_date: 自定义结束日期 (YYYY-MM-DD)

    Returns:
        (start_datetime, end_datetime, period_str)
    """
    now = datetime.utcnow()

    if start_date and end_date:
        # 使用自定义日期范围
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # 包含结束日期
        period_str = f"{start_date}~{end_date}"
    else:
        # 使用预定义时间段
        if period == "day":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_str = now.strftime("%Y-%m-%d")
        elif period == "week":
            start = now - timedelta(days=7)
            period_str = f"{start.strftime('%Y-%m-%d')}~{now.strftime('%Y-%m-%d')}"
        else:  # month
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            period_str = now.strftime("%Y-%m")

        end = now

    return start, end, period_str


def get_truncate_expr(granularity: str):
    """
    获取日期截断表达式（兼容 SQLite 和 PostgreSQL）

    Args:
        granularity: 粒度 (hour, day, week)

    Returns:
        SQLAlchemy 表达式
    """
    # 检测数据库类型
    dialect_name = engine.dialect.name

    if dialect_name == "sqlite":
        # SQLite 使用 strftime
        if granularity == "hour":
            return func.strftime('%Y-%m-%d %H:00', RequestLog.created_at)
        elif granularity == "week":
            return func.strftime('%Y-%m-%d', RequestLog.created_at)
        else:  # day
            return func.strftime('%Y-%m-%d', RequestLog.created_at)
    else:
        # PostgreSQL 使用 to_char
        if granularity == "hour":
            return func.to_char(RequestLog.created_at, 'YYYY-MM-DD HH24:00')
        elif granularity == "week":
            return func.to_char(RequestLog.created_at, 'YYYY-MM-DD')
        else:  # day
            return func.to_char(RequestLog.created_at, 'YYYY-MM-DD')


# ─────────────────────────────────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────────────────────────────────

@router.get("/by-model", response_model=UsageByModelResponse)
async def get_usage_by_model(
    period: str = Query(default="month", pattern="^(day|week|month)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    按模型统计用户用量

    Query 参数：
    - period: 时间段 (day|week|month)，默认 month
    - start_date: 自定义开始日期 (YYYY-MM-DD)
    - end_date: 自定义结束日期 (YYYY-MM-DD)
    """
    start, end, period_str = get_date_range(period, start_date, end_date)

    # 查询用户在此时间段内的所有日志，按模型分组
    query = (
        select(
            RequestLog.model,
            func.count().label("request_count"),
            func.sum(RequestLog.input_tokens).label("input_tokens"),
            func.sum(RequestLog.output_tokens).label("output_tokens"),
            func.sum(RequestLog.cost_usd).label("cost_usd")
        )
        .where(
            and_(
                RequestLog.user_id == current_user.id,
                RequestLog.created_at >= start,
                RequestLog.created_at < end,
                RequestLog.status == RequestStatus.SUCCESS
            )
        )
        .group_by(RequestLog.model)
        .order_by(func.sum(RequestLog.cost_usd).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    # 获取模型目录信息
    model_ids = [row.model for row in rows]
    catalog_query = select(ModelCatalog).where(ModelCatalog.model_id.in_(model_ids))
    catalog_result = await db.execute(catalog_query)
    catalog_map = {c.model_id: c.display_name for c in catalog_result.scalars().all()}

    # 计算总费用
    total_cost = sum(float(row.cost_usd or 0) for row in rows)
    total_requests = sum(row.request_count for row in rows)

    # 构建响应
    models = []
    for row in rows:
        cost = float(row.cost_usd or 0)
        percentage = (cost / total_cost * 100) if total_cost > 0 else 0
        models.append(ModelUsageItem(
            model_id=row.model,
            display_name=catalog_map.get(row.model),
            request_count=row.request_count,
            input_tokens=int(row.input_tokens or 0),
            output_tokens=int(row.output_tokens or 0),
            cost_usd=cost,
            percentage=round(percentage, 1)
        ))

    return UsageByModelResponse(
        period=period_str,
        total_cost_usd=round(total_cost, 6),
        total_requests=total_requests,
        models=models
    )


@router.get("/by-key", response_model=UsageByKeyResponse)
async def get_usage_by_key(
    period: str = Query(default="month", pattern="^(day|week|month)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    按 Key 统计用户用量

    Query 参数：
    - period: 时间段 (day|week|month)，默认 month
    - start_date: 自定义开始日期 (YYYY-MM-DD)
    - end_date: 自定义结束日期 (YYYY-MM-DD)
    """
    start, end, _ = get_date_range(period, start_date, end_date)

    # 查询用户的所有 Key
    keys_query = select(UserApiKey).where(UserApiKey.user_id == current_user.id)
    keys_result = await db.execute(keys_query)
    user_keys = keys_result.scalars().all()
    key_map = {str(k.id): k for k in user_keys}

    # 查询日志，按 Key 和模型分组
    query = (
        select(
            RequestLog.key_id,
            RequestLog.model,
            func.count().label("request_count"),
            func.sum(RequestLog.cost_usd).label("cost_usd")
        )
        .where(
            and_(
                RequestLog.user_id == current_user.id,
                RequestLog.created_at >= start,
                RequestLog.created_at < end,
                RequestLog.status == RequestStatus.SUCCESS,
                RequestLog.key_id.isnot(None)
            )
        )
        .group_by(RequestLog.key_id, RequestLog.model)
    )

    result = await db.execute(query)
    rows = result.all()

    # 获取模型目录信息
    model_ids = list(set(row.model for row in rows))
    catalog_query = select(ModelCatalog).where(ModelCatalog.model_id.in_(model_ids))
    catalog_result = await db.execute(catalog_query)
    catalog_map = {c.model_id: c.display_name for c in catalog_result.scalars().all()}

    # 按 Key 聚合
    key_data = {}
    for row in rows:
        key_id = str(row.key_id) if row.key_id else None
        if key_id not in key_data:
            key_obj = key_map.get(key_id)
            key_data[key_id] = {
                "key_suffix": key_obj.key_suffix if key_obj else "unknown",
                "key_name": key_obj.name if key_obj else "Unknown Key",
                "total_cost_usd": 0.0,
                "models": {}
            }

        cost = float(row.cost_usd or 0)
        key_data[key_id]["total_cost_usd"] += cost

        if row.model not in key_data[key_id]["models"]:
            key_data[key_id]["models"][row.model] = {
                "model_id": row.model,
                "display_name": catalog_map.get(row.model),
                "request_count": 0,
                "cost_usd": 0.0
            }
        key_data[key_id]["models"][row.model]["request_count"] += row.request_count
        key_data[key_id]["models"][row.model]["cost_usd"] += cost

    # 构建响应
    keys = []
    for key_id, data in key_data.items():
        keys.append(KeyUsageItem(
            key_suffix=data["key_suffix"],
            key_name=data["key_name"],
            total_cost_usd=round(data["total_cost_usd"], 6),
            models=[
                KeyModelUsage(
                    model_id=m["model_id"],
                    display_name=m["display_name"],
                    request_count=m["request_count"],
                    cost_usd=round(m["cost_usd"], 6)
                )
                for m in data["models"].values()
            ]
        ))

    return UsageByKeyResponse(keys=keys)


@router.get("/timeline", response_model=UsageTimelineResponse)
async def get_usage_timeline(
    granularity: str = Query(default="day", pattern="^(hour|day|week)$"),
    model_id: Optional[str] = Query(default=None),
    period: str = Query(default="month", pattern="^(day|week|month)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    时间线统计

    Query 参数：
    - granularity: 粒度 (hour|day|week)，默认 day
    - model_id: 可选，按模型过滤
    - period: 时间段 (day|week|month)，默认 month
    - start_date: 自定义开始日期 (YYYY-MM-DD)
    - end_date: 自定义结束日期 (YYYY-MM-DD)
    """
    start, end, _ = get_date_range(period, start_date, end_date)

    # 构建查询条件
    conditions = [
        RequestLog.user_id == current_user.id,
        RequestLog.created_at >= start,
        RequestLog.created_at < end,
        RequestLog.status == RequestStatus.SUCCESS
    ]
    if model_id:
        conditions.append(RequestLog.model == model_id)

    # 获取日期截断表达式
    date_expr = get_truncate_expr(granularity)

    # 查询按时间分组
    query = (
        select(
            date_expr.label("date"),
            func.count().label("requests"),
            func.sum(RequestLog.cost_usd).label("cost_usd"),
            func.sum(RequestLog.input_tokens).label("input_tokens"),
            func.sum(RequestLog.output_tokens).label("output_tokens")
        )
        .where(and_(*conditions))
        .group_by(date_expr)
        .order_by(date_expr)
    )

    result = await db.execute(query)
    rows = result.all()

    # 构建响应
    data = []
    for row in rows:
        data.append(TimelineDataPoint(
            date=row.date,
            requests=row.requests,
            cost_usd=round(float(row.cost_usd or 0), 6),
            input_tokens=int(row.input_tokens or 0),
            output_tokens=int(row.output_tokens or 0)
        ))

    return UsageTimelineResponse(
        granularity=granularity,
        data=data
    )
