import time
import uuid


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
