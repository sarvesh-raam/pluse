import { useAuthStore } from "@/lib/auth-store"
import type {
  DeadLetterEntry,
  Job,
  JobBatchProgress,
  JobExecution,
  JobLog,
  MeResponse,
  Member,
  MetricsOverview,
  Organization,
  Page,
  Project,
  Queue,
  QueueMetric,
  QueueStats,
  RetryPolicy,
  ScheduledJob,
  ThroughputResponse,
  WorkerHeartbeat,
  WorkerInfo,
} from "@/types/api"

const API_BASE = "/api/v1"

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value))
  }
  const s = search.toString()
  return s ? `?${s}` : ""
}

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, logout } = useAuthStore.getState()
  if (!refreshToken) return null

  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!res.ok) {
    logout()
    return null
  }
  const data = await res.json()
  setTokens(data.access_token, data.refresh_token)
  return data.access_token as string
}

const UNAUTHENTICATED_PATHS = ["/auth/login", "/auth/register", "/auth/refresh"]

async function apiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const { accessToken } = useAuthStore.getState()
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json")
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`)

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  // A 401 from these endpoints means "wrong credentials" or "invalid/expired refresh
  // token" — never "your access token needs refreshing", so skip the refresh-retry
  // dance and let the real backend error message (e.g. "Invalid email or password")
  // surface below instead of being masked by a generic "Session expired".
  const isUnauthenticatedEndpoint = UNAUTHENTICATED_PATHS.some((p) => path.startsWith(p))

  if (res.status === 401 && retry && !isUnauthenticatedEndpoint) {
    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null
    })
    const newToken = await refreshPromise
    if (newToken) return apiFetch<T>(path, options, false)
    throw new ApiError(401, "unauthorized", "Session expired")
  }

  if (!res.ok) {
    let body: { error?: { code: string; message: string; details?: unknown } } | null = null
    try {
      body = await res.json()
    } catch {
      /* no JSON body */
    }
    throw new ApiError(
      res.status,
      body?.error?.code ?? "error",
      body?.error?.message ?? res.statusText,
      body?.error?.details
    )
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

// --- auth ---
export const authApi = {
  register: (body: { email: string; password: string; full_name: string }) =>
    apiFetch<{ id: string; email: string; full_name: string; created_at: string }>(
      "/auth/register",
      { method: "POST", body: JSON.stringify(body) }
    ),
  login: (body: { email: string; password: string }) =>
    apiFetch<{ access_token: string; refresh_token: string; token_type: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify(body) }
    ),
  me: () => apiFetch<MeResponse>("/auth/me"),
}

// --- orgs ---
export const orgsApi = {
  list: () => apiFetch<Page<Organization>>(`/orgs${qs({ size: 100 })}`),
  create: (body: { name: string; slug: string }) =>
    apiFetch<Organization>("/orgs", { method: "POST", body: JSON.stringify(body) }),
  get: (id: string) => apiFetch<Organization>(`/orgs/${id}`),
  members: (id: string) => apiFetch<Member[]>(`/orgs/${id}/members`),
  invite: (id: string, body: { email: string; role: string }) =>
    apiFetch<Member>(`/orgs/${id}/members`, { method: "POST", body: JSON.stringify(body) }),
  updateMemberRole: (id: string, memberId: string, role: string) =>
    apiFetch<Member>(`/orgs/${id}/members/${memberId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  removeMember: (id: string, memberId: string) =>
    apiFetch<void>(`/orgs/${id}/members/${memberId}`, { method: "DELETE" }),
}

// --- projects ---
export const projectsApi = {
  list: (orgId: string) => apiFetch<Page<Project>>(`/projects${qs({ org_id: orgId, size: 100 })}`),
  create: (body: { org_id: string; name: string; slug: string }) =>
    apiFetch<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  get: (id: string) => apiFetch<Project>(`/projects/${id}`),
}

// --- retry policies ---
export const retryPoliciesApi = {
  list: (projectId: string) =>
    apiFetch<Page<RetryPolicy>>(`/retry-policies${qs({ project_id: projectId, size: 100 })}`),
  create: (body: {
    project_id: string
    name: string
    strategy: string
    base_delay_sec: number
    max_delay_sec: number
    max_attempts: number
    jitter_pct?: number
  }) => apiFetch<RetryPolicy>("/retry-policies", { method: "POST", body: JSON.stringify(body) }),
}

