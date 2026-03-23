# Feature Spec: 供应商 Key 软分配与溢出机制

> **文档类型**: Feature Spec（功能需求规格）
> **版本**: v1.0
> **日期**: 2026-03-23
> **关联**: LLM Token Manager PRD v1.2
> **优先级**: P1（资源利用优化）
> **预估工作量**: 3-4 天

---

## 1. 背景与动机

### 1.1 当前问题

网关目前对同一供应商的多个 Key 没有智能分配策略：

```
现状：所有用户的请求都使用第一个 active 的 Key

用户A ─┐                      ┌── Key 1 (60 RPM) ← 打满，频繁 429
用户B ─┼──→ 网关 ─────────────┤
用户C ─┘                      ├── Key 2 (60 RPM) ← 闲置
                              └── Key 3 (60 RPM) ← 闲置
```

**问题**：
- **资源浪费**：部分 Key 闲置，RPM 配额用不完
- **用户体验差**：高活跃用户组触发 429，其他 Key 却空闲
- **无容错能力**：某个 Key 失效，其用户完全不可用
- **成本归因模糊**：无法知道哪个用户的成本应该归属到哪个 Key

### 1.2 目标

实现 **软分配 + 溢出机制**：

```
目标：每个用户有主 Key，RPM 打满时自动溢出

用户A ──→ 主 Key: Key 1 ──→ 有额度 → 使用 Key 1
                      └──→ 无额度 → 溢出到 Key 2/3

用户B ──→ 主 Key: Key 2 ──→ 有额度 → 使用 Key 2
                      └──→ 无额度 → 溢出到 Key 1/3
```

**核心价值**：
1. **公平性**：每个用户获得均等的资源份额
2. **高利用率**：空闲 Key 可被借用
3. **容错能力**：单 Key 故障不影响用户
4. **成本清晰**：主 Key 归属明确，便于成本分摊

---

## 2. 核心概念

### 2.1 术语定义

| 术语 | 定义 |
|------|------|
| **Primary Key** | 用户绑定的主供应商 Key，用于成本归因和默认路由 |
| **Overflow Pool** | 溢出池，当 Primary Key 无额度时，可借用其他 Key |
| **RPM (Requests Per Minute)** | 每分钟请求数限制，由供应商设定 |
| **Key Assignment** | 用户与 Primary Key 的绑定关系 |

### 2.2 分配策略

**用户数 / Key 数 = 每个Key服务的用户数**

```
示例：
- 50 个用户
- 5 个 OpenAI Key
- 每个 Key 服务 10 个用户

分配结果：
Key 1: 用户 01-10 (Primary)
Key 2: 用户 11-20 (Primary)
Key 3: 用户 21-30 (Primary)
Key 4: 用户 31-40 (Primary)
Key 5: 用户 41-50 (Primary)
```

### 2.3 溢出规则

```
请求流程：

1. 用户发起请求
      ↓
2. 查询用户的 Primary Key
      ↓
3. 检查 Primary Key 的 RPM 额度
      ├── 有额度 → 使用 Primary Key
      └── 无额度 → 进入溢出流程
                      ↓
              从其他 Key 中选择
              (轮询 + RPM 检查)
                      ↓
              找到有额度的 Key → 使用
              或全部无额度 → 返回 429
```

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM Token Manager                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户请求 ──→ 鉴权 ──→ 额度检查 ──→ KeySelector ──→ 代理转发    │
│                                      │                          │
│                                      ↓                          │
│                         ┌────────────────────────┐              │
│                         │    KeySelector 服务     │              │
│                         │                        │              │
│                         │  1. 获取用户的 Primary │              │
│                         │  2. RPM 额度检查        │              │
│                         │  3. 溢出到其他 Key      │              │
│                         └────────────────────────┘              │
│                                      │                          │
│                    ┌─────────────────┼─────────────────┐        │
│                    ↓                 ↓                 ↓        │
│               ┌─────────┐      ┌─────────┐      ┌─────────┐    │
│               │  Key 1  │      │  Key 2  │      │  Key 3  │    │
│               │ RPM:60  │      │ RPM:60  │      │ RPM:60  │    │
│               │ 用户:10 │      │ 用户:10 │      │ 用户:10 │    │
│               └─────────┘      └─────────┘      └─────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 RPM 追踪架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      RPM 追踪方案                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  方案 A: 内存追踪（单实例）                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  KeyUsageTracker (内存 Dict)                             │   │
│  │  {                                                        │   │
│  │    "key_1": {"minute": "14:32", "count": 45},            │   │
│  │    "key_2": {"minute": "14:32", "count": 12},            │   │
│  │  }                                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│  优点：实现简单，无外部依赖                                      │
│  缺点：重启丢失，不支持多实例                                    │
│                                                                 │
│  方案 B: Redis 追踪（多实例）                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Redis Key: rpm:{provider}:{key_id}:{minute}             │   │
│  │  TTL: 60s 自动过期                                        │   │
│  │  INCR 原子操作                                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│  优点：支持多实例，数据可靠                                      │
│  缺点：需要 Redis 依赖                                          │
│                                                                 │
│  MVP 阶段：采用方案 A，预留 Redis 接口                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据模型变更

