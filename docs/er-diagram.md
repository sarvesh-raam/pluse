# ER diagram

All 13 tables from spec §4, exactly as migrated in
`backend/alembic/versions/0001_initial_schema.py` (verified against a live
Postgres in Phase 1 — every FK/index/cascade below is what's actually in the
database, not just what was planned).

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERS : has
    USERS ||--o{ ORGANIZATION_MEMBERS : has
    ORGANIZATIONS ||--o{ PROJECTS : owns
    PROJECTS ||--o{ RETRY_POLICIES : defines
    PROJECTS ||--o{ QUEUES : owns
    PROJECTS ||--o{ WORKERS : owns
    RETRY_POLICIES |o--o{ QUEUES : "used by (nullable)"
    QUEUES ||--o{ JOBS : contains
    QUEUES ||--o{ SCHEDULED_JOBS : contains
    QUEUES ||--o{ DEAD_LETTER_QUEUE : contains
    SCHEDULED_JOBS |o--o{ JOBS : spawns
    WORKERS |o--o{ JOBS : "claims (nullable)"
    WORKERS ||--o{ WORKER_HEARTBEATS : reports
    WORKERS |o--o{ JOB_EXECUTIONS : "ran (nullable)"
    JOBS ||--o{ JOB_EXECUTIONS : has
    JOBS ||--o{ JOB_LOGS : has
    JOBS ||--o{ DEAD_LETTER_QUEUE : "moved to"
    JOB_EXECUTIONS ||--o{ JOB_LOGS : has

    ORGANIZATIONS {
        uuid id PK
        string name
        string slug UK
        timestamptz created_at
    }
    USERS {
        uuid id PK
        citext email UK
        string password_hash
        string full_name
        timestamptz created_at
    }
    ORGANIZATION_MEMBERS {
        uuid id PK
        uuid org_id FK "ON DELETE CASCADE"
        uuid user_id FK "ON DELETE CASCADE"
        enum role "owner|admin|member|viewer"
    }
    PROJECTS {
        uuid id PK
        uuid org_id FK "ON DELETE CASCADE"
        string name
        string slug "UK with org_id"
        timestamptz created_at
    }
    RETRY_POLICIES {
        uuid id PK
        uuid project_id FK "ON DELETE CASCADE"
        string name
        enum strategy "fixed|linear|exponential"
        int base_delay_sec
        int max_delay_sec
        int max_attempts
        float jitter_pct
    }
    QUEUES {
        uuid id PK
        uuid project_id FK "ON DELETE CASCADE"
        uuid retry_policy_id FK "ON DELETE SET NULL"
        string name "UK with project_id"
        int priority_default
        int concurrency_limit
        int rate_limit_per_sec "nullable"
        bool is_paused
        timestamptz created_at
    }
    JOBS {
        uuid id PK
        uuid queue_id FK "ON DELETE CASCADE"
        enum type "immediate|delayed|scheduled|recurring|batch"
        enum status "9 values, see spec §4.1"
        int priority
        jsonb payload
        string handler
        timestamptz run_at
        int attempts
        int max_attempts
        string idempotency_key "nullable, UK with queue_id"
        uuid lock_token "nullable"
        uuid worker_id FK "ON DELETE SET NULL, nullable"
        uuid_array depends_on "nullable, no FK (see note)"
        uuid batch_id "nullable, no FK"
        string cron_expr "nullable"
        uuid scheduled_job_id FK "ON DELETE SET NULL, nullable"
        timestamptz claimed_at "nullable"
        timestamptz started_at "nullable"
        timestamptz finished_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    JOB_EXECUTIONS {
        uuid id PK
        uuid job_id FK "ON DELETE CASCADE"
        uuid worker_id FK "ON DELETE SET NULL, nullable"
        int attempt_number
        enum status "running|completed|failed"
        timestamptz started_at
        timestamptz finished_at "nullable"
        int duration_ms "nullable"
        string error_type "nullable"
        text error_message "nullable"
        text ai_summary "nullable, Groq bonus"
    }
    SCHEDULED_JOBS {
        uuid id PK
        uuid queue_id FK "ON DELETE CASCADE"
        string cron_expr
        string timezone
        string handler
        jsonb payload
        bool is_active
        timestamptz next_run_at
        timestamptz last_run_at "nullable"
    }
    WORKERS {
        uuid id PK
        uuid project_id FK "ON DELETE CASCADE"
        string name
        string hostname
        enum status "active|idle|draining|dead"
        text_array queues
        int concurrency
        timestamptz registered_at
        timestamptz last_heartbeat_at "nullable"
        float cpu_percent "nullable, latest reading"
        float ram_mb "nullable, latest reading"
    }
    WORKER_HEARTBEATS {
        uuid id PK
        uuid worker_id FK "ON DELETE CASCADE"
        timestamptz ts
        int running_jobs
        float cpu_percent "nullable"
        float ram_mb "nullable"
    }
    JOB_LOGS {
        uuid id PK
        uuid job_id FK "ON DELETE CASCADE"
        uuid execution_id FK "ON DELETE CASCADE"
        timestamptz ts
        enum level "debug|info|warn|error"
        text message
    }
    DEAD_LETTER_QUEUE {
        uuid id PK
        uuid job_id FK "ON DELETE CASCADE"
        uuid queue_id FK "ON DELETE CASCADE"
        jsonb payload
        text final_error
        int total_attempts
        timestamptz failed_at
        timestamptz replayed_at "nullable"
    }
```

## Indexes that carry real query load

- **`idx_jobs_claim (queue_id, status, priority DESC, run_at)`** — the claim
  query's entire `WHERE queue_id=... AND status='queued' AND run_at<=now()
  ORDER BY priority DESC, run_at ASC` is served by this one composite index.
- **`idx_jobs_due (run_at) WHERE status IN ('scheduled','retrying')`** —
  partial index backing the scheduler's due-scan; rows in any other status
  (the overwhelming majority once a system's been running a while —
  completed/failed/dead/cancelled) never bloat it.
- **`uq_jobs_idem (queue_id, idempotency_key) WHERE idempotency_key IS NOT
  NULL`** — a partial *unique* index, so idempotency is enforced by Postgres
  itself, not just application logic, and jobs without a key (the common
  case) don't pay for an index entry.
- **`idx_heartbeats_worker_ts (worker_id, ts DESC)`** and **`idx_dlq_queue_failed
  (queue_id, failed_at DESC)`** — both back "most recent N for this
  worker/queue" queries the dashboard makes constantly (utilization charts,
  DLQ list).

## depends_on and batch_id have no FK — on purpose

Both are plain `uuid[]` / `uuid` columns, not foreign keys. Postgres has no
native way to express "array of FKs" (`uuid[] REFERENCES jobs(id)` isn't
valid DDL), and a batch's `batch_id` is a *grouping* value shared by N rows,
not a reference to a single parent row — there's no one row for it to point
at. Both are handled at the application layer instead: `_validate_depends_on`
checks referenced jobs exist at creation time, and the scheduler's
`resolve_dependencies` step re-checks their live status on every tick.
