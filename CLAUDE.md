# LLM Token Manager

大模型 Token 管理网关 — 统一管理团队的 LLM API 使用。

## 项目简介

这是一个 LLM Gateway（大模型网关），为 20-50 人团队提供统一的大模型 API 接入、用量统计和成本控制能力。用户通过平台分发的 Key 调用各家大模型，所有请求经过网关转发、计量和限额。

完整需求文档见 `docs/PRD.md`，在实现任何功能前请先阅读对应章节。

## 技术栈

- **后端**: Python 3.11+ / FastAPI / Uvicorn
- **数据库**: PostgreSQL（开发期可先用 SQLite）
- **ORM**: SQLAlchemy 2.0 + Alembic（数据库迁移）
- **前端**: React 18 + Ant Design 5 + React Router 6
- **部署**: Docker + Docker Compose
- **认证**: JWT（管理后台登录） + 平台 Key（API 调用鉴权），两套体系独立
- **测试**: pytest + pytest-asyncio + httpx（后端） / Vitest（前端）

## 项目结构

```
llm-token-manager/
├── docker-compose.yml
├── .env.example
├── .env.test                    # 测试专用环境变量
├── .gitignore
├── backend/
│   ├── main.py                  # FastAPI 入口，挂载所有 router
│   ├── config.py                # 从环境变量加载配置
│   ├── database.py              # 数据库引擎和 session
│   ├── models/                  # SQLAlchemy 模型（每表一个文件）
│   ├── routers/                 # API 路由（按功能模块拆分）
│   │   ├── gateway.py           # OpenAI 格式网关 /v1/chat/completions
│   │   └── anthropic_gateway.py # Anthropic 格式网关 /v1/messages
│   ├── services/                # 业务逻辑（不依赖 HTTP 层）
│   │   ├── proxy.py             # OpenAI 格式代理逻辑
│   │   ├── anthropic_proxy.py   # Anthropic 格式透传代理逻辑
│   │   ├── quota.py             # 额度与限流检查
│   │   ├── billing.py           # 计量与费用计算
│   │   └── providers/           # 各 LLM 供应商的请求/响应适配器
│   ├── middleware/               # 认证、限流中间件
│   ├── alembic/                 # 数据库迁移脚本
│   ├── tests/                   # 测试目录
│   │   ├── conftest.py          # 全局 fixtures
│   │   ├── test_auth.py
│   │   ├── test_user_keys.py
│   │   ├── test_admin.py
│   │   ├── test_gateway.py
│   │   ├── test_anthropic_gateway.py  # Anthropic 端点测试
│   │   ├── test_quota.py
│   │   └── test_billing.py
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/
│   └── package.json
└── docs/
    ├── PRD.md
    └── anthropic-api-setup.md   # Anthropic API 配置指南
```

## 核心概念

- **平台 Key**: 格式 `ltm-sk-{32位随机字符}`，分发给用户，数据库存 SHA-256 哈希
- **供应商 Key**: Admin 配置的 OpenAI/Anthropic 等原始 API Key，AES-256 加密存储
- **网关代理**: 统一接口 `POST /v1/chat/completions`，兼容 OpenAI 格式，根据 model 字段路由到对应供应商
- **额度控制**: 按用户维度设置月度 USD 额度，同一用户所有 Key 的用量合并计算

---

## ⚠️ 开发铁律（Agent 必须遵守）

### 规则一：先写测试，后写实现

每个功能的开发流程必须是：
1. 先编写测试用例（可以先失败）
2. 再编写实现代码
3. 使用 miniconda 环境运行测试：`/Users/hxuaj/miniconda3/envs/llm-token-manager/bin/python -m pytest`
4. 提交代码

**禁止**在没有对应测试的情况下提交任何 router 或 service 代码。

### 规则二：提交前必须测试通过

在执行 `git commit` 之前，**必须**先运行测试并确认所有测试通过：
```bash
/Users/hxuaj/miniconda3/envs/llm-token-manager/bin/python -m pytest
```
如果有测试失败，先修复再提交，绝不跳过。

### 规则三：每个逻辑变更单独提交

不要把多个不相关的改动塞进一个 commit。一个 commit 只做一件事。

### 规则四：不破坏已有功能

实现新功能后，必须运行**完整**测试套件（不仅是新写的测试），确保没有引入回归。