### 4.1 User 表扩展

```python
# models/user.py

class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(unique=True)
    # ... 现有字段 ...

    # 新增：供应商 Key 绑定（按供应商存储）
    # JSON 结构: {"openai": "key_uuid", "anthropic": "key_uuid", ...}
    primary_provider_keys: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default={}
    )
```

**primary_provider_keys 字段结构**：

```json
{
  "openai": "550e8400-e29b-41d4-a716-446655440001",
  "anthropic": "550e8400-e29b-41d4-a716-446655440002",
  "zhipu": "550e8400-e29b-41d4-a716-446655440003"
}
```

### 4.2 数据库迁移

```sql
-- Alembic migration
ALTER TABLE users ADD COLUMN primary_provider_keys JSONB DEFAULT '{}';

-- 创建索引（可选，用于按 Key 查询关联用户）
CREATE INDEX idx_users_primary_keys ON users USING GIN (primary_provider_keys);
```

---

## 5. 业务逻辑设计

### 5.1 KeySelector 服务重构

```python
# services/key_selector.py

class KeySelector:
    """供应商 Key 选择器 - 软分配 + 溢出机制"""

    def __init__(self, db: AsyncSession, rpm_tracker: RPMTracker):
        self.db = db
        self.rpm_tracker = rpm_tracker

    async def select_key(
        self,
        user_id: UUID,
        provider_name: str,
        model_id: str
    ) -> ProviderApiKey:
        """
        为用户选择合适的供应商 Key

        策略：
        1. 获取用户的 Primary Key
        2. 如果 Primary Key 有 RPM 额度，使用它
        3. 否则，溢出到其他有额量的 Key
        """

        # Step 1: 获取该供应商的所有活跃 Key
        all_keys = await self._get_active_keys(provider_name)

        if not all_keys:
            raise NoAvailableKeyError(f"No active keys for provider: {provider_name}")

        # Step 2: 获取用户的 Primary Key
        primary_key = await self._get_user_primary_key(user_id, provider_name)

        # Step 3: 优先尝试 Primary Key
        if primary_key and primary_key in all_keys:
            if await self.rpm_tracker.check_and_consume(primary_key.id, primary_key.rpm_limit):
                return primary_key

        # Step 4: 溢出到其他 Key
        for key in self._round_robin_iter(all_keys, exclude=primary_key):
            if await self.rpm_tracker.check_and_consume(key.id, key.rpm_limit):
                return key

        # Step 5: 所有 Key 都无额度
        raise RateLimitExceededError(
            f"All keys rate limited for provider: {provider_name}"
        )

    async def _get_user_primary_key(
        self,
        user_id: UUID,
        provider_name: str
    ) -> Optional[ProviderApiKey]:
        """获取用户绑定到指定供应商的 Primary Key"""
        user = await self.db.get(User, user_id)
        if not user or not user.primary_provider_keys:
            return None

        key_id = user.primary_provider_keys.get(provider_name)
        if not key_id:
            return None

        return await self.db.get(ProviderApiKey, UUID(key_id))

    def _round_robin_iter(
        self,
        keys: list[ProviderApiKey],
        exclude: Optional[ProviderApiKey] = None
    ) -> Iterator[ProviderApiKey]:
        """轮询迭代器，排除指定的 Key"""
        available = [k for k in keys if k != exclude]
        # 简单轮询：按创建时间排序后循环
        for key in sorted(available, key=lambda k: k.created_at):
            yield key
```

### 5.2 RPMTracker 服务

