import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuthStore } from "@/lib/auth-store"

interface WsEvent {
  type: "job.updated" | "worker.updated" | "queue.stats" | "metrics.tick"
  data: Record<string, unknown>
}

/** Subscribes to /ws for a project and patches the TanStack Query cache as
 * events arrive. Falls back gracefully: if the socket never connects (or
 * drops), callers still get fresh data via each query's own refetchInterval. */
export function useLiveUpdates(projectId: string | null) {
  const queryClient = useQueryClient()
  const accessToken = useAuthStore((s) => s.accessToken)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!projectId || !accessToken) return

    let cancelled = false
    let socket: WebSocket | null = null
    let retryTimeout: ReturnType<typeof setTimeout> | null = null
    let attempt = 0

    // A burst of events (up to 200 job.updated per publisher tick) used to
    // trigger one invalidation each — hundreds of refetch storms per second.
    // Collect the distinct keys and flush them together instead.
    const pending = new Map<string, readonly unknown[]>()
    let flushTimer: ReturnType<typeof setTimeout> | null = null
    function invalidate(queryKey: readonly unknown[]) {
      pending.set(JSON.stringify(queryKey), queryKey)
      flushTimer ??= setTimeout(() => {
        flushTimer = null
        for (const key of pending.values()) queryClient.invalidateQueries({ queryKey: key })
        pending.clear()
      }, 300)
    }

    function connect() {
      if (cancelled) return
      const protocol = window.location.protocol === "https:" ? "wss" : "ws"
      const url = `${protocol}://${window.location.host}/api/v1/ws?token=${encodeURIComponent(
        accessToken!
      )}&project_id=${projectId}`
      socket = new WebSocket(url)

      socket.onopen = () => {
        attempt = 0
        setConnected(true)
      }

      socket.onmessage = (event: MessageEvent<string>) => {
        let msg: WsEvent
        try {
          msg = JSON.parse(event.data)
        } catch {
          return
        }
        switch (msg.type) {
          case "job.updated":
            invalidate(["jobs"])
            invalidate(["job", msg.data.id])
            invalidate(["batchProgress"])
            break
          case "worker.updated":
            invalidate(["workers"])
            invalidate(["worker", msg.data.id])
            break
          case "queue.stats":
            invalidate(["queues"])
            invalidate(["queueStats", msg.data.queue_id])
            break
          case "metrics.tick":
            queryClient.setQueryData(["metricsLive", projectId], msg.data)
            invalidate(["metricsOverview"])
            break
        }
      }

      socket.onclose = () => {
        setConnected(false)
        if (cancelled) return
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        attempt += 1
        retryTimeout = setTimeout(connect, delay)
      }

      socket.onerror = () => socket?.close()
    }

    connect()

    return () => {
      cancelled = true
      if (retryTimeout) clearTimeout(retryTimeout)
      if (flushTimer) clearTimeout(flushTimer)
      socket?.close()
    }
  }, [projectId, accessToken, queryClient])

  return { connected }
}
