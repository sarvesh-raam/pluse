import { useState } from "react"
import { useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useAuthStore } from "@/lib/auth-store"
import { ApiError, queuesApi } from "@/lib/api"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatCard } from "@/components/shared/StatCard"
import { JobsTable } from "@/components/shared/JobsTable"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"

export function QueueDetail() {
  const { queueId } = useParams<{ queueId: string }>()
  const projectId = useAuthStore((s) => s.currentProjectId)!
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)

  const { data: queue, isLoading } = useQuery({
    queryKey: ["queue", queueId],
    queryFn: () => queuesApi.get(queueId!),
  })
  const { data: stats } = useQuery({
    queryKey: ["queueStats", queueId],
    queryFn: () => queuesApi.stats(queueId!),
    refetchInterval: 3000,
  })

  const [concurrency, setConcurrency] = useState<string | null>(null)
  const [priority, setPriority] = useState<string | null>(null)

  const updateMutation = useMutation({
    mutationFn: () =>
      queuesApi.update(queueId!, {
        concurrency_limit: concurrency !== null ? Number(concurrency) : undefined,
        priority_default: priority !== null ? Number(priority) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queue", queueId] })
      queryClient.invalidateQueries({ queryKey: ["queues"] })
      toast.success("Queue updated")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Update failed"),
  })

  const toggleMutation = useMutation({
    mutationFn: () => (queue?.is_paused ? queuesApi.resume(queueId!) : queuesApi.pause(queueId!)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queue", queueId] })
      toast.success(queue?.is_paused ? "Queue resumed" : "Queue paused")
    },
  })

  if (isLoading || !queue) return <Skeleton className="h-64 w-full" />

  return (
    <div>
      <PageHeader
        eyebrow="Queue"
        title={queue.name}
        description={queue.is_paused ? "Paused — no new jobs will be claimed" : "Active"}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Active</span>
            <Switch checked={!queue.is_paused} onCheckedChange={() => toggleMutation.mutate()} />
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Queued" value={stats?.queued ?? "—"} />
        <StatCard label="Running" value={stats?.running ?? "—"} />
        <StatCard label="Completed" value={stats?.completed ?? "—"} />
        <StatCard label="Dead" value={stats?.dead ?? "—"} />
      </div>

      <div className="mt-6 rounded-[var(--radius)] border border-border bg-surface p-5">
        <p className="eyebrow">Configuration</p>
        <form
          className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault()
            updateMutation.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label>Concurrency limit</Label>
            <Input
              type="number"
              min={1}
              defaultValue={queue.concurrency_limit}
              onChange={(e) => setConcurrency(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Default priority</Label>
            <Input
              type="number"
              defaultValue={queue.priority_default}
              onChange={(e) => setPriority(e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <Button type="submit" disabled={updateMutation.isPending}>
              Save changes
            </Button>
          </div>
        </form>
      </div>

      <div className="mt-6">
        <p className="eyebrow mb-3">Jobs in this queue</p>
        <JobsTable projectId={projectId} queueId={queueId} page={page} onPageChange={setPage} />
      </div>
    </div>
  )
}
