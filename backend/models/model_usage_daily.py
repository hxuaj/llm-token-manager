"""
每日用量预聚合模型

存储按天聚合的用量数据，用于加速历史数据查询
"""
import uuid
from datetime import date
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, Date, Integer, BigInteger, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.user import GUID


class ModelUsageDaily(Base):
    """每日用量预聚合表"""
    __tablename__ = "model_usage_daily"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    model_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )
    key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("user_api_keys.id", ondelete="SET NULL"),
        nullable=True
    )
    request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0"),
        nullable=False
    )
    avg_latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint('date', 'user_id', 'model_id', 'key_id', name='uq_model_usage_daily'),
    )

    def __repr__(self) -> str:
        return f"<ModelUsageDaily {self.date} {self.model_id}>"
