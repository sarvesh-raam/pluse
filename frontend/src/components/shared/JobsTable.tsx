import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { jobsApi } from "@/lib/api"
import { formatRelative } from "@/lib/format"
import { StatusPill, TypeBadge } from "@/components/shared/StatusPill"
import { EmptyState } from "@/components/shared/EmptyState"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

export function JobsTable({
  projectId,
  queueId,
  status,
  type,
  page,
  onPageChange,
}: {
  projectId: string
  queueId?: string
  status?: string
  type?: string
  page: number
  onPageChange: (page: number) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["jobs", projectId, { queueId, status, type, page }],
    queryFn: () =>
      jobsApi.list({
        project_id: projectId,
        queue_id: queueId,
        status,
        type,
        page,
        size: 20,
        sort: "created_at",
        order: "desc",
      }),
    refetchInterval: 4000,
  })

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    )
  }

  if (!data?.items.length) {
    return <EmptyState title="No jobs found" description="Try adjusting your filters, or enqueue a job." />
  }

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-surface">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Handler</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Attempts</TableHead>
              <TableHead>Run at</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((job) => (
              <TableRow key={job.id} className="cursor-pointer">
                <TableCell>
                  <Link
                    to={`/app/jobs/${job.id}`}
                    className="block font-medium text-foreground hover:text-primary"
                  >
                    {job.handler}
                  </Link>
                </TableCell>
                <TableCell>
                  <TypeBadge type={job.type} />
                </TableCell>
                <TableCell>
                  <StatusPill status={job.status} />
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {job.attempts}/{job.max_attempts}
                </TableCell>
                <TableCell className="text-muted-foreground">{formatRelative(job.run_at)}</TableCell>
                <TableCell className="text-muted-foreground">{formatRelative(job.updated_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Page {data.page} of {Math.max(data.pages, 1)} · {data.total} jobs
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= data.pages}
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
