import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import RetryStrategy


class RetryPolicy(Base):
    __tablename__ = "retry_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    strategy: Mapped[RetryStrategy] = mapped_column(
        Enum(RetryStrategy, name="retry_strategy"), nullable=False
    )
    base_delay_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    max_delay_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    jitter_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    project: Mapped["Project"] = relationship(back_populates="retry_policies")
    queues: Mapped[list["Queue"]] = relationship(back_populates="retry_policy")
