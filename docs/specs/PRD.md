# LLM Token Manager — 项目需求文档 (PRD)

> **版本**: v1.2（新增 Git 工作流与测试规范）  
> **日期**: 2026-02-26  
> **状态**: 草稿  
> **开发工具**: OpenCode / Claude Code  

---

## 1. 项目概述

### 1.1 背景与问题

团队规模 20–50 人，同时使用 OpenAI (GPT)、Anthropic (Claude)、国内模型（通义千问/文心一言等）多家大模型服务。团队成员既有通过代码 API 调用的开发者，也有通过聊天界面使用的非技术人员。目前存在以下核心痛点：

- **API Key 分散管理**：各人各自使用不同的 Key，难以统一管控，存在泄露风险
- **用量不可见**：无法知道谁用了多少 token，无法归因到人
- **成本失控**：没有预算上限，月底账单经常超出预期
- **多供应商切换麻烦**：不同模型接入方式不一样，缺乏统一抽象

### 1.2 解决方案

构建一个 **LLM Gateway（大模型网关）**，作为团队与所有大模型供应商之间的统一中间层。用户自助注册后获得平台分发的 API Key，在自己的应用中将请求指向网关即可使用所有模型。网关负责鉴权、计量、限额和日志记录。

### 1.3 系统架构总览

```
团队成员                          外部服务
────────                          ────────

开发者 (API) ────┐              ┌─── OpenAI
  │ 平台Key鉴权     │              │
聊天界面 (Web) ───┼── [Gateway] ─┼─── Anthropic
  │ 平台Key鉴权     │     │        │
管理员 (Dashboard) ─┘     │        └─── 国内模型
  │ JWT登录           │
                     [数据库]
               用户/Key/日志/额度
```

### 1.4 用户使用流程总览

```
用户注册账号         登录管理后台         创建平台 Key
(自助注册)    ───→  (账号密码)    ───→  (命名为"项目A")
                                             │
                                             ↓
                                     获得 Key（仅显示一次）
                                  ltm-sk-a3f8b2c1d4e5...
                                             │
                                             ↓
                              在代码中配置网关地址 + Key
                              base_url: https://llm.xxx.com/v1
                              api_key:  ltm-sk-a3f8b2c1d4e5...
                                             │
                                             ↓
                                  像平常一样调用即可
```

**关键设计决策：**

- 用户自助注册，无需 Admin 主动创建账号
- 每个用户可创建多个平台 Key，每个 Key 可命名（如"项目A""本地调试"），方便区分用途
- Key 创建后仅显示一次完整值，之后只展示后 4 位（与主流平台一致的安全实践）
- MVP 阶段 Key 默认不过期，支持手动删除/吊销；Phase 2 再加可选有效期
- 所有用量按 Key 维度记录，同时归属到用户维度汇总

### 1.5 技术栈推荐

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 后端框架 | Python + FastAPI | 异步高性能，最适合代理场景 |
| 数据库 | PostgreSQL | 生产用；开发期可先用 SQLite |
| ORM | SQLAlchemy + Alembic | 数据建模与迁移 |
| 前端管理后台 | React + Ant Design | 组件丰富，适合后台类项目 |
| 前端聊天界面 | React（第二期） | MVP 不包含，优先做网关和管理后台 |
| 部署 | Docker + Docker Compose | 一键启动，环境一致 |
| 认证 | JWT Token | 轻量级，无需外部依赖 |

---

## 2. 版本规划

| 阶段 | 周期 | 目标 | 核心交付物 |
|------|------|------|-----------|
| **MVP (Phase 1)** | 1–2 周 | 跑通核心链路 | 自助注册 + 多Key + API 网关 + 用量统计 + 额度控制 + 管理后台 |
| Phase 2 | 3–4 周 | 体验完善 | 内置聊天界面 + 审计日志 + 告警通知 + Key 可选有效期 |
| Phase 3 | 5–6 周 | 规模化 | 部门/项目维度 + SSO集成 + 模型路由策略 |

> **本文档专注于 MVP (Phase 1) 的详细需求定义。**

---

## 3. 用户角色定义

| 角色 | 权限范围 | 典型用户 |
|------|----------|----------|
| **Admin（管理员）** | 全部权限：管理用户、供应商 Key、额度、查看全局统计、审批注册 | 技术负责人、团队 Leader |
| **User（普通用户）** | 自助注册、创建/管理自己的平台 Key、查看自己的用量统计 | 开发者、业务人员 |

---

## 4. MVP 功能模块详细设计

### 4.1 模块一：用户注册与认证（User & Auth）

#### 4.1.1 自助注册

用户通过管理后台的注册页面自助创建账号。注册流程：

1. 用户填写用户名、邮箱、密码
2. 系统创建账号，角色默认为 User，分配默认月度额度
3. 注册成功后自动登录，跳转到个人后台

**注册审核策略（可配置）：**

- **默认模式**：注册后立即可用（适合团队内部使用）
- **可选模式**：注册后需 Admin 审批激活（适合对外开放时）
- **可选模式**：限制只允许特定邮箱后缀注册（如 `@yourcompany.com`）

