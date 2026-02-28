# 开发计划：模型级用量监测与分析

> 本文档供 Claude Code 直接执行。请按 Batch 顺序完成，每个 Batch 完成后运行对应测试通过后再进入下一批次。

---

## 前置说明

在开始任何编码前，请先完成以下步骤：

1. 阅读项目根目录的 `README.md`，了解项目结构、技术栈、运行方式
2. 查阅现有数据库 migration 文件（通常在 `alembic/versions/`），了解当前表结构
3. 查阅 `backend/models/` 或对应 ORM 定义，确认已有的 `request_logs`、`provider_api_keys`、`providers`、`users` 等表的字段
4. 查阅现有的 `backend/routers/admin.py`，了解供应商 Key 添加接口的当前实现
5. 查阅现有的网关转发逻辑（`/v1/chat/completions`、`/v1/messages`），了解 Key 选择和计费的当前实现

确认清楚后再开始编码。

---

## Batch 1：模型目录 + 自动发现 + 白名单管理 + Key 计划类型

> 这是整个功能的基础，估计 4–5 天。完成后 Batch 2 的统计才有数据来源。

### Step 1：数据库 Migration

创建 Alembic migration 文件，包含以下变更（**顺序执行，不要合并成一个 migration**）：

**Migration 1：创建 model_catalog 表**

```sql
CREATE TABLE model_catalog (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id        VARCHAR(100) NOT NULL UNIQUE,
    display_name    VARCHAR(200) NOT NULL,
    provider_id     UUID NOT NULL REFERENCES providers(id),
    input_price     DECIMAL(10,4) NOT NULL DEFAULT 0,
    output_price    DECIMAL(10,4) NOT NULL DEFAULT 0,
    cache_write_price   DECIMAL(10,4) DEFAULT 0,
    cache_read_price    DECIMAL(10,4) DEFAULT 0,
    context_window  INTEGER,
    max_output      INTEGER,
    supports_vision BOOLEAN DEFAULT FALSE,
    supports_tools  BOOLEAN DEFAULT FALSE,
    supports_streaming BOOLEAN DEFAULT TRUE,
    status          VARCHAR(20) DEFAULT 'pending',        -- 'pending' | 'active' | 'inactive'
    is_pricing_confirmed BOOLEAN DEFAULT FALSE,
    source          VARCHAR(20) DEFAULT 'manual',         -- 'auto_discovered' | 'manual' | 'builtin_default'
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_model_catalog_provider ON model_catalog(provider_id);
CREATE INDEX idx_model_catalog_status ON model_catalog(status);
```

**Migration 2：修改 provider_api_keys 表**

```sql
ALTER TABLE provider_api_keys ADD COLUMN key_plan VARCHAR(20) DEFAULT 'standard';
ALTER TABLE provider_api_keys ADD COLUMN plan_models JSON DEFAULT NULL;
ALTER TABLE provider_api_keys ADD COLUMN plan_description TEXT DEFAULT NULL;
ALTER TABLE provider_api_keys ADD COLUMN override_input_price DECIMAL(10,4) DEFAULT NULL;
ALTER TABLE provider_api_keys ADD COLUMN override_output_price DECIMAL(10,4) DEFAULT NULL;
```

**Migration 3：修改 request_logs 表**

```sql
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS cost_usd DECIMAL(10,6) DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS input_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS output_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS cache_write_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS latency_ms INTEGER;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS key_plan VARCHAR(20) DEFAULT 'standard';
```

> 注意：如果项目中已存在 `model_pricing` 表，在 migration 中添加注释说明该表将被废弃，但**不要在 Batch 1 中删除它**，保持向后兼容。

### Step 2：ORM 模型

在 `backend/models/` 中创建或更新对应的 SQLAlchemy 模型：

- 新建 `ModelCatalog` 模型，对应 `model_catalog` 表
- 更新 `ProviderApiKey` 模型，新增 `key_plan`、`plan_models`、`plan_description`、`override_input_price`、`override_output_price` 字段
- 更新 `RequestLog` 模型，新增 `cost_usd`、`input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_write_tokens`、`latency_ms`、`key_plan` 字段

### Step 3：内置默认定价表

创建 `backend/services/model_pricing_defaults.py`：

