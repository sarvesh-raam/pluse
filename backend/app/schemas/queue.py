import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueueCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    priority_default: int = Field(default=0, ge=-1000, le=1000)
    concurrency_limit: int = Field(default=5, ge=1, le=10_000)
    rate_limit_per_sec: int | None = Field(default=None, ge=1, le=100_000)
    retry_policy_id: uuid.UUID | None = None


class QueueUpdate(BaseModel):
    """PATCH body. rate_limit_per_sec and retry_policy_id may be explicitly
    set to null (to clear them); the other fields are NOT NULL columns, so
    an explicit null is rejected instead of crashing the UPDATE."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    priority_default: int | None = Field(default=None, ge=-1000, le=1000)
    concurrency_limit: int | None = Field(default=None, ge=1, le=10_000)
    rate_limit_per_sec: int | None = Field(default=None, ge=1, le=100_000)
    retry_policy_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _reject_null_for_required_columns(self) -> "QueueUpdate":
        for field in ("name", "priority_default", "concurrency_limit"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class QueueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    priority_default: int
    concurrency_limit: int
    rate_limit_per_sec: int | None
    retry_policy_id: uuid.UUID | None
    is_paused: bool
    created_at: datetime


class QueueStats(BaseModel):
    queue_id: uuid.UUID
    scheduled: int
    queued: int
    claimed: int
    running: int
    completed: int
    failed: int
    retrying: int
    dead: int
    cancelled: int
    success_rate: float | None
    avg_duration_ms: float | None
    p95_duration_ms: float | None
