"""
供应商 Key 分配服务

提供：
- 新用户自动分配 Primary Key
- Key 重新平衡
- 手动设置 Primary Key
- 分配统计
"""
import uuid
import json
from typing import Dict, List, Optional
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm.attributes import flag_modified

from models.user import User
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus


class KeyAssignmentStats:
    """Key 分配统计"""
    def __init__(
        self,
        key_id: uuid.UUID,
        key_suffix: str,
        rpm_limit: int,
        assigned_users: int
    ):
        self.key_id = key_id
        self.key_suffix = key_suffix
        self.rpm_limit = rpm_limit
        self.assigned_users = assigned_users

    def to_dict(self) -> dict:
        return {
            "key_id": str(self.key_id),
            "key_suffix": self.key_suffix,
            "rpm_limit": self.rpm_limit,
            "assigned_users": self.assigned_users
        }


class KeyAssignmentService:
    """Key 分配服务"""

    @staticmethod
    async def assign_primary_keys_for_new_user(
        user_id: uuid.UUID,
        db: AsyncSession
    ) -> Dict[str, str]:
        """
        为新用户自动分配所有供应商的 Primary Key

        选择策略：为每个供应商选择当前分配用户最少的 standard Key

        Args:
            user_id: 新用户 ID
            db: 数据库 session

        Returns:
            分配结果: {"openai": "key-uuid", "anthropic": "key-uuid", ...}
        """
        # 获取所有启用的供应商
        result = await db.execute(
            select(Provider).where(Provider.enabled == True)
        )
        providers = result.scalars().all()

        assignments = {}

        for provider in providers:
            # 为每个供应商选择最少用户的 Key
            key_id = await KeyAssignmentService._select_least_loaded_key(
                provider.id, db
            )
            if key_id:
                assignments[provider.name] = str(key_id)

        # 更新用户的 primary_provider_keys
        if assignments:
            await KeyAssignmentService._update_user_primary_keys(
                user_id, assignments, db
            )

        return assignments

    @staticmethod
    async def _select_least_loaded_key(
        provider_id: uuid.UUID,
        db: AsyncSession
    ) -> Optional[uuid.UUID]:
        """
        选择当前分配用户最少的 Key

        Args:
            provider_id: 供应商 ID
            db: 数据库 session

        Returns:
            Key ID，如果没有可用的 Key 则返回 None
        """
        # 获取该供应商所有活跃的 Key（不区分类型）
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.provider_id == provider_id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
                )
            ).order_by(ProviderApiKey.created_at)
        )
        keys = result.scalars().all()

        if not keys:
            return None

        # 如果只有一个 Key，直接返回
        if len(keys) == 1:
            return keys[0].id

        # 统计每个 Key 当前分配的用户数
        key_user_counts = {}
        for key in keys:
            key_user_counts[str(key.id)] = 0

        # 查询所有用户的 primary_provider_keys
        result = await db.execute(
            select(User).where(User.primary_provider_keys.isnot(None))
        )
        users = result.scalars().all()

        # 获取供应商名称
        result = await db.execute(
            select(Provider).where(Provider.id == provider_id)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            return keys[0].id

        for user in users:
            if user.primary_provider_keys:
                key_id = user.primary_provider_keys.get(provider.name)
                if key_id and key_id in key_user_counts:
                    key_user_counts[key_id] += 1

        # 选择用户最少的 Key
        min_key_id = min(key_user_counts.keys(), key=lambda k: key_user_counts[k])
        return uuid.UUID(min_key_id)

    @staticmethod
    async def _update_user_primary_keys(
        user_id: uuid.UUID,
        assignments: Dict[str, str],
        db: AsyncSession
    ):
        """
        更新用户的 primary_provider_keys

        Args:
            user_id: 用户 ID
            assignments: 分配映射
            db: 数据库 session
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        # 合并现有绑定（创建新字典确保 SQLAlchemy 检测到变更）
        current = dict(user.primary_provider_keys or {})
        current.update(assignments)
        user.primary_provider_keys = current
        flag_modified(user, "primary_provider_keys")

        await db.commit()

    @staticmethod
    async def set_user_primary_key(
        user_id: uuid.UUID,
        provider_name: str,
        key_id: uuid.UUID,
        db: AsyncSession
    ) -> bool:
        """
        手动设置用户的 Primary Key

        Args:
            user_id: 用户 ID
            provider_name: 供应商名称
            key_id: Key ID
            db: 数据库 session

        Returns:
            是否成功

        Raises:
            ValueError: Key 不存在或不属于该供应商
        """
        # 验证供应商存在
        result = await db.execute(
            select(Provider).where(Provider.name == provider_name)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise ValueError(f"Provider '{provider_name}' not found")

        # 验证 Key 存在且属于该供应商（不区分类型）
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.id == key_id,
                    ProviderApiKey.provider_id == provider.id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
                )
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            raise ValueError(
                f"Key {key_id} not found or not active for provider '{provider_name}'"
            )

        # 更新用户的 primary_provider_keys
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        current = dict(user.primary_provider_keys or {})
        current[provider_name] = str(key_id)
        user.primary_provider_keys = current
        flag_modified(user, "primary_provider_keys")

        await db.commit()
        return True

    @staticmethod
    async def rebalance_provider(
        provider_name: str,
        db: AsyncSession
    ) -> Dict[str, int]:
        """
        重新平衡供应商的 Key 分配

        1. 为未绑定该供应商的用户分配 Key
        2. 将用户均匀分布到各个 Key 上

        Args:
            provider_name: 供应商名称
            db: 数据库 session

        Returns:
            {"total_users": N, "keys": M, "reassigned": K, "newly_assigned": J}
        """
        # 获取供应商
        result = await db.execute(
            select(Provider).where(Provider.name == provider_name)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise ValueError(f"Provider '{provider_name}' not found")

        # 获取该供应商的所有活跃 Key（不区分类型）
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.provider_id == provider.id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
                )
            ).order_by(ProviderApiKey.created_at)
        )
        keys = list(result.scalars().all())

        if not keys:
            return {"total_users": 0, "keys": 0, "reassigned": 0, "newly_assigned": 0}

        # 获取所有用户
        result = await db.execute(
            select(User)
        )
        all_users = result.scalars().all()

        # 分类用户：已绑定 vs 未绑定
        users_with_binding = []
        users_without_binding = []

        for user in all_users:
            bound_key = None
            if user.primary_provider_keys:
                bound_key = user.primary_provider_keys.get(provider_name)
            if bound_key:
                users_with_binding.append(user)
            else:
                users_without_binding.append(user)

        # 初始化 Key 分配计数
        key_assignments = {str(k.id): 0 for k in keys}

        # 统计当前已绑定用户的 Key 分布
        for user in users_with_binding:
            bound_key = user.primary_provider_keys.get(provider_name)
            if bound_key in key_assignments:
                key_assignments[bound_key] += 1

        newly_assigned = 0
        reassigned = 0

        # 为未绑定用户分配 Key
        for user in users_without_binding:
            # 选择当前分配最少的 Key
            min_key = min(key_assignments.keys(), key=lambda k: key_assignments[k])

            current = dict(user.primary_provider_keys or {})
            current[provider_name] = min_key
            user.primary_provider_keys = current
            flag_modified(user, "primary_provider_keys")
            newly_assigned += 1
            key_assignments[min_key] += 1

        # 如果有多个 Key，对已绑定用户进行重平衡
        if len(keys) > 1:
            # 计算目标分布
            total_users = len(users_with_binding) + newly_assigned
            users_per_key = total_users // len(keys)
            extra = total_users % len(keys)

            # 重新计算目标分配
            target_assignments = {}
            for i, key in enumerate(keys):
                target_assignments[str(key.id)] = users_per_key + (1 if i < extra else 0)

            # 重置计数为实际绑定数（包括新分配的）
            key_assignments = {str(k.id): 0 for k in keys}

            # 对所有用户重新分配
            all_bound_users = users_with_binding + users_without_binding
            for user in all_bound_users:
                if not user.primary_provider_keys:
                    continue

                old_key = user.primary_provider_keys.get(provider_name)

                # 选择当前分配最少的 Key
                min_key = min(key_assignments.keys(), key=lambda k: key_assignments[k])

                if old_key != min_key:
                    current = dict(user.primary_provider_keys or {})
                    current[provider_name] = min_key
                    user.primary_provider_keys = current
                    flag_modified(user, "primary_provider_keys")
                    if user in users_with_binding:
                        reassigned += 1

                key_assignments[min_key] += 1

        await db.commit()

        return {
            "total_users": len(users_with_binding) + newly_assigned,
            "keys": len(keys),
            "reassigned": reassigned,
            "newly_assigned": newly_assigned
        }

    @staticmethod
    async def get_key_assignment_stats(
        provider_name: str,
        db: AsyncSession
    ) -> List[KeyAssignmentStats]:
        """
        获取供应商的 Key 分配统计

        Args:
            provider_name: 供应商名称
            db: 数据库 session

        Returns:
            每个 Key 的分配统计列表（包含所有类型的 key）
        """
        # 获取供应商
        result = await db.execute(
            select(Provider).where(Provider.name == provider_name)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise ValueError(f"Provider '{provider_name}' not found")

        # 获取该供应商的所有活跃 Key（不限类型）
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.provider_id == provider.id,
                    ProviderApiKey.status == ProviderKeyStatus.ACTIVE.value
                )
            ).order_by(ProviderApiKey.created_at)
        )
        keys = result.scalars().all()

        # 统计每个 Key 分配的用户数
        key_user_counts = {str(k.id): 0 for k in keys}

        result = await db.execute(
            select(User).where(User.primary_provider_keys.isnot(None))
        )
        users = result.scalars().all()

        for user in users:
            if user.primary_provider_keys:
                key_id = user.primary_provider_keys.get(provider_name)
                if key_id and key_id in key_user_counts:
                    key_user_counts[key_id] += 1

        # 构建统计结果
        stats = []
        for key in keys:
            stats.append(KeyAssignmentStats(
                key_id=key.id,
                key_suffix=key.key_suffix,
                rpm_limit=key.rpm_limit,
                assigned_users=key_user_counts[str(key.id)]
            ))

        return stats

    @staticmethod
    async def get_user_primary_keys(
        user_id: uuid.UUID,
        db: AsyncSession
    ) -> Dict[str, Optional[dict]]:
        """
        获取用户的 Primary Key 绑定信息

        Args:
            user_id: 用户 ID
            db: 数据库 session

        Returns:
            {"openai": {"key_id": "...", "key_suffix": "..."}, ...}
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user or not user.primary_provider_keys:
            return {}

        primary_keys = {}
        for provider_name, key_id_str in user.primary_provider_keys.items():
            try:
                key_id = uuid.UUID(key_id_str)
                # 获取 Key 详情
                result = await db.execute(
                    select(ProviderApiKey).where(ProviderApiKey.id == key_id)
                )
                key = result.scalar_one_or_none()
                if key and key.status == ProviderKeyStatus.ACTIVE.value:
                    primary_keys[provider_name] = {
                        "key_id": str(key.id),
                        "key_suffix": key.key_suffix,
                        "rpm_limit": key.rpm_limit
                    }
                else:
                    primary_keys[provider_name] = None
            except (ValueError, TypeError):
                primary_keys[provider_name] = None

        return primary_keys

    @staticmethod
    async def remove_deleted_key_from_assignments(
        key_id: uuid.UUID,
        db: AsyncSession
    ) -> int:
        """
        从所有用户的绑定中移除已删除的 Key

        Args:
            key_id: 被删除的 Key ID
            db: 数据库 session

        Returns:
            受影响的用户数
        """
        key_id_str = str(key_id)
        affected = 0

        result = await db.execute(
            select(User).where(User.primary_provider_keys.isnot(None))
        )
        users = list(result.scalars().all())

        for user in users:
            if user.primary_provider_keys:
                modified = False
                new_keys = dict(user.primary_provider_keys)
                for provider_name, bound_key_id in list(new_keys.items()):
                    if bound_key_id == key_id_str:
                        del new_keys[provider_name]
                        modified = True

                if modified:
                    user.primary_provider_keys = new_keys if new_keys else None
                    flag_modified(user, "primary_provider_keys")
                    affected += 1

        if affected > 0:
            await db.commit()

        return affected

    @staticmethod
    async def get_users_assigned_to_key(
        provider_name: str,
        key_id: uuid.UUID,
        db: AsyncSession
    ) -> List[dict]:
        """
        获取绑定到某个 Key 的所有用户

        Args:
            provider_name: 供应商名称
            key_id: Key ID
            db: 数据库 session

        Returns:
            绑定到该 Key 的用户列表
            [{"id": uuid, "username": str, "email": str}, ...]

        Raises:
            ValueError: 供应商不存在
        """
        # 验证供应商存在
        result = await db.execute(
            select(Provider).where(Provider.name == provider_name)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise ValueError(f"Provider '{provider_name}' not found")

        # 验证 Key 存在且属于该供应商
        result = await db.execute(
            select(ProviderApiKey).where(
                and_(
                    ProviderApiKey.id == key_id,
                    ProviderApiKey.provider_id == provider.id
                )
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            raise ValueError(f"Key {key_id} not found for provider '{provider_name}'")

        key_id_str = str(key_id)

        # 查询所有绑定了该 Key 的用户
        result = await db.execute(
            select(User).where(User.primary_provider_keys.isnot(None))
        )
        all_users = result.scalars().all()

        assigned_users = []
        for user in all_users:
            if user.primary_provider_keys:
                binding = user.primary_provider_keys.get(provider_name)

                # 支持新旧两种数据格式
                # 旧格式: {"provider": "key_id_str"}
                # 新格式: {"provider": {"key_id": "key_id_str"}}
                if binding == key_id_str:
                    # 旧格式
                    assigned_users.append({
                        "id": user.id,
                        "username": user.username,
                        "email": user.email
                    })
                elif isinstance(binding, dict) and binding.get("key_id") == key_id_str:
                    # 新格式
                    assigned_users.append({
                        "id": user.id,
                        "username": user.username,
                        "email": user.email
                    })

        return assigned_users
