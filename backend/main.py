"""
LLM Token Manager - FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from config import get_settings
from database import init_db, close_db
from routers import auth, admin, admin_models, admin_usage, admin_model_limits, admin_pricing_history, user_keys, user, user_usage, gateway, anthropic_gateway, admin_provider_presets

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()

    # 初始化 RPMTracker 单例
    from services.rpm_tracker import get_rpm_tracker
    get_rpm_tracker()

    yield
    # 关闭时清理资源
    await close_db()


app = FastAPI(
    title="LLM Token Manager",
    description="大模型 Token 管理网关 — 统一管理团队的 LLM API 使用",
    version="1.1.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────
# 异常处理器 - 将 Pydantic 验证错误转换为友好格式
# ─────────────────────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    将 FastAPI 的 422 验证错误转换为友好的字符串格式

    Pydantic v2 默认返回:
    {"detail": [{"type": "...", "loc": [...], "msg": "...", ...}]}

    转换为:
    {"detail": "字段 xxx: 错误信息"}
    """
    errors = exc.errors()
    if not errors:
        return JSONResponse(
            status_code=422,
            content={"detail": "请求参数验证失败"}
        )

    # 将所有错误合并为友好的字符串
    error_messages = []
    for error in errors:
        loc = error.get("loc", [])
        msg = error.get("msg", "验证失败")

        # 提取字段名（跳过 "body" 前缀）
        field_parts = [str(part) for part in loc if part != "body"]
        field_name = ".".join(field_parts) if field_parts else "未知字段"

        error_messages.append(f"{field_name}: {msg}")

    detail = "; ".join(error_messages)

    return JSONResponse(
        status_code=422,
        content={"detail": detail}
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
        "version": "1.1.0"
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
# 路由注册
# ─────────────────────────────────────────────────────────────────────

# 认证路由（注册、登录、获取当前用户）
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])

# 用户路由（用量统计等）
app.include_router(user.router, prefix="/api/user", tags=["User"])

# 用户用量统计路由
app.include_router(user_usage.router, prefix="/api/user/usage", tags=["User Usage"])

# 用户 Key 管理路由
app.include_router(user_keys.router, prefix="/api/user/keys", tags=["User Keys"])

# Admin 供应商预设路由（必须在 admin.router 之前注册，避免路由冲突）
app.include_router(admin_provider_presets.router, prefix="/api/admin", tags=["Admin Provider Presets"])

# Admin 管理路由
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])

# Admin 模型管理路由
app.include_router(admin_models.router, prefix="/api/admin", tags=["Admin Models"])

# Admin 用量统计路由
app.include_router(admin_usage.router, prefix="/api/admin/usage", tags=["Admin Usage"])

# Admin 用户模型限制路由
app.include_router(admin_model_limits.router, prefix="/api/admin", tags=["Admin Model Limits"])

# Admin 定价历史路由
app.include_router(admin_pricing_history.router, prefix="/api/admin", tags=["Admin Pricing History"])

# 网关代理路由（OpenAI 兼容）
app.include_router(gateway.router, prefix="/v1", tags=["Gateway"])

# Anthropic Messages API 网关路由
app.include_router(anthropic_gateway.router, prefix="/v1", tags=["Anthropic Gateway"])
