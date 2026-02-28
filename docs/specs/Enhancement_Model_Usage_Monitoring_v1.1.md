# 优化方案：模型级用量监测与分析

> **文档类型**: 优化方案（Enhancement Proposal）  
> **版本**: v1.1
> **日期**: 2026-02-27  
> **关联**: LLM Token Manager PRD v1.2、Feature Spec v1.1  
> **优先级**: P1（MVP 后首批优化）  
> **参考**: OpenRouter Activity Dashboard / Usage Accounting  
> **变更说明**:  
> - v2.0 新增「模型白名单管理」与「供应商模型自动发现」章节，重构模型目录数据模型  
> - v2.1 新增「供应商 Key 计划类型」，区分标准 API Key 与 Coding Plan 订阅 Key，影响模型可用范围与路由策略

---

## 1. 现状分析

### 1.1 已有的基础

当前 `request_logs` 表已经记录了每次请求的 `model` 字段，意味着原始数据是有的。但存在以下不足：

| 能力 | 当前状态 | 目标 |
|------|---------|------|
| 记录每次请求用了哪个模型 | ✅ request_logs.model | ✅ |
| 按模型计算不同的费用 | ❌ 只有粗粒度的 model_pricing | 精确到每个模型的 input/output 单价 |
| 用户看到自己按模型的用量分布 | ❌ 只有总额度消耗 | 按模型、按 Key、按时间段看 |
| Admin 看到全局按模型的用量分析 | ❌ 只有用户级汇总 | 多维度报表 + 导出 |
| API 响应中返回本次费用 | ❌ 只有 token 数 | 返回 token + 费用 |
| 供应商导入时自动拉取可用模型 | ❌ 完全手动配置 | 自动发现 + 手动微调 |
| Admin 按供应商管理模型白名单 | ❌ 无模型维度管控 | 供应商 → 模型的启用/禁用管理 |

### 1.2 核心问题

**问题一：计费精度失真**

同一个供应商 Key 背后有多个模型，每个模型价格不同。例如 Anthropic 的一个 Key 可以调用：

| 模型 | Input 单价 | Output 单价 |
|------|-----------|------------|
| claude-sonnet-4-20250514 | $3 / 1M tokens | $15 / 1M tokens |
| claude-opus-4-20250514 | $15 / 1M tokens | $75 / 1M tokens |
| claude-haiku-4-5-20251001 | $0.80 / 1M tokens | $4 / 1M tokens |

如果不按模型区分定价，用 Haiku 的人和用 Opus 的人在费用上看起来一样，成本核算就完全失真。

**问题二：模型管理缺乏自动化**

当前 Admin 添加供应商后，需要手动逐一添加支持的模型及其定价。这带来两个问题：

1. **新供应商接入成本高**：以 Anthropic 为例，一个 Key 支持 10+ 模型，手动逐一录入效率低下
2. **模型更新感知滞后**：供应商发布新模型后（如 Claude 新版本），Admin 无法及时知晓并启用

**问题三：`GET /v1/models` 端点无法返回准确信息**

当 Claude Code / OpenCode 等客户端调用 `GET /v1/models` 时，网关需要知道当前启用了哪些模型才能正确响应。没有模型白名单管理，这个端点要么返回全量模型（含实际不可用的），要么无法实现。

**问题四：供应商 Key 的计划类型未区分**

并非所有供应商 API Key 都是通用的按量付费 Key。部分供应商提供**订阅制的 Coding Plan**，其 Key 有特殊限制：

| 供应商 | Key 类型 | 特点 | 限制 |
|--------|---------|------|------|
| 智谱 GLM | Coding Plan 订阅 Key | 月费订阅，面向编码工具 | 仅支持 coding 相关模型（如 GLM-5），不保证支持通用 API 大量调用 |
| 智谱 GLM | 标准 API Key | 按量付费 | 支持所有模型，无场景限制 |
| MiniMax | Coding Plan Key | 月费订阅 | 类似限制 |
| Anthropic | 标准 API Key | 按量付费 | 支持所有 Claude 模型 |

如果不区分 Key 类型，网关可能用 Coding Plan Key 去转发通用对话请求导致调用失败，或将本应使用 Coding Plan 低成本通道的编码请求路由到了按量付费 Key，造成不必要的开支。

---

## 2. 供应商模型自动发现

### 2.1 设计思路

主流 LLM 供应商均提供模型列表 API，但**不提供定价 API**。因此采用混合策略：

| 能力 | 来源 | 说明 |
|------|------|------|
| 模型 ID 列表 | 供应商 API 自动拉取 | `GET /v1/models` (OpenAI) 或 `GET /v1/models` (Anthropic) |
| 模型 display_name | 供应商 API（部分支持） | Anthropic 返回 `display_name`，OpenAI 不返回 |
| 模型定价 | 内置默认定价表 + Admin 手动覆盖 | 供应商不提供定价 API，需维护内置数据库 |
| 模型能力标签 | 内置默认值 + Admin 覆盖 | context_window、supports_vision 等 |

### 2.2 各供应商的模型发现接口

#### OpenAI 格式（OpenAI / 通义千问等兼容接口）

```
GET {base_url}/models
Authorization: Bearer {api_key}

Response:
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4o",               ← model_id
      "object": "model",
      "created": 1686935002,
      "owned_by": "openai"           ← 可用于归属标识
    }
  ]
}
```

> 注意：OpenAI `/v1/models` 返回的列表包含所有模型（含 embedding、tts、dall-e 等），需要过滤出 chat 类模型。

#### Anthropic 格式

```
GET {base_url}/v1/models
x-api-key: {api_key}
anthropic-version: 2023-06-01

Response:
{
  "data": [
    {
      "id": "claude-sonnet-4-20250514",    ← model_id
      "display_name": "Claude Sonnet 4",   ← 可直接使用
      "created_at": "2025-02-19T00:00:00Z",
      "type": "model"
    }
  ],
  "has_more": true,
  "first_id": "...",
  "last_id": "..."
}
```

> Anthropic 的接口支持分页（`has_more` + cursor），需要循环拉取完整列表。

#### 国内供应商（智谱 GLM / MiniMax 等）

部分国内供应商提供 OpenAI 兼容的 `/v1/models` 端点，部分不提供。对于不提供模型列表接口的供应商，跳过自动发现，回退到手动配置。

### 2.3 自动发现触发时机

