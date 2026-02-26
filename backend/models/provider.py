"""
供应商模型

存储大模型供应商配置（OpenAI、Anthropic 等）
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.user import GUID


class Provider(Base):
    """供应商表"""
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )
    base_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    config: Mapped[Optional[str]] = mapped_column(
        Text,  # JSON 配置
        nullable=True
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

    # 关联
    api_keys: Mapped[list["ProviderApiKey"]] = relationship(
        "ProviderApiKey",
        back_populates="provider",
        cascade="all, delete-orphan"
    )
    model_pricing: Mapped[list["ModelPricing"]] = relationship(
        "ModelPricing",
        back_populates="provider",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Provider {self.name}>"
