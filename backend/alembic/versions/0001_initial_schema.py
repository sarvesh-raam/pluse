"""initial schema — all 13 Pulse tables

Revision ID: 0001
Revises:
Create Date: 2026-07-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# enum type definitions (created inline the first time they're used in a create_table)
member_role = postgresql.ENUM("owner", "admin", "member", "viewer", name="member_role")
retry_strategy = postgresql.ENUM("fixed", "linear", "exponential", name="retry_strategy")
worker_status = postgresql.ENUM("active", "idle", "draining", "dead", name="worker_status")
job_type = postgresql.ENUM("immediate", "delayed", "scheduled", "recurring", "batch", name="job_type")
job_status = postgresql.ENUM(
    "scheduled", "queued", "claimed", "running", "completed", "failed",
    "retrying", "dead", "cancelled", name="job_status",
)
execution_status = postgresql.ENUM("running", "completed", "failed", name="execution_status")
log_level = postgresql.ENUM("debug", "info", "warn", "error", name="log_level")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("slug", sa.String, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", postgresql.CITEXT, nullable=False, unique=True),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", member_role, nullable=False, server_default=sa.text("'member'")),
        sa.UniqueConstraint("org_id", "user_id", name="uq_org_members_org_user"),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("slug", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "slug", name="uq_projects_org_slug"),
    )

    op.create_table(
        "retry_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("strategy", retry_strategy, nullable=False),
        sa.Column("base_delay_sec", sa.Integer, nullable=False),
        sa.Column("max_delay_sec", sa.Integer, nullable=False),
        sa.Column("max_attempts", sa.Integer, nullable=False),
        sa.Column("jitter_pct", sa.Float, nullable=False, server_default="0"),
    )

    op.create_table(
        "queues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("retry_policy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("retry_policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("priority_default", sa.Integer, nullable=False, server_default="0"),
        sa.Column("concurrency_limit", sa.Integer, nullable=False, server_default="5"),
        sa.Column("rate_limit_per_sec", sa.Integer, nullable=True),
        sa.Column("is_paused", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_queues_project_name"),
    )

    op.create_table(
        "workers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("hostname", sa.String, nullable=False),
        sa.Column("status", worker_status, nullable=False, server_default=sa.text("'idle'")),
        sa.Column("queues", postgresql.ARRAY(sa.String), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("concurrency", sa.Integer, nullable=False, server_default="5"),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workers_last_heartbeat_at", "workers", ["last_heartbeat_at"])

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("queue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cron_expr", sa.String, nullable=False),
        sa.Column("timezone", sa.String, nullable=False, server_default=sa.text("'UTC'")),
        sa.Column("handler", sa.String, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_scheduled_jobs_next_run", "scheduled_jobs", ["next_run_at"],
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("queue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", job_type, nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("handler", sa.String, nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("idempotency_key", sa.String, nullable=True),
        sa.Column("lock_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("depends_on", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cron_expr", sa.String, nullable=True),
        sa.Column("scheduled_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scheduled_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "idx_jobs_claim", "jobs", ["queue_id", "status", sa.text("priority DESC"), "run_at"],
    )
    op.create_index(
        "idx_jobs_due", "jobs", ["run_at"], postgresql_where=sa.text("status = 'scheduled'"),
    )
    op.create_index(
        "uq_jobs_idem", "jobs", ["queue_id", "idempotency_key"], unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index("idx_jobs_status", "jobs", ["status"])
    op.create_index("idx_jobs_batch", "jobs", ["batch_id"])

    op.create_table(
        "job_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("status", execution_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error_type", sa.String, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("ai_summary", sa.Text, nullable=True),
    )
    op.create_index("idx_exec_job", "job_executions", ["job_id", "attempt_number"])

    op.create_table(
        "worker_heartbeats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("running_jobs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cpu_pct", sa.Float, nullable=True),
        sa.Column("mem_mb", sa.Integer, nullable=True),
    )
    op.create_index(
        "idx_heartbeats_worker_ts", "worker_heartbeats", ["worker_id", sa.text("ts DESC")],
    )

    op.create_table(
        "job_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("level", log_level, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
    )
    op.create_index("idx_job_logs_job_ts", "job_logs", ["job_id", "ts"])

    op.create_table(
        "dead_letter_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("queue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("final_error", sa.Text, nullable=False),
        sa.Column("total_attempts", sa.Integer, nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_dlq_queue_failed", "dead_letter_queue", ["queue_id", sa.text("failed_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("dead_letter_queue")
    op.drop_table("job_logs")
    op.drop_table("worker_heartbeats")
    op.drop_table("job_executions")
    op.drop_table("jobs")
    op.drop_table("scheduled_jobs")
    op.drop_table("workers")
    op.drop_table("queues")
    op.drop_table("retry_policies")
    op.drop_table("projects")
    op.drop_table("organization_members")
    op.drop_table("users")
    op.drop_table("organizations")

    log_level.drop(op.get_bind(), checkfirst=True)
    execution_status.drop(op.get_bind(), checkfirst=True)
    job_status.drop(op.get_bind(), checkfirst=True)
    job_type.drop(op.get_bind(), checkfirst=True)
    worker_status.drop(op.get_bind(), checkfirst=True)
    retry_strategy.drop(op.get_bind(), checkfirst=True)
    member_role.drop(op.get_bind(), checkfirst=True)