| 触发场景 | 行为 |
|----------|------|
| Admin **首次添加供应商 API Key** | 立即调用供应商模型列表接口，拉取可用模型 |
| Admin **手动点击「刷新模型列表」** | 重新拉取，合并新模型，不影响已有配置 |
| **定时任务**（每日凌晨，可选） | 后台自动同步，发现新模型后标记为「待审核」 |

### 2.4 自动发现流程

```
Admin 添加供应商 Key
        │
        ▼
  根据 api_format 选择发现策略
        │
        ├─ openai  → GET {base_url}/models (Bearer)
        ├─ anthropic → GET {base_url}/v1/models (x-api-key)
        └─ 不支持  → 跳过，提示手动添加
        │
        ▼
  过滤出 chat 类模型
  （排除 embedding / tts / image 等非对话模型）
        │
        ▼
  与内置定价表匹配
        │
        ├─ 匹配到 → 自动填充 input_price / output_price / 能力标签
        └─ 未匹配 → 标记为「待定价」，提示 Admin 补充
        │
        ▼
  写入 model_catalog 表
  （默认 is_active = false，需 Admin 确认启用）
        │
        ▼
  返回发现结果摘要给 Admin
  「发现 12 个模型，其中 8 个已匹配定价，4 个需手动配置」
```

### 2.5 内置默认定价表

由于供应商不提供定价 API，网关需要维护一份内置的模型定价数据库。此数据随应用发版更新。

```python
# backend/services/model_pricing_defaults.py

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
        "input_price": 0.0000,   # 待 Admin 确认
        "output_price": 0.0000,
        "context_window": 128000,
        "max_output": 4096,
        "supports_vision": False,
        "supports_tools": True,
    },
    # ── MiniMax ──
    "minimax-m2.5": {
        "display_name": "MiniMax M2.5",
        "input_price": 0.0000,   # 待 Admin 确认
        "output_price": 0.0000,
        "context_window": 1000000,
        "max_output": 65536,
        "supports_vision": False,
        "supports_tools": True,
    },
    # ... 更多模型
}
```

### 2.6 Chat 模型过滤策略

OpenAI 的 `/v1/models` 返回所有类型模型（包括 embedding、tts、image 生成等），需要过滤。策略：

```python
# 白名单前缀：只保留 chat 类模型
CHAT_MODEL_PREFIXES = [
    "gpt-",
    "o1-", "o3-", "o4-",
    "claude-",
    "glm-",
    "minimax-",
    "qwen-",
    "ernie-",
    "deepseek-",
]

# 黑名单关键词：排除非对话模型
NON_CHAT_KEYWORDS = [
    "embedding", "embed",
    "tts", "whisper", "audio",
    "dall-e", "image",
    "moderation",
    "instruct",  # 旧版 completions 模型
]

def is_chat_model(model_id: str) -> bool:
    model_lower = model_id.lower()
    if any(kw in model_lower for kw in NON_CHAT_KEYWORDS):
        return False
    if any(model_lower.startswith(prefix) for prefix in CHAT_MODEL_PREFIXES):
        return True
    return False  # 未知模型默认不纳入，Admin 可手动添加
```

### 2.7 供应商 Key 计划类型（Key Plan）

#### 2.7.1 问题场景

以智谱 GLM 为例，团队可能同时持有两种 Key：

```
供应商：智谱 GLM
├── Key A (标准 API Key)     → 按量付费，支持 GLM-5、GLM-4-Plus、GLM-4-Flash 等全部模型
└── Key B (Coding Plan Key)  → 月费 ¥99 订阅，仅限 GLM-5，面向 Claude Code / OpenCode 等编码工具
```

两个 Key 的**可用模型范围不同、计费方式不同、使用场景不同**，网关必须区分处理。

#### 2.7.2 Key Plan 类型定义

| key_plan | 说明 | 典型供应商 | 可用模型 | 计费方式 |
|----------|------|-----------|----------|----------|
| `standard` | 标准按量付费 Key | 所有供应商 | 该供应商的全部已启用模型 | 按 token 计费（input/output 单价） |
| `coding_plan` | 编码工具订阅 Key | 智谱 GLM、MiniMax | 仅限订阅计划包含的模型 | 月费订阅，调用不额外计费（或有包量上限） |

#### 2.7.3 对数据模型的影响

`provider_api_keys` 表新增字段：

```sql
ALTER TABLE provider_api_keys ADD COLUMN key_plan VARCHAR(20) DEFAULT 'standard';
    -- 'standard' | 'coding_plan'
ALTER TABLE provider_api_keys ADD COLUMN plan_models JSON DEFAULT NULL;
    -- Coding Plan Key 允许的模型列表，如 ["glm-5"]
    -- standard Key 此字段为 null，表示不限制（由 model_catalog 决定）
ALTER TABLE provider_api_keys ADD COLUMN plan_description TEXT DEFAULT NULL;
    -- 备注信息，如 "GLM Coding Plan 月费订阅 ¥99"
```

#### 2.7.4 对网关路由的影响

选择供应商 Key 时，按以下优先级匹配：

```python
async def select_provider_key(
    provider: Provider,
    model_id: str,
    db: AsyncSession
) -> ProviderApiKey:
    """
    选择最合适的供应商 Key 转发请求。
    优先级：
    1. Coding Plan Key（如果请求的模型在其 plan_models 中）→ 节省成本
    2. Standard Key（兜底，支持所有已启用模型）
    """
    active_keys = await get_active_provider_keys(db, provider.id)

    # 优先尝试 Coding Plan Key
    for key in active_keys:
        if key.key_plan == "coding_plan" and key.plan_models:
            if model_id in key.plan_models:
                return key

    # 回退到 Standard Key
    for key in active_keys:
        if key.key_plan == "standard":
            return key

    raise NoAvailableKeyError(f"No active key for {provider.name}/{model_id}")
```

**路由逻辑说明**：

- Coding Plan Key 可以用于任何来源的请求（不需要判断请求是否来自编码工具），只要模型匹配就优先使用——因为 Coding Plan 通常成本更低
- 如果 Coding Plan Key 的 `plan_models` 不包含请求的模型，则跳过该 Key
- `standard` Key 作为兜底，支持 `model_catalog` 中该供应商下所有已启用模型
- 如果同类型存在多个 Key，按现有的 RPM 限流 + 轮转逻辑选择

#### 2.7.5 对模型发现的影响

不同 Key Plan 的发现行为：