#### 4.1.2 登录机制

管理后台使用账号密码 + JWT 登录。API 调用使用平台 Key（Bearer Token）鉴权，无需登录流程。两套认证体系独立运行：

| 场景 | 认证方式 | 凭证载体 |
|------|----------|----------|
| 管理后台操作 | 账号密码登录 | JWT Token（存 localStorage，2h 过期） |
| API 调用大模型 | 平台 Key 鉴权 | Bearer Token: `ltm-sk-xxxx` |

---

### 4.2 模块二：平台 Key 管理（User API Key Management）

每个用户可创建多个平台 Key，用于不同项目或应用场景。

#### 4.2.1 Key 生命周期

```
创建 Key          使用中          删除/吊销
  │                 │                │
  ↓                 ↓                ↓
命名 + 生成   ───→  active   ───→  revoked
仅显示一次完整值        │                │
                   Admin也可强制吊销   关联日志保留
```

#### 4.2.2 功能要求

**User 可以：**

- 创建新 Key：填写名称（如"项目A-后端""本地调试"），系统生成 `ltm-sk-` 前缀的 Key
- 查看 Key 列表：显示名称、创建时间、后 4 位、状态、最后使用时间
- 删除/吊销 Key：立即失效，不可恢复
- 查看单个 Key 的用量统计：某个 Key 的调用次数、token 用量、费用

**Admin 额外可以：**

- 查看所有用户的 Key 列表
- 强制吊销任何用户的 Key（安全事件时使用）
- 设置每个用户可创建的最大 Key 数量（默认 5 个）

#### 4.2.3 Key 格式与安全

- **Key 格式**：`ltm-sk-{32位随机字符}`，如 `ltm-sk-a3f8b2c1d4e56789abcdef0123456789ab`
- `ltm-sk-` 前缀用于让用户明确区分"这是平台 Key 而非供应商 Key"
- 数据库中存储 Key 的 **SHA-256 哈希值**（而非明文），验证时对传入 Key 做哈希后比对
- 创建时返回完整 Key **仅一次**，之后无法再次获取——与 GitHub Personal Access Token 机制一致
- MVP 阶段 Key 不设自动过期，支持手动吊销；Phase 2 加入可选有效期字段

#### 4.2.4 用户代码示例（文档中提供给用户参考）

**Python (OpenAI SDK)：**

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://llm.yourcompany.com/v1",
    api_key="ltm-sk-a3f8b2c1d4e5..."  # 你的平台 Key
)

response = client.chat.completions.create(
    model="gpt-4o",  # 或 claude-sonnet-4-20250514, qwen-plus 等
    messages=[{"role": "user", "content": "你好"}]
)
```

**curl：**

```bash
curl https://llm.yourcompany.com/v1/chat/completions \
  -H "Authorization: Bearer ltm-sk-a3f8b2c1d4e5..." \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"你好"}]}'
```

---

### 4.3 模块三：API 代理网关（Gateway Proxy）

网关是整个系统的核心，提供与 OpenAI Chat Completions API 兼容的统一端点。

#### 4.3.1 统一接入端点

```
POST /v1/chat/completions

Headers:
  Authorization: Bearer ltm-sk-xxxx  # 用户的平台 Key

Body:
{
  "model": "gpt-4o | claude-sonnet-4-20250514 | qwen-plus | ...",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": true/false
}
```

#### 4.3.2 模型路由逻辑

网关根据请求中的 `model` 字段自动路由到对应的供应商：

- model 以 `gpt-` 开头 → 转发到 OpenAI
- model 以 `claude-` 开头 → 转发到 Anthropic
- model 以 `qwen-` 开头 → 转发到通义千问
- model 以 `ernie-` 开头 → 转发到文心一言

对于非 OpenAI 供应商，网关需要做请求/响应格式转换（尤其是 Anthropic 的 Messages API 格式与 OpenAI 不同）。

#### 4.3.3 请求处理流程

每个请求经过以下 pipeline：

1. **鉴权**：校验平台 Key，确认用户身份和 Key 状态
2. **额度检查**：查询用户剩余额度（用户维度），不足则拒绝（429）
3. **模型权限检查**：确认用户有权使用请求的模型
4. **模型路由**：根据 model 字段匹配供应商
5. **请求转换**：将统一格式转为供应商特定格式
6. **转发请求**：用 Admin 配置的供应商 API Key 调用供应商
7. **响应转换**：将供应商响应统一为 OpenAI 格式返回
8. **计量记录**：异步记录 token 用量、成本、耗时（同时记录 user_id 和 key_id）

#### 4.3.4 流式响应支持

必须支持 SSE (Server-Sent Events) 流式输出。网关从供应商接收流式响应后，实时转发给客户端，并在流结束后汇总 token 用量。

---

### 4.4 模块四：供应商 Key 管理（Provider Key Management，Admin）

> **注意区分**："平台 Key"是发给用户的，"供应商 Key"是 Admin 配置的各家大模型的原始 API Key。用户永远接触不到供应商 Key。

#### 4.4.1 功能要求

1. 每个供应商支持配置多个 API Key（负载均衡/备份）
2. Key 存储必须加密（AES-256），数据库中不存储明文
3. Admin 只能看到 Key 的后 4 位，不能查看完整 Key
4. 支持标记 Key 状态：启用 / 禁用 / 已过期
5. 支持为每个 Key 配置每分钟请求限制 (RPM)，避免触发供应商限流

#### 4.4.2 供应商配置模型

每个供应商需要配置：

| 字段 | 说明 | 示例 |
|------|------|------|
| provider_name | 供应商名称 | openai / anthropic / qwen / ernie |
| base_url | API 基础地址 | `https://api.openai.com/v1` |
| api_keys[] | 密钥列表（AES-256 加密存储） | sk-xxxx... |
| models[] | 支持的模型列表 | `["gpt-4o", "gpt-4o-mini"]` |
| rpm_limit | 每个 Key 的 RPM 上限 | 60 |
| enabled | 是否启用 | true/false |