```python
# services/rpm_tracker.py

from collections import defaultdict
from datetime import datetime
from typing import Optional
import asyncio

class RPMTracker:
    """
    RPM 使用量追踪器

    内存实现，适合单实例部署。
    预留 Redis 接口以便未来扩展。
    """

    def __init__(self):
        # 结构: {key_id: {minute_timestamp: count}}
        self._usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._lock = asyncio.Lock()

    async def check_and_consume(
        self,
        key_id: str,
        rpm_limit: int
    ) -> bool:
        """
        检查是否有 RPM 额度，如果有则消耗一个额度

        Returns:
            True 如果有额度并成功消耗
            False 如果无额度
        """
        current_minute = self._get_current_minute()

        async with self._lock:
            current_count = self._usage[key_id][current_minute]

            if current_count >= rpm_limit:
                return False

            self._usage[key_id][current_minute] += 1
            return True

    async def get_current_usage(self, key_id: str) -> int:
        """获取当前分钟的已用请求数"""
        current_minute = self._get_current_minute()
        return self._usage[key_id][current_minute]

    async def get_remaining(self, key_id: str, rpm_limit: int) -> int:
        """获取剩余 RPM 额度"""
        current = await self.get_current_usage(key_id)
        return max(0, rpm_limit - current)

    def _get_current_minute(self) -> str:
        """获取当前分钟的时间戳字符串"""
        now = datetime.utcnow()
        return now.strftime("%Y-%m-%d %H:%M")

    async def cleanup_old_entries(self):
        """清理过期的分钟记录（可由定时任务调用）"""
        current_minute = self._get_current_minute()
        async with self._lock:
            for key_id in list(self._usage.keys()):
                for minute in list(self._usage[key_id].keys()):
                    if minute < current_minute:
                        del self._usage[key_id][minute]
```

### 5.3 用户 Key 分配服务

```python
# services/key_assignment.py

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from collections import defaultdict

class KeyAssignmentService:
    """
    供应商 Key 分配服务

    负责：
    1. 新用户注册时自动分配 Primary Key
    2. 新增供应商 Key 时重新平衡分配
    3. 提供 Admin 手动重新分配的接口
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def assign_primary_keys_for_new_user(self, user_id: UUID):
        """
        为新用户分配所有供应商的 Primary Key

        策略：选择当前用户数最少的 Key
        """
        # 获取所有供应商
        providers = await self._get_all_providers()

        assignments = {}

        for provider in providers:
            # 获取该供应商的所有活跃 Key
            keys = await self._get_active_keys(provider.id)
            if not keys:
                continue

            # 选择负载最少的 Key
            best_key = await self._select_least_loaded_key(keys)
            assignments[provider.name] = str(best_key.id)

        # 更新用户的 primary_provider_keys
        user = await self.db.get(User, user_id)
        user.primary_provider_keys = assignments
        await self.db.commit()

    async def rebalance_provider(self, provider_name: str):
        """
        重新平衡某个供应商的 Key 分配

        场景：新增或删除 Key 后调用
        """
        provider = await self._get_provider_by_name(provider_name)
        keys = await self._get_active_keys(provider.id)
        users = await self._get_users_by_provider(provider.name)

        if not keys:
            return

        # 按用户 ID 排序后均分
        sorted_users = sorted(users, key=lambda u: u.id)

        for i, user in enumerate(sorted_users):
            key_index = i % len(keys)
            assigned_key = keys[key_index]

            if user.primary_provider_keys is None:
                user.primary_provider_keys = {}

            user.primary_provider_keys[provider_name] = str(assigned_key.id)

        await self.db.commit()

    async def _select_least_loaded_key(
        self,
        keys: list[ProviderApiKey]
    ) -> ProviderApiKey:
        """选择当前绑定用户数最少的 Key"""
        key_user_counts = defaultdict(int)

        # 统计每个 Key 已绑定的用户数
        result = await self.db.execute(
            select(User)
            .where(User.primary_provider_keys.isnot(None))
        )
        users = result.scalars().all()

        for user in users:
            for provider_name, key_id in (user.primary_provider_keys or {}).items():
                key_user_counts[key_id] += 1

        # 选择用户数最少的 Key
        return min(keys, key=lambda k: key_user_counts.get(str(k.id), 0))

    async def get_key_assignment_stats(self, provider_name: str) -> dict:
        """
        获取某供应商的 Key 分配统计

        Returns:
            {
                "total_keys": 5,
                "total_users": 50,
                "assignments": {
                    "key_1": {"users": 10, "key_suffix": "ab12"},
                    "key_2": {"users": 10, "key_suffix": "cd34"},
                    ...
                }
            }
        """
        provider = await self._get_provider_by_name(provider_name)
        keys = await self._get_active_keys(provider.id)

        # 统计每个 Key 的用户数
        key_stats = {}
        for key in keys:
            key_stats[str(key.id)] = {
                "key_suffix": key.key_suffix,
                "users": 0,
                "user_list": []
            }

        result = await self.db.execute(
            select(User).where(User.primary_provider_keys.isnot(None))
        )
        users = result.scalars().all()

        for user in users:
            key_id = (user.primary_provider_keys or {}).get(provider_name)
            if key_id and key_id in key_stats:
                key_stats[key_id]["users"] += 1
                key_stats[key_id]["user_list"].append({
                    "id": str(user.id),
                    "username": user.username
                })

        return {
            "total_keys": len(keys),
            "total_users": sum(s["users"] for s in key_stats.values()),
            "assignments": key_stats
        }
```

