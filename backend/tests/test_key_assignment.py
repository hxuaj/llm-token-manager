"""
KeyAssignmentService 测试

测试 Key 分配服务的核心功能：
- 新用户自动分配
- 重新平衡
- 手动设置
- 分配统计
"""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.user import User, UserRole
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus, KeyPlan
from services.key_assignment import KeyAssignmentService
from services.auth import hash_password


@pytest_asyncio.fixture
async def test_provider(db_session: AsyncSession):
    """创建一个测试供应商"""
    provider = Provider(
        name="test_provider",
        display_name="Test Provider",
        base_url="https://api.test.com",
        api_format="openai",
        enabled=True
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


@pytest_asyncio.fixture
async def test_provider_keys(test_provider: Provider, db_session: AsyncSession):
    """创建多个测试 Key"""
    from services.encryption import encrypt, extract_key_suffix

    keys = []
    for i in range(3):
        raw_key = f"sk-test-key-{i}-{uuid.uuid4().hex[:8]}"
        encrypted_key = encrypt(raw_key)
        key_suffix = extract_key_suffix(raw_key)

        key = ProviderApiKey(
            provider_id=test_provider.id,
            encrypted_key=encrypted_key,
            key_suffix=key_suffix,
            rpm_limit=60,
            status=ProviderKeyStatus.ACTIVE.value,
            key_plan=KeyPlan.STANDARD.value
        )
        db_session.add(key)
        keys.append(key)

    await db_session.commit()
    for key in keys:
        await db_session.refresh(key)
    return keys


@pytest_asyncio.fixture
async def test_users(db_session: AsyncSession):
    """创建多个测试用户"""
    users = []
    for i in range(5):
        user = User(
            username=f"testuser_{i}",
            email=f"testuser_{i}@example.com",
            password_hash=hash_password("testpassword123"),
            role=UserRole.USER,
            is_active=True
        )
        db_session.add(user)
        users.append(user)

    await db_session.commit()
    for user in users:
        await db_session.refresh(user)
    return users


class TestKeyAssignmentService:
    """KeyAssignmentService 测试类"""

    @pytest.mark.asyncio
    async def test_assign_primary_keys_for_new_user(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        db_session: AsyncSession
    ):
        """测试新用户自动分配 Primary Key"""
        # 创建新用户
        user = User(
            username="new_user",
            email="new_user@example.com",
            password_hash=hash_password("testpassword123"),
            role=UserRole.USER,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 分配 Primary Keys
        assignments = await KeyAssignmentService.assign_primary_keys_for_new_user(
            user.id, db_session
        )

        # 验证分配结果
        assert "test_provider" in assignments
        assigned_key_id = uuid.UUID(assignments["test_provider"])
        assert any(k.id == assigned_key_id for k in test_provider_keys)

        # 验证用户的 primary_provider_keys 已更新
        await db_session.refresh(user)
        assert user.primary_provider_keys is not None
        assert "test_provider" in user.primary_provider_keys

    @pytest.mark.asyncio
    async def test_assign_selects_least_loaded_key(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试选择负载最少的 Key"""
        # 为前两个用户绑定第一个 Key
        for user in test_users[:2]:
            user.primary_provider_keys = {"test_provider": str(test_provider_keys[0].id)}

        await db_session.commit()

        # 创建新用户
        new_user = User(
            username="new_user_least",
            email="new_user_least@example.com",
            password_hash=hash_password("testpassword123"),
            role=UserRole.USER,
            is_active=True
        )
        db_session.add(new_user)
        await db_session.commit()
        await db_session.refresh(new_user)

        # 分配
        assignments = await KeyAssignmentService.assign_primary_keys_for_new_user(
            new_user.id, db_session
        )

        # 应该分配到第二个或第三个 Key（负载最少）
        assigned_key_id = uuid.UUID(assignments["test_provider"])
        assert assigned_key_id in [test_provider_keys[1].id, test_provider_keys[2].id]

    @pytest.mark.asyncio
    async def test_set_user_primary_key(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试手动设置 Primary Key"""
        user = test_users[0]
        target_key = test_provider_keys[1]

        # 设置
        success = await KeyAssignmentService.set_user_primary_key(
            user.id, "test_provider", target_key.id, db_session
        )

        assert success is True

        # 验证
        await db_session.refresh(user)
        assert user.primary_provider_keys["test_provider"] == str(target_key.id)

    @pytest.mark.asyncio
    async def test_set_user_primary_key_invalid_provider(
        self,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试设置不存在的供应商"""
        user = test_users[0]

        with pytest.raises(ValueError, match="Provider.*not found"):
            await KeyAssignmentService.set_user_primary_key(
                user.id, "non_existent", test_provider_keys[0].id, db_session
            )

    @pytest.mark.asyncio
    async def test_set_user_primary_key_invalid_key(
        self,
        test_provider: Provider,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试设置不存在的 Key"""
        user = test_users[0]
        fake_key_id = uuid.uuid4()

        with pytest.raises(ValueError, match="Key.*not found"):
            await KeyAssignmentService.set_user_primary_key(
                user.id, "test_provider", fake_key_id, db_session
            )

    @pytest.mark.asyncio
    async def test_get_key_assignment_stats(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试获取分配统计"""
        # 绑定用户
        for i, user in enumerate(test_users[:3]):
            key_index = i % len(test_provider_keys)
            user.primary_provider_keys = {
                "test_provider": str(test_provider_keys[key_index].id)
            }

        await db_session.commit()

        # 获取统计
        stats = await KeyAssignmentService.get_key_assignment_stats(
            "test_provider", db_session
        )

        assert len(stats) == 3

        # 验证统计结果
        stats_dict = {str(s.key_id): s for s in stats}
        assert stats_dict[str(test_provider_keys[0].id)].assigned_users == 1
        assert stats_dict[str(test_provider_keys[1].id)].assigned_users == 1
        assert stats_dict[str(test_provider_keys[2].id)].assigned_users == 1

    @pytest.mark.asyncio
    async def test_get_key_assignment_stats_invalid_provider(
        self,
        db_session: AsyncSession
    ):
        """测试获取不存在供应商的统计"""
        with pytest.raises(ValueError, match="Provider.*not found"):
            await KeyAssignmentService.get_key_assignment_stats(
                "non_existent", db_session
            )

    @pytest.mark.asyncio
    async def test_rebalance_provider(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试重新平衡"""
        # 将所有用户绑定到第一个 Key
        for user in test_users:
            user.primary_provider_keys = {
                "test_provider": str(test_provider_keys[0].id)
            }

        await db_session.commit()

        # 重平衡
        result = await KeyAssignmentService.rebalance_provider("test_provider", db_session)

        assert result["total_users"] == 5
        assert result["keys"] == 3
        assert result["reassigned"] >= 0  # 可能有重分配

        # 验证分布更均匀
        stats = await KeyAssignmentService.get_key_assignment_stats(
            "test_provider", db_session
        )

        # 每个 Key 应该有 1-2 个用户
        for s in stats:
            assert s.assigned_users >= 1
            assert s.assigned_users <= 2

    @pytest.mark.asyncio
    async def test_rebalance_provider_invalid(
        self,
        db_session: AsyncSession
    ):
        """测试重新平衡不存在的供应商"""
        with pytest.raises(ValueError, match="Provider.*not found"):
            await KeyAssignmentService.rebalance_provider("non_existent", db_session)

    @pytest.mark.asyncio
    async def test_get_user_primary_keys(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试获取用户的 Primary Keys"""
        user = test_users[0]
        user.primary_provider_keys = {
            "test_provider": str(test_provider_keys[0].id)
        }
        await db_session.commit()

        primary_keys = await KeyAssignmentService.get_user_primary_keys(user.id, db_session)

        assert "test_provider" in primary_keys
        assert primary_keys["test_provider"]["key_id"] == str(test_provider_keys[0].id)
        assert primary_keys["test_provider"]["key_suffix"] == test_provider_keys[0].key_suffix

    @pytest.mark.asyncio
    async def test_get_user_primary_keys_deleted_key(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试获取已删除 Key 的情况"""
        user = test_users[0]
        # 绑定一个不存在的 Key
        user.primary_provider_keys = {
            "test_provider": str(uuid.uuid4())
        }
        await db_session.commit()

        primary_keys = await KeyAssignmentService.get_user_primary_keys(user.id, db_session)

        # 应该返回 None
        assert primary_keys.get("test_provider") is None

    @pytest.mark.asyncio
    async def test_remove_deleted_key_from_assignments(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试从用户绑定中移除已删除的 Key"""
        target_key = test_provider_keys[0]

        # 将多个用户绑定到这个 Key
        for user in test_users[:3]:
            user.primary_provider_keys = {
                "test_provider": str(target_key.id)
            }

        await db_session.commit()

        # 移除
        affected = await KeyAssignmentService.remove_deleted_key_from_assignments(
            target_key.id, db_session
        )

        assert affected == 3

        # 验证用户绑定已被清除
        for user in test_users[:3]:
            await db_session.refresh(user)
            assert "test_provider" not in (user.primary_provider_keys or {})

    @pytest.mark.asyncio
    async def test_rebalance_assigns_to_unassigned_users(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试重平衡时为未绑定用户分配 Key"""
        # 只绑定前2个用户，后3个用户没有绑定
        for user in test_users[:2]:
            user.primary_provider_keys = {
                "test_provider": str(test_provider_keys[0].id)
            }
        # 后3个用户保持未绑定状态（primary_provider_keys 为 None 或不包含 test_provider）

        await db_session.commit()

        # 重平衡
        result = await KeyAssignmentService.rebalance_provider("test_provider", db_session)

        # 应该处理所有5个用户
        assert result["total_users"] == 5
        assert result["keys"] == 3
        # 新分配的应该至少有3个（之前未绑定的用户）
        assert result["newly_assigned"] == 3

        # 验证所有用户现在都已绑定
        stats = await KeyAssignmentService.get_key_assignment_stats(
            "test_provider", db_session
        )

        # 总绑定用户数应该是5
        total_assigned = sum(s.assigned_users for s in stats)
        assert total_assigned == 5

        # 每个用户都应该有绑定
        for user in test_users:
            await db_session.refresh(user)
            assert user.primary_provider_keys is not None
            assert "test_provider" in user.primary_provider_keys

    @pytest.mark.asyncio
    async def test_rebalance_assigns_to_users_with_no_keys_field(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        db_session: AsyncSession
    ):
        """测试重平衡时为 primary_provider_keys 为 None 的用户分配 Key"""
        # 创建一个没有任何 Key 绑定的用户
        user = User(
            username="unassigned_user",
            email="unassigned@example.com",
            password_hash=hash_password("testpassword123"),
            role=UserRole.USER,
            is_active=True,
            primary_provider_keys=None  # 明确为 None
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 重平衡
        result = await KeyAssignmentService.rebalance_provider("test_provider", db_session)

        # 应该处理这个用户
        assert result["total_users"] == 1
        assert result["newly_assigned"] == 1

        # 验证用户已绑定
        await db_session.refresh(user)
        assert user.primary_provider_keys is not None
        assert "test_provider" in user.primary_provider_keys

    @pytest.mark.asyncio
    async def test_get_users_assigned_to_key(
        self,
        test_provider: Provider,
        test_provider_keys: list,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试获取绑定到某个 Key 的用户列表"""
        # 将前 3 个用户绑定到第一个 Key
        first_key = test_provider_keys[0]
        for user in test_users[:3]:
            user.primary_provider_keys = {
                "test_provider": str(first_key.id)
            }

        # 将后 2 个用户绑定到第二个 Key
        second_key = test_provider_keys[1]
        for user in test_users[3:]:
            user.primary_provider_keys = {
                "test_provider": str(second_key.id)
            }

        await db_session.commit()

        # 获取绑定到第一个 Key 的用户
        users = await KeyAssignmentService.get_users_assigned_to_key(
            "test_provider", first_key.id, db_session
        )

        assert len(users) == 3
        usernames = [u["username"] for u in users]
        assert "testuser_0" in usernames
        assert "testuser_1" in usernames
        assert "testuser_2" in usernames

        # 获取绑定到第二个 Key 的用户
        users = await KeyAssignmentService.get_users_assigned_to_key(
            "test_provider", second_key.id, db_session
        )

        assert len(users) == 2
        usernames = [u["username"] for u in users]
        assert "testuser_3" in usernames
        assert "testuser_4" in usernames

    @pytest.mark.asyncio
    async def test_get_users_assigned_to_key_invalid_provider(
        self,
        db_session: AsyncSession
    ):
        """测试获取不存在供应商的用户列表"""
        with pytest.raises(ValueError, match="Provider.*not found"):
            await KeyAssignmentService.get_users_assigned_to_key(
                "non_existent", uuid.uuid4(), db_session
            )

    @pytest.mark.asyncio
    async def test_get_users_assigned_to_key_invalid_key(
        self,
        test_provider: Provider,
        db_session: AsyncSession
    ):
        """测试获取不存在 Key 的用户列表"""
        with pytest.raises(ValueError, match="Key.*not found"):
            await KeyAssignmentService.get_users_assigned_to_key(
                "test_provider", uuid.uuid4(), db_session
            )

    @pytest.mark.asyncio
    async def test_rebalance_with_coding_plan_key(
        self,
        test_provider: Provider,
        test_users: list,
        db_session: AsyncSession
    ):
        """测试重平衡支持 CODING_PLAN 类型的 Key"""
        from services.encryption import encrypt, extract_key_suffix

        # 创建一个 CODING_PLAN 类型的 Key
        raw_key = f"sk-coding-plan-{uuid.uuid4().hex[:8]}"
        encrypted_key = encrypt(raw_key)
        key_suffix = extract_key_suffix(raw_key)

        coding_plan_key = ProviderApiKey(
            provider_id=test_provider.id,
            encrypted_key=encrypted_key,
            key_suffix=key_suffix,
            rpm_limit=60,
            status=ProviderKeyStatus.ACTIVE.value,
            key_plan=KeyPlan.CODING_PLAN.value
        )
        db_session.add(coding_plan_key)
        await db_session.commit()
        await db_session.refresh(coding_plan_key)

        # 重平衡
        result = await KeyAssignmentService.rebalance_provider("test_provider", db_session)

        # 应该处理所有用户，包括 CODING_PLAN 类型的 Key
        assert result["total_users"] == 5
        assert result["keys"] == 1  # 只有这一个 CODING_PLAN Key

        # 验证用户被分配到了 CODING_PLAN Key
        stats = await KeyAssignmentService.get_key_assignment_stats(
            "test_provider", db_session
        )
        assert len(stats) == 1
        assert stats[0].assigned_users == 5
        assert str(stats[0].key_id) == str(coding_plan_key.id)
