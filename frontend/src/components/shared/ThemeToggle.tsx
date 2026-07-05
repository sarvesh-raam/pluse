import { Sun, Moon, Monitor } from "lucide-react"
import { useThemeStore, type ThemeMode } from "@/lib/theme-store"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

const MODES: { value: ThemeMode; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
]

export function ThemeToggle({ className }: { className?: string }) {
  const mode = useThemeStore((s) => s.mode)
  const setMode = useThemeStore((s) => s.setMode)

  const ActiveIcon = MODES.find((m) => m.value === mode)?.icon ?? Monitor

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "inline-flex h-8 w-8 items-center justify-center rounded-md outline-none transition-colors hover:bg-surface-2",
          className
        )}
        aria-label="Toggle theme"
      >
        <ActiveIcon className="h-4 w-4 text-muted-foreground transition-transform duration-200" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {MODES.map(({ value, label, icon: Icon }) => (
          <DropdownMenuItem
            key={value}
            onClick={() => setMode(value)}
            className={cn(mode === value && "bg-surface-2")}
          >
            <Icon className="mr-2 h-4 w-4" />
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
