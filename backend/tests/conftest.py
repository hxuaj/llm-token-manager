"""
pytest 全局配置和 fixtures

为所有测试提供：
- 测试数据库 session
- HTTP 测试客户端
- 测试用户和 Admin
- JWT token
- Mock 供应商 API
"""
import os
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# 设置测试环境变量（必须在导入应用之前）
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-32-characters!"

from database import Base, get_db
from models.user import User, UserRole
from models.user_api_key import UserApiKey
from services.auth import hash_password, create_access_token
from services.user_key_service import generate_api_key
from main import app


# ─────────────────────────────────────────────────────────────────────
# 测试数据库引擎和 Session
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session():
    """
    创建独立的测试数据库 session

    每个测试函数获得：
    - 全新的内存 SQLite 数据库
    - 所有表已创建
    - 测试结束后自动回滚（隔离）
    """
    # 创建内存数据库引擎
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 创建 session
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session

    # 清理
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """
    创建绑定了测试数据库的 HTTP 客户端

    使用 httpx.AsyncClient 测试 FastAPI 应用
    """
    # 覆盖应用的 get_db 依赖
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # 创建测试客户端
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    # 清理依赖覆盖
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────
# 用户 fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """
    创建一个普通测试用户

    返回 user 对象
    """
    user = User(
        username="testuser",
        email="testuser@example.com",
        password_hash=hash_password("testpassword123"),
        real_name="测试用户",
        role=UserRole.USER,
        is_active=True,
        monthly_quota_usd=10.00,
        rpm_limit=30,
        max_keys=5,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """
    创建一个 Admin 测试用户

    返回 admin user 对象
    """
    admin = User(
        username="testadmin",
        email="testadmin@example.com",
        password_hash=hash_password("adminpassword123"),
        real_name="测试管理员",
        role=UserRole.ADMIN,
        is_active=True,
        monthly_quota_usd=100.00,
        rpm_limit=100,
        max_keys=10,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def user_token(test_user: User):
    """
    普通用户的 JWT token

    返回 token 字符串
    """
    role = test_user.role.value if hasattr(test_user.role, 'value') else test_user.role
    token = create_access_token(
        data={
            "sub": test_user.username,
            "user_id": str(test_user.id),
            "role": role
        }
    )
    return token


@pytest_asyncio.fixture
async def admin_token(test_admin: User):
    """
    Admin 用户的 JWT token

    返回 token 字符串
    """
    role = test_admin.role.value if hasattr(test_admin.role, 'value') else test_admin.role
    token = create_access_token(
        data={
            "sub": test_admin.username,
            "user_id": str(test_admin.id),
            "role": role
        }
    )
    return token


# ─────────────────────────────────────────────────────────────────────
# 平台 Key fixtures（Step 3 实现后添加）
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def user_api_key(test_user, db_session: AsyncSession):
    """
    为测试用户创建一个平台 Key

    返回 (key_object, raw_key_string) 元组
    """
    import uuid
    raw_key, key_hash, key_suffix = generate_api_key()
    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Test Key",
        key_hash=key_hash,
        key_prefix="ltm-sk-",
        key_suffix=key_suffix,
        status="active",
    )
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)
    return key, raw_key


# ─────────────────────────────────────────────────────────────────────
# Mock 供应商 API fixtures（Step 5 实现后添加）
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_openai():
    """
    Mock OpenAI API 响应

    用于测试网关代理逻辑，不发送真实请求
    """
    # TODO: Step 5 实现后添加
    pass


@pytest.fixture
def mock_anthropic():
    """
    Mock Anthropic API 响应
    """
    # TODO: Step 5 实现后添加
    pass


# ─────────────────────────────────────────────────────────────────────
# 供应商和 Key fixtures（用于 Key 软分配测试）
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_provider(db_session: AsyncSession):
    """创建一个测试供应商"""
    from models.provider import Provider

    provider = Provider(
        name="test_provider",
        display_name="Test Provider",
        base_url="https://api.test.com",
        api_format="openai",
        enabled=True
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


@pytest_asyncio.fixture
async def test_provider_keys(test_provider, db_session: AsyncSession):
    """创建多个测试 Key"""
    from models.provider_api_key import ProviderApiKey, ProviderKeyStatus, KeyPlan
    from services.encryption import encrypt, extract_key_suffix

    keys = []
    for i in range(3):
        raw_key = f"sk-test-key-{i}-{uuid.uuid4().hex[:8]}"
        encrypted_key = encrypt(raw_key)
        key_suffix = extract_key_suffix(raw_key)

        key = ProviderApiKey(
            provider_id=test_provider.id,
            encrypted_key=encrypted_key,
            key_suffix=key_suffix,
            rpm_limit=60,
            status=ProviderKeyStatus.ACTIVE.value,
            key_plan=KeyPlan.STANDARD.value
        )
        db_session.add(key)
        keys.append(key)

    await db_session.commit()
    for key in keys:
        await db_session.refresh(key)
    return keys


@pytest_asyncio.fixture
async def user_with_primary_key(test_user, test_provider, test_provider_keys, db_session: AsyncSession):
    """已分配 Primary Key 的用户"""
    # 绑定第一个 Key 作为 Primary Key
    test_user.primary_provider_keys = {
        test_provider.name: str(test_provider_keys[0].id)
    }
    await db_session.commit()
    await db_session.refresh(test_user)
    return test_user


@pytest_asyncio.fixture
async def rpm_tracker():
    """创建一个独立的 RPMTracker 实例用于测试"""
    from services.rpm_tracker import RPMTracker

    # 创建新实例（不使用单例）
    tracker = RPMTracker.__new__(RPMTracker)
    tracker._initialized = False
    tracker.__init__()
    yield tracker
    # 清理
    await tracker.reset()