```python
# 单价单位：USD per 1M tokens
DEFAULT_MODEL_PRICING = {
    # ── Anthropic ──
    "claude-opus-4-20250514": {
        "display_name": "Claude Opus 4",
        "input_price": 15.0000,
        "output_price": 75.0000,
        "context_window": 200000,
        "max_output": 32000,
        "supports_vision": True,
        "supports_tools": True,
    },
    "claude-sonnet-4-20250514": {
        "display_name": "Claude Sonnet 4",
        "input_price": 3.0000,
        "output_price": 15.0000,
        "context_window": 200000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_tools": True,
    },
    "claude-haiku-4-5-20251001": {
        "display_name": "Claude Haiku 4.5",
        "input_price": 0.8000,
        "output_price": 4.0000,
        "context_window": 200000,
        "max_output": 8192,
        "supports_vision": True,
        "supports_tools": True,
    },
    # ── OpenAI ──
    "gpt-4o": {
        "display_name": "GPT-4o",
        "input_price": 2.5000,
        "output_price": 10.0000,
        "context_window": 128000,
        "max_output": 16384,
        "supports_vision": True,
        "supports_tools": True,
    },
    "gpt-4o-mini": {
        "display_name": "GPT-4o Mini",
        "input_price": 0.1500,
        "output_price": 0.6000,
        "context_window": 128000,
        "max_output": 16384,
        "supports_vision": True,
        "supports_tools": True,
    },
    # ── 智谱 GLM ──
    "glm-5": {
        "display_name": "GLM-5",
        "input_price": 0.0000,
        "output_price": 0.0000,
        "context_window": 128000,
        "max_output": 4096,
        "supports_vision": False,
        "supports_tools": True,
    },
    # ── MiniMax ──
    "minimax-m2.5": {
        "display_name": "MiniMax M2.5",
        "input_price": 0.0000,
        "output_price": 0.0000,
        "context_window": 1000000,
        "max_output": 65536,
        "supports_vision": False,
        "supports_tools": True,
    },
}

# Chat 模型过滤策略
CHAT_MODEL_PREFIXES = [
    "gpt-", "o1-", "o3-", "o4-",
    "claude-",
    "glm-",
    "minimax-",
    "qwen-",
    "ernie-",
    "deepseek-",
]

NON_CHAT_KEYWORDS = [
    "embedding", "embed",
    "tts", "whisper", "audio",
    "dall-e", "image",
    "moderation",
    "instruct",
]

def is_chat_model(model_id: str) -> bool:
    model_lower = model_id.lower()
    if any(kw in model_lower for kw in NON_CHAT_KEYWORDS):
        return False
    if any(model_lower.startswith(prefix) for prefix in CHAT_MODEL_PREFIXES):
        return True
    return False
```

### Step 4：模型发现服务

创建 `backend/services/model_discovery.py`，实现 `ModelDiscoveryService` 类：

**需实现的方法：**

- `discover_models(provider, api_key, db) -> DiscoveryResult`：主入口，根据 `provider.api_format` 分发
- `_fetch_openai_models(base_url, api_key) -> list[dict]`：调用 `GET {base_url}/models`，Bearer 认证
- `_fetch_anthropic_models(base_url, api_key) -> list[dict]`：调用 `GET {base_url}/v1/models`，x-api-key 认证，**支持分页**（循环直到 `has_more=false`）
- `_merge_into_catalog(models, provider, db) -> DiscoveryResult`：匹配内置定价后写入 `model_catalog`（已存在的 model_id 跳过，不覆盖）

**返回的 DiscoveryResult 数据类：**

```python
@dataclass
class DiscoveryResult:
    discovered: int = 0
    new_models: int = 0
    pricing_matched: int = 0
    pricing_pending: int = 0
    details: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
```

**异常类：**

```python
class UnsupportedDiscoveryError(Exception):
    pass
```

**关键细节：**

- `_merge_into_catalog` 中，如果内置定价表有该模型且 `input_price > 0`，则 `is_pricing_confirmed=True`，`source="builtin_default"`；否则 `is_pricing_confirmed=False`，`source="auto_discovered"`
- 新写入的模型默认 `status="pending"`，需要 Admin 手动启用
- httpx 请求超时统一设 10 秒

### Step 5：模型目录 CRUD 服务

创建 `backend/services/model_catalog_service.py`，封装对 `model_catalog` 的常用查询：

