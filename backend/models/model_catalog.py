"""
模型目录模型

存储从供应商自动发现或手动配置的模型信息
"""
import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.user import GUID


class ModelStatus:
    """模型状态常量"""
    PENDING = "pending"    # 待启用（新发现的模型）
    ACTIVE = "active"      # 已启用
    INACTIVE = "inactive"  # 已禁用
    DEPRECATED = "deprecated"  # 已废弃
    ALPHA = "alpha"        # 内测
    BETA = "beta"          # 公测


class ModelSource:
    """模型来源常量"""
    AUTO_DISCOVERED = "auto_discovered"  # 自动发现
    MANUAL = "manual"                     # 手动添加
    BUILTIN_DEFAULT = "builtin_default"   # 内置默认定价
    MODELS_DEV = "models_dev"             # 从 models.dev 同步


class ModelCatalog(Base):
    """模型目录表"""
    __tablename__ = "model_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    model_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    # 定价（单位：USD per 1M tokens）
    input_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0"),
        nullable=False
    )
    output_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0"),
        nullable=False
    )
    cache_write_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True
    )
    cache_read_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True
    )
    # 模型能力
    context_window: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    max_output: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    supports_vision: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    supports_tools: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    supports_streaming: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    # 扩展能力字段
    supports_reasoning: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    # 状态和来源
    status: Mapped[str] = mapped_column(
        String(20),
        default=ModelStatus.PENDING,
        nullable=False,
        index=True
    )
    is_pricing_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(20),
        default=ModelSource.MANUAL,
        nullable=False
    )
    # SSOT 字段
    models_dev_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    base_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
    )
    local_overrides: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    # 额外元数据
    family: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    knowledge_cutoff: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )
    release_date: Mapped[Optional[str]] = mapped_column(
        String(20),
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

    # 关系
    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="models"
    )

    def __repr__(self) -> str:
        return f"<ModelCatalog {self.model_id}>"

    @property
    def is_active(self) -> bool:
        """检查模型是否已启用"""
        return self.status == ModelStatus.ACTIVE

    @property
    def has_confirmed_pricing(self) -> bool:
        """检查定价是否已确认"""
        return self.is_pricing_confirmed and self.input_price > 0


# 避免循环导入
from models.provider import Provider
