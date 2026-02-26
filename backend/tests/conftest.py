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
# 用户 fixtures（后续 Step 会实现）
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """
    创建一个普通测试用户

    返回 user 对象（Step 2 实现后完善）
    """
    # TODO: Step 2 实现后添加
    # from models.user import User
    # from passlib.context import CryptContext
    #
    # pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    # user = User(
    #     username="testuser",
    #     email="testuser@example.com",
    #     password_hash=pwd_context.hash("testpassword123"),
    #     role="user",
    #     is_active=True,
    # )
    # db_session.add(user)
    # await db_session.commit()
    # await db_session.refresh(user)
    # return user
    return None


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """
    创建一个 Admin 测试用户

    返回 admin user 对象（Step 2 实现后完善）
    """
    # TODO: Step 2 实现后添加
    return None


@pytest_asyncio.fixture
async def user_token(test_user):
    """
    普通用户的 JWT token

    返回 token 字符串（Step 2 实现后完善）
    """
    # TODO: Step 2 实现后添加
    return None


@pytest_asyncio.fixture
async def admin_token(test_admin):
    """
    Admin 用户的 JWT token

    返回 token 字符串（Step 2 实现后完善）
    """
    # TODO: Step 2 实现后添加
    return None


# ─────────────────────────────────────────────────────────────────────
# 平台 Key fixtures（Step 3 实现后添加）
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def user_api_key(test_user, db_session: AsyncSession):
    """
    为测试用户创建一个平台 Key

    返回 (key_object, raw_key_string) 元组
    """
    # TODO: Step 3 实现后添加
    return None, None


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