- `get_active_models(db) -> list[ModelCatalog]`：查询所有 `status='active'` 的模型
- `get_provider_models(db, provider_id) -> list[ModelCatalog]`：查询指定供应商下的所有模型
- `get_model_by_id(db, model_id) -> ModelCatalog | None`
- `update_model_status(db, model_id, status) -> ModelCatalog`
- `update_model_pricing(db, model_id, input_price, output_price, changed_by_id, reason) -> ModelCatalog`：更新定价，并写 `model_pricing_history` 记录（如 Batch 3 中的 history 表暂未创建，此处 TODO 注释占位即可）
- `create_model(db, **kwargs) -> ModelCatalog`
- `batch_activate_priced_models(db, provider_id) -> int`：启用所有 `is_pricing_confirmed=True` 且 `status='pending'` 的模型，返回启用数量

### Step 6：Key 选择路由

创建 `backend/services/key_selector.py`，将现有网关中 Key 选择逻辑**重构到此文件**（而非修改原有逻辑），新增 coding_plan 优先级：

```python
async def select_provider_key(provider, model_id, db) -> ProviderApiKey:
    """
    优先级：
    1. coding_plan Key 且 model_id 在其 plan_models 中
    2. standard Key（兜底）
    如无可用 Key，抛出 NoAvailableKeyError
    """
```

异常类：`class NoAvailableKeyError(Exception): pass`

> 注意：保留原有的 RPM 限流 + 轮转逻辑（如有），在新的优先级框架内复用它。

### Step 7：修改供应商 Key 添加接口

修改 `backend/routers/admin.py` 中的 `POST /api/admin/providers/{provider_id}/keys`：

1. `AddProviderKeyRequest` schema 新增字段：`key_plan`（默认 `"standard"`）、`plan_models`（List[str]，可选）、`plan_description`（str，可选）、`override_input_price`（float，可选）、`override_output_price`（float，可选）
2. 校验：`key_plan == "coding_plan"` 时必须提供 `plan_models`，否则返回 400
3. 存储 Key 时带入新字段
4. 仅当 `key_plan == "standard"` 且该供应商**首次添加** standard Key 时，异步调用 `ModelDiscoveryService.discover_models()`（失败时只 warning 日志，不影响 Key 添加成功）
5. 响应中附加 `discovery` 字段（发现结果摘要或 null）

### Step 8：Admin 模型管理 API

新建 `backend/routers/admin_models.py`，注册以下路由（均需 Admin 权限）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/admin/providers/{id}/models` | 获取供应商下所有模型及摘要 |
| `POST` | `/api/admin/providers/{id}/discover-models` | 手动触发模型发现 |
| `PUT` | `/api/admin/models/{model_id}/status` | 更新模型状态（body: `{"status": "active"}`） |
| `PUT` | `/api/admin/models/{model_id}/pricing` | 更新定价（body: `{"input_price": x, "output_price": x, "reason": "..."}`) |
| `POST` | `/api/admin/models` | 手动添加模型 |
| `POST` | `/api/admin/providers/{id}/models/batch-activate` | 批量启用（body: `{"activate_all_priced": true}` 或 `{"model_ids": [...]}`) |

**GET /api/admin/providers/{id}/models 响应格式：**

```json
{
  "provider_id": "uuid",
  "provider_name": "Anthropic",
  "models": [ { ...ModelCatalog 字段... } ],
  "summary": { "total": 8, "active": 5, "pending": 2, "inactive": 1, "pricing_pending": 1 }
}
```

**POST discover-models 错误处理：**
- 供应商无可用 API Key → 400
- 供应商 api_format 不支持发现 → 422
- 上游接口错误 → 502
- 上游超时 → 504

在 `backend/main.py`（或应用注册路由的地方）注册新 router。

### Step 9：更新 GET /v1/models 端点

找到现有的 `GET /v1/models` 路由，重写为：

1. 查询 `model_catalog` 中 `status='active'` 的所有模型
2. 如果当前用户有 `allowed_models` 限制，进一步过滤
3. 返回 OpenAI 兼容格式：

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-sonnet-4-20250514",
      "object": "model",
      "created": 1700000000,
      "owned_by": "Anthropic"
    }
  ]
}
```

### Step 10：修改计费逻辑

找到网关转发 `/v1/chat/completions` 和 `/v1/messages` 的处理逻辑，在请求完成后：

