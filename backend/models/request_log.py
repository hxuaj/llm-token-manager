"""
请求日志模型

记录每次 API 调用的详细信息
"""
import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.user import GUID


class RequestStatus:
    """请求状态常量"""
    SUCCESS = "success"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"


class RequestLog(Base):
    """请求日志表"""
    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    request_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    key_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("user_api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True
    )
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )
    # Token 使用量（原有字段，保持兼容）
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    # Token 使用量（新增字段，与 prompt_tokens/completion_tokens 保持同步）
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    # 缓存相关 token
    cache_read_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    cache_write_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    # 费用
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        default=Decimal("0"),
        nullable=False
    )
    # 性能
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    # 状态
    status: Mapped[str] = mapped_column(
        String(20),
        default=RequestStatus.SUCCESS,
        nullable=False,
        index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    # Key 计划类型（记录请求时使用的 Key 类型）
    key_plan: Mapped[str] = mapped_column(
        String(20),
        default="standard",
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    # 关系
    user: Mapped[Optional["User"]] = relationship("User")
    key: Mapped[Optional["UserApiKey"]] = relationship("UserApiKey")
    provider: Mapped[Optional["Provider"]] = relationship("Provider")

    __table_args__ = (
        Index('ix_request_logs_user_created', 'user_id', 'created_at'),
        Index('ix_request_logs_key_created', 'key_id', 'created_at'),
        Index('ix_request_logs_model_created', 'model', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<RequestLog {self.request_id}>"

    @property
    def is_success(self) -> bool:
        """检查是否成功"""
        return self.status == RequestStatus.SUCCESS

    def sync_token_fields(self) -> None:
        """同步 token 字段（input_tokens <-> prompt_tokens, output_tokens <-> completion_tokens）"""
        self.input_tokens = self.prompt_tokens
        self.output_tokens = self.completion_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens


# 避免循环导入
from models.user import User
from models.user_api_key import UserApiKey
from models.provider import Provider
