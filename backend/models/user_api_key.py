"""
用户 API Key 模型

存储用户创建的平台 Key，用于 API 调用鉴权
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from database import Base
from models.user import GUID


class KeyStatus(str, enum.Enum):
    """Key 状态枚举"""
    ACTIVE = "active"
    REVOKED = "revoked"


class UserApiKey(Base):
    """用户 API Key 表"""
    __tablename__ = "user_api_keys"

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
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 哈希
        unique=True,
        nullable=False,
        index=True
    )
    key_prefix: Mapped[str] = mapped_column(
        String(12),
        default="ltm-sk-",
        nullable=False
    )
    key_suffix: Mapped[str] = mapped_column(
        String(4),
        nullable=False
    )
    status: Mapped[KeyStatus] = mapped_column(
        String(20),
        default=KeyStatus.ACTIVE.value,
        nullable=False,
        index=True
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )

    # 关联用户
    user: Mapped["User"] = relationship("User", backref="api_keys")

    def __repr__(self) -> str:
        return f"<UserApiKey {self.key_prefix}...{self.key_suffix}>"

    @property
    def is_active(self) -> bool:
        """检查 Key 是否活跃"""
        return self.status == KeyStatus.ACTIVE.value or self.status == KeyStatus.ACTIVE

    def revoke(self):
        """吊销 Key"""
        self.status = KeyStatus.REVOKED.value if isinstance(self.status, str) else KeyStatus.REVOKED
        self.revoked_at = datetime.utcnow()
