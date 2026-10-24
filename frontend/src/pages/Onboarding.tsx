import { type FormEvent, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowRight } from "lucide-react"
import { orgsApi, projectsApi, ApiError } from "@/lib/api"
import { useAuthStore } from "@/lib/auth-store"
import { GridBackground } from "@/components/shared/GridBackground"

import { Eyebrow } from "@/components/shared/Eyebrow"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function slugify(value: string): string {
  const base = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 60)
  // Org slugs are globally unique and names like "日本" slugify to "", so
  // always add a short random suffix rather than failing with a 409/422.
  const suffix = Math.random().toString(36).slice(2, 7)
  return base ? `${base}-${suffix}` : `workspace-${suffix}`
}

export function Onboarding() {
  const navigate = useNavigate()
  const setWorkspace = useAuthStore((s) => s.setWorkspace)
  const queryClient = useQueryClient()
  const [orgName, setOrgName] = useState("")
  const [projectName, setProjectName] = useState("")
  const [loading, setLoading] = useState(false)
  // if project creation fails after the org was created, a retry must reuse
  // that org instead of creating a second one
  const [createdOrgId, setCreatedOrgId] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      const org = createdOrgId
        ? { id: createdOrgId }
        : await orgsApi.create({ name: orgName, slug: slugify(orgName) })
      setCreatedOrgId(org.id)
      const project = await projectsApi.create({
        org_id: org.id,
        name: projectName,
        slug: slugify(projectName),
      })
      setWorkspace(org.id, project.id)
      await queryClient.invalidateQueries({ queryKey: ["orgs"] })
      navigate("/app/dashboard")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Setup failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-6">
      <GridBackground className="h-[420px]" />
      <div className="relative w-full max-w-sm rounded-[var(--radius)] border border-border bg-surface p-8">

        <Eyebrow>One-time setup</Eyebrow>
        <h1 className="mt-1 text-xl font-semibold text-foreground">Create your workspace</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          An organization owns projects; a project owns queues and jobs.
        </p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="org_name">Organization name</Label>
            <Input
              id="org_name"
              required
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Acme Inc"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project_name">First project name</Label>
            <Input
              id="project_name"
              required
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="Production"
            />
          </div>
          <Button type="submit" className="glow-cta w-full" disabled={loading}>
            {loading ? "Creating..." : "Create workspace"}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </form>
      </div>
    </div>
  )
}
