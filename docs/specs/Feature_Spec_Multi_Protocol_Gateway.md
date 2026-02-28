# Feature Spec: Anthropic Messages API 端点 — 支持 Agent 编程工具接入

> **文档类型**: Feature Spec（功能需求规格）  
> **版本**: v1.1（简化版，纯透传，不含协议转换）  
> **日期**: 2026-02-26  
> **关联**: LLM Token Manager PRD v1.2  
> **优先级**: P0（团队核心使用场景）  
> **预估工作量**: 3–5 天  

---

## 1. 背景与动机

### 1.1 问题

网关目前仅支持 **OpenAI 格式** `POST /v1/chat/completions`。但团队成员需要在 **Claude Code** 和 **OpenCode** 中通过平台 Key 使用 LLM，这些工具在 Anthropic provider 模式下调用的是 **Anthropic Messages API** 格式 `POST /v1/messages`。

### 1.2 关键简化条件

团队在 Claude Code 中使用的三家供应商 **全部原生支持 Anthropic Messages API**：

| 供应商 | 模型 | Anthropic 兼容端点 |
|--------|------|-------------------|
| Anthropic | Claude Sonnet / Opus | `https://api.anthropic.com` |
| 智谱 GLM | GLM-5 | `https://open.bigmodel.cn/api/anthropic` 或 `https://api.z.ai/api/anthropic` |
| MiniMax | MiniMax-M2.5 | MiniMax Anthropic 兼容端点 |

**因此，网关只需做纯透传代理**：根据 model 名称路由到对应的 Anthropic 兼容后端，请求和响应原样转发，不需要任何 Anthropic ↔ OpenAI 协议转换。

### 1.3 目标

新增 `POST /v1/messages` 端点，使平台 Key 可在以下场景中使用：

| 使用场景 | 入站协议 | 当前 → 目标 |
|----------|----------|------------|
| 聊天应用 / OpenAI SDK / OpenCode(OpenAI模式) | OpenAI 格式 | ✅ 已支持 |
| **Claude Code** | **Anthropic Messages** | ❌ → ✅ |
| **OpenCode（Anthropic provider 模式）** | **Anthropic Messages** | ❌ → ✅ |
| **Anthropic Python/TS SDK** | **Anthropic Messages** | ❌ → ✅ |

---

## 2. 架构设计

### 2.1 透传代理架构

```
                         ┌──────────────────────────────────┐
                         │        LLM Token Manager         │
                         │           Gateway                │
                         │                                  │
Claude Code ─────────────┤  POST /v1/messages               │
OpenCode (Anthropic) ────┤    │                             │
Anthropic SDK ───────────┤    ├── 鉴权（平台 Key）          │
                         │    ├── 额度检查                  │
                         │    ├── 模型路由                  │
                         │    │    │                        │
                         │    │    ├─ claude-* ──────────────┼──→ api.anthropic.com
                         │    │    ├─ glm-* ────────────────┼──→ open.bigmodel.cn/api/anthropic
                         │    │    └─ minimax-* ────────────┼──→ MiniMax Anthropic 端点
                         │    │                             │
                         │    ├── 替换鉴权头（平台Key→供应商Key）
                         │    ├── 转发 anthropic-version / anthropic-beta 头
                         │    ├── 原样代理请求和响应         │
                         │    └── 计量记录（异步）           │
                         │                                  │
聊天应用 / OpenAI SDK ───┤  POST /v1/chat/completions       │  ← 已有，不变
                         └──────────────────────────────────┘
```

核心特点：**零格式转换**。网关只做鉴权、路由、换 Key、计量，请求体和响应体原样透传。

### 2.2 请求处理 Pipeline

```
1. 接收 POST /v1/messages 请求
   │
2. 提取平台 Key（x-api-key 或 Authorization: Bearer）
   │
3. 鉴权：SHA-256 哈希后查库验证
   │
4. 额度检查：用户剩余额度 > 0？
   │
5. 模型路由：根据 body.model 确定供应商
   │   claude-sonnet-4-*  →  Anthropic
   │   claude-opus-*      →  Anthropic
   │   glm-5 / glm-4.*   →  智谱 GLM
   │   minimax-*          →  MiniMax
   │
6. 构造上游请求
   │   - URL = 供应商 Anthropic 兼容端点 + "/v1/messages"
   │   - 替换鉴权头：x-api-key = 供应商 Key（解密后）
   │   - 透传：anthropic-version, anthropic-beta, content-type
   │   - Body：原样转发，不修改
   │
7. 代理响应
   │   - stream=false：等待完整响应，提取 usage → 原样返回
   │   - stream=true：逐 chunk 转发 SSE，累积 usage
   │
8. 异步计量
   │   - 从响应的 usage 字段提取 input_tokens / output_tokens
   │   - 计算费用 = tokens × 对应模型单价
   │   - 写入 request_logs，更新 monthly_usage
```