---

### 4.5 模块五：用量统计与计费（Usage & Billing）

#### 4.5.1 请求日志记录

每次 API 调用异步记录以下信息（同时包含 user_id 和 key_id，支持双维度查询）：

| 字段 | 类型 | 说明 |
|------|------|------|
| request_id | UUID | 唯一请求标识 |
| user_id | FK | 调用用户 |
| key_id | FK | 使用的平台 Key |
| model | String | 使用的模型名称 |
| provider | String | 供应商名称 |
| prompt_tokens | Integer | 输入 token 数 |
| completion_tokens | Integer | 输出 token 数 |
| total_tokens | Integer | 总 token 数 |
| cost_usd | Decimal | 本次调用估算费用 (USD) |
| latency_ms | Integer | 响应耗时（毫秒） |
| status | Enum | success / error / rate_limited / quota_exceeded |
| created_at | Timestamp | 请求时间 |

#### 4.5.2 费用计算

网关内置各模型的单价表（管理员可配置）：

```
cost = (prompt_tokens * input_price_per_1k / 1000)
     + (completion_tokens * output_price_per_1k / 1000)
```

#### 4.5.3 统计看板

**Admin 视角：**

- 全局统计：今日/本周/本月总用量、总费用、请求数
- 用户排名：按用量/费用排序的 Top N 用户
- 模型分布：各模型的使用占比
- 趋势图：近 7天/30天的用量趋势

**User 视角：**

- 个人总统计：自己的总用量、费用、剩余额度
- 按 Key 维度统计：每个 Key 的用量分布（帮助用户了解哪个项目用得多）
- 调用历史：最近的调用记录列表（不包含对话内容）

---

### 4.6 模块六：额度与限流控制（Quota & Rate Limiting）

#### 4.6.1 用户额度

额度按**用户维度**设置（而非按 Key），用户同一账号下所有 Key 的用量合并计算：

- **月度额度（USD）**：超额后请求被拒绝，返回 429 + 明确错误信息
- **每分钟请求限制 (RPM)**：防止单个用户占用过多资源
- **可用模型白名单**：限制用户只能使用特定模型（例如实习生只能用 gpt-4o-mini）

新注册用户的默认额度由 Admin 在系统配置中统一设置。

#### 4.6.2 额度重置策略

月度额度每月 1 号自动重置。未用完的额度不累计到下月。管理员可手动调整某个用户的当月额度。

#### 4.6.3 超额响应示例

```json
HTTP 429 Too Many Requests
{
  "error": {
    "type": "quota_exceeded",
    "message": "您的月度额度已用尽，请联系管理员。",
    "quota_used": 50.00,
    "quota_limit": 50.00,
    "resets_at": "2026-04-01T00:00:00Z"
  }
}
```

---

### 4.7 模块七：管理后台 Dashboard

管理后台采用 Web 单页应用 (SPA)，同时服务 Admin 和 User 两种角色。

#### 4.7.1 页面清单

| 页面 | 访问角色 | 核心功能 |
|------|----------|----------|
| 注册页 | 所有人 | 账号自助注册 |
| 登录页 | 所有人 | 账号密码登录 |
| 仪表盘总览 | Admin | 全局用量图表、今日概览、Top 用户 |
| 用户管理 | Admin | 用户列表、设置额度、禁用用户、审批注册 |
| 供应商 Key 管理 | Admin | 配置供应商、添加/禁用 Key |
| 模型单价配置 | Admin | 配置各模型的 token 单价 |
| 调用日志 | Admin | 全局调用记录，支持筛选 |
| 我的 Key | User | 创建/查看/删除平台 Key |
| 我的用量 | User | 个人统计、按 Key 维度、调用历史 |

---

## 5. 核心数据模型

以下是 MVP 阶段的核心数据表设计：

