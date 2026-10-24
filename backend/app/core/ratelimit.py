import time
import uuid
from collections import deque


class TokenBucket:
    """Refills continuously at `rate_per_sec`, capped at `capacity` (default:
    one second's worth of tokens, so a queue can't burst past its configured
    rate even if the scheduler tick is delayed and several ticks' worth of
    due jobs pile up)."""

    def __init__(self, rate_per_sec: float, capacity: float | None = None):
        self.rate_per_sec = rate_per_sec
        self.capacity = capacity if capacity is not None else max(rate_per_sec, 1.0)
        self._tokens = self.capacity
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_sec)
        self._last_refill = now

    def take_available(self) -> int:
        """Consume and return however many whole tokens are currently available."""
        self._refill()
        n = int(self._tokens)
        self._tokens -= n
        return n


class RateLimiterRegistry:
    """Per-queue token buckets, keyed by queue_id. Lives for the lifetime of
    the scheduler process — in-memory is fine since only the scheduler
    promotes due jobs, so there's no cross-process state to share."""

    def __init__(self) -> None:
        self._buckets: dict[uuid.UUID, TokenBucket] = {}

    def take_available(self, queue_id: uuid.UUID, rate_per_sec: float) -> int:
        bucket = self._buckets.get(queue_id)
        if bucket is None or bucket.rate_per_sec != rate_per_sec:
            bucket = TokenBucket(rate_per_sec)
            self._buckets[queue_id] = bucket
        return bucket.take_available()


registry = RateLimiterRegistry()


class FailureLimiter:
    """Sliding-window limit on *failed* attempts per key (used for login:
    key = client IP + email). In-memory per API process — with N replicas an
    attacker gets N x the budget, which still turns an unbounded online
    password-guessing attack into a handful of tries per window."""

    def __init__(self, max_failures: int, window_sec: float, max_keys: int = 50_000):
        self.max_failures = max_failures
        self.window_sec = window_sec
        self.max_keys = max_keys
        self._failures: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures.get(key)
        if q is None:
            return deque()
        while q and now - q[0] > self.window_sec:
            q.popleft()
        if not q:
            del self._failures[key]
        return q

    def is_blocked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self.max_failures

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        if len(self._failures) >= self.max_keys:
            # bounded memory: drop the oldest-inserted key
            self._failures.pop(next(iter(self._failures)))
        q = self._prune(key, now)
        q.append(now)
        self._failures[key] = q

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


login_limiter = FailureLimiter(max_failures=10, window_sec=300)