---

## 3. 供应商配置扩展

### 3.1 providers 表变更

现有 `providers` 表需要新增一个字段，标识该供应商的 **API 协议类型**：

```sql
ALTER TABLE providers ADD COLUMN api_format VARCHAR(20) DEFAULT 'openai';
-- 可选值: 'openai' | 'anthropic'
```

| 供应商 | api_format | base_url |
|--------|-----------|----------|
| OpenAI | openai | https://api.openai.com |
| Anthropic | anthropic | https://api.anthropic.com |
| 智谱 GLM | anthropic | https://open.bigmodel.cn/api/anthropic |
| MiniMax | anthropic | MiniMax Anthropic 兼容端点 |
| 通义千问 | openai | https://dashscope.aliyuncs.com/compatible-mode |

### 3.2 Admin 管理界面变更

Admin 在添加/编辑供应商时，需要选择 API 格式：

- **OpenAI 格式**：请求走 `/v1/chat/completions`
- **Anthropic 格式**：请求走 `/v1/messages`

这决定了网关向上游转发时使用哪种端点路径和鉴权头格式。

---

## 4. API 端点详细设计

### 4.1 POST `/v1/messages` — Anthropic Messages 兼容端点

**认证**（两种方式均可）：
- `x-api-key: ltm-sk-xxx`（Anthropic SDK 默认）
- `Authorization: Bearer ltm-sk-xxx`（Claude Code ANTHROPIC_AUTH_TOKEN）

**必须透传的请求头**：
- `anthropic-version`（如 `2023-06-01`）
- `anthropic-beta`（如 `prompt-caching-2024-07-31` 等）
- `content-type`

**请求体**：原样透传，不解析不修改。典型结构：

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 4096,
  "system": "You are a helpful assistant.",
  "messages": [
    { "role": "user", "content": "Hello" }
  ],
  "stream": true
}
```

**响应**：原样返回供应商的 Anthropic 格式响应。

**错误响应**：必须使用 Anthropic 错误格式：

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "Invalid API key"
  }
}
```

错误类型映射：

| 场景 | HTTP 状态码 | error.type |
|------|-----------|------------|
| Key 无效 / 已吊销 | 401 | `authentication_error` |
| 非 Admin 访问管理接口 | 403 | `permission_error` |
| 模型不存在 / 未启用 | 404 | `not_found_error` |
| 额度超限 | 429 | `rate_limit_error` |
| RPM 超限 | 429 | `rate_limit_error` |
| 请求体格式错误 | 400 | `invalid_request_error` |
| 供应商返回错误 | 502 | `api_error` |

### 4.2 POST `/v1/messages/count_tokens`（Phase 2，暂不实现）

Claude Code 可能调用此端点，不实现时 Claude Code 会跳过，不影响核心功能。

---

## 5. 鉴权适配

### 5.1 修改认证中间件

`backend/middleware/auth.py` 的 Key 提取逻辑扩展为：

```python
def extract_platform_key(request) -> str:
    """按优先级提取平台 Key"""
    # 1. Authorization: Bearer xxx
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    # 2. x-api-key: xxx（Anthropic SDK 惯例）
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key

    raise AuthenticationError("Missing API key")
```

所有 API Key 鉴权端点（`/v1/chat/completions`、`/v1/messages`、`/v1/models`）共用此函数。

### 5.2 上游鉴权头替换

向供应商转发时，根据 `api_format` 设置不同的鉴权头：

| 供应商 api_format | 上游鉴权头 |
|-------------------|-----------|
| `openai` | `Authorization: Bearer {供应商Key}` |
| `anthropic` | `x-api-key: {供应商Key}` |

---

## 6. 用量计量

### 6.1 Token 提取

Anthropic 格式响应的 usage 字段：

```json
{
  "usage": {
    "input_tokens": 100,
    "output_tokens": 50,
    "cache_creation_input_tokens": 80,
    "cache_read_input_tokens": 20
  }
}
```