### 5.1 users 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 用户 ID |
| username | VARCHAR(50) | 用户名，唯一 |
| email | VARCHAR(100) | 邮箱，唯一 |
| password_hash | VARCHAR(255) | 密码哈希 (bcrypt) |
| role | ENUM | admin / user |
| monthly_quota_usd | DECIMAL(10,2) | 月度额度 (USD) |
| rpm_limit | INTEGER | 每分钟请求上限 |
| allowed_models | JSON | 可用模型白名单，null 表示不限制 |
| max_keys | INTEGER | 可创建的最大 Key 数量，默认 5 |
| is_active | BOOLEAN | 是否启用（支持审批模式） |
| created_at | TIMESTAMP | 注册时间 |

### 5.2 user_api_keys 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | Key ID |
| user_id | UUID (FK) | 关联用户 |
| name | VARCHAR(50) | Key 名称（用户自定义，如"项目A-后端"） |
| key_hash | VARCHAR(64) | Key 的 SHA-256 哈希值（用于验证） |
| key_prefix | VARCHAR(12) | Key 前缀（ltm-sk-） |
| key_suffix | VARCHAR(4) | Key 后 4 位（用于展示） |
| status | ENUM | active / revoked |
| last_used_at | TIMESTAMP | 最后使用时间（每次调用时更新） |
| created_at | TIMESTAMP | 创建时间 |
| revoked_at | TIMESTAMP | 吊销时间（如已吊销） |

**索引说明**：key_hash 建唯一索引（快速鉴权查找），user_id 建普通索引（查询用户的 Key 列表）。

### 5.3 providers 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 供应商 ID |
| name | VARCHAR(50) | 供应商名称（openai/anthropic/qwen/ernie） |
| base_url | VARCHAR(255) | API 基础地址 |
| enabled | BOOLEAN | 是否启用 |
| config | JSON | 额外配置（请求头等） |

### 5.4 provider_api_keys 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 密钥 ID |
| provider_id | UUID (FK) | 关联供应商 |
| encrypted_key | TEXT | AES-256 加密存储的供应商 API Key |
| key_suffix | VARCHAR(4) | Key 后 4 位，用于展示 |
| rpm_limit | INTEGER | 该 Key 的 RPM 上限 |
| status | ENUM | active / disabled / expired |
| created_at | TIMESTAMP | 创建时间 |

### 5.5 model_pricing 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| provider_id | UUID (FK) | 关联供应商 |
| model_name | VARCHAR(100) | 模型名称（如 gpt-4o） |
| input_price_per_1k | DECIMAL(10,6) | 输入 token 单价 ($/1K tokens) |
| output_price_per_1k | DECIMAL(10,6) | 输出 token 单价 ($/1K tokens) |

### 5.6 request_logs 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 请求 ID |
| user_id | UUID (FK) | 调用用户 |
| key_id | UUID (FK) | 使用的平台 Key |
| provider_id | UUID (FK) | 供应商 |
| model | VARCHAR(100) | 模型名称 |
| prompt_tokens | INTEGER | 输入 token |
| completion_tokens | INTEGER | 输出 token |
| total_tokens | INTEGER | 总 token |
| cost_usd | DECIMAL(10,6) | 费用 (USD) |
| latency_ms | INTEGER | 耗时 |
| status | ENUM | success / error / rate_limited / quota_exceeded |
| error_message | TEXT | 错误信息（失败时记录） |
| created_at | TIMESTAMP | 请求时间，建索引 |

### 5.7 monthly_usage 表（汇总表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| user_id | UUID (FK) | 用户 |
| year_month | VARCHAR(7) | 归属月份（如 2026-03） |
| total_tokens | BIGINT | 本月总 token |
| total_cost_usd | DECIMAL(10,4) | 本月总费用 |
| request_count | INTEGER | 本月请求数 |

每次请求完成后异步更新该表，避免每次查看额度时都要聚合 request_logs。

---

## 6. API 接口设计（后端 REST API）

所有接口返回 JSON 格式。"Auth" 列标注认证方式。

### 6.1 认证接口

| 方法 | 路径 | Auth | 说明 |
|------|------|------|------|
| POST | `/api/auth/register` | 无 | 自助注册 |
| POST | `/api/auth/login` | 无 | 登录，返回 JWT |
| POST | `/api/auth/refresh` | JWT | 刷新 JWT Token |

### 6.2 平台 Key 管理接口（User 自己的 Key）

| 方法 | 路径 | Auth | 说明 |
|------|------|------|------|
| GET | `/api/user/keys` | JWT | 我的 Key 列表 |
| POST | `/api/user/keys` | JWT | 创建新 Key（传入 name），返回完整 Key（仅一次） |
| DELETE | `/api/user/keys/{id}` | JWT | 吊销 Key |
| GET | `/api/user/keys/{id}/stats` | JWT | 某个 Key 的用量统计 |

### 6.3 用户管理接口 (Admin)

| 方法 | 路径 | Auth | 说明 |
|------|------|------|------|
| GET | `/api/admin/users` | JWT+Admin | 用户列表，支持分页 |
| PUT | `/api/admin/users/{id}` | JWT+Admin | 编辑用户信息/额度/角色 |
| PATCH | `/api/admin/users/{id}/status` | JWT+Admin | 启用/禁用用户（审批注册） |
| DELETE | `/api/admin/users/{id}` | JWT+Admin | 删除用户 |
| GET | `/api/admin/users/{id}/keys` | JWT+Admin | 查看用户的所有 Key |
| DELETE | `/api/admin/users/{id}/keys/{kid}` | JWT+Admin | 强制吊销用户的某个 Key |