| key_plan | 自动发现行为 |
|----------|------------|
| `standard` | 正常拉取完整模型列表 |
| `coding_plan` | **跳过自动发现**，因为此类 Key 可能不支持 `/v1/models` 端点，或返回的列表不准确。Admin 手动填写 `plan_models` |

#### 2.7.6 对计费的影响

| key_plan | 计费方式 | `request_logs` 记录 |
|----------|----------|-------------------|
| `standard` | 按 model_catalog 中的单价计算 `cost_usd` | `cost_usd` = token × 单价 |
| `coding_plan` | 月费订阅，单次调用不额外产生费用 | `cost_usd` = 0（或由 Admin 配置一个折算单价用于统计） |

Admin 可选择为 Coding Plan Key 设置一个**虚拟单价**（如按订阅费除以预估月调用量折算），便于在用量报表中体现该 Key 的成本占比。`provider_api_keys` 新增可选字段：

```sql
ALTER TABLE provider_api_keys ADD COLUMN override_input_price DECIMAL(10,4) DEFAULT NULL;
ALTER TABLE provider_api_keys ADD COLUMN override_output_price DECIMAL(10,4) DEFAULT NULL;
    -- 非 null 时覆盖 model_catalog 的定价（仅限通过此 Key 转发的请求）
```

#### 2.7.7 Admin 添加 Key 的流程变更

```
Admin 添加供应商 Key
        │
        ▼
  选择 Key Plan 类型
        │
        ├─ standard ──────────→ 存储 Key → 触发自动发现 → 完成
        │
        └─ coding_plan ──────→ 存储 Key
                                   │
                                   ▼
                            手动指定 plan_models
                            (如 ["glm-5"])
                                   │
                                   ▼
                            可选：设置虚拟单价
                                   │
                                   ▼
                               完成（不触发自动发现）
```

---

## 3. 模型白名单管理

### 3.1 设计原则

模型白名单管理分为两个层级：

| 层级 | 控制主体 | 效果 |
|------|----------|------|
| **平台级**（`model_catalog.is_active`） | Admin | 模型全局启用/禁用，禁用后所有用户不可用 |
| **用户级**（`users.allowed_models`） | Admin | 限制特定用户只能使用指定模型（已有功能） |

### 3.2 平台级模型白名单管理

Admin 在供应商管理页面中，可以按供应商查看和管理模型白名单：

```
供应商管理页面
├── Anthropic（3 个 Key，8 个模型）
│   ├── ✅ claude-sonnet-4-20250514     $3/$15      已启用
│   ├── ✅ claude-haiku-4-5-20251001    $0.8/$4     已启用
│   ├── ❌ claude-opus-4-20250514       $15/$75     已禁用（成本过高）
│   ├── ⚠️ claude-sonnet-4-5-20250929   待定价      待审核
│   └── ...
├── OpenAI（2 个 Key，5 个模型）
│   ├── ✅ gpt-4o                       $2.5/$10    已启用
│   ├── ✅ gpt-4o-mini                  $0.15/$0.6  已启用
│   └── ...
└── 智谱 GLM（1 个 Key，2 个模型）
    ├── ✅ glm-5                        待定价      已启用
    └── ...
```

### 3.3 模型状态流转

```
┌───────────┐   Admin 确认启用   ┌──────────┐
│  待审核    │ ────────────────→ │  已启用   │
│ (pending)  │                   │ (active)  │
└───────────┘                   └──────────┘
      ↑                              │ ↑
      │ 自动发现新模型     Admin 禁用 │ │ Admin 重新启用
      │                              ↓ │
      │                         ┌──────────┐
      │                         │  已禁用   │
      └─────────────────────── │(inactive) │
          Admin 删除后重新发现   └──────────┘
```

### 3.4 与 `GET /v1/models` 端点的联动

`GET /v1/models` 只返回 `is_active = true` 的模型：

```python
@router.get("/v1/models")
async def list_models(
    user: User = Depends(verify_platform_key),
    db: AsyncSession = Depends(get_db)
):
    # 1. 查询所有平台级启用的模型
    active_models = await get_active_models(db)

    # 2. 如果该用户有 allowed_models 限制，进一步过滤
    if user.allowed_models:
        active_models = [
            m for m in active_models
            if m.model_id in user.allowed_models
        ]

    # 3. 返回 OpenAI 兼容格式
    return {
        "object": "list",
        "data": [
            {
                "id": m.model_id,
                "object": "model",
                "created": int(m.created_at.timestamp()),
                "owned_by": m.provider.name,
            }
            for m in active_models
        ]
    }
```

---

## 4. 数据模型改造

### 4.1 新增：model_catalog 表（模型目录）

参考 OpenRouter 的模型目录，建立平台级的模型注册表：

```sql
CREATE TABLE model_catalog (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 模型标识
    model_id        VARCHAR(100) NOT NULL UNIQUE,  -- "claude-sonnet-4-20250514"
    display_name    VARCHAR(200) NOT NULL,          -- "Claude Sonnet 4"

    -- 归属
    provider_id     UUID NOT NULL REFERENCES providers(id),

    -- 定价（USD per 1M tokens）
    input_price     DECIMAL(10,4) NOT NULL DEFAULT 0,   -- 3.0000 = $3/1M
    output_price    DECIMAL(10,4) NOT NULL DEFAULT 0,   -- 15.0000 = $15/1M
    cache_write_price   DECIMAL(10,4) DEFAULT 0,        -- 缓存写入价格（Phase 2）
    cache_read_price    DECIMAL(10,4) DEFAULT 0,        -- 缓存读取价格（Phase 2）

    -- 模型元信息
    context_window  INTEGER,                         -- 200000
    max_output      INTEGER,                         -- 8192
    supports_vision BOOLEAN DEFAULT FALSE,
    supports_tools  BOOLEAN DEFAULT FALSE,
    supports_streaming BOOLEAN DEFAULT TRUE,

    -- 状态管理
    status          VARCHAR(20) DEFAULT 'pending',   -- 'pending' | 'active' | 'inactive'
    is_pricing_confirmed BOOLEAN DEFAULT FALSE,      -- 定价是否已由 Admin 确认

    -- 数据来源
    source          VARCHAR(20) DEFAULT 'manual',    -- 'auto_discovered' | 'manual' | 'builtin_default'

    -- 审计
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_model_catalog_provider ON model_catalog(provider_id);
CREATE INDEX idx_model_catalog_status ON model_catalog(status);
```

**状态字段说明**：

