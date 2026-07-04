import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QueueCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    priority_default: int = 0
    concurrency_limit: int = Field(default=5, ge=1)
    rate_limit_per_sec: int | None = Field(default=None, ge=1)
    retry_policy_id: uuid.UUID | None = None


class QueueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    priority_default: int | None = None
    concurrency_limit: int | None = Field(default=None, ge=1)
    rate_limit_per_sec: int | None = Field(default=None, ge=1)
    retry_policy_id: uuid.UUID | None = None


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
