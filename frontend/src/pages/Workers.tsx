import { useQuery } from "@tanstack/react-query"
import { useAuthStore } from "@/lib/auth-store"
import { workersApi } from "@/lib/api"
import { formatRelative, isFreshHeartbeat } from "@/lib/format"
import { PageHeader } from "@/components/shared/PageHeader"

import { EmptyState } from "@/components/shared/EmptyState"
import { UtilizationChart } from "@/components/charts/UtilizationChart"
import { cn } from "@/lib/utils"

function WorkerCard({ workerId }: { workerId: string }) {
  const { data: worker } = useQuery({
    queryKey: ["worker", workerId],
    queryFn: () => workersApi.get(workerId),
    refetchInterval: 4000,
  })
  const { data: heartbeats } = useQuery({
    queryKey: ["workerHeartbeats", workerId],
    queryFn: () => workersApi.heartbeats(workerId, 40),
    refetchInterval: 4000,
  })

  if (!worker) return null
  const fresh = isFreshHeartbeat(worker.last_heartbeat_at)
  const runningNow = heartbeats?.[heartbeats.length - 1]?.running_jobs ?? 0

  return (
    <div className="relative rounded-[var(--radius)] border border-border bg-surface p-5">

      <div className="flex items-start justify-between">
        <div>
          <p className="truncate text-sm font-medium text-foreground">{worker.name}</p>
          <p className="text-xs text-muted-foreground">{worker.hostname}</p>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={cn("h-2 w-2 rounded-full", fresh ? "bg-success pulse-dot" : "bg-danger")}
            title={fresh ? "Heartbeat fresh" : "Heartbeat stale"}
          />
          <span className="text-xs capitalize text-muted-foreground">{worker.status}</span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-muted-foreground">Running</p>
          <p className="mt-0.5 text-base font-semibold text-foreground">
            {runningNow}/{worker.concurrency}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Last heartbeat</p>
          <p className="mt-0.5 text-foreground">{formatRelative(worker.last_heartbeat_at)}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {worker.queues.map((q) => (
          <span key={q} className="rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted-foreground">
            {q === "*" ? "All queues" : q}
          </span>
        ))}
      </div>

      <div className="mt-4">
        <p className="mb-1 text-[11px] text-muted-foreground">Utilization</p>
        {heartbeats ? <UtilizationChart heartbeats={heartbeats} /> : null}
      </div>
    </div>
  )
}

export function Workers() {
  const projectId = useAuthStore((s) => s.currentProjectId)!
  const { data: workers } = useQuery({
    queryKey: ["workers", projectId],
    queryFn: () => workersApi.list(projectId),
    refetchInterval: 4000,
  })

  return (
    <div>
      <PageHeader
        eyebrow="Fleet"
        title="Workers"
        description="Heartbeat freshness, running jobs, and subscribed queues."
      />

      {workers?.items.length ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workers.items.map((w) => (
            <WorkerCard key={w.id} workerId={w.id} />
          ))}
        </div>
      ) : (
        <EmptyState title="No workers registered" description="Start a worker process to see it here." />
      )}
    </div>
  )
}
