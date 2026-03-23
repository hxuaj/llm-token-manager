"""
数据库连接模块
支持 PostgreSQL（生产）和 SQLite（开发/测试）
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import get_settings

settings = get_settings()

# 根据环境选择数据库
if settings.testing:
    # 测试使用内存 SQLite
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
else:
    DATABASE_URL = settings.database_url
    # 如果是 PostgreSQL URL 但没有指定驱动，自动添加 asyncpg
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=settings.testing,  # 测试时打印 SQL
    future=True,
)

# 创建异步 Session 工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 模型基类"""
    pass


async def get_db() -> AsyncSession:
    """获取数据库 session（依赖注入）"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库（创建所有表）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