| status | is_pricing_confirmed | 含义 |
|--------|---------------------|------|
| `pending` | `false` | 自动发现但尚未被 Admin 审核 |
| `pending` | `true` | 已确认定价，但尚未启用 |
| `active` | `true` | 正常启用，用户可调用 |
| `active` | `false` | 启用但定价可能不准（Admin 可能使用了内置默认值） |
| `inactive` | `*` | Admin 主动禁用 |

### 4.2 修改：request_logs 表

增加费用相关字段（如果还没有的话），由网关在每次请求后计算填入：

```sql
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS cost_usd DECIMAL(10,6) DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS input_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS output_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS cache_write_tokens INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS latency_ms INTEGER;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS key_plan VARCHAR(20) DEFAULT 'standard';
    -- 记录本次请求使用的供应商 Key 计划类型，便于区分成本来源
```

**费用计算公式**：

```python
cost_usd = (input_tokens * model.input_price / 1_000_000)
         + (output_tokens * model.output_price / 1_000_000)
```

### 4.3 新增：model_usage_daily 表（每日汇总，预聚合）

为了 Dashboard 查询性能，每天定时聚合：

```sql
CREATE TABLE model_usage_daily (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL,
    user_id         UUID NOT NULL REFERENCES users(id),
    model_id        VARCHAR(100) NOT NULL,
    key_id          UUID REFERENCES user_api_keys(id),  -- nullable，用于 Key 维度

    -- 聚合指标
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

### 4.4 新增：model_pricing_history 表（定价变更日志）

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
    reason          TEXT                              -- 'manual_update' | 'builtin_sync' | 'admin_override'
);
```

---

## 5. Admin API：模型发现与白名单管理

### 5.1 供应商模型发现 API

#### POST `/api/admin/providers/{id}/discover-models`

触发对指定供应商的模型列表拉取。

**请求**：无 body（使用已存储的供应商 API Key 调用上游接口）。

**响应**：

```json
{
  "discovered": 12,
  "new_models": 4,
  "pricing_matched": 3,
  "pricing_pending": 1,
  "details": [
    {
      "model_id": "claude-sonnet-4-5-20250929",
      "display_name": "Claude Sonnet 4.5",
      "status": "new",
      "pricing_source": "builtin_default",
      "input_price": 3.0000,
      "output_price": 15.0000
    },
    {
      "model_id": "claude-opus-4-6",
      "display_name": "Claude Opus 4.6",
      "status": "new",
      "pricing_source": "none",
      "input_price": null,
      "output_price": null,
      "message": "未找到内置定价，请手动配置"
    }
  ]
}
```

**错误处理**：

| 场景 | HTTP 状态码 | 说明 |
|------|-----------|------|
| 供应商无可用 API Key | 400 | 需先添加 Key |
| 供应商不支持模型列表接口 | 422 | 提示手动添加模型 |
| 上游接口返回错误 | 502 | 返回上游错误信息 |
| 上游接口超时 | 504 | 设置 10s 超时 |

### 5.2 模型白名单管理 API

#### GET `/api/admin/providers/{id}/models`

获取指定供应商下的所有模型及其状态。

**响应**：

```json
{
  "provider_id": "uuid",
  "provider_name": "Anthropic",
  "models": [
    {
      "id": "uuid",
      "model_id": "claude-sonnet-4-20250514",
      "display_name": "Claude Sonnet 4",
      "status": "active",
      "input_price": 3.0000,
      "output_price": 15.0000,
      "is_pricing_confirmed": true,
      "context_window": 200000,
      "supports_vision": true,
      "supports_tools": true,
      "source": "auto_discovered",
      "created_at": "2026-02-27T10:00:00Z",
      "updated_at": "2026-02-27T10:00:00Z"
    }
  ],
  "summary": {
    "total": 8,
    "active": 5,
    "pending": 2,
    "inactive": 1,
    "pricing_pending": 1
  }
}
```

#### PUT `/api/admin/models/{model_id}/status`

启用/禁用/设为待审核。

**请求**：

```json
{
  "status": "active"
}
```

#### PUT `/api/admin/models/{model_id}/pricing`

更新模型定价。

**请求**：

```json
{
  "input_price": 3.0000,
  "output_price": 15.0000,
  "reason": "同步 Anthropic 2026-02 定价调整"
}
```

写入 `model_pricing_history` 记录变更。

#### POST `/api/admin/models`

手动添加模型（用于供应商不支持自动发现的情况）。

**请求**：

```json
{
  "model_id": "glm-5",
  "display_name": "GLM-5",
  "provider_id": "uuid",
  "input_price": 1.0000,
  "output_price": 5.0000,
  "context_window": 128000,
  "status": "active"
}
```

#### POST `/api/admin/providers/{id}/models/batch-activate`

批量启用模型（自动发现后一键启用所有已定价模型）。

**请求**：

```json
{
  "model_ids": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
  "activate_all_priced": false
}
```

`activate_all_priced = true` 时忽略 `model_ids`，启用所有 `is_pricing_confirmed = true` 的 pending 模型。

---

## 6. 自动发现服务实现

### 6.1 项目结构变更

```
backend/
├── services/
│   ├── model_discovery.py           # 模型发现核心逻辑
│   ├── model_pricing_defaults.py    # 内置默认定价表
│   ├── model_catalog_service.py     # 模型目录 CRUD
│   └── key_selector.py              # Key 选择路由（含 plan 优先级）
├── routers/
│   └── admin_models.py              # 模型管理 Admin API
└── tests/
    ├── test_model_discovery.py      # 模型发现测试
    ├── test_admin_models.py         # 模型管理 API 测试
    └── test_key_plan_routing.py     # Key 计划类型路由测试
```

### 6.2 模型发现服务