1. 使用 `key_selector.select_provider_key()` 替换原有 Key 选择逻辑
2. 从上游响应中提取 `input_tokens`、`output_tokens`
3. 查询 `model_catalog` 获取当前模型的单价
4. 费用计算：
   ```python
   if key.override_input_price is not None:
       # Coding Plan Key 或 Admin 覆盖单价
       cost_usd = (input_tokens * key.override_input_price / 1_000_000
                 + output_tokens * key.override_output_price / 1_000_000)
   elif key.key_plan == "coding_plan":
       cost_usd = 0.0  # 月费订阅，无按量计费
   else:
       cost_usd = (input_tokens * model.input_price / 1_000_000
                 + output_tokens * model.output_price / 1_000_000)
   ```
5. 写入 `request_logs`，填充 `cost_usd`、`input_tokens`、`output_tokens`、`latency_ms`、`key_plan`

**API 响应增强：**

- `/v1/chat/completions`（OpenAI 格式）：在响应 JSON 中追加顶层 `x_ltm` 字段：
  ```json
  "x_ltm": {
    "cost_usd": 0.001050,
    "remaining_quota_usd": 8.95,
    "key_id_suffix": "...a3f8"
  }
  ```

- `/v1/messages`（Anthropic 格式）：在响应头中追加（body 透传不修改）：
  ```
  X-LTM-Cost-USD: 0.001050
  X-LTM-Remaining-Quota-USD: 8.95
  X-LTM-Key-ID-Suffix: ...a3f8
  ```

### Step 11：Batch 1 测试

按照以下规范在 `backend/tests/` 中创建测试文件，**所有供应商 API 调用使用 mock，禁止真实请求**：

**`test_model_discovery.py`**（12 个测试函数）：

| 测试函数 | 验证内容 |
|----------|----------|
| `test_discover_openai_models` | Mock OpenAI `/v1/models` 返回混合列表，正确过滤出 chat 模型，排除 embedding/tts |
| `test_discover_anthropic_models` | Mock Anthropic `/v1/models` 返回结果，正确解析 display_name |
| `test_discover_anthropic_pagination` | Mock `has_more=true` + `has_more=false`，两次请求后返回完整列表 |
| `test_merge_with_builtin_pricing` | 发现的模型在内置定价表中，`is_pricing_confirmed=true`，定价正确填充 |
| `test_unknown_model_pricing_pending` | 发现的模型不在内置定价表中，`is_pricing_confirmed=false`，定价为 0 |
| `test_skip_existing_models` | 模型已在 catalog 中，不重复写入，不覆盖已有配置 |
| `test_discovery_upstream_error` | 供应商返回 500，抛出异常，不影响已有数据 |
| `test_discovery_timeout` | 供应商响应超时，抛出超时异常 |
| `test_unsupported_provider` | api_format 不支持，抛出 UnsupportedDiscoveryError |
| `test_chat_model_filter` | 包含 embedding、tts、dalle 等模型 ID，全部被过滤 |
| `test_coding_plan_key_skips_discovery` | 添加 coding_plan Key，不触发自动发现 |
| `test_standard_key_triggers_discovery` | 添加 standard Key（首个），触发自动发现 |

**`test_admin_models.py`**（12 个测试函数）：

| 测试函数 | 验证内容 |
|----------|----------|
| `test_list_provider_models` | 获取供应商下的模型列表，200，返回正确摘要 |
| `test_activate_model` | pending → active，200，状态变更 |
| `test_deactivate_model` | active → inactive，200，`GET /v1/models` 不再返回 |
| `test_update_model_pricing` | 修改定价，200 |
| `test_manual_add_model` | 手动添加模型，201，model_catalog 有新记录 |
| `test_batch_activate` | 批量启用已定价模型，所有 pending+pricing_confirmed 变 active |
| `test_trigger_discovery` | 调用发现端点，200，返回发现结果摘要 |
| `test_user_cannot_manage_models` | 普通用户调用模型管理 API，403 |
| `test_v1_models_only_active` | `GET /v1/models` 只返回 active 模型 |
| `test_v1_models_user_allowed_filter` | 用户有 `allowed_models` 限制，只返回允许且 active 的模型 |
| `test_auto_discover_on_first_key` | 添加第一个 standard Key，自动触发模型发现 |
| `test_no_discover_on_subsequent_key` | 添加第二个 standard Key，不触发自动发现 |

**`test_key_plan_routing.py`**（10 个测试函数）：

