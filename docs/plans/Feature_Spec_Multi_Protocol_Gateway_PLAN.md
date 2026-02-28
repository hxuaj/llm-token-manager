# Claude Code 开发任务：Multi-Protocol Gateway — Anthropic Messages API 支持

> 本文件是交给 Claude Code 执行的完整开发计划，按步骤顺序完成即可。
> 参考文档：Feature Spec v1.1（支持 Agent 编程工具接入）

---

## 前置：理解现有代码库

在开始任何修改之前，请先完成以下阅读任务，理解现有代码结构：

1. 阅读 `CLAUDE.md` / `AGENTS.md`（如存在），了解项目约定
2. 阅读 `backend/main.py`，理解路由注册方式
3. 阅读 `backend/middleware/auth.py`，理解现有鉴权逻辑
4. 阅读 `backend/routers/` 目录，理解现有路由结构（重点看 `chat.py` 或 `completions.py`）
5. 阅读 `backend/services/proxy.py`，理解现有代理逻辑和公共工具函数
6. 阅读 `backend/models/provider.py`，理解 providers 数据模型
7. 查看现有数据库 migration 文件（`alembic/versions/` 目录），理解 migration 规范

理解完毕后，开始按下面步骤执行。

---

## Step 1：鉴权适配

**分支**：`feature/anthropic-messages-api`（从 main 创建）

**目标**：让鉴权中间件同时支持 `Authorization: Bearer` 和 `x-api-key` 两种方式。

### 1.1 修改 `backend/middleware/auth.py`

将 Key 提取逻辑重构为独立函数 `extract_platform_key(request)`，按以下优先级提取：

1. `Authorization: Bearer {key}` —— 优先级最高
2. `x-api-key: {key}` —— Anthropic SDK / Claude Code 惯例

如果两者都不存在，返回 Anthropic 格式错误（见下方错误格式规范）。

确保 `/v1/chat/completions`、`/v1/models`、以及即将新增的 `/v1/messages` **共用同一个 `extract_platform_key` 函数**，不要重复逻辑。

### 1.2 错误格式规范（全局适用）

凡是 `/v1/messages` 端点返回的错误，**必须**使用 Anthropic 格式：

```json
{
  "type": "error",
  "error": {
    "type": "<error_type>",
    "message": "<描述>"
  }
}
```

错误类型映射表：

| 场景 | HTTP 状态码 | error.type |
|------|------------|------------|
| Key 无效 / 不存在 | 401 | `authentication_error` |
| Key 已吊销 | 401 | `authentication_error` |
| 缺少鉴权头 | 401 | `authentication_error` |
| 非 Admin 访问管理接口 | 403 | `permission_error` |
| 模型不存在 / 未启用 | 404 | `not_found_error` |
| 额度超限 | 429 | `rate_limit_error` |
| RPM 超限 | 429 | `rate_limit_error` |
| 请求体格式错误 | 400 | `invalid_request_error` |
| 供应商返回 5xx | 502 | `api_error` |
| 供应商超时 | 504 | `api_error` |

### 1.3 补充测试到 `backend/tests/test_gateway.py`

新增以下测试（使用现有测试框架，所有外部调用使用 mock）：

- `test_auth_x_api_key`：通过 `x-api-key` 头正常鉴权，预期 200
- `test_auth_bearer_still_works`：已有 Bearer 鉴权不受影响，预期 200
- `test_auth_missing_key`：无任何鉴权头，预期 401，Anthropic 错误格式

### 1.4 提交

```
feat(auth): support x-api-key header for Anthropic SDK compatibility
```

---

## Step 2：供应商模型扩展

**目标**：`providers` 表新增 `api_format` 字段，Admin 接口支持配置，添加智谱 GLM 和 MiniMax 供应商。

### 2.1 数据库 Migration

创建 Alembic migration 文件，执行以下变更：

```sql
ALTER TABLE providers ADD COLUMN api_format VARCHAR(20) NOT NULL DEFAULT 'openai';
-- 约束：CHECK (api_format IN ('openai', 'anthropic'))
```

### 2.2 修改 `backend/models/provider.py`

在 Provider 模型中新增 `api_format` 字段（默认值 `'openai'`），加入必要的校验。

### 2.3 修改 Admin 供应商接口

在添加/编辑供应商的 API（通常是 `POST /admin/providers` 和 `PUT /admin/providers/{id}`）中：

- 请求体新增 `api_format` 字段（可选，默认 `openai`，可选值 `openai` | `anthropic`）
- 返回体也包含 `api_format`

