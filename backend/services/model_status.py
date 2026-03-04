"""
模型状态服务

提供模型状态检查功能，包括废弃模型警告
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.model_catalog import ModelCatalog, ModelStatus


async def check_model_deprecation(model_id: str, db: AsyncSession) -> bool:
    """
    检查模型是否已废弃

    Args:
        model_id: 模型 ID（可能包含变体，需要标准化）
        db: 数据库会话

    Returns:
        True 如果模型已废弃，否则 False
        未知模型返回 False（不阻塞请求）
    """
    # 标准化模型 ID（去除变体）
    from services.model_variants import get_model_variants_service
    variants_service = get_model_variants_service()
    normalized_model_id = variants_service.normalize_model_string(model_id)

    result = await db.execute(
        select(ModelCatalog).where(ModelCatalog.model_id == normalized_model_id)
    )
    model = result.scalar_one_or_none()

    if model is None:
        # 未知模型不阻塞
        return False

    return model.status == ModelStatus.DEPRECATED


async def get_model_status(model_id: str, db: AsyncSession) -> Optional[str]:
    """
    获取模型状态

    Args:
        model_id: 模型 ID
        db: 数据库会话

    Returns:
        模型状态字符串，如果模型不存在则返回 None
    """
    # 标准化模型 ID
    from services.model_variants import get_model_variants_service
    variants_service = get_model_variants_service()
    normalized_model_id = variants_service.normalize_model_string(model_id)

    result = await db.execute(
        select(ModelCatalog.status).where(ModelCatalog.model_id == normalized_model_id)
    )
    status = result.scalar_one_or_none()

    return status
