"""
供应商 API Key 模型

存储供应商的 API Key，AES-256 加密存储
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from database import Base
from models.user import GUID


class ProviderKeyStatus(str, enum.Enum):
    """供应商 Key 状态枚举"""
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class ProviderApiKey(Base):
    """供应商 API Key 表"""
    __tablename__ = "provider_api_keys"

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
    encrypted_key: Mapped[str] = mapped_column(
        Text,  # AES-256 加密后的 Base64 字符串
        nullable=False
    )
    key_suffix: Mapped[str] = mapped_column(
        String(4),
        nullable=False
    )
    rpm_limit: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False
    )
    status: Mapped[ProviderKeyStatus] = mapped_column(
        String(20),
        default=ProviderKeyStatus.ACTIVE.value,
        nullable=False,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # 关联供应商
    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="api_keys"
    )

    def __repr__(self) -> str:
        return f"<ProviderApiKey ...{self.key_suffix}>"

    @property
    def is_active(self) -> bool:
        """检查 Key 是否可用"""
        return self.status == ProviderKeyStatus.ACTIVE.value or self.status == ProviderKeyStatus.ACTIVE