### 规则五：敏感信息不入库

- `.env` 文件必须在 `.gitignore` 中
- 测试中使用 mock 数据，不使用真实 API Key
- 供应商 API Key 在任何日志、测试输出、commit message 中都不得出现

---

## Git 工作流

### 项目根目录

**项目根目录**: `/Users/hxuaj/Desktop/Work/projects/llm-token-manager-claude-glm5`

由于 Agent 工作目录可能在 `backend/` 子目录，执行 git 命令时必须使用以下方式之一：

```bash
# 方式1: 使用 -C 指定仓库根目录（推荐）
git -C /Users/hxuaj/Desktop/Work/projects/llm-token-manager-claude-glm5 status
git -C /Users/hxuaj/Desktop/Work/projects/llm-token-manager-claude-glm5 add .
git -C /Users/hxuaj/Desktop/Work/projects/llm-token-manager-claude-glm5 commit -m "msg"

# 方式2: 使用相对路径（当前在 backend/ 目录时）
git add ../CLAUDE.md
```

### 分支策略

```
main                          ← 稳定版本，每个 Step 完成后合并
  ├── step1/project-init      ← Step 1: 项目初始化
  ├── step2/auth              ← Step 2: 注册/登录
  ├── step3/user-keys         ← Step 3: 平台 Key 管理
  ├── step4/provider-keys     ← Step 4: 供应商 Key 管理
  ├── step5/gateway           ← Step 5: 网关代理
  ├── step6/billing-quota     ← Step 6: 计量与额度
  └── step7/frontend          ← Step 7: 管理后台前端
```

### 每个 Step 的 Git 操作流程

```bash
# 1. 从 main 创建新分支
git checkout main
git checkout -b step2/auth

# 2. 开发过程中频繁小提交（每次提交前运行测试）
#    cd backend && python -m pytest
git add .
git commit -m "test(auth): add registration endpoint tests"
#    cd backend && python -m pytest
git add .
git commit -m "feat(auth): implement registration endpoint"

# 3. Step 完成且所有测试通过后，合并回 main
git checkout main
git merge step2/auth
git tag v0.2-auth
```

### Commit Message 规范（Conventional Commits）

格式：`<type>(<scope>): <description>`

| type | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(gateway): add OpenAI proxy endpoint` |
| `fix` | 修复 Bug | `fix(quota): fix monthly reset calculation` |
| `test` | 添加/修改测试 | `test(auth): add JWT expiration test` |
| `refactor` | 重构 | `refactor(proxy): extract provider adapter base class` |
| `docs` | 文档 | `docs: update API endpoint list in PRD` |
| `chore` | 构建/配置 | `chore: add docker-compose and .env.example` |

---

## 测试规范

### 测试框架与工具

```
pytest              # 测试框架
pytest-asyncio      # 异步测试支持
httpx               # 异步 HTTP 客户端（用于测试 FastAPI）
pytest-cov          # 覆盖率报告
unittest.mock       # Mock 外部依赖（供应商 API）
```

### conftest.py 必须提供的 fixtures

```python
# backend/tests/conftest.py 应包含以下 fixtures：

@pytest.fixture
async def db_session():
    """每个测试用例独立的数据库 session，测试后自动回滚"""

@pytest.fixture
async def client(db_session):
    """绑定了测试数据库的 AsyncClient（httpx）"""

@pytest.fixture
async def test_user(db_session):
    """一个已注册的普通 User"""

@pytest.fixture
async def test_admin(db_session):
    """一个已注册的 Admin"""

@pytest.fixture
async def user_token(test_user):
    """普通用户的 JWT token"""

@pytest.fixture
async def admin_token(test_admin):
    """Admin 用户的 JWT token"""

@pytest.fixture
async def user_api_key(test_user):
    """为测试用户创建一个平台 Key，返回 (key_object, raw_key_string)"""

@pytest.fixture
async def mock_openai():
    """Mock OpenAI API 响应，不发真实请求"""
```

### 测试数据库策略

- 使用 SQLite 内存数据库 `sqlite+aiosqlite:///:memory:`，无需外部依赖
- 每个测试函数独立 session + 自动回滚，测试之间互不影响
- 通过环境变量 `TESTING=true` 切换到测试数据库

### 每个模块的测试要求

