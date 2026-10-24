import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ExecutionStatus, JobStatus, JobType, LogLevel


class JobCreate(BaseModel):
    queue_id: uuid.UUID
    type: JobType
    handler: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-1000, le=1000)
    run_at: datetime | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=100)
    idempotency_key: str | None = Field(default=None, max_length=200)
    depends_on: list[uuid.UUID] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _validate_type(self) -> "JobCreate":
        if self.run_at is not None and self.run_at.tzinfo is None:
            raise ValueError("run_at must include a timezone offset (e.g. 2026-01-01T00:00:00Z)")
        if self.type in (JobType.batch, JobType.recurring):
            raise ValueError(
                "type must be one of immediate, delayed, scheduled — "
                "use POST /jobs/batch or POST /jobs/schedule instead"
            )
        if self.type in (JobType.delayed, JobType.scheduled) and self.run_at is None:
            raise ValueError(f"run_at is required for type={self.type.value}")
        return self


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    queue_id: uuid.UUID
    type: JobType
    status: JobStatus
    priority: int
    payload: dict[str, Any]
    handler: str
    run_at: datetime
    attempts: int
    max_attempts: int
    idempotency_key: str | None
    worker_id: uuid.UUID | None
    depends_on: list[uuid.UUID] | None
    batch_id: uuid.UUID | None
    cron_expr: str | None
    scheduled_job_id: uuid.UUID | None
    claimed_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BatchJobItem(BaseModel):
    handler: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-1000, le=1000)
    idempotency_key: str | None = Field(default=None, max_length=200)


class JobBatchCreate(BaseModel):
    queue_id: uuid.UUID
    jobs: list[BatchJobItem] = Field(min_length=1, max_length=1000)
    run_at: datetime | None = None

    @model_validator(mode="after")
    def _validate(self) -> "JobBatchCreate":
        if self.run_at is not None and self.run_at.tzinfo is None:
            raise ValueError("run_at must include a timezone offset")
        keys = [j.idempotency_key for j in self.jobs if j.idempotency_key]
        if len(keys) != len(set(keys)):
            raise ValueError("idempotency_key values must be unique within a batch")
        return self


class JobBatchOut(BaseModel):
    batch_id: uuid.UUID
    jobs: list[JobOut]


class JobBatchProgress(BaseModel):
    batch_id: uuid.UUID
    total: int
    by_status: dict[str, int]


class JobScheduleCreate(BaseModel):
    queue_id: uuid.UUID
    cron_expr: str = Field(min_length=1, max_length=100)
    timezone: str = "UTC"
    handler: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduledJobUpdate(BaseModel):
    is_active: bool


class ScheduledJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    queue_id: uuid.UUID
    cron_expr: str
    timezone: str
    handler: str
    payload: dict[str, Any]
    is_active: bool
    next_run_at: datetime
    last_run_at: datetime | None


class JobExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: uuid.UUID | None
    attempt_number: int
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_type: str | None
    error_message: str | None
    ai_summary: str | None


class JobLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    execution_id: uuid.UUID
    ts: datetime
    level: LogLevel
    message: str
