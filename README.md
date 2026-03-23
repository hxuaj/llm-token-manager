# LLM Token Manager

大模型 Token 管理网关 — 为团队提供统一的大模型 API 接入、用量统计和成本控制能力。

## 功能特性

- **统一网关**: 兼容 OpenAI 和 Anthropic API 格式，一键切换模型供应商
- **多供应商支持**: 支持 OpenAI、Anthropic、Azure 等多家 LLM 供应商
- **Key 管理**: 为团队成员分发平台 Key，统一管理供应商 API Key
- **用量统计**: 实时追踪 Token 消耗和 API 调用成本
- **额度控制**: 按用户设置月度 USD 额度和 RPM 限制
- **管理后台**: React 前端提供完整的可视化管理界面
- **灵活部署**: 支持自定义端口和子目录部署

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy 2.0 |
| 数据库 | PostgreSQL / SQLite (开发) |
| 前端 | React 18 + Ant Design 5 + Vite |
| 认证 | JWT (管理后台) + Platform Key (API 调用) |
| 部署 | Docker + Docker Compose + Nginx |
| 测试 | pytest + httpx (后端) / Vitest (前端) |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ (或使用 Docker)
- Docker & Docker Compose (推荐)

### 使用 Docker Compose (开发模式)

```bash
# 1. 克隆项目
git clone https://github.com/your-username/llm-token-manager.git
cd llm-token-manager

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填写必要的配置

# 3. 启动服务
docker-compose up -d

# 4. 运行数据库迁移
docker-compose exec backend alembic upgrade head

# 5. 访问服务
# 后端 API: http://localhost:8000
# 前端: http://localhost:3000
# API 文档: http://localhost:8000/docs
```

### 本地开发

**后端:**

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example .env

# 运行数据库迁移
alembic upgrade head

