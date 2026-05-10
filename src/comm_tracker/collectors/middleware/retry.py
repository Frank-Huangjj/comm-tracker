"""指数退避重试处理器。"""

import asyncio
import logging
import random
from typing import Callable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 不重试的 HTTP 状态码
_NO_RETRY_STATUS = {400, 401, 403, 404, 405}


class RetryHandler:
    """带指数退避 + 随机抖动的重试。"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def execute(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """执行异步函数，失败时按策略重试。"""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _NO_RETRY_STATUS:
                    raise
                if e.response.status_code == 429:
                    # 429 额外等待
                    delay = self._delay(attempt) * 2
                else:
                    delay = self._delay(attempt)
                last_error = e
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                delay = self._delay(attempt)
                last_error = e

            if attempt < self.max_retries:
                logger.warning(
                    "请求失败（第 %d 次重试），%0.1f 秒后重试: %s",
                    attempt + 1,
                    delay,
                    last_error,
                )
                await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]

    def _delay(self, attempt: int) -> float:
        jitter = random.uniform(0, 1)
        delay = min(self.base_delay * (2 ** attempt) + jitter, self.max_delay)
        return delay
