import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Skull } from "lucide-react"
import { useAuthStore } from "@/lib/auth-store"
import { ApiError, chaosApi, workersApi } from "@/lib/api"
import { formatRelative, isFreshHeartbeat } from "@/lib/format"
import { PageHeader } from "@/components/shared/PageHeader"

import { EmptyState } from "@/components/shared/EmptyState"
import { ChaosPanel } from "@/components/shared/ChaosPanel"
import { UtilizationChart } from "@/components/charts/UtilizationChart"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

function WorkerCard({ workerId, projectId }: { workerId: string; projectId: string }) {
  const queryClient = useQueryClient()
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

  const killMutation = useMutation({
    mutationFn: () => chaosApi.kill(projectId, workerId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["worker", workerId] })
      queryClient.invalidateQueries({ queryKey: ["chaosStatus", projectId] })
      toast.warning(`Killed ${result.worker_name}`, { description: result.detail })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Chaos kill failed"),
  })

  if (!worker) return null
  const fresh = isFreshHeartbeat(worker.last_heartbeat_at)
  const runningNow = heartbeats?.[heartbeats.length - 1]?.running_jobs ?? 0
  const killable = fresh && worker.status !== "dead" && worker.status !== "draining" && !worker.chaos_kill_requested_at

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
          <span className="text-xs capitalize text-muted-foreground">
            {worker.chaos_kill_requested_at && worker.status !== "dead" ? "killed…" : worker.status}
          </span>
          {killable && (
            <Button
              size="icon"
              variant="ghost"
              className="ml-1 h-6 w-6 text-danger hover:text-danger"
              title="Chaos: kill this worker"
              aria-label={`Kill ${worker.name}`}
              disabled={killMutation.isPending}
              onClick={() => killMutation.mutate()}
            >
              <Skull className="h-3.5 w-3.5" />
            </Button>
          )}
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

      <ChaosPanel className="mb-6" />

      {workers?.items.length ? (
        <div data-tour="worker-cards" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workers.items.map((w) => (
            <WorkerCard key={w.id} workerId={w.id} projectId={projectId} />
          ))}
        </div>
      ) : (
        <EmptyState title="No workers registered" description="Start a worker process to see it here." />
      )}
    </div>
  )
}
