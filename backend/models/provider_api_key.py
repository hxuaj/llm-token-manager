"""
供应商 API Key 模型

存储供应商的 API Key，AES-256 加密存储
"""
import uuid
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from database import Base
from models.user import GUID


class ProviderKeyStatus(str, enum.Enum):
    """供应商 Key 状态枚举"""
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class KeyPlan(str, enum.Enum):
    """Key 计划类型枚举"""
    STANDARD = "standard"      # 标准 API Key（按量计费）
    CODING_PLAN = "coding_plan"  # Coding Plan 订阅（月费制）


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
    # Key 计划类型相关字段
    key_plan: Mapped[str] = mapped_column(
        String(20),
        default=KeyPlan.STANDARD.value,
        nullable=False
    )
    plan_models: Mapped[Optional[str]] = mapped_column(
        Text,  # JSON 数组字符串，coding_plan 时存储支持的模型列表
        nullable=True
    )
    plan_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    override_input_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True  # coding_plan 时可设置虚拟单价用于统计
    )
    override_output_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True
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

    @property
    def is_coding_plan(self) -> bool:
        """检查是否为 Coding Plan Key"""
        return self.key_plan == KeyPlan.CODING_PLAN.value or self.key_plan == KeyPlan.CODING_PLAN

    def get_plan_models_list(self) -> List[str]:
        """获取 plan_models 的列表形式"""
        import json
        if not self.plan_models:
            return []
        try:
            return json.loads(self.plan_models)
        except (json.JSONDecodeError, TypeError):
            return []

    def supports_model(self, model_id: str) -> bool:
        """检查该 Key 是否支持指定模型（仅对 coding_plan 有效）"""
        if not self.is_coding_plan:
            return True  # standard Key 支持所有模型
        return model_id in self.get_plan_models_list()
