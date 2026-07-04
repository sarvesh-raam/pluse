import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    __table_args__ = (Index("idx_heartbeats_worker_ts", "worker_id", "ts", postgresql_ops={"ts": "DESC"}),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    running_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    worker: Mapped["Worker"] = relationship(back_populates="heartbeats")
