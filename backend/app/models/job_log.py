import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import LogLevel


class JobLog(Base):
    __tablename__ = "job_logs"
    __table_args__ = (Index("idx_job_logs_job_ts", "job_id", "ts"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_executions.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    level: Mapped[LogLevel] = mapped_column(Enum(LogLevel, name="log_level"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="logs")
    execution: Mapped["JobExecution"] = relationship(back_populates="logs")