### 2.4 添加供应商初始数据（通过 migration 或 seed 脚本）

插入以下供应商配置（如果尚不存在）：

| name | api_format | base_url | 备注 |
|------|-----------|----------|------|
| Anthropic | anthropic | https://api.anthropic.com | 现有供应商更新 api_format |
| 智谱 GLM | anthropic | https://open.bigmodel.cn/api/anthropic | 新增 |
| MiniMax | anthropic | （MiniMax Anthropic 兼容端点，从环境变量或配置读取） | 新增 |

> **注意**：供应商的实际 API Key 通过现有的加密存储机制管理，此处只添加供应商基础配置。实际 Key 由管理员通过 Admin 界面配置。

### 2.5 模型路由规则

在 `backend/services/` 中（新建 `anthropic_proxy.py` 或在 migration 里）实现模型前缀到供应商的路由规则：

```python
MODEL_ROUTE_RULES = [
    ("claude-", "anthropic"),    # claude-sonnet-4-*, claude-opus-* 等
    ("glm-",    "zhipu"),        # glm-5, glm-4.* 等  
    ("minimax-","minimax"),      # minimax-m2.5 等
]

def resolve_provider(model_name: str) -> Provider:
    """根据 model 名称前缀查找对应供应商，找不到抛出 NotFoundError"""
    for prefix, provider_name in MODEL_ROUTE_RULES:
        if model_name.startswith(prefix):
            provider = db.query(Provider).filter_by(name=provider_name, is_active=True).first()
            if provider:
                return provider
    raise NotFoundError(f"Model '{model_name}' not found or not enabled")
```

### 2.6 提交

```
feat(provider): add api_format field for Anthropic-compatible providers
```

---

## Step 3：Anthropic 透传端点（核心功能）

**目标**：实现 `POST /v1/messages`，支持鉴权、路由、换 Key、透传请求/响应、流式 SSE。

### 3.1 新建 `backend/services/anthropic_proxy.py`

实现以下核心函数：

#### `build_upstream_headers(request_headers, vendor_key) -> dict`

构造转发给上游的 headers：
- 删除原始的 `authorization` / `x-api-key`（平台 Key）
- 新增 `x-api-key: {vendor_key}`（解密后的供应商 Key）
- 透传：`anthropic-version`、`anthropic-beta`、`content-type`
- 不透传：`host`、`connection`、`transfer-encoding` 等逐跳头

#### `proxy_request_non_stream(upstream_url, headers, body) -> Response`

- 使用 `httpx.AsyncClient` 发送 POST 请求（超时 120s）
- 上游返回 2xx：直接将响应体和状态码原样返回给客户端
- 上游返回 4xx/5xx：返回 502 + Anthropic 格式 `api_error`
- 超时：返回 504 + Anthropic 格式 `api_error`
- 提取 `response.json()["usage"]` 用于计量

#### `proxy_request_stream(upstream_url, headers, body) -> StreamingResponse`

- 使用 `httpx.AsyncClient.stream()` 发送 POST 请求
- 逐 chunk 转发 SSE 事件给客户端（`text/event-stream`）
- 同时解析以下两个 SSE 事件累积 token 用于计量：
  - `message_start`：提取 `usage.input_tokens`
  - `message_delta`：提取 `usage.output_tokens`
- 流结束后异步触发计量记录（不阻塞响应）

### 3.2 新建 `backend/routers/anthropic_gateway.py`

注册路由 `POST /v1/messages`，实现以下 pipeline：

```
1. extract_platform_key(request)        → 提取平台 Key，失败返回 401 Anthropic 格式
2. authenticate_key(key)                → 验证 Key 有效性（复用现有鉴权逻辑）
3. check_quota(user_id)                 → 检查额度（复用现有额度检查逻辑）
4. check_rpm(user_id)                   → 检查 RPM（复用现有 RPM 逻辑）
5. parse body → extract model name      → 只读 model 字段，body 本身不修改
6. resolve_provider(model)              → 路由到供应商，失败返回 404 Anthropic 格式
7. decrypt_vendor_key(provider)         → 解密供应商 Key
8. build_upstream_url(provider)         → f"{provider.base_url}/v1/messages"
9. build_upstream_headers(...)          → 替换鉴权头，透传必要头部
10. if stream: proxy_request_stream     → 流式透传 + 异步计量
    else:      proxy_request_non_stream → 完整透传 + 同步计量
```

**关键实现要点**：
- Body 在提取 `model` 字段后**原样转发**，不做任何序列化/反序列化
- 使用 `request.body()` 获取原始字节，避免二次序列化改变格式
- `stream` 字段从 body JSON 中读取判断，但不修改 body

