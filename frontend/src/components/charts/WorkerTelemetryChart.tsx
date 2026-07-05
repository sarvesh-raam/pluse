import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { workersApi } from "@/lib/api"
import { useAuthStore } from "@/lib/auth-store"

interface TelemetryPoint {
  time: string
  cpu: number
  ram: number
}

export function WorkerTelemetryChart() {
  const projectId = useAuthStore((s) => s.currentProjectId)
  const [data, setData] = useState<TelemetryPoint[]>([])

  const { data: workers } = useQuery({
    queryKey: ["workers", projectId],
    queryFn: () => workersApi.list(projectId!),
    enabled: !!projectId,
    refetchInterval: 3000,
  })

  useEffect(() => {
    if (!workers) return

    const activeWorkers = workers.items.filter(w => w.status === "active" || w.status === "idle")
    const totalCpu = activeWorkers.reduce((acc, w) => acc + (w.cpu_percent || 0), 0)
    const totalRam = activeWorkers.reduce((acc, w) => acc + (w.ram_mb || 0), 0)

    const now = new Date().toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })

    setData(prev => {
      const next = [...prev, { time: now, cpu: Math.round(totalCpu * 10) / 10, ram: Math.round(totalRam) }]
      return next.slice(-30) // Keep last 30 data points (~90 seconds)
    })
  }, [workers])

  return (
    <div className="relative rounded-[var(--radius)] border border-border bg-surface p-5">
      <p className="eyebrow">Live Telemetry</p>
      <h2 className="mt-1 text-sm font-medium text-foreground">Fleet CPU & Memory</h2>
      <div className="h-[240px] mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="fillCpu" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-brand)" stopOpacity={0.4} />
                <stop offset="95%" stopColor="var(--color-brand)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="fillRam" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-info)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--color-info)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="var(--color-muted-foreground)"
              fontSize={11}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              yAxisId="cpu"
              stroke="var(--color-brand)"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              width={44}
              domain={[0, "auto"]}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
            />
            <YAxis
              yAxisId="ram"
              orientation="right"
              stroke="var(--color-info)"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              width={56}
              domain={["auto", "auto"]}
              tickFormatter={(v: number) => `${Math.round(v)}`}
            />
            <Tooltip
              contentStyle={{
                background: "var(--color-surface-2)",
                border: "1px solid var(--color-border)",
                borderRadius: 8,
                fontSize: 12,
                color: "var(--color-foreground)",
              }}
              labelStyle={{ color: "var(--color-foreground)" }}
              itemStyle={{ color: "var(--color-muted-foreground)" }}
            />
            <Area
              yAxisId="cpu"
              type="monotone"
              dataKey="cpu"
              stroke="var(--color-brand)"
              fill="url(#fillCpu)"
              strokeWidth={2}
              name="CPU (%)"
            />
            <Area
              yAxisId="ram"
              type="monotone"
              dataKey="ram"
              stroke="var(--color-info)"
              fill="url(#fillRam)"
              strokeWidth={2}
              name="RAM (MB)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
