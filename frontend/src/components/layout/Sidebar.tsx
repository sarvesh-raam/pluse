import { NavLink } from "react-router-dom"
import {
  LayoutDashboard,
  ListOrdered,
  ListChecks,
  Cpu,
  Skull,
  Settings as SettingsIcon,
  Activity,
} from "lucide-react"
import { cn } from "@/lib/utils"

const NAV_ITEMS = [
  { to: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/app/queues", label: "Queues", icon: ListOrdered },
  { to: "/app/jobs", label: "Jobs", icon: ListChecks },
  { to: "/app/workers", label: "Workers", icon: Cpu },
  { to: "/app/dlq", label: "Dead Letter Queue", icon: Skull },
  { to: "/app/settings", label: "Settings", icon: SettingsIcon },
]

export function Sidebar() {
  return (
    <aside className="hidden w-56 shrink-0 border-r border-border bg-surface md:flex md:flex-col">
      <div className="flex h-14 items-center gap-2 border-b border-border px-5">
        <Activity className="h-5 w-5 text-primary" />
        <span className="text-sm font-semibold tracking-tight">Pulse</span>
      </div>
      <nav className="flex-1 space-y-0.5 p-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-surface-2 text-foreground"
                  : "text-muted-foreground hover:bg-surface-2 hover:text-foreground"
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