### 3.3 在 `backend/main.py` 注册路由

```python
from backend.routers.anthropic_gateway import router as anthropic_router
app.include_router(anthropic_router)
```

确保路由在现有 OpenAI 格式路由**之前**注册，避免路径冲突。

### 3.4 新建 `backend/tests/test_anthropic_gateway.py`

所有供应商 HTTP 调用使用 `unittest.mock` 或 `httpx.MockTransport` mock，**禁止真实网络请求**。

实现以下测试（每个测试独立，使用 fixtures 设置测试数据）：

**鉴权测试（5个）**：
- `test_auth_bearer_token`：`Authorization: Bearer ltm-sk-xxx` → 200
- `test_auth_x_api_key`：`x-api-key: ltm-sk-xxx` → 200  
- `test_auth_invalid_key`：无效 Key → 401，响应体符合 Anthropic 错误格式
- `test_auth_revoked_key`：已吊销 Key → 401，Anthropic 格式
- `test_auth_missing_key`：无鉴权头 → 401，Anthropic 格式

**路由测试（4个）**：
- `test_route_claude_to_anthropic`：`model="claude-sonnet-4-20250514"` → 请求发送到 `api.anthropic.com` mock
- `test_route_glm_to_zhipu`：`model="glm-5"` → 请求发送到 `open.bigmodel.cn` mock
- `test_route_minimax_to_minimax`：`model="minimax-m2.5"` → 请求发送到 MiniMax mock
- `test_route_unknown_model`：`model="nonexistent-model"` → 404，Anthropic `not_found_error`

**透传正确性测试（4个）**：
- `test_headers_forwarded`：`anthropic-version` 和 `anthropic-beta` 被透传到上游 mock
- `test_supplier_key_substituted`：上游收到的 `x-api-key` 是供应商 Key，不是平台 Key
- `test_body_passthrough`：上游收到的请求体与客户端发送的完全一致（字节级别）
- `test_response_passthrough`：客户端收到的响应体与上游返回的完全一致

**流式测试（2个）**：
- `test_stream_passthrough`：`stream=true`，mock 上游返回完整 Anthropic SSE 序列，验证客户端收到相同事件序列
- `test_stream_usage_logged`：流式请求结束后，`request_logs` 中正确记录 input/output tokens

**额度与计量测试（5个）**：
- `test_quota_exceeded`：超额用户 → 429，Anthropic `rate_limit_error`
- `test_rpm_exceeded`：RPM 超限 → 429，Anthropic `rate_limit_error`
- `test_usage_logged`：成功请求后 `request_logs` 有新记录，包含正确的 `key_id`、`input_tokens`、`output_tokens`
- `test_cost_calculated`：费用 = input_tokens × input_price + output_tokens × output_price，精度误差 < 0.000001
- `test_monthly_usage_updated`：`monthly_usage` 表对应用户/月份的累计值正确增加

**错误处理测试（3个）**：
- `test_upstream_500`：mock 上游返回 500 → 网关返回 502，Anthropic `api_error`
- `test_upstream_timeout`：mock 上游超时 → 网关返回 504，Anthropic `api_error`
- `test_upstream_429`：mock 上游返回 429 → 网关返回 429，透传上游限流信息

### 3.5 提交

```
feat(gateway): add /v1/messages endpoint with Anthropic passthrough proxy
```

---

## Step 4：额度与计量集成

**目标**：确保 `/v1/messages` 的计量逻辑与 `/v1/chat/completions` 一致，代码复用。

### 4.1 检查并重构计量公共逻辑

检查现有 `backend/services/proxy.py` 或计量相关模块，确认以下逻辑已被抽取为可复用函数：

- `record_usage(key_id, model, input_tokens, output_tokens, cost_usd, request_id, ...)`
- `update_monthly_usage(user_id, month, cost_usd)`
- `calculate_cost(model, input_tokens, output_tokens) -> float`

如果尚未抽取，现在将其移到 `backend/services/billing.py` 中，让 `proxy.py` 和 `anthropic_proxy.py` 都从这里导入。

### 4.2 实现 Anthropic 格式 Token 提取

在 `backend/services/anthropic_proxy.py` 中实现：