---

## 6. API 变更

### 6.1 Admin API 新增

#### GET `/api/admin/providers/{provider_name}/key-assignments`

获取供应商 Key 的用户分配情况。

**响应**：
```json
{
  "total_keys": 5,
  "total_users": 50,
  "assignments": {
    "550e8400-e29b-41d4-a716-446655440001": {
      "key_suffix": "ab12",
      "users": 10,
      "user_list": [
        {"id": "...", "username": "user01"},
        {"id": "...", "username": "user02"}
      ]
    },
    "550e8400-e29b-41d4-a716-446655440002": {
      "key_suffix": "cd34",
      "users": 10,
      "user_list": [...]
    }
  }
}
```

#### POST `/api/admin/providers/{provider_name}/rebalance-keys`

手动触发 Key 分配重新平衡。

**响应**：
```json
{
  "message": "Keys rebalanced successfully",
  "total_users_affected": 50
}
```

#### PATCH `/api/admin/users/{user_id}/primary-key`

手动修改用户的 Primary Key。

**请求体**：
```json
{
  "provider": "openai",
  "key_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

### 6.2 User API 新增

#### GET `/api/user/primary-keys`

获取当前用户的 Primary Key 绑定情况。

**响应**：
```json
{
  "primary_keys": {
    "openai": {
      "key_id": "550e8400-...",
      "key_suffix": "ab12",
      "rpm_limit": 60
    },
    "anthropic": {
      "key_id": "550e8400-...",
      "key_suffix": "cd34",
      "rpm_limit": 100
    }
  }
}
```

### 6.3 Gateway 响应扩展

在 `x_ltm` 元数据中增加 `key_source` 字段，标识使用的是 Primary 还是 Overflow：

```json
{
  "x_ltm": {
    "cost_usd": 0.0023,
    "remaining_quota_usd": 9.9977,
    "key_id_suffix": "ab12",
    "key_source": "primary",  // 新增: "primary" | "overflow"
    "rpm_remaining": 45       // 新增: 当前 Key 剩余 RPM
  }
}
```

---

## 7. 前端变更

### 7.1 Admin 界面

#### 供应商详情页新增 "Key 分配" 标签

```
┌─────────────────────────────────────────────────────────────────┐
│  供应商: OpenAI                                                  │
├─────────────────────────────────────────────────────────────────┤
│  [Keys] [模型列表] [Key 分配] [设置]                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Key 分配概览                                                    │
│  ────────────────────────────────────────────────────────────   │
│  总 Key 数: 5    总用户数: 50    平均每 Key: 10 用户             │
│                                                                 │
│  [重新平衡分配]                                                  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Key 后缀 │ 绑定用户数 │ 用户列表                           │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ ...ab12 │ 10         │ user01, user02, user03... [展开]   │ │
│  │ ...cd34 │ 10         │ user11, user12, user13... [展开]   │ │
│  │ ...ef56 │ 10         │ user21, user22, user23... [展开]   │ │
│  │ ...gh78 │ 10         │ user31, user32, user33... [展开]   │ │
│  │ ...ij90 │ 10         │ user41, user42, user43... [展开]   │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 用户详情页显示 Primary Key

