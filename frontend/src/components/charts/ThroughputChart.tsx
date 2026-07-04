import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { ThroughputBucket } from "@/types/api"

export function ThroughputChart({ buckets }: { buckets: ThroughputBucket[] }) {
  const data = buckets.map((b) => ({
    time: new Date(b.bucket_start).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }),
    completed: b.completed,
    failed: b.failed,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
        <defs>
          <linearGradient id="fillCompleted" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-brand)" stopOpacity={0.4} />
            <stop offset="95%" stopColor="var(--color-brand)" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="fillFailed" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-danger)" stopOpacity={0.3} />
            <stop offset="95%" stopColor="var(--color-danger)" stopOpacity={0} />
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
        <YAxis stroke="var(--color-muted-foreground)" fontSize={11} tickLine={false} axisLine={false} width={30} />
        <Tooltip
          contentStyle={{
            background: "var(--color-surface-2)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "var(--color-foreground)" }}
        />
        <Area
          type="monotone"
          dataKey="completed"
          stroke="var(--color-brand)"
          fill="url(#fillCompleted)"
          strokeWidth={2}
          name="Completed"
        />
        <Area
          type="monotone"
          dataKey="failed"
          stroke="var(--color-danger)"
          fill="url(#fillFailed)"
          strokeWidth={2}
          name="Failed"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
