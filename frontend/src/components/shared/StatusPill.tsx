import type { JobStatus } from "@/types/api"
import { STATUS_META } from "@/lib/format"
import { cn } from "@/lib/utils"

export function StatusPill({ status, className }: { status: JobStatus; className?: string }) {
  const meta = STATUS_META[status]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        meta.className,
        className
      )}
    >
      {meta.animated && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-current" />}
      {meta.label}
    </span>
  )
}

const TYPE_LABEL: Record<string, string> = {
  immediate: "Immediate",
  delayed: "Delayed",
  scheduled: "Scheduled",
  recurring: "Recurring",
  batch: "Batch",
}

export function TypeBadge({ type, className }: { type: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-surface-2 px-2 py-0.5 text-xs text-muted-foreground",
        className
      )}
    >
      {TYPE_LABEL[type] ?? type}
    </span>
  )
}