```
┌─────────────────────────────────────────────────────────────────┐
│  用户: user01                                                    │
├─────────────────────────────────────────────────────────────────┤
│  [基本信息] [平台 Key] [用量统计] [Primary Key 绑定]             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  供应商 Key 绑定                                                 │
│  ────────────────────────────────────────────────────────────   │
│                                                                 │
│  ┌──────────────┬────────────────┬───────────┬────────────┐    │
│  │ 供应商        │ Key 后缀        │ RPM 限制   │ 操作        │    │
│  ├──────────────┼────────────────┼───────────┼────────────┤    │
│  │ OpenAI       │ ...ab12        │ 60        │ [更换]      │    │
│  │ Anthropic    │ ...cd34        │ 100       │ [更换]      │    │
│  │ 智谱         │ ...ef56        │ 60        │ [更换]      │    │
│  └──────────────┴────────────────┴───────────┴────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 User 界面

#### 个人设置页新增 "我的 Key 绑定"

```
┌─────────────────────────────────────────────────────────────────┐
│  个人设置                                                        │
├─────────────────────────────────────────────────────────────────┤
│  [账号信息] [我的平台 Key] [我的供应商绑定]                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  供应商 Key 绑定                                                 │
│  ────────────────────────────────────────────────────────────   │
│                                                                 │
│  您的请求默认使用以下供应商 Key（RPM 打满时自动切换到其他 Key）    │
│                                                                 │
│  ┌──────────────┬────────────────┬─────────────────────────┐   │
│  │ 供应商        │ Key 后缀        │ 说明                     │   │
│  ├──────────────┼────────────────┼─────────────────────────┤   │
│  │ OpenAI       │ ...ab12        │ 您的主 Key              │   │
│  │ Anthropic    │ ...cd34        │ 您的主 Key              │   │
│  └──────────────┴────────────────┴─────────────────────────┘   │
│                                                                 │
│  💡 提示：当您的请求超过 Key 的 RPM 限制时，系统会自动使用        │
│     其他可用的 Key，确保服务不中断。                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. 测试用例

### 8.1 单元测试

#### test_key_selector.py

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.key_selector import KeySelector
from services.rpm_tracker import RPMTracker
from models.user import User
from models.provider import Provider
from models.provider_api_key import ProviderApiKey

class TestKeySelector:

    @pytest.fixture
    def rpm_tracker(self):
        return RPMTracker()

    @pytest.fixture
    def key_selector(self, db_session, rpm_tracker):
        return KeySelector(db_session, rpm_tracker)

    async def test_select_primary_key_when_available(
        self, key_selector, test_user, db_session
    ):
        """Primary Key 有额度时，应该使用 Primary Key"""
        # Setup: 创建供应商和 Key
        provider = Provider(name="openai", display_name="OpenAI")
        db_session.add(provider)
        await db_session.commit()

        key = ProviderApiKey(
            provider_id=provider.id,
            encrypted_key="encrypted",
            key_suffix="ab12",
            rpm_limit=60,
            status="active"
        )
        db_session.add(key)
        await db_session.commit()

        # 绑定到用户
        test_user.primary_provider_keys = {"openai": str(key.id)}
        await db_session.commit()

        # Act
        selected = await key_selector.select_key(
            test_user.id, "openai", "gpt-4o"
        )

        # Assert
        assert selected.id == key.id

    async def test_overflow_when_primary_rate_limited(
        self, key_selector, test_user, db_session, rpm_tracker
    ):
        """Primary Key 无额度时，应该溢出到其他 Key"""
        # Setup: 创建两个 Key
        provider = Provider(name="openai")
        db_session.add(provider)
        await db_session.commit()

        primary_key = ProviderApiKey(
            provider_id=provider.id,
            encrypted_key="enc1",
            key_suffix="ab12",
            rpm_limit=2,  # 很低的限制
            status="active"
        )
        overflow_key = ProviderApiKey(
            provider_id=provider.id,
            encrypted_key="enc2",
            key_suffix="cd34",
            rpm_limit=60,
            status="active"
        )
        db_session.add_all([primary_key, overflow_key])
        await db_session.commit()

        test_user.primary_provider_keys = {"openai": str(primary_key.id)}
        await db_session.commit()

        # 用完 Primary Key 的额度
        await rpm_tracker.check_and_consume(str(primary_key.id), 2)
        await rpm_tracker.check_and_consume(str(primary_key.id), 2)

        # Act
        selected = await key_selector.select_key(
            test_user.id, "openai", "gpt-4o"
        )

        # Assert: 应该是 overflow_key
        assert selected.id == overflow_key.id

    async def test_all_keys_rate_limited(
        self, key_selector, test_user, db_session, rpm_tracker
    ):
        """所有 Key 都无额度时，应该抛出 RateLimitExceededError"""
        # Setup
        provider = Provider(name="openai")
        db_session.add(provider)
        await db_session.commit()

        key = ProviderApiKey(
            provider_id=provider.id,
            encrypted_key="enc",
            key_suffix="ab12",
            rpm_limit=1,
            status="active"
        )
        db_session.add(key)
        await db_session.commit()

        test_user.primary_provider_keys = {"openai": str(key.id)}
        await db_session.commit()

        # 用完额度
        await rpm_tracker.check_and_consume(str(key.id), 1)

        # Act & Assert
        with pytest.raises(RateLimitExceededError):
            await key_selector.select_key(test_user.id, "openai", "gpt-4o")

    async def test_no_primary_key_fallback_to_any_active(
        self, key_selector, test_user, db_session
    ):
        """用户没有 Primary Key 时，应该选择任意活跃 Key"""
        provider = Provider(name="openai")
        db_session.add(provider)
        await db_session.commit()

        key = ProviderApiKey(
            provider_id=provider.id,
            encrypted_key="enc",
            key_suffix="ab12",
            rpm_limit=60,
            status="active"
        )
        db_session.add(key)
        await db_session.commit()

        # 用户没有绑定 Primary Key
        test_user.primary_provider_keys = {}
        await db_session.commit()

        # Act
        selected = await key_selector.select_key(
            test_user.id, "openai", "gpt-4o"
        )

        # Assert
        assert selected.id == key.id
