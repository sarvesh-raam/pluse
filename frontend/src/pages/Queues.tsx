import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { Plus } from "lucide-react"
import { useAuthStore } from "@/lib/auth-store"
import { ApiError, metricsApi, queuesApi, retryPoliciesApi } from "@/lib/api"
import { useRollingHistory } from "@/hooks/useRollingHistory"
import { PageHeader } from "@/components/shared/PageHeader"
import { EmptyState } from "@/components/shared/EmptyState"
import { Sparkline } from "@/components/charts/Sparkline"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

function QueueRow({ queue, depth, successRate }: {
  queue: { id: string; name: string; priority_default: number; concurrency_limit: number; is_paused: boolean }
  depth: number
  successRate: number | null
}) {
  const queryClient = useQueryClient()
  const history = useRollingHistory(`queue-depth-${queue.id}`, depth)

  const toggleMutation = useMutation({
    mutationFn: () => (queue.is_paused ? queuesApi.resume(queue.id) : queuesApi.pause(queue.id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queues"] })
      toast.success(queue.is_paused ? "Queue resumed" : "Queue paused")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to update queue"),
  })

  return (
    <TableRow>
      <TableCell>
        <Link to={`/app/queues/${queue.id}`} className="font-medium text-foreground hover:text-primary">
          {queue.name}
        </Link>
      </TableCell>
      <TableCell className="text-muted-foreground">{queue.priority_default}</TableCell>
      <TableCell className="text-muted-foreground">{queue.concurrency_limit}</TableCell>
      <TableCell className="text-muted-foreground">{depth}</TableCell>
      <TableCell className="text-muted-foreground">
        {successRate !== null ? `${(successRate * 100).toFixed(0)}%` : "—"}
      </TableCell>
      <TableCell>
        <Sparkline data={history} />
      </TableCell>
      <TableCell>
        <Switch
          checked={!queue.is_paused}
          onCheckedChange={() => toggleMutation.mutate()}
          disabled={toggleMutation.isPending}
          aria-label="Toggle queue active"
        />
      </TableCell>
    </TableRow>
  )
}

function CreateQueueDialog({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [concurrency, setConcurrency] = useState("5")
  const [priority, setPriority] = useState("0")
  const [retryPolicyId, setRetryPolicyId] = useState<string>("")

  const { data: retryPolicies } = useQuery({
    queryKey: ["retryPolicies", projectId],
    queryFn: () => retryPoliciesApi.list(projectId),
  })

  const createMutation = useMutation({
    mutationFn: () =>
      queuesApi.create({
        project_id: projectId,
        name,
        concurrency_limit: Number(concurrency),
        priority_default: Number(priority),
        retry_policy_id: retryPolicyId || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queues"] })
      toast.success("Queue created")
      setOpen(false)
      setName("")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to create queue"),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm" className="glow-cta">
            <Plus className="mr-1.5 h-4 w-4" /> New queue
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create queue</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="queue_name">Name</Label>
            <Input id="queue_name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="concurrency">Concurrency limit</Label>
              <Input
                id="concurrency"
                type="number"
                min={1}
                value={concurrency}
                onChange={(e) => setConcurrency(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="priority">Default priority</Label>
              <Input
                id="priority"
                type="number"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Retry policy</Label>
            <Select
              items={Object.fromEntries(
                retryPolicies?.items.map((rp) => [rp.id, `${rp.name} (${rp.strategy})`]) ?? []
              )}
              value={retryPolicyId}
              onValueChange={(v) => setRetryPolicyId(v ?? "")}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                {retryPolicies?.items.map((rp) => (
                  <SelectItem key={rp.id} value={rp.id}>
                    {rp.name} ({rp.strategy})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create queue"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Queues() {
  const projectId = useAuthStore((s) => s.currentProjectId)!

  const { data: queues } = useQuery({
    queryKey: ["queues", projectId],
    queryFn: () => queuesApi.list(projectId),
    refetchInterval: 4000,
  })
  const { data: metrics } = useQuery({
    queryKey: ["queueMetrics", projectId],
    queryFn: () => metricsApi.queues(projectId),
    refetchInterval: 4000,
  })

  const metricsByQueue = new Map(metrics?.map((m) => [m.queue_id, m]))

  return (
    <div>
      <PageHeader
        eyebrow="Queue health"
        title="Queues"
        description="Priority, concurrency, live depth, and pause controls."
        actions={<CreateQueueDialog projectId={projectId} />}
      />

      {queues?.items.length ? (
        <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-surface">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Concurrency</TableHead>
                <TableHead>Depth</TableHead>
                <TableHead>Success</TableHead>
                <TableHead>Trend</TableHead>
                <TableHead>Active</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {queues.items.map((q) => (
                <QueueRow
                  key={q.id}
                  queue={q}
                  depth={metricsByQueue.get(q.id)?.depth ?? 0}
                  successRate={metricsByQueue.get(q.id)?.success_rate ?? null}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState title="No queues yet" description="Create your first queue to start enqueueing jobs." />
      )}
    </div>
  )
}