计量记录：
- `input_tokens` = `usage.input_tokens`
- `output_tokens` = `usage.output_tokens`
- `cost_usd` = input_tokens × input_price + output_tokens × output_price

> **Note**：`cache_creation_input_tokens` 和 `cache_read_input_tokens` 在响应中原样透传给客户端，但 MVP 阶段按普通 input token 计费，不单独计算缓存折扣价。

### 6.2 流式响应的 Token 提取

流式模式下，token 数量在最后的 `message_delta` 事件中：

```
event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":50}}
```

结合 `message_start` 事件中的 `usage.input_tokens`，可得到完整 token 统计。

---

## 7. 项目结构变更

### 7.1 新增文件

```
backend/
├── routers/
│   └── anthropic_gateway.py        # POST /v1/messages 路由
├── services/
│   └── anthropic_proxy.py          # Anthropic 格式透传代理逻辑
└── tests/
    └── test_anthropic_gateway.py   # Anthropic 端点测试
```

### 7.2 修改文件

```
backend/
├── middleware/
│   └── auth.py                     # 增加 x-api-key 提取
├── services/
│   └── proxy.py                    # 提取公共逻辑（鉴权、额度、计量）
├── models/
│   └── provider.py                 # providers 表增加 api_format 字段
├── main.py                         # 挂载 anthropic_gateway router
└── tests/
    └── test_gateway.py             # 增加 x-api-key 鉴权测试
```

---

## 8. 测试要求

### 8.1 test_anthropic_gateway.py

所有供应商调用使用 mock，禁止真实请求。

**鉴权测试**：

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_auth_bearer_token | `Authorization: Bearer ltm-sk-xxx` | 200 |
| test_auth_x_api_key | `x-api-key: ltm-sk-xxx` | 200 |
| test_auth_invalid_key | 无效 Key | 401，Anthropic 错误格式 |
| test_auth_revoked_key | 已吊销 Key | 401，Anthropic 错误格式 |
| test_auth_missing_key | 无鉴权头 | 401，Anthropic 错误格式 |

**路由测试**：

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_route_claude_to_anthropic | model=claude-sonnet-4-* | 请求转发到 Anthropic mock |
| test_route_glm_to_zhipu | model=glm-5 | 请求转发到智谱 mock |
| test_route_minimax_to_minimax | model=minimax-m2.5 | 请求转发到 MiniMax mock |
| test_route_unknown_model | model=nonexistent | 404，Anthropic 错误格式 |

**透传测试**：

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_headers_forwarded | anthropic-version + anthropic-beta | 被透传到上游 mock |
| test_supplier_key_substituted | x-api-key 替换为供应商 Key | 上游收到供应商 Key |
| test_body_passthrough | 请求体不被修改 | 上游收到的 body 与客户端发送的一致 |
| test_response_passthrough | 响应体不被修改 | 客户端收到的与上游返回的一致 |

**流式测试**：

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_stream_passthrough | stream=true，SSE 事件流 | 客户端收到完整的 Anthropic SSE 事件序列 |
| test_stream_usage_logged | 流式请求的 token 计量 | request_logs 正确记录 token 数 |

**额度与计量测试**：

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_quota_exceeded | 超额用户 | 429，Anthropic 格式 rate_limit_error |
| test_rpm_exceeded | 超过 RPM | 429，Anthropic 格式 rate_limit_error |
| test_usage_logged | 成功请求 | request_logs 记录正确，含 key_id |
| test_cost_calculated | 费用计算 | input/output tokens × 单价 = 正确费用 |
| test_monthly_usage_updated | 月度累计 | monthly_usage 正确累加 |

**错误处理**：

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_upstream_500 | 供应商返回 500 | 502，Anthropic 格式 api_error |
| test_upstream_timeout | 供应商超时 | 504，Anthropic 格式 api_error |
| test_upstream_429 | 供应商限流 | 429，透传供应商的限流信息 |

---

## 9. 开发计划

### Git 分支：`feature/anthropic-messages-api`

### Step 1：鉴权适配（0.5 天）

- 修改 `middleware/auth.py` 支持 `x-api-key` 头
- 确保 `/v1/chat/completions` 和 `/v1/models` 也兼容新的提取逻辑
- 编写鉴权测试
- 提交：`feat(auth): support x-api-key header for Anthropic SDK compatibility`

### Step 2：供应商模型扩展（0.5 天）

