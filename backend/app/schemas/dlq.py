import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DeadLetterEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    queue_id: uuid.UUID
    payload: dict[str, Any]
    final_error: str
    total_attempts: int
    failed_at: datetime
    replayed_at: datetime | None
