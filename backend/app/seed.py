import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from croniter import croniter
from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db import AsyncSessionLocal
from app.models.enums import JobStatus, JobType, MemberRole, RetryStrategy
from app.models.job import Job
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.project import Project
from app.models.queue import Queue
from app.models.retry_policy import RetryPolicy
from app.models.scheduled_job import ScheduledJob
from app.models.user import User

logger = logging.getLogger("pulse.seed")

ORG_SLUG = "demo-org"
PROJECT_SLUG = "demo"
DEMO_EMAIL = "demo@pulse.dev"
DEMO_PASSWORD = "demo1234"


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
        if existing is not None:
            logger.info("seed data already present (org slug=%r) — skipping", ORG_SLUG)
            return

        org = Organization(name="Demo Org", slug=ORG_SLUG)
        db.add(org)
        await db.flush()

        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), full_name="Demo Owner")
        db.add(user)
        await db.flush()

        db.add(OrganizationMember(org_id=org.id, user_id=user.id, role=MemberRole.owner))

        project = Project(org_id=org.id, name="Demo Project", slug=PROJECT_SLUG)
        db.add(project)
        await db.flush()

        retry_policy = RetryPolicy(
            project_id=project.id,
            name="default-exponential",
            strategy=RetryStrategy.exponential,
            base_delay_sec=2,
            max_delay_sec=60,
            max_attempts=5,
            jitter_pct=0.2,
        )
        db.add(retry_policy)
        await db.flush()

        emails = Queue(
            project_id=project.id, name="emails", priority_default=5,
            concurrency_limit=3, retry_policy_id=retry_policy.id,
        )
        reports = Queue(
            project_id=project.id, name="reports", priority_default=3,
            concurrency_limit=2, retry_policy_id=retry_policy.id,
        )
        webhooks = Queue(
            project_id=project.id, name="webhooks", priority_default=1,
            concurrency_limit=5, rate_limit_per_sec=10, retry_policy_id=retry_policy.id,
        )
        db.add_all([emails, reports, webhooks])
        await db.flush()

        now = datetime.now(timezone.utc)

        # immediate jobs
        db.add(Job(
            queue_id=emails.id, type=JobType.immediate, status=JobStatus.queued,
            handler="sleep", payload={"seconds": 2}, run_at=now, max_attempts=5,
        ))
        db.add(Job(
            queue_id=reports.id, type=JobType.immediate, status=JobStatus.queued,
            handler="compute", payload={"n": 28}, run_at=now, max_attempts=5,
        ))
        db.add(Job(
            queue_id=webhooks.id, type=JobType.immediate, status=JobStatus.queued,
            handler="http_call", payload={"url": "https://example.com"}, run_at=now, max_attempts=5,
        ))

        # delayed job
        db.add(Job(
            queue_id=emails.id, type=JobType.delayed, status=JobStatus.scheduled,
            handler="sleep", payload={"seconds": 1}, run_at=now + timedelta(minutes=2),
            max_attempts=5,
        ))

        # fail_n_times — demonstrates retry -> backoff -> eventual success
        db.add(Job(
            queue_id=emails.id, type=JobType.immediate, status=JobStatus.queued,
            handler="fail_n_times", payload={"fail_until": 2}, run_at=now, max_attempts=5,
        ))

        # flaky jobs
        for _ in range(3):
            db.add(Job(
                queue_id=webhooks.id, type=JobType.immediate, status=JobStatus.queued,
                handler="flaky", payload={"fail_rate": 0.5}, run_at=now, max_attempts=5,
            ))

        # batch of compute jobs sharing one batch_id
        batch_id = uuid.uuid4()
        for n in (10, 15, 20, 25, 30):
            db.add(Job(
                queue_id=reports.id, type=JobType.batch, status=JobStatus.queued,
                handler="compute", payload={"n": n}, run_at=now, max_attempts=5,
                batch_id=batch_id,
            ))

        # cron / recurring schedule
        next_run = croniter("*/5 * * * *", now).get_next(datetime)
        db.add(ScheduledJob(
            queue_id=reports.id, cron_expr="*/5 * * * *", timezone="UTC",
            handler="compute", payload={"n": 20}, next_run_at=next_run,
        ))

        await db.commit()
        logger.info(
            "seed complete: org=%s project=%s login=%s/%s",
            ORG_SLUG, PROJECT_SLUG, DEMO_EMAIL, DEMO_PASSWORD,
        )


async def main() -> None:
    configure_logging()
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
