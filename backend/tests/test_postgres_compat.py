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
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

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
from models.request_log import RequestLog, RequestStatus
from services.auth import hash_password, create_access_token
from services.user_key_service import generate_api_key
from main import app


# ─────────────────────────────────────────────────────────────────────
# PostgreSQL 数据库 Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session():
    """创建 PostgreSQL 测试 session"""
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


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


# ─────────────────────────────────────────────────────────────────────
# 用户 fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """创建测试用户"""
    user = User(
        username="pg-test-user",
        email="pg-test@example.com",
        password_hash=hash_password("password123"),
        real_name="PG测试用户",
        role=UserRole.USER,
        is_active=True,
        monthly_quota_usd=100.0,
        rpm_limit=30,
        max_keys=5,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession):
    """创建测试管理员"""
    admin = User(
        username="pg-test-admin",
        email="pg-admin@example.com",
        password_hash=hash_password("admin123"),
        real_name="PG测试管理员",
        role=UserRole.ADMIN,
        is_active=True,
        monthly_quota_usd=1000.0,
        rpm_limit=100,
        max_keys=10,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def user_token(test_user: User):
    """生成用户 JWT token"""
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
    """生成管理员 JWT token"""
    role = test_admin.role.value if hasattr(test_admin.role, 'value') else test_admin.role
    token = create_access_token(
        data={
            "sub": test_admin.username,
            "user_id": str(test_admin.id),
            "role": role
        }
    )
    return token


@pytest_asyncio.fixture
async def user_api_key(test_user, db_session: AsyncSession):
    """创建用户 API Key"""
    raw_key, key_hash, key_suffix = generate_api_key()
    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="PG Test Key",
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
# 兼容性测试
# ─────────────────────────────────────────────────────────────────────

class TestPostgresBasicCompatibility:
    """基础 PostgreSQL 兼容性测试"""

    @pytest.mark.asyncio
    async def test_database_connection(self, db_session):
        """验证 PostgreSQL 连接正常"""
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_user_creation(self, db_session: AsyncSession):
        """验证用户创建在 PostgreSQL 上正常"""
        user = User(
            username="pg-create-user",
            email="pg-create@example.com",
            password_hash=hash_password("test123"),
            real_name="PG创建测试用户",
            role=UserRole.USER,
            is_active=True,
            monthly_quota_usd=50.0,
            rpm_limit=30,
            max_keys=5,
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

        assert key.id is not None
        assert key.key_suffix == key_suffix


class TestPostgresAuthCompatibility:
    """认证功能 PostgreSQL 兼容性测试"""

    @pytest.mark.asyncio
    async def test_login_success(self, client, test_user):
        """验证登录在 PostgreSQL 上正常"""
        response = await client.post(
            "/api/auth/login",
            json={"username": "pg-test-user", "password": "password123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, test_user):
        """验证错误密码被拒绝"""
        response = await client.post(
            "/api/auth/login",
            json={"username": "pg-test-user", "password": "wrongpassword"}
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
        assert response.status_code == 201  # Created
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
        # API 返回的是列表，不是 {users: [...]}
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_user_cannot_access_admin(self, client, user_token):
        """验证普通用户无法访问管理接口"""
        response = await client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403


class TestPostgresRequestLogCompatibility:
    """请求日志 PostgreSQL 兼容性测试"""

    @pytest.mark.asyncio
    async def test_request_log_creation(self, db_session: AsyncSession, test_user):
        """验证请求日志在 PostgreSQL 上正常创建"""
        log = RequestLog(
            id=uuid.uuid4(),
            request_id=f"req-{uuid.uuid4().hex[:16]}",
            user_id=test_user.id,
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_usd=0.01,
            status=RequestStatus.SUCCESS,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.id is not None
        assert log.model == "gpt-4o"
        assert log.input_tokens == 100
        assert log.output_tokens == 50
