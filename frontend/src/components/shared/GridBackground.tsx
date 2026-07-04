import { cn } from "@/lib/utils"

export function GridBackground({ className }: { className?: string }) {
  return (
    <div
      className={cn("grid-bg pointer-events-none absolute inset-0", className)}
      aria-hidden="true"
    />
  )
}
