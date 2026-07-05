import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts"
import type { WorkerHeartbeat } from "@/types/api"

export function UtilizationChart({ heartbeats }: { heartbeats: WorkerHeartbeat[] }) {
  const data = heartbeats.map((h) => ({
    time: new Date(h.ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
    running: h.running_jobs,
  }))

  if (data.length < 2) {
    return <div className="flex h-20 items-center text-xs text-muted-foreground">Not enough data yet.</div>
  }

  return (
    <ResponsiveContainer width="100%" height={80}>
      <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="fillUtil" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-brand)" stopOpacity={0.4} />
            <stop offset="95%" stopColor="var(--color-brand)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={[0, "dataMax + 1"]} />
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
        <Area type="monotone" dataKey="running" stroke="var(--color-brand)" fill="url(#fillUtil)" strokeWidth={1.5} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
