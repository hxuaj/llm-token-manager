"""
Key 选择路由服务

提供供应商 Key 的选择逻辑，支持：
- coding_plan 优先级
- Primary Key 软分配
- RPM 溢出机制
"""
import uuid
import json
from typing import Optional, Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus, KeyPlan
from services.rpm_tracker import get_rpm_tracker


class NoAvailableKeyError(Exception):
    """没有可用的 API Key"""
    pass


class RateLimitExceededError(Exception):
    """所有 Key 的 RPM 都已超限"""
    def __init__(self, provider_name: str, tried_keys: List[str]):
        self.provider_name = provider_name
        self.tried_keys = tried_keys
        super().__init__(
            f"All keys for provider '{provider_name}' have exceeded RPM limit"
        )


# Key 选择结果
class KeySelectionResult:
    """Key 选择结果"""
    def __init__(
        self,
        key: ProviderApiKey,
        key_source: str = "standard",  # "primary" | "overflow" | "standard"
        rpm_remaining: int = -1  # -1 表示无限制
    ):
        self.key = key
        self.key_source = key_source
        self.rpm_remaining = rpm_remaining

    def __repr__(self):
        return f"<KeySelectionResult key=...{self.key.key_suffix} source={self.key_source} remaining={self.rpm_remaining}>"


class KeySelector:
    """Key 选择器"""

    @staticmethod
    async def select_provider_key(
        provider: Provider,
        model_id: str,
        db: AsyncSession,
        user_id: Optional[uuid.UUID] = None
    ) -> ProviderApiKey:
        """
        为指定模型选择合适的供应商 Key（向后兼容版本）

        选择优先级：
        1. coding_plan Key 且 model_id 在其 plan_models 中
        2. standard Key（兜底）

        Args:
            provider: 供应商对象
            model_id: 模型 ID
            db: 数据库 session
            user_id: 用户 ID（可选，用于 primary key 分配）

        Returns:
            选中的 ProviderApiKey

        Raises:
            NoAvailableKeyError: 没有可用的 Key
        """
        result = await KeySelector.select_provider_key_with_source(
            provider, model_id, db, user_id
        )
        return result.key

    @staticmethod
    async def select_provider_key_with_source(
        provider: Provider,
        model_id: str,
        db: AsyncSession,
        user_id: Optional[uuid.UUID] = None
    ) -> KeySelectionResult:
        """
        为指定模型选择合适的供应商 Key，返回详细信息

        选择优先级：
        1. coding_plan Key 且 model_id 在其 plan_models 中
        2. Primary Key（用户绑定的 standard Key）
        3. Overflow 到其他 standard Key（当 Primary Key RPM 打满时）
        4. 第一个可用的 standard Key（兜底）

        Args:
            provider: 供应商对象
            model_id: 模型 ID
            db: 数据库 session
            user_id: 用户 ID（用于 primary key 分配）

        Returns:
            KeySelectionResult，包含 key、key_source 和 rpm_remaining

        Raises:
            NoAvailableKeyError: 没有可用的 Key
            RateLimitExceededError: 所有 Key 的 RPM 都已超限
        """
        rpm_tracker = get_rpm_tracker()

        # 查询所有可用的 Key
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.provider_id == provider.id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
                )
            ).order_by(ProviderApiKey.created_at)
        )
        all_keys = list(result.scalars().all())

        if not all_keys:
            raise NoAvailableKeyError(
                f"No active API key for provider '{provider.name}'"
            )

        # 分类 Key
        coding_plan_keys: List[ProviderApiKey] = []
        standard_keys: List[ProviderApiKey] = []

        for key in all_keys:
            if key.is_coding_plan:
                coding_plan_keys.append(key)
            else:
                standard_keys.append(key)

        # 优先级 1: 查找支持该模型的 coding_plan Key
        for key in coding_plan_keys:
            if key.supports_model(model_id):
                # coding_plan Key 不受 RPM 限制（假设供应商端限制）
                return KeySelectionResult(key=key, key_source="standard", rpm_remaining=-1)

        # 如果没有 standard Key，抛出异常
        if not standard_keys:
            raise NoAvailableKeyError(
                f"No available API key for model '{model_id}' in provider '{provider.name}'"
            )

        # 获取用户的 primary key 绑定
        primary_key_id = None
        if user_id:
            primary_key_id = await KeySelector._get_user_primary_key_id(
                user_id, provider.name, db
            )

        # 优先级 2: 尝试使用 Primary Key
        if primary_key_id:
            primary_key = next(
                (k for k in standard_keys if k.id == primary_key_id),
                None
            )
            if primary_key:
                allowed, _, rpm_limit = await rpm_tracker.check_and_consume(
                    primary_key.id, primary_key.rpm_limit
                )
                if allowed:
                    remaining = await rpm_tracker.get_remaining(
                        primary_key.id, primary_key.rpm_limit
                    )
                    return KeySelectionResult(
                        key=primary_key,
                        key_source="primary",
                        rpm_remaining=remaining
                    )
                # Primary Key RPM 打满，尝试 overflow

        # 优先级 3: Overflow 到其他 standard Key
        tried_keys = []
        for key in standard_keys:
            # 跳过已尝试的 primary key
            if primary_key_id and key.id == primary_key_id:
                tried_keys.append(f"...{key.key_suffix}")
                continue

            allowed, _, rpm_limit = await rpm_tracker.check_and_consume(
                key.id, key.rpm_limit
            )
            if allowed:
                remaining = await rpm_tracker.get_remaining(key.id, key.rpm_limit)
                return KeySelectionResult(
                    key=key,
                    key_source="overflow",
                    rpm_remaining=remaining
                )
            tried_keys.append(f"...{key.key_suffix}")

        # 所有 Key 都打满了
        raise RateLimitExceededError(
            provider_name=provider.name,
            tried_keys=tried_keys
        )

    @staticmethod
    async def _get_user_primary_key_id(
        user_id: uuid.UUID,
        provider_name: str,
        db: AsyncSession
    ) -> Optional[uuid.UUID]:
        """
        获取用户在指定供应商上的 Primary Key ID

        Args:
            user_id: 用户 ID
            provider_name: 供应商名称
            db: 数据库 session

        Returns:
            Primary Key ID，如果未绑定则返回 None
        """
        from models.user import User

        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user or not user.primary_provider_keys:
            return None

        try:
            key_id_str = user.primary_provider_keys.get(provider_name)
            if key_id_str:
                return uuid.UUID(key_id_str)
        except (TypeError, ValueError):
            pass

        return None

    @staticmethod
    async def get_any_active_key(
        provider: Provider,
        db: AsyncSession
    ) -> Optional[ProviderApiKey]:
        """
        获取供应商的任意一个活跃 Key（用于模型发现等场景）

        Args:
            provider: 供应商对象
            db: 数据库 session

        Returns:
            活跃的 ProviderApiKey，如果没有则返回 None
        """
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.provider_id == provider.id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
                )
            ).order_by(ProviderApiKey.created_at).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def has_standard_key(
        provider: Provider,
        db: AsyncSession
    ) -> bool:
        """
        检查供应商是否有 standard Key

        Args:
            provider: 供应商对象
            db: 数据库 session

        Returns:
            是否有 standard Key
        """
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.provider_id == provider.id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value,
                    ProviderApiKey.key_plan == KeyPlan.STANDARD.value
                )
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def count_standard_keys(
        provider: Provider,
        db: AsyncSession
    ) -> int:
        """
        统计供应商的 standard Key 数量

        Args:
            provider: 供应商对象
            db: 数据库 session

        Returns:
            standard Key 数量
        """
        from sqlalchemy import func

        result = await db.execute(
            select(func.count()).where(
                and_(
                    ProviderApiKey.provider_id == provider.id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value,
                    ProviderApiKey.key_plan == KeyPlan.STANDARD.value
                )
            )
        )
        return result.scalar() or 0


