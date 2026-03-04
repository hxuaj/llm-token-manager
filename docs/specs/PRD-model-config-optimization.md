# 模型配置系统优化需求文档

> 版本: v1.2
> 日期: 2026-03-03
> 状态: 草案
> 参考: Opencode 模型配置架构、models.dev

---

## 1. 背景与目标

### 1.1 背景

当前 LLM Token Manager 的模型配置系统存在以下问题：

- 模型元数据（定价、能力）需要手动维护，更新滞后
- 多个 OpenAI 兼容供应商存在大量重复代码
- 模型能力描述不够丰富，无法支持 reasoning、多模态等新特性
- 缺乏缓存 Token 计费支持
- 模型路由机制不够灵活

### 1.2 目标

参考 Opencode 的模型配置架构，优化现有系统：

1. **自动化**：从 models.dev 自动获取模型元数据，减少手动维护
2. **标准化**：统一模型能力描述，支持新模型特性
3. **简化**：消除重复代码，配置化添加新供应商
4. **精确化**：支持缓存 Token 计费

### 1.3 非目标

- 不改变现有的认证和鉴权机制
- 不改变现有的用户配额和限流逻辑
- 不改变现有的请求日志结构

---

## 2. 功能需求

### 2.0 数据架构：models.dev 作为单一真相来源

#### 2.0.1 设计原则

1. **models.dev 是基础数据源**：所有供应商和模型的元数据（定价、能力、限制）优先从 models.dev 获取
2. **本地配置优先**：数据库中的本地配置优先级高于 models.dev，可以覆盖任意字段
3. **支持完全自定义**：支持添加 models.dev 中没有的供应商和模型（显示为 "Other"）
4. **增量更新不覆盖**：models.dev 更新时不覆盖本地手动修改的配置

#### 2.0.2 配置来源与优先级

| 来源 | 优先级 | 说明 | 示例 |
|------|--------|------|------|
| `local_override` | 最高 | 数据库中的本地覆盖配置 | 修改某模型的定价 |
| `local_config` | 高 | 数据库中的自定义配置 | 自定义供应商 |
| `models_dev` | 基础 | models.dev 元数据 | 自动获取的模型列表 |

```
配置合并示意：

models.dev 数据          本地覆盖           最终生效
─────────────────────────────────────────────────────────
cost.input: 3.5    +    cost.input: 3.0  =  cost.input: 3.0
cost.output: 15.0  +    (无覆盖)         =  cost.output: 15.0
name: "Claude 4"   +    (无覆盖)         =  name: "Claude 4"
```

#### 2.0.3 配置合并策略

```python
def merge_model_config(base: dict, override: dict) -> dict:
    """
    深度合并模型配置

    规则：
    - override 中的字段覆盖 base 中的同名字段
    - 嵌套对象递归合并
    - 列表类型：override 替换 base（不合并）
    - None 值表示删除字段

    Args:
        base: models.dev 的基础配置
        override: 本地覆盖配置

    Returns:
        合并后的有效配置
    """
    result = deepcopy(base)
    for key, value in override.items():
        if value is None:
            # None 表示删除该字段
            result.pop(key, None)
        elif (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            # 递归合并嵌套对象
            result[key] = merge_model_config(result[key], value)
        else:
            # 直接覆盖
            result[key] = value
    return result
```

#### 2.0.4 数据流

```
启动时：
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  models.dev  │ ──▶ │  深度合并    │ ──▶ │  运行时配置  │
│  (基础数据)  │     │              │     │  (最终生效)  │
└──────────────┘     └──────────────┘     └──────────────┘
       ▲                    ▲
       │                    │
   定时同步            ┌──────────────┐
   (每天一次)          │  数据库配置  │
       │               │  (覆盖层)    │
       │               └──────────────┘
  手动触发 API
```

#### 2.0.5 同步策略

- **自动同步**：每天一次（可通过环境变量配置）
- **手动同步**：通过管理 API 触发
- **冲突处理**：本地修改的字段不会被覆盖，未修改的字段更新为最新值

#### 2.0.6 模型配置字段分组

| 字段组 | 主要来源 | 可被本地覆盖 | 说明 |
|--------|----------|--------------|------|
| **元数据** | models.dev | 是 | name, family, release_date |
| **能力** | models.dev | 是 | capabilities.* |
| **限制** | models.dev | 是 | limit.context, limit.output |
| **定价** | models.dev | 是 | cost.input, cost.output, cost.cache.* |
| **状态** | 本地 | - | is_active, custom_status |
| **覆盖标记** | 本地 | - | local_overrides (记录哪些字段被修改) |

#### 2.0.7 数据库表设计调整

**providers 表增加字段**：

```sql
ALTER TABLE providers ADD COLUMN source VARCHAR(20) DEFAULT 'models_dev';
-- 可能的值: 'models_dev' (从 models.dev 同步), 'custom' (用户自定义)

ALTER TABLE providers ADD COLUMN models_dev_id VARCHAR(100);
-- 对应 models.dev 中的供应商 ID，用于数据关联和同步
-- 自定义供应商此字段为 NULL

ALTER TABLE providers ADD COLUMN local_overrides JSONB DEFAULT '{}';
-- 记录本地覆盖的字段，同步时跳过这些字段

ALTER TABLE providers ADD COLUMN last_synced_at TIMESTAMP;
-- 上次从 models.dev 同步的时间
```

**model_catalog 表增加字段**：

```sql
ALTER TABLE model_catalog ADD COLUMN source VARCHAR(20) DEFAULT 'models_dev';
-- 可能的值: 'models_dev', 'custom'

ALTER TABLE model_catalog ADD COLUMN models_dev_id VARCHAR(100);
-- 对应 models.dev 中的模型 ID

ALTER TABLE model_catalog ADD COLUMN base_config JSONB;
-- 存储 models.dev 的原始配置（用于对比和增量更新）

ALTER TABLE model_catalog ADD COLUMN local_overrides JSONB DEFAULT '{}';
-- 存储本地覆盖的字段，同步时保留

ALTER TABLE model_catalog ADD COLUMN last_synced_at TIMESTAMP;
```

#### 2.0.8 API 设计

**同步 API**：

```python
# POST /api/admin/models/sync
# 从 models.dev 同步模型数据（手动触发）
# Request
{
    "provider_id": "anthropic",  # 可选，不传则同步全部
    "force": false               # 是否强制刷新缓存
}

# Response
{
    "success": true,
    "synced_at": "2026-03-03T10:30:00Z",
    "stats": {
        "providers_synced": 5,
        "models_synced": 120,
        "new_models": 3,
        "updated_models": 12,
        "preserved_local": 5  # 因本地修改而保留的字段数
    },
    "conflicts": [
        {
            "model_id": "claude-sonnet-4",
            "field": "cost.input",
            "local_value": 3.0,
            "remote_value": 3.5,
            "resolution": "preserved_local"
        }
    ]
}
```

**获取模型信息 API**（显示来源）：

```python
# GET /api/admin/models/{model_id}
{
    "id": "claude-sonnet-4",
    "source": "models_dev",  # 数据来源: models_dev | custom
    "name": "Claude Sonnet 4",

    # 合并后的有效配置
    "config": {
        "capabilities": {...},
        "cost": {
            "input": 3.0,     # 被本地覆盖
            "output": 15.0    # 来自 models.dev
        },
        "limit": {...}
    },

    # 本地覆盖的字段
    "local_overrides": {
        "cost.input": 3.0
    },

    # models.dev 原始值（用于对比）
    "base_values": {
        "cost.input": 3.5
    }
}
```

**重置本地覆盖 API**：

```python
# DELETE /api/admin/models/{model_id}/overrides
# 删除本地覆盖，恢复为 models.dev 的值
{
    "success": true,
    "reset_fields": ["cost.input"],
    "new_value": 3.5  # 恢复后的值
}
```

---

### 2.1 P0 - 统一适配器体系（支持 OpenAI 和 Anthropic 格式）

**问题**：

1. ZhipuAdapter、OpenAIAdapter、MiniMaxAdapter 等代码几乎完全相同，新增供应商需要重复编写
2. Anthropic 格式和 OpenAI 格式使用两套独立的路由系统，代码重复
3. 路由规则分散在 `proxy.py` 和 `anthropic_proxy.py` 两处

**现状分析**：

