import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { RotateCcw } from "lucide-react"
import { useAuthStore } from "@/lib/auth-store"
import { ApiError, dlqApi, queuesApi } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { PageHeader } from "@/components/shared/PageHeader"
import { EmptyState } from "@/components/shared/EmptyState"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export function Dlq() {
  const projectId = useAuthStore((s) => s.currentProjectId)!
  const queryClient = useQueryClient()
  const [queueId, setQueueId] = useState<string>("")

  const { data: queues } = useQuery({ queryKey: ["queues", projectId], queryFn: () => queuesApi.list(projectId) })

  useEffect(() => {
    if (!queueId && queues?.items.length) setQueueId(queues.items[0].id)
  }, [queues, queueId])

  const { data: entries } = useQuery({
    queryKey: ["dlq", queueId],
    queryFn: () => dlqApi.list(queueId),
    enabled: !!queueId,
    refetchInterval: 5000,
  })

  const replayMutation = useMutation({
    mutationFn: (id: string) => dlqApi.replay(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dlq", queueId] })
      toast.success("Job replayed — back in the queue")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Replay failed"),
  })

  return (
    <div>
      <PageHeader
        eyebrow="Dead letter queue"
        title="Failed jobs"
        description="Jobs that exhausted every retry attempt. Replay to give them another shot."
        actions={
          <Select
            items={Object.fromEntries(queues?.items.map((q) => [q.id, q.name]) ?? [])}
            value={queueId}
            onValueChange={(v) => setQueueId(v ?? "")}
          >
            <SelectTrigger size="sm" className="w-44">
              <SelectValue placeholder="Queue" />
            </SelectTrigger>
            <SelectContent>
              {queues?.items.map((q) => (
                <SelectItem key={q.id} value={q.id}>
                  {q.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      {entries?.items.length ? (
        <div data-tour="dlq-table" className="overflow-hidden rounded-[var(--radius)] border border-border bg-surface">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Failed at</TableHead>
                <TableHead>Attempts</TableHead>
                <TableHead>Final error</TableHead>
                <TableHead>Replayed</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="text-muted-foreground">{formatDateTime(entry.failed_at)}</TableCell>
                  <TableCell className="text-muted-foreground">{entry.total_attempts}</TableCell>
                  <TableCell className="max-w-md truncate text-danger">{entry.final_error}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {entry.replayed_at ? formatDateTime(entry.replayed_at) : "—"}
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!!entry.replayed_at || replayMutation.isPending}
                      onClick={() => replayMutation.mutate(entry.id)}
                    >
                      <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Replay
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState title="No dead letters" description="Jobs that exhaust every retry will show up here." />
      )}
    </div>
  )
}
