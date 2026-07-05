import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { LogOut } from "lucide-react"
import { orgsApi, projectsApi } from "@/lib/api"
import { useAuthStore } from "@/lib/auth-store"
import { LivePulseBadge } from "@/components/shared/LivePulseBadge"
import { ThemeToggle } from "@/components/shared/ThemeToggle"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"

export function Topbar({ connected }: { connected: boolean }) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const currentOrgId = useAuthStore((s) => s.currentOrgId)
  const currentProjectId = useAuthStore((s) => s.currentProjectId)
  const setWorkspace = useAuthStore((s) => s.setWorkspace)
  const logout = useAuthStore((s) => s.logout)

  const { data: orgs } = useQuery({ queryKey: ["orgs"], queryFn: orgsApi.list })
  const { data: projects } = useQuery({
    queryKey: ["projects", currentOrgId],
    queryFn: () => projectsApi.list(currentOrgId!),
    enabled: !!currentOrgId,
  })

  return (
    <header className="flex h-14 items-center justify-between gap-4 border-b border-border bg-surface px-5">
      <div className="flex items-center gap-2">
        <Select
          items={Object.fromEntries(orgs?.items.map((o) => [o.id, o.name]) ?? [])}
          value={currentOrgId ?? ""}
          onValueChange={(orgId) => setWorkspace(orgId, null)}
        >
          <SelectTrigger size="sm" className="w-40 border-border bg-surface-2">
            <SelectValue placeholder="Organization" />
          </SelectTrigger>
          <SelectContent>
            {orgs?.items.map((org) => (
              <SelectItem key={org.id} value={org.id}>
                {org.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <span className="text-muted-foreground">/</span>

        <Select
          items={Object.fromEntries(projects?.items.map((p) => [p.id, p.name]) ?? [])}
          value={currentProjectId ?? ""}
          onValueChange={(projectId) => setWorkspace(currentOrgId, projectId)}
          disabled={!currentOrgId}
        >
          <SelectTrigger size="sm" className="w-40 border-border bg-surface-2">
            <SelectValue placeholder="Project" />
          </SelectTrigger>
          <SelectContent>
            {projects?.items.map((project) => (
              <SelectItem key={project.id} value={project.id}>
                {project.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-3">
        <LivePulseBadge connected={connected} />
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 rounded-md px-1.5 py-1 outline-none hover:bg-surface-2">
            <Avatar className="h-7 w-7">
              <AvatarFallback className="bg-primary/20 text-xs text-primary">
                {user?.full_name?.slice(0, 1).toUpperCase() ?? "?"}
              </AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <div className="px-2 py-1.5 text-xs text-muted-foreground">{user?.email}</div>
            <DropdownMenuItem
              onClick={() => {
                logout()
                navigate("/login")
              }}
            >
              <LogOut className="mr-2 h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