```python
# backend/services/model_discovery.py

class ModelDiscoveryService:
    """从供应商 API 自动发现可用模型"""

    async def discover_models(
        self, provider: Provider, api_key: str, db: AsyncSession
    ) -> DiscoveryResult:
        """
        主入口：根据供应商类型调用对应的发现策略。
        返回发现结果摘要。
        """
        if provider.api_format == "openai":
            raw_models = await self._fetch_openai_models(provider.base_url, api_key)
        elif provider.api_format == "anthropic":
            raw_models = await self._fetch_anthropic_models(provider.base_url, api_key)
        else:
            raise UnsupportedDiscoveryError(f"不支持自动发现: {provider.api_format}")

        # 过滤出 chat 类模型
        chat_models = [m for m in raw_models if is_chat_model(m["id"])]

        # 匹配内置定价、写入数据库
        return await self._merge_into_catalog(chat_models, provider, db)

    async def _fetch_openai_models(self, base_url: str, api_key: str) -> list[dict]:
        """调用 OpenAI 格式的 GET /v1/models"""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {"id": m["id"], "display_name": None, "owned_by": m.get("owned_by")}
                for m in data.get("data", [])
            ]

    async def _fetch_anthropic_models(self, base_url: str, api_key: str) -> list[dict]:
        """调用 Anthropic 格式的 GET /v1/models（支持分页）"""
        models = []
        params = {"limit": 100}
        async with httpx.AsyncClient(timeout=10) as client:
            while True:
                resp = await client.get(
                    f"{base_url.rstrip('/')}/v1/models",
                    params=params,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01"
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                for m in data.get("data", []):
                    models.append({
                        "id": m["id"],
                        "display_name": m.get("display_name"),
                        "owned_by": "anthropic"
                    })
                if not data.get("has_more"):
                    break
                params["after_id"] = data["last_id"]
        return models

    async def _merge_into_catalog(
        self, models: list[dict], provider: Provider, db: AsyncSession
    ) -> DiscoveryResult:
        """将发现的模型与内置定价匹配后写入 model_catalog"""
        from .model_pricing_defaults import DEFAULT_MODEL_PRICING

        result = DiscoveryResult(discovered=len(models))

        for m in models:
            existing = await db.execute(
                select(ModelCatalog).where(ModelCatalog.model_id == m["id"])
            )
            if existing.scalar_one_or_none():
                continue  # 已存在，跳过

            defaults = DEFAULT_MODEL_PRICING.get(m["id"], {})

            catalog_entry = ModelCatalog(
                model_id=m["id"],
                display_name=m.get("display_name") or defaults.get("display_name", m["id"]),
                provider_id=provider.id,
                input_price=defaults.get("input_price", 0),
                output_price=defaults.get("output_price", 0),
                context_window=defaults.get("context_window"),
                max_output=defaults.get("max_output"),
                supports_vision=defaults.get("supports_vision", False),
                supports_tools=defaults.get("supports_tools", False),
                status="pending",
                is_pricing_confirmed=bool(defaults.get("input_price")),
                source="auto_discovered" if not defaults else "builtin_default",
            )
            db.add(catalog_entry)
            result.new_models += 1

            if catalog_entry.is_pricing_confirmed:
                result.pricing_matched += 1
            else:
                result.pricing_pending += 1

        await db.commit()
        return result
```

### 6.3 供应商 Key 添加时触发自动发现

修改 Admin 添加供应商 Key 的接口，在 Key 添加成功后异步触发模型发现：

```python
# backend/routers/admin.py

@router.post("/api/admin/providers/{provider_id}/keys")
async def add_provider_key(
    provider_id: UUID,
    body: AddProviderKeyRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    添加供应商 API Key。
    body.key_plan: "standard" | "coding_plan" (默认 standard)
    body.plan_models: ["glm-5"] (仅 coding_plan 时需填写)
    body.plan_description: 备注 (可选)
    body.override_input_price / override_output_price: 虚拟单价 (可选)
    """
    provider = await get_provider(db, provider_id)

    # 1. 校验 coding_plan 必须提供 plan_models
    if body.key_plan == "coding_plan" and not body.plan_models:
        raise HTTPException(400, "Coding Plan Key 必须指定 plan_models（该 Key 支持的模型列表）")

    # 2. 存储加密 Key（已有逻辑），附带 plan 信息
    key_obj = await store_encrypted_key(
        provider, body.api_key, db,
        key_plan=body.key_plan or "standard",
        plan_models=body.plan_models,
        plan_description=body.plan_description,
        override_input_price=body.override_input_price,
        override_output_price=body.override_output_price,
    )

    # 3. 仅 standard Key 且为该供应商首个 standard Key 时触发自动发现
    discovery_result = None
    if body.key_plan != "coding_plan":
        standard_keys_count = await count_provider_keys(
            db, provider_id, key_plan="standard"
        )
        if standard_keys_count == 1:  # 刚添加的是第一个 standard Key
            try:
                discovery_service = ModelDiscoveryService()
                discovery_result = await discovery_service.discover_models(
                    provider, body.api_key, db
                )
            except Exception as e:
                logger.warning(f"Model discovery failed for {provider.name}: {e}")

    return {
        "key_id": str(key_obj.id),
        "key_suffix": key_obj.key_suffix,
        "key_plan": key_obj.key_plan,
        "plan_models": key_obj.plan_models,
        "discovery": discovery_result.to_dict() if discovery_result else None
    }
```

---

## 7. API 响应增强

### 7.1 OpenAI 格式响应（/v1/chat/completions）

在现有 `usage` 字段基础上，追加网关级信息。在响应的顶层追加一个 `x_ltm` 字段（不破坏 OpenAI 格式兼容性）：

```json
{
  "id": "chatcmpl-xxx",
  "model": "claude-sonnet-4-20250514",
  "choices": [],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150
  },
  "x_ltm": {
    "cost_usd": 0.001050,
    "remaining_quota_usd": 8.95,
    "key_id_suffix": "...a3f8"
  }
}
```

### 7.2 Anthropic 格式响应（/v1/messages）

Anthropic 格式本身已包含 `usage`，网关在透传后追加网关级信息到响应头（不修改 body，保持透传）：

```
X-LTM-Cost-USD: 0.001050
X-LTM-Remaining-Quota-USD: 8.95
X-LTM-Key-ID-Suffix: ...a3f8
```

---

## 8. 统计分析 API

### 8.1 用户级统计 API

#### GET `/api/user/usage/by-model`

用户查看自己按模型的用量分布。

**请求参数**：
- `period`: `day` | `week` | `month`（默认 month）
- `start_date` / `end_date`：可选时间范围

