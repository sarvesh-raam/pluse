import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useAuthStore } from "@/lib/auth-store"
import { Play, Loader2, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, jobsApi, queuesApi } from "@/lib/api"
import { cn } from "@/lib/utils"

const MAX_JOBS = 1000

export function LoadGenerator({ className }: { className?: string }) {
  const projectId = useAuthStore((s) => s.currentProjectId)!
  const queryClient = useQueryClient()
  const { data: queues } = useQuery({
    queryKey: ["queues", projectId],
    queryFn: () => queuesApi.list(projectId),
  })

  const queue = queues?.items?.[0]
  const [jobCount, setJobCount] = useState(100)
  const [isFiring, setIsFiring] = useState(false)

  const handleFire = async () => {
    if (!queue) return
    setIsFiring(true)
    try {
      // One request through the batch endpoint (max 1000 jobs, a single
      // transaction) instead of N parallel POSTs — fewer round trips, no
      // partial blasts, and it's what the endpoint exists for.
      const result = await jobsApi.createBatch({
        queue_id: queue.id,
        jobs: Array.from({ length: jobCount }, () => ({ handler: "sleep", payload: { seconds: 1 } })),
      })
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
      toast.success(`Enqueued ${result.jobs.length} jobs on "${queue.name}"`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to enqueue jobs")
    } finally {
      setIsFiring(false)
    }
  }

  return (
    <div className={cn("relative overflow-hidden rounded-2xl border border-border bg-surface p-6", className)}>
      <div className="absolute inset-0 bg-gradient-to-br from-brand/5 to-transparent pointer-events-none" />

      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-brand" />
            <h3 className="font-semibold text-foreground">Load Generator</h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Stress test event-driven dispatch (LISTEN/NOTIFY) on queue:{" "}
            <strong className="text-foreground">{queue?.name ?? (queues ? "no queues yet" : "Loading...")}</strong>
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 rounded-full border border-border bg-background px-4 py-1.5">
            <Input
              type="number"
              min={1}
              max={MAX_JOBS}
              value={jobCount}
              onChange={(e) => setJobCount(Math.min(MAX_JOBS, Math.max(1, parseInt(e.target.value) || 1)))}
              className="w-16 h-8 text-center"
              disabled={isFiring || !queue}
              aria-label="Number of jobs"
            />
            <input
              type="range"
              min="1"
              max={MAX_JOBS}
              value={jobCount}
              onChange={(e) => setJobCount(parseInt(e.target.value))}
              disabled={isFiring || !queue}
              className="w-24 accent-brand"
              aria-label="Number of jobs"
            />
          </div>

          <Button
            size="sm"
            disabled={isFiring || !queue}
            onClick={handleFire}
            className="rounded-full bg-brand px-6 text-brand-foreground hover:bg-brand/90 min-w-[120px]"
            nativeButton
          >
            {isFiring ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4 fill-current" />
            )}
            Blast Jobs
          </Button>
        </div>
      </div>
    </div>
  )
}
