"""
RPM (Requests Per Minute) 追踪服务

提供内存中的每分钟请求数追踪，用于：
- 追踪每个供应商 Key 的实时 RPM
- 支持原子性的检查并消耗操作
- 自动清理过期的计数器
"""
import asyncio
import time
from typing import Dict, Optional
from collections import defaultdict
import uuid


class RPMTracker:
    """
    RPM 追踪器（单例模式）

    使用滑动窗口追踪每个 Key 的每分钟请求数。
    线程安全，支持并发访问。
    """

    _instance: Optional["RPMTracker"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # key_id -> list of timestamps (within current minute window)
        self._request_timestamps: Dict[uuid.UUID, list] = defaultdict(list)
        # 每个 Key 的独立锁，避免全局锁竞争
        self._key_locks: Dict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
        # 清理间隔（秒）
        self._cleanup_interval = 60
        # 上次清理时间
        self._last_cleanup = time.time()

    async def _cleanup_if_needed(self):
        """清理过期的 timestamp 记录"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        cutoff = now - 60  # 保留最近 60 秒

        for key_id in list(self._request_timestamps.keys()):
            # 过滤掉过期的 timestamp
            self._request_timestamps[key_id] = [
                ts for ts in self._request_timestamps[key_id]
                if ts > cutoff
            ]
            # 如果列表为空，删除该 key 的记录
            if not self._request_timestamps[key_id]:
                del self._request_timestamps[key_id]
                if key_id in self._key_locks:
                    del self._key_locks[key_id]

    async def check_and_consume(
        self,
        key_id: uuid.UUID,
        rpm_limit: int
    ) -> tuple[bool, int, int]:
        """
        原子性检查并消耗一个请求配额

        Args:
            key_id: 供应商 Key ID
            rpm_limit: 该 Key 的 RPM 限制

        Returns:
            (是否允许, 当前 RPM, RPM 限制)
            - 如果 rpm_limit <= 0，表示不限制，直接返回 (True, current_rpm, 0)
        """
        if rpm_limit <= 0:
            # 不限制 RPM
            return True, 0, 0

        # 获取该 Key 的独立锁
        key_lock = self._key_locks[key_id]
        async with key_lock:
            now = time.time()
            cutoff = now - 60  # 1 分钟窗口

            # 清理过期的 timestamp
            self._request_timestamps[key_id] = [
                ts for ts in self._request_timestamps[key_id]
                if ts > cutoff
            ]

            # 当前 RPM
            current_rpm = len(self._request_timestamps[key_id])

            if current_rpm >= rpm_limit:
                # 超过限制
                return False, current_rpm, rpm_limit

            # 消耗一个配额
            self._request_timestamps[key_id].append(now)

            # 定期清理
            await self._cleanup_if_needed()

            return True, current_rpm + 1, rpm_limit

    async def get_current_usage(self, key_id: uuid.UUID) -> int:
        """
        获取指定 Key 的当前 RPM 使用量

        Args:
            key_id: 供应商 Key ID

        Returns:
            当前 RPM
        """
        key_lock = self._key_locks[key_id]
        async with key_lock:
            now = time.time()
            cutoff = now - 60

            # 过滤掉过期的 timestamp
            self._request_timestamps[key_id] = [
                ts for ts in self._request_timestamps[key_id]
                if ts > cutoff
            ]

            return len(self._request_timestamps[key_id])

    async def get_remaining(
        self,
        key_id: uuid.UUID,
        rpm_limit: int
    ) -> int:
        """
        获取指定 Key 的剩余 RPM 配额

        Args:
            key_id: 供应商 Key ID
            rpm_limit: RPM 限制

        Returns:
            剩余配额（如果 rpm_limit <= 0，返回 -1 表示无限制）
        """
        if rpm_limit <= 0:
            return -1  # 无限制

        current = await self.get_current_usage(key_id)
        remaining = rpm_limit - current
        return max(0, remaining)

    async def reset(self, key_id: Optional[uuid.UUID] = None):
        """
        重置指定 Key 或所有 Key 的计数器

        Args:
            key_id: 指定 Key ID，如果为 None 则重置所有
        """
        if key_id:
            key_lock = self._key_locks[key_id]
            async with key_lock:
                if key_id in self._request_timestamps:
                    del self._request_timestamps[key_id]
        else:
            async with self._lock:
                self._request_timestamps.clear()
                self._key_locks.clear()

    def get_tracked_keys(self) -> list[uuid.UUID]:
        """
        获取当前正在追踪的所有 Key ID

        Returns:
            Key ID 列表
        """
        return list(self._request_timestamps.keys())


# 全局单例
_rpm_tracker: Optional[RPMTracker] = None


def get_rpm_tracker() -> RPMTracker:
    """
    获取 RPMTracker 单例实例

    Returns:
        RPMTracker 实例
    """
    global _rpm_tracker
    if _rpm_tracker is None:
        _rpm_tracker = RPMTracker()
    return _rpm_tracker