### 6.4 供应商与 Key 管理接口 (Admin)

| 方法 | 路径 | Auth | 说明 |
|------|------|------|------|
| GET | `/api/admin/providers` | JWT+Admin | 供应商列表 |
| POST | `/api/admin/providers` | JWT+Admin | 添加供应商 |
| PUT | `/api/admin/providers/{id}` | JWT+Admin | 编辑供应商配置 |
| POST | `/api/admin/providers/{id}/keys` | JWT+Admin | 添加供应商 API Key |
| DELETE | `/api/admin/providers/{id}/keys/{kid}` | JWT+Admin | 删除供应商 API Key |
| GET | `/api/admin/model-pricing` | JWT+Admin | 模型单价列表 |
| PUT | `/api/admin/model-pricing/{id}` | JWT+Admin | 更新模型单价 |

### 6.5 统计接口

| 方法 | 路径 | Auth | 说明 |
|------|------|------|------|
| GET | `/api/admin/stats/overview` | JWT+Admin | 全局概览统计 |
| GET | `/api/admin/stats/users` | JWT+Admin | 用户用量排名 |
| GET | `/api/admin/stats/trends` | JWT+Admin | 用量趋势数据 |
| GET | `/api/admin/logs` | JWT+Admin | 调用日志列表（分页+筛选） |
| GET | `/api/user/me/stats` | JWT | 当前用户个人统计 |
| GET | `/api/user/me/logs` | JWT | 当前用户调用历史 |

### 6.6 代理网关接口（核心）

| 方法 | 路径 | Auth | 说明 |
|------|------|------|------|
| POST | `/v1/chat/completions` | 平台Key | 统一对话接口（兼容 OpenAI 格式） |
| GET | `/v1/models` | 平台Key | 当前用户可用的模型列表 |

---

## 7. 非功能性需求

### 7.1 性能

- 网关代理增加的延迟不超过 50ms
- 支持至少 50 并发请求
- 统计看板加载时间不超过 2秒

### 7.2 安全

- 供应商 API Key 必须 AES-256 加密存储，加密密钥通过环境变量注入
- 平台 Key 以 SHA-256 哈希存储，数据库中不存明文
- 用户密码使用 bcrypt 哈希
- 所有管理接口需 JWT 认证 + Admin 角色校验
- 供应商 API Key 在日志中不得出现

### 7.3 可部署性

- 提供 Docker Compose 一键部署方案
- 支持通过环境变量配置所有敏感信息
- 提供数据库迁移脚本（Alembic）

### 7.4 可观测性

- 网关请求日志输出到 stdout（方便 Docker 日志收集）
- 提供 `/health` 健康检查端点

---

## 8. 项目目录结构建议（Claude Code 友好）

以下目录结构优化了模块边界，适合用 Claude Code 逐模块开发：

```
llm-token-manager/
├── docker-compose.yml
├── .env.example                 # 环境变量模板
├── .env.test                    # 测试专用环境变量
├── .gitignore
├── backend/
│   ├── main.py                   # FastAPI 入口
│   ├── config.py                 # 配置加载
│   ├── database.py               # 数据库连接
│   ├── models/                   # SQLAlchemy 模型
│   │   ├── user.py
│   │   ├── user_api_key.py       # 平台 Key 模型
│   │   ├── provider.py
│   │   ├── provider_api_key.py
│   │   ├── request_log.py
│   │   └── model_pricing.py
│   ├── routers/                  # API 路由
│   │   ├── auth.py               # 登录 + 注册
│   │   ├── user_keys.py          # 用户 Key 管理
│   │   ├── user.py               # 用户个人统计
│   │   ├── admin.py
│   │   └── gateway.py            # 核心代理路由
│   ├── services/                 # 业务逻辑
│   │   ├── proxy.py              # 请求转发核心逻辑
│   │   ├── providers/            # 各供应商适配器
│   │   │   ├── base.py
│   │   │   ├── openai_adapter.py
│   │   │   ├── anthropic_adapter.py
│   │   │   └── qwen_adapter.py
│   │   ├── user_key_service.py   # Key 生成/验证/吊销
│   │   ├── quota.py              # 额度检查与更新
│   │   ├── key_manager.py        # 供应商 Key 加解密与轮转
│   │   └── billing.py            # 计费逻辑
│   ├── middleware/                # 中间件
│   │   ├── auth.py               # JWT + 平台Key 双模式认证
│   │   └── rate_limiter.py       # 限流中间件
│   ├── tests/                    # 自动化测试
│   │   ├── conftest.py           # 全局 fixtures（TestClient, 测试DB等）
│   │   ├── test_auth.py          # 注册/登录测试
│   │   ├── test_user_keys.py     # 平台 Key 管理测试
│   │   ├── test_admin.py         # Admin 接口测试
│   │   ├── test_gateway.py       # 网关代理测试（mock 供应商）
│   │   ├── test_quota.py         # 额度与限流测试
│   │   └── test_billing.py       # 计费逻辑测试
│   ├── alembic/                  # 数据库迁移
│   ├── requirements.txt
│   └── pytest.ini                # pytest 配置
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Register.jsx
│   │   │   ├── Login.jsx
│   │   │   ├── MyKeys.jsx            # 用户 Key 管理页
│   │   │   ├── MyUsage.jsx
│   │   │   ├── AdminDashboard.jsx
│   │   │   ├── AdminUsers.jsx
│   │   │   └── AdminProviders.jsx
│   │   ├── components/
│   │   └── api/                  # API 调用层
│   └── package.json
└── docs/
    └── PRD.md
```

