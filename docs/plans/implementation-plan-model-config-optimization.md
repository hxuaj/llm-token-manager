# 模型配置系统优化实施计划

> 版本: v1.0
> 基于: docs/PRD-model-config-optimization.md
> 预计工期: 5-6 周

---

## 1. 背景与目标

### 1.1 问题现状

1. **适配器重复代码**：OpenAIAdapter、ZhipuAdapter、QwenAdapter、OpenRouterAdapter 代码几乎完全相同（约 90%+ 重复）
2. **路由规则分散**：`MODEL_PREFIX_TO_PROVIDER` 和 `ANTHROPIC_MODEL_ROUTE_RULES` 两套独立定义，存在重复（claude-、glm-、minimax-）
3. **模型元数据维护困难**：定价、能力信息需要手动维护，更新滞后
4. **缺乏 models.dev 集成**：无法自动获取最新的模型元数据

### 1.2 优化目标

1. **models.dev 作为 SSOT**：自动同步模型元数据（定价、能力），减少手动维护
2. **统一适配器体系**：消除重复代码，配置化添加新供应商
3. **统一路由机制**：合并两套路由规则，支持 OpenAI 和 Anthropic 两种端点格式
4. **本地配置优先**：支持覆盖 models.dev 数据，同步时保留本地修改

---

## 2. 实施阶段

### 阶段一：数据架构与统一适配器（P0）- 1.5 周

#### Step 1.1：models.dev 数据同步服务

**目标**：实现从 models.dev 获取模型元数据的基础设施

**新增文件**：
- `backend/services/models_dev_service.py` - 数据同步服务

**核心功能**：
```python
class ModelsDevService:
    MODELS_DEV_URL = "https://models.dev/api.json"

    async def fetch_all_data(force_refresh: bool = False) -> dict
    async def get_provider(provider_id: str) -> dict | None
    async def get_model(provider_id: str, model_id: str) -> dict | None
    async def sync_to_database(db: AsyncSession, provider_id: str | None = None) -> SyncResult

    @staticmethod
    def merge_configs(base: dict, override: dict) -> dict  # 深度合并
```

**测试用例** (`backend/tests/test_models_dev_service.py`):
- [ ] `test_fetch_all_data_success` - 成功获取数据
- [ ] `test_fetch_all_data_with_cache` - 缓存命中
- [ ] `test_fetch_all_data_force_refresh` - 强制刷新
- [ ] `test_merge_configs_simple` - 简单字段覆盖
- [ ] `test_merge_configs_nested` - 嵌套对象合并
- [ ] `test_merge_configs_none_deletes` - None 值删除字段
- [ ] `test_sync_to_database_new_provider` - 同步新供应商
- [ ] `test_sync_preserves_local_overrides` - 保留本地覆盖

---

#### Step 1.2：数据库 Schema 扩展

**目标**：添加支持 SSOT 的字段

**迁移文件**：
- `backend/alembic/versions/xxx_add_ssot_fields.py`

**providers 表新增字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | VARCHAR(20) | 'models_dev' / 'custom' |
| `models_dev_id` | VARCHAR(100) | 对应 models.dev 的供应商 ID |
| `local_overrides` | JSON | 本地覆盖的字段 |
| `last_synced_at` | DateTime | 上次同步时间 |
| `supported_endpoints` | JSON | 支持的端点 ["openai", "anthropic"] |

**model_catalog 表新增字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `models_dev_id` | VARCHAR(100) | 对应 models.dev 的模型 ID |
| `base_config` | JSON | models.dev 原始配置 |
| `local_overrides` | JSON | 本地覆盖的字段 |
| `last_synced_at` | DateTime | 上次同步时间 |

**测试用例** (`backend/tests/test_ssot_migration.py`):
- [ ] `test_migration_applies_successfully`
- [ ] `test_provider_ssot_fields`
- [ ] `test_model_catalog_ssot_fields`

---

#### Step 1.3：统一 OpenAI 兼容适配器

**目标**：合并重复的 OpenAI 兼容适配器

**新增文件**：
- `backend/services/providers/openai_compatible.py`

**删除文件**（重构后）：
- `backend/services/providers/zhipu_adapter.py`
- `backend/services/providers/qwen_adapter.py`
- （保留 `openai_adapter.py` 作为参考，标记 deprecated）

