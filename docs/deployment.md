# 部署文档

> LLM Token Manager 部署指南
> 最后更新：2026-03-04

---

## 目录

1. [环境要求](#环境要求)
2. [快速部署](#快速部署)
3. [配置说明](#配置说明)
4. [models.dev 同步配置](#modelsdev-同步配置)
5. [生产部署](#生产部署)
6. [故障排查](#故障排查)

---

## 环境要求

### 最低配置

| 组件 | 版本要求 |
|------|---------|
| Python | 3.11+ |
| PostgreSQL | 14+ |
| Docker | 20.10+ |
| Docker Compose | 2.0+ |

### 推荐配置（20-50 人团队）

| 资源 | 配置 |
|------|------|
| CPU | 2 核 |
| 内存 | 4 GB |
| 存储 | 20 GB SSD |

---

## 快速部署

### 使用 Docker Compose

1. **克隆代码**
   ```bash
   git clone <repository-url>
   cd llm-token-manager
   ```

2. **创建环境配置**
   ```bash
   cp .env.example .env
   ```

3. **编辑 .env 文件**
   ```bash
   # 数据库
   DATABASE_URL=postgresql://ltm:password@postgres:5432/llm_manager

   # JWT 密钥（生产环境必须修改）
   SECRET_KEY=your-secret-key-at-least-32-characters

   # 供应商 Key 加密密钥（必须 32 字符）
   ENCRYPTION_KEY=your-encryption-key-32-chars!!!

   # 额度配置
   DEFAULT_MONTHLY_QUOTA_USD=10.00
   DEFAULT_RPM_LIMIT=30
   DEFAULT_MAX_KEYS=5
   ```

4. **启动服务**
   ```bash
   docker-compose up -d
   ```

5. **运行数据库迁移**
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

6. **创建管理员账户**
   ```bash
   docker-compose exec backend python scripts/create_admin.py
   ```

---

## 配置说明

### 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | 是 | SQLite | 数据库连接字符串 |
| `SECRET_KEY` | 是 | - | JWT 签名密钥 |
| `ENCRYPTION_KEY` | 是 | - | 供应商 Key 加密密钥（32字符） |
| `REGISTRATION_MODE` | 否 | open | 注册模式：open/approval/restricted |
| `ALLOWED_EMAIL_DOMAINS` | 否 | - | 允许注册的邮箱域名（逗号分隔） |
| `DEFAULT_MONTHLY_QUOTA_USD` | 否 | 10.00 | 默认月度额度（USD） |
| `DEFAULT_RPM_LIMIT` | 否 | 30 | 默认每分钟请求数限制 |
| `DEFAULT_MAX_KEYS` | 否 | 5 | 默认每个用户最多 Key 数 |

### 注册模式说明

| 模式 | 说明 |
|------|------|
| `open` | 任何人都可以注册 |
| `approval` | 注册后需要管理员审核 |
| `restricted` | 只有指定域名的邮箱可以注册 |

---

## models.dev 同步配置

### 概述

LLM Token Manager 使用 [models.dev](https://models.dev) 作为模型元数据的单一真相来源（SSOT），自动获取：
- 模型定价（输入/输出/缓存 Token）
- 模型能力（上下文窗口、多模态、工具调用等）
- 新模型发布

### 同步机制

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ models.dev  │ ──► │ LTM Gateway  │ ──► │  PostgreSQL │
│  (远程源)   │     │  (缓存合并)  │     │  (持久化)   │
└─────────────┘     └──────────────┘     └─────────────┘
       │                   │
       │   24小时缓存      │  本地覆盖
       │   自动过期        │  优先级更高
       └───────────────────┘
```

### 配置合并优先级

```
优先级：本地覆盖 > 本地配置 > models.dev 数据

示例：
models.dev 定价: input=3.5, output=15.0
本地覆盖:       input=3.0
───────────────────────────────
最终生效:       input=3.0, output=15.0
```

### 手动同步

**通过 API 同步**：
```bash
# 同步所有供应商
curl -X POST https://llm.yourcompany.com/api/admin/models/sync \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{}'

# 强制刷新缓存
curl -X POST https://llm.yourcompany.com/api/admin/models/sync \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"force_refresh": true}'

# 只同步指定供应商
curl -X POST https://llm.yourcompany.com/api/admin/models/sync \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"provider_id": "anthropic"}'
```

**通过管理后台同步**：
1. 登录管理后台
2. 进入「系统设置」→「模型同步」
3. 点击「立即同步」按钮

### 自动同步（推荐）

配置定时任务，每天自动同步：

**使用 cron**：
```bash
# 编辑 crontab
crontab -e

# 添加每天凌晨 3 点同步
0 3 * * * curl -X POST http://localhost:8000/api/admin/models/sync -H "Authorization: Bearer <token>" -d '{}'
```

**使用 Docker 容器内定时任务**：
```yaml
# docker-compose.yml
services:
  sync-scheduler:
    image: curlimages/curl
    command: >
      sh -c "while true; do
        sleep 86400;
        curl -X POST http://backend:8000/api/admin/models/sync
          -H 'Authorization: Bearer $ADMIN_TOKEN'
          -d '{}';
      done"
```

### 离线环境配置

如果服务器无法访问外网：

1. **手动下载 models.dev 数据**
   ```bash
   curl -o models-dev-api.json https://models.dev/api.json
   ```

2. **配置本地文件源**
   ```python
   # config.py 添加
   MODELS_DEV_LOCAL_FILE = "/path/to/models-dev-api.json"
   ```

3. **导入到数据库**
   ```bash
   python scripts/import_models_dev.py models-dev-api.json
   ```

---

## 生产部署

### HTTPS 配置

推荐使用 Nginx 反向代理：

```nginx
server {
    listen 443 ssl http2;
    server_name llm.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/llm.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/llm.yourcompany.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### 数据库备份

```bash
# PostgreSQL 备份
pg_dump -U ltm -d llm_manager > backup_$(date +%Y%m%d).sql

# 恢复
psql -U ltm -d llm_manager < backup_20260304.sql
```

### 高可用部署

```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      replicas: 2
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    # 使用外部 PostgreSQL 集群
```

---

## 故障排查

### 常见问题

#### 1. models.dev 同步失败

**症状**：`POST /api/admin/models/sync` 返回错误

**排查步骤**：
```bash
# 检查网络连接
curl -I https://models.dev/api.json

# 检查日志
docker-compose logs backend | grep models_dev

# 检查缓存状态
docker-compose exec backend python -c "
from services.models_dev_service import get_models_dev_service
service = get_models_dev_service()
print(f'Cache: {service._cache is not None}')
print(f'Expires: {service._cache_expires}')
"
```

#### 2. 供应商 Key 加密错误

**症状**：创建供应商时报 "Encryption key must be 32 characters"

**解决**：
```bash
# 确保 ENCRYPTION_KEY 正好 32 字符
echo -n "your-encryption-key-32-chars!!!" | wc -c
# 输出应该是 32
```

#### 3. 数据库迁移失败

**症状**：`alembic upgrade head` 报错

**解决**：
```bash
# 检查当前版本
alembic current

# 查看迁移历史
alembic history

# 回滚到上一版本
alembic downgrade -1

# 重新迁移
alembic upgrade head
```

### 日志查看

```bash
# 查看后端日志
docker-compose logs -f backend

# 查看 PostgreSQL 日志
docker-compose logs -f postgres

# 导出最近 1000 行日志
docker-compose logs --tail=1000 backend > backend.log
```

---

*最后更新：2026-03-04*