---

## 9. 开发策略建议（含 Git 工作流与测试）

建议按以下顺序逐模块开发，每步都可独立验证。每个 Step 使用独立 Git 分支，合并前所有测试必须通过。

### Step 1: 项目初始化 → 分支 `step1/project-init`

创建项目结构、docker-compose.yml、.env.example、FastAPI 入口（含 /health）、requirements.txt（含 pytest 等测试依赖）、pytest.ini、tests/conftest.py。

**验证**：`/health` 返回 200，`python -m pytest` 能正常运行（此时可以是 0 个测试）。

**提交后**：合并到 main，打 tag `v0.1-init`。

### Step 2: 注册/登录 → 分支 `step2/auth`

实现 users 表、注册接口、登录接口、JWT 中间件。**同时编写 test_auth.py**。

**测试覆盖**：注册成功/失败、登录成功/失败、JWT 过期/无效、角色权限（详见第 11 章）。

**验证**：`python -m pytest tests/test_auth.py -v` 全部通过 → 合并到 main，打 tag `v0.2-auth`。

### Step 3: 平台 Key 管理 → 分支 `step3/user-keys`

实现 user_api_keys 表、Key 创建/列表/吊销接口。**同时编写 test_user_keys.py**。

**测试覆盖**：创建/列表/吊销、数量限制、Key 维度统计。

**验证**：全部测试通过（含之前的 test_auth.py）→ 合并到 main，打 tag `v0.3-keys`。

### Step 4: 供应商 Key 管理 → 分支 `step4/provider-keys`

实现 providers / provider_api_keys 表和 Admin 管理接口，包含 AES-256 加密存储。**同时编写 test_admin.py**。

**测试覆盖**：供应商 CRUD、Key CRUD、单价配置、403 权限校验。

**验证**：全部测试通过 → 合并到 main，打 tag `v0.4-providers`。

### Step 5: 网关代理核心 → 分支 `step5/gateway`

实现 `/v1/chat/completions` 代理逻辑。先做 OpenAI 转发，再扩展 Anthropic 和国内模型。**同时编写 test_gateway.py**，所有供应商调用使用 mock。

**测试覆盖**：鉴权、模型路由、请求/响应转换、流式响应、错误处理、模型白名单。

**验证**：全部测试通过 → 合并到 main，打 tag `v0.5-gateway`。

### Step 6: 计量与额度 → 分支 `step6/billing-quota`

实现请求日志记录（含 key_id）、费用计算、额度检查、月度汇总。**同时编写 test_quota.py 和 test_billing.py**。

**测试覆盖**：额度检查/扣减/超额拒绝/月度重置/RPM 限流、日志完整性、费用精度。

**验证**：全部测试通过 → 合并到 main，打 tag `v0.6-billing`。

### Step 7: 管理后台前端 → 分支 `step7/frontend`

实现 React 管理后台，包含注册页、登录页、"我的 Key" 页面、Admin 页面。

**验证**：手动 E2E 验证核心流程（注册 → 登录 → 创建 Key → 查看统计），后端全部测试仍然通过 → 合并到 main，打 tag `v0.7-mvp`。

---

## 10. Phase 2 功能预告（仅作参考）

以下功能计划在 MVP 之后实现：

- **内置聊天界面**：提供类似 ChatGPT 的 Web UI，非技术人员可直接使用
- **Key 可选有效期**：创建 Key 时可设置过期时间，到期自动失效
- **审计日志**：记录对话内容（需考虑隐私合规）
- **告警通知**：额度使用超过 80% 时通知用户和 Admin（邮件/飞书/钉钉）
- **部门维度**：按部门/项目组管理用户和额度
- **SSO 集成**：对接企业 LDAP / OAuth2
- **智能路由**：根据成本/性能自动选择最优模型

---

## 11. 自动化测试规范

### 11.1 测试框架与工具

| 工具 | 用途 |
|------|------|
| pytest | 测试框架 |
| pytest-asyncio | 异步测试支持 |
| httpx | 异步 HTTP 客户端（测试 FastAPI） |
| pytest-cov | 覆盖率报告 |
| unittest.mock | Mock 外部依赖（供应商 API） |

requirements.txt 中需包含以上测试依赖。

### 11.2 测试数据库策略

