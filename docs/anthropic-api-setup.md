# Anthropic Messages API 配置指南

本指南帮助团队成员配置 Claude Code、OpenCode 和 Anthropic SDK 使用平台 Key。

## 支持的供应商

| 供应商 | 模型前缀 | 示例模型 |
|--------|---------|---------|
| Anthropic | `claude-` | claude-sonnet-4-20250514, claude-opus-4-20250514 |
| 智谱 GLM | `glm-` | glm-5, glm-4-plus |
| MiniMax | `minimax-` | minimax-m2.5 |

---

## Claude Code 配置

### 使用 Claude 模型

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"

claude
```

### 使用 GLM-5

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"
export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5"

claude
```

### 使用 MiniMax-M2.5

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_AUTH_TOKEN="ltm-sk-你的平台Key"
export ANTHROPIC_DEFAULT_SONNET_MODEL="minimax-m2.5"

claude
```

---

## OpenCode 配置

### Anthropic Provider 模式

```bash
export ANTHROPIC_BASE_URL="https://llm.yourcompany.com"
export ANTHROPIC_API_KEY="ltm-sk-你的平台Key"

opencode
```

### OpenAI Provider 模式（已支持）

```bash
export OPENAI_BASE_URL="https://llm.yourcompany.com/v1"
export OPENAI_API_KEY="ltm-sk-你的平台Key"

opencode
```

---

## Anthropic Python SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="https://llm.yourcompany.com",
    api_key="ltm-sk-你的平台Key"
)

# 使用 Claude
message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)

# 使用 GLM-5
message = client.messages.create(
    model="glm-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}]
)

# 使用 MiniMax
message = client.messages.create(
    model="minimax-m2.5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

---

## 鉴权方式

网关支持两种鉴权方式：

1. **Authorization: Bearer**（推荐）
   ```
   Authorization: Bearer ltm-sk-xxx
   ```

2. **x-api-key**（Anthropic SDK 默认）
   ```
   x-api-key: ltm-sk-xxx
   ```

---

## 错误格式

所有 `/v1/messages` 端点的错误响应使用 Anthropic 格式：

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "Invalid API key"
  }
}
```

常见错误类型：

| error.type | HTTP 状态码 | 说明 |
|-----------|------------|------|
| `authentication_error` | 401 | Key 无效或已吊销 |
| `permission_error` | 403 | 无权访问该模型 |
| `not_found_error` | 404 | 模型不存在或未启用 |
| `rate_limit_error` | 429 | 额度超限或 RPM 超限 |
| `invalid_request_error` | 400 | 请求体格式错误 |
| `api_error` | 502/504 | 供应商错误或超时 |

---

## 获取平台 Key

1. 登录管理后台
2. 进入「我的 Key」页面
3. 点击「创建新 Key」
4. 复制生成的 Key（格式：`ltm-sk-xxx`）

**注意**：Key 只会在创建时显示一次，请妥善保存。

---

## 常见问题

### Q: 为什么我的请求返回 429 错误？

A: 可能原因：
- 月度额度已用完，联系管理员增加额度
- 请求频率超过 RPM 限制，稍后重试

### Q: 为什么使用 GLM 模型时报错？

A: 请确保：
- 管理员已配置智谱供应商的 API Key
- 模型名称以 `glm-` 开头

### Q: 流式响应支持吗？

A: 支持。设置 `"stream": true` 即可。

---

*最后更新：2026-02-28*
