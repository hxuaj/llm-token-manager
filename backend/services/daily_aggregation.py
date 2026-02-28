"""
每日用量聚合服务

将 request_logs 中的数据聚合到 model_usage_daily 表
用于加速历史数据查询
"""
import uuid
import asyncio
from datetime import date, timedelta, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.dialects.postgresql import insert

from database import AsyncSessionLocal
from models.request_log import RequestLog, RequestStatus
from models.model_usage_daily import ModelUsageDaily
from models.user_api_key import UserApiKey


class DailyAggregationService:
    """每日用量聚合服务"""

    async def aggregate_day(self, target_date: date, db: Optional[AsyncSession] = None) -> dict:
        """
        聚合指定日期的用量数据

        Args:
            target_date: 目标日期
            db: 数据库 session（可选，不传则创建新的）

        Returns:
            聚合结果统计
        """
        if db is None:
            async with AsyncSessionLocal() as session:
                return await self._do_aggregate(target_date, session)
        else:
            return await self._do_aggregate(target_date, db)

    async def _do_aggregate(self, target_date: date, db: AsyncSession) -> dict:
        """执行聚合逻辑"""
        # 计算时间范围（UTC）
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = start_time + timedelta(days=1)

        # 按 (user_id, model_id, key_id) 分组聚合
        query = (
            select(
                RequestLog.user_id,
                RequestLog.model_id,
                RequestLog.key_id,
                func.count().label("request_count"),
                func.sum(RequestLog.input_tokens).label("input_tokens"),
                func.sum(RequestLog.output_tokens).label("output_tokens"),
                func.sum(RequestLog.cost_usd).label("total_cost_usd"),
                func.avg(RequestLog.latency_ms).label("avg_latency_ms"),
                func.sum(
                    func.case(
                        (RequestLog.status != RequestStatus.SUCCESS, 1),
                        else_=0
                    )
                ).label("error_count")
            )
            .where(
                and_(
                    RequestLog.created_at >= start_time,
                    RequestLog.created_at < end_time
                )
            )
            .group_by(RequestLog.user_id, RequestLog.model_id, RequestLog.key_id)
        )

        result = await db.execute(query)
        rows = result.all()

        aggregated_count = 0
        updated_count = 0

        for row in rows:
            # 检查是否已有聚合记录
            existing_result = await db.execute(
                select(ModelUsageDaily).where(
                    and_(
                        ModelUsageDaily.date == target_date,
                        ModelUsageDaily.user_id == row.user_id,
                        ModelUsageDaily.model_id == row.model_id,
                        ModelUsageDaily.key_id == row.key_id
                    )
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # 更新现有记录
                existing.request_count = row.request_count
                existing.input_tokens = int(row.input_tokens or 0)
                existing.output_tokens = int(row.output_tokens or 0)
                existing.total_cost_usd = Decimal(str(row.total_cost_usd or 0))
                existing.avg_latency_ms = int(row.avg_latency_ms or 0)
                existing.error_count = int(row.error_count or 0)
                updated_count += 1
            else:
                # 创建新记录
                daily = ModelUsageDaily(
                    id=uuid.uuid4(),
                    date=target_date,
                    user_id=row.user_id,
                    model_id=row.model_id,
                    key_id=row.key_id,
                    request_count=row.request_count,
                    input_tokens=int(row.input_tokens or 0),
                    output_tokens=int(row.output_tokens or 0),
                    total_cost_usd=Decimal(str(row.total_cost_usd or 0)),
                    avg_latency_ms=int(row.avg_latency_ms or 0),
                    error_count=int(row.error_count or 0)
                )
                db.add(daily)
                aggregated_count += 1

        await db.commit()

        return {
            "date": target_date.isoformat(),
            "aggregated": aggregated_count,
            "updated": updated_count,
            "total": len(rows)
        }

    async def aggregate_yesterday(self) -> dict:
        """聚合昨天的数据（常用入口）"""
        yesterday = date.today() - timedelta(days=1)
        return await self.aggregate_day(yesterday)

    async def aggregate_last_n_days(self, n: int = 7) -> List[dict]:
        """
        聚合过去 N 天的数据

        Args:
            n: 天数

        Returns:
            每天的聚合结果
        """
        results = []
        today = date.today()

        for i in range(1, n + 1):
            target_date = today - timedelta(days=i)
            result = await self.aggregate_day(target_date)
            results.append(result)

        return results


# 全局实例
daily_aggregation_service = DailyAggregationService()


async def run_daily_aggregation_task():
    """
    每日聚合任务入口

    可以被定时任务框架（如 APScheduler）调用
    """
    return await daily_aggregation_service.aggregate_yesterday()


# ─────────────────────────────────────────────────────────────────────
# 定时任务配置（使用 asyncio 或外部调度器）
# ─────────────────────────────────────────────────────────────────────

async def start_daily_aggregation_scheduler():
    """
    启动每日聚合定时任务

    注意：这是一个简单的实现，生产环境建议使用：
    - APScheduler
    - Celery Beat
    - 系统 cron + 脚本调用
    """
    while True:
        now = datetime.utcnow()
        # 每天凌晨 1:00 执行
        target_time = now.replace(hour=1, minute=0, second=0, microsecond=0)
        if now >= target_time:
            target_time = target_time + timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        try:
            result = await run_daily_aggregation_task()
            print(f"Daily aggregation completed: {result}")
        except Exception as e:
            print(f"Daily aggregation failed: {e}")
