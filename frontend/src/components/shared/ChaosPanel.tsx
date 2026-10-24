import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Flame, Loader2, Skull } from "lucide-react"
import { ApiError, chaosApi } from "@/lib/api"
import { useAuthStore } from "@/lib/auth-store"
import { formatRelative } from "@/lib/format"
import type { ChaosKillResult } from "@/types/api"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface KillEvent extends ChaosKillResult {
  at: string
}

/** Kills a live worker for real (pod delete on Kubernetes, hard process
 * exit elsewhere) so you can watch the platform heal: the orchestrator
 * restarts it, and the reaper requeues its in-flight jobs once its
 * heartbeat goes stale. */
export function ChaosPanel({ className }: { className?: string }) {
  const projectId = useAuthStore((s) => s.currentProjectId)!
  const queryClient = useQueryClient()
  const [history, setHistory] = useState<KillEvent[]>([])

  const { data: status } = useQuery({
    queryKey: ["chaosStatus", projectId],
    queryFn: () => chaosApi.status(projectId),
    refetchInterval: 3000,
  })

  const killMutation = useMutation({
    mutationFn: () => chaosApi.kill(projectId),
    onSuccess: (result) => {
      setHistory((h) => [{ ...result, at: new Date().toISOString() }, ...h].slice(0, 5))
      queryClient.invalidateQueries({ queryKey: ["workers"] })
      queryClient.invalidateQueries({ queryKey: ["chaosStatus", projectId] })
      toast.warning(`Killed ${result.worker_name}`, { description: result.detail })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Chaos kill failed"),
  })

  const disabled = !status?.enabled || !status.live_workers || killMutation.isPending

  return (
    <div className={cn("relative overflow-hidden rounded-2xl border border-danger/30 bg-surface p-6", className)}>
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-danger/5 to-transparent" />

      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Flame className="h-4 w-4 text-danger" />
            <h3 className="font-semibold text-foreground">Chaos engineering</h3>
          </div>
          <p className="mt-1 max-w-xl text-xs text-muted-foreground">
            Hard-kill a live worker mid-job. Its supervisor restarts it and the reaper recovers stranded jobs
            once the heartbeat goes stale.{" "}
            {status && (
              <>
                Mode: <strong className="text-foreground">{status.mode === "kubernetes" ? "pod delete" : "process kill"}</strong>
                {" · "}
                <strong className="text-foreground">{status.live_workers}</strong> live worker
                {status.live_workers === 1 ? "" : "s"}
              </>
            )}
            {status && !status.enabled && <span className="ml-1 text-danger">(disabled on this deployment)</span>}
          </p>
        </div>

        <Button
          size="sm"
          disabled={disabled}
          onClick={() => killMutation.mutate()}
          className="min-w-[160px] rounded-full bg-danger px-6 text-white hover:bg-danger/90"
          data-tour="chaos-button"
        >
          {killMutation.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Skull className="mr-2 h-4 w-4" />
          )}
          Kill a random worker
        </Button>
      </div>

      {history.length > 0 && (
        <ul className="relative mt-4 space-y-1.5 border-t border-border pt-4 text-xs">
          {history.map((event) => (
            <li key={event.at} className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
              <span className="text-muted-foreground">{formatRelative(event.at)}</span>
              <span className="font-medium text-foreground">{event.worker_name}</span>
              <span className="text-muted-foreground">{event.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
