from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHANNEL = "pulse_jobs"


async def notify_jobs_available(db: AsyncSession) -> None:
    """§10 bonus: event-driven execution. Wakes any worker LISTENing on this
    channel immediately instead of making it wait for its next poll tick.
    A single generic notification (no payload routing) is enough — a woken
    worker just polls all of its subscribed queues right away, same as it
    would on its normal cadence, so there's no need to track which specific
    queue(s) changed."""
    await db.execute(text("SELECT pg_notify(:channel, 'wake')"), {"channel": CHANNEL})
