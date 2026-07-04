import asyncio
import random
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx


@dataclass
class JobContext:
    job_id: uuid.UUID
    attempt: int
    queue_id: uuid.UUID
    handler: str


Handler = Callable[[dict[str, Any], JobContext], Awaitable[dict[str, Any]]]


async def sleep_handler(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    seconds = float(payload.get("seconds", 1))
    await asyncio.sleep(seconds)
    return {"slept_seconds": seconds}


async def http_call_handler(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    url = payload["url"]
    timeout = float(payload.get("timeout_sec", 10))
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
    result = await asyncio.to_thread(_fibonacci, n)
    return {"fib": result}


HANDLERS: dict[str, Handler] = {
    "sleep": sleep_handler,
    "http_call": http_call_handler,
    "fail_n_times": fail_n_times_handler,
    "flaky": flaky_handler,
    "compute": compute_handler,
}
