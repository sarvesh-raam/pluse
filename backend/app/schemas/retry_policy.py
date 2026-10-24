import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import RetryStrategy


class RetryPolicyCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    strategy: RetryStrategy
    base_delay_sec: int = Field(ge=0, le=86_400)
    max_delay_sec: int = Field(ge=0, le=7 * 86_400)
    max_attempts: int = Field(ge=1, le=100)
    jitter_pct: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="after")
    def _max_not_below_base(self) -> "RetryPolicyCreate":
        if self.max_delay_sec < self.base_delay_sec:
            raise ValueError("max_delay_sec must be >= base_delay_sec")
        return self


class RetryPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    strategy: RetryStrategy | None = None
    base_delay_sec: int | None = Field(default=None, ge=0, le=86_400)
    max_delay_sec: int | None = Field(default=None, ge=0, le=7 * 86_400)
    max_attempts: int | None = Field(default=None, ge=1, le=100)
    jitter_pct: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _reject_null(self) -> "RetryPolicyUpdate":
        # every retry_policies column is NOT NULL
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


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