```python
def extract_usage_from_response(response_body: dict) -> tuple[int, int]:
    """从非流式 Anthropic 响应提取 (input_tokens, output_tokens)"""
    usage = response_body.get("usage", {})
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)

def extract_usage_from_stream(sse_events: list[str]) -> tuple[int, int]:
    """
    从流式 SSE 事件列表提取 (input_tokens, output_tokens)
    - input_tokens 来自 event: message_start → data.message.usage.input_tokens
    - output_tokens 来自 event: message_delta → data.usage.output_tokens
    """
    input_tokens = 0
    output_tokens = 0
    for event in sse_events:
        # 解析 SSE，提取对应事件的 usage 字段
        ...
    return input_tokens, output_tokens
```

### 4.3 验证计量测试通过

运行 Step 3 中写的额度与计量相关测试（5个），全部通过后继续。

### 4.4 提交

```
feat(billing): integrate quota and usage tracking for /v1/messages
```

---

## Step 5：集成测试与文档

**目标**：全量测试通过，更新项目文档。

### 5.1 运行完整测试套件

```bash
pytest backend/tests/ -v --tb=short
```

确认：
- 所有已有测试（包括 OpenAI 格式端点）仍然通过
- 新增测试全部通过
- `backend/routers/anthropic_gateway.py` 覆盖率 ≥ 90%
- `backend/services/anthropic_proxy.py` 覆盖率 ≥ 85%

如有失败，逐一修复后再继续。

### 5.2 更新项目文档

在 `CLAUDE.md` 或 `AGENTS.md`（按项目现有约定）更新以下内容：

1. **API 路径表**：新增 `POST /v1/messages` 行，注明用途和鉴权方式
2. **项目结构**：新增 `anthropic_gateway.py` 和 `anthropic_proxy.py` 的说明
3. **环境变量**：如新增了任何环境变量（如 MiniMax 端点 URL），在此说明

### 5.3 创建用户配置指南

新建 `docs/anthropic-api-setup.md`，内容包含以下章节：

**Claude Code 使用 Claude 模型**：
```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"
claude
```

**Claude Code 使用 GLM-5**：
```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"
export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5"
claude
```

**Claude Code 使用 MiniMax-M2.5**：
```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"
export ANTHROPIC_DEFAULT_SONNET_MODEL="minimax-m2.5"
claude
```

**OpenCode（Anthropic provider 模式）**：
```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_API_KEY="ltm-sk-你的平台Key"
opencode
```

**Anthropic Python SDK**：
```python
import anthropic
client = anthropic.Anthropic(
    base_url="https://llm.yourcompany.com",
    api_key="ltm-sk-你的平台Key"
)
```

### 5.4 验收检查清单

在提交前，逐项确认以下验收标准：

- [ ] `POST /v1/messages` 端点存在，支持 `x-api-key` 和 `Authorization: Bearer` 两种鉴权
- [ ] `model=claude-*` 路由到 Anthropic 后端
- [ ] `model=glm-*` 路由到智谱 GLM 后端  
- [ ] `model=minimax-*` 路由到 MiniMax 后端
- [ ] 流式响应（`stream=true`）正常工作
- [ ] `anthropic-version` 和 `anthropic-beta` 头被正确透传
- [ ] 用量正确记录到 `request_logs`，费用正确扣减
- [ ] 所有错误响应使用 Anthropic 错误格式
- [ ] 所有已有测试通过，无回归
- [ ] 新增测试覆盖率达标

### 5.5 提交并打 tag

```bash
git add -A
git commit -m "feat(docs): update project docs and add user setup guide for /v1/messages"

# 合并到 main（走 PR 流程或直接合并，按团队约定）
git checkout main
git merge feature/anthropic-messages-api
git tag v0.8-anthropic-api
git push origin main --tags
```

---

## 附录：不实现的功能（MVP 范围外）

以下功能**不在本次开发范围内**，遇到相关请求时直接返回 404 或 501：

- `POST /v1/messages/count_tokens`：Claude Code 会跳过，不影响核心功能
- `POST /v1/messages/batches`：Anthropic Batch API，暂不支持
- Prompt caching 折扣计费：`cache_creation_input_tokens` 和 `cache_read_input_tokens` 按普通 input token 计费

---

## 附录：遇到问题时的处理原则

1. **不确定现有代码结构**：先读代码，再动手，不要假设
2. **发现现有 bug**：记录在 TODO 注释中，不要在本 PR 修复，保持 diff 干净
3. **测试失败但原因不明**：先确认 mock 设置正确，再检查业务逻辑
4. **需要新的环境变量**：在 `.env.example` 中添加注释说明，不要硬编码
5. **供应商 base_url 不确定**：从数据库/配置读取，不要在代码中硬编码 URL

---

*计划结束，共 5 个步骤，预计工作量 3–5 天*
