"""
供应商模型

存储大模型供应商配置（OpenAI、Anthropic 等）
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.user import GUID


class ApiFormat:
    """API 格式枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"


class ProviderSource:
    """供应商来源常量"""
    MODELS_DEV = "models_dev"    # 从 models.dev 同步
    CUSTOM = "custom"            # 用户自定义


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
    display_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    base_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    api_format: Mapped[str] = mapped_column(
        String(20),
        default=ApiFormat.OPENAI,
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
    # SSOT 字段
    source: Mapped[str] = mapped_column(
        String(20),
        default=ProviderSource.CUSTOM,
        nullable=False
    )
    models_dev_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    local_overrides: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict
    )
    supported_endpoints: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=list
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
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
    models: Mapped[list["ModelCatalog"]] = relationship(
        "ModelCatalog",
        back_populates="provider",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Provider {self.name}>"
