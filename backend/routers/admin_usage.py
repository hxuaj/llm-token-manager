"""
Admin 用量统计路由

提供管理员视角的用量统计 API：
- 用量概览
- 按模型统计
- 按用户统计
- 导出 CSV
"""
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from database import get_db
from models.user import User
from models.request_log import RequestLog, RequestStatus
from models.user_api_key import UserApiKey
from models.model_catalog import ModelCatalog
from middleware.auth import get_current_admin_user


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Pydantic 模型（请求/响应）
# ─────────────────────────────────────────────────────────────────────

class TopModelItem(BaseModel):
    """热门模型项"""
    model_id: str
    cost_usd: float
    requests: int


class TopUserItem(BaseModel):
    """热门用户项"""
    user_id: str
    username: str
    cost_usd: float


class UsageOverviewResponse(BaseModel):
    """用量概览响应"""
    period: str
    total_cost_usd: float
    total_requests: int
    active_users: int
    top_models: List[TopModelItem]
    top_users: List[TopUserItem]


class AdminModelUsageItem(BaseModel):
    """Admin 按模型统计项"""
    model_id: str
    display_name: Optional[str] = None
    request_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    percentage: float = 0.0


class AdminUsageByModelResponse(BaseModel):
    """Admin 按模型统计响应"""
    models: List[AdminModelUsageItem]


class UserModelUsage(BaseModel):
    """用户按模型统计"""
    model_id: str
    display_name: Optional[str] = None
    request_count: int
    cost_usd: float


class AdminUserUsageItem(BaseModel):
    """Admin 按用户统计项"""
    user_id: str
    username: str
    request_count: int
    cost_usd: float
    models: List[UserModelUsage] = []


class AdminUsageByUserResponse(BaseModel):
    """Admin 按用户统计响应"""
    users: List[AdminUserUsageItem]


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
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
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


# ─────────────────────────────────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────────────────────────────────

@router.get("/overview", response_model=UsageOverviewResponse)
async def get_usage_overview(
    period: str = Query(default="month", pattern="^(day|week|month)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin 用量概览

    Query 参数：
    - period: 时间段 (day|week|month)，默认 month
    - start_date: 自定义开始日期 (YYYY-MM-DD)
    - end_date: 自定义结束日期 (YYYY-MM-DD)
    """
    start, end, period_str = get_date_range(period, start_date, end_date)

    # 查询总费用和请求数
    total_query = (
        select(
            func.count().label("total_requests"),
            func.sum(RequestLog.cost_usd).label("total_cost"),
            func.count(func.distinct(RequestLog.user_id)).label("active_users")
        )
        .where(
            and_(
                RequestLog.created_at >= start,
                RequestLog.created_at < end,
                RequestLog.status == RequestStatus.SUCCESS
            )
        )
    )
    total_result = await db.execute(total_query)
    total_row = total_result.one()

    total_requests = total_row.total_requests or 0
    total_cost = float(total_row.total_cost or 0)
    active_users = total_row.active_users or 0

    # 查询 Top 5 模型
    top_models_query = (
        select(
            RequestLog.model,
            func.count().label("requests"),
            func.sum(RequestLog.cost_usd).label("cost_usd")
        )
        .where(
            and_(
                RequestLog.created_at >= start,
                RequestLog.created_at < end,
                RequestLog.status == RequestStatus.SUCCESS
            )
        )
        .group_by(RequestLog.model)
        .order_by(desc(func.sum(RequestLog.cost_usd)))
        .limit(5)
    )
    top_models_result = await db.execute(top_models_query)
    top_models = [
        TopModelItem(
            model_id=row.model,
            cost_usd=round(float(row.cost_usd or 0), 6),
            requests=row.requests
        )
        for row in top_models_result.all()
    ]

    # 查询 Top 5 用户
    top_users_query = (
        select(
            RequestLog.user_id,
            func.sum(RequestLog.cost_usd).label("cost_usd")
        )
        .where(
            and_(
                RequestLog.created_at >= start,
                RequestLog.created_at < end,
                RequestLog.status == RequestStatus.SUCCESS,
                RequestLog.user_id.isnot(None)
            )
        )
        .group_by(RequestLog.user_id)
        .order_by(desc(func.sum(RequestLog.cost_usd)))
        .limit(5)
    )
    top_users_result = await db.execute(top_users_query)
    top_user_rows = top_users_result.all()

    # 获取用户名
    user_ids = [str(row.user_id) for row in top_user_rows if row.user_id]
    users_query = select(User).where(User.id.in_(user_ids))
    users_result = await db.execute(users_query)
    user_map = {str(u.id): u.username for u in users_result.scalars().all()}

    top_users = [
        TopUserItem(
            user_id=str(row.user_id),
            username=user_map.get(str(row.user_id), "unknown"),
            cost_usd=round(float(row.cost_usd or 0), 6)
        )
        for row in top_user_rows
    ]

    return UsageOverviewResponse(
        period=period_str,
        total_cost_usd=round(total_cost, 6),
        total_requests=total_requests,
        active_users=active_users,
        top_models=top_models,
        top_users=top_users
    )


@router.get("/by-model", response_model=AdminUsageByModelResponse)
async def get_usage_by_model(
    period: str = Query(default="month", pattern="^(day|week|month)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    sort_by: str = Query(default="cost_usd", pattern="^(cost_usd|request_count)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin 按模型统计

    Query 参数：
    - period: 时间段 (day|week|month)，默认 month
    - start_date: 自定义开始日期 (YYYY-MM-DD)
    - end_date: 自定义结束日期 (YYYY-MM-DD)
    - sort_by: 排序字段 (cost_usd|request_count)
    - sort_order: 排序方向 (asc|desc)
    """
    start, end, _ = get_date_range(period, start_date, end_date)

    # 查询按模型分组
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
                RequestLog.created_at >= start,
                RequestLog.created_at < end,
                RequestLog.status == RequestStatus.SUCCESS
            )
        )
        .group_by(RequestLog.model)
    )

    # 排序
    if sort_by == "request_count":
        order_col = func.count()
    else:
        order_col = func.sum(RequestLog.cost_usd)

    if sort_order == "desc":
        query = query.order_by(desc(order_col))
    else:
        query = query.order_by(order_col)

    result = await db.execute(query)
    rows = result.all()

    # 获取模型目录信息
    model_ids = [row.model for row in rows]
    catalog_query = select(ModelCatalog).where(ModelCatalog.model_id.in_(model_ids))
    catalog_result = await db.execute(catalog_query)
    catalog_map = {c.model_id: c.display_name for c in catalog_result.scalars().all()}

    # 计算总费用
    total_cost = sum(float(row.cost_usd or 0) for row in rows)

    # 构建响应
    models = []
    for row in rows:
        cost = float(row.cost_usd or 0)
        percentage = (cost / total_cost * 100) if total_cost > 0 else 0
        models.append(AdminModelUsageItem(
            model_id=row.model,
            display_name=catalog_map.get(row.model),
            request_count=row.request_count,
            input_tokens=int(row.input_tokens or 0),
            output_tokens=int(row.output_tokens or 0),
            cost_usd=round(cost, 6),
            percentage=round(percentage, 1)
        ))

    return AdminUsageByModelResponse(models=models)


