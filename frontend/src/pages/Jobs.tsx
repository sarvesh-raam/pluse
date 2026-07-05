import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Plus } from "lucide-react"
import { useAuthStore } from "@/lib/auth-store"
import { ApiError, jobsApi, queuesApi } from "@/lib/api"
import { PageHeader } from "@/components/shared/PageHeader"
import { JobsTable } from "@/components/shared/JobsTable"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

const HANDLERS = ["sleep", "http_call", "fail_n_times", "flaky", "compute"]

function EnqueueJobDialog({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [queueId, setQueueId] = useState("")
  const [handler, setHandler] = useState(HANDLERS[0])
  const [type, setType] = useState<"immediate" | "delayed" | "scheduled">("immediate")
  const [payload, setPayload] = useState("{}")
  const [delaySec, setDelaySec] = useState("60")

  const { data: queues } = useQuery({ queryKey: ["queues", projectId], queryFn: () => queuesApi.list(projectId) })

  const createMutation = useMutation({
    mutationFn: () => {
      let parsedPayload: Record<string, unknown> = {}
      try {
        parsedPayload = JSON.parse(payload || "{}")
      } catch {
        throw new ApiError(422, "invalid_payload", "Payload must be valid JSON")
      }
      const run_at =
        type !== "immediate" ? new Date(Date.now() + Number(delaySec) * 1000).toISOString() : undefined
      return jobsApi.create({ queue_id: queueId, type, handler, payload: parsedPayload, run_at })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
      toast.success("Job enqueued")
      setOpen(false)
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to enqueue job"),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button data-tour="enqueue-job-btn" size="sm" className="glow-cta">
            <Plus className="mr-1.5 h-4 w-4" /> Enqueue job
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Enqueue job</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label>Queue</Label>
            <Select
              items={Object.fromEntries(queues?.items.map((q) => [q.id, q.name]) ?? [])}
              value={queueId}
              onValueChange={(v) => setQueueId(v ?? "")}
              required
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a queue" />
              </SelectTrigger>
              <SelectContent>
                {queues?.items.map((q) => (
                  <SelectItem key={q.id} value={q.id}>
                    {q.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Handler</Label>
              <Select value={handler} onValueChange={(v) => setHandler(v ?? HANDLERS[0])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HANDLERS.map((h) => (
                    <SelectItem key={h} value={h}>
                      {h}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select value={type} onValueChange={(v) => v && setType(v as typeof type)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="immediate">Immediate</SelectItem>
                  <SelectItem value="delayed">Delayed</SelectItem>
                  <SelectItem value="scheduled">Scheduled</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {type !== "immediate" && (
            <div className="space-y-1.5">
              <Label>Run in (seconds from now)</Label>
              <Input type="number" min={1} value={delaySec} onChange={(e) => setDelaySec(e.target.value)} />
            </div>
          )}
          <div className="space-y-1.5">
            <Label>Payload (JSON)</Label>
            <textarea
              className="w-full rounded-md border border-border bg-surface-2 p-2 font-mono text-xs text-foreground"
              rows={4}
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!queueId || createMutation.isPending}>
              {createMutation.isPending ? "Enqueueing..." : "Enqueue"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Jobs() {
  const projectId = useAuthStore((s) => s.currentProjectId)!
  const [status, setStatus] = useState<string>("")
  const [type, setType] = useState<string>("")
  const [page, setPage] = useState(1)

  return (
    <div>
      <PageHeader
        eyebrow="Jobs explorer"
        title="Jobs"
        description="Every job across your queues, filterable by status and type."
        actions={<EnqueueJobDialog projectId={projectId} />}
      />

      <div className="mb-4 flex gap-3">
        <Select
          value={status || "all"}
          onValueChange={(v) => {
            setStatus(v && v !== "all" ? v : "")
            setPage(1)
          }}
        >
          <SelectTrigger size="sm" className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {["scheduled", "queued", "claimed", "running", "completed", "failed", "retrying", "dead", "cancelled"].map(
              (s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              )
            )}
          </SelectContent>
        </Select>

        <Select
          value={type || "all"}
          onValueChange={(v) => {
            setType(v && v !== "all" ? v : "")
            setPage(1)
          }}
        >
          <SelectTrigger size="sm" className="w-40">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {["immediate", "delayed", "scheduled", "recurring", "batch"].map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div data-tour="jobs-table">
        <JobsTable projectId={projectId} status={status} type={type} page={page} onPageChange={setPage} />
      </div>
    </div>
  )
}
