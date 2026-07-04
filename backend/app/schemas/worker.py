import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import WorkerStatus


class WorkerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    hostname: str
    status: WorkerStatus
    queues: list[str]
    concurrency: int
    registered_at: datetime
    last_heartbeat_at: datetime | None


class WorkerHeartbeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_id: uuid.UUID
    ts: datetime
    running_jobs: int
    cpu_pct: float | None
    mem_mb: int | None
