import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dispatcher import move_to_dlq
from app.models.enums import JobStatus, RetryStrategy
from app.models.job import Job
from app.models.retry_policy import RetryPolicy

DEFAULT_BASE_DELAY_SEC = 5
DEFAULT_MAX_DELAY_SEC = 300
DEFAULT_MAX_ATTEMPTS = 3


def compute_delay_sec(
    strategy: RetryStrategy,
    attempt: int,
    base_delay_sec: int,
    max_delay_sec: int,
    jitter_pct: float = 0.0,
) -> float:
    """Delay before retry attempt `n` (1-indexed: n=1 is the first retry,
    i.e. the delay applied after the 1st failed execution)."""
    if strategy == RetryStrategy.fixed:
        delay = float(base_delay_sec)
    elif strategy == RetryStrategy.linear:
        delay = float(base_delay_sec * attempt)
    elif strategy == RetryStrategy.exponential:
        delay = float(min(base_delay_sec * (2 ** (attempt - 1)), max_delay_sec))
    else:
        raise ValueError(f"Unknown retry strategy: {strategy}")

    delay = min(delay, float(max_delay_sec))

    if jitter_pct:
        jitter_range = delay * jitter_pct
        delay += random.uniform(-jitter_range, jitter_range)

    return max(delay, 0.0)


async def apply_failure(
    db: AsyncSession,
    job: Job,
    retry_policy: RetryPolicy | None,
    error_message: str,
) -> JobStatus:
    """Called after `job.attempts` has already been incremented for the
    execution attempt that just failed. Decides retry-with-backoff vs.
    permanent failure, applies the resulting transition on `job`, and
    returns the resulting status. Does not commit."""
    if job.attempts >= job.max_attempts:
        await move_to_dlq(db, job, final_error=error_message)
        return JobStatus.dead

    strategy = retry_policy.strategy if retry_policy else RetryStrategy.fixed
    base_delay_sec = retry_policy.base_delay_sec if retry_policy else DEFAULT_BASE_DELAY_SEC
    max_delay_sec = retry_policy.max_delay_sec if retry_policy else DEFAULT_MAX_DELAY_SEC
    jitter_pct = retry_policy.jitter_pct if retry_policy else 0.0

    delay = compute_delay_sec(strategy, job.attempts, base_delay_sec, max_delay_sec, jitter_pct)

    job.status = JobStatus.retrying
    job.run_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    job.worker_id = None
    job.lock_token = None
    return JobStatus.retrying
