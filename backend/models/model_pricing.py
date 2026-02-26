"""
模型单价配置模型

存储各模型的 token 单价
"""
import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.user import GUID


class ModelPricing(Base):
    """模型单价表"""
    __tablename__ = "model_pricing"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )
    input_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        default=0.0,
        nullable=False
    )
    output_price_per_1k: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        default=0.0,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # 关联供应商
    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="model_pricing"
    )

    def __repr__(self) -> str:
        return f"<ModelPricing {self.model_name}>"