- 使用 SQLite 内存数据库 `sqlite+aiosqlite:///:memory:`，无需外部依赖
- 每个测试函数独立 session + 自动回滚，测试之间互不影响
- 通过环境变量 `TESTING=true` 切换到测试数据库
- 测试中的供应商 API 调用全部使用 mock，**禁止发送真实请求**

### 11.3 conftest.py 全局 fixtures

`backend/tests/conftest.py` 必须提供以下 fixtures：

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ── 数据库 fixtures ──

@pytest_asyncio.fixture
async def db_session():
    """每个测试用例独立的数据库 session，测试后自动回滚"""
    # 使用 sqlite+aiosqlite:///:memory:
    # 每次创建全新的 engine 和表
    ...

@pytest_asyncio.fixture
async def client(db_session):
    """绑定了测试数据库的 httpx AsyncClient"""
    ...

# ── 用户 fixtures ──

@pytest_asyncio.fixture
async def test_user(db_session):
    """一个已注册的普通 User，返回 user 对象"""
    ...

@pytest_asyncio.fixture
async def test_admin(db_session):
    """一个已注册的 Admin，返回 user 对象"""
    ...

@pytest_asyncio.fixture
async def user_token(test_user):
    """普通用户的 JWT token 字符串"""
    ...

@pytest_asyncio.fixture
async def admin_token(test_admin):
    """Admin 用户的 JWT token 字符串"""
    ...

# ── Key fixtures ──

@pytest_asyncio.fixture
async def user_api_key(test_user, db_session):
    """为测试用户创建一个平台 Key，返回 (key_object, raw_key_string)"""
    ...

# ── Mock fixtures ──

@pytest.fixture
def mock_openai():
    """Mock OpenAI API 响应"""
    ...

