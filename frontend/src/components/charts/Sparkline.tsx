import { Area, AreaChart, ResponsiveContainer } from "recharts"

export function Sparkline({ data, color = "var(--color-brand)" }: { data: number[]; color?: string }) {
  if (data.length < 2) {
    return <div className="h-8 w-20 text-xs text-muted-foreground">—</div>
  }
  const points = data.map((v, i) => ({ i, v }))
  return (
    <div className="h-8 w-20">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.5} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area type="monotone" dataKey="v" stroke={color} fill={`url(#spark-${color})`} strokeWidth={1.5} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
