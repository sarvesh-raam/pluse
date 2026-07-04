import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Queue(Base):
    __tablename__ = "queues"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_queues_project_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    retry_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retry_policies.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    priority_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    rate_limit_per_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="queues")
    retry_policy: Mapped["RetryPolicy | None"] = relationship(back_populates="queues")
    jobs: Mapped[list["Job"]] = relationship(back_populates="queue", cascade="all, delete-orphan")
    scheduled_jobs: Mapped[list["ScheduledJob"]] = relationship(
        back_populates="queue", cascade="all, delete-orphan"
    )
    dlq_entries: Mapped[list["DeadLetterEntry"]] = relationship(
        back_populates="queue", cascade="all, delete-orphan"
    )
