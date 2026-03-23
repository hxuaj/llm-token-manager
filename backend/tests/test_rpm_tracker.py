"""
RPMTracker 服务测试

测试 RPM 追踪服务的核心功能：
- 原子性检查并消耗
- 获取当前使用量
- 获取剩余配额
- 重置功能
"""
import uuid
import pytest
import pytest_asyncio
import asyncio

from services.rpm_tracker import RPMTracker, get_rpm_tracker


@pytest_asyncio.fixture
async def rpm_tracker():
    """创建一个独立的 RPMTracker 实例用于测试"""
    # 创建新实例（不使用单例）
    tracker = RPMTracker.__new__(RPMTracker)
    tracker._initialized = False
    tracker.__init__()
    yield tracker
    # 清理
    await tracker.reset()


class TestRPMTracker:
    """RPMTracker 测试类"""

    @pytest.mark.asyncio
    async def test_check_and_consume_allows_under_limit(self, rpm_tracker):
        """测试在限制内允许请求"""
        key_id = uuid.uuid4()

        allowed, current_rpm, limit = await rpm_tracker.check_and_consume(key_id, 10)

        assert allowed is True
        assert current_rpm == 1
        assert limit == 10

    @pytest.mark.asyncio
    async def test_check_and_consume_blocks_at_limit(self, rpm_tracker):
        """测试达到限制时阻止请求"""
        key_id = uuid.uuid4()
        rpm_limit = 3

        # 消耗 3 次应该都成功
        for i in range(3):
            allowed, current_rpm, _ = await rpm_tracker.check_and_consume(key_id, rpm_limit)
            assert allowed is True
            assert current_rpm == i + 1

        # 第 4 次应该被阻止
        allowed, current_rpm, _ = await rpm_tracker.check_and_consume(key_id, rpm_limit)
        assert allowed is False
        assert current_rpm == 3

    @pytest.mark.asyncio
    async def test_unlimited_rpm(self, rpm_tracker):
        """测试 rpm_limit = 0 表示不限制"""
        key_id = uuid.uuid4()

        # rpm_limit = 0 表示不限制
        for _ in range(100):
            allowed, current_rpm, limit = await rpm_tracker.check_and_consume(key_id, 0)
            assert allowed is True
            assert current_rpm == 0  # 不跟踪
            assert limit == 0

    @pytest.mark.asyncio
    async def test_get_current_usage(self, rpm_tracker):
        """测试获取当前使用量"""
        key_id = uuid.uuid4()

        # 初始为 0
        usage = await rpm_tracker.get_current_usage(key_id)
        assert usage == 0

        # 消耗 5 次
        for _ in range(5):
            await rpm_tracker.check_and_consume(key_id, 10)

        usage = await rpm_tracker.get_current_usage(key_id)
        assert usage == 5

    @pytest.mark.asyncio
    async def test_get_remaining(self, rpm_tracker):
        """测试获取剩余配额"""
        key_id = uuid.uuid4()
        rpm_limit = 10

        # 初始剩余
        remaining = await rpm_tracker.get_remaining(key_id, rpm_limit)
        assert remaining == 10

        # 消耗 3 次
        for _ in range(3):
            await rpm_tracker.check_and_consume(key_id, rpm_limit)

        remaining = await rpm_tracker.get_remaining(key_id, rpm_limit)
        assert remaining == 7

    @pytest.mark.asyncio
    async def test_get_remaining_unlimited(self, rpm_tracker):
        """测试无限额时返回 -1"""
        key_id = uuid.uuid4()

        remaining = await rpm_tracker.get_remaining(key_id, 0)
        assert remaining == -1  # 无限制

    @pytest.mark.asyncio
    async def test_reset_single_key(self, rpm_tracker):
        """测试重置单个 Key"""
        key_id = uuid.uuid4()

        # 消耗几次
        for _ in range(5):
            await rpm_tracker.check_and_consume(key_id, 10)

        usage = await rpm_tracker.get_current_usage(key_id)
        assert usage == 5

        # 重置
        await rpm_tracker.reset(key_id)

        usage = await rpm_tracker.get_current_usage(key_id)
        assert usage == 0

    @pytest.mark.asyncio
    async def test_reset_all_keys(self, rpm_tracker):
        """测试重置所有 Key"""
        key_id_1 = uuid.uuid4()
        key_id_2 = uuid.uuid4()

        # 消耗
        await rpm_tracker.check_and_consume(key_id_1, 10)
        await rpm_tracker.check_and_consume(key_id_2, 10)

        # 重置所有
        await rpm_tracker.reset()

        assert await rpm_tracker.get_current_usage(key_id_1) == 0
        assert await rpm_tracker.get_current_usage(key_id_2) == 0

    @pytest.mark.asyncio
    async def test_different_keys_tracked_separately(self, rpm_tracker):
        """测试不同 Key 独立追踪"""
        key_id_1 = uuid.uuid4()
        key_id_2 = uuid.uuid4()

        # Key 1 消耗 3 次
        for _ in range(3):
            await rpm_tracker.check_and_consume(key_id_1, 10)

        # Key 2 消耗 5 次
        for _ in range(5):
            await rpm_tracker.check_and_consume(key_id_2, 10)

        assert await rpm_tracker.get_current_usage(key_id_1) == 3
        assert await rpm_tracker.get_current_usage(key_id_2) == 5

    @pytest.mark.asyncio
    async def test_concurrent_access(self, rpm_tracker):
        """测试并发访问的线程安全性"""
        key_id = uuid.uuid4()
        rpm_limit = 100

        async def consume():
            allowed, _, _ = await rpm_tracker.check_and_consume(key_id, rpm_limit)
            return allowed

        # 并发 50 次请求
        tasks = [consume() for _ in range(50)]
        results = await asyncio.gather(*tasks)

        # 所有请求都应该成功（限制是 100）
        assert all(results)

        # 使用量应该是 50
        usage = await rpm_tracker.get_current_usage(key_id)
        assert usage == 50

    @pytest.mark.asyncio
    async def test_get_tracked_keys(self, rpm_tracker):
        """测试获取追踪的 Key 列表"""
        key_id_1 = uuid.uuid4()
        key_id_2 = uuid.uuid4()

        # 初始为空
        tracked = rpm_tracker.get_tracked_keys()
        assert len(tracked) == 0

        # 消耗后
        await rpm_tracker.check_and_consume(key_id_1, 10)
        await rpm_tracker.check_and_consume(key_id_2, 10)

        tracked = rpm_tracker.get_tracked_keys()
        assert len(tracked) == 2
        assert key_id_1 in tracked
        assert key_id_2 in tracked


class TestRPMTrackerSingleton:
    """RPMTracker 单例测试"""

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self):
        """测试单例返回相同实例"""
        tracker1 = get_rpm_tracker()
        tracker2 = get_rpm_tracker()

        assert tracker1 is tracker2
