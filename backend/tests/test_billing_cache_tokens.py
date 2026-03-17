"""
缓存 Token 计费测试

测试用例：
- 使用 ModelCatalog 计算基础费用
- 计算 cache_read_tokens 费用
- 计算 cache_write_tokens 费用
- 无缓存定价时的处理
- 混合计费（基础 + 缓存）
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import uuid


class TestCacheTokenBilling:
    """测试缓存 Token 计费"""

    @pytest.mark.asyncio
    async def test_calculate_cost_with_cache_read_tokens(self, client, db_session):
        """计算包含 cache_read_tokens 的费用"""
        from services.billing import calculate_cost
        from models.model_catalog import ModelCatalog, ModelStatus
        from models.provider import Provider

        # 创建供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_format="anthropic",
            enabled=True
        )
        db_session.add(provider)
        await db_session.flush()

        # 创建模型定价（包含缓存定价）
        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="claude-3-5-sonnet-20241022",
            display_name="Claude 3.5 Sonnet",
            provider_id=provider.id,
            input_price=Decimal("3.00"),      # $3 per 1M tokens
            output_price=Decimal("15.00"),    # $15 per 1M tokens
            cache_read_price=Decimal("0.30"), # $0.30 per 1M tokens
            cache_write_price=Decimal("3.75"), # $3.75 per 1M tokens
            status=ModelStatus.ACTIVE
        )
        db_session.add(model)
        await db_session.commit()

        # 计算费用
        cost = await calculate_cost(
            model="claude-3-5-sonnet-20241022",
            prompt_tokens=1000,
            completion_tokens=500,
            db=db_session,
            cache_read_tokens=2000,
            cache_write_tokens=0
        )

        # 验证费用计算
        # input_cost = 1000 * 3.00 / 1M = 0.003
        # output_cost = 500 * 15.00 / 1M = 0.0075
        # cache_read_cost = 2000 * 0.30 / 1M = 0.0006
        # total = 0.003 + 0.0075 + 0.0006 = 0.0111
        assert cost == Decimal("0.0111")

    @pytest.mark.asyncio
    async def test_calculate_cost_with_cache_write_tokens(self, client, db_session):
        """计算包含 cache_write_tokens 的费用"""
        from services.billing import calculate_cost
        from models.model_catalog import ModelCatalog, ModelStatus
        from models.provider import Provider

        # 创建供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_format="anthropic",
            enabled=True
        )
        db_session.add(provider)
        await db_session.flush()

        # 创建模型定价
        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="claude-3-5-sonnet-20241022",
            display_name="Claude 3.5 Sonnet",
            provider_id=provider.id,
            input_price=Decimal("3.00"),
            output_price=Decimal("15.00"),
            cache_read_price=Decimal("0.30"),
            cache_write_price=Decimal("3.75"),
            status=ModelStatus.ACTIVE
        )
        db_session.add(model)
        await db_session.commit()

        # 计算费用
        cost = await calculate_cost(
            model="claude-3-5-sonnet-20241022",
            prompt_tokens=1000,
            completion_tokens=500,
            db=db_session,
            cache_write_tokens=1000
        )

        # 验证费用计算
        # input_cost = 1000 * 3.00 / 1M = 0.003
        # output_cost = 500 * 15.00 / 1M = 0.0075
        # cache_write_cost = 1000 * 3.75 / 1M = 0.00375
        # total = 0.003 + 0.0075 + 0.00375 = 0.01425
        assert cost == Decimal("0.01425")

    @pytest.mark.asyncio
    async def test_calculate_cost_with_both_cache_tokens(self, client, db_session):
        """计算同时包含 cache_read 和 cache_write tokens 的费用"""
        from services.billing import calculate_cost
        from models.model_catalog import ModelCatalog, ModelStatus
        from models.provider import Provider

        # 创建供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_format="anthropic",
            enabled=True
        )
        db_session.add(provider)
        await db_session.flush()

        # 创建模型定价
        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="claude-3-5-sonnet-20241022",
            display_name="Claude 3.5 Sonnet",
            provider_id=provider.id,
            input_price=Decimal("3.00"),
            output_price=Decimal("15.00"),
            cache_read_price=Decimal("0.30"),
            cache_write_price=Decimal("3.75"),
            status=ModelStatus.ACTIVE
        )
        db_session.add(model)
        await db_session.commit()

        # 计算费用
        cost = await calculate_cost(
            model="claude-3-5-sonnet-20241022",
            prompt_tokens=1000,
            completion_tokens=500,
            db=db_session,
            cache_read_tokens=2000,
            cache_write_tokens=1000
        )

        # 验证费用计算
        # input_cost = 1000 * 3.00 / 1M = 0.003
        # output_cost = 500 * 15.00 / 1M = 0.0075
        # cache_read_cost = 2000 * 0.30 / 1M = 0.0006
        # cache_write_cost = 1000 * 3.75 / 1M = 0.00375
        # total = 0.003 + 0.0075 + 0.0006 + 0.00375 = 0.01485
        assert cost == Decimal("0.01485")

    @pytest.mark.asyncio
    async def test_calculate_cost_without_cache_pricing(self, client, db_session):
        """模型没有缓存定价时只计算基础费用"""
        from services.billing import calculate_cost
        from models.model_catalog import ModelCatalog, ModelStatus
        from models.provider import Provider

        # 创建供应商
        provider = Provider(
            id=uuid.uuid4(),
            name="openai",
            base_url="https://api.openai.com/v1",
            api_format="openai",
            enabled=True
        )
        db_session.add(provider)
        await db_session.flush()

        # 创建模型定价（无缓存定价）
        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="gpt-4o",
            display_name="GPT-4o",
            provider_id=provider.id,
            input_price=Decimal("2.50"),
            output_price=Decimal("10.00"),
            cache_read_price=None,  # 无缓存定价
            cache_write_price=None,
            status=ModelStatus.ACTIVE
        )
        db_session.add(model)
        await db_session.commit()

        # 计算费用（传入缓存 tokens 但无缓存定价）
        cost = await calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            db=db_session,
            cache_read_tokens=2000,
            cache_write_tokens=1000
        )

        # 验证只计算基础费用
        # input_cost = 1000 * 2.50 / 1M = 0.0025
        # output_cost = 500 * 10.00 / 1M = 0.005
        # total = 0.0075 (缓存不计费)
        assert cost == Decimal("0.0075")

    @pytest.mark.asyncio
    async def test_log_request_with_cache_tokens(self, client, db_session, test_user, user_api_key):
        """记录包含缓存 tokens 的请求日志"""
        from services.billing import log_request
        from models.request_log import RequestLog
        from models.model_catalog import ModelCatalog, ModelStatus
        from models.provider import Provider

        # user_api_key 是 (key_object, raw_key_string) 元组
        key_obj, _ = user_api_key

        # 创建供应商和模型
        provider = Provider(
            id=uuid.uuid4(),
            name="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_format="anthropic",
            enabled=True
        )
        db_session.add(provider)
        await db_session.flush()

        model = ModelCatalog(
            id=uuid.uuid4(),
            model_id="claude-3-5-sonnet-20241022",
            display_name="Claude 3.5 Sonnet",
            provider_id=provider.id,
            input_price=Decimal("3.00"),
            output_price=Decimal("15.00"),
            cache_read_price=Decimal("0.30"),
            cache_write_price=Decimal("3.75"),
            status=ModelStatus.ACTIVE
        )
        db_session.add(model)
        await db_session.commit()

        # 记录请求
        log = await log_request(
            user_id=test_user.id,
            key_id=key_obj.id,
            model="claude-3-5-sonnet-20241022",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=200,
            provider_id=provider.id,
            db=db_session,
            cache_read_tokens=2000,
            cache_write_tokens=1000
        )

        # 验证日志记录
        assert log.cache_read_tokens == 2000
        assert log.cache_write_tokens == 1000
        assert log.cost_usd == Decimal("0.01485")

    @pytest.mark.asyncio
    async def test_calculate_cost_no_pricing_info(self, client, db_session):
        """找不到任何定价信息时返回 0"""
        from services.billing import calculate_cost

        cost = await calculate_cost(
            model="unknown-model",
            prompt_tokens=1000,
            completion_tokens=500,
            db=db_session
        )

        assert cost == Decimal("0")