| 测试函数 | 验证内容 |
|----------|----------|
| `test_add_coding_plan_key` | 添加 coding_plan Key 时不提供 plan_models，400 |
| `test_add_coding_plan_key_success` | 正确添加 coding_plan Key，201 |
| `test_add_standard_key_no_plan_models` | standard Key 不需要 plan_models，201 |
| `test_route_prefer_coding_plan` | 请求 glm-5 且有 coding_plan Key，优先选择 coding_plan Key |
| `test_route_fallback_to_standard` | 请求 glm-4-plus 无 coding_plan Key 覆盖，选择 standard Key |
| `test_route_no_coding_plan_for_model` | coding_plan Key 的 plan_models 不含请求模型，跳过，用 standard Key |
| `test_coding_plan_cost_zero` | 通过 coding_plan Key 转发（无虚拟单价），`cost_usd = 0` |
| `test_coding_plan_override_pricing` | coding_plan Key 设置了虚拟单价，按虚拟单价计算 |
| `test_standard_key_normal_pricing` | standard Key 转发，按 model_catalog 单价计算 |
| `test_no_available_key` | 供应商无 active Key，返回 503 |

**Batch 1 验收标准（所有测试通过后检查）：**
- [ ] Admin 添加 standard 供应商 Key 后，响应中包含 `discovery` 摘要
- [ ] Admin 添加 coding_plan Key 时不指定 plan_models 返回 400
- [ ] `GET /v1/models` 只返回 `status='active'` 的模型
- [ ] 每次请求的 `cost_usd` 按实际模型单价计算并写入 `request_logs`
- [ ] coding_plan Key 转发时 `cost_usd = 0`（无虚拟单价时）

---

## Batch 2：统计 API + 前端 Dashboard

> 依赖 Batch 1 完成。估计 3–4 天。

### Step 1：用户级统计 API

新建 `backend/routers/user_usage.py`，注册以下路由（需用户登录态）：

**GET `/api/user/usage/by-model`**

Query 参数：`period`（`day|week|month`，默认 `month`）、`start_date`、`end_date`（可选）

直接查询 `request_logs` 表（Batch 3 再切换到预聚合表），按 `model_id` 分组聚合：

```json
{
  "period": "2026-02",
  "total_cost_usd": 23.45,
  "total_requests": 1247,
  "models": [
    {
      "model_id": "claude-sonnet-4-20250514",
      "display_name": "Claude Sonnet 4",
      "request_count": 890,
      "input_tokens": 4500000,
      "output_tokens": 1200000,
      "cost_usd": 18.45,
      "percentage": 78.6
    }
  ]
}
```

**GET `/api/user/usage/by-key`**

按用户的 `user_api_keys` 分组，每个 Key 下再按模型拆分：

```json
{
  "keys": [
    {
      "key_suffix": "...a3f8",
      "key_name": "Claude Code 主力",
      "total_cost_usd": 15.20,
      "models": [
        { "model_id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4", "cost_usd": 12.00, "request_count": 580 }
      ]
    }
  ]
}
```

**GET `/api/user/usage/timeline`**

Query 参数：`granularity`（`hour|day|week`）、`model_id`（可选）

```json
{
  "granularity": "day",
  "data": [
    { "date": "2026-02-24", "requests": 45, "cost_usd": 1.23, "input_tokens": 230000, "output_tokens": 58000 }
  ]
}
```

### Step 2：Admin 统计 API

在 `backend/routers/admin.py` 或新建 `backend/routers/admin_usage.py`，注册以下路由：

**GET `/api/admin/usage/overview`**

```json
{
  "period": "2026-02",
  "total_cost_usd": 342.50,
  "total_requests": 18420,
  "active_users": 28,
  "top_models": [ { "model_id": "...", "cost_usd": 189.30, "requests": 9200 } ],
  "top_users": [ { "user_id": "...", "username": "alice", "cost_usd": 52.30 } ]
}
```

Query 参数：`period`（`day|week|month`）、`start_date`、`end_date`

**GET `/api/admin/usage/by-model`**

按模型聚合，支持时间段筛选。返回每个模型的 `request_count`、`input_tokens`、`output_tokens`、`cost_usd`、占比。

**GET `/api/admin/usage/by-user`**

按用户聚合，每个用户可展开到模型维度。

**GET `/api/admin/usage/export`**