**响应**：

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
    },
    {
      "model_id": "glm-5",
      "display_name": "GLM-5",
      "request_count": 357,
      "input_tokens": 1800000,
      "output_tokens": 600000,
      "cost_usd": 5.00,
      "percentage": 21.4
    }
  ]
}
```

#### GET `/api/user/usage/by-key`

用户查看按 Key 的用量分布（每个 Key 进一步拆分到模型）。

```json
{
  "keys": [
    {
      "key_suffix": "...a3f8",
      "key_name": "Claude Code 主力",
      "total_cost_usd": 15.20,
      "models": [
        { "model_id": "claude-sonnet-4-20250514", "cost_usd": 12.00 },
        { "model_id": "glm-5", "cost_usd": 3.20 }
      ]
    },
    {
      "key_suffix": "...b9c2",
      "key_name": "测试用",
      "total_cost_usd": 8.25,
      "models": [
        { "model_id": "claude-sonnet-4-20250514", "cost_usd": 8.25 }
      ]
    }
  ]
}
```

#### GET `/api/user/usage/timeline`

用户查看时间维度的用量趋势。

**请求参数**：
- `granularity`: `hour` | `day` | `week`
- `model_id`：可选，筛选特定模型

```json
{
  "granularity": "day",
  "data": [
    { "date": "2026-02-24", "requests": 45, "cost_usd": 1.23, "input_tokens": 230000, "output_tokens": 58000 },
    { "date": "2026-02-25", "requests": 62, "cost_usd": 1.87, "input_tokens": 310000, "output_tokens": 82000 },
    { "date": "2026-02-26", "requests": 38, "cost_usd": 0.95, "input_tokens": 180000, "output_tokens": 45000 }
  ]
}
```

### 8.2 Admin 统计 API

#### GET `/api/admin/usage/overview`

全局用量概览。

```json
{
  "period": "2026-02",
  "total_cost_usd": 342.50,
  "total_requests": 18420,
  "active_users": 28,
  "top_models": [
    { "model_id": "claude-sonnet-4-20250514", "cost_usd": 189.30, "requests": 9200 },
    { "model_id": "glm-5", "cost_usd": 98.40, "requests": 6300 },
    { "model_id": "minimax-m2.5", "cost_usd": 54.80, "requests": 2920 }
  ],
  "top_users": [
    { "user_id": "...", "username": "alice", "cost_usd": 52.30 },
    { "user_id": "...", "username": "bob", "cost_usd": 48.10 }
  ]
}
```

#### GET `/api/admin/usage/by-model`

全局按模型的详细用量，可按时间段筛选。

#### GET `/api/admin/usage/by-user`

按用户查看用量，每个用户可展开到模型维度。

#### GET `/api/admin/usage/export`

导出用量报表（CSV 格式），参考 OpenRouter 的导出功能。

**请求参数**：
- `format`: `csv`（后续可加 `pdf`）
- `group_by`: `model` | `user` | `key`
- `start_date` / `end_date`

---

## 9. 前端 Dashboard 设计

### 9.1 供应商模型管理页面（Admin，新增）

```
┌──────────────────────────────────────────────────────┐
│  供应商管理 > 智谱 GLM                               │
├──────────────────────────────────────────────────────┤
│                                                      │
│  供应商信息                                          │
│  名称: 智谱 GLM    格式: Anthropic API               │
│  Base URL: https://open.bigmodel.cn/api/anthropic    │
│                                                      │
│  API Keys                              [添加 Key]    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Key         计划类型       状态   可用模型     │    │
│  ├──────────────────────────────────────────────┤    │
│  │ ...x8f2     🔑 标准 Key    活跃   全部已启用   │    │
│  │             按量付费                          │    │
│  │                                               │    │
│  │ ...k3a9     📦 Coding Plan  活跃   glm-5      │    │
│  │             月费订阅 ¥99                       │    │
│  │             虚拟单价: $0.50/$2.00 /1M tokens   │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  模型白名单                    [🔄 刷新模型列表]      │
│  ┌──────────────────────────────────────────────┐    │
│  │ □ 全选    模型              Input    Output   │    │
│  ├──────────────────────────────────────────────┤    │
│  │ ✅ glm-5                   $0.50   $2.00     │    │
│  │    GLM-5                   active ✓定价已确认 │    │
│  │    路由优先: 📦 Coding Plan Key ...k3a9       │    │
│  │                                               │    │
│  │ ✅ glm-4-plus              $3.00   $15.00    │    │
│  │    GLM-4-Plus              active ✓定价已确认 │    │
│  │    路由: 🔑 标准 Key ...x8f2                  │    │
│  │                                               │    │
│  │ ⚠️ glm-4-flash             待定价             │    │
│  │    GLM-4-Flash             pending ⚠待定价    │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  [批量启用已定价模型]  [手动添加模型]                  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**添加 Key 弹窗**：

```
┌────────────────────────────────────┐
│  添加供应商 API Key                 │
├────────────────────────────────────┤
│                                    │
│  API Key *                         │
│  ┌────────────────────────────┐   │
│  │ sk-xxxxxxxxxxxxxxxx        │   │
│  └────────────────────────────┘   │
│                                    │
│  计划类型 *                        │
│  ○ 🔑 标准 API Key（按量付费）     │
│  ● 📦 Coding Plan（订阅制）        │
│                                    │
│  ── 以下仅 Coding Plan 显示 ──     │
│                                    │
│  支持的模型 *（逗号分隔）           │
│  ┌────────────────────────────┐   │
│  │ glm-5                      │   │
│  └────────────────────────────┘   │
│                                    │
│  备注                              │
│  ┌────────────────────────────┐   │
│  │ GLM Coding Plan 月费 ¥99   │   │
│  └────────────────────────────┘   │
│                                    │
│  虚拟单价（可选，用于报表统计）     │
│  Input: [0.50] $/1M   Output: [2.00] $/1M │
│                                    │
│        [取消]    [确认添加]         │
│                                    │
└────────────────────────────────────┘
```

### 9.2 用户视角 — "我的用量"页面

