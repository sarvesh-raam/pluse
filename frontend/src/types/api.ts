export type MemberRole = "owner" | "admin" | "member" | "viewer"
export type JobType = "immediate" | "delayed" | "scheduled" | "recurring" | "batch"
export type JobStatus =
  | "scheduled"
  | "queued"
  | "claimed"
  | "running"
  | "completed"
  | "failed"
  | "retrying"
  | "dead"
  | "cancelled"
export type ExecutionStatus = "running" | "completed" | "failed"
export type WorkerStatus = "active" | "idle" | "draining" | "dead"
export type RetryStrategy = "fixed" | "linear" | "exponential"
export type LogLevel = "debug" | "info" | "warn" | "error"

export interface Page<T> {
  items: T[]
  page: number
  size: number
  total: number
  pages: number
}

export interface User {
  id: string
  email: string
  full_name: string
  created_at: string
}

export interface OrgMembership {
  org_id: string
  role: MemberRole
}

export interface MeResponse {
  user: User
  memberships: OrgMembership[]
}

export interface Organization {
  id: string
  name: string
  slug: string
  created_at: string
}

export interface Member {
  id: string
  org_id: string
  user_id: string
  role: MemberRole
  email: string
  full_name: string
}

export interface Project {
  id: string
  org_id: string
  name: string
  slug: string
  created_at: string
}

export interface RetryPolicy {
  id: string
  project_id: string
  name: string
  strategy: RetryStrategy
  base_delay_sec: number
  max_delay_sec: number
  max_attempts: number
  jitter_pct: number
}

export interface Queue {
  id: string
  project_id: string
  name: string
  priority_default: number
  concurrency_limit: number
  rate_limit_per_sec: number | null
  retry_policy_id: string | null
  is_paused: boolean
  created_at: string
}

export interface QueueStats {
  queue_id: string
  scheduled: number
  queued: number
  claimed: number
  running: number
  completed: number
  failed: number
  retrying: number
  dead: number
  cancelled: number
  success_rate: number | null
  avg_duration_ms: number | null
  p95_duration_ms: number | null
}

export interface Job {
  id: string
  queue_id: string
  type: JobType
  status: JobStatus
  priority: number
  payload: Record<string, unknown>
  handler: string
  run_at: string
  attempts: number
  max_attempts: number
  idempotency_key: string | null
  worker_id: string | null
  depends_on: string[] | null
  batch_id: string | null
  cron_expr: string | null
  scheduled_job_id: string | null
  claimed_at: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface JobExecution {
  id: string
  job_id: string
  worker_id: string | null
  attempt_number: number
  status: ExecutionStatus
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  error_type: string | null
  error_message: string | null
  ai_summary: string | null
}

export interface JobLog {
  id: string
  job_id: string
  execution_id: string
  ts: string
  level: LogLevel
  message: string
}

export interface ScheduledJob {
  id: string
  queue_id: string
  cron_expr: string
  timezone: string
  handler: string
  payload: Record<string, unknown>
  is_active: boolean
  next_run_at: string
  last_run_at: string | null
}

export interface JobBatchProgress {
  batch_id: string
  total: number
  by_status: Record<string, number>
}

export interface WorkerInfo {
  id: string
  project_id: string
  name: string
  hostname: string
  status: WorkerStatus
  queues: string[]
  concurrency: number
  registered_at: string
  last_heartbeat_at: string | null
}

export interface WorkerHeartbeat {
  id: string
  worker_id: string
  ts: string
  running_jobs: number
  cpu_pct: number | null
  mem_mb: number | null
}

export interface DeadLetterEntry {
  id: string
  job_id: string
  queue_id: string
  payload: Record<string, unknown>
  final_error: string
  total_attempts: number
  failed_at: string
  replayed_at: string | null
}

export interface MetricsOverview {
  project_id: string
  throughput_per_min: number
  success_rate: number | null
  active_workers: number
  queue_depth_total: number
}

export interface ThroughputBucket {
  bucket_start: string
  completed: number
  failed: number
}

export interface ThroughputResponse {
  project_id: string
  window: string
  bucket_size: string
  buckets: ThroughputBucket[]
}

export interface QueueMetric {
  queue_id: string
  name: string
  depth: number
  running: number
  success_rate: number | null
  avg_duration_ms: number | null
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: unknown
  }
}
