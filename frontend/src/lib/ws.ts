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
            queryClient.invalidateQueries({ queryKey: ["jobs"] })
            queryClient.invalidateQueries({ queryKey: ["job", msg.data.id] })
            queryClient.invalidateQueries({ queryKey: ["batchProgress"] })
            break
          case "worker.updated":
            queryClient.invalidateQueries({ queryKey: ["workers"] })
            queryClient.invalidateQueries({ queryKey: ["worker", msg.data.id] })
            break
          case "queue.stats":
            queryClient.invalidateQueries({ queryKey: ["queues"] })
            queryClient.invalidateQueries({ queryKey: ["queueStats", msg.data.queue_id] })
            break
          case "metrics.tick":
            queryClient.setQueryData(["metricsLive", projectId], msg.data)
            queryClient.invalidateQueries({ queryKey: ["metricsOverview"] })
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
      socket?.close()
    }
  }, [projectId, accessToken, queryClient])

  return { connected }
}