Query 参数：`format`（目前只支持 `csv`）、`group_by`（`model|user|key`）、`start_date`、`end_date`

返回 CSV 文件，设置 `Content-Type: text/csv` 和 `Content-Disposition: attachment; filename="usage_export.csv"`。

### Step 3：前端页面

> 以下为页面需求描述，实现时请参考项目现有的前端框架、组件库和代码风格。

**页面一：供应商模型管理页面（Admin，新增页面或在现有供应商详情页新增 Tab）**

布局：
- 顶部：供应商基本信息（名称、格式、Base URL）
- API Keys 列表：展示 `key_suffix`、`key_plan`（"标准 Key" / "Coding Plan"）、状态、可用模型（coding_plan 显示 plan_models，standard 显示"全部已启用"）
- "添加 Key" 按钮：弹窗，包含以下字段：
  - API Key 输入框
  - 计划类型单选：标准 API Key / Coding Plan
  - Coding Plan 时额外显示：支持的模型（逗号分隔输入）、备注、虚拟单价（Input/Output 各一个数字输入框）
- 模型白名单列表：展示 `model_id`、`display_name`、`status`（带颜色标签）、`input_price`/`output_price`、`is_pricing_confirmed`
  - 每行可操作：启用/禁用、编辑定价（弹窗）
  - 顶部工具栏："🔄 刷新模型列表"（调用 discover-models API）、"批量启用已定价模型"

**页面二：用户"我的用量"页面（用户端，新增页面）**

布局：
- 顶部：月份选择器（默认当月）
- 四张统计卡片：本月消耗 ($)、请求次数、剩余额度 ($)、最常用模型占比 (%)
- 下方两栏：
  - 左：按模型分布饼图（各模型费用占比，含 legend）
  - 右：用量趋势折线图（按天，X 轴为日期，Y 轴为费用 $）
- 按 Key 明细表：列 Key 名称、模型、请求次数、费用

使用的图表库参考项目现有使用的库（如 recharts、echarts 等）。

**页面三：Admin 用量分析页面（Admin，新增页面或在现有 Admin Dashboard 中新增 Tab）**

布局：
- 顶部：月份选择器 + "导出 CSV" 按钮
- 四张统计卡片：总费用、总请求、活跃用户数、使用中供应商数
- Tab 切换（按模型 / 按用户 / 按供应商）：
  - "按模型"：排行表（模型名、请求数、Token 数、费用、进度条占比）+ 堆叠面积图（按模型，X 轴时间）
  - "按用户"：用户排行表（用户名、请求数、费用），可展开查看该用户的模型分布
  - "按供应商"：供应商聚合数据

### Step 4：Batch 2 测试

在 `backend/tests/` 中创建 `test_user_usage.py` 和 `test_admin_usage.py`，覆盖以下场景：
- 各统计 API 的基本查询（时间段过滤、正确聚合）
- 用户只能看到自己的用量，不能看其他用户
- Admin 才能访问 Admin 用量 API（普通用户 403）
- 导出 CSV 返回正确的 `Content-Type` 和数据

**Batch 2 验收标准：**
- [ ] 用户能在"我的用量"页面看到按模型的费用分布饼图和趋势折线图
- [ ] Admin 能在"用量分析"页面看到全局按模型的排行和堆叠趋势图
- [ ] Admin 能导出 CSV 报表

---

## Batch 3：高级功能（可延后）

> 依赖 Batch 2 完成。估计 2–3 天。

### Step 1：model_usage_daily 预聚合表

创建 Alembic migration：

```sql
CREATE TABLE model_usage_daily (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL,
    user_id         UUID NOT NULL REFERENCES users(id),
    model_id        VARCHAR(100) NOT NULL,
    key_id          UUID REFERENCES user_api_keys(id),
    request_count   INTEGER DEFAULT 0,
    input_tokens    BIGINT DEFAULT 0,
    output_tokens   BIGINT DEFAULT 0,
    total_cost_usd  DECIMAL(10,4) DEFAULT 0,
    avg_latency_ms  INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0,
    UNIQUE(date, user_id, model_id, key_id)
);
CREATE INDEX idx_model_usage_daily_date ON model_usage_daily(date);
CREATE INDEX idx_model_usage_daily_user ON model_usage_daily(user_id, date);
CREATE INDEX idx_model_usage_daily_model ON model_usage_daily(model_id, date);
```