@router.get("/by-user", response_model=AdminUsageByUserResponse)
async def get_usage_by_user(
    period: str = Query(default="month", pattern="^(day|week|month)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    expand_models: bool = Query(default=False),
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin 按用户统计

    Query 参数：
    - period: 时间段 (day|week|month)，默认 month
    - start_date: 自定义开始日期 (YYYY-MM-DD)
    - end_date: 自定义结束日期 (YYYY-MM-DD)
    - expand_models: 是否展开模型维度
    """
    start, end, _ = get_date_range(period, start_date, end_date)

    # 查询按用户分组
    query = (
        select(
            RequestLog.user_id,
            func.count().label("request_count"),
            func.sum(RequestLog.cost_usd).label("cost_usd")
        )
        .where(
            and_(
                RequestLog.created_at >= start,
                RequestLog.created_at < end,
                RequestLog.status == RequestStatus.SUCCESS,
                RequestLog.user_id.isnot(None)
            )
        )
        .group_by(RequestLog.user_id)
        .order_by(desc(func.sum(RequestLog.cost_usd)))
    )

    result = await db.execute(query)
    rows = result.all()

    # 获取用户信息
    user_ids = [str(row.user_id) for row in rows if row.user_id]
    users_query = select(User).where(User.id.in_(user_ids))
    users_result = await db.execute(users_query)
    user_map = {str(u.id): u for u in users_result.scalars().all()}

    # 如果需要展开模型
    model_data = {}
    if expand_models:
        model_query = (
            select(
                RequestLog.user_id,
                RequestLog.model,
                func.count().label("request_count"),
                func.sum(RequestLog.cost_usd).label("cost_usd")
            )
            .where(
                and_(
                    RequestLog.created_at >= start,
                    RequestLog.created_at < end,
                    RequestLog.status == RequestStatus.SUCCESS,
                    RequestLog.user_id.isnot(None)
                )
            )
            .group_by(RequestLog.user_id, RequestLog.model)
        )
        model_result = await db.execute(model_query)
        for row in model_result.all():
            user_id = str(row.user_id)
            if user_id not in model_data:
                model_data[user_id] = []
            model_data[user_id].append({
                "model_id": row.model,
                "request_count": row.request_count,
                "cost_usd": float(row.cost_usd or 0)
            })

        # 获取模型目录信息
        all_model_ids = list(set(
            m["model_id"]
            for models in model_data.values()
            for m in models
        ))
        if all_model_ids:
            catalog_query = select(ModelCatalog).where(ModelCatalog.model_id.in_(all_model_ids))
            catalog_result = await db.execute(catalog_query)
            catalog_map = {c.model_id: c.display_name for c in catalog_result.scalars().all()}
        else:
            catalog_map = {}

        # 添加 display_name
        for user_id, models in model_data.items():
            for m in models:
                m["display_name"] = catalog_map.get(m["model_id"])

    # 构建响应
    users = []
    for row in rows:
        user_id = str(row.user_id)
        user = user_map.get(user_id)

        user_item = AdminUserUsageItem(
            user_id=user_id,
            username=user.username if user else "unknown",
            request_count=row.request_count,
            cost_usd=round(float(row.cost_usd or 0), 6),
            models=[]
        )

        if expand_models and user_id in model_data:
            user_item.models = [
                UserModelUsage(
                    model_id=m["model_id"],
                    display_name=m.get("display_name"),
                    request_count=m["request_count"],
                    cost_usd=round(m["cost_usd"], 6)
                )
                for m in model_data[user_id]
            ]

        users.append(user_item)

    return AdminUsageByUserResponse(users=users)


@router.get("/export")
async def export_usage(
    format: str = Query(default="csv", pattern="^csv$"),
    group_by: str = Query(default="model", pattern="^(model|user|key)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    period: str = Query(default="month", pattern="^(day|week|month)$"),
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    导出用量数据为 CSV

    Query 参数：
    - format: 导出格式 (csv)，目前只支持 csv
    - group_by: 分组方式 (model|user|key)
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    - period: 时间段 (day|week|month)
    """
    start, end, _ = get_date_range(period, start_date, end_date)

    # 根据分组方式查询数据
    if group_by == "model":
        query = (
            select(
                RequestLog.model.label("model_id"),
                func.count().label("request_count"),
                func.sum(RequestLog.input_tokens).label("input_tokens"),
                func.sum(RequestLog.output_tokens).label("output_tokens"),
                func.sum(RequestLog.cost_usd).label("cost_usd")
            )
            .where(
                and_(
                    RequestLog.created_at >= start,
                    RequestLog.created_at < end,
                    RequestLog.status == RequestStatus.SUCCESS
                )
            )
            .group_by(RequestLog.model)
            .order_by(desc(func.sum(RequestLog.cost_usd)))
        )
        result = await db.execute(query)
        rows = result.all()

        # 创建 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["model_id", "request_count", "input_tokens", "output_tokens", "cost_usd"])
        for row in rows:
            writer.writerow([
                row.model_id,
                row.request_count,
                int(row.input_tokens or 0),
                int(row.output_tokens or 0),
                round(float(row.cost_usd or 0), 6)
            ])

    elif group_by == "user":
        query = (
            select(
                RequestLog.user_id,
                func.count().label("request_count"),
                func.sum(RequestLog.cost_usd).label("cost_usd")
            )
            .where(
                and_(
                    RequestLog.created_at >= start,
                    RequestLog.created_at < end,
                    RequestLog.status == RequestStatus.SUCCESS,
                    RequestLog.user_id.isnot(None)
                )
            )
            .group_by(RequestLog.user_id)
            .order_by(desc(func.sum(RequestLog.cost_usd)))
        )
        result = await db.execute(query)
        rows = result.all()

        # 获取用户名
        user_ids = [str(row.user_id) for row in rows if row.user_id]
        users_query = select(User).where(User.id.in_(user_ids))
        users_result = await db.execute(users_query)
        user_map = {str(u.id): u.username for u in users_result.scalars().all()}

        # 创建 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["user_id", "username", "request_count", "cost_usd"])
        for row in rows:
            writer.writerow([
                str(row.user_id),
                user_map.get(str(row.user_id), "unknown"),
                row.request_count,
                round(float(row.cost_usd or 0), 6)
            ])

    else:  # key
        query = (
            select(
                RequestLog.key_id,
                RequestLog.user_id,
                func.count().label("request_count"),
                func.sum(RequestLog.cost_usd).label("cost_usd")
            )
            .where(
                and_(
                    RequestLog.created_at >= start,
                    RequestLog.created_at < end,
                    RequestLog.status == RequestStatus.SUCCESS,
                    RequestLog.key_id.isnot(None)
                )
            )
            .group_by(RequestLog.key_id, RequestLog.user_id)
            .order_by(desc(func.sum(RequestLog.cost_usd)))
        )
        result = await db.execute(query)
        rows = result.all()

        # 获取 Key 信息
        key_ids = [str(row.key_id) for row in rows if row.key_id]
        keys_query = select(UserApiKey).where(UserApiKey.id.in_(key_ids))
        keys_result = await db.execute(keys_query)
        key_map = {str(k.id): k for k in keys_result.scalars().all()}

        # 获取用户名
        user_ids = list(set(str(row.user_id) for row in rows if row.user_id))
        users_query = select(User).where(User.id.in_(user_ids))
        users_result = await db.execute(users_query)
        user_map = {str(u.id): u.username for u in users_result.scalars().all()}

        # 创建 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["key_id", "key_suffix", "username", "request_count", "cost_usd"])
        for row in rows:
            key = key_map.get(str(row.key_id))
            writer.writerow([
                str(row.key_id),
                key.key_suffix if key else "unknown",
                user_map.get(str(row.user_id), "unknown"),
                row.request_count,
                round(float(row.cost_usd or 0), 6)
            ])

    # 生成响应
    csv_content = output.getvalue()
    filename = f"usage_export_{group_by}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