```python
class OpenAICompatibleAdapter(BaseAdapter):
    """所有 OpenAI 兼容 API 的通用适配器"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_headers: dict = None,
        endpoint: str = "/chat/completions",
        timeout: float = 120.0
    ):
        super().__init__(base_url, api_key)
        self.default_headers = default_headers or {}
        self.endpoint = endpoint
        self.timeout = timeout

    def provider_name(self) -> str:
        return "openai_compatible"

    def convert_request(self, openai_request: Dict) -> Dict:
        return openai_request  # 透传

    def convert_response(self, provider_response: Dict, model: str) -> Dict:
        return provider_response  # 透传

    def get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.default_headers
        }
```

**测试用例** (`backend/tests/test_openai_compatible_adapter.py`):
- [ ] `test_convert_request_passthrough`
- [ ] `test_convert_response_passthrough`
- [ ] `test_get_headers_with_defaults`
- [ ] `test_get_headers_custom_headers`
- [ ] `test_forward_request_success`
- [ ] `test_forward_stream_success`

---

#### Step 1.4：Anthropic 透传适配器

**目标**：为 Anthropic 端点添加透传适配器

**新增文件**：
- `backend/services/providers/anthropic_passthrough.py`

```python
class AnthropicPassthroughAdapter(BaseAdapter):
    """Anthropic 格式原生透传适配器"""

    def get_endpoint(self) -> str:
        return f"{self.base_url}/v1/messages"

    def get_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            **self.default_headers
        }

    def convert_request(self, anthropic_request: Dict) -> Dict:
        return anthropic_request  # 透传

    def convert_response(self, provider_response: Dict, model: str) -> Dict:
        return provider_response  # 透传
```

**测试用例** (`backend/tests/test_anthropic_passthrough_adapter.py`):
- [ ] `test_get_endpoint`
- [ ] `test_get_headers`
- [ ] `test_convert_request_passthrough`
- [ ] `test_forward_request_success`

---

#### Step 1.5：统一路由服务

**目标**：合并两套路由规则，支持两种端点格式

**新增文件**：
- `backend/services/unified_router.py`

**核心实现**：
```python
class UnifiedRouterService:
    """统一模型路由服务"""

    # 统一的路由规则（替代 MODEL_PREFIX_TO_PROVIDER 和 ANTHROPIC_MODEL_ROUTE_RULES）
    ROUTE_RULES = {
        "openai": {
            "prefixes": ["gpt-", "o1-", "o3-", "o4-"],
            "api_format": "openai",
            "supported_endpoints": ["openai"]
        },
        "anthropic": {
            "prefixes": ["claude-"],
            "api_format": "anthropic",
            "supported_endpoints": ["openai", "anthropic"]
        },
        "zhipu": {
            "prefixes": ["glm-"],
            "api_format": "openai_compatible",
            "supported_endpoints": ["openai", "anthropic"]
        },
        "deepseek": {
            "prefixes": ["deepseek-"],
            "api_format": "openai_compatible",
            "supported_endpoints": ["openai"]
        },
        "minimax": {
            "prefixes": ["minimax-", "MiniMax-"],
            "api_format": "openai_compatible",
            "supported_endpoints": ["openai", "anthropic"]
        },
        "openrouter": {
            "prefixes": ["openai/", "anthropic/", "google/", "meta-llama/", "deepseek/"],
            "api_format": "openai_compatible",
            "supported_endpoints": ["openai"]
        },
        "qwen": {
            "prefixes": ["qwen-"],
            "api_format": "openai_compatible",
            "supported_endpoints": ["openai"]
        },
    }

    def parse_model_string(self, model: str) -> Tuple[str, str]:
        """解析模型字符串，支持 provider/model 和前缀匹配"""

    def supports_endpoint(self, provider_name: str, endpoint: str) -> bool:
        """检查供应商是否支持指定端点"""

    async def get_adapter(
        self,
        provider: Provider,
        api_key: str,
        endpoint: str,  # "openai" or "anthropic"
        db: AsyncSession
    ) -> BaseAdapter:
        """根据供应商和端点获取适配器"""
```

**测试用例** (`backend/tests/test_unified_router.py`):
- [ ] `test_parse_model_implicit_prefix`
- [ ] `test_parse_model_explicit_provider`
- [ ] `test_parse_model_unknown`
- [ ] `test_supports_endpoint_openai`
- [ ] `test_supports_endpoint_anthropic`
- [ ] `test_get_adapter_openai_compatible`
- [ ] `test_get_adapter_anthropic_conversion`
- [ ] `test_get_adapter_anthropic_passthrough`

---

#### Step 1.6：更新网关路由