# 便捷函数
async def select_provider_key(
    provider: Provider,
    model_id: str,
    db: AsyncSession,
    user_id: Optional[uuid.UUID] = None
) -> ProviderApiKey:
    """
    为指定模型选择合适的供应商 Key

    这是 KeySelector.select_provider_key 的便捷包装

    Args:
        provider: 供应商对象
        model_id: 模型 ID
        db: 数据库 session
        user_id: 用户 ID（可选，用于 primary key 分配）

    Returns:
        选中的 ProviderApiKey

    Raises:
        NoAvailableKeyError: 没有可用的 Key
    """
    return await KeySelector.select_provider_key(provider, model_id, db, user_id)


async def select_provider_key_with_source(
    provider: Provider,
    model_id: str,
    db: AsyncSession,
    user_id: Optional[uuid.UUID] = None
) -> KeySelectionResult:
    """
    为指定模型选择合适的供应商 Key，返回详细信息

    这是 KeySelector.select_provider_key_with_source 的便捷包装

    Args:
        provider: 供应商对象
        model_id: 模型 ID
        db: 数据库 session
        user_id: 用户 ID（用于 primary key 分配）

    Returns:
        KeySelectionResult，包含 key、key_source 和 rpm_remaining

    Raises:
        NoAvailableKeyError: 没有可用的 Key
        RateLimitExceededError: 所有 Key 的 RPM 都已超限
    """
    return await KeySelector.select_provider_key_with_source(
        provider, model_id, db, user_id
    )
