"""add_jobs_notify_trigger

Revision ID: a07f99fc0ca8
Revises: 0002
Create Date: 2026-07-05 15:34:09.862261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a07f99fc0ca8'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_new_job()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.status = 'queued' THEN
                PERFORM pg_notify('pulse_jobs', 'wake');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trigger_notify_new_job
        AFTER INSERT OR UPDATE OF status ON jobs
        FOR EACH ROW
        EXECUTE FUNCTION notify_new_job();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trigger_notify_new_job ON jobs")
    op.execute("DROP FUNCTION IF EXISTS notify_new_job()")