**修改文件**：
- `backend/routers/gateway.py` - 使用 UnifiedRouterService
- `backend/routers/anthropic_gateway.py` - 使用 UnifiedRouterService
- `backend/services/proxy.py` - 删除 MODEL_PREFIX_TO_PROVIDER
- `backend/services/anthropic_proxy.py` - 删除 ANTHROPIC_MODEL_ROUTE_RULES

**变更要点**：
1. gateway.py 使用 `UnifiedRouterService.parse_model_string()` 替代 `get_provider_name_by_model()`
2. anthropic_gateway.py 使用 `UnifiedRouterService.get_adapter()` 获取 AnthropicPassthroughAdapter
3. 统一使用 KeySelector 逻辑选择 API Key
4. 为 Anthropic 端点添加成本计算和 x_ltm 元数据

**测试用例** (`backend/tests/test_gateway_unified.py`):
- [ ] `test_openai_endpoint_gpt_model`
- [ ] `test_openai_endpoint_claude_model`
- [ ] `test_openai_endpoint_provider_prefix`
- [ ] `test_anthropic_endpoint_claude_model`
- [ ] `test_anthropic_endpoint_zhipu_model`
- [ ] `test_anthropic_endpoint_unsupported_provider` - DeepSeek 不支持 Anthropic 格式
- [ ] `test_both_endpoints_consistent_behavior`

---

### 阶段二：供应商预设与简化配置（P1）- 2.5 周

#### Step 2.1：供应商预设配置

**新增文件**：
- `backend/services/provider_presets.py`

```python
@dataclass
class ProviderPreset:
    id: str
    display_name: str
    category: Literal["standard", "other"]
    models_dev_id: str | None = None
    default_base_url: str = ""
    api_format: str = "openai_compatible"
    supported_endpoints: list[str] = None
    default_headers: dict = None
    loader: str | None = None
    supports_cache_tokens: bool = False

PROVIDER_PRESETS = {
    "openai": ProviderPreset(...),
    "anthropic": ProviderPreset(...),
    "zhipu": ProviderPreset(...),
    "deepseek": ProviderPreset(...),
    "minimax": ProviderPreset(...),
    "openrouter": ProviderPreset(...),
    "qwen": ProviderPreset(...),
    "google": ProviderPreset(...),
    "mistral": ProviderPreset(...),
    "other": ProviderPreset(
        id="other",
        display_name="Other (自定义)",
        category="other",
        ...
    ),
}
```

**测试用例** (`backend/tests/test_provider_presets.py`):
- [ ] `test_get_preset_by_id`
- [ ] `test_get_preset_by_models_dev_id`
- [ ] `test_standard_presets_have_models_dev_id`
- [ ] `test_other_preset_is_custom`

---

#### Step 2.2：供应商管理 API

**新增路由** (`backend/routers/admin_providers.py`):

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/admin/providers/presets` | GET | 获取预设列表 |
| `/api/admin/providers/validate-key` | POST | 验证 API Key |
| `/api/admin/providers/quick-create` | POST | 一键创建供应商 |
| `/api/admin/models/sync` | POST | 手动同步 models.dev |
| `/api/admin/models/{model_id}/overrides` | DELETE | 重置本地覆盖 |

**测试用例** (`backend/tests/test_admin_provider_apis.py`):
- [ ] `test_get_presets_list`
- [ ] `test_validate_key_success`
- [ ] `test_validate_key_invalid`
- [ ] `test_quick_create_standard_provider`
- [ ] `test_quick_create_custom_provider`
- [ ] `test_manual_sync_models_dev`
- [ ] `test_reset_local_overrides`

---

#### Step 2.3：自定义加载器机制

**新增文件**：
- `backend/services/provider_loaders/__init__.py` - 加载器基类和注册表
- `backend/services/provider_loaders/builtin.py` - 内置加载器实现

```python
class ProviderLoader(ABC):
    @abstractmethod
    async def load(self, provider: Provider, api_key: str, db: AsyncSession) -> LoaderResult:
        pass

class LoaderResult:
    autoload: bool = True
    options: dict = None
    headers: dict = None

# 内置加载器
class AnthropicLoader(ProviderLoader):
    """添加 beta headers 支持 Claude Code"""
    async def load(self, provider, api_key, db):
        return LoaderResult(
            headers={"anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14"}
        )

class OpenRouterLoader(ProviderLoader):
    """添加 Referer 和 Title headers"""
    async def load(self, provider, api_key, db):
        return LoaderResult(
            headers={"HTTP-Referer": "https://ltm.example.com", "X-Title": "LTM Gateway"}
        )
