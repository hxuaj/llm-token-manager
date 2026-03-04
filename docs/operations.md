# 运维手册

> LLM Token Manager 日常运维指南
> 最后更新：2026-03-04

---

## 目录

1. [日常运维任务](#日常运维任务)
2. [监控与告警](#监控与告警)
3. [用户管理](#用户管理)
4. [供应商管理](#供应商管理)
5. [模型管理](#模型管理)
6. [额度与计费](#额度与计费)
7. [故障处理](#故障处理)
8. [安全运维](#安全运维)

---

## 日常运维任务

### 每日检查清单

- [ ] 检查服务健康状态
- [ ] 检查错误日志
- [ ] 检查存储空间
- [ ] 检查异常用量

### 每周检查清单

- [ ] 检查模型同步状态
- [ ] 检查供应商 Key 有效性
- [ ] 检查用户额度使用情况
- [ ] 备份数据库

### 每月检查清单

- [ ] 审计用户账户
- [ ] 检查并清理废弃模型
- [ ] 检查计费准确性
- [ ] 更新系统依赖

---

## 监控与告警

### 健康检查端点

```bash
# 基础健康检查
curl https://llm.yourcompany.com/health

# 响应示例
{
  "status": "healthy",
  "database": "connected",
  "version": "1.2.0"
}
```

### 关键指标监控

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| API 响应时间 | > 5s | 网关响应延迟 |
| 错误率 | > 5% | 5xx 错误比例 |
| 数据库连接数 | > 80% | 连接池使用率 |
| 磁盘使用率 | > 80% | 存储空间 |
| 内存使用率 | > 85% | 内存占用 |
| 供应商错误率 | > 10% | 上游供应商故障 |

### Prometheus 指标

系统暴露以下 Prometheus 指标：

```
# 请求计数
ltm_requests_total{endpoint, model, status}

# 请求延迟
ltm_request_duration_seconds{endpoint, model}

# Token 使用
ltm_tokens_total{type="input|output|cache_read|cache_write", model}

# 费用统计
ltm_cost_usd_total{user_id, model}

# 活跃用户
ltm_active_users_gauge
```

### 日志级别配置

```bash
# 在 .env 中配置
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# 特定模块日志级别
LOG_LEVEL_MODELS_DEV=DEBUG
LOG_LEVEL_BILLING=INFO
```

---

## 用户管理

### 创建用户

```bash
# 通过管理后台
1. 登录管理后台
2. 进入「用户管理」
3. 点击「添加用户」
4. 填写邮箱和初始额度
```

### 重置用户密码

```bash
# 通过脚本
docker-compose exec backend python scripts/reset_password.py user@example.com

# 通过 API（需要 Admin Token）
curl -X POST https://llm.yourcompany.com/api/admin/users/{user_id}/reset-password \
  -H "Authorization: Bearer <admin_token>"
```

### 调整用户额度

```bash
# 增加月度额度
curl -X PATCH https://llm.yourcompany.com/api/admin/users/{user_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"monthly_quota_usd": 50.00}'
```

### 禁用/启用用户

```bash
# 禁用用户
curl -X PATCH https://llm.yourcompany.com/api/admin/users/{user_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'

# 启用用户
curl -X PATCH https://llm.yourcompany.com/api/admin/users/{user_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"is_active": true}'
```

### 查看用户用量

```sql
-- 查询用户本月用量
SELECT
    u.email,
    SUM(rl.cost_usd) as total_cost,
    SUM(rl.input_tokens) as total_input_tokens,
    SUM(rl.output_tokens) as total_output_tokens
FROM users u
JOIN user_api_keys uak ON u.id = uak.user_id
JOIN request_logs rl ON uak.id = rl.api_key_id
WHERE rl.created_at >= date_trunc('month', CURRENT_DATE)
GROUP BY u.id, u.email
ORDER BY total_cost DESC;
```

---

## 供应商管理

### 添加新供应商

1. **使用预设（推荐）**
   ```bash
   # 查看可用预设
   curl https://llm.yourcompany.com/api/admin/providers/presets \
     -H "Authorization: Bearer <admin_token>"

   # 快速创建
   curl -X POST https://llm.yourcompany.com/api/admin/providers/quick-create \
     -H "Authorization: Bearer <admin_token>" \
     -H "Content-Type: application/json" \
     -d '{
       "preset_id": "deepseek",
       "api_key": "sk-xxx"
     }'
   ```

2. **自定义供应商**
   ```bash
   curl -X POST https://llm.yourcompany.com/api/admin/providers \
     -H "Authorization: Bearer <admin_token>" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "custom-provider",
       "display_name": "自定义供应商",
       "base_url": "https://api.custom.com/v1",
       "api_format": "openai_compatible",
       "api_key": "sk-xxx"
     }'
   ```

### 供应商 Key 轮换

```bash
# 1. 添加新 Key
curl -X POST https://llm.yourcompany.com/api/admin/providers/{provider_id}/keys \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-new-key"}'

# 2. 验证新 Key
curl -X POST https://llm.yourcompany.com/api/admin/providers/validate-key \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"provider_id": "openai", "api_key": "sk-new-key"}'

# 3. 删除旧 Key
curl -X DELETE https://llm.yourcompany.com/api/admin/providers/{provider_id}/keys/{key_id} \
  -H "Authorization: Bearer <admin_token>"
```

### 禁用供应商

```bash
curl -X PATCH https://llm.yourcompany.com/api/admin/providers/{provider_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

## 模型管理

### 同步模型元数据

```bash
# 同步所有供应商（推荐每天执行）
curl -X POST https://llm.yourcompany.com/api/admin/models/sync \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{}'

# 强制刷新（跳过缓存）
curl -X POST https://llm.yourcompany.com/api/admin/models/sync \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"force_refresh": true}'
```

### 更新模型定价（本地覆盖）

```bash
# 覆盖模型定价
curl -X PATCH https://llm.yourcompany.com/api/admin/models/{model_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "input_price": 3.00,
    "output_price": 15.00
  }'
```

### 重置本地覆盖

```bash
# 恢复 models.dev 原始定价
curl -X DELETE https://llm.yourcompany.com/api/admin/models/{model_id}/overrides \
  -H "Authorization: Bearer <admin_token>"
```

### 管理模型状态

```bash
# 启用模型
curl -X PATCH https://llm.yourcompany.com/api/admin/models/{model_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "active"}'

# 废弃模型（用户请求时收到警告）
curl -X PATCH https://llm.yourcompany.com/api/admin/models/{model_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "deprecated"}'

# 禁用模型
curl -X PATCH https://llm.yourcompany.com/api/admin/models/{model_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "inactive"}'
```

### 查看模型列表

```bash
# 按状态筛选
curl "https://llm.yourcompany.com/api/admin/models?status=deprecated" \
  -H "Authorization: Bearer <admin_token>"

# 按来源筛选
curl "https://llm.yourcompany.com/api/admin/models?source=models_dev" \
  -H "Authorization: Bearer <admin_token>"
```

---

## 额度与计费

### 查看系统用量统计

```sql
-- 本月用量汇总
SELECT
    DATE(created_at) as date,
    COUNT(*) as requests,
    SUM(input_tokens) as input_tokens,
    SUM(output_tokens) as output_tokens,
    SUM(cache_read_tokens) as cache_read_tokens,
    SUM(cost_usd) as cost_usd
FROM request_logs
WHERE created_at >= date_trunc('month', CURRENT_DATE)
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### 用户额度重置

```sql
-- 手动重置用户月度用量（通常在月初自动执行）
UPDATE users
SET current_month_usage_usd = 0
WHERE id = 'user-uuid';
```

### 费用核对

```bash
# 导出计费明细
curl "https://llm.yourcompany.com/api/admin/billing/export?month=2026-03" \
  -H "Authorization: Bearer <admin_token>" \
  -o billing_202603.csv
```

---

## 故障处理

### 供应商故障

**症状**：大量 502 错误

**处理步骤**：
1. 检查供应商状态页面
2. 临时切换到备用供应商
3. 通知用户

```bash
# 禁用故障供应商
curl -X PATCH https://llm.yourcompany.com/api/admin/providers/{provider_id} \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### 数据库性能问题

**症状**：响应缓慢

**处理步骤**：
```bash
# 检查慢查询
docker-compose exec postgres psql -U ltm -d llm_manager -c "
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"

# 清理旧日志（保留最近 90 天）
docker-compose exec postgres psql -U ltm -d llm_manager -c "
DELETE FROM request_logs
WHERE created_at < CURRENT_DATE - INTERVAL '90 days';
"
```

### 内存泄漏

**症状**：内存持续增长

**处理步骤**：
```bash
# 重启服务
docker-compose restart backend

# 如果问题持续，检查是否有大对象未释放
docker-compose exec backend python -c "
import gc
print(f'Garbage objects: {len(gc.get_objects())}')
"
```

---

## 安全运维

### Key 泄露处理

**步骤**：
1. 立即吊销泄露的平台 Key
2. 检查该 Key 的使用记录
3. 如有异常用量，评估损失
4. 通知相关用户

```bash
# 吊销 Key
curl -X DELETE https://llm.yourcompany.com/api/admin/keys/{key_id} \
  -H "Authorization: Bearer <admin_token>"

# 查看 Key 使用记录
curl "https://llm.yourcompany.com/api/admin/keys/{key_id}/logs" \
  -H "Authorization: Bearer <admin_token>"
```

### 审计日志

```sql
-- 查看最近的管理操作
SELECT * FROM audit_logs
WHERE created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
```

### 定期安全检查

```bash
# 检查弱密码用户（需要自定义脚本）
python scripts/check_weak_passwords.py

# 检查过期 Token
docker-compose exec postgres psql -U ltm -d llm_manager -c "
SELECT u.email, COUNT(*) as expired_sessions
FROM users u
JOIN sessions s ON u.id = s.user_id
WHERE s.expires_at < NOW()
GROUP BY u.email
HAVING COUNT(*) > 5;
"

# 检查异常 IP
docker-compose exec postgres psql -U ltm -d llm_manager -c "
SELECT ip_address, COUNT(*) as requests
FROM request_logs
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY ip_address
HAVING COUNT(*) > 1000
ORDER BY requests DESC;
"
```

---

## 配置热重载

当修改数据库中的配置后，无需重启服务：

```bash
# 重载配置
curl -X POST https://llm.yourcompany.com/api/admin/config/reload \
  -H "Authorization: Bearer <admin_token>"
```

适用场景：
- 修改供应商配置
- 添加/删除供应商 Key
- 修改模型状态

---

## 常用命令速查

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f backend

# 重启服务
docker-compose restart backend

# 进入容器
docker-compose exec backend bash

# 数据库迁移
docker-compose exec backend alembic upgrade head

# 同步模型
curl -X POST http://localhost:8000/api/admin/models/sync \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 重载配置
curl -X POST http://localhost:8000/api/admin/config/reload \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 备份数据库
docker-compose exec postgres pg_dump -U ltm llm_manager > backup.sql

# 恢复数据库
cat backup.sql | docker-compose exec -T postgres psql -U ltm llm_manager
```

---

*最后更新：2026-03-04*
