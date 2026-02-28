"""
Key 选择路由服务

提供供应商 Key 的选择逻辑，支持 coding_plan 优先级
"""
from typing import Optional, Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus, KeyPlan


class NoAvailableKeyError(Exception):
    """没有可用的 API Key"""
    pass


class KeySelector:
    """Key 选择器"""

    @staticmethod
    async def select_provider_key(
        provider: Provider,
        model_id: str,
        db: AsyncSession
    ) -> ProviderApiKey:
        """
        为指定模型选择合适的供应商 Key

        选择优先级：
        1. coding_plan Key 且 model_id 在其 plan_models 中
        2. standard Key（兜底）

        Args:
            provider: 供应商对象
            model_id: 模型 ID
            db: 数据库 session

        Returns:
            选中的 ProviderApiKey

        Raises:
            NoAvailableKeyError: 没有可用的 Key
        """
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
                return key

        # 优先级 2: 使用 standard Key（兜底）
        if standard_keys:
            # TODO: 在此处可以添加 RPM 限流 + 轮转逻辑
            # 目前简单返回第一个
            return standard_keys[0]

        # 没有可用的 Key
        raise NoAvailableKeyError(
            f"No available API key for model '{model_id}' in provider '{provider.name}'"
        )

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
    db: AsyncSession
) -> ProviderApiKey:
    """
    为指定模型选择合适的供应商 Key

    这是 KeySelector.select_provider_key 的便捷包装

    Args:
        provider: 供应商对象
        model_id: 模型 ID
        db: 数据库 session

    Returns:
        选中的 ProviderApiKey

    Raises:
        NoAvailableKeyError: 没有可用的 Key
    """
    return await KeySelector.select_provider_key(provider, model_id, db)