```
当前架构：
┌─────────────────────────────────────────────────────────────┐
│  OpenAI 格式 (/v1/chat/completions)                         │
│  ├── proxy.py: MODEL_PREFIX_TO_PROVIDER 硬编码路由          │
│  ├── OpenAIAdapter (透传)                                   │
│  ├── AnthropicAdapter (格式转换)                            │
│  ├── ZhipuAdapter (透传) ← 重复                             │
│  └── MiniMaxAdapter (透传) ← 重复                           │
├─────────────────────────────────────────────────────────────┤
│  Anthropic 格式 (/v1/messages)                              │
│  ├── anthropic_proxy.py: ANTHROPIC_MODEL_ROUTE_RULES 硬编码 │
│  └── 透传模式，不做格式转换                                  │
└─────────────────────────────────────────────────────────────┘
```

**方案**：

1. 创建通用的 `OpenAICompatibleAdapter`，支持所有 OpenAI 兼容 API
2. 保留 `AnthropicAdapter`，用于 OpenAI 端点到 Anthropic 的格式转换
3. 新增 `AnthropicPassthroughAdapter`，用于 Anthropic 端点的透传
4. 统一路由机制，支持两种 API 格式

**目标架构**：

```
优化后架构：
┌─────────────────────────────────────────────────────────────┐
│                    UnifiedRouterService                     │
│  ├── parse_model(model) → (provider_name, model_id)        │
│  ├── get_adapter(provider, api_format) → Adapter           │
│  └── 支持 provider/model 格式                               │
├─────────────────────────────────────────────────────────────┤
│  OpenAI 格式 (/v1/chat/completions)                         │
│  ├── OpenAICompatibleAdapter (通用透传)                     │
│  │   ├── zhipu, deepseek, minimax, openrouter, qwen...    │
│  └── AnthropicAdapter (格式转换: OpenAI → Anthropic)       │
├─────────────────────────────────────────────────────────────┤
│  Anthropic 格式 (/v1/messages)                              │
│  ├── AnthropicPassthroughAdapter (Anthropic 原生透传)       │
│  └── AnthropicCompatibleAdapter (其他 Anthropic 兼容厂商)   │
│       ├── zhipu (智谱 GLM 支持 Anthropic 格式)              │
│       └── minimax (MiniMax 支持 Anthropic 格式)             │
└─────────────────────────────────────────────────────────────┘
```

**适配器设计**：

```python
# 1. 通用 OpenAI 兼容适配器
class OpenAICompatibleAdapter(BaseAdapter):
    """所有 OpenAI 兼容 API 的通用适配器"""

    def __init__(self, base_url: str, api_key: str,
                 default_headers: dict = None,
                 endpoint: str = "/chat/completions"):
        super().__init__(base_url, api_key)
        self.default_headers = default_headers or {}
        self.endpoint = endpoint

    def convert_request(self, openai_request): return openai_request
    def convert_response(self, provider_response, model): return provider_response
    # ... 统一的 HTTP 转发逻辑

# 2. Anthropic 格式转换适配器（保留，用于 OpenAI 端点访问 Anthropic）
class AnthropicAdapter(BaseAdapter):
    """OpenAI 格式 → Anthropic 格式转换"""
    # 保持现有实现

# 3. Anthropic 透传适配器（新增）
class AnthropicPassthroughAdapter(BaseAdapter):
    """Anthropic 格式原生透传"""

    def get_endpoint(self) -> str:
        return f"{self.base_url}/messages"

    def convert_request(self, anthropic_request): return anthropic_request
    def convert_response(self, provider_response, model): return provider_response
```

**供应商配置示例**：

```json
{
  "providers": {
    "openai": {
      "name": "OpenAI",
      "base_url": "https://api.openai.com/v1",
      "api_format": "openai",
      "supported_endpoints": ["openai"]
    },
    "anthropic": {
      "name": "Anthropic",
      "base_url": "https://api.anthropic.com/v1",
      "api_format": "anthropic",
      "supported_endpoints": ["openai", "anthropic"],
      "headers": {
        "anthropic-version": "2023-06-01"
      }
    },
    "zhipu": {
      "name": "智谱 AI",
      "base_url": "https://open.bigmodel.cn/api/paas/v4",
      "api_format": "openai_compatible",
      "supported_endpoints": ["openai", "anthropic"]
    },
    "deepseek": {
      "name": "DeepSeek",
      "base_url": "https://api.deepseek.com",
      "api_format": "openai_compatible",
      "supported_endpoints": ["openai"]
    },
    "minimax": {
      "name": "MiniMax",
      "base_url": "https://api.minimax.chat/v1",
      "api_format": "openai_compatible",
      "supported_endpoints": ["openai", "anthropic"],
      "headers": {"X-Source": "llm-gateway"}
    }
  }
}
```

**路由逻辑**：

```python
class UnifiedRouterService:
    """统一路由服务"""

    async def route_openai_request(self, model: str, request: dict, db: AsyncSession):
        """
        处理 OpenAI 格式请求 (/v1/chat/completions)

        - OpenAI 兼容供应商 → OpenAICompatibleAdapter (透传)
        - Anthropic → AnthropicAdapter (格式转换)
        """
        provider_name, model_id = self.parse_model(model)
        provider = await self.get_provider(provider_name, db)

        if provider.api_format == "anthropic":
            adapter = AnthropicAdapter(provider.base_url, api_key)
        else:
            adapter = OpenAICompatibleAdapter(provider.base_url, api_key, provider.headers)

        return await adapter.forward_request(request)

    async def route_anthropic_request(self, model: str, request: dict, db: AsyncSession):
        """
        处理 Anthropic 格式请求 (/v1/messages)

        - 所有支持的供应商 → AnthropicPassthroughAdapter (透传)
        """
        provider_name, model_id = self.parse_model(model)
        provider = await self.get_provider(provider_name, db)

        if "anthropic" not in provider.supported_endpoints:
            raise ValueError(f"Provider '{provider_name}' does not support Anthropic format")

        adapter = AnthropicPassthroughAdapter(provider.base_url, api_key, provider.headers)
        return await adapter.forward_request(request)
```

**验收标准**：

- [ ] 删除 ZhipuAdapter、MiniMaxAdapter、QwenAdapter 等重复适配器
- [ ] OpenAI 格式端点 (`/v1/chat/completions`) 功能正常
- [ ] Anthropic 格式端点 (`/v1/messages`) 功能正常
- [ ] 新增 OpenAI 兼容供应商只需修改配置，无需写代码
- [ ] 模型前缀路由和 `provider/model` 格式路由都正常工作
- [ ] 现有功能不受影响，测试全部通过

---

### 2.2 P0 - 改进模型路由机制（统一 OpenAI 和 Anthropic 格式）

**问题**：

1. 当前只能通过模型前缀匹配供应商，不够灵活
2. OpenAI 格式和 Anthropic 格式使用两套独立的路由规则（`MODEL_PREFIX_TO_PROVIDER` vs `ANTHROPIC_MODEL_ROUTE_RULES`）
3. 路由规则分散，维护困难

**现状分析**：

```python
# proxy.py - OpenAI 格式路由
MODEL_PREFIX_TO_PROVIDER = {
    "gpt-": "openai",
    "claude-": "anthropic",
    "glm-": "zhipu",
    # ...
}

# anthropic_proxy.py - Anthropic 格式路由
ANTHROPIC_MODEL_ROUTE_RULES = [
    ("claude-", "anthropic"),
    ("glm-", "zhipu"),      # 重复定义
    ("minimax-", "minimax"),
    # ...
]
```

**方案**：

1. **统一模型解析**：支持 `provider/model` 显式格式和前缀匹配
2. **统一路由规则**：合并两套路由规则，按 API 格式自动适配
3. **端点级路由**：根据请求端点自动选择适配器

**模型格式支持**：

| 格式 | 示例 | 说明 |
|------|------|------|
| 隐式格式 | `gpt-4o` | 通过前缀匹配供应商（保持兼容） |
| 显式格式 | `openai/gpt-4o` | 直接指定供应商 |
| OpenRouter 格式 | `anthropic/claude-sonnet-4` | 透传到 OpenRouter |

**统一路由服务**：

