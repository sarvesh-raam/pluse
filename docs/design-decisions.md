# Design decisions

This document is built up across the build phases. This first pass (Phase 8)
covers the eight bonus features from §10, each as its own labeled section per
spec. Phase 9 adds the remaining core trade-off sections (Postgres vs. Redis,
normalization, cascades, at-least-once vs. exactly-once, retry/jitter,
idempotency) above this line.

---

## 1. WebSocket live updates

`app/ws/manager.py` + `app/ws/publisher.py` + `app/ws/router.py`.

**Design:** the API process runs a single background task (`EventPublisher`,
started/stopped via FastAPI's `lifespan`) that polls the DB every 2s — but
only for projects that currently have at least one open WebSocket connection.
For each such project it diffs `jobs.updated_at` / `workers.last_heartbeat_at`
against the last check and broadcasts `job.updated` / `worker.updated`, plus a
lightweight `queue.stats` and `metrics.tick` snapshot every tick.

**Why polling instead of Postgres LISTEN/NOTIFY for this:** the worker and
scheduler run in separate containers from the API, so "an event happened"
can't be pushed directly to the API process — something has to bridge
processes, and LISTEN/NOTIFY is one option. But the spec explicitly files
LISTEN/NOTIFY under bonus item 8 ("nice-to-have"), not as a requirement for
live updates specifically, and polling has a real advantage here: it doesn't
care *which* process changed the DB (API, worker, or scheduler) or how many
different code paths could have changed it — it just looks at what changed.
Given `updated_at`/`last_heartbeat_at` already exist as columns, this was the
smallest-surface-area way to satisfy "WS /ws … events: job.updated,
worker.updated, queue.stats, metrics.tick" from §7. ~2s latency is the
accepted trade-off, consistent with the spec's own fallback-polling framing
for the frontend (§8.3).

**Auth:** the WS handshake validates the JWT and the caller's viewer+ role in
the requested project's org *before* accepting the connection (closes with
4401 otherwise) — a WS connection is scoped to exactly one project for its
whole lifetime.

---

## 2. RBAC

`organization_members.role` (owner/admin/member/viewer) + `app/core/rbac.py`.

**Design:** a simple total order — `viewer < member < admin < owner` — checked
via `require_role(minimum)` (a FastAPI dependency, for routes where `org_id`
is directly a path/query param) or `ensure_role(...)` (a plain async
function, for routes where the org has to be resolved from a parent resource
— e.g. a project, queue, or job — before a role check is possible). Every
mutating endpoint sits behind one of these two.

**Role semantics in this app specifically:**
- **viewer** — read-only everywhere.
- **member** — can create/retry/cancel jobs (the day-to-day operational
  action), but can't touch queue/retry-policy configuration.
- **admin** — full config control (queues, retry policies) plus member
  management, short of removing the org's last owner.
- **owner** — everything, plus the only role that can't be demoted/removed
  once it's the last one standing (`orgs.py`'s `_count_owners` guard) — an
  org can never be left without at least one owner.

---

## 3. Rate limiting

`app/core/ratelimit.py` (`TokenBucket` + `RateLimiterRegistry`) wired into
`engine/scheduler.py`'s `promote_due_jobs`.

