"""
模型定价历史模型

记录模型定价的变更历史
"""
import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.user import GUID


class ModelPricingHistory(Base):
    """模型定价历史表"""
    __tablename__ = "model_pricing_history"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    model_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )
    old_input_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True
    )
    new_input_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False
    )
    old_output_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True
    )
    new_output_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False
    )
    changed_by: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    def __repr__(self) -> str:
        return f"<ModelPricingHistory {self.model_id} at {self.changed_at}>"
