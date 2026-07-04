import type { JobStatus } from "@/types/api"

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

export function formatRelative(iso: string | null): string {
  if (!iso) return "—"
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffSec = Math.round(diffMs / 1000)
  if (diffSec < 5) return "just now"
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  const diffDay = Math.round(diffHour / 24)
  return `${diffDay}d ago`
}

export function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return "—"
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
}

export function formatPercent(value: number | null): string {
  if (value === null || value === undefined) return "—"
  return `${(value * 100).toFixed(1)}%`
}

export const STATUS_META: Record<JobStatus, { label: string; className: string; animated?: boolean }> = {
  scheduled: { label: "Scheduled", className: "bg-muted text-muted-foreground border-border" },
  queued: { label: "Queued", className: "bg-info/15 text-info border-info/30" },
  claimed: { label: "Claimed", className: "bg-primary/15 text-primary border-primary/30", animated: true },
  running: { label: "Running", className: "bg-primary/15 text-primary border-primary/30", animated: true },
  completed: { label: "Completed", className: "bg-success/15 text-success border-success/30" },
  failed: { label: "Failed", className: "bg-warn/15 text-warn border-warn/30" },
  retrying: { label: "Retrying", className: "bg-warn/15 text-warn border-warn/30", animated: true },
  dead: { label: "Dead", className: "bg-danger/15 text-danger border-danger/30" },
  cancelled: { label: "Cancelled", className: "bg-muted text-muted-foreground border-border" },
}

export function isFreshHeartbeat(lastHeartbeatAt: string | null, timeoutSec = 30): boolean {
  if (!lastHeartbeatAt) return false
  return Date.now() - new Date(lastHeartbeatAt).getTime() < timeoutSec * 1000
}