**Design:** a classic token bucket per queue, refilling continuously at
`queues.rate_limit_per_sec`, capped at one second's worth of tokens (so a
queue that's been quiet for a while can't suddenly release a huge burst —
capacity defaults to `rate_per_sec`, not unbounded). It's scoped specifically
to *promotion* (waiting → queued), independent of `concurrency_limit` (which
caps how many run *simultaneously*): a queue can be rate-limited to 2
promotions/sec and still run 20 concurrently once they're queued — these are
two different knobs answering two different questions ("how fast can new work
start" vs. "how much can run at once").

**Why in-memory, single-process state is fine here:** only the scheduler
promotes due jobs (one process, one `RateLimiterRegistry` instance), so there
is no cross-process coordination problem to solve — unlike the job claim
itself, which genuinely needs a DB-level guarantee because *multiple workers*
race for the same rows.

**Verified live:** a queue with `rate_limit_per_sec=2` and 14 jobs all due at
once was promoted at exactly 2/sec across 7 consecutive seconds (checked via
each job's `claimed_at`, since NOTIFY makes claiming happen within
milliseconds of promotion — see §8 below — so `claimed_at` timestamps are a
faithful proxy for when each batch was actually promoted).

**Scope note:** this only throttles jobs that go through the scheduler's
promote step (delayed/scheduled/cron/retrying). `immediate`-type jobs are
created already-`queued` by the API and bypass promotion entirely — this
matches the spec's wording ("scheduler respects rate_limit_per_sec **when
promoting**"), not an oversight. A caller wanting rate-limited intake for
what would otherwise be immediate work can use `type=delayed` with a small
`run_at` offset instead.

---

## 4. Distributed locking

Inherent in the claim design (`engine/claim.py`), not a separate mechanism —
documented here because §10 calls it out as its own bonus line.

**Two layers, two different races:**
1. **`FOR UPDATE OF j SKIP LOCKED`** on the claim query guarantees two workers
   never claim the *same* job row — one worker's row lock makes a concurrent
   claimer simply skip past it rather than block on it.
2. **A per-queue Postgres advisory lock** (`pg_advisory_xact_lock(hashtext(...))`)
   wraps the capacity-check-then-claim sequence. SKIP LOCKED alone doesn't
   stop two workers from *jointly* claiming past `concurrency_limit` — each
   could read "3 free slots" from its own snapshot and claim 3 apiece. The
   advisory lock serializes that read-then-claim decision per queue (workers
   claiming from *other* queues are unaffected), closing that race without
   needing a second datastore (Redis, etcd, ...) for distributed locks.

Verified under real contention: 3 workers hammering a `concurrency_limit=2`
queue with 12 jobs never exceeded 2 concurrently running, and `job_executions`
showed exactly one execution per job — zero double-claims (Phase 5).

A third guard, `lock_token`, protects the *later* part of a job's lifecycle:
every state transition after claiming (running → completed/failed) re-reads
the row with `WHERE lock_token = :token FOR UPDATE`, so a worker that's been
reaped (its lock_token reset to NULL by the reaper) can't clobber state a new
claimant has since written, and holding that row lock during the transition
blocks a concurrent reaper sweep from acting on the same row mid-transition.

---

## 5. Workflow dependencies

`jobs.depends_on UUID[]` + `engine/scheduler.py`'s `resolve_dependencies()`.

**Design:** a job created with `depends_on` is forced into `status=scheduled`
regardless of `run_at` (the run_at value, if given, is stored but not used for
gating — dependency satisfaction is the only thing that promotes it). The
scheduler's deps step, run every tick, checks all referenced jobs' statuses:
- all `completed` → promote to `queued` (with `run_at` reset to now).
- any `dead` or `cancelled` → cascade-cancel the dependent (spec only
  mentions "if a dep is dead"; cancelled was added too, since a cancelled
  prerequisite is just as terminally unrunnable as a dead one).

**Why the time-based promote step explicitly excludes deps-gated jobs:** §6's
promote query (`status='scheduled' AND run_at<=now()`) would otherwise
promote a deps-gated job the moment its `run_at` passes, regardless of
whether its dependencies have actually finished. `promote_due_jobs` filters
these out (`_no_deps`) so the *only* path to `queued` for a deps-gated job is
through `resolve_dependencies` actually confirming its deps are done.

Verified live: job B (`depends_on=[A]`) stayed `scheduled` while A was
`queued`; flipping A to `completed` promoted B to `queued` within one tick. A
second case confirmed a `dead` dependency cascades to `cancelled`.

---

## 6. AI failure summaries

`engine/ai_summary.py`, called from `worker/main.py` when a job's failure
results in a DLQ move (`attempts >= max_attempts`).

**Design:** on final failure, the worker gathers the error message and the
job's last 10 `job_logs` lines, and asks Groq (`llama-3.3-70b-versatile`) for
a 1-2 sentence root-cause-and-fix summary, stored on that attempt's
`job_executions.ai_summary` and rendered in the Job Detail page.

**Why this happens *after* the failure transaction commits, not inside it:**
the Groq call is a network round-trip (up to 15s) — making it from inside the
same `async with AsyncSessionLocal()` block that holds the job's row lock
(via `load_for_transition`'s `FOR UPDATE`) would hold that lock for however
long Groq takes to respond, for no reason (the job is already in its terminal
`dead` state by that point; nothing else needs that row urgently). Instead:
commit the failure/DLQ transition first, call Groq with no open transaction,
then do a second short transaction to attach `ai_summary` to the
already-written execution row.

**Failure mode:** if `GROQ_API_KEY` is unset or the request fails for any
reason, `summarize_failure()` catches the exception, logs it, and returns
`None` — the DLQ pipeline itself never depends on this succeeding. This is an
annotation, not a load-bearing part of the failure path.

Verified live with a real Groq key: a `fail_n_times` job with `max_attempts=1`
failed once, moved straight to the DLQ, and its execution row got a genuine
Groq-generated summary ("The likely root cause is a deliberate failure
configured in the 'fail_n_times' handler... To fix, review and update the
'fail_until' parameter...") — rendered correctly in the Job Detail page's AI
failure summary panel.

---

## 7. Queue sharding (documented, not implemented — per spec, "implement if time permits")

**The idea:** today, a single scheduler process handles promotion for every
queue in the database, and any worker can claim from any queue it's
subscribed to — there's no partitioning of the claim workload itself. At a
scale where the claim query's per-queue advisory lock (§4 above) starts being
a real bottleneck — many workers, many queues, high enqueue rate — the next
step is sharding the *claim* responsibility, not just relying on SKIP LOCKED
to sort out contention after the fact.

**Proposed design:** introduce `shard_key = hash(job_id) % N` (computed at
enqueue time, stored as a generated/computed column or set explicitly by the
API) and have each worker instance declare which shard(s) it serves (an env
var, e.g. `WORKER_SHARD=0`, alongside `WORKER_QUEUES`). The claim query in
`engine/claim.py` gains one more predicate: `WHERE shard_key = ANY(:my_shards)`.
This turns the single advisory lock per queue into `N` independent locks per
queue (one per shard), so workers serving different shards of the same queue
never contend with each other at all — not even briefly for the capacity
check — while workers serving the *same* shard still get the existing
SKIP LOCKED + advisory-lock guarantees among themselves.

**Why `job_id` and not something else for the hash key:** it's already
unique, already indexed (primary key), and evenly distributed by
`gen_random_uuid()` — no new column needed to compute the shard, only to
*cache* it if recomputing the hash on every claim query proves too expensive
(a generated column `shard_key int GENERATED ALWAYS AS (hashtext(id::text) % N) STORED`
would let it participate in an index).

**Why this wasn't implemented for this submission:** the assignment's actual
scale (single scheduler, a handful of workers, a handful of queues) never
approaches the point where the advisory lock is a measurable bottleneck —
building sharding now would be optimizing for a load profile this system
doesn't have yet, at the cost of real complexity (shard rebalancing when `N`
changes, worker shard assignment, uneven load if queues aren't evenly
distributed across shards). It's a documented next step, not a needed one.

---

## 8. Event-driven execution

`app/core/notify.py` (`NOTIFY pulse_jobs`) + a LISTEN connection in
`worker/main.py`.

**Design:** a single generic channel, no payload routing — every place that
enqueues, promotes, or requeues a job (`POST /jobs`, `POST /jobs/batch`,
`POST /jobs/{id}/retry`, `POST /dlq/{id}/replay`, the scheduler's tick, and
the reaper) issues `NOTIFY pulse_jobs` after committing, *if* that operation
actually resulted in a job reaching `queued`. Each worker opens one dedicated
`asyncpg` connection (separate from the SQLAlchemy pool — LISTEN needs a
long-lived raw connection) and registers a callback that sets an
`asyncio.Event`. The poll loop's `sleep(interval)` became
`wait_for(wake_event.wait(), timeout=interval)`: it still polls on the normal
cadence as a fallback (safe if the LISTEN connection never connects or drops
— logged, not fatal), but a notification short-circuits the wait immediately.

**Why one generic channel instead of per-queue payloads:** a worker already
polls *all* of its subscribed queues every cycle, not one at a time — so
"something changed, go poll now" is exactly as actionable as "queue X
changed, go poll now" would be, for less bookkeeping (no need to track which
distinct queue_ids were touched by a bulk `UPDATE ... RETURNING`, which
matters for e.g. the scheduler's bulk promote statement touching many queues
in one query).

**Verified live, isolated from ordinary polling:** ran a worker with
`WORKER_POLL_INTERVAL_SEC=30` and confirmed a freshly-enqueued immediate job
was claimed and completed within ~30ms of creation — impossible on a 30s poll
interval alone, so the notification path is what's actually driving pickup,
not favorable poll timing.
