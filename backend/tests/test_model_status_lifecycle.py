"""
测试模型状态生命周期和废弃警告

测试：
- 废弃模型检查服务
- 各种状态的模型返回正确的废弃标记
"""
import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from models.provider import Provider
from models.model_catalog import ModelCatalog, ModelStatus, ModelSource
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus


@pytest_asyncio.fixture
async def test_provider_with_key(db_session: AsyncSession):
    """创建测试供应商和 API Key"""
    from services.encryption import encrypt

    provider = Provider(
        name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_format="openai",
        enabled=True,
    )
    db_session.add(provider)
    await db_session.flush()

    encrypted_key = encrypt("sk-test-key-12345")
    api_key = ProviderApiKey(
        provider_id=provider.id,
        encrypted_key=encrypted_key,
        key_suffix="12345",
        status=ProviderKeyStatus.ACTIVE.value,
        key_plan="standard",
    )
    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider, api_key


@pytest_asyncio.fixture
async def active_model(db_session: AsyncSession, test_provider_with_key):
    """创建活跃模型"""
    provider, _ = test_provider_with_key
    model = ModelCatalog(
        model_id="active-model",
        display_name="Active Model",
        provider_id=provider.id,
        input_price=Decimal("0.01"),
        output_price=Decimal("0.03"),
        status=ModelStatus.ACTIVE,
        source=ModelSource.MANUAL,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest_asyncio.fixture
async def deprecated_model(db_session: AsyncSession, test_provider_with_key):
    """创建废弃模型"""
    provider, _ = test_provider_with_key
    model = ModelCatalog(
        model_id="deprecated-model",
        display_name="Deprecated Model",
        provider_id=provider.id,
        input_price=Decimal("0.01"),
        output_price=Decimal("0.03"),
        status=ModelStatus.DEPRECATED,
        source=ModelSource.MANUAL,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


class TestCheckModelDeprecation:
    """模型废弃检查服务测试"""

    @pytest.mark.asyncio
    async def test_check_deprecation_service_deprecated(
        self, db_session, deprecated_model
    ):
        """测试废弃模型返回 True"""
        from services.model_status import check_model_deprecation

        is_deprecated = await check_model_deprecation("deprecated-model", db_session)
        assert is_deprecated is True

    @pytest.mark.asyncio
    async def test_check_deprecation_service_active(
        self, db_session, active_model
    ):
        """测试活跃模型返回 False"""
        from services.model_status import check_model_deprecation

        is_deprecated = await check_model_deprecation("active-model", db_session)
        assert is_deprecated is False

    @pytest.mark.asyncio
    async def test_check_deprecation_service_unknown(
        self, db_session
    ):
        """测试未知模型返回 False（不阻塞请求）"""
        from services.model_status import check_model_deprecation

        is_deprecated = await check_model_deprecation("unknown-model", db_session)
        assert is_deprecated is False

    @pytest.mark.asyncio
    async def test_beta_model_not_deprecated(
        self, db_session, test_provider_with_key
    ):
        """测试 Beta 模型不被视为废弃"""
        from services.model_status import check_model_deprecation

        provider, _ = test_provider_with_key
        beta_model = ModelCatalog(
            model_id="beta-model",
            display_name="Beta Model",
            provider_id=provider.id,
            input_price=Decimal("0.01"),
            output_price=Decimal("0.03"),
            status=ModelStatus.BETA,
            source=ModelSource.MANUAL,
        )
        db_session.add(beta_model)
        await db_session.commit()

        is_deprecated = await check_model_deprecation("beta-model", db_session)
        assert is_deprecated is False

    @pytest.mark.asyncio
    async def test_alpha_model_not_deprecated(
        self, db_session, test_provider_with_key
    ):
        """测试 Alpha 模型不被视为废弃"""
        from services.model_status import check_model_deprecation

        provider, _ = test_provider_with_key
        alpha_model = ModelCatalog(
            model_id="alpha-model",
            display_name="Alpha Model",
            provider_id=provider.id,
            input_price=Decimal("0.01"),
            output_price=Decimal("0.03"),
            status=ModelStatus.ALPHA,
            source=ModelSource.MANUAL,
        )
        db_session.add(alpha_model)
        await db_session.commit()

        is_deprecated = await check_model_deprecation("alpha-model", db_session)
        assert is_deprecated is False

    @pytest.mark.asyncio
    async def test_inactive_model_not_deprecated(
        self, db_session, test_provider_with_key
    ):
        """测试 Inactive 模型不被视为废弃（只是禁用）"""
        from services.model_status import check_model_deprecation

        provider, _ = test_provider_with_key
        inactive_model = ModelCatalog(
            model_id="inactive-model",
            display_name="Inactive Model",
            provider_id=provider.id,
            input_price=Decimal("0.01"),
            output_price=Decimal("0.03"),
            status=ModelStatus.INACTIVE,
            source=ModelSource.MANUAL,
        )
        db_session.add(inactive_model)
        await db_session.commit()

        is_deprecated = await check_model_deprecation("inactive-model", db_session)
        assert is_deprecated is False

    @pytest.mark.asyncio
    async def test_deprecation_with_variant(
        self, db_session, deprecated_model
    ):
        """测试带变体的模型也能正确检测废弃状态"""
        from services.model_status import check_model_deprecation

        # 带变体的模型 ID
        is_deprecated = await check_model_deprecation("deprecated-model:extended-thinking", db_session)
        assert is_deprecated is True


class TestGetModelStatus:
    """获取模型状态测试"""

    @pytest.mark.asyncio
    async def test_get_model_status_existing(
        self, db_session, deprecated_model
    ):
        """测试获取已存在模型的状态"""
        from services.model_status import get_model_status

        status = await get_model_status("deprecated-model", db_session)
        assert status == ModelStatus.DEPRECATED

    @pytest.mark.asyncio
    async def test_get_model_status_unknown(
        self, db_session
    ):
        """测试获取未知模型的状态"""
        from services.model_status import get_model_status

        status = await get_model_status("unknown-model", db_session)
        assert status is None

    @pytest.mark.asyncio
    async def test_get_model_status_with_variant(
        self, db_session, active_model
    ):
        """测试带变体的模型也能获取正确的状态"""
        from services.model_status import get_model_status

        status = await get_model_status("active-model:extended-thinking", db_session)
        assert status == ModelStatus.ACTIVE
