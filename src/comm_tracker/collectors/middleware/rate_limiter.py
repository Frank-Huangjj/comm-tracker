"""令牌桶限速器。"""

import asyncio
import time


class RateLimiter:
    """基于令牌桶算法的限速器，每个数据源独立限速。"""

    def __init__(self, rate: float = 0.5, burst: int = 3):
        """
        Args:
            rate: 每秒允许的请求数，默认 0.5（每 2 秒 1 个）
            burst: 突发请求数上限
        """
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """等待直到有可用令牌。"""
        async with self._lock:
            while self._tokens < 1:
                self._refill()
                if self._tokens < 1:
                    wait_time = (1 - self._tokens) / self.rate
                    await asyncio.sleep(wait_time)
                    self._refill()
            self._tokens -= 1

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_refill = now
