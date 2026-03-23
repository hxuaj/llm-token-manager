"""
用户模型

存储用户账号信息，包括：
- 认证信息（用户名、邮箱、密码哈希）
- 角色权限（admin/user）
- 额度配置
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Numeric, Integer, Text, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator, CHAR
import enum

from database import Base


class GUID(TypeDecorator):
    """
    平台无关的 GUID 类型，使用 CHAR(32) 存储。

    在 PostgreSQL 中使用原生 UUID，在其他数据库中使用 CHAR(32)。
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, uuid.UUID):
                return value.hex
            else:
                return uuid.UUID(value).hex

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if isinstance(value, uuid.UUID):
                return value
            return uuid.UUID(value) if len(str(value)) == 36 else uuid.UUID(hex=value)


class UserRole(str, enum.Enum):
    """用户角色枚举"""
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    role: Mapped[UserRole] = mapped_column(
        String(20),
        default=UserRole.USER.value,
        nullable=False
    )

    # 额度配置
    monthly_quota_usd: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=10.00,
        nullable=False
    )
    rpm_limit: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False
    )
    allowed_models: Mapped[Optional[str]] = mapped_column(
        Text,  # JSON 字符串
        nullable=True  # null 表示不限制
    )
    max_keys: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False
    )

    # 供应商 Key 软分配
    primary_provider_keys: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict
        # 数据结构: {"openai": "uuid-of-primary-key", "anthropic": "uuid-of-primary-key", ...}
    )

    # 状态
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"

    @property
    def is_admin(self) -> bool:
        """检查是否为管理员"""
        return self.role == UserRole.ADMIN.value or self.role == UserRole.ADMIN
