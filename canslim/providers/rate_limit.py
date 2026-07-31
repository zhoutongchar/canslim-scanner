from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    """Space request starts so a semaphore cannot create upstream bursts."""

    def __init__(self, qps: float) -> None:
        self._interval = 1.0 / max(float(qps), 0.01)
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next_at - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.monotonic()
            self._next_at = max(self._next_at, now) + self._interval

    async def defer(self, seconds: float) -> None:
        """Push the next permitted request out after an upstream 429."""
        async with self._lock:
            self._next_at = max(self._next_at, time.monotonic() + max(seconds, 0.0))
