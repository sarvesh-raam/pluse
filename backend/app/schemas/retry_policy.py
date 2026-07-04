import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RetryStrategy


class RetryPolicyCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    strategy: RetryStrategy
    base_delay_sec: int = Field(ge=0)
    max_delay_sec: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    jitter_pct: float = Field(default=0.0, ge=0, le=1)


class RetryPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    strategy: RetryStrategy | None = None
    base_delay_sec: int | None = Field(default=None, ge=0)
    max_delay_sec: int | None = Field(default=None, ge=0)
    max_attempts: int | None = Field(default=None, ge=1)
    jitter_pct: float | None = Field(default=None, ge=0, le=1)


class RetryPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    strategy: RetryStrategy
    base_delay_sec: int
    max_delay_sec: int
    max_attempts: int
    jitter_pct: float
