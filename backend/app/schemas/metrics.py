import uuid
from datetime import datetime

from pydantic import BaseModel


class MetricsOverview(BaseModel):
    project_id: uuid.UUID
    throughput_per_min: float
    success_rate: float | None
    active_workers: int
    queue_depth_total: int


class ThroughputBucket(BaseModel):
    bucket_start: datetime
    completed: int
    failed: int


class ThroughputResponse(BaseModel):
    project_id: uuid.UUID
    window: str
    bucket_size: str
    buckets: list[ThroughputBucket]


class QueueMetric(BaseModel):
    queue_id: uuid.UUID
    name: str
    depth: int
    running: int
    success_rate: float | None
    avg_duration_ms: float | None
