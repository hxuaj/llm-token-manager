"""
额度告警服务

检查用户额度使用情况，在达到阈值时生成告警
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from models.user import User
from models.request_log import RequestLog, RequestStatus
from models.user_model_limit import UserModelLimit
from models.monthly_usage import MonthlyUsage


class QuotaLevel(str, Enum):
    """额度告警级别"""
    NORMAL = "normal"       # < 80%
    WARNING = "warning"     # 80% - 95%
    CRITICAL = "critical"   # 95% - 100%
    EXCEEDED = "exceeded"   # >= 100%


class QuotaAlertService:
    """额度告警服务"""

    # 告警阈值
    WARNING_THRESHOLD = 0.80   # 80%
    CRITICAL_THRESHOLD = 0.95  # 95%

    async def check_user_quota(
        self,
        user: User,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        检查用户总额度使用情况

        Args:
            user: 用户对象
            db: 数据库 session

        Returns:
            {
                "level": QuotaLevel,
                "percent_used": float,
                "quota_used": float,
                "quota_limit": float,
                "warning": Optional[str]
            }
        """
        # 获取本月用量
        year_month = datetime.utcnow().strftime("%Y-%m")
        result = await db.execute(
            select(MonthlyUsage).where(
                and_(
                    MonthlyUsage.user_id == user.id,
                    MonthlyUsage.year_month == year_month
                )
            )
        )
        monthly_usage = result.scalar_one_or_none()

        quota_used = float(monthly_usage.total_cost_usd) if monthly_usage else 0.0
        quota_limit = float(user.monthly_quota_usd) if user.monthly_quota_usd else 0.0

        if quota_limit <= 0:
            return {
                "level": QuotaLevel.NORMAL,
                "percent_used": 0.0,
                "quota_used": quota_used,
                "quota_limit": quota_limit,
                "warning": None
            }

        percent_used = min(100.0, (quota_used / quota_limit) * 100)

        # 确定告警级别
        if percent_used >= 100:
            level = QuotaLevel.EXCEEDED
            warning = "quota_exceeded"
        elif percent_used >= self.CRITICAL_THRESHOLD * 100:
            level = QuotaLevel.CRITICAL
            warning = "quota_critical"
        elif percent_used >= self.WARNING_THRESHOLD * 100:
            level = QuotaLevel.WARNING
            warning = "quota_warning"
        else:
            level = QuotaLevel.NORMAL
            warning = None

        return {
            "level": level,
            "percent_used": percent_used,
            "quota_used": quota_used,
            "quota_limit": quota_limit,
            "warning": warning
        }

    async def check_model_quota(
        self,
        user: User,
        model_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        检查用户对特定模型的额度使用情况

        Args:
            user: 用户对象
            model_id: 模型 ID
            db: 数据库 session

        Returns:
            {
                "level": QuotaLevel,
                "percent_used": float,
                "model_used": float,
                "model_limit": float,
                "daily_requests": int,
                "daily_limit": Optional[int],
                "warning": Optional[str]
            }
        """
        # 查询模型级限制
        result = await db.execute(
            select(UserModelLimit).where(
                and_(
                    UserModelLimit.user_id == user.id,
                    UserModelLimit.model_id == model_id
                )
            )
        )
        model_limit = result.scalar_one_or_none()

        # 如果没有模型级限制，返回正常
        if not model_limit or (
            not model_limit.monthly_limit_usd and not model_limit.daily_request_limit
        ):
            return {
                "level": QuotaLevel.NORMAL,
                "percent_used": 0.0,
                "model_used": 0.0,
                "model_limit": 0.0,
                "daily_requests": 0,
                "daily_limit": None,
                "warning": None
            }

        # 计算本月该模型用量
        year_month = datetime.utcnow().strftime("%Y-%m")
        cost_result = await db.execute(
            select(func.sum(RequestLog.cost_usd)).where(
                and_(
                    RequestLog.user_id == user.id,
                    RequestLog.model == model_id,
                    RequestLog.status == RequestStatus.SUCCESS,
                    func.strftime('%Y-%m', RequestLog.created_at) == year_month
                )
            )
        )
        model_used = float(cost_result.scalar() or 0)

        # 计算今日请求数
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        request_result = await db.execute(
            select(func.count()).where(
                and_(
                    RequestLog.user_id == user.id,
                    RequestLog.model == model_id,
                    RequestLog.created_at >= today_start
                )
            )
        )
        daily_requests = request_result.scalar() or 0

        # 检查月度额度
        monthly_limit = float(model_limit.monthly_limit_usd) if model_limit.monthly_limit_usd else None
        daily_limit = model_limit.daily_request_limit

        percent_used = 0.0
        level = QuotaLevel.NORMAL
        warning = None

        # 检查日请求限制
        if daily_limit and daily_requests >= daily_limit:
            level = QuotaLevel.EXCEEDED
            warning = "daily_request_limit_exceeded"

        # 检查月度额度
        if monthly_limit and monthly_limit > 0:
            percent_used = min(100.0, (model_used / monthly_limit) * 100)

            if percent_used >= 100:
                level = QuotaLevel.EXCEEDED
                warning = "model_quota_exceeded"
            elif percent_used >= self.CRITICAL_THRESHOLD * 100 and level != QuotaLevel.EXCEEDED:
                level = QuotaLevel.CRITICAL
                warning = "model_quota_critical"
            elif percent_used >= self.WARNING_THRESHOLD * 100 and level == QuotaLevel.NORMAL:
                level = QuotaLevel.WARNING
                warning = "model_quota_warning"

        return {
            "level": level,
            "percent_used": percent_used,
            "model_used": model_used,
            "model_limit": monthly_limit or 0.0,
            "daily_requests": daily_requests,
            "daily_limit": daily_limit,
            "warning": warning
        }

    async def get_alert_headers(
        self,
        user: User,
        model_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        获取响应头中的告警信息

        Args:
            user: 用户对象
            model_id: 模型 ID
            db: 数据库 session

        Returns:
            用于 x_ltm 响应头的告警信息
        """
        user_quota = await self.check_user_quota(user, db)
        model_quota = await self.check_model_quota(user, model_id, db)

        x_ltm = {
            "quota_used": round(user_quota["quota_used"], 4),
            "quota_limit": round(user_quota["quota_limit"], 2),
            "quota_percent": round(user_quota["percent_used"], 1),
        }

        # 添加告警
        if user_quota["warning"]:
            x_ltm["quota_warning"] = user_quota["warning"]

        if model_quota["warning"]:
            x_ltm["model_warning"] = model_quota["warning"]

        # 检查是否超限
        if user_quota["level"] == QuotaLevel.EXCEEDED:
            x_ltm["quota_exceeded"] = True

        if model_quota["level"] == QuotaLevel.EXCEEDED:
            x_ltm["model_exceeded"] = True

        return x_ltm


# 全局实例
quota_alert_service = QuotaAlertService()
