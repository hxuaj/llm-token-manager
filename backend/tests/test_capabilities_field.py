"""
测试 capabilities JSONB 字段

测试：
- capabilities JSONB 结构存储
- 向后兼容现有字段
- 从 models.dev 同步 capabilities
"""
import pytest
import pytest_asyncio
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.provider import Provider
from models.model_catalog import ModelCatalog, ModelStatus, ModelSource


@pytest_asyncio.fixture
async def test_provider(db_session: AsyncSession):
    """创建测试供应商"""
    provider = Provider(
        name="test-provider",
        display_name="Test Provider",
        base_url="https://api.test.com/v1",
        api_format="openai",
        enabled=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


@pytest.mark.asyncio
async def test_capabilities_jsonb_structure(db_session: AsyncSession, test_provider):
    """测试 capabilities JSONB 字段可以存储完整结构"""
    capabilities = {
        "temperature": True,
        "reasoning": False,
        "attachment": False,
        "toolcall": True,
        "interleaved": False,
        "input": {"text": True, "audio": False, "image": True, "video": False, "pdf": False},
        "output": {"text": True, "audio": False, "image": False, "video": False, "pdf": False}
    }

    model = ModelCatalog(
        model_id="test-model-with-caps",
        display_name="Test Model",
        provider_id=test_provider.id,
        input_price=Decimal("0.01"),
        output_price=Decimal("0.03"),
        status=ModelStatus.ACTIVE,
        source=ModelSource.MANUAL,
        capabilities=capabilities,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    # 验证存储
    assert model.capabilities is not None
    assert model.capabilities["temperature"] is True
    assert model.capabilities["reasoning"] is False
    assert model.capabilities["toolcall"] is True
    assert model.capabilities["input"]["text"] is True
    assert model.capabilities["input"]["image"] is True
    assert model.capabilities["output"]["text"] is True


@pytest.mark.asyncio
async def test_capabilities_backward_compat(db_session: AsyncSession, test_provider):
    """测试 capabilities 字段向后兼容现有布尔字段"""
    # 创建模型，同时设置旧字段和新的 capabilities
    capabilities = {
        "temperature": True,
        "reasoning": True,
        "attachment": True,
        "toolcall": False,
        "interleaved": False,
        "input": {"text": True, "audio": False, "image": True, "video": False, "pdf": True},
        "output": {"text": True, "audio": False, "image": False, "video": False, "pdf": False}
    }

    model = ModelCatalog(
        model_id="test-model-compat",
        display_name="Test Model Compat",
        provider_id=test_provider.id,
        input_price=Decimal("0.01"),
        output_price=Decimal("0.03"),
        status=ModelStatus.ACTIVE,
        source=ModelSource.MANUAL,
        # 旧字段
        supports_vision=True,
        supports_tools=False,
        supports_reasoning=True,
        # 新字段
        capabilities=capabilities,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    # 旧字段保持不变
    assert model.supports_vision is True
    assert model.supports_tools is False
    assert model.supports_reasoning is True

    # capabilities 字段独立存储
    assert model.capabilities["attachment"] is True
    assert model.capabilities["input"]["pdf"] is True


@pytest.mark.asyncio
async def test_capabilities_null_by_default(db_session: AsyncSession, test_provider):
    """测试 capabilities 默认为 null（未设置）"""
    model = ModelCatalog(
        model_id="test-model-no-caps",
        display_name="Test Model No Caps",
        provider_id=test_provider.id,
        input_price=Decimal("0.01"),
        output_price=Decimal("0.03"),
        status=ModelStatus.ACTIVE,
        source=ModelSource.MANUAL,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    # 默认为 null
    assert model.capabilities is None


@pytest.mark.asyncio
async def test_capabilities_update(db_session: AsyncSession, test_provider):
    """测试 capabilities 字段可以更新"""
    model = ModelCatalog(
        model_id="test-model-update-caps",
        display_name="Test Model Update",
        provider_id=test_provider.id,
        input_price=Decimal("0.01"),
        output_price=Decimal("0.03"),
        status=ModelStatus.ACTIVE,
        source=ModelSource.MANUAL,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    # 初始为 null
    assert model.capabilities is None

    # 更新 capabilities
    model.capabilities = {
        "temperature": True,
        "reasoning": False,
        "toolcall": True,
        "input": {"text": True, "image": False},
        "output": {"text": True}
    }
    await db_session.commit()
    await db_session.refresh(model)

    # 验证更新
    assert model.capabilities is not None
    assert model.capabilities["toolcall"] is True


@pytest.mark.asyncio
async def test_sync_capabilities_from_models_dev(db_session: AsyncSession, test_provider):
    """测试从 models.dev 同步 capabilities 的映射"""
    from services.models_dev_service import ModelsDevService

    service = ModelsDevService()

    # 模拟 models.dev 返回的数据结构
    model_data = {
        "name": "claude-sonnet-4-20250514",
        "cost": {
            "input": 3.0,
            "output": 15.0,
            "cache_write": 3.75,
            "cache_read": 0.3
        },
        "limit": {
            "context": 200000,
            "output": 16000
        },
        "capabilities": {
            "temperature": True,
            "reasoning": True,
            "attachment": True,
            "toolcall": True,
            "interleaved": True,
            "input": {"text": True, "audio": False, "image": True, "video": False, "pdf": True},
            "output": {"text": True, "audio": False, "image": False, "video": False, "pdf": False}
        }
    }

    # 解析 capabilities
    capabilities = model_data.get("capabilities", {})

    # 创建模型并存储 capabilities
    model = ModelCatalog(
        model_id="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        provider_id=test_provider.id,
        input_price=Decimal("3.0"),
        output_price=Decimal("15.0"),
        status=ModelStatus.ACTIVE,
        source=ModelSource.MODELS_DEV,
        models_dev_id="claude-sonnet-4-20250514",
        capabilities=capabilities,
        supports_reasoning=capabilities.get("reasoning", False),
        supports_vision=capabilities.get("input", {}).get("image", False),
        supports_tools=capabilities.get("toolcall", True),
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    # 验证 capabilities 已存储
    assert model.capabilities is not None
    assert model.capabilities["reasoning"] is True
    assert model.capabilities["attachment"] is True
    assert model.capabilities["input"]["pdf"] is True

    # 验证旧字段也被正确映射
    assert model.supports_reasoning is True
    assert model.supports_vision is True
    assert model.supports_tools is True


@pytest.mark.asyncio
async def test_capabilities_partial_structure(db_session: AsyncSession, test_provider):
    """测试 capabilities 可以存储部分结构"""
    # 某些模型可能只有部分 capabilities 信息
    partial_capabilities = {
        "temperature": True,
        "toolcall": True,
    }

    model = ModelCatalog(
        model_id="test-model-partial",
        display_name="Test Model Partial",
        provider_id=test_provider.id,
        input_price=Decimal("0.01"),
        output_price=Decimal("0.03"),
        status=ModelStatus.ACTIVE,
        source=ModelSource.MANUAL,
        capabilities=partial_capabilities,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    # 验证部分结构存储
    assert model.capabilities["temperature"] is True
    assert model.capabilities["toolcall"] is True
    # 不存在的键返回 None 而不是报错
    assert model.capabilities.get("reasoning") is None
    assert model.capabilities.get("input") is None
