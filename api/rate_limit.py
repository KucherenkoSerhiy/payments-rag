"""Sliding-window rate limiting, framework-free; `api.guard` maps it to 429s."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class SlidingWindowLimiter:
    """Per-key sliding-window counter. `clock` is injectable for tests."""

    def __init__(
        self, limit: int, window_s: int = 3600, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = clock()
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int | None:
        """Count a hit and return None, or seconds to wait if the key is over the limit."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(self.window_s - (now - hits[0])) + 1)
            hits.append(now)
            self._maybe_sweep(now)
            return None

    def reset(self) -> None:
        """Forget all counted hits (tests; not needed in production)."""
        with self._lock:
            self._hits.clear()

    def _maybe_sweep(self, now: float) -> None:
        """Drop stale keys, at most once per window, to bound memory over months."""
        if now - self._last_sweep < self.window_s:
            return
        self._last_sweep = now
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] > self.window_s]
        for key in stale:
            del self._hits[key]
