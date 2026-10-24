"""chaos kill flag on workers, indexes for reaper/publisher hot paths

Revision ID: 0005
Revises: 1f6ec311d762
Create Date: 2026-10-24

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "1f6ec311d762"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workers", sa.Column("chaos_kill_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    # reaper: "claimed/running jobs under worker X"
    op.create_index(
        "idx_jobs_worker_inflight", "jobs", ["worker_id"],
        postgresql_where=sa.text("status IN ('claimed', 'running')"),
    )
    # ws publisher: "jobs updated since T"
    op.create_index("idx_jobs_updated_at", "jobs", ["updated_at"])
    # metrics: executions finished in a time window
    op.create_index("idx_exec_finished_at", "job_executions", ["finished_at"])
    # heartbeat retention pruning
    op.create_index("idx_heartbeats_ts", "worker_heartbeats", ["ts"])


def downgrade() -> None:
    op.drop_index("idx_heartbeats_ts", table_name="worker_heartbeats")
    op.drop_index("idx_exec_finished_at", table_name="job_executions")
    op.drop_index("idx_jobs_updated_at", table_name="jobs")
    op.drop_index("idx_jobs_worker_inflight", table_name="jobs")
    op.drop_column("workers", "chaos_kill_requested_at")
