# API 参考文档

> LLM Token Manager API 接口文档
> 最后更新：2026-03-04

---

## 目录

1. [认证说明](#认证说明)
2. [网关 API](#网关-api)
3. [用户 API](#用户-api)
4. [管理 API](#管理-api)
   - [配置热重载](#配置热重载)
   - [模型同步](#模型同步)
   - [供应商管理](#供应商管理)
   - [模型管理](#模型管理)
5. [错误响应](#错误响应)

---

## 认证说明

### 平台 Key 认证（网关 API）

用于调用 `/v1/chat/completions` 和 `/v1/messages` 端点。

```
Authorization: Bearer ltm-sk-xxx
```

或

```
x-api-key: ltm-sk-xxx
```

### JWT 认证（管理 API）

用于调用 `/api/admin/*` 和 `/api/user/*` 端点。

```
Authorization: Bearer <jwt_token>
```

---

## 网关 API

### POST /v1/chat/completions

OpenAI 格式的聊天补全接口。

**请求示例**：
```json
{
  "model": "gpt-4o",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 1024,
  "stream": false
}
```

**支持的模型前缀**：
| 前缀 | 供应商 |
|------|--------|
| `gpt-`, `o1-`, `o3-`, `o4-` | OpenAI |
| `claude-` | Anthropic |
| `glm-` | 智谱 |
| `deepseek-` | DeepSeek |
| `minimax-`, `MiniMax-` | MiniMax |
| `qwen-` | 通义千问 |
| `openai/`, `anthropic/`, etc. | OpenRouter |

**模型变体支持**：
```
claude-sonnet-4:extended-thinking  # 扩展思考模式
claude-sonnet-4:max               # 最大输出模式
```

### POST /v1/messages

Anthropic Messages API 格式接口。

**请求示例**：
```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1024,
  "messages": [{"role": "user", "content": "Hello"}]
}
```

### GET /v1/models

获取可用模型列表。

---

## 管理 API

### 配置热重载

#### POST /api/admin/config/reload

重载供应商和模型配置（从数据库重新读取）。

**认证**：需要 Admin 角色

**请求**：无请求体

**响应**：
```json
{
  "success": true,
  "message": "Configuration reloaded successfully",
  "providers_count": 5,
  "reloaded_at": "2026-03-04T10:30:00.000000"
}
```

**使用场景**：
- 数据库中直接修改了供应商配置后
- 添加或删除供应商 API Key 后
- 需要立即生效配置变更时

---

### 模型同步

#### POST /api/admin/models/sync

从 models.dev 同步模型元数据（定价、能力等）。

**认证**：需要 Admin 角色

**请求**：
```json
{
  "force_refresh": false,
  "provider_id": null
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `force_refresh` | boolean | 是否强制刷新 models.dev 缓存，默认 false |
| `provider_id` | string | 只同步指定供应商，null 表示同步全部 |

**响应**：
```json
{
  "success": true,
  "synced_at": "2026-03-04T10:30:00.000000",
  "providers_synced": 3,
  "models_synced": 45,
  "new_models": 5,
  "updated_models": 12,
  "preserved_local": 3,
  "conflicts": [],
  "error": null
}
```

| 字段 | 说明 |
|------|------|
| `success` | 同步是否成功 |
| `synced_at` | 同步时间（UTC） |
| `providers_synced` | 同步的供应商数量 |
| `models_synced` | 同步的模型数量 |
| `new_models` | 新发现的模型数量 |
| `updated_models` | 更新的模型数量 |
| `preserved_local` | 保留的本地覆盖数量 |
| `conflicts` | 冲突列表 |
| `error` | 错误信息（如果有） |

**同步策略**：
1. models.dev 是基础数据源
2. 本地覆盖（`local_overrides`）优先级更高
3. 同步时不会覆盖手动修改的配置
4. 支持 24 小时本地缓存

---

### 供应商管理

#### GET /api/admin/providers

获取供应商列表。

#### POST /api/admin/providers

创建新供应商。

#### GET /api/admin/providers/presets

获取供应商预设列表（标准供应商配置模板）。

**响应**：
```json
{
  "presets": [
    {
      "id": "openai",
      "display_name": "OpenAI",
      "category": "standard",
      "default_base_url": "https://api.openai.com/v1",
      "api_format": "openai_compatible",
      "supported_endpoints": ["openai"],
      "supports_cache_tokens": false
    },
    {
      "id": "anthropic",
      "display_name": "Anthropic",
      "category": "standard",
      "default_base_url": "https://api.anthropic.com",
      "api_format": "anthropic",
      "supported_endpoints": ["openai", "anthropic"],
      "supports_cache_tokens": true
    }
  ]
}
```

#### POST /api/admin/providers/quick-create

使用预设快速创建供应商。

---

### 模型管理

#### GET /api/admin/models

获取模型列表。

**查询参数**：
| 参数 | 说明 |
|------|------|
| `provider_id` | 按供应商筛选 |
| `status` | 按状态筛选 |
| `source` | 按来源筛选 |

#### PATCH /api/admin/models/{model_id}

更新模型配置（会记录为本地覆盖）。

#### DELETE /api/admin/models/{model_id}/overrides

重置本地覆盖，恢复为 models.dev 原始配置。

---

## 模型状态

| 状态 | 说明 |
|------|------|
| `active` | 已启用，正常使用 |
| `inactive` | 已禁用 |
| `deprecated` | 已废弃，请求时返回警告头 |
| `alpha` | 内测中 |
| `beta` | 公测中 |
| `pending` | 待审核（新发现的模型） |

### 废弃模型警告

当请求废弃模型时，响应会包含警告头：

```
X-Model-Deprecated: true
```

---

## 错误响应

### OpenAI 格式错误

```json
{
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

### Anthropic 格式错误

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "Invalid API key"
  }
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 认证失败 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 429 | 额度超限或频率限制 |
| 500 | 服务器内部错误 |
| 502 | 供应商错误 |
| 504 | 供应商超时 |

---

## 响应头说明

| 响应头 | 说明 |
|--------|------|
| `X-Request-ID` | 请求唯一标识 |
| `X-Model-Deprecated` | 模型已废弃警告 |
| `X-LTM-Input-Tokens` | 输入 Token 数 |
| `X-LTM-Output-Tokens` | 输出 Token 数 |
| `X-LTM-Cache-Read-Tokens` | 缓存读取 Token 数 |
| `X-LTM-Cache-Write-Tokens` | 缓存写入 Token 数 |
| `X-LTM-Cost-USD` | 本次请求费用（USD） |

---

*最后更新：2026-03-04*
