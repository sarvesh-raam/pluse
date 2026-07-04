# API reference

All routes are prefixed `/api/v1` (omitted below for brevity) and return
JSON. Interactive, always-up-to-date docs are also served by FastAPI itself
at `http://localhost:8000/docs` (Swagger UI) and `/redoc` — this file is a
static companion for quick reference and grading, generated against the
routes actually registered in the running app (see the mapping table in
`docs/design-decisions.md` for any place a route's name/shape didn't match
the original spec listing 1:1).

**Auth:** every route except `/auth/register`, `/auth/login`, `/auth/refresh`,
and `/health` requires `Authorization: Bearer <access_token>`. Missing/invalid
token → `401`. Insufficient role for the action → `403`.

**Errors:** every error response is `{"error": {"code", "message", "details"}}`.
Validation errors (`422`) put the Pydantic error list in `details`.

**Pagination:** list endpoints accept `page` (1-indexed, default 1) and `size`
(default 20, max 100), plus resource-specific filters, and return
`{"items": [...], "page", "size", "total", "pages"}`.

---

## Auth

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | none | `{email, password, full_name}` → `201` user (no org membership yet) |
| POST | `/auth/login` | none | `{email, password}` → `200 {access_token, refresh_token, token_type}` |
| POST | `/auth/refresh` | none | `{refresh_token}` → new token pair (rotated) |
| GET | `/auth/me` | any | current user + their `[{org_id, role}]` memberships |

## Organizations

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/orgs` | any | orgs the caller is a member of |
| POST | `/orgs` | any | creates the org; caller becomes `owner` |
| GET | `/orgs/{org_id}` | viewer | |
| GET | `/orgs/{org_id}/members` | viewer | |
| POST | `/orgs/{org_id}/members` | admin | invites an *existing* registered user by email (no pending-invite table — see design-decisions.md) |
| PATCH | `/orgs/{org_id}/members/{member_id}` | admin | change role; blocked if it would demote the last `owner` |
| DELETE | `/orgs/{org_id}/members/{member_id}` | admin | blocked if it would remove the last `owner` |

## Projects

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/projects?org_id=` | viewer | |
| POST | `/projects` | admin | `{org_id, name, slug}` |
| GET | `/projects/{project_id}` | viewer | |

## Retry policies

Not in the original endpoint sketch, added because `queues.retry_policy_id`
and the retry engine both need somewhere to define reusable policies (spec
§4.1 calls retry_policies "reusable ... referenced by queues/jobs").

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/retry-policies?project_id=` | viewer | |
| POST | `/retry-policies` | admin | `{project_id, name, strategy, base_delay_sec, max_delay_sec, max_attempts, jitter_pct?}` |
| GET | `/retry-policies/{id}` | viewer | |
| PATCH | `/retry-policies/{id}` | admin | partial update |
| DELETE | `/retry-policies/{id}` | admin | queues referencing it get `retry_policy_id` set to `NULL` |

## Queues

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/queues?project_id=` | viewer | |
| POST | `/queues` | admin | `{project_id, name, priority_default?, concurrency_limit?, rate_limit_per_sec?, retry_policy_id?}` |
| GET | `/queues/{id}` | viewer | |
| PATCH | `/queues/{id}` | admin | partial update of config fields (not `is_paused` — use pause/resume) |
| DELETE | `/queues/{id}` | admin | cascades to its jobs/scheduled_jobs/DLQ entries |
| POST | `/queues/{id}/pause` | admin | no new jobs claimed until resumed |
| POST | `/queues/{id}/resume` | admin | |
| GET | `/queues/{id}/stats` | viewer | per-status counts, success_rate, avg/p95 duration |

## Jobs

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/jobs?project_id=&queue_id=&status=&type=` | viewer | filtered, paginated, sortable |
| POST | `/jobs` | member | `type` must be `immediate`\|`delayed`\|`scheduled` (`recurring`/`batch` rejected — use the endpoints below); duplicate `idempotency_key` for the same queue returns the existing job with `200` instead of creating a new one |
| POST | `/jobs/batch` | member | `{queue_id, jobs: [{handler, payload, priority}], run_at?}` → shared `batch_id` |
| GET | `/jobs/batch/{batch_id}` | viewer | aggregate progress: `{total, by_status}` |
| POST | `/jobs/schedule` | member | `{queue_id, cron_expr, timezone?, handler, payload?}` → creates a `scheduled_jobs` template; croniter computes `next_run_at` immediately |
| GET | `/jobs/schedule?queue_id=` | viewer | list a queue's cron templates |
| GET | `/jobs/{id}` | viewer | |
| POST | `/jobs/{id}/retry` | member | only from `failed`/`dead`; resets `attempts` to 0 |
| POST | `/jobs/{id}/cancel` | member | only from `scheduled`/`queued`/`retrying` |
| GET | `/jobs/{id}/executions` | viewer | full attempt history, oldest first |
| GET | `/jobs/{id}/logs` | viewer | paginated, oldest first |

## Workers

Not in the original endpoint sketch — added in Phase 7 because the Workers
dashboard page needs to read back what the worker process itself only ever
wrote (see design-decisions.md).

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/workers?project_id=` | viewer | |
| GET | `/workers/{id}` | viewer | |
| GET | `/workers/{id}/heartbeats?limit=` | viewer | chronological (oldest first), default last 60 |

## Dead letter queue

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/dlq?queue_id=` | viewer | |
| POST | `/dlq/{id}/replay` | member | resets the original job to `queued`/`attempts=0`; `409` if already replayed |

## Metrics

| Method | Path | Min role | Notes |
|---|---|---|---|
| GET | `/metrics/overview?project_id=` | viewer | throughput/min (5m avg), success_rate (1h), active_workers, queue_depth_total |
| GET | `/metrics/throughput?project_id=&window=` | viewer | `window` e.g. `30m`/`1h`/`24h`/`7d`; bucket size auto-scales (minute/hour/day) |
| GET | `/metrics/queues?project_id=` | viewer | per-queue depth/running/success_rate/avg_duration_ms |

## WebSocket

| Path | Auth | Notes |
|---|---|---|
| `GET /ws?token=&project_id=` | JWT in query string, viewer+ role in the project's org | Events: `job.updated`, `worker.updated`, `queue.stats`, `metrics.tick`. Connection is validated *before* the handshake completes (closes with code `4401` on failure). See design-decisions.md §1 for why this is poll-bridged rather than pushed directly from worker/scheduler processes. |