```

### 8.2 集成测试

#### test_key_assignment.py

```python
class TestKeyAssignment:

    async def test_auto_assign_on_user_registration(self, client):
        """新用户注册时应自动分配 Primary Key"""
        # Setup: 先创建供应商和 Key
        # ...

        # Act: 注册新用户
        response = await client.post("/api/auth/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "password123"
        })

        # Assert: 用户应该有 Primary Key 绑定
        user_data = response.json()
        assert "primary_provider_keys" in user_data
        assert "openai" in user_data["primary_provider_keys"]

    async def test_rebalance_on_key_added(self, admin_client):
        """新增 Key 后重新平衡，用户应该均匀分布"""
        # ...

    async def test_rebalance_api(self, admin_client):
        """Admin 可以手动触发重新平衡"""
        response = await admin_client.post(
            "/api/admin/providers/openai/rebalance-keys"
        )
        assert response.status_code == 200
```

### 8.3 E2E 测试

```python
class TestGatewayWithKeyAllocation:

    async def test_request_uses_primary_key(self, client, user_api_key):
        """请求应该使用用户的 Primary Key"""
        # ...

    async def test_overflow_visible_in_response(self, client, user_api_key):
        """溢出应该在响应的 x_ltm 中体现"""
        # Setup: 让 Primary Key 达到 RPM 限制
        # ...

        # Act
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {user_api_key}"},
            json={"model": "gpt-4o", "messages": [...]}
        )

        # Assert
        x_ltm = response.json().get("x_ltm", {})
        assert x_ltm["key_source"] == "overflow"
```

---

## 9. 实现计划

### Phase 1: 核心逻辑（2天）

| 任务 | 预估时间 |
|------|----------|
| RPMTracker 服务实现 | 2h |
| KeySelector 重构 | 3h |
| KeyAssignmentService 实现 | 3h |
| 单元测试编写 | 4h |
| 集成测试编写 | 2h |

### Phase 2: 数据模型与 API（1天）

| 任务 | 预估时间 |
|------|----------|
| User 表扩展 + 迁移 | 1h |
| Admin API 实现 | 2h |
| User API 实现 | 1h |
| Gateway 响应扩展 | 2h |
| API 测试 | 2h |

### Phase 3: 前端界面（1天）

| 任务 | 预估时间 |
|------|----------|
| Admin Key 分配页面 | 3h |
| User 绑定展示页面 | 2h |
| E2E 测试 | 2h |
| 文档更新 | 1h |

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 内存 RPM 追踪在重启后丢失 | 低 | 重启后计数器归零，不影响功能正确性 |
| 多实例部署时 RPM 计数不准 | 中 | MVP 阶段单实例，后续支持 Redis |
| Key 分配不均匀（用户活跃度差异） | 中 | 溢出机制自动平衡，无需人工干预 |
| 用户对 Primary Key 概念困惑 | 低 | 前端清晰展示，提示溢出机制 |

---

## 11. 基于历史 RPM 的加权重平衡

### 11.1 问题分析

当前的重平衡策略按用户数均分，假设所有用户活跃度相同：

```
问题场景：
- Key 1: 10 用户（其中 5 个高频用户，各 50 RPM）→ 实际负载 250 RPM，频繁 429
- Key 2: 10 用户（其中 1 个高频用户）→ 实际负载 100 RPM，大量闲置
```

### 11.2 解决方案：加权分配

根据用户历史 RPM 统计，计算每个 Key 的预期负载，实现负载均衡。

### 11.3 数据模型扩展

```python
# models/user_rpm_stats.py