```python
class ModelRouter:
    """统一模型路由"""

    # 统一的路由规则（替代 MODEL_PREFIX_TO_PROVIDER 和 ANTHROPIC_MODEL_ROUTE_RULES）
    ROUTE_RULES = {
        "openai": {
            "prefixes": ["gpt-", "o1-", "o3-", "o4-"],
            "api_format": "openai",
            "endpoints": ["openai"]
        },
        "anthropic": {
            "prefixes": ["claude-"],
            "api_format": "anthropic",
            "endpoints": ["openai", "anthropic"]
        },
        "zhipu": {
            "prefixes": ["glm-"],
            "api_format": "openai_compatible",
            "endpoints": ["openai", "anthropic"]
        },
        "deepseek": {
            "prefixes": ["deepseek-"],
            "api_format": "openai_compatible",
            "endpoints": ["openai"]
        },
        "minimax": {
            "prefixes": ["minimax-", "MiniMax-"],
            "api_format": "openai_compatible",
            "endpoints": ["openai", "anthropic"]
        },
        "openrouter": {
            "prefixes": ["openai/", "anthropic/", "google/", "meta-llama/", "deepseek/"],
            "api_format": "openai_compatible",
            "endpoints": ["openai"]
        },
        # 新增供应商只需在此配置，无需写代码
    }

    def parse_model_string(self, model: str) -> Tuple[str, str]:
        """
        解析模型字符串

        Examples:
            "gpt-4o" -> ("openai", "gpt-4o")
            "openai/gpt-4o" -> ("openai", "gpt-4o")
            "anthropic/claude-sonnet-4" -> ("anthropic", "claude-sonnet-4")
            "claude-sonnet-4" -> ("anthropic", "claude-sonnet-4")

        Returns:
            (provider_name, model_id)
        """
        # 显式格式: provider/model
        if "/" in model:
            provider_name, model_id = model.split("/", 1)
            return provider_name, model_id

        # 隐式格式: 通过前缀匹配
        for provider_name, config in self.ROUTE_RULES.items():
            for prefix in config["prefixes"]:
                if model.startswith(prefix):
                    return provider_name, model

        raise ValueError(f"Unknown model: {model}")

    def supports_endpoint(self, provider_name: str, endpoint: str) -> bool:
        """
        检查供应商是否支持指定的 API 端点格式

        Args:
            provider_name: 供应商名称
            endpoint: "openai" 或 "anthropic"

        Returns:
            是否支持
        """
        config = self.ROUTE_RULES.get(provider_name)
        if not config:
            return False
        return endpoint in config["endpoints"]
```

**API 端点处理**：

```python
# OpenAI 格式端点 (/v1/chat/completions)
async def handle_openai_request(model: str, request: dict, db: AsyncSession):
    router = ModelRouter()
    provider_name, model_id = router.parse_model_string(model)

    if not router.supports_endpoint(provider_name, "openai"):
        raise ValueError(f"Provider '{provider_name}' does not support OpenAI format")

    # ... 转发请求

# Anthropic 格式端点 (/v1/messages)
async def handle_anthropic_request(model: str, request: dict, db: AsyncSession):
    router = ModelRouter()
    provider_name, model_id = router.parse_model_string(model)

    if not router.supports_endpoint(provider_name, "anthropic"):
        raise ValueError(f"Provider '{provider_name}' does not support Anthropic format")

    # ... 转发请求
```

**请求示例**：

```bash
# OpenAI 格式端点
curl -X POST /v1/chat/completions \
  -H "Authorization: Bearer ltm-sk-xxx" \
  -d '{"model": "gpt-4o", "messages": [...]}'

curl -X POST /v1/chat/completions \
  -H "Authorization: Bearer ltm-sk-xxx" \
  -d '{"model": "openai/gpt-4o", "messages": [...]}'

curl -X POST /v1/chat/completions \
  -H "Authorization: Bearer ltm-sk-xxx" \
  -d '{"model": "claude-sonnet-4", "messages": [...]}'

# Anthropic 格式端点
curl -X POST /v1/messages \
  -H "x-api-key: ltm-sk-xxx" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model": "claude-sonnet-4", "messages": [...]}'

curl -X POST /v1/messages \
  -H "x-api-key: ltm-sk-xxx" \
  -d '{"model": "zhipu/glm-5", "messages": [...]}'
```

**验收标准**：

- [ ] 支持 `provider/model` 显式格式
- [ ] 保持原有前缀匹配兼容性
- [ ] 当显式指定的供应商不存在时返回明确错误
- [ ] OpenAI 格式端点 (`/v1/chat/completions`) 正常工作
- [ ] Anthropic 格式端点 (`/v1/messages`) 正常工作
- [ ] 不支持某格式的供应商返回明确错误（如 DeepSeek 不支持 Anthropic 格式）
- [ ] 路由规则统一管理，删除重复定义

---

### 2.3 P1 - 供应商预设与简化配置流程

**问题**：

1. 管理员需要手动填写供应商名称、Base URL、API 格式等多个字段
2. 无法自动从供应商 API 验证 Key 有效性并发现能力
3. 定价信息需要手动维护，无法从外部数据源自动获取

**目标**：管理员只需 **选择供应商 + 输入 API Key**，系统自动完成其余配置。

#### 2.3.1 供应商预设数据

供应商预设分为两类：
1. **标准供应商**：在 models.dev 中存在，基础数据从 models.dev 获取
2. **自定义供应商**：不在 models.dev 中，用户完全自定义

