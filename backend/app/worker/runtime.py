import asyncio
import logging
from collections.abc import Coroutine

logger = logging.getLogger("pulse.worker")


class WorkerRuntime:
    """Bounds concurrently-running job tasks to `concurrency` and supports
    waiting for in-flight tasks to drain on graceful shutdown (§5.5)."""

    def __init__(self, concurrency: int):
        self.concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)
        self._running = 0
        self._tasks: set[asyncio.Task] = set()

    @property
    def running_count(self) -> int:
        return self._running

    @property
    def free_slots(self) -> int:
        return self.concurrency - self._running

    async def submit(self, coro: Coroutine) -> None:
        await self._sem.acquire()
        self._running += 1
        task = asyncio.create_task(self._run(coro))
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    async def _run(self, coro: Coroutine) -> None:
        try:
            await coro
        except Exception:
            logger.exception("unhandled error in job task")

    def _on_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        self._running -= 1
        self._sem.release()

    async def wait_for_idle(self, timeout: float) -> None:
        """Wait up to `timeout` for in-flight tasks to finish on their own.
        Uses asyncio.wait() rather than wait_for()/gather() deliberately:
        wait_for cancels the awaited coroutine when it times out, and that
        cancellation propagates down into every gathered task — silently
        killing a job that's still legitimately running (and mid-execution
        cancellation isn't caught by our `except Exception` in _execute,
        since CancelledError is a BaseException, so the job would be left
        stuck in 'running' with no failure recorded until the reaper
        eventually catches it). asyncio.wait() never cancels on timeout —
        it just reports which tasks are still pending so we can log an
        accurate count and let the process exit; those jobs simply get
        reaped once this worker's heartbeat goes stale."""
        if not self._tasks:
            return
        _done, pending = await asyncio.wait(self._tasks, timeout=timeout)
        if pending:
            logger.warning(
                "shutdown grace period exceeded with %d task(s) still in flight",
                len(pending),
            )