```
┌──────────────────────────────────────────────────┐
│  我的用量                     2026年2月 ▼        │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌──────┐  ┌──────┐  ┌──────────┐  ┌─────────┐ │
│  │$23.45│  │1,247 │  │$26.55    │  │ 78.6%   │ │
│  │本月消耗│  │请求次数│  │剩余额度   │  │Claude用量│ │
│  └──────┘  └──────┘  └──────────┘  └─────────┘ │
│                                                  │
│  按模型分布（饼图）          用量趋势（折线图）    │
│  ┌──────────────┐          ┌──────────────────┐ │
│  │  ● Sonnet 4  │          │  ╱╲    ╱╲       │ │
│  │    78.6%     │          │ ╱  ╲╱╱  ╲╱╲     │ │
│  │  ● GLM-5    │          │╱           ╲    │ │
│  │    21.4%     │          │ 2/20  2/23  2/26 │ │
│  └──────────────┘          └──────────────────┘ │
│                                                  │
│  按 Key 明细                                     │
│  ┌──────────────────────────────────────────┐   │
│  │ Key           模型         请求   费用    │   │
│  ├──────────────────────────────────────────┤   │
│  │ ...a3f8       Sonnet 4     580   $12.00  │   │
│  │ "Claude Code" GLM-5        310   $3.20   │   │
│  │ ...b9c2       Sonnet 4     350   $8.25   │   │
│  │ "测试用"                                  │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 9.3 Admin 视角 — 用量分析页面

```
┌──────────────────────────────────────────────────┐
│  用量分析                    2026年2月 ▼  导出 ⬇ │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────────┐   │
│  │$342  │  │18.4K │  │ 28   │  │ 3 供应商  │   │
│  │总费用  │  │总请求  │  │活跃用户│  │使用中     │   │
│  └──────┘  └──────┘  └──────┘  └──────────┘   │
│                                                  │
│  ┌─ 按模型 ─┬─ 按用户 ─┬─ 按供应商 ─┐ Tab切换  │
│                                                  │
│  模型用量排行                                     │
│  ┌──────────────────────────────────────────┐   │
│  │ 模型           请求    Token     费用     │   │
│  ├──────────────────────────────────────────┤   │
│  │ Sonnet 4       9,200  28.5M    $189.30   │   │
│  │ ████████████████████████░░░░░░  55.3%    │   │
│  │ GLM-5          6,300  12.8M    $98.40    │   │
│  │ ████████████████░░░░░░░░░░░░░  28.7%    │   │
│  │ MiniMax M2.5   2,920  8.2M     $54.80    │   │
│  │ ██████████░░░░░░░░░░░░░░░░░░  16.0%    │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  费用趋势（按模型堆叠面积图）                      │
│  ┌──────────────────────────────────────────┐   │
│  │ ▓▓▓▓▓▓▓▓▓▓▓▓ Sonnet 4                   │   │
│  │ ░░░░░░░░ GLM-5                           │   │
│  │ ▒▒▒▒ MiniMax                             │   │
│  │  2/1   2/8   2/15  2/22  2/26            │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## 10. 额度管理增强

### 10.1 模型级额度限制（可选）

除了现有的用户级月度总额度外，Admin 可对特定用户设置模型级限制：

```sql
CREATE TABLE user_model_limits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    model_id        VARCHAR(100) NOT NULL,
    monthly_limit_usd DECIMAL(10,2),          -- 该模型的月度额度
    daily_request_limit INTEGER,               -- 每日请求次数限制
    UNIQUE(user_id, model_id)
);
```

用途举例：
- 允许所有人用 Sonnet，但 Opus 只允许高级开发者使用
- 限制实习生每天只能调用 100 次 GLM-5

### 10.2 额度告警

当用户的某个模型或总额度使用超过阈值时，触发通知：
- 80% → 提醒用户
- 95% → 提醒用户 + Admin
- 100% → 拒绝请求

---

## 11. 测试要求

### 11.1 test_model_discovery.py — 模型发现测试

所有供应商 API 调用使用 mock，禁止真实请求。

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_discover_openai_models | Mock OpenAI `/v1/models` 返回混合模型列表 | 正确过滤出 chat 模型，排除 embedding/tts |
| test_discover_anthropic_models | Mock Anthropic `/v1/models` 返回分页结果 | 循环拉取完整列表，正确解析 display_name |
| test_discover_anthropic_pagination | Mock 分页 `has_more=true` + `has_more=false` | 两次请求后返回完整列表 |
| test_merge_with_builtin_pricing | 发现的模型在内置定价表中 | `is_pricing_confirmed=true`，定价正确填充 |
| test_unknown_model_pricing_pending | 发现的模型不在内置定价表中 | `is_pricing_confirmed=false`，定价为 0 |
| test_skip_existing_models | 模型已在 catalog 中 | 不重复写入，不覆盖已有配置 |
| test_discovery_upstream_error | 供应商返回 500 | 抛出异常，不影响已有数据 |
| test_discovery_timeout | 供应商响应超时 | 抛出超时异常 |
| test_unsupported_provider | 供应商 api_format 不支持发现 | 返回 UnsupportedDiscoveryError |
| test_chat_model_filter | 包含 embedding、tts、dalle 等模型 ID | 全部被过滤，仅保留 chat 模型 |
| test_coding_plan_key_skips_discovery | 添加 coding_plan Key | 不触发自动发现 |
| test_standard_key_triggers_discovery | 添加 standard Key（首个） | 触发自动发现 |

### 11.2 test_admin_models.py — 模型管理 API 测试

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_list_provider_models | 获取供应商下的模型列表 | 200，返回正确的模型和摘要 |
| test_activate_model | 将 pending 模型设为 active | 200，状态变更 |
| test_deactivate_model | 将 active 模型设为 inactive | 200，`GET /v1/models` 不再返回 |
| test_update_model_pricing | 修改模型定价 | 200，`model_pricing_history` 有记录 |
| test_manual_add_model | 手动添加模型 | 201，model_catalog 有新记录 |
| test_batch_activate | 批量启用已定价模型 | 200，所有 `is_pricing_confirmed` 的 pending 模型变 active |
| test_trigger_discovery | 调用发现端点 | 200，返回发现结果摘要 |
| test_user_cannot_manage_models | 普通用户调用模型管理 API | 403 |
| test_v1_models_only_active | `GET /v1/models` 只返回 active 模型 | inactive/pending 模型不在列表中 |
| test_v1_models_user_allowed_filter | 用户有 `allowed_models` 限制 | 只返回允许的且 active 的模型 |
| test_auto_discover_on_first_key | 给供应商添加第一个 standard Key | 自动触发模型发现 |
| test_no_discover_on_subsequent_key | 给供应商添加第二个 standard Key | 不触发自动发现 |

### 11.3 test_key_plan_routing.py — Key 计划类型路由测试