```python
# services/provider_presets.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class ProviderPreset:
    """供应商预设配置"""

    # 基本信息
    id: str                          # 预设 ID
    display_name: str                # 显示名称
    category: Literal["standard", "other"]  # 分类

    # models.dev 关联（标准供应商）
    models_dev_id: str | None = None # 对应 models.dev 的供应商 ID

    # API 配置（可被用户覆盖）
    default_base_url: str = ""       # 默认 API 地址
    api_format: str = "openai_compatible"
    supported_endpoints: list[str] = None  # ["openai"], ["openai", "anthropic"]

    # 默认请求头
    default_headers: dict = None

    # 自定义加载器（处理特殊逻辑）
    loader: str | None = None        # 引用预定义的加载器 ID

    # 特性标记
    supports_cache_tokens: bool = False

PROVIDER_PRESETS = {
    # ============ 标准供应商（models.dev 中存在）============
    "openai": ProviderPreset(
        id="openai",
        display_name="OpenAI",
        category="standard",
        models_dev_id="openai",
        default_base_url="https://api.openai.com/v1",
        api_format="openai",
        supported_endpoints=["openai"],
        supports_cache_tokens=True,
    ),
    "anthropic": ProviderPreset(
        id="anthropic",
        display_name="Anthropic",
        category="standard",
        models_dev_id="anthropic",
        default_base_url="https://api.anthropic.com/v1",
        api_format="anthropic",
        supported_endpoints=["openai", "anthropic"],
        default_headers={"anthropic-version": "2023-06-01"},
        loader="anthropic",  # 使用 Anthropic 加载器添加 beta headers
        supports_cache_tokens=True,
    ),
    "zhipu": ProviderPreset(
        id="zhipu",
        display_name="智谱 AI",
        category="standard",
        models_dev_id="zhipuai",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        api_format="openai_compatible",
        supported_endpoints=["openai", "anthropic"],
    ),
    "deepseek": ProviderPreset(
        id="deepseek",
        display_name="DeepSeek",
        category="standard",
        models_dev_id="deepseek",
        default_base_url="https://api.deepseek.com",
        api_format="openai_compatible",
        supported_endpoints=["openai"],
        supports_cache_tokens=True,
    ),
    "minimax": ProviderPreset(
        id="minimax",
        display_name="MiniMax",
        category="standard",
        models_dev_id="minimax",
        default_base_url="https://api.minimax.chat/v1",
        api_format="openai_compatible",
        supported_endpoints=["openai", "anthropic"],
    ),
    "moonshot": ProviderPreset(
        id="moonshot",
        display_name="Moonshot (月之暗面)",
        category="standard",
        models_dev_id="moonshotai-cn",
        default_base_url="https://api.moonshot.cn/v1",
        api_format="openai_compatible",
        supported_endpoints=["openai"],
    ),
    "openrouter": ProviderPreset(
        id="openrouter",
        display_name="OpenRouter",
        category="standard",
        models_dev_id="openrouter",
        default_base_url="https://openrouter.ai/api/v1",
        api_format="openai_compatible",
        supported_endpoints=["openai"],
        default_headers={
            "HTTP-Referer": "https://ltm.example.com",
            "X-Title": "LTM Gateway"
        },
        loader="openrouter",  # 使用 OpenRouter 加载器
    ),
    "qwen": ProviderPreset(
        id="qwen",
        display_name="通义千问 (阿里云)",
        category="standard",
        models_dev_id="alibaba",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_format="openai_compatible",
        supported_endpoints=["openai"],
    ),
    "google": ProviderPreset(
        id="google",
        display_name="Google AI Studio",
        category="standard",
        models_dev_id="google",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        api_format="openai_compatible",
        supported_endpoints=["openai"],
    ),
    "mistral": ProviderPreset(
        id="mistral",
        display_name="Mistral AI",
        category="standard",
        models_dev_id="mistral",
        default_base_url="https://api.mistral.ai/v1",
        api_format="openai_compatible",
        supported_endpoints=["openai"],
    ),

    # ============ 自定义供应商（不在 models.dev 中）============
    "other": ProviderPreset(
        id="other",
        display_name="Other (自定义)",
        category="other",
        models_dev_id=None,  # 标记为自定义
        default_base_url="",  # 用户必须填写
        api_format="openai_compatible",
        supported_endpoints=["openai"],
    ),
}

def get_preset_by_models_dev_id(models_dev_id: str) -> ProviderPreset | None:
    """根据 models.dev ID 查找预设"""
    for preset in PROVIDER_PRESETS.values():
        if preset.models_dev_id == models_dev_id:
            return preset
    return None
```
```

#### 2.3.2 前端配置流程改进

```
┌─────────────────────────────────────────────────────────────┐
│  步骤 1: 选择供应商类型                                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 供应商类型: [ 智谱 AI                    ▼ ]             ││
│  │                                                         ││
│  │ 标准供应商:                                             ││
│  │ ├── OpenAI        (仅 OpenAI 格式, 支持缓存 Token)     ││
│  │ ├── Anthropic     (OpenAI + Anthropic 格式, 支持缓存)  ││
│  │ ├── 智谱 AI       (OpenAI + Anthropic 格式)            ││
│  │ ├── DeepSeek      (仅 OpenAI 格式, 支持缓存 Token)     ││
│  │ ├── MiniMax       (OpenAI + Anthropic 格式)            ││
│  │ ├── Moonshot      (仅 OpenAI 格式)                     ││
│  │ ├── OpenRouter    (仅 OpenAI 格式, 聚合平台)           ││
│  │ ├── 通义千问      (仅 OpenAI 格式)                     ││
│  │ ├── Google AI     (仅 OpenAI 格式)                     ││
│  │ └── Mistral       (仅 OpenAI 格式)                     ││
│  │                                                         ││
│  │ ─────────────────────────────────────────────────────── ││
│  │ Other (自定义)  ← 完全自定义供应商配置                  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  步骤 2a: 标准供应商 - 输入 API Key（base_url 自动填充）    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 供应商名称: 智谱 AI (自动，可修改)                      ││
│  │ Base URL: https://open.bigmodel.cn/api/paas/v4 (自动)  ││
│  │ API Key:  [ ••••••••••••••••••••••••                  ││
│  │                                          [ 验证并发现 ]  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  步骤 2b: Other (自定义) - 填写所有配置                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 供应商名称: [ 我的私有 API           ] (必填)          ││
│  │ Base URL:   [ https://my-api.example.com/v1 ] (必填)   ││
│  │ API Key:    [ •••••••••••••••••••••••• ] (必填)        ││
│  │ API 格式:   [ OpenAI Compatible      ▼ ]               ││
│  │ 支持端点:   [x] OpenAI 格式  [ ] Anthropic 格式         ││
│  │                                          [ 验证连接 ]   ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  步骤 3: 确认配置                                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 标准供应商:                                              ││
│  │ ✓ API Key 有效                                          ││
│  │ ✓ 发现 8 个可用模型（从 API 获取）                      ││
│  │ ✓ 定价信息: 从 models.dev 获取 (5 个已确认)            ││
│  │                                                         ││
│  │ 自定义供应商 (Other):                                   ││
│  │ ✓ 连接成功                                              ││
│  │ ✓ 发现 3 个可用模型                                     ││
│  │ ⚠ 定价信息: 需要手动配置（models.dev 中无此供应商）    ││
│  │                                                         ││
│  │ 发现的模型:                                             ││
│  │ ├── model-1        定价待配置                          ││
│  │ ├── model-2        定价待配置                          ││
│  │ └── model-3        定价待配置                          ││
│  │                                                         ││
│  │                                [ 取消 ]   [ 确认并创建 ] ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**自定义供应商 (Other) 说明**：

- 不关联 models.dev，所有配置由用户填写
- 模型列表从供应商 API 的 `/models` 端点获取
- 定价和能力信息需要管理员手动配置
- 在供应商列表中显示为用户自定义的名称

#### 2.3.3 新增 API 接口

```python
# GET /api/admin/providers/presets
# 返回可用供应商预设列表
{
    "presets": [
        {
            "id": "openai",
            "name": "OpenAI",
            "api_format": "openai",
            "supported_endpoints": ["openai"],
            "supports_anthropic": false
        },
        {
            "id": "anthropic",
            "name": "Anthropic",
            "api_format": "anthropic",
            "supported_endpoints": ["openai", "anthropic"],
            "supports_anthropic": true
        },
        {
            "id": "zhipu",
            "name": "智谱 AI",
            "api_format": "openai_compatible",
            "supported_endpoints": ["openai", "anthropic"],
            "supports_anthropic": true
        },
        // ... 更多供应商
    ]
}

# POST /api/admin/providers/validate-key
# 验证 API Key 并自动发现配置
# Request
{
    "provider_preset": "zhipu",     # 供应商预设 ID
    "api_key": "sk-xxx...",
    "custom_base_url": null         # 可选，覆盖预设的 base_url
}

# Response (成功)
{
    "valid": true,
    "provider_preset": "zhipu",
    "auto_config": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_format": "openai_compatible",
        "supported_endpoints": ["openai", "anthropic"]
    },
    "discovered_models": [
        {
            "id": "glm-5",
            "display_name": "GLM-5",
            "pricing": {
                "input_price": 1.0,
                "output_price": 3.2,
                "cache_read_price": 0.2,
                "source": "models_dev"  # 或 "builtin" 或 "unknown"
            },
            "capabilities": {
                "supports_vision": false,
                "supports_tools": true,
                "supports_reasoning": true,
                "context_window": 204800
            }
        },
        // ... 更多模型
    ],
    "summary": {
        "total_models": 8,
        "pricing_confirmed": 5,
        "pricing_pending": 3
    }
}

# Response (失败)
{
    "valid": false,
    "error": {
        "type": "invalid_api_key",
        "message": "API Key 无效或已过期"
    }
}
```

#### 2.3.4 简化的创建供应商 API

```python
# POST /api/admin/providers/quick-create
# 一键创建供应商（预设 + API Key）
# Request
{
    "provider_preset": "zhipu",
    "api_key": "sk-xxx...",
    "key_plan": "standard",         # 可选: standard | coding_plan
    "rpm_limit": 60,                # 可选
    "custom_base_url": null,        # 可选，覆盖预设
    "auto_activate_models": true    # 是否自动激活发现的模型
}

# Response
{
    "provider": {
        "id": "uuid-xxx",
        "name": "zhipu",
        "display_name": "智谱 AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_format": "openai_compatible",
        "supported_endpoints": ["openai", "anthropic"]
    },
    "api_key": {
        "id": "uuid-yyy",
        "key_suffix": "...xxxx",
        "status": "active"
    },
    "discovery_result": {
        "total_models": 8,
        "activated_models": 8,
        "pricing_confirmed": 5
    }
}
```

#### 2.3.5 models.dev 数据同步服务

```python
# services/models_dev_service.py

from dataclasses import dataclass
from datetime import datetime, timedelta
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class SyncResult:
    """同步结果"""
    success: bool
    synced_at: datetime
    providers_synced: int
    models_synced: int
    new_models: int
    updated_models: int
    preserved_local: int  # 因本地修改而保留的字段数
    conflicts: list[dict]
    error: str | None = None


class ModelsDevService:
    """
    models.dev 数据同步服务

    作为模型元数据的单一真相来源（SSOT），
    定期同步到本地数据库，支持本地覆盖。
    """

    MODELS_DEV_URL = "https://models.dev/api.json"
    SYNC_INTERVAL = timedelta(hours=24)  # 每天同步一次

    _cache: dict | None = None
    _cache_expires: datetime | None = None

    async def fetch_all_data(self, force_refresh: bool = False) -> dict:
        """
        从 models.dev 获取所有供应商和模型数据

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            {
                "openai": {
                    "id": "openai",
                    "name": "OpenAI",
                    "api": "https://api.openai.com/v1",
                    "models": {
                        "gpt-4o": { ... },
                        ...
                    }
                },
                ...
            }
        """
        now = datetime.utcnow()

        if not force_refresh and self._cache and self._cache_expires > now:
            return self._cache

        async with httpx.AsyncClient() as client:
            response = await client.get(self.MODELS_DEV_URL, timeout=30)
            response.raise_for_status()
            self._cache = response.json()
            self._cache_expires = now + self.SYNC_INTERVAL

        return self._cache

    async def get_provider(self, provider_id: str) -> dict | None:
        """获取单个供应商信息"""
        data = await self.fetch_all_data()
        return data.get(provider_id)

    async def get_model(self, provider_id: str, model_id: str) -> dict | None:
        """获取单个模型信息"""
        provider = await self.get_provider(provider_id)
        if provider:
            return provider.get("models", {}).get(model_id)
        return None

    async def sync_to_database(
        self,
        db: AsyncSession,
        provider_id: str | None = None,
        force_refresh: bool = False
    ) -> SyncResult:
        """
        同步 models.dev 数据到数据库

        Args:
            db: 数据库会话
            provider_id: 指定供应商 ID，None 表示同步全部
            force_refresh: 是否强制刷新缓存

        Returns:
            SyncResult: 同步结果统计
        """
        result = SyncResult(
            success=False,
            synced_at=datetime.utcnow(),
            providers_synced=0,
            models_synced=0,
            new_models=0,
            updated_models=0,
            preserved_local=0,
            conflicts=[]
        )

        try:
            data = await self.fetch_all_data(force_refresh)

            # 确定要同步的供应商
            providers_to_sync = [provider_id] if provider_id else list(data.keys())

            for pid in providers_to_sync:
                if pid not in data:
                    continue

                provider_data = data[pid]
                preset = get_preset_by_models_dev_id(pid)

                # 同步供应商
                await self._sync_provider(db, pid, provider_data, preset)
                result.providers_synced += 1

                # 同步模型
                for model_id, model_data in provider_data.get("models", {}).items():
                    sync_result = await self._sync_model(
                        db, pid, model_id, model_data
                    )
                    result.models_synced += 1
                    if sync_result == "new":
                        result.new_models += 1
                    elif sync_result == "updated":
                        result.updated_models += 1

            await db.commit()
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result

    async def _sync_provider(
        self,
        db: AsyncSession,
        models_dev_id: str,
        provider_data: dict,
        preset: ProviderPreset | None
    ):
        """
        同步单个供应商

        如果数据库中已有该供应商，更新 base_config 和 last_synced_at
        但保留 local_overrides 中的字段
        """
        # 实现细节...
        pass

    async def _sync_model(
        self,
        db: AsyncSession,
        provider_models_dev_id: str,
        model_id: str,
        model_data: dict
    ) -> str:
        """
        同步单个模型

        Returns:
            "new" | "updated" | "preserved"
        """
        # 实现细节...
        pass

    @staticmethod
    def merge_configs(base: dict, override: dict) -> dict:
        """
        深度合并配置

        Args:
            base: models.dev 的基础配置
            override: 本地覆盖配置

        Returns:
            合并后的有效配置
        """
        result = deepcopy(base)
        for key, value in override.items():
            if value is None:
                result.pop(key, None)
            elif (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ModelsDevService.merge_configs(result[key], value)
            else:
                result[key] = value
        return result
```

**同步调度**：

```python
# services/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

async def scheduled_sync():
    """每天凌晨 3 点同步 models.dev 数据"""
    async with get_db_session() as db:
        service = ModelsDevService()
        result = await service.sync_to_database(db)
        logger.info(f"Models.dev sync completed: {result}")

# 启动时注册定时任务
scheduler.add_job(
    scheduled_sync,
    trigger="cron",
    hour=3,
    minute=0,
    id="models_dev_sync"
)
```

**验收标准**：

- [ ] 管理员可从预设列表选择供应商
- [ ] 选择预设后，base_url 和 api_format 自动填充
- [ ] 输入 API Key 后可验证有效性
- [ ] 验证成功后自动发现可用模型
- [ ] 从 models.dev 自动获取定价和能力信息
- [ ] 一键完成供应商和 Key 的创建
- [ ] 支持自定义供应商（手动填写所有配置）

---

### 2.4 P1 - 自定义加载器机制

**问题**：某些供应商需要特殊的初始化或请求处理逻辑，静态配置无法满足。

**方案**：使用**预定义加载器**，在代码中定义供应商的特殊处理逻辑。

#### 2.4.1 加载器设计

```python
# services/provider_loaders.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Awaitable

@dataclass
class LoaderResult:
    """加载器返回结果"""
    autoload: bool = True           # 是否自动加载模型
    options: dict = None            # 传递给 SDK/适配器的选项
    get_model: Callable | None = None  # 自定义模型获取函数
    headers: dict = None            # 额外的请求头

class ProviderLoader(ABC):
    """供应商加载器基类"""

    @abstractmethod
    async def load(
        self,
        provider: "Provider",
        api_key: str,
        db: AsyncSession
    ) -> LoaderResult:
        """
        加载供应商配置

        Args:
            provider: 供应商数据库记录
            api_key: 解密后的 API Key
            db: 数据库会话

        Returns:
            LoaderResult: 加载结果
        """
        pass

# 加载器注册表
LOADERS: dict[str, type[ProviderLoader]] = {}
```

#### 2.4.2 内置加载器

```python
# services/provider_loaders/builtin.py

class AnthropicLoader(ProviderLoader):
    """
    Anthropic 供应商加载器

    处理：
    - 添加 beta headers 支持 Claude Code 功能
    """

    async def load(self, provider, api_key, db) -> LoaderResult:
        return LoaderResult(
            autoload=False,
            options={},
            headers={
                "anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14"
            }
        )


class OpenRouterLoader(ProviderLoader):
    """
    OpenRouter 供应商加载器

    处理：
    - 添加必需的 Referer 和 Title headers
    """

    async def load(self, provider, api_key, db) -> LoaderResult:
        return LoaderResult(
            autoload=False,
            options={},
            headers={
                "HTTP-Referer": "https://ltm.example.com",
                "X-Title": "LTM Gateway"
            }
        )


class AmazonBedrockLoader(ProviderLoader):
    """
    Amazon Bedrock 供应商加载器

    处理：
    - AWS 凭证链
    - 跨区域推理配置文件前缀
    """

    async def load(self, provider, api_key, db) -> LoaderResult:
        # 从 provider 配置获取区域
        region = provider.config.get("region", "us-east-1")

        # 处理跨区域推理前缀
        def get_model(sdk, model_id: str, options: dict):
            cross_region_prefixes = ["global.", "us.", "eu.", "jp.", "apac."]
            if any(model_id.startswith(p) for p in cross_region_prefixes):
                return sdk.language_model(model_id)

            # 根据区域添加前缀
            region_prefix = region.split("-")[0]
            if region_prefix in ["us", "eu", "ap"]:
                # 某些模型需要跨区域前缀
                if any(m in model_id for m in ["claude", "nova", "deepseek"]):
                    model_id = f"{region_prefix}.{model_id}"

            return sdk.language_model(model_id)

        return LoaderResult(
            autoload=True,
            options={"region": region},
            get_model=get_model
        )


class GoogleVertexLoader(ProviderLoader):
    """
    Google Vertex AI 供应商加载器

    处理：
    - Google 认证
    - 项目和位置配置
    """

    async def load(self, provider, api_key, db) -> LoaderResult:
        project = provider.config.get("project")
        location = provider.config.get("location", "us-central1")

        # 使用 Google Auth 获取 token
        async def custom_fetch(url, init):
            from google.auth import default
            from google.auth.transport.requests import Request

            credentials, _ = default()
            credentials.refresh(Request())
            init["headers"]["Authorization"] = f"Bearer {credentials.token}"
            return await fetch(url, init)

        return LoaderResult(
            autoload=bool(project),
            options={
                "project": project,
                "location": location,
                "fetch": custom_fetch
            }
        )


# 注册加载器
LOADERS.update({
    "anthropic": AnthropicLoader,
    "openrouter": OpenRouterLoader,
    "amazon_bedrock": AmazonBedrockLoader,
    "google_vertex": GoogleVertexLoader,
})
```

#### 2.4.3 加载器使用

```python
# services/unified_router.py

async def get_adapter_for_provider(
    provider: Provider,
    api_key: str,
    db: AsyncSession
) -> BaseAdapter:
    """
    根据供应商配置获取适配器
    """
    # 获取预设
    preset = PROVIDER_PRESETS.get(provider.name)

    # 检查是否需要加载器
    loader_result = None
    if preset and preset.loader:
        loader_class = LOADERS.get(preset.loader)
        if loader_class:
            loader = loader_class()
            loader_result = await loader.load(provider, api_key, db)

    # 合并配置
    headers = {**(preset.default_headers or {}), **(loader_result.headers or {})}
    options = {**(loader_result.options or {})}

    # 创建适配器
    if provider.api_format == "anthropic":
        return AnthropicAdapter(
            base_url=provider.base_url,
            api_key=api_key,
            headers=headers,
            **options
        )
    else:
        return OpenAICompatibleAdapter(
            base_url=provider.base_url,
            api_key=api_key,
            headers=headers,
            **options
        )
```

#### 2.4.4 添加新加载器

如需支持新的特殊供应商：

1. 在 `services/provider_loaders/builtin.py` 中添加新的加载器类
2. 在 `LOADERS` 注册表中注册
3. 在 `PROVIDER_PRESETS` 中设置对应的 `loader` 字段

**验收标准**：

- [ ] Anthropic 加载器正确添加 beta headers
- [ ] OpenRouter 加载器正确添加必需 headers
- [ ] Amazon Bedrock 加载器正确处理跨区域前缀
- [ ] 无加载器的供应商正常工作
- [ ] 加载器错误不影响其他供应商

---

### 2.5 P1 - 缓存 Token 计费支持

**问题**：已有 `cache_read_price` 和 `cache_write_price` 字段，但计费逻辑未使用。

**方案**：

1. 从响应中提取缓存 Token 使用量（如果供应商返回）
2. 计费时包含缓存 Token

**支持供应商**：

| 供应商 | 缓存 Token 字段 |
|--------|----------------|
| Anthropic | `usage.cache_read_input_tokens` |
| OpenAI | `usage.prompt_tokens_details.cached_tokens` |
| DeepSeek | `usage.prompt_cache_hit_tokens` |

**计费逻辑**：

```python
async def calculate_request_cost(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    model_id: str,
    ...
) -> Decimal:
    cost = (
        input_tokens * input_price / 1_000_000
        + output_tokens * output_price / 1_000_000
        + cache_read_tokens * cache_read_price / 1_000_000
        + cache_write_tokens * cache_write_price / 1_000_000
    )
    return cost
```

**验收标准**：

- [ ] Anthropic 请求正确记录缓存 Token
- [ ] 计费正确包含缓存 Token 费用
- [ ] 账单明细显示缓存 Token 使用量

---

### 2.6 P1 - 供应商配置选项增强

**问题**：供应商配置不够灵活，无法设置超时、自定义请求头等。

**方案**：

扩展 `Provider` 模型，增加配置字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `request_timeout` | int | 请求超时（秒），默认 120 |
| `custom_headers` | JSON | 自定义请求头（合并到加载器提供的 headers） |
| `model_whitelist` | JSON | 模型白名单 |
| `model_blacklist` | JSON | 模型黑名单 |

**验收标准**：

- [ ] 可为每个供应商配置不同的超时时间
- [ ] 自定义请求头正确附加到 API 请求
- [ ] 白名单/黑名单正确过滤可用模型

---

### 2.7 P2 - 丰富模型能力字段

**问题**：当前只有 3 个能力字段，无法描述 reasoning、多模态等新特性。

**方案**：

扩展 `ModelCatalog` 模型，参考 models.dev 的能力结构：

```python
# 与 models.dev 对齐的能力结构
capabilities: {
    "temperature": bool,      # 是否支持 temperature 参数
    "reasoning": bool,        # 是否支持 chain-of-thought
    "attachment": bool,       # 是否支持附件
    "toolcall": bool,         # 是否支持工具调用
    "interleaved": bool | {   # 思维链交织
        "field": "reasoning_content" | "reasoning_details"
    },
    "input": {
        "text": bool,
        "audio": bool,
        "image": bool,
        "video": bool,
        "pdf": bool,
    },
    "output": {
        "text": bool,
        "audio": bool,
        "image": bool,
        "video": bool,
        "pdf": bool,
    }
}
```

| 新增字段 | 类型 | 说明 |
|----------|------|------|
| `capabilities` | JSONB | 完整的能力结构（如上） |
| `family` | str | 模型家族（如 "claude"、"gpt"） |
| `knowledge_cutoff` | str | 知识截止日期 |
| `release_date` | datetime | 发布日期 |

**验收标准**：

- [ ] 数据库迁移成功
- [ ] 从 models.dev 同步能力字段
- [ ] 管理后台可编辑能力字段
- [ ] `/v1/models` 接口返回能力信息

---

### 2.8 P2 - 模型变体支持

**问题**：不支持模型变体（如不同 reasoning 级别）。

**方案**：

参考 Opencode 的设计，使用代码定义变体生成规则，而非纯数据库配置：

```python
# services/model_variants.py

from dataclasses import dataclass

@dataclass
class ModelVariant:
    """模型变体配置"""
    id: str                    # 变体 ID
    display_name: str          # 显示名称
    config: dict               # 应用的配置
    disabled: bool = False     # 是否禁用

def generate_variants(model: Model) -> dict[str, ModelVariant]:
    """
    根据模型能力生成变体

    Returns:
        {
            "extended-thinking": ModelVariant(...),
            ...
        }
    """
    variants = {}

    # Reasoning 模型支持 extended-thinking 变体
    if model.capabilities.get("reasoning"):
        variants["extended-thinking"] = ModelVariant(
            id="extended-thinking",
            display_name="Extended Thinking",
            config={
                "thinking": {"type": "enabled", "budget_tokens": 10000}
            }
        )

    # 支持 interleaved 的模型
    if model.capabilities.get("interleaved"):
        variants["interleaved"] = ModelVariant(
            id="interleaved",
            display_name="Interleaved Thinking",
            config={
                "thinking": {"type": "interleaved"}
            }
        )

    return variants
```

**API 变更**：

```python
# 支持变体格式
"claude-sonnet-4:extended-thinking"  # model:variant
```

**验收标准**：

- [ ] 根据模型能力自动生成变体
- [ ] 请求时可指定变体
- [ ] 变体配置正确应用到请求

---

### 2.9 P2 - 模型状态生命周期

**问题**：模型状态过于简单，无法表示废弃、实验等状态。

**方案**：

从 models.dev 同步状态，支持本地覆盖：

| 状态 | 说明 | 行为 |
|------|------|------|
| `active` | 正常可用 | - |
| `deprecated` | 已废弃 | 仍可用，返回警告头 |
| `alpha` | 实验性 | 默认不显示，需显式启用 |
| `beta` | 测试中 | 默认显示，标注 beta |
| `inactive` | 已禁用 | 不可用 |

**API 响应**：

```json
{
  "id": "gpt-3.5-turbo",
  "status": "deprecated",
  "deprecation_message": "此模型已废弃，建议迁移到 gpt-4o-mini"
}
```

**验收标准**：

- [ ] 从 models.dev 同步状态字段
- [ ] 废弃模型请求返回 `X-Model-Deprecated` 警告头
- [ ] Alpha 模型默认不在列表中显示
- [ ] 管理后台可覆盖状态

---

### 2.10 P2 - 优化模型发现服务

**问题**：模型发现只支持部分供应商，且发现后需手动确认定价。

**方案**：

整合 models.dev 作为模型信息源：

```
流程：
1. 从供应商 API 获取模型列表
2. 从 models.dev 获取模型元数据（定价、能力）
3. 合并信息，本地配置优先
4. 新模型自动激活（如果有匹配的定价）
```

**验收标准**：

- [ ] 支持所有 OpenAI 兼容供应商的模型发现
- [ ] 发现的模型自动填充定价和能力（来自 models.dev）
- [ ] 本地修改不被同步覆盖

---

### 2.11 P3 - 配置热重载

**问题**：配置修改需要重启服务。

**方案**：

1. 提供管理 API 触发重载
2. 通过事件通知相关服务
3. models.dev 数据刷新

**API**：

```python
# 手动触发同步
POST /api/admin/models/sync
{
    "provider_id": "anthropic",  # 可选
    "force": false
}

# 重载本地配置
POST /api/admin/config/reload
{
    "reload_providers": true
}
```

**验收标准**：

- [ ] 修改配置后可通过 API 热重载
- [ ] 重载过程不中断现有请求
- [ ] 重载失败时回滚并记录错误

---

## 3. 技术方案

### 3.1 架构变更

```
┌─────────────────────────────────────────────────────────────┐
│                    数据流架构                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    每天    ┌──────────────────────────┐  │
│  │  models.dev  │ ─────────▶ │    ModelsDevService      │  │
│  │  (SSOT)      │    同步    │    (数据同步服务)         │  │
│  └──────────────┘            └────────────┬─────────────┘  │
│                                           │                 │
│                                           ▼                 │
│                              ┌──────────────────────────┐   │
│                              │     深度合并配置          │   │
│                              │  (保留本地覆盖)           │   │
│                              └────────────┬─────────────┘   │
│                                           │                 │
│                                           ▼                 │
│  ┌──────────────┐            ┌──────────────────────────┐  │
│  │  数据库配置  │ ─────────▶ │      运行时配置          │  │
│  │  (覆盖层)    │   合并     │      (最终生效)          │  │
│  └──────────────┘            └──────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      请求处理架构                            │
├─────────────────────────────────────────────────────────────┤
│  API Layer                                                  │
│  ├── /v1/chat/completions (OpenAI 格式)                     │
│  └── /v1/messages (Anthropic 格式)                          │
└───────────────────┬─────────────────────┬───────────────────┘
                    │                     │
                    ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  UnifiedRouterService                       │
│  ├── parse_model(model) → (provider_name, model_id)        │
│  ├── get_adapter(provider, endpoint) → Adapter             │
│  ├── supports_endpoint(provider, endpoint) → bool          │
│  └── 应用 ProviderLoader (自定义加载器)                      │
├─────────────────────────────────────────────────────────────┤
│                    Adapter Layer                            │
├─────────────────────────────────────────────────────────────┤
│  OpenAI 端点:                                               │
│  ├── OpenAICompatibleAdapter  (通用透传)                    │
│  └── AnthropicAdapter         (格式转换)                    │
│                                                             │
│  Anthropic 端点:                                            │
│  └── AnthropicPassthroughAdapter (原生透传)                 │
├─────────────────────────────────────────────────────────────┤
│                    Provider Loaders                         │
├─────────────────────────────────────────────────────────────┤
│  AnthropicLoader      # 添加 beta headers                   │
│  OpenRouterLoader     # 添加 Referer/Title headers          │
│  AmazonBedrockLoader  # 处理跨区域前缀                       │
│  GoogleVertexLoader   # 处理 Google 认证                     │
├─────────────────────────────────────────────────────────────┤
│                    Service Layer                            │
├─────────────────────────────────────────────────────────────┤
│  ModelsDevService          # models.dev 数据同步            │
│  ProviderPresets           # 供应商预设配置                  │
│  BillingService            # 缓存 Token 计费                │
├─────────────────────────────────────────────────────────────┤
│                    Data Layer                               │
├─────────────────────────────────────────────────────────────┤
│  providers                 # source, models_dev_id, local_overrides │
│  model_catalog             # base_config, local_overrides, capabilities │
└─────────────────────────────────────────────────────────────┘
```

**删除的文件/代码**：

- `services/providers/zhipu_adapter.py` - 合并到 OpenAICompatibleAdapter
- `services/providers/minimax_adapter.py` - 合并到 OpenAICompatibleAdapter
- `services/providers/qwen_adapter.py` - 合并到 OpenAICompatibleAdapter
- `services/proxy.py` 中的 `MODEL_PREFIX_TO_PROVIDER` - 迁移到统一路由
- `services/anthropic_proxy.py` 中的 `ANTHROPIC_MODEL_ROUTE_RULES` - 迁移到统一路由

**新增的文件**：

- `services/unified_router.py` - 统一路由服务
- `services/providers/openai_compatible.py` - 通用 OpenAI 兼容适配器
- `services/providers/anthropic_passthrough.py` - Anthropic 透传适配器
- `services/provider_presets.py` - 供应商预设配置
- `services/provider_loaders/` - 自定义加载器目录
  - `__init__.py` - 加载器基类和注册表
  - `builtin.py` - 内置加载器实现
- `services/models_dev_service.py` - models.dev 数据同步服务

### 3.2 数据库迁移

```bash
# 新增迁移
alembic revision -m "add_provider_ssot_fields"      # source, models_dev_id, local_overrides
alembic revision -m "add_model_ssot_fields"         # base_config, local_overrides, capabilities
alembic revision -m "add_provider_config_options"   # request_timeout, custom_headers, whitelist
```

### 3.3 环境配置

```bash
# models.dev 同步配置
MODELS_DEV_ENABLED=true
MODELS_DEV_SYNC_HOUR=3          # 每天凌晨 3 点同步
MODELS_DEV_CACHE_TTL=86400      # 缓存 24 小时
```

---

## 4. 实施计划

### 4.1 阶段一（P0 - 1.5 周）

| 任务 | 工作量 | 说明 |
|------|--------|------|
| 2.0 数据架构改造 | 2d | models.dev 作为 SSOT，配置合并逻辑 |
| 2.1 统一适配器体系 | 2d | OpenAI + Anthropic 格式统一适配器 |
| 2.2 改进模型路由机制 | 2d | 统一路由，支持两种 API 格式 |
| 测试和文档 | 1d | 回归测试 + API 文档更新 |

**详细任务分解**：

```
Day 1-2: 数据架构
├── 实现 ModelsDevService (数据获取和缓存)
├── 实现深度合并逻辑 (merge_configs)
├── 数据库迁移 (source, models_dev_id, local_overrides)
└── 定时同步任务 (每天凌晨 3 点)

Day 3-4: 统一适配器
├── 创建 OpenAICompatibleAdapter
├── 创建 AnthropicPassthroughAdapter
├── 修改 AnthropicAdapter (仅用于 OpenAI 端点转换)
└── 删除 ZhipuAdapter, MiniMaxAdapter, QwenAdapter

Day 5-6: 统一路由
├── 创建 UnifiedRouterService
├── 合并 MODEL_PREFIX_TO_PROVIDER 和 ANTHROPIC_MODEL_ROUTE_RULES
├── 支持 provider/model 显式格式
└── 在 Provider 模型添加 supported_endpoints 字段

Day 7: 修改 Router
├── 修改 routers/gateway.py (OpenAI 格式)
├── 修改 routers/anthropic_gateway.py (Anthropic 格式)
└── 统一使用 UnifiedRouterService

Day 8-9: 测试和文档
├── 单元测试：适配器转换、路由解析、配置合并
├── 集成测试：端到端请求
├── 回归测试：确保现有功能正常
└── 更新 API 文档
```

### 4.2 阶段二（P1 - 2.5 周）

| 任务 | 工作量 | 说明 |
|------|--------|------|
| 2.3 供应商预设与简化配置流程 | 4d | 含 "Other" 自定义供应商 |
| 2.4 自定义加载器机制 | 2d | Anthropic/OpenRouter/Bedrock 加载器 |
| 2.5 缓存 Token 计费 | 2d | - |
| 2.6 供应商配置增强 | 1d | 超时、headers、白名单 |
| 测试和文档 | 1d | - |

**详细任务分解（2.3 供应商预设）**：

```
Day 1: 供应商预设数据
├── 创建 services/provider_presets.py（预设配置）
├── 实现 "Other" 自定义供应商支持
└── 编写预设数据单元测试

Day 2: 后端 API
├── GET /api/admin/providers/presets（预设列表）
├── POST /api/admin/providers/validate-key（Key 验证）
├── POST /api/admin/providers/quick-create（一键创建）
└── POST /api/admin/models/sync（手动同步）

Day 3-4: 前端
├── 改造 AdminProviders.jsx
├── 添加供应商预设下拉选择（标准 + Other）
├── 自动填充 base_url 和 api_format
├── 添加"验证并发现"按钮
├── 展示验证结果和发现的模型
└── 模型定价预览界面（区分 models.dev 来源和手动配置）

Day 5: 集成测试
├── 端到端测试：预设选择 → Key 验证 → 模型发现
├── "Other" 自定义供应商流程测试
├── 本地覆盖不被同步覆盖测试
└── 错误场景测试（无效 Key、网络错误等）
```

**详细任务分解（2.4 自定义加载器）**：

```
Day 1: 加载器框架
├── 创建 ProviderLoader 基类
├── 实现加载器注册表
└── 集成到 UnifiedRouterService

Day 2: 内置加载器
├── AnthropicLoader (beta headers)
├── OpenRouterLoader (referer headers)
├── AmazonBedrockLoader (跨区域前缀)
└── GoogleVertexLoader (认证处理)
```
└── 更新文档
```

### 4.3 阶段三（P2 - 1.5 周）

| 任务 | 工作量 |
|------|--------|
| 2.7 丰富能力字段 | 2d |
| 2.8 模型变体支持 | 2d |
| 2.9 状态生命周期 | 1d |
| 2.10 优化模型发现 | 2d |
| 测试和文档 | 1d |

### 4.4 阶段四（P3 - 0.5 周）

| 任务 | 工作量 |
|------|--------|
| 2.11 配置热重载 | 1d |
| 性能优化 | 1d |
| 文档完善 | 1d |

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| models.dev 服务不可用 | 无法同步最新模型信息 | 本地 24 小时缓存 + 回退到上次成功数据 |
| 配置合并冲突 | 本地修改被意外覆盖 | local_overrides 字段记录修改，同步时跳过 |
| 适配器重构影响现有功能 | 服务中断 | 保持旧适配器兼容，灰度发布 |
| 数据库迁移失败 | 数据丢失 | 迁移前备份，支持回滚 |
| 缓存 Token 计费不准确 | 计费纠纷 | 保留原始响应日志，支持申诉 |
| 自定义加载器 Bug | 特定供应商不可用 | 隔离加载器错误，降级到默认配置 |

---

## 6. 验收标准

### 6.1 功能验收

**P0 验收**：
- [ ] models.dev 数据正常同步（每天一次）
- [ ] 本地配置优先级正确（不被同步覆盖）
- [ ] 统一适配器体系工作正常
- [ ] OpenAI 和 Anthropic 两种端点格式都正常

**P1 验收**：
- [ ] 供应商预设选择流程正常
- [ ] "Other" 自定义供应商配置正常
- [ ] 自定义加载器正确应用特殊配置
- [ ] 缓存 Token 计费正确

**回归验收**：
- [ ] 现有功能不受影响
- [ ] 所有现有测试通过

### 6.2 性能验收

- [ ] 模型列表 API 响应时间 < 100ms
- [ ] models.dev 缓存命中率 > 95%
- [ ] 请求转发延迟增加 < 5ms
- [ ] 配置合并耗时 < 10ms

### 6.3 文档验收

- [ ] API 文档更新（新增同步 API、预设 API）
- [ ] 部署文档更新（models.dev 同步配置）
- [ ] 运维手册更新（手动同步、冲突处理）

---

## 7. 附录

### 7.1 models.dev API 参考

- Base URL: `https://models.dev`
- Models API: `GET /api.json`
- 更新频率: 实时

### 7.2 支持的供应商列表

#### 标准供应商（数据来自 models.dev）

| 供应商 | 预设 ID | models.dev ID | 加载器 | OpenAI | Anthropic | 缓存 |
|--------|---------|---------------|--------|--------|-----------|------|
| OpenAI | `openai` | `openai` | - | ✅ | ❌ | ✅ |
| Anthropic | `anthropic` | `anthropic` | `anthropic` | ✅ | ✅ | ✅ |
| 智谱 AI | `zhipu` | `zhipuai` | - | ✅ | ✅ | ❌ |
| DeepSeek | `deepseek` | `deepseek` | - | ✅ | ❌ | ✅ |
| MiniMax | `minimax` | `minimax` | - | ✅ | ✅ | ❌ |
| Moonshot | `moonshot` | `moonshotai-cn` | - | ✅ | ❌ | ❌ |
| OpenRouter | `openrouter` | `openrouter` | `openrouter` | ✅ | ❌ | ❌ |
| 通义千问 | `qwen` | `alibaba` | - | ✅ | ❌ | ❌ |
| Google AI | `google` | `google` | - | ✅ | ❌ | ❌ |
| Mistral | `mistral` | `mistral` | - | ✅ | ❌ | ❌ |
| Amazon Bedrock | `bedrock` | `amazon-bedrock` | `amazon_bedrock` | ✅ | ❌ | ✅ |
| Google Vertex | `vertex` | `google-vertex` | `google_vertex` | ✅ | ❌ | ✅ |

#### 自定义供应商（不在 models.dev 中）

| 类型 | 预设 ID | 说明 |
|------|---------|------|
| Other | `other` | 用户完全自定义：名称、API 地址、API Key、能力 |

**加载器说明**：

- `anthropic`: 添加 Claude Code beta headers
- `openrouter`: 添加 HTTP-Referer 和 X-Title headers
- `amazon_bedrock`: 处理跨区域推理前缀
- `google_vertex`: 处理 Google 认证

**数据来源优先级**：

```
本地配置 (local_overrides) > models.dev 数据
```

**同步策略**：

- 自动同步：每天凌晨 3 点
- 手动同步：`POST /api/admin/models/sync`

### 7.3 客户端配置指南

#### 7.3.1 Opencode 配置方法

Opencode 是一个开源的 AI 编程助手，支持通过配置文件添加自定义供应商。

**配置文件位置**：`~/.config/opencode/opencode.json` 或项目根目录的 `opencode.json`

**配置 LTM 平台为供应商**：

```json
{
  "$schema": "https://opencode.ai/schema/config.json",
  "model": "ltm/claude-sonnet-4-20250514",
  "provider": {
    "ltm": {
      "name": "LTM Gateway",
      "type": "openai-compatible",
      "baseURL": "https://your-ltm-gateway.com/v1",
      "apiKey": "${LTM_API_KEY}",
      "models": {
        "claude-sonnet-4-20250514": {
          "name": "Claude Sonnet 4",
          "contextWindow": 200000,
          "maxOutput": 64000
        },
        "claude-opus-4-20250514": {
          "name": "Claude Opus 4",
          "contextWindow": 200000,
          "maxOutput": 32000
        },
        "gpt-4o": {
          "name": "GPT-4o",
          "contextWindow": 128000,
          "maxOutput": 16384
        },
        "glm-5": {
          "name": "GLM-5",
          "contextWindow": 204800,
          "maxOutput": 131072
        },
        "deepseek-r1": {
          "name": "DeepSeek R1",
          "contextWindow": 128000,
          "maxOutput": 8192
        }
      }
    }
  }
}
```

**环境变量设置**：

```bash
# 在 ~/.bashrc 或 ~/.zshrc 中添加
export LTM_API_KEY="ltm-sk-your-platform-key-here"
```

**使用方法**：

```bash
# 使用默认模型（配置文件中指定的 model）
opencode

# 指定模型
opencode --model ltm/claude-opus-4-20250514
opencode --model ltm/gpt-4o
opencode --model ltm/glm-5
opencode --model ltm/deepseek-r1

# 查看可用模型
opencode --list-models
```

**配置说明**：

| 字段 | 说明 |
|------|------|
| `model` | 默认使用的模型，格式为 `ltm/{model_id}` |
| `provider.ltm.baseURL` | LTM 网关地址，指向 `/v1` 端点 |
| `provider.ltm.apiKey` | 平台分发的 API Key（`ltm-sk-xxx` 格式）|
| `provider.ltm.models` | 可用模型列表及其能力配置 |

**支持的模型前缀路由**：

```
# 直接使用模型 ID（通过前缀匹配）
gpt-4o          → OpenAI
claude-sonnet-4 → Anthropic
glm-5           → 智谱 AI
deepseek-r1     → DeepSeek

# 或显式指定供应商
ltm/gpt-4o
ltm/claude-sonnet-4
ltm/glm-5
```

---

#### 7.3.2 Claude Code 配置方法

> ⚠️ **状态**: 待研究，本期优化暂不实现

Claude Code 是 Anthropic 官方的命令行工具，使用 Anthropic Messages API 格式。

**预期配置方式**：

```bash
# 设置环境变量指向 LTM 网关
export ANTHROPIC_BASE_URL="https://your-ltm-gateway.com"
export ANTHROPIC_API_KEY="ltm-sk-your-platform-key-here"

# 运行 Claude Code
claude
```

**注意事项**：

1. Claude Code 使用 `/v1/messages` 端点（Anthropic 格式）
2. LTM 网关需要支持 Anthropic 格式的透传
3. 需要验证 Claude Code 的请求格式是否与标准 Anthropic API 兼容

**待研究事项**：

- [ ] Claude Code 的完整请求/响应格式
- [ ] Claude Code 对 `anthropic-version` 头的要求
- [ ] Claude Code 对流式响应的处理方式
- [ ] 是否支持自定义 headers

---

#### 7.3.3 其他客户端配置

**Cursor / Continue / Cline 等 OpenAI 兼容客户端**：

```json
{
  "apiProvider": "openai-compatible",
  "apiBase": "https://your-ltm-gateway.com/v1",
  "apiKey": "ltm-sk-your-platform-key-here",
  "model": "claude-sonnet-4-20250514"
}
```

**Python SDK (openai)**：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://your-ltm-gateway.com/v1",
    api_key="ltm-sk-your-platform-key-here"
)

response = client.chat.completions.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

**Python SDK (anthropic)**：

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="https://your-ltm-gateway.com",
    api_key="ltm-sk-your-platform-key-here"
)

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)
```

---

### 7.4 参考资料

- [Opencode 源码](https://github.com/anomalyco/opencode)
- [models.dev 文档](https://models.dev)
- [AI SDK Provider 规范](https://sdk.vercel.ai/docs/ai-sdk-core/provider)
