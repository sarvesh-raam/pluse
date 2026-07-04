"""extend idx_jobs_due to cover retrying jobs too

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_jobs_due", table_name="jobs")
    op.create_index(
        "idx_jobs_due", "jobs", ["run_at"],
        postgresql_where=sa.text("status IN ('scheduled', 'retrying')"),
    )


def downgrade() -> None:
    op.drop_index("idx_jobs_due", table_name="jobs")
    op.create_index(
        "idx_jobs_due", "jobs", ["run_at"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )
