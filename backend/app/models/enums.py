import enum


class MemberRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class RetryStrategy(str, enum.Enum):
    fixed = "fixed"
    linear = "linear"
    exponential = "exponential"


class JobType(str, enum.Enum):
    immediate = "immediate"
    delayed = "delayed"
    scheduled = "scheduled"
    recurring = "recurring"
    batch = "batch"


class JobStatus(str, enum.Enum):
    scheduled = "scheduled"
    queued = "queued"
    claimed = "claimed"
    running = "running"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"
    dead = "dead"
    cancelled = "cancelled"


class ExecutionStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class WorkerStatus(str, enum.Enum):
    active = "active"
    idle = "idle"
    draining = "draining"
    dead = "dead"


class LogLevel(str, enum.Enum):
    debug = "debug"
    info = "info"
    warn = "warn"
    error = "error"
