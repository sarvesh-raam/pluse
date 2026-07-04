import { useRef } from "react"

const store = new Map<string, number[]>()

/** Accumulates a rolling client-side history for a numeric value that's
 * refetched periodically (e.g. queue depth). There's no persisted
 * per-queue time-series endpoint, so this builds a live trend in-memory
 * for the session instead of adding a metrics-history table just for a
 * sparkline. Resets on page reload. */
export function useRollingHistory(key: string, value: number | undefined, maxPoints = 20): number[] {
  const ref = useRef<number[]>(store.get(key) ?? [])

  if (value !== undefined) {
    const history = store.get(key) ?? []
    const last = history[history.length - 1]
    if (last !== value) {
      const next = [...history, value].slice(-maxPoints)
      store.set(key, next)
      ref.current = next
    } else {
      ref.current = history
    }
  }

  return ref.current
}
