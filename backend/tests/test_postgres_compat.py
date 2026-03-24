"""
PostgreSQL 兼容性测试

这些测试验证核心功能在 PostgreSQL 上正常工作。
只在使用 POSTGRES_TEST_URL 环境变量时运行。

用法:
    # 使用脚本一键运行
    ./scripts/test-pg-compat.sh

    # 或手动运行
    POSTGRES_TEST_URL=postgresql+asyncpg://user:pass@localhost:5432/db \
        python -m pytest tests/test_postgres_compat.py -v
"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# 检查是否配置了 PostgreSQL 测试 URL
POSTGRES_URL = os.getenv("POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Set POSTGRES_TEST_URL to run PostgreSQL compatibility tests"
)

# 设置测试环境变量（必须在导入应用之前）
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = POSTGRES_URL or "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "pg-test-secret-key-for-testing-only"
os.environ["ENCRYPTION_KEY"] = "pg-test-encryption-key-32-chars!"

from database import Base, get_db
from models.user import User, UserRole
from models.user_api_key import UserApiKey
from models.provider import Provider
from models.provider_api_key import ProviderApiKey
from models.request_log import RequestLog
from services.auth import hash_password, create_access_token
from services.user_key_service import generate_api_key
from main import app


# ─────────────────────────────────────────────────────────────────────
# PostgreSQL 数据库 Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def pg_engine():
    """创建 PostgreSQL 测试引擎（模块级别，只创建一次）"""
    engine = create_async_engine(
        POSTGRES_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(pg_engine):
    """创建独立的测试 session，每个测试后回滚"""
    async_session_maker = async_sessionmaker(
        pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        # 开始事务
        async with session.begin():
            yield session
        # 事务自动回滚


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """创建 HTTP 测试客户端"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """创建测试用户"""
    user = User(
        email="pg-test@example.com",
        password_hash=hash_password("password123"),
        role=UserRole.USER,
        monthly_quota_usd=100.0,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """创建测试管理员"""
    admin = User(
        email="pg-admin@example.com",
        password_hash=hash_password("admin123"),
        role=UserRole.ADMIN,
        monthly_quota_usd=1000.0,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def user_token(test_user):
    """生成用户 JWT token"""
    return create_access_token({"sub": str(test_user.id), "role": "user"})


@pytest_asyncio.fixture
async def admin_token(test_admin):
    """生成管理员 JWT token"""
    return create_access_token({"sub": str(test_admin.id), "role": "admin"})


@pytest_asyncio.fixture
async def user_api_key(db_session: AsyncSession, test_user):
    """创建用户 API Key"""
    raw_key = generate_api_key()
    key_obj = UserApiKey(
        user_id=test_user.id,
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        key_prefix=raw_key[:8],
        name="PG Test Key",
        is_active=True,
    )
    db_session.add(key_obj)
    await db_session.commit()
    await db_session.refresh(key_obj)
    return (key_obj, raw_key)


import hashlib


# ─────────────────────────────────────────────────────────────────────
# 兼容性测试
# ─────────────────────────────────────────────────────────────────────

class TestPostgresBasicCompatibility:
    """基础 PostgreSQL 兼容性测试"""

    @pytest.mark.asyncio
    async def test_database_connection(self, pg_engine):
        """验证 PostgreSQL 连接正常"""
        async with pg_engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_user_creation(self, db_session: AsyncSession):
        """验证用户创建在 PostgreSQL 上正常"""
        user = User(
            email="pg-create@example.com",
            password_hash=hash_password("test123"),
            role=UserRole.USER,
            monthly_quota_usd=50.0,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.email == "pg-create@example.com"
        assert user.role == UserRole.USER

    @pytest.mark.asyncio
    async def test_user_api_key_creation(self, db_session: AsyncSession, test_user):
        """验证 API Key 创建在 PostgreSQL 上正常"""
        raw_key = generate_api_key()
        key_obj = UserApiKey(
            user_id=test_user.id,
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            key_prefix=raw_key[:8],
            name="Test Key",
            is_active=True,
        )
        db_session.add(key_obj)
        await db_session.commit()
        await db_session.refresh(key_obj)

        assert key_obj.id is not None
        assert key_obj.key_prefix == raw_key[:8]


class TestPostgresAuthCompatibility:
    """认证功能 PostgreSQL 兼容性测试"""

    @pytest.mark.asyncio
    async def test_login_success(self, client, test_user):
        """验证登录在 PostgreSQL 上正常"""
        response = await client.post(
            "/api/auth/login",
            json={"email": "pg-test@example.com", "password": "password123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, test_user):
        """验证错误密码被拒绝"""
        response = await client.post(
            "/api/auth/login",
            json={"email": "pg-test@example.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401


class TestPostgresUserKeyCompatibility:
    """用户 Key 管理 PostgreSQL 兼容性测试"""

    @pytest.mark.asyncio
    async def test_create_user_key(self, client, user_token):
        """验证创建 Key 在 PostgreSQL 上正常"""
        response = await client.post(
            "/api/user/keys",
            json={"name": "New PG Key"},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "key" in data
        assert data["key"].startswith("ltm-sk-")

    @pytest.mark.asyncio
    async def test_list_user_keys(self, client, user_token, user_api_key):
        """验证列出 Key 在 PostgreSQL 上正常"""
        response = await client.get(
            "/api/user/keys",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestPostgresAdminCompatibility:
    """管理功能 PostgreSQL 兼容性测试"""

    @pytest.mark.asyncio
    async def test_admin_list_users(self, client, admin_token, test_user):
        """验证管理员列出用户在 PostgreSQL 上正常"""
        response = await client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert len(data["users"]) >= 1

    @pytest.mark.asyncio
    async def test_user_cannot_access_admin(self, client, user_token):
        """验证普通用户无法访问管理接口"""
        response = await client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403


class TestPostgresJSONCompatibility:
    """JSON 字段 PostgreSQL 兼容性测试（重点）"""

    @pytest.mark.asyncio
    async def test_request_log_json_fields(self, db_session: AsyncSession, test_user):
        """验证 JSON 字段在 PostgreSQL 上正常存储和读取"""
        log = RequestLog(
            user_id=test_user.id,
            model="gpt-4o",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            request_metadata={"key": "value", "nested": {"data": 123}},
            response_metadata={"status": "success"},
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.request_metadata["key"] == "value"
        assert log.request_metadata["nested"]["data"] == 123
        assert log.response_metadata["status"] == "success"
