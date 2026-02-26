"""
LLM Token Manager - FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db, close_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
    yield
    # 关闭时清理资源
    await close_db()


app = FastAPI(
    title="LLM Token Manager",
    description="大模型 Token 管理网关 — 统一管理团队的 LLM API 使用",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────
# 健康检查端点
# ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    """
    健康检查端点

    用于 Docker/K8s 健康检查和负载均衡器探测
    """
    return {
        "status": "healthy",
        "service": "llm-token-manager",
        "version": "0.1.0"
    }


@app.get("/", tags=["Root"])
async def root():
    """根路径重定向到健康检查"""
    return {
        "message": "LLM Token Manager API",
        "docs": "/docs",
        "health": "/health"
    }


# ─────────────────────────────────────────────────────────────────────
# 路由注册（后续 Step 会逐步添加）
# ─────────────────────────────────────────────────────────────────────

# from routers import auth, user_keys, admin, gateway
# app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
# app.include_router(user_keys.router, prefix="/api/user", tags=["User Keys"])
# app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
# app.include_router(gateway.router, prefix="/v1", tags=["Gateway"])
