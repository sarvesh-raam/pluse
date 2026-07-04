import { useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { CheckCircle2, CircleDot, CircleX, Clock, Sparkles } from "lucide-react"
import { ApiError, jobsApi } from "@/lib/api"
import { formatDateTime, formatDuration } from "@/lib/format"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatusPill, TypeBadge } from "@/components/shared/StatusPill"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

const RETRYABLE = new Set(["failed", "dead"])
const CANCELLABLE = new Set(["scheduled", "queued", "retrying"])

function LifecycleTimeline({ job }: { job: NonNullable<ReturnType<typeof useJob>["data"]> }) {
  const steps = [
    { label: "Created", ts: job.created_at, done: true },
    { label: "Claimed", ts: job.claimed_at, done: !!job.claimed_at },
    { label: "Running", ts: job.started_at, done: !!job.started_at },
    {
      label: job.status === "failed" || job.status === "dead" ? "Failed" : job.status === "cancelled" ? "Cancelled" : "Completed",
      ts: job.finished_at,
      done: !!job.finished_at,
    },
  ]

  return (
    <div className="flex items-center">
      {steps.map((step, i) => (
        <div key={step.label} className="flex flex-1 items-center last:flex-none">
          <div className="flex flex-col items-center gap-1.5">
            {step.done ? (
              <CheckCircle2 className="h-5 w-5 text-success" />
            ) : (
              <CircleDot className="h-5 w-5 text-muted-foreground" />
            )}
            <span className="text-xs font-medium text-foreground">{step.label}</span>
            <span className="text-[11px] text-muted-foreground">{formatDateTime(step.ts)}</span>
          </div>
          {i < steps.length - 1 && (
            <div className={`mx-2 mb-6 h-px flex-1 ${step.done ? "bg-success" : "bg-border"}`} />
          )}
        </div>
      ))}
    </div>
  )
}

function useJob(jobId: string) {
  return useQuery({ queryKey: ["job", jobId], queryFn: () => jobsApi.get(jobId), refetchInterval: 3000 })
}

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()
  const { data: job, isLoading } = useJob(jobId!)

  const { data: executions } = useQuery({
    queryKey: ["executions", jobId],
    queryFn: () => jobsApi.executions(jobId!),
    refetchInterval: 3000,
  })
  const { data: logs } = useQuery({
    queryKey: ["logs", jobId],
    queryFn: () => jobsApi.logs(jobId!),
    refetchInterval: 3000,
  })

  const retryMutation = useMutation({
    mutationFn: () => jobsApi.retry(jobId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job", jobId] })
      toast.success("Job requeued")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Retry failed"),
  })
  const cancelMutation = useMutation({
    mutationFn: () => jobsApi.cancel(jobId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job", jobId] })
      toast.success("Job cancelled")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Cancel failed"),
  })

  if (isLoading || !job) {
    return <Skeleton className="h-64 w-full" />
  }

  const aiSummary = executions?.find((e) => e.ai_summary)?.ai_summary

  return (
    <div>
      <PageHeader
        eyebrow="Job detail"
        title={job.handler}
        description={
          <span className="flex items-center gap-2">
            <StatusPill status={job.status} />
            <TypeBadge type={job.type} />
          </span>
        }
        actions={
          <>
            {RETRYABLE.has(job.status) && (
              <Button size="sm" variant="outline" onClick={() => retryMutation.mutate()} disabled={retryMutation.isPending}>
                <Clock className="mr-1.5 h-3.5 w-3.5" /> Retry
              </Button>
            )}
            {CANCELLABLE.has(job.status) && (
              <Button size="sm" variant="outline" onClick={() => cancelMutation.mutate()} disabled={cancelMutation.isPending}>
                <CircleX className="mr-1.5 h-3.5 w-3.5" /> Cancel
              </Button>
            )}
          </>
        }
      />

      <div className="rounded-[var(--radius)] border border-border bg-surface p-6">
        <LifecycleTimeline job={job} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-[var(--radius)] border border-border bg-surface p-5">
          <p className="eyebrow">Details</p>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-muted-foreground">Attempts</dt><dd>{job.attempts}/{job.max_attempts}</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">Priority</dt><dd>{job.priority}</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">Worker</dt><dd className="truncate max-w-[140px]">{job.worker_id ?? "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">Run at</dt><dd>{formatDateTime(job.run_at)}</dd></div>
            {job.batch_id && <div className="flex justify-between"><dt className="text-muted-foreground">Batch</dt><dd className="truncate max-w-[140px]">{job.batch_id}</dd></div>}
            {job.idempotency_key && <div className="flex justify-between"><dt className="text-muted-foreground">Idempotency key</dt><dd className="truncate max-w-[140px]">{job.idempotency_key}</dd></div>}
          </dl>
        </div>

        <div className="rounded-[var(--radius)] border border-border bg-surface p-5 lg:col-span-2">
          <p className="eyebrow">Payload</p>
          <pre className="mt-3 max-h-40 overflow-auto rounded-md bg-surface-2 p-3 text-xs text-muted-foreground">
            {JSON.stringify(job.payload, null, 2)}
          </pre>
        </div>
      </div>

      {aiSummary && (
        <div className="mt-6 rounded-[var(--radius)] border border-primary/30 bg-primary/5 p-5">
          <p className="eyebrow flex items-center gap-1.5 text-primary">
            <Sparkles className="h-3.5 w-3.5" /> AI failure summary
          </p>
          <p className="mt-2 text-sm text-foreground">{aiSummary}</p>
        </div>
      )}

      <div className="mt-6">
        <p className="eyebrow">Execution history</p>
        <div className="mt-3 overflow-hidden rounded-[var(--radius)] border border-border bg-surface">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Attempt</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {executions?.map((exec) => (
                <TableRow key={exec.id}>
                  <TableCell>{exec.attempt_number}</TableCell>
                  <TableCell className="capitalize text-muted-foreground">{exec.status}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDateTime(exec.started_at)}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDuration(exec.duration_ms)}</TableCell>
                  <TableCell className="max-w-xs truncate text-danger">{exec.error_message ?? "—"}</TableCell>
                </TableRow>
              ))}
              {!executions?.length && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No execution attempts yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="mt-6">
        <p className="eyebrow">Logs</p>
        <div className="mt-3 max-h-72 overflow-auto rounded-[var(--radius)] border border-border bg-surface p-4 font-mono text-xs">
          {logs?.items.length ? (
            logs.items.map((log) => (
              <div key={log.id} className="flex gap-3 py-0.5">
                <span className="shrink-0 text-muted-foreground">{formatDateTime(log.ts)}</span>
                <span
                  className={
                    log.level === "error"
                      ? "text-danger"
                      : log.level === "warn"
                        ? "text-warn"
                        : "text-muted-foreground"
                  }
                >
                  [{log.level}]
                </span>
                <span className="text-foreground">{log.message}</span>
              </div>
            ))
          ) : (
            <p className="text-muted-foreground">No log lines recorded.</p>
          )}
        </div>
      </div>
    </div>
  )
}
