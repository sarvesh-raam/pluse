import { useEffect } from "react"
import { Navigate, Outlet } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { orgsApi, projectsApi } from "@/lib/api"
import { useAuthStore } from "@/lib/auth-store"
import { useLiveUpdates } from "@/lib/ws"
import { Sidebar } from "@/components/layout/Sidebar"
import { Topbar } from "@/components/layout/Topbar"

export function AppShell() {
  const accessToken = useAuthStore((s) => s.accessToken)
  const currentOrgId = useAuthStore((s) => s.currentOrgId)
  const currentProjectId = useAuthStore((s) => s.currentProjectId)
  const setWorkspace = useAuthStore((s) => s.setWorkspace)

  const { data: orgs, isLoading: orgsLoading } = useQuery({
    queryKey: ["orgs"],
    queryFn: orgsApi.list,
    enabled: !!accessToken,
  })
  const { data: projects } = useQuery({
    queryKey: ["projects", currentOrgId],
    queryFn: () => projectsApi.list(currentOrgId!),
    enabled: !!currentOrgId,
  })

  // Auto-select the first org/project so the demo user lands straight on
  // populated data instead of an empty picker.
  // Also repairs a stale persisted selection (org deleted, membership
  // revoked, project removed) — previously that left every page stuck on
  // 403/404s with no way out short of clearing localStorage.
  useEffect(() => {
    if (!orgs?.items.length) return
    if (!currentOrgId || !orgs.items.some((o) => o.id === currentOrgId)) {
      setWorkspace(orgs.items[0].id, null)
    }
  }, [orgs, currentOrgId, setWorkspace])

  useEffect(() => {
    if (!currentOrgId || !projects) return
    if (currentProjectId && projects.items.some((p) => p.id === currentProjectId)) return
    const next = projects.items[0]?.id ?? null
    if (next !== currentProjectId) setWorkspace(currentOrgId, next)
  }, [projects, currentOrgId, currentProjectId, setWorkspace])

  const { connected } = useLiveUpdates(currentProjectId)

  if (!accessToken) return <Navigate to="/login" replace />

  if (!orgsLoading && orgs?.items.length === 0) {
    return <Navigate to="/onboarding" replace />
  }

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar connected={connected} />
        <main className="flex-1 overflow-y-auto p-6">
          {currentProjectId ? (
            <Outlet />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Select a project to get started.
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