详细测试用例清单见 `docs/PRD.md` 第 11 章。以下是摘要：

- **test_auth.py**：注册成功/失败、登录成功/失败、JWT 过期/无效、角色权限
- **test_user_keys.py**：创建/列表/吊销 Key、数量限制、Key 维度统计
- **test_admin.py**：用户 CRUD、供应商 CRUD、单价配置、403 权限校验
- **test_gateway.py**：鉴权、模型路由、请求/响应转换、流式、错误处理、模型白名单（全部用 mock）
- **test_quota.py**：额度检查/扣减/超额拒绝/月度重置/RPM 限流
- **test_billing.py**：日志记录完整性、月度汇总、按 Key 统计、费用精度

### 运行命令

```bash
# 全部测试
cd backend && python -m pytest

# 全部测试 + 覆盖率
cd backend && python -m pytest --cov=. --cov-report=term-missing

# 单个文件
cd backend && python -m pytest tests/test_auth.py -v

# 单个函数
cd backend && python -m pytest tests/test_auth.py::test_register_success -v

# 只跑上次失败的
cd backend && python -m pytest --lf
```

---

## 开发规范

### Python 后端
- 遵循 PEP 8，使用 type hints
- 路由函数放 `routers/`，业务逻辑放 `services/`，保持分层清晰
- 异步优先：路由和数据库操作使用 async/await
- 敏感信息一律通过环境变量注入，禁止硬编码

### React 前端
- 使用函数式组件 + Hooks
- 使用 Ant Design 组件库
- API 调用统一封装在 `src/api/` 目录

### 数据库
- 所有表使用 UUID 主键
- 用户密码用 bcrypt 哈希
- 平台 Key 存 SHA-256 哈希（不可逆）
- 供应商 Key 存 AES-256 加密（可解密用于调用）
- 每次 schema 变更必须通过 Alembic migration

---

## 开发顺序

严格按以下步骤推进，每步完成后验证再进入下一步：

1. **项目初始化** → docker-compose + FastAPI + /health + pytest 配置 + conftest.py
2. **注册/登录** → users 表 + JWT + test_auth.py 全部通过 → 合并到 main
3. **平台 Key 管理** → user_api_keys 表 + CRUD + test_user_keys.py 全部通过 → 合并到 main
4. **供应商 Key 管理** → providers + provider_api_keys + test_admin.py 全部通过 → 合并到 main
5. **网关代理** → /v1/chat/completions + test_gateway.py 全部通过 → 合并到 main
6. **计量与额度** → request_logs + 计费 + test_quota.py + test_billing.py 全部通过 → 合并到 main
7. **管理后台前端** → React SPA + 基础 E2E 验证 → 合并到 main

---

## 关键 API 路径

| 路径 | 用途 |
|------|------|
| `POST /v1/chat/completions` | 核心网关代理（平台 Key 鉴权，OpenAI 格式） |
| `POST /v1/messages` | Anthropic Messages API 代理（平台 Key 鉴权，Anthropic 格式） |
| `GET /v1/models` | 可用模型列表（平台 Key 鉴权） |
| `POST /api/auth/register` | 用户注册 |
| `POST /api/auth/login` | 登录获取 JWT |
| `POST /api/user/keys` | 创建平台 Key |
| `/api/admin/*` | Admin 管理接口（JWT + Admin 角色） |

## 环境变量

参考 `.env.example`，关键变量包括：

```
DATABASE_URL=postgresql://user:pass@localhost:5432/llm_manager
SECRET_KEY=<JWT签名密钥>
ENCRYPTION_KEY=<AES-256加密密钥，用于供应商Key加密>
DEFAULT_MONTHLY_QUOTA_USD=10.00
DEFAULT_RPM_LIMIT=30
DEFAULT_MAX_KEYS=5
REGISTRATION_MODE=open
ALLOWED_EMAIL_DOMAINS=yourcompany.com
```

## 常用命令

```bash
# 启动开发环境
docker-compose up -d

# 后端本地开发
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# 运行测试（每次提交前必须执行）
cd backend && python -m pytest

# 运行测试 + 覆盖率
cd backend && python -m pytest --cov=. --cov-report=term-missing

# 数据库迁移
cd backend && alembic upgrade head

# 前端本地开发
cd frontend && npm install && npm run dev
```