实现每日聚合任务（使用项目现有的定时任务框架，如 APScheduler / Celery Beat / cron）：

- 每天凌晨 01:00 执行，聚合前一天的 `request_logs` 到 `model_usage_daily`
- 聚合维度：`(date, user_id, model_id, key_id)` 的组合
- 聚合后，Batch 2 的统计 API 改为优先查 `model_usage_daily`（时间范围超过 7 天时），实时数据仍查 `request_logs`

### Step 2：model_pricing_history 表

创建 Alembic migration：

```sql
CREATE TABLE model_pricing_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id        VARCHAR(100) NOT NULL,
    old_input_price DECIMAL(10,4),
    new_input_price DECIMAL(10,4) NOT NULL,
    old_output_price DECIMAL(10,4),
    new_output_price DECIMAL(10,4) NOT NULL,
    changed_by      UUID NOT NULL REFERENCES users(id),
    changed_at      TIMESTAMP DEFAULT NOW(),
    reason          TEXT
);
```

回到 Batch 1 Step 5 的 TODO 注释处，补全 `update_model_pricing()` 的历史记录写入逻辑。

新增 Admin API：`GET /api/admin/models/{model_id}/pricing-history`，返回该模型的定价变更历史。

### Step 3：定时模型同步任务

实现每日凌晨自动模型发现任务：

1. 遍历所有供应商
2. 对每个供应商调用 `ModelDiscoveryService.discover_models()`
3. 发现新模型（原本不在 catalog 中的）后，**不自动启用**，保持 `status='pending'`
4. 记录发现结果到日志（后续可扩展为通知 Admin）

### Step 4：user_model_limits 表（模型级额度限制）

创建 Alembic migration：

```sql
CREATE TABLE user_model_limits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    model_id        VARCHAR(100) NOT NULL,
    monthly_limit_usd DECIMAL(10,2),
    daily_request_limit INTEGER,
    UNIQUE(user_id, model_id)
);
```

Admin API：
- `GET /api/admin/users/{user_id}/model-limits`：查询该用户的模型级限制
- `PUT /api/admin/users/{user_id}/model-limits/{model_id}`：设置或更新限制
- `DELETE /api/admin/users/{user_id}/model-limits/{model_id}`：删除限制

在网关转发前，检查当前用户对请求模型是否有 `daily_request_limit` 或 `monthly_limit_usd` 超限，超限时返回 429。

### Step 5：额度告警

在每次请求写入 `request_logs` 后，检查用户的总额度和模型级额度使用情况：

| 阈值 | 动作 |
|------|------|
| 80% | 在响应的 `x_ltm` 字段或响应头中附加 `quota_warning: "80%"` |
| 95% | 同上，`quota_warning: "95%"`；同时记录告警日志（后续可扩展为邮件/Webhook 通知 Admin） |
| 100% | 拒绝请求，返回 429，`x_ltm.quota_exceeded: true` |

**Batch 3 验收标准：**
- [ ] 每日聚合任务正常运行，`model_usage_daily` 有数据
- [ ] 定价变更有历史记录
- [ ] Admin 可对特定用户设置模型级使用限制
- [ ] 用量超过 95% 时响应中有告警字段

---

## 注意事项

1. **不要破坏现有 API 的向后兼容性**：`x_ltm` 字段是新增顶层字段，不影响现有客户端解析 `choices`、`usage` 等标准字段
2. **加密存储**：`override_input_price`、`override_output_price` 等价格字段是明文，但 `api_key` 字段继续使用现有的加密方式
3. **所有外部 HTTP 请求**（供应商模型发现）使用 `httpx.AsyncClient`，超时统一 10 秒
4. **测试隔离**：测试文件中所有数据库操作使用独立的测试数据库或 rollback，所有外部 HTTP 请求用 `unittest.mock` 或 `respx` mock
5. **定价精度**：`DECIMAL(10,4)` 对应 `$X.XXXX/1M tokens`；`cost_usd` 用 `DECIMAL(10,6)` 保留更多小数位，避免小额请求四舍五入丢失精度
6. **coding_plan Key 的 plan_models** 存储为 JSON 数组，读取时做 `model_id in key.plan_models` 判断
7. **Batch 顺序**：每个 Batch 完成所有 Step 和测试后，提交一次 git commit，再进入下一 Batch
