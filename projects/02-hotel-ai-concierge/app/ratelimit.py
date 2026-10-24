"""Per-guest rate limit: every message costs an LLM call, so cap how fast one chat can send."""

import time
from collections import defaultdict, deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window = window_s
        self._clock = clock
        self._hits: defaultdict[int, deque[float]] = defaultdict(deque)

    def allow(self, key: int) -> bool:
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True
