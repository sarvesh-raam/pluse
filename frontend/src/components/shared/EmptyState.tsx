import type { ReactNode } from "react"
import { GridBackground } from "@/components/shared/GridBackground"

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="relative overflow-hidden rounded-[var(--radius)] border border-border bg-surface px-6 py-16 text-center">
      <GridBackground />
      <div className="relative">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        {action && <div className="mt-4 flex justify-center">{action}</div>}
      </div>
    </div>
  )
}