| 测试函数 | 验证内容 | 预期 |
|----------|----------|------|
| test_add_coding_plan_key | 添加 coding_plan Key 时必须提供 plan_models | 不提供时 400 |
| test_add_coding_plan_key_success | 正确添加 coding_plan Key | 201，存储 key_plan + plan_models |
| test_add_standard_key_no_plan_models | standard Key 不需要 plan_models | 201，plan_models 为 null |
| test_route_prefer_coding_plan | 请求 glm-5 且有 coding_plan Key | 优先选择 coding_plan Key 转发 |
| test_route_fallback_to_standard | 请求 glm-4-plus 无 coding_plan Key 覆盖 | 选择 standard Key 转发 |
| test_route_no_coding_plan_for_model | coding_plan Key 的 plan_models 不含请求模型 | 跳过 coding_plan Key，使用 standard Key |
| test_coding_plan_cost_zero | 通过 coding_plan Key 转发 | `request_logs.cost_usd` = 0（或使用虚拟单价） |
| test_coding_plan_override_pricing | coding_plan Key 设置了虚拟单价 | `request_logs.cost_usd` 按虚拟单价计算 |
| test_standard_key_normal_pricing | 通过 standard Key 转发 | `request_logs.cost_usd` 按 model_catalog 单价计算 |
| test_no_available_key | 供应商无 active Key 适用于请求模型 | 返回 503（无可用 Key） |

---

## 12. 开发优先级

分三个批次实施，每批独立可用：

### Batch 1：模型目录 + 自动发现 + 白名单管理 + Key 计划类型（4–5 天）

**最高优先级**，这是后续所有功能的基础。

- 创建 `model_catalog` 表 + Alembic migration
- `provider_api_keys` 表新增 `key_plan`、`plan_models`、`override_*_price` 字段 + migration
- 实现 `model_pricing_defaults.py` 内置定价表
- 实现 `ModelDiscoveryService`：OpenAI / Anthropic 模型列表拉取 + chat 模型过滤
- 修改供应商 Key 添加接口：区分 standard / coding_plan，仅 standard 首个 Key 触发自动发现
- Admin API：模型 CRUD + 白名单管理 + 批量启用 + 手动触发发现
- 实现 Key 选择路由逻辑：coding_plan Key 优先匹配 plan_models，standard Key 兜底
- 实现 `GET /v1/models`：返回当前用户可用的 active 模型列表
- 修改计费逻辑：从 `model_catalog` 查询单价，coding_plan Key 使用虚拟单价或零计费
- 修改 `request_logs`：记录 `input_tokens`、`output_tokens`、`cost_usd`、使用的 key_plan
- 在 API 响应中附加费用信息（`x_ltm` 字段 / 响应头）
- 测试覆盖：`test_model_discovery.py` + `test_admin_models.py` + `test_key_plan_routing.py`

**验收**：
- Admin 添加 standard 供应商 Key 后自动拉取模型列表
- Admin 添加 coding_plan Key 时需指定 plan_models，不触发自动发现
- 网关路由请求时优先使用 coding_plan Key（当请求模型在其 plan_models 中）
- Admin 可按供应商管理模型白名单
- `GET /v1/models` 返回用户可用的模型列表
- 每次请求的费用按实际模型单价计算并记录（coding_plan Key 按虚拟单价或零计费）

### Batch 2：统计 API + 用户 Dashboard（3–4 天）

- 用户端 API：`/api/user/usage/by-model`、`by-key`、`timeline`
- Admin 端 API：`/api/admin/usage/overview`、`by-model`、`by-user`
- 前端 — 供应商模型管理页面（模型白名单 + 发现 + 定价配置）
- 前端 — 用户"我的用量"页面（饼图 + 趋势图 + Key 明细表）
- 前端 — Admin"用量分析"页面（排行 + Tab 切换 + 堆叠图）
- 测试覆盖

**验收**：用户和 Admin 都能按模型维度查看用量分布和趋势。

### Batch 3：高级功能（2–3 天，可延后）

- `model_usage_daily` 预聚合表 + 每日定时任务
- 定时模型同步任务（每日凌晨自动发现新模型）
- Admin 导出 CSV 报表
- 模型级额度限制（`user_model_limits` 表）
- 额度告警（80%/95%/100%）
- 定价变更日志（`model_pricing_history`）

**验收**：Admin 可导出报表，可对特定用户设置模型级使用限制，新模型能被自动发现。

---

## 13. 与现有系统的兼容性

| 现有模块 | 影响 | 改动 |
|----------|------|------|
| `/v1/chat/completions` | 计费逻辑改为查 model_catalog；Key 选择逻辑加入 plan 优先级 | 中改 |
| `/v1/messages` | 同上 | 中改 |
| `/v1/models` | 从 model_catalog 读取 active 模型 | 重写（已在 PRD 中规划） |
| `provider_api_keys` 表 | 新增 key_plan、plan_models、override_*_price 字段 | Alembic migration |
| `monthly_usage` 表 | 继续使用，作为用户总额度的快速查询 | 不变 |
| `model_pricing` 表（如已有） | 被 `model_catalog` 替代 | 废弃或合并 |
| 供应商 Key 添加接口 | 新增 key_plan 参数 + 自动发现逻辑 | 中改 |
| 网关 Key 选择逻辑 | 新增 coding_plan 优先级匹配 | 中改（抽取 key_selector.py） |
| 用户 Key 管理 | 不受影响 | 不变 |
| Admin 用户管理 | 不受影响 | 不变 |

---

## 14. 已知限制与后续优化

### 当前限制

| 限制 | 原因 | 后续计划 |
|------|------|----------|
| 定价需手动维护 | 供应商不提供定价 API | 考虑接入 OpenRouter `/api/v1/models` 获取定价 |
| 国内供应商可能不支持自动发现 | 部分供应商无模型列表接口 | 扩展适配器，或支持从配置文件批量导入 |
| 内置定价表需随版本更新 | 模型定价可能变动 | 提供 Admin UI 一键从模板更新定价 |
| Coding Plan Key 的可用模型需手动维护 | 此类 Key 通常不支持 `/v1/models` 查询 | 后续可尝试探测 + Admin 确认 |
| Coding Plan 的包量上限未跟踪 | 订阅计划通常有月调用量上限 | Phase 3 加入 plan_quota 字段和用量统计 |

### Phase 3+ 优化方向

- 接入 OpenRouter 的模型定价数据作为参考来源
- 支持从 CSV / JSON 批量导入模型定价
- prompt caching 费用单独计算
- 管理后台统计增加「按入站协议」维度
- 模型定价变更时自动通知 Admin
- Coding Plan Key 包量上限跟踪与告警（如月调用量接近订阅上限时提醒 Admin）
- 支持更多 Key 计划类型（如 Enterprise Plan、团队共享额度包等）
- Coding Plan Key 自动探测可用模型（尝试发送 test 请求判断模型是否可用）

---

*文档结束*