```

**测试用例** (`backend/tests/test_provider_loaders.py`):
- [ ] `test_anthropic_loader_adds_beta_headers`
- [ ] `test_openrouter_loader_adds_headers`
- [ ] `test_loader_registry`
- [ ] `test_loader_error_isolation`

---

#### Step 2.4：缓存 Token 计费

**修改文件**：
- `backend/services/billing.py` - 添加缓存 Token 计费逻辑
- `backend/models/request_log.py` - 添加缓存 Token 字段

**计费逻辑**：
```python
async def calculate_request_cost(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    model: ModelCatalog
) -> Decimal:
    return (
        input_tokens * model.input_price / 1_000_000
        + output_tokens * model.output_price / 1_000_000
        + cache_read_tokens * (model.cache_read_price or 0) / 1_000_000
        + cache_write_tokens * (model.cache_write_price or 0) / 1_000_000
    )
```

**测试用例** (`backend/tests/test_cache_token_billing.py`):
- [ ] `test_calculate_cost_with_cache_read`
- [ ] `test_calculate_cost_with_cache_write`
- [ ] `test_anthropic_cache_token_extraction`
- [ ] `test_openai_cache_token_extraction`
- [ ] `test_deepseek_cache_token_extraction`

---

#### Step 2.5：前端供应商配置改造

**修改文件**：
- `frontend/src/pages/AdminProviders.jsx`

**UI 变更**：
1. 供应商类型下拉选择（标准 + Other）
2. 选择预设后自动填充 base_url
3. "验证并发现" 按钮
4. 展示发现的模型列表
5. 定价来源标识（models.dev / 手动配置）

---

### 阶段三：能力增强（P2）- 1.5 周

#### Step 3.1：丰富模型能力字段

**数据库迁移**：
- 添加 `capabilities` JSONB 字段（完整能力结构）
- 添加 `family`, `knowledge_cutoff`, `release_date` 字段

**能力结构**：
```json
{
  "temperature": true,
  "reasoning": false,
  "attachment": false,
  "toolcall": true,
  "interleaved": false,
  "input": {"text": true, "audio": false, "image": true, "video": false, "pdf": false},
  "output": {"text": true, "audio": false, "image": false, "video": false, "pdf": false}
}
```

---

#### Step 3.2：模型变体支持

**新增文件**：
- `backend/services/model_variants.py`

支持格式：`claude-sonnet-4:extended-thinking`

---

#### Step 3.3：模型状态生命周期

状态：`active` / `deprecated` / `alpha` / `beta` / `inactive`

废弃模型请求返回 `X-Model-Deprecated` 警告头

---

### 阶段四：优化与文档（P3）- 0.5 周

#### Step 4.1：配置热重载 API

```
POST /api/admin/config/reload
POST /api/admin/models/sync
```

#### Step 4.2：文档更新

- API 文档
- 部署文档（models.dev 同步配置）
- 运维手册

---

## 3. 关键文件变更清单

### 新增文件

| 文件路径 | 说明 |
|----------|------|
| `services/models_dev_service.py` | models.dev 数据同步服务 |
| `services/unified_router.py` | 统一路由服务 |
| `services/provider_presets.py` | 供应商预设配置 |
| `services/providers/openai_compatible.py` | 通用 OpenAI 兼容适配器 |
| `services/providers/anthropic_passthrough.py` | Anthropic 透传适配器 |
| `services/provider_loaders/__init__.py` | 加载器基类和注册表 |
| `services/provider_loaders/builtin.py` | 内置加载器实现 |
| `alembic/versions/xxx_add_ssot_fields.py` | 数据库迁移 |

### 删除文件

| 文件路径 | 原因 |
|----------|------|
| `services/providers/zhipu_adapter.py` | 合并到 OpenAICompatibleAdapter |
| `services/providers/qwen_adapter.py` | 合并到 OpenAICompatibleAdapter |

### 修改文件

| 文件路径 | 变更说明 |
|----------|----------|
| `models/provider.py` | 添加 SSOT 字段 |
| `models/model_catalog.py` | 添加 SSOT 字段 |
| `routers/gateway.py` | 使用 UnifiedRouterService |
| `routers/anthropic_gateway.py` | 使用 UnifiedRouterService |
| `services/proxy.py` | 删除 MODEL_PREFIX_TO_PROVIDER |
| `services/anthropic_proxy.py` | 删除 ANTHROPIC_MODEL_ROUTE_RULES |
| `services/billing.py` | 添加缓存 Token 计费 |

---

## 4. 验证方案

### 4.1 单元测试

每个 Step 完成后运行：
```bash
/Users/hxuaj/miniconda3/envs/llm-token-manager/bin/python -m pytest backend/tests/test_<module>.py -v
```

### 4.2 集成测试

阶段完成后运行完整测试套件：
```bash
/Users/hxuaj/miniconda3/envs/llm-token-manager/bin/python -m pytest backend/tests/ -v
```

### 4.3 端到端验证

1. **OpenAI 端点**：`curl -X POST /v1/chat/completions -d '{"model": "gpt-4o", ...}'`
2. **Anthropic 端点**：`curl -X POST /v1/messages -d '{"model": "claude-sonnet-4", ...}'`
3. **provider/model 格式**：`curl -X POST /v1/chat/completions -d '{"model": "openai/gpt-4o", ...}'`
4. **models.dev 同步**：`curl -X POST /api/admin/models/sync`

---

## 5. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| models.dev 不可用 | 本地 24 小时缓存 + 回退到上次成功数据 |
| 配置合并冲突 | local_overrides 字段记录修改，同步时跳过 |
| 适配器重构影响现有功能 | 保持旧代码兼容，灰度发布，完整测试覆盖 |
| 数据库迁移失败 | 迁移前备份，支持回滚 |

---

## 6. 实施顺序建议

按以下顺序执行，每个 Step 完成后验证再进入下一步：

1. **Step 1.1** - models.dev 服务（无依赖）
2. **Step 1.2** - 数据库迁移（依赖 1.1 的数据结构设计）
3. **Step 1.3** - OpenAI 兼容适配器（无依赖）
4. **Step 1.4** - Anthropic 透传适配器（无依赖）
5. **Step 1.5** - 统一路由服务（依赖 1.3, 1.4）
6. **Step 1.6** - 更新网关路由（依赖 1.5，核心变更）
7. **Step 2.x** - 供应商预设和加载器
8. **Step 3.x** - 能力增强
9. **Step 4.x** - 优化与文档

---

## 7. 现有代码分析摘要

### 7.1 适配器重复分析

| 适配器 | 重复度 | 建议 |
|--------|--------|------|
| OpenAIAdapter | 100% | 使用 `OpenAICompatibleAdapter` 基类 |
| ZhipuAdapter | 100% | 使用 `OpenAICompatibleAdapter` 基类 |
| QwenAdapter | 100% | 使用 `OpenAICompatibleAdapter` 基类 |
| OpenRouterAdapter | 90% | 使用基类 + 覆盖 `get_headers()` |
| AnthropicAdapter | 0% | 保持独立，有复杂转换逻辑 |
| MiniMaxAdapter | 0% | 保持继承 AnthropicAdapter |

### 7.2 路由规则重复

| 前缀 | MODEL_PREFIX_TO_PROVIDER | ANTHROPIC_MODEL_ROUTE_RULES |
|------|--------------------------|----------------------------|
| `claude-` | ✓ anthropic | ✓ anthropic |
| `glm-` | ✓ zhipu | ✓ zhipu |
| `minimax-` | ✓ minimax | ✓ minimax |
| `MiniMax-` | ✓ minimax | ✓ minimax |

### 7.3 数据库现状

**providers 表**：已有 `name`, `base_url`, `api_format`, `enabled`, `config` 字段

**model_catalog 表**：已有 `source` 字段（值：auto_discovered, manual, builtin_default），需要扩展支持 models_dev

---

## 8. Claude Code 执行提示

当使用 Claude Code 实施此计划时，请：

1. **严格遵循 CLAUDE.md 中的开发规范**：
   - 先写测试，后写实现
   - 提交前必须运行测试
   - 使用 miniconda 环境：`/Users/hxuaj/miniconda3/envs/llm-token-manager/bin/python`

2. **按 Step 顺序执行**：
   - 每个 Step 完成后运行测试确认通过
   - 使用 `git commit` 提交，commit message 遵循 Conventional Commits

3. **测试文件命名**：
   - `test_models_dev_service.py`
   - `test_openai_compatible_adapter.py`
   - `test_unified_router.py`
   - 等等

4. **迁移文件命名**：
   - `alembic revision -m "add_ssot_fields_to_providers"`
   - `alembic revision -m "add_ssot_fields_to_model_catalog"`
