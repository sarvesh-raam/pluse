import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class JobContext:
    job_id: uuid.UUID
    attempt: int
    queue_id: uuid.UUID
    handler: str


Handler = Callable[[dict[str, Any], JobContext], Awaitable[dict[str, Any]]]

# Payloads are user-supplied. Bound the demo handlers so one bad payload
# can't wedge a worker slot forever — compute runs in a thread, which can't
# be cancelled once started.
MAX_SLEEP_SEC = 3600.0
MAX_FIB_N = 100_000


async def sleep_handler(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    seconds = min(max(float(payload.get("seconds", 1)), 0.0), MAX_SLEEP_SEC)
    await asyncio.sleep(seconds)
    return {"slept_seconds": seconds}


async def http_call_handler(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    url = str(payload["url"])
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be http:// or https://")
    timeout = min(max(float(payload.get("timeout_sec", 10)), 0.1), 60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        return {"status_code": response.status_code}


async def fail_n_times_handler(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    """Fails deterministically on attempts 1..fail_until, then succeeds —
    proves retry -> backoff -> eventual success (or DLQ if max_attempts is
    lower than fail_until)."""
    fail_until = int(payload.get("fail_until", 1))
    if ctx.attempt <= fail_until:
        raise RuntimeError(f"deliberate failure on attempt {ctx.attempt} (fail_until={fail_until})")
    return {"succeeded_on_attempt": ctx.attempt}


async def flaky_handler(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    fail_rate = float(payload.get("fail_rate", 0.5))
    if random.random() < fail_rate:
        raise RuntimeError("flaky handler randomly failed")
    return {"ok": True}


def _fibonacci(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


async def compute_handler(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    n = int(payload.get("n", 30))
    if not 0 <= n <= MAX_FIB_N:
        raise ValueError(f"n must be between 0 and {MAX_FIB_N}")
    result = await asyncio.to_thread(_fibonacci, n)
    # fib(n) has ~0.2n digits; past a few thousand digits Python refuses to
    # even str() it (int max_str_digits), so report its size instead
    return {"fib": result} if n <= 1000 else {"fib_bits": result.bit_length()}


HANDLERS: dict[str, Handler] = {
    "sleep": sleep_handler,
    "http_call": http_call_handler,
    "fail_n_times": fail_n_times_handler,
    "flaky": flaky_handler,
    "compute": compute_handler,
}