- `providers` 表增加 `api_format` 字段（Alembic migration）
- Admin 接口支持设置 `api_format`
- 为智谱 GLM 和 MiniMax 添加供应商配置（base_url + api_format=anthropic）
- 提交：`feat(provider): add api_format field for Anthropic-compatible providers`

### Step 3：Anthropic 透传端点（1.5–2 天）

- 新增 `routers/anthropic_gateway.py` + `services/anthropic_proxy.py`
- 实现 `POST /v1/messages`：鉴权 → 路由 → 换 Key → 透传 → 计量
- 支持 stream / non-stream
- 转发 `anthropic-version`、`anthropic-beta` 头
- 错误响应统一为 Anthropic 格式
- 编写路由、透传、流式、错误处理测试
- 提交：`feat(gateway): add /v1/messages endpoint with Anthropic passthrough proxy`

### Step 4：额度与计量集成（0.5 天）

- `/v1/messages` 的额度检查和计量与 `/v1/chat/completions` 共享逻辑
- 从 Anthropic 格式响应中提取 `usage.input_tokens` / `output_tokens`
- 流式模式下从 `message_start` + `message_delta` 累积 token
- 编写额度与计量测试
- 提交：`feat(billing): integrate quota and usage tracking for /v1/messages`

### Step 5：集成测试和文档（0.5 天）

- 运行完整测试套件确认无回归
- 更新 AGENTS.md / CLAUDE.md 的项目结构和 API 路径表
- 编写用户配置指南（见第 10 章）
- 合并到 main，打 tag `v0.8-anthropic-api`

**总计：3–5 天**

---

## 10. 用户配置指南

完成后需提供给团队成员的配置说明：

### 10.1 Claude Code 使用 Claude 模型

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"

claude
```

### 10.2 Claude Code 使用 GLM-5

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"
export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5"

claude
```

### 10.3 Claude Code 使用 MiniMax-M2.5

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"
export ANTHROPIC_DEFAULT_SONNET_MODEL="minimax-m2.5"

claude
```

### 10.4 OpenCode（Anthropic provider 模式）

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_API_KEY="ltm-sk-你的平台Key"

opencode
```

### 10.5 OpenCode（OpenAI provider 模式，已支持）

```bash
export OPENAI_BASE_URL="https://llm.yourcompany.com/v1"
export OPENAI_API_KEY="ltm-sk-你的平台Key"

opencode
```

### 10.6 Anthropic Python SDK 直接调用

```python
import anthropic

client = anthropic.Anthropic(
    base_url="https://llm.yourcompany.com",
    api_key="ltm-sk-你的平台Key"
)

message = client.messages.create(
    model="claude-sonnet-4-20250514",  # 或 "glm-5" / "minimax-m2.5"
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

---

## 11. 验收标准

- [ ] `POST /v1/messages` 端点可用，支持 `x-api-key` 和 `Bearer` 两种鉴权
- [ ] Claude Code 通过 `ANTHROPIC_BASE_URL` + 平台 Key 可正常使用 Claude 模型
- [ ] Claude Code 通过网关可正常使用 GLM-5 模型
- [ ] Claude Code 通过网关可正常使用 MiniMax-M2.5 模型
- [ ] 流式响应在所有供应商下正常工作
- [ ] `anthropic-version` 和 `anthropic-beta` 头被正确透传
- [ ] 用量正确记录到 request_logs，费用正确扣减
- [ ] 错误响应符合 Anthropic 格式（Claude Code 可正确解析）
- [ ] 所有已有测试仍然通过
- [ ] 新增测试覆盖率达标（routers ≥ 90%，services ≥ 85%）

---

## 12. 已知限制与后续优化

### MVP 限制

- `/v1/messages/count_tokens` 暂不实现（Claude Code 会跳过）
- prompt caching 按普通 token 计费，不单独计算折扣
- 不支持 Anthropic Batch API（`/v1/messages/batches`）

### 后续优化（Phase 3+）

- 实现 `/v1/messages/count_tokens`
- prompt caching 费用单独计算（`cache_creation_input_tokens` 和 `cache_read_input_tokens` 使用不同单价）
- 管理后台统计增加「按入站协议」维度
- 支持更多 Anthropic 兼容供应商（DeepSeek、Moonshot 等）
- 如需支持不兼容 Anthropic 格式的模型（如 GPT），再实现协议转换层

---

*文档结束*
