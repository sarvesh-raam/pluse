import { cn } from "@/lib/utils"

export function LivePulseBadge({ connected }: { connected: boolean }) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        connected
          ? "border-success/30 bg-success/10 text-success"
          : "border-border bg-surface-2 text-muted-foreground"
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full bg-current",
          connected && "pulse-dot"
        )}
      />
      {connected ? "Live" : "Polling"}
    </div>
  )
}
