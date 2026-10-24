# Changelog

## 0.2.0 — hardening + operations

### Security fixes

- **Privilege escalation in org membership.** Any `admin` could invite
  someone as `owner`, promote themselves to `owner`, and then demote or
  remove the real owners. Only owners can now grant, change or revoke the
  owner role.
- **Cross-tenant references.** A queue could be attached to another
  project's retry policy, and `depends_on` accepted job ids from any tenant
  (an existence oracle for other orgs' jobs). Both are now restricted to the
  caller's own project.
- **Public `/dbcheck` endpoint removed.** It returned raw driver errors
  (hostnames, users, SSL details) to anyone. Replaced by `/readyz`, which
  returns only up/down.
- **Login brute force.** No limit existed; now 10 failures per client+email
  per 5 minutes, then `429`.
- **Production secret guard.** `ENV=production` refuses to boot with the
  default (public) `JWT_SECRET`; API docs are hidden in production.
- Containers no longer run as root, and production images no longer ship
  pytest or a compiler.

### Correctness fixes

- **Poison-pill jobs looped forever.** A job that crashed its worker
  (OOM, segfault, kill) was requeued with `attempts` unchanged, so it could
  never reach the DLQ, and its execution row stayed `running` forever. The
  reaper now closes the execution as `WorkerLost`, charges the attempt, and
  dead-letters the job once attempts are exhausted. A job that was only
  claimed (never started) is still requeued for free.
- **Multiple scheduler replicas double-spawned every cron job** and
  double-promoted jobs. Ticks are now leader-elected with a Postgres
  advisory lock, so the scheduler can run with replicas>1 for availability.
- **Cron catch-up burst.** After scheduler downtime, a schedule spawned one
  job per tick for every missed slot (an hour of `* * * * *` = 60 jobs).
  Missed runs now collapse into one.
- **One bad schedule broke all of them.** An invalid timezone/cron written
  to the DB made every scheduler tick fail. The bad schedule is now
  deactivated and the rest keep running.
- **A worker wrongly declared dead never recovered** (e.g. after a GC pause
  or DB blip): it kept claiming jobs that the reaper then immediately stole
  back. It now revives itself on its next heartbeat.
- **Worker updated the wrong execution row** after a reap + re-claim
  (it looked rows up by a non-unique `attempt_number`).
- **Worker LISTEN connection never reconnected** after a drop; workers
  silently fell back to polling forever. It now reconnects.
- **Retrying a dead job left its DLQ entry pending**, so a later "replay"
  could re-run a job that had since completed. Retry now supersedes the
  entry, and replay refuses jobs that are no longer dead.
- **Cancel/retry raced with worker claims** (a job claimed a millisecond
  earlier could be "cancelled" and run anyway). Both now row-lock first.
  Invalid state transitions return `409` instead of `403`.
- **WebSocket broadcast crashed** with `Set changed size during iteration`
  when a client connected mid-broadcast; reconnecting clients were flooded
  with stale updates; bursts over 200 updates per tick were silently
  dropped.
- **500s from bad input:** `?sort=` with a relationship/method name,
  explicit `null` for required PATCH fields, `?window=99999999d`, unbounded
  integers overflowing int4, naive `run_at` datetimes, duplicate
  idempotency keys within a batch, and unique-constraint races (now `409`).
- **Logged tracebacks were dropped** by the JSON log formatter, making
  every "tick failed" log undebuggable.
- `sslmode=disable` in `DATABASE_URL` was rewritten to `ssl=require`;
  Neon's `channel_binding` parameter crashed asyncpg.
- Worker graceful shutdown never ran on Windows (no signal handler).
- Worker telemetry reported host-wide RAM instead of the worker's own,
  so the dashboard summed the whole machine's memory once per worker.
- Demo handlers accepted payloads that could wedge a worker slot forever
  (`compute` with a huge `n` runs in an uncancellable thread).
- Deleting a queue loaded every job/log/execution row into memory to
  cascade; DB-level `ON DELETE CASCADE` is now used directly.
- `worker_heartbeats` and dead `workers` rows grew forever; they are now
  pruned (`HEARTBEAT_RETENTION_HOURS`, `DEAD_WORKER_RETENTION_HOURS`).
- Several N+1 query loops (queue metrics, WS queue stats, dependency
  resolution) replaced with grouped queries, plus new indexes for the
  reaper, publisher and metrics hot paths (migration `0005`).

### Frontend fixes

- Dashboard "Recent failures" was always empty: it queried `status=failed`,
  which jobs never rest in. It now shows dead jobs.
- "Active workers" counted only busy workers; it now counts live ones.
- Switching projects left the DLQ page showing (and replaying into) the
  previous project's queue.
- A stale persisted org/project (membership revoked, project deleted) left
  every page stuck on 403/404s.
- Load generator fired up to 1,000 separate POSTs and swallowed errors; it
  now uses the batch endpoint and reports failures.
- Onboarding failed on names that slugify to nothing or collide, and
  created a duplicate org when project creation failed and was retried.
- WebSocket events triggered hundreds of cache invalidations per second
  under load; they are now coalesced.
- Initial bundle halved (≈990 KB → ≈490 KB) with route-level code splitting.

### New

- **Prometheus metrics** from every process, `/healthz` + `/readyz` probes,
  7 alert rules, and a provisioned Grafana dashboard in docker-compose.
- **Chaos engineering:** `POST /chaos/kill` plus UI buttons and a CLI
  command that hard-kill a live worker (pod delete on Kubernetes, process
  kill elsewhere) to demonstrate self-healing.
- **Kubernetes manifests** (Kustomize) with probes, HPAs, PDBs, a migration
  Job, least-privilege RBAC, and Pod Security `restricted`.
- **GitHub Actions CI/CD:** lint, tests against real Postgres, manifest
  validation, image publishing to GHCR, and an optional Kubernetes rollout
  with smoke test and automatic rollback.
- Cron schedules can be paused, resumed and deleted
  (`PATCH`/`DELETE /jobs/schedule/{id}`).
- 16 new regression tests (39 total).
