import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Activity, CheckCircle2, Cpu, ListOrdered } from "lucide-react"
import { useAuthStore } from "@/lib/auth-store"
import { jobsApi, metricsApi, workersApi } from "@/lib/api"
import { formatPercent, formatRelative, isFreshHeartbeat } from "@/lib/format"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatCard } from "@/components/shared/StatCard"
import { StatusPill } from "@/components/shared/StatusPill"
import { EmptyState } from "@/components/shared/EmptyState"
import { ThroughputChart } from "@/components/charts/ThroughputChart"
import { LoadGenerator } from "@/components/shared/LoadGenerator"
import { Skeleton } from "@/components/ui/skeleton"

export function Dashboard() {
  const projectId = useAuthStore((s) => s.currentProjectId)!

  const { data: overview } = useQuery({
    queryKey: ["metricsOverview", projectId],
    queryFn: () => metricsApi.overview(projectId),
    refetchInterval: 5000,
  })
  const { data: throughput } = useQuery({
    queryKey: ["throughput", projectId, "1h"],
    queryFn: () => metricsApi.throughput(projectId, "1h"),
    refetchInterval: 5000,
  })
  const { data: failedJobs } = useQuery({
    queryKey: ["jobs", projectId, { status: "failed" }],
    queryFn: () => jobsApi.list({ project_id: projectId, status: "failed", size: 6, sort: "updated_at" }),
    refetchInterval: 5000,
  })
  const { data: workers } = useQuery({
    queryKey: ["workers", projectId],
    queryFn: () => workersApi.list(projectId),
    refetchInterval: 5000,
  })
  const { data: queues } = useQuery({
    queryKey: ["queues", projectId],
    queryFn: () => queuesApi.list(projectId),
  })

  const firstQueue = queues?.items[0]

  return (
    <div>
      <PageHeader eyebrow="Overview" title="Dashboard" description="Live view of your project's job pipeline." />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Throughput"
          value={overview ? overview.throughput_per_min.toFixed(1) : <Skeleton className="h-9 w-16" />}
          caption="jobs / min (5m avg)"
          icon={<Activity className="h-4 w-4" />}
        />
        <StatCard
          label="Success rate"
          value={overview ? formatPercent(overview.success_rate) : <Skeleton className="h-9 w-16" />}
          caption="last hour"
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <StatCard
          label="Active workers"
          value={overview ? overview.active_workers : <Skeleton className="h-9 w-16" />}
          caption="reporting heartbeats"
          icon={<Cpu className="h-4 w-4" />}
        />
        <StatCard
          label="Queue depth"
          value={overview ? overview.queue_depth_total : <Skeleton className="h-9 w-16" />}
          caption="jobs waiting"
          icon={<ListOrdered className="h-4 w-4" />}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="relative rounded-[var(--radius)] border border-border bg-surface p-5 lg:col-span-2">
          <p className="eyebrow">Throughput</p>
          <h2 className="mt-1 text-sm font-medium text-foreground">Completed vs. failed (last hour)</h2>
          <div className="mt-4">
            {throughput ? <ThroughputChart buckets={throughput.buckets} /> : <Skeleton className="h-60 w-full" />}
          </div>
        </div>

        <div className="rounded-[var(--radius)] border border-border bg-surface p-5">
          <p className="eyebrow">Worker status</p>
          <h2 className="mt-1 text-sm font-medium text-foreground">Fleet</h2>
          <div className="mt-4 space-y-3">
            {workers?.items.length ? (
              workers.items.slice(0, 6).map((w) => {
                const fresh = isFreshHeartbeat(w.last_heartbeat_at)
                return (
                  <div key={w.id} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2 w-2 rounded-full ${fresh ? "bg-success pulse-dot" : "bg-danger"}`}
                      />
                      <span className="truncate text-foreground">{w.name}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{w.status}</span>
                  </div>
                )
              })
            ) : (
              <p className="text-sm text-muted-foreground">No workers registered yet.</p>
            )}
          </div>
          <Link to="/app/workers" className="mt-4 inline-block text-xs text-primary hover:underline">
            View all workers →
          </Link>
        </div>
      </div>

      <div className="mt-6">
        <LoadGenerator />
      </div>

      <div className="mt-6">
        <p className="eyebrow">Recent failures</p>
        <h2 className="mt-1 mb-4 text-sm font-medium text-foreground">Needs attention</h2>
        {failedJobs?.items.length ? (
          <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-surface">
            {failedJobs.items.map((job) => (
              <Link
                key={job.id}
                to={`/app/jobs/${job.id}`}
                className="flex items-center justify-between border-b border-border px-4 py-3 text-sm last:border-b-0 hover:bg-surface-2"
              >
                <div className="flex items-center gap-3">
                  <StatusPill status={job.status} />
                  <span className="text-foreground">{job.handler}</span>
                  <span className="text-xs text-muted-foreground">
                    attempt {job.attempts}/{job.max_attempts}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">{formatRelative(job.updated_at)}</span>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="No recent failures" description="Everything's running smoothly." />
        )}
      </div>
    </div>
  )
}