class UserRPMStats(Base):
    """用户 RPM 统计表 - 按供应商维度"""
    __tablename__ = "user_rpm_stats"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider_name: Mapped[str] = mapped_column(index=True)  # openai, anthropic, etc.

    # 统计数据（滑动窗口）
    avg_rpm: Mapped[float] = mapped_column(default=0.0)     # 过去 7 天的平均 RPM
    peak_rpm: Mapped[int] = mapped_column(default=0)        # 观察到的峰值 RPM
    total_requests: Mapped[int] = mapped_column(default=0)  # 累计请求数

    # 时间戳
    window_start: Mapped[datetime]  # 统计窗口起始时间
    updated_at: Mapped[datetime]    # 最后更新时间

    __table_args__ = (
        UniqueConstraint("user_id", "provider_name", name="uq_user_provider_stats"),
    )
```

### 11.4 统计数据收集

```python
# services/rpm_stats_collector.py

class RPMStatsCollector:
    """
    RPM 统计收集器

    定时任务：每日凌晨统计过去 7 天的用户 RPM 数据
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def collect_user_rpm_stats(self, provider_name: str):
        """
        从 request_logs 聚合用户 RPM 统计

        计算逻辑：
        1. 查询过去 7 天的 request_logs
        2. 按 user_id + provider 分组
        3. 计算每分钟平均请求数、峰值等
        """
        window_start = datetime.utcnow() - timedelta(days=7)

        # 按用户统计过去 7 天的请求分布
        query = (
            select(
                RequestLog.user_id,
                func.count(RequestLog.id).label("total_requests"),
                # 按分钟分组后的平均请求数
                func.avg(func.count(RequestLog.id)).over().label("avg_rpm"),
            )
            .where(RequestLog.provider == provider_name)
            .where(RequestLog.created_at >= window_start)
            .group_by(RequestLog.user_id, text("date_trunc('minute', created_at)"))
        )

        result = await self.db.execute(query)
        # ... 聚合并更新 user_rpm_stats 表
```

### 11.5 加权重平衡算法

```python
# services/key_assignment.py (扩展)

class KeyAssignmentService:

    async def rebalance_provider_weighted(
        self,
        provider_name: str,
        strategy: str = "avg_rpm"  # "avg_rpm" | "peak_rpm" | "hybrid"
    ):
        """
        基于用户历史 RPM 的加权重平衡

        Args:
            provider_name: 供应商名称
            strategy: 负载计算策略
                - avg_rpm: 使用平均 RPM
                - peak_rpm: 使用峰值 RPM（更保守）
                - hybrid: 0.7 * avg + 0.3 * peak

        目标：让每个 Key 的预期负载相近，而非用户数相近
        """
        keys = await self._get_active_keys(provider_name)
        users_with_stats = await self._get_users_with_rpm_stats(provider_name)

        if not keys or not users_with_stats:
            return {"message": "No keys or users to rebalance"}

        # 计算每个用户的权重
        def get_weight(user_stats: UserRPMStats) -> float:
            if strategy == "avg_rpm":
                return user_stats.avg_rpm
            elif strategy == "peak_rpm":
                return float(user_stats.peak_rpm)
            else:  # hybrid
                return 0.7 * user_stats.avg_rpm + 0.3 * user_stats.peak_rpm

        # 按权重降序排列（高活跃用户优先分配）
        sorted_users = sorted(
            users_with_stats,
            key=lambda u: get_weight(u) if u else 0.0,
            reverse=True
        )

        # 追踪每个 Key 的当前负载
        key_loads = {str(k.id): 0.0 for k in keys}
        key_user_counts = {str(k.id): 0 for k in keys}

        # 贪心算法：每次把用户分配给当前负载最低的 Key
        for user, stats in sorted_users:
            weight = get_weight(stats) if stats else 0.0

            # 找负载最低的 Key
            best_key_id = min(key_loads, key=key_loads.get)

            # 更新分配
            user.primary_provider_keys = user.primary_provider_keys or {}
            user.primary_provider_keys[provider_name] = best_key_id

            key_loads[best_key_id] += weight
            key_user_counts[best_key_id] += 1

        await self.db.commit()

        return {
            "message": "Weighted rebalance completed",
            "strategy": strategy,
            "total_users": len(sorted_users),
            "key_loads": key_loads,
            "key_user_counts": key_user_counts
        }

    async def _get_users_with_rpm_stats(
        self,
        provider_name: str
    ) -> list[tuple[User, Optional[UserRPMStats]]]:
        """获取用户及其 RPM 统计"""
        query = (
            select(User, UserRPMStats)
            .outerjoin(
                UserRPMStats,
                and_(
                    UserRPMStats.user_id == User.id,
                    UserRPMStats.provider_name == provider_name
                )
            )
        )
        result = await self.db.execute(query)
        return result.all()
```

### 11.6 分配效果对比

**场景**：50 用户，5 个 Key（每个 RPM 限制 60）

| 指标 | 均分策略 | 加权策略 (avg_rpm) |
|------|----------|-------------------|
| Key 1 | 10 用户 / 180 RPM ❌ | 6 用户 / 78 RPM ✅ |
| Key 2 | 10 用户 / 45 RPM | 7 用户 / 82 RPM ✅ |
| Key 3 | 10 用户 / 60 RPM | 8 用户 / 80 RPM ✅ |
| Key 4 | 10 用户 / 30 RPM | 9 用户 / 78 RPM ✅ |
| Key 5 | 10 用户 / 75 RPM | 10 用户 / 82 RPM ✅ |
| **负载标准差** | 54.3 | 1.8 |

### 11.7 周期性重平衡配置

```python
# config.py 或环境变量

REBALANCE_CONFIG = {
    "schedule": "0 3 * * 0",      # 每周日凌晨 3 点执行
    "strategy": "hybrid",          # avg_rpm | peak_rpm | hybrid
    "min_requests_for_stats": 100, # 统计有效性的最小请求数
    "stats_window_days": 7,        # 统计窗口
    "dry_run": False,              # True 时只返回预览，不实际执行
}
```

### 11.8 API 扩展

#### POST `/api/admin/providers/{provider_name}/rebalance-keys`

**请求体（扩展）**：
```json
{
  "strategy": "hybrid",
  "dry_run": true
}
```

**响应（dry_run=true 时）**：
```json
{
  "dry_run": true,
  "current_assignments": {
    "key_1": {"users": 10, "load": 180},
    "key_2": {"users": 10, "load": 45}
  },
  "proposed_assignments": {
    "key_1": {"users": 6, "load": 78},
    "key_2": {"users": 7, "load": 82}
  },
  "affected_users": ["user_id_1", "user_id_2"]
}
```

### 11.9 平滑过渡策略

重平衡后，给用户一个"宽限期"，避免立即强制切换：

```python
class KeyAssignmentService:

    async def rebalance_provider_weighted(self, provider_name: str):
        # ... 分配逻辑 ...

        # 记录重平衡时间，用于宽限期判断
        for user in affected_users:
            user.key_rebalanced_at = datetime.utcnow()
            user.previous_primary_key = old_key_id  # 保留旧 Key 引用

        await self.db.commit()
```

```python
# services/key_selector.py (扩展)

async def select_key(self, user_id: UUID, provider_name: str, model_id: str):
    primary_key = await self._get_user_primary_key(user_id, provider_name)

    # 宽限期逻辑：24 小时内优先使用旧 Key（如果仍有额度）
    if primary_key and await self._is_in_grace_period(user_id):
        old_key = await self._get_previous_primary_key(user_id, provider_name)
        if old_key and await self.rpm_tracker.check_and_consume(old_key.id, old_key.rpm_limit):
            return old_key

    # 正常逻辑...
```

### 11.10 极端情况处理

```python
async def rebalance_provider_weighted(self, provider_name: str):
    for user, stats in sorted_users:
        weight = get_weight(stats) if stats else 0.0

        # 极端值处理：单用户 RPM > 单 Key 限制
        if weight > max(k.rpm_limit for k in keys):
            # 标记为"超限用户"，强制使用溢出机制
            user.is_over_limit = True
            logger.warning(
                f"User {user.id} avg_rpm ({weight}) exceeds all key limits, "
                "will rely on overflow mechanism"
            )

        # 正常分配...
```

---

## 12. 后续优化（非 MVP）

1. **Redis RPM 追踪**：支持多实例部署
2. **Key 健康检查**：自动禁用失效的 Key
3. **加权分配**：根据 Key 的 RPM 限制按比例分配用户（已在上文第 11 节详细说明）
4. **成本报表**：按 Primary Key 维度生成成本分摊报表
5. **用户自助切换**：允许用户自己选择 Primary Key（在合理范围内）
6. **智能预测**：基于时间序列预测用户未来 RPM，提前调整分配
