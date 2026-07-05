import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export function StatCard({
  label,
  value,
  caption,
  icon,
  className,
}: {
  label: string
  value: ReactNode
  caption?: ReactNode
  icon?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "relative rounded-[var(--radius)] border border-border bg-surface p-5",
        className
      )}
    >

      <div className="flex items-start justify-between">
        <p className="eyebrow">{label}</p>
        {icon && <div className="text-muted-foreground">{icon}</div>}
      </div>
      <div className="stat-number mt-2">{value}</div>
      {caption && <p className="mt-1 text-xs text-muted-foreground">{caption}</p>}
    </div>
  )
}