// --- queues ---
export const queuesApi = {
  list: (projectId: string) => apiFetch<Page<Queue>>(`/queues${qs({ project_id: projectId, size: 100 })}`),
  create: (body: {
    project_id: string
    name: string
    priority_default?: number
    concurrency_limit?: number
    rate_limit_per_sec?: number | null
    retry_policy_id?: string | null
  }) => apiFetch<Queue>("/queues", { method: "POST", body: JSON.stringify(body) }),
  get: (id: string) => apiFetch<Queue>(`/queues/${id}`),
  update: (id: string, body: Partial<Queue>) =>
    apiFetch<Queue>(`/queues/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => apiFetch<void>(`/queues/${id}`, { method: "DELETE" }),
  pause: (id: string) => apiFetch<Queue>(`/queues/${id}/pause`, { method: "POST" }),
  resume: (id: string) => apiFetch<Queue>(`/queues/${id}/resume`, { method: "POST" }),
  stats: (id: string) => apiFetch<QueueStats>(`/queues/${id}/stats`),
}

// --- jobs ---
export const jobsApi = {
  list: (params: {
    project_id: string
    queue_id?: string
    status?: string
    type?: string
    page?: number
    size?: number
    sort?: string
    order?: string
  }) => apiFetch<Page<Job>>(`/jobs${qs(params)}`),
  create: (body: {
    queue_id: string
    type: string
    handler: string
    payload?: Record<string, unknown>
    priority?: number
    run_at?: string
    max_attempts?: number
    idempotency_key?: string
    depends_on?: string[]
  }) => apiFetch<Job>("/jobs", { method: "POST", body: JSON.stringify(body) }),
  get: (id: string) => apiFetch<Job>(`/jobs/${id}`),
  retry: (id: string) => apiFetch<Job>(`/jobs/${id}/retry`, { method: "POST" }),
  cancel: (id: string) => apiFetch<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
  executions: (id: string) => apiFetch<JobExecution[]>(`/jobs/${id}/executions`),
  logs: (id: string, page = 1, size = 100) =>
    apiFetch<Page<JobLog>>(`/jobs/${id}/logs${qs({ page, size })}`),
  batchProgress: (batchId: string) => apiFetch<JobBatchProgress>(`/jobs/batch/${batchId}`),
  schedule: (body: {
    queue_id: string
    cron_expr: string
    timezone?: string
    handler: string
    payload?: Record<string, unknown>
  }) => apiFetch<ScheduledJob>("/jobs/schedule", { method: "POST", body: JSON.stringify(body) }),
  schedules: (queueId: string) => apiFetch<ScheduledJob[]>(`/jobs/schedule${qs({ queue_id: queueId })}`),
}

// --- workers ---
export const workersApi = {
  list: (projectId: string) => apiFetch<Page<WorkerInfo>>(`/workers${qs({ project_id: projectId, size: 100 })}`),
  get: (id: string) => apiFetch<WorkerInfo>(`/workers/${id}`),
  heartbeats: (id: string, limit = 60) =>
    apiFetch<WorkerHeartbeat[]>(`/workers/${id}/heartbeats${qs({ limit })}`),
}

// --- dlq ---
export const dlqApi = {
  list: (queueId: string) => apiFetch<Page<DeadLetterEntry>>(`/dlq${qs({ queue_id: queueId, size: 100 })}`),
  replay: (id: string) => apiFetch<Job>(`/dlq/${id}/replay`, { method: "POST" }),
}

// --- metrics ---
export const metricsApi = {
  overview: (projectId: string) => apiFetch<MetricsOverview>(`/metrics/overview${qs({ project_id: projectId })}`),
  throughput: (projectId: string, window = "1h") =>
    apiFetch<ThroughputResponse>(`/metrics/throughput${qs({ project_id: projectId, window })}`),
  queues: (projectId: string) => apiFetch<QueueMetric[]>(`/metrics/queues${qs({ project_id: projectId })}`),
}
