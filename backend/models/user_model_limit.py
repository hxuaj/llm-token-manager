"""
用户模型级额度限制模型

允许 Admin 为特定用户设置模型级别的使用限制
"""
import uuid
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.user import GUID


class UserModelLimit(Base):
    """用户模型级限制表"""
    __tablename__ = "user_model_limits"

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
    model_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )
    monthly_limit_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )
    daily_request_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint('user_id', 'model_id', name='uq_user_model_limits'),
    )

    def __repr__(self) -> str:
        return f"<UserModelLimit user={self.user_id} model={self.model_id}>"
