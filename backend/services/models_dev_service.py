"""
models.dev 数据同步服务

作为模型元数据的单一真相来源（SSOT），
定期同步到本地数据库，支持本地覆盖。

功能：
- 从 models.dev 获取供应商和模型元数据
- 缓存机制避免频繁请求
- 深度合并配置（本地覆盖优先）
- 同步到数据库时保留本地修改
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.provider import Provider
from models.model_catalog import ModelCatalog, ModelSource, ModelStatus


logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """同步结果"""
    success: bool
    synced_at: datetime
    providers_synced: int = 0
    models_synced: int = 0
    new_models: int = 0
    updated_models: int = 0
    preserved_local: int = 0
    conflicts: list = field(default_factory=list)
    error: Optional[str] = None


class ModelsDevService:
    """
    models.dev 数据同步服务

    从 models.dev 获取供应商和模型元数据，
    并同步到本地数据库。
    """

    MODELS_DEV_URL = "https://models.dev/api.json"
    SYNC_INTERVAL = timedelta(hours=24)  # 缓存过期时间

    def __init__(self):
        self._cache: Optional[dict] = None
        self._cache_expires: Optional[datetime] = None

    async def fetch_all_data(self, force_refresh: bool = False) -> dict:
        """
        从 models.dev 获取所有供应商和模型数据

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            {
                "openai": {
                    "id": "openai",
                    "name": "OpenAI",
                    "api": "https://api.openai.com/v1",
                    "models": {
                        "gpt-4o": { ... },
                        ...
                    }
                },
                ...
            }
        """
        now = datetime.utcnow()

        # 检查缓存
        if not force_refresh and self._cache and self._cache_expires and self._cache_expires > now:
            return self._cache

        # 从远程获取
        data = await self._fetch_from_remote()

        # 更新缓存
        self._cache = data
        self._cache_expires = now + self.SYNC_INTERVAL

        return data

    async def _fetch_from_remote(self) -> dict:
        """
        从 models.dev 获取数据（内部方法）

        Returns:
            原始 JSON 数据
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.MODELS_DEV_URL)
            response.raise_for_status()
            return response.json()

    async def get_provider(self, provider_id: str) -> Optional[dict]:
        """
        获取单个供应商信息

        Args:
            provider_id: 供应商 ID

        Returns:
            供应商数据，不存在则返回 None
        """
        data = await self.fetch_all_data()
        return data.get(provider_id)

    async def get_model(self, provider_id: str, model_id: str) -> Optional[dict]:
        """
        获取单个模型信息

        Args:
            provider_id: 供应商 ID
            model_id: 模型 ID

        Returns:
            模型数据，不存在则返回 None
        """
        provider = await self.get_provider(provider_id)
        if provider:
            return provider.get("models", {}).get(model_id)
        return None

    async def sync_to_database(
        self,
        db: AsyncSession,
        provider_id: Optional[str] = None,
        force_refresh: bool = False
    ) -> SyncResult:
        """
        同步 models.dev 数据到数据库

        Args:
            db: 数据库会话
            provider_id: 指定供应商 ID，None 表示同步全部
            force_refresh: 是否强制刷新缓存

        Returns:
            SyncResult: 同步结果统计
        """
        result = SyncResult(
            success=False,
            synced_at=datetime.utcnow()
        )

        try:
            data = await self.fetch_all_data(force_refresh)

            # 确定要同步的供应商
            providers_to_sync = [provider_id] if provider_id else list(data.keys())

            for pid in providers_to_sync:
                if pid not in data:
                    continue

                provider_data = data[pid]

                # 同步供应商
                await self._sync_provider(db, pid, provider_data, result)
                result.providers_synced += 1

                # Flush 以确保供应商在数据库中可见
                await db.flush()

                # 同步模型
                for model_id, model_data in provider_data.get("models", {}).items():
                    sync_status = await self._sync_model(
                        db, pid, model_id, model_data, result
                    )
                    result.models_synced += 1
                    if sync_status == "new":
                        result.new_models += 1
                    elif sync_status == "updated":
                        result.updated_models += 1

            await db.commit()
            result.success = True

        except Exception as e:
            logger.error(f"Failed to sync models.dev data: {e}")
            result.error = str(e)

        return result

    async def _sync_provider(
        self,
        db: AsyncSession,
        models_dev_id: str,
        provider_data: dict,
        result: SyncResult
    ):
        """
        同步单个供应商

        如果数据库中已有该供应商，更新基本信息但保留 local_overrides
        """
        # 查找已有供应商
        existing = await db.execute(
            select(Provider).where(Provider.models_dev_id == models_dev_id)
        )
        provider = existing.scalar_one_or_none()

        if provider:
            # 更新已有供应商，但保留本地覆盖
            # 只更新未被本地覆盖的字段
            provider.last_synced_at = datetime.utcnow()
            # 如果 display_name 未被覆盖，更新它
            if "display_name" not in (provider.local_overrides or {}):
                provider.display_name = provider_data.get("name", provider.name)
        else:
            # 创建新供应商
            provider = Provider(
                name=models_dev_id,
                display_name=provider_data.get("name", models_dev_id),
                base_url=provider_data.get("api", ""),
                api_format="openai",  # 默认 OpenAI 格式
                source=ModelSource.AUTO_DISCOVERED,
                models_dev_id=models_dev_id,
                local_overrides={},
                last_synced_at=datetime.utcnow()
            )
            db.add(provider)

    async def _sync_model(
        self,
        db: AsyncSession,
        provider_models_dev_id: str,
        model_id: str,
        model_data: dict,
        result: SyncResult
    ) -> str:
        """
        同步单个模型

        Args:
            db: 数据库会话
            provider_models_dev_id: 供应商的 models.dev ID
            model_id: 模型 ID
            model_data: 模型数据
            result: 同步结果（用于记录冲突）

        Returns:
            "new" | "updated" | "preserved"
        """
        # 查找供应商
        provider_result = await db.execute(
            select(Provider).where(Provider.models_dev_id == provider_models_dev_id)
        )
        provider = provider_result.scalar_one_or_none()

        if not provider:
            return "preserved"

        # 查找已有模型
        existing = await db.execute(
            select(ModelCatalog).where(ModelCatalog.model_id == model_id)
        )
        model = existing.scalar_one_or_none()

        # 解析 models.dev 数据
        cost = model_data.get("cost", {})
        limit = model_data.get("limit", {})

        # 计算价格（models.dev 使用 per million tokens）
        input_price = self._parse_cost(cost.get("input", 0))
        output_price = self._parse_cost(cost.get("output", 0))
        cache_read_price = self._parse_cost(cost.get("cache_read")) if cost.get("cache_read") else None
        cache_write_price = self._parse_cost(cost.get("cache_write")) if cost.get("cache_write") else None

        # 能力信息
        capabilities = model_data.get("capabilities", {})

        if model:
            # 更新已有模型，保留本地覆盖
            base_config = {
                "display_name": model_data.get("name", model_id),
                "cost": cost,
                "limit": limit,
                "capabilities": capabilities
            }

            # 记录是否需要更新
            needs_update = False

            # 更新 base_config
            model.base_config = base_config
            model.last_synced_at = datetime.utcnow()

            # 只更新未被本地覆盖的字段
            local_overrides = model.local_overrides or {}

            if "display_name" not in local_overrides:
                new_name = model_data.get("name", model_id)
                if model.display_name != new_name:
                    model.display_name = new_name
                    needs_update = True

            if "input_price" not in local_overrides:
                if model.input_price != input_price:
                    model.input_price = input_price
                    needs_update = True

            if "output_price" not in local_overrides:
                if model.output_price != output_price:
                    model.output_price = output_price
                    needs_update = True

            # 缓存价格可选
            if cache_read_price is not None and "cache_read_price" not in local_overrides:
                model.cache_read_price = cache_read_price
            if cache_write_price is not None and "cache_write_price" not in local_overrides:
                model.cache_write_price = cache_write_price

            # 上下文窗口
            context_window = limit.get("context")
            if context_window and "context_window" not in local_overrides:
                if model.context_window != context_window:
                    model.context_window = context_window
                    needs_update = True

            # 更新 capabilities 字段
            if capabilities and "capabilities" not in local_overrides:
                model.capabilities = capabilities
                # 同时更新旧的能力字段以保持兼容
                if capabilities.get("reasoning") is not None and "supports_reasoning" not in local_overrides:
                    model.supports_reasoning = capabilities.get("reasoning", False)
                if capabilities.get("input", {}).get("image") is not None and "supports_vision" not in local_overrides:
                    model.supports_vision = capabilities.get("input", {}).get("image", False)
                if capabilities.get("toolcall") is not None and "supports_tools" not in local_overrides:
                    model.supports_tools = capabilities.get("toolcall", True)

            # 检测冲突：本地值与远程值不同
            if "input_price" in local_overrides:
                remote_input = input_price
                if local_overrides["input_price"] != remote_input:
                    result.conflicts.append({
                        "model_id": model_id,
                        "field": "input_price",
                        "local_value": float(local_overrides["input_price"]),
                        "remote_value": float(remote_input),
                        "resolution": "preserved_local"
                    })
                    result.preserved_local += 1

            return "updated" if needs_update else "preserved"

        else:
            # 创建新模型
            model = ModelCatalog(
                model_id=model_id,
                display_name=model_data.get("name", model_id),
                provider_id=provider.id,
                input_price=input_price,
                output_price=output_price,
                cache_read_price=cache_read_price,
                cache_write_price=cache_write_price,
                context_window=limit.get("context"),
                max_output=limit.get("output"),
                supports_vision=capabilities.get("input", {}).get("image", capabilities.get("vision", False)),
                supports_tools=capabilities.get("toolcall", capabilities.get("tools", True)),
                supports_streaming=True,
                supports_reasoning=capabilities.get("reasoning", False),
                capabilities=capabilities if capabilities else None,
                status=ModelStatus.PENDING,
                source=ModelSource.AUTO_DISCOVERED,
                models_dev_id=model_id,
                base_config={
                    "display_name": model_data.get("name", model_id),
                    "cost": cost,
                    "limit": limit,
                    "capabilities": capabilities
                },
                local_overrides={},
                last_synced_at=datetime.utcnow()
            )
            db.add(model)
            return "new"

    def _parse_cost(self, value: Any) -> float:
        """
        解析价格值

        models.dev 可能返回数字或字典 {"prompt": x, "completion": y}
        """
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            # 某些格式可能使用 prompt/completion
            return float(value.get("prompt", value.get("input", 0)))
        return 0.0

    @staticmethod
    def merge_configs(base: dict, override: dict) -> dict:
        """
        深度合并配置

        规则：
        - override 中的字段覆盖 base 中的同名字段
        - 嵌套对象递归合并
        - 列表类型：override 替换 base（不合并）
        - None 值表示删除字段

        Args:
            base: models.dev 的基础配置
            override: 本地覆盖配置

        Returns:
            合并后的有效配置
        """
        result = deepcopy(base)

        for key, value in override.items():
            if value is None:
                # None 表示删除该字段
                result.pop(key, None)
            elif (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # 递归合并嵌套对象
                result[key] = ModelsDevService.merge_configs(result[key], value)
            else:
                # 直接覆盖（包括列表类型）
                result[key] = value

        return result


# 单例实例（可选）
_models_dev_service: Optional[ModelsDevService] = None


def get_models_dev_service() -> ModelsDevService:
    """获取 models.dev 服务实例"""
    global _models_dev_service
    if _models_dev_service is None:
        _models_dev_service = ModelsDevService()
    return _models_dev_service
