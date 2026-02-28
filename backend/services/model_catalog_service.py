"""
模型目录服务

封装对 model_catalog 的常用查询和操作
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from models.model_catalog import ModelCatalog, ModelStatus, ModelSource
from models.provider import Provider


class ModelCatalogService:
    """模型目录服务"""

    @staticmethod
    async def get_active_models(db: AsyncSession) -> List[ModelCatalog]:
        """
        获取所有已启用的模型

        Args:
            db: 数据库 session

        Returns:
            已启用的模型列表
        """
        result = await db.execute(
            select(ModelCatalog)
            .where(ModelCatalog.status == ModelStatus.ACTIVE)
            .order_by(ModelCatalog.model_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_provider_models(
        db: AsyncSession,
        provider_id: uuid.UUID
    ) -> List[ModelCatalog]:
        """
        获取指定供应商下的所有模型

        Args:
            db: 数据库 session
            provider_id: 供应商 ID

        Returns:
            模型列表
        """
        result = await db.execute(
            select(ModelCatalog)
            .where(ModelCatalog.provider_id == provider_id)
            .order_by(ModelCatalog.model_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_model_by_id(
        db: AsyncSession,
        model_id: str
    ) -> Optional[ModelCatalog]:
        """
        根据 model_id 获取模型

        Args:
            db: 数据库 session
            model_id: 模型 ID

        Returns:
            模型对象，如果不存在则返回 None
        """
        result = await db.execute(
            select(ModelCatalog).where(ModelCatalog.model_id == model_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_model_by_pk(
        db: AsyncSession,
        pk: uuid.UUID
    ) -> Optional[ModelCatalog]:
        """
        根据主键获取模型

        Args:
            db: 数据库 session
            pk: 模型主键 ID

        Returns:
            模型对象，如果不存在则返回 None
        """
        result = await db.execute(
            select(ModelCatalog).where(ModelCatalog.id == pk)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_model_status(
        db: AsyncSession,
        model_id: str,
        status: str
    ) -> Optional[ModelCatalog]:
        """
        更新模型状态

        Args:
            db: 数据库 session
            model_id: 模型 ID
            status: 新状态

        Returns:
            更新后的模型对象，如果不存在则返回 None
        """
        model = await ModelCatalogService.get_model_by_id(db, model_id)
        if not model:
            return None

        model.status = status
        model.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def update_model_pricing(
        db: AsyncSession,
        model_id: str,
        input_price: Decimal,
        output_price: Decimal,
        changed_by_id: Optional[uuid.UUID] = None,
        reason: Optional[str] = None
    ) -> Optional[ModelCatalog]:
        """
        更新模型定价

        Args:
            db: 数据库 session
            model_id: 模型 ID
            input_price: 新的输入单价
            output_price: 新的输出单价
            changed_by_id: 操作者 ID（用于历史记录，Batch 3 实现）
            reason: 变更原因（用于历史记录，Batch 3 实现）

        Returns:
            更新后的模型对象，如果不存在则返回 None
        """
        model = await ModelCatalogService.get_model_by_id(db, model_id)
        if not model:
            return None

        # TODO: Batch 3 实现后，在此处写入 model_pricing_history 记录
        # old_input_price = model.input_price
        # old_output_price = model.output_price

        model.input_price = input_price
        model.output_price = output_price
        model.is_pricing_confirmed = True
        model.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def create_model(
        db: AsyncSession,
        model_id: str,
        display_name: str,
        provider_id: uuid.UUID,
        input_price: Decimal = Decimal("0"),
        output_price: Decimal = Decimal("0"),
        context_window: Optional[int] = None,
        max_output: Optional[int] = None,
        supports_vision: bool = False,
        supports_tools: bool = True,
        status: str = ModelStatus.PENDING,
        **kwargs
    ) -> ModelCatalog:
        """
        创建新模型

        Args:
            db: 数据库 session
            model_id: 模型 ID
            display_name: 显示名称
            provider_id: 供应商 ID
            input_price: 输入单价
            output_price: 输出单价
            context_window: 上下文窗口大小
            max_output: 最大输出长度
            supports_vision: 是否支持视觉
            supports_tools: 是否支持工具调用
            status: 初始状态
            **kwargs: 其他参数

        Returns:
            创建的模型对象
        """
        model = ModelCatalog(
            model_id=model_id,
            display_name=display_name,
            provider_id=provider_id,
            input_price=input_price,
            output_price=output_price,
            context_window=context_window,
            max_output=max_output,
            supports_vision=supports_vision,
            supports_tools=supports_tools,
            status=status,
            source=kwargs.get("source", ModelSource.MANUAL),
            is_pricing_confirmed=kwargs.get("is_pricing_confirmed", input_price > 0),
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model

    @staticmethod
    async def batch_activate_priced_models(
        db: AsyncSession,
        provider_id: uuid.UUID
    ) -> int:
        """
        批量启用已确认定价的待审核模型

        Args:
            db: 数据库 session
            provider_id: 供应商 ID

        Returns:
            启用的模型数量
        """
        # 查询所有已确认定价但状态为 pending 的模型
        result = await db.execute(
            select(ModelCatalog).where(
                and_(
                    ModelCatalog.provider_id == provider_id,
                    ModelCatalog.status == ModelStatus.PENDING,
                    ModelCatalog.is_pricing_confirmed == True,
                    ModelCatalog.input_price > 0
                )
            )
        )
        models = result.scalars().all()

        count = 0
        for model in models:
            model.status = ModelStatus.ACTIVE
            model.updated_at = datetime.utcnow()
            count += 1

        await db.commit()
        return count

    @staticmethod
    async def get_provider_models_summary(
        db: AsyncSession,
        provider_id: uuid.UUID
    ) -> dict:
        """
        获取供应商模型统计摘要

        Args:
            db: 数据库 session
            provider_id: 供应商 ID

        Returns:
            统计摘要字典
        """
        # 总数
        total_result = await db.execute(
            select(func.count()).where(ModelCatalog.provider_id == provider_id)
        )
        total = total_result.scalar() or 0

        # 各状态数量
        active_result = await db.execute(
            select(func.count()).where(
                and_(
                    ModelCatalog.provider_id == provider_id,
                    ModelCatalog.status == ModelStatus.ACTIVE
                )
            )
        )
        active = active_result.scalar() or 0

        pending_result = await db.execute(
            select(func.count()).where(
                and_(
                    ModelCatalog.provider_id == provider_id,
                    ModelCatalog.status == ModelStatus.PENDING
                )
            )
        )
        pending = pending_result.scalar() or 0

        inactive_result = await db.execute(
            select(func.count()).where(
                and_(
                    ModelCatalog.provider_id == provider_id,
                    ModelCatalog.status == ModelStatus.INACTIVE
                )
            )
        )
        inactive = inactive_result.scalar() or 0

        # 待确认定价数量
        pricing_pending_result = await db.execute(
            select(func.count()).where(
                and_(
                    ModelCatalog.provider_id == provider_id,
                    ModelCatalog.is_pricing_confirmed == False
                )
            )
        )
        pricing_pending = pricing_pending_result.scalar() or 0

        return {
            "total": total,
            "active": active,
            "pending": pending,
            "inactive": inactive,
            "pricing_pending": pricing_pending
        }
