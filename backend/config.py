"""
应用配置模块
从环境变量加载所有配置项
"""
from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./llm_manager.db"

    # JWT 配置
    secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120  # 2 小时

    # 加密配置（供应商 Key 加密）
    encryption_key: str = "dev-encryption-key-32-characters!!"

    # 测试模式
    testing: bool = False

    # 注册配置
    registration_mode: str = "open"  # open / approval / restricted
    allowed_email_domains: Optional[str] = None

    # 默认额度配置
    default_monthly_quota_usd: float = 10.00
    default_rpm_limit: int = 30
    default_max_keys: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
