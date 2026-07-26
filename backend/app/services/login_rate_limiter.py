from collections import deque
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable, Iterable


class LoginRateLimiter:
    """Small in-process guard for failed login bursts.

    CodeMind runs one backend process in the supplied Docker deployment.  The
    limiter deliberately has no database dependency, so it still protects the
    authentication endpoint while MySQL is under pressure.  A distributed
    deployment should replace it with a shared store such as Redis.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self._clock = clock
        self._max_keys = max(100, max_keys)
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def retry_after(
        self,
        keys: Iterable[tuple[str, int]],
        *,
        window_seconds: float,
    ) -> int:
        window = max(1.0, float(window_seconds))
        now = self._clock()
        with self._lock:
            self._prune(now, window)
            remaining = 0.0
            for key, limit in keys:
                if limit <= 0:
                    continue
                timestamps = self._attempts.get(key)
                if timestamps and len(timestamps) >= limit:
                    remaining = max(remaining, window - (now - timestamps[0]))
            return max(0, ceil(remaining))

    def record_failure(
        self,
        keys: Iterable[tuple[str, int]],
        *,
        window_seconds: float,
    ) -> None:
        window = max(1.0, float(window_seconds))
        now = self._clock()
        with self._lock:
            self._prune(now, window)
            for key, limit in keys:
                if limit <= 0:
                    continue
                self._attempts.setdefault(key, deque()).append(now)
            self._trim_to_max_keys()

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    def _prune(self, now: float, window_seconds: float) -> None:
        cutoff = now - window_seconds
        for key, timestamps in list(self._attempts.items()):
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if not timestamps:
                self._attempts.pop(key, None)

    def _trim_to_max_keys(self) -> None:
        overflow = len(self._attempts) - self._max_keys
        if overflow <= 0:
            return
        oldest_keys = sorted(
            self._attempts,
            key=lambda key: self._attempts[key][-1],
        )[:overflow]
        for key in oldest_keys:
            self._attempts.pop(key, None)


login_rate_limiter = LoginRateLimiter()