# 启动开发服务器
uvicorn main:app --reload
```

**前端:**

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

## 核心 API

| 端点 | 说明 |
|------|------|
| `POST {BASE_PATH}/v1/chat/completions` | OpenAI 格式网关代理 |
| `POST {BASE_PATH}/v1/messages` | Anthropic 格式网关代理 |
| `GET {BASE_PATH}/v1/models` | 获取可用模型列表 |
| `POST {BASE_PATH}/api/auth/register` | 用户注册 |
| `POST {BASE_PATH}/api/auth/login` | 用户登录 |
| `{BASE_PATH}/api/user/keys` | 平台 Key 管理 |
| `{BASE_PATH}/api/admin/*` | 管理员接口 |

## 项目结构

```
llm-token-manager/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库连接
│   ├── models/              # SQLAlchemy 模型
│   ├── routers/             # API 路由
│   ├── services/            # 业务逻辑
│   ├── middleware/          # 中间件
│   ├── alembic/             # 数据库迁移
│   └── tests/               # 测试用例
├── frontend/
│   └── src/
│       ├── pages/           # 页面组件
│       ├── components/      # 通用组件
│       └── api/             # API 封装
├── nginx.conf.tpl           # Nginx 配置模板
├── docker-compose.prod.yml  # 生产环境编排
├── deploy.sh                # 一键部署脚本
└── docs/
    └── PRD.md               # 产品需求文档
```

## 生产部署

### 服务器要求

- Linux 服务器 (Ubuntu 20.04+ / CentOS 7+ / Debian 10+)
- Docker & Docker Compose 已安装
- 至少 2GB 内存
- 防火墙开放对应端口（默认 8080）

### 一键部署

```bash
# 1. 克隆项目
git clone https://github.com/your-username/llm-token-manager.git
cd llm-token-manager

# 2. 配置环境变量
cp .env.example .env
nano .env  # 填写 SECRET_KEY 和 ENCRYPTION_KEY

# 3. 运行部署脚本
./deploy.sh
```

### 部署后访问

部署完成后，通过以下地址访问：

```
http://你的服务器IP:{LTM_PORT}{LTM_BASE_PATH}/
```

**默认配置示例** (`LTM_PORT=8080`, `LTM_BASE_PATH=/ltm`)：

| 访问地址 | 说明 |
|----------|------|
| `http://192.168.1.100:8080/ltm/` | 管理后台前端 |
| `http://192.168.1.100:8080/ltm/docs` | API 交互文档 |
| `http://192.168.1.100:8080/ltm/v1/chat/completions` | OpenAI 格式网关 |

**获取服务器 IP：**

```bash
# 查看服务器 IP
hostname -I | awk '{print $1}'
# 或
curl -4 ifconfig.me
```

### 调用 API 示例

```bash
# 使用平台 Key 调用 OpenAI 格式接口（默认配置）
curl http://192.168.1.100:8080/ltm/v1/chat/completions \
  -H "Authorization: Bearer ltm-sk-your-platform-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### 创建管理员账号

首次部署后，通过以下方式创建管理员账号：

```bash
# 注册账号（默认配置）
curl -X POST http://192.168.1.100:8080/ltm/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your-password",
    "name": "Admin"
  }'
```

> 注册后，可通过数据库将该用户设为管理员，或通过已实现的管理员创建接口。

### 手动部署

```bash
# 生成密钥
openssl rand -hex 32  # SECRET_KEY
openssl rand -base64 32 | head -c 32  # ENCRYPTION_KEY

# 编辑 .env
cp .env.example .env
nano .env

# 生成 nginx 配置
source .env
envsubst '${LTM_BASE_PATH}' < nginx.conf.tpl > nginx.conf

# 构建并启动
docker-compose -f docker-compose.prod.yml up -d --build

# 运行数据库迁移
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### 常用运维命令

```bash
# 查看日志
docker-compose -f docker-compose.prod.yml logs -f

# 重启服务
docker-compose -f docker-compose.prod.yml restart

# 停止服务
docker-compose -f docker-compose.prod.yml down

# 更新代码后重新部署
git pull
./deploy.sh
```

### 架构说明

```
                       ┌──────────────────────────────────────────┐
                       │            Linux Server                  │
                       │                                          │
   用户请求 ──────────►│  Nginx (:${LTM_PORT})                     │
   http://IP:8080/ltm/ │    ├── ${LTM_BASE_PATH}/ (前端静态文件)    │
                       │    ├── ${LTM_BASE_PATH}/v1/* ──► Backend  │
                       │    └── ${LTM_BASE_PATH}/api/* ──► Backend │
                       │                                          │
                       │  Backend (:8000) ──► PostgreSQL (:5432)  │
                       └──────────────────────────────────────────┘
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | JWT 签名密钥 | **必填** |
| `ENCRYPTION_KEY` | AES-256 加密密钥 (32字符) | **必填** |
| `LTM_PORT` | 服务端口 | 8080 |
| `LTM_BASE_PATH` | 基础路径 (子目录部署) | /ltm |
| `POSTGRES_PASSWORD` | PostgreSQL 密码 | postgres |
| `DATABASE_URL` | 数据库连接字符串 | 自动配置 |
| `REGISTRATION_MODE` | 注册模式 (open/invite) | open |
| `ALLOWED_EMAIL_DOMAINS` | 允许的邮箱域名 | - |
| `DEFAULT_MONTHLY_QUOTA_USD` | 默认月度额度 | 10.00 |
| `DEFAULT_RPM_LIMIT` | 默认 RPM 限制 | 30 |
| `DEFAULT_MAX_KEYS` | 默认 Key 数量限制 | 5 |

### 自定义端口和路径

```bash
# .env 文件中配置

# 示例1: 使用 9000 端口
LTM_PORT=9000              # 访问 http://IP:9000/ltm/

# 示例2: 自定义子目录
LTM_BASE_PATH=/llm-gateway # 访问 http://IP:8080/llm-gateway/

# 示例3: 部署在根路径
LTM_PORT=80
LTM_BASE_PATH=             # 访问 http://IP/

# 示例4: 完整自定义
LTM_PORT=9000
LTM_BASE_PATH=/api/llm     # 访问 http://IP:9000/api/llm/
```

### 防火墙配置

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8080/tcp

# CentOS (firewalld)
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload

# 仅允许特定 IP 访问
sudo ufw allow from 192.168.1.0/24 to any port 8080
```

## 运行测试

```bash
# 后端测试
cd backend
python -m pytest

# 后端测试 + 覆盖率
python -m pytest --cov=. --cov-report=term-missing

# 前端测试
cd frontend
npm run test
```

## 许可证

MIT License
