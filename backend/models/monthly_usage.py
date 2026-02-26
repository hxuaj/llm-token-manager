"""
月度用量统计模型

汇总每个用户每月的用量数据
"""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.user import GUID


class MonthlyUsage(Base):
    """月度用量统计表"""
    __tablename__ = "monthly_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    year_month: Mapped[str] = mapped_column(
        String(7),  # 格式: 2026-02
        nullable=False
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0"),
        nullable=False
    )
    request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # 关系
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint('user_id', 'year_month', name='uq_user_year_month'),
        Index('ix_monthly_usage_year_month', 'year_month'),
    )

    def __repr__(self) -> str:
        return f"<MonthlyUsage user={self.user_id} month={self.year_month}>"

    @property
    def remaining_quota(self) -> Decimal:
        """计算剩余额度（需要用户额度）"""
        if self.user:
            return Decimal(str(self.user.monthly_quota_usd)) - self.total_cost_usd
        return Decimal("0")


# 避免循环导入
from models.user import User