@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API 响应"""
    ...
```

### 11.4 各模块测试用例清单

#### 11.4.1 test_auth.py — 注册/登录

| 测试函数 | 验证内容 | 预期结果 |
|----------|----------|----------|
| test_register_success | 正常注册 | 201，返回用户信息 + JWT |
| test_register_duplicate_username | 用户名重复 | 409 Conflict |
| test_register_duplicate_email | 邮箱重复 | 409 Conflict |
| test_register_weak_password | 密码少于 8 位 | 422 Validation Error |
| test_register_invalid_email | 邮箱格式错误 | 422 Validation Error |
| test_login_success | 正确账号密码 | 200，返回有效 JWT |
| test_login_wrong_password | 错误密码 | 401 Unauthorized |
| test_login_nonexistent_user | 不存在的用户 | 401 Unauthorized |
| test_login_disabled_user | 被禁用的用户 | 403 Forbidden |
| test_jwt_expired | 使用过期 JWT | 401 Unauthorized |
| test_jwt_invalid | 使用伪造 JWT | 401 Unauthorized |
| test_user_cannot_access_admin | 普通用户调 Admin 接口 | 403 Forbidden |

#### 11.4.2 test_user_keys.py — 平台 Key 管理

| 测试函数 | 验证内容 | 预期结果 |
|----------|----------|----------|
| test_create_key_success | 创建 Key 并命名 | 201，返回完整 Key（含 ltm-sk- 前缀） |
| test_create_key_name_required | 不传 name | 422 Validation Error |
| test_create_key_full_value_shown_once | 创建后再查列表 | 列表中只显示后 4 位 |
| test_list_keys_only_own | 用户 A 看不到用户 B 的 Key | 200，只有自己的 Key |
| test_revoke_key_success | 吊销自己的 Key | 200，状态变 revoked |
| test_revoked_key_cannot_call_api | 用已吊销 Key 调 /v1/chat/completions | 401 Unauthorized |
| test_max_keys_limit | 超过 max_keys 数量 | 400 或 429 |
| test_key_stats | 查看某 Key 的用量统计 | 200，返回该 Key 的统计数据 |

#### 11.4.3 test_admin.py — Admin 接口

| 测试函数 | 验证内容 | 预期结果 |
|----------|----------|----------|
| test_list_users | 用户列表分页 | 200，返回分页数据 |
| test_update_user_quota | 修改用户额度 | 200，额度已更新 |
| test_disable_user | 禁用用户 | 200，用户 is_active=false |
| test_delete_user | 删除用户 | 200/204 |
| test_add_provider | 添加供应商 | 201 |
| test_add_provider_key | 添加供应商 Key | 201，返回后 4 位 |
| test_provider_key_not_readable | 查看供应商 Key | 只显示后 4 位，无法获取完整值 |
| test_update_model_pricing | 修改模型单价 | 200 |
| test_user_cannot_access_any_admin_api | 普通用户调所有 Admin 接口 | 全部返回 403 |
| test_force_revoke_user_key | Admin 强制吊销用户 Key | 200，Key 状态变 revoked |

#### 11.4.4 test_gateway.py — 网关代理（核心，测试最密集）

| 测试函数 | 验证内容 | 预期结果 |
|----------|----------|----------|
| test_valid_key_passes_auth | 有效平台 Key 调用 | 200，返回模型响应 |
| test_invalid_key_rejected | 无效 Key | 401 |
| test_revoked_key_rejected | 已吊销 Key | 401 |
| test_route_to_openai | model="gpt-4o" | 请求转发到 OpenAI mock |
| test_route_to_anthropic | model="claude-sonnet-4-20250514" | 请求转发到 Anthropic mock |
| test_route_to_qwen | model="qwen-plus" | 请求转发到通义 mock |
| test_openai_request_format | 检查发给 OpenAI 的请求 | 格式正确 |
| test_anthropic_request_conversion | OpenAI 格式 → Anthropic Messages 格式 | 转换正确 |
| test_response_unified_format | 各供应商响应统一为 OpenAI 格式 | 格式一致 |
| test_stream_response | stream=true | SSE 流正确转发 |
| test_provider_error_handling | 供应商返回 500 | 网关返回友好错误信息 |
| test_model_whitelist_allowed | 用户有权的模型 | 200 |
| test_model_whitelist_blocked | 用户无权的模型 | 403 |
| test_unknown_model | model="nonexistent-model" | 400 或 404 |

#### 11.4.5 test_quota.py — 额度与限流

| 测试函数 | 验证内容 | 预期结果 |
|----------|----------|----------|
| test_within_quota_passes | 额度内请求 | 200 |
| test_exceed_quota_rejected | 超额请求 | 429 + quota_exceeded 错误体 |
| test_quota_deducted_after_request | 请求后额度减少 | monthly_usage 正确更新 |
| test_monthly_reset | 模拟跨月 | 额度恢复到满额 |
| test_admin_adjust_quota | Admin 临时加额度 | 用户可继续调用 |
| test_rpm_within_limit | RPM 限制内请求 | 200 |
| test_rpm_exceed_limit | 超过 RPM | 429 + rate_limited |

#### 11.4.6 test_billing.py — 计费逻辑

| 测试函数 | 验证内容 | 预期结果 |
|----------|----------|----------|
| test_request_log_created | 调用后生成日志 | request_logs 有新记录，字段完整 |
| test_log_contains_key_id | 日志包含 key_id | key_id 字段正确 |
| test_cost_calculation | token 数 × 单价 | cost_usd 计算正确 |
| test_monthly_usage_accumulated | 多次调用 | monthly_usage 累加正确 |
| test_different_keys_separate_stats | 同用户不同 Key | 各 Key 用量分别记录 |
| test_cost_decimal_precision | 小额调用 | 小数精度不丢失 |
| test_failed_request_logged | 失败请求 | 日志记录 status=error，不扣费 |

### 11.5 运行命令

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

### 11.6 覆盖率目标

- **routers/ 目录**：≥ 90%（每个接口都有测试）
- **services/ 目录**：≥ 85%（核心业务逻辑）
- **middleware/ 目录**：≥ 90%（认证和限流是安全关键路径）
- **整体**：≥ 80%

---

## 12. Git 工作流规范

### 12.1 分支策略

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

### 12.2 每个 Step 的 Git 流程

```bash
# 1. 从 main 创建分支
git checkout main
git checkout -b step2/auth

# 2. 开发中频繁提交（每次提交前运行测试）
cd backend && python -m pytest          # 确认通过
git add .
git commit -m "test(auth): add registration endpoint tests"

cd backend && python -m pytest          # 确认通过
git add .
git commit -m "feat(auth): implement registration endpoint"

# 3. Step 完成，合并回 main
git checkout main
git merge step2/auth
git tag v0.2-auth
```

### 12.3 Commit Message 规范（Conventional Commits）

格式：`<type>(<scope>): <description>`

| type | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(gateway): add OpenAI proxy endpoint` |
| `fix` | 修复 Bug | `fix(quota): fix monthly reset calculation` |
| `test` | 添加/修改测试 | `test(auth): add JWT expiration test` |
| `refactor` | 重构 | `refactor(proxy): extract provider adapter base class` |
| `docs` | 文档 | `docs: update API endpoint list in PRD` |
| `chore` | 构建/配置 | `chore: add docker-compose and .env.example` |

### 12.4 .gitignore 必须包含

```
# 环境变量（含敏感信息）
.env
.env.local
.env.production

# Python
__pycache__/
*.pyc
.pytest_cache/
htmlcov/
.coverage

# Node
node_modules/
dist/
build/

# IDE
.vscode/
.idea/

# 数据库
*.db
*.sqlite3

# 系统
.DS_Store
```

### 12.5 里程碑标签

| Tag | 对应 Step | 含义 |
|-----|-----------|------|
| v0.1-init | Step 1 | 项目骨架可运行 |
| v0.2-auth | Step 2 | 注册/登录可用 |
| v0.3-keys | Step 3 | 平台 Key 管理可用 |
| v0.4-providers | Step 4 | 供应商管理可用 |
| v0.5-gateway | Step 5 | 网关代理核心可用 |
| v0.6-billing | Step 6 | 计量与额度可用 |
| v0.7-mvp | Step 7 | MVP 完整可用 |

---

*文档结束*
