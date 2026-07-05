import { type FormEvent, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { ArrowRight } from "lucide-react"
import { authApi, ApiError } from "@/lib/api"
import { useAuthStore } from "@/lib/auth-store"
import { GridBackground } from "@/components/shared/GridBackground"

import { Eyebrow } from "@/components/shared/Eyebrow"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function Login() {
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)
  const [email, setEmail] = useState("demo@pulse.dev")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      const tokens = await authApi.login({ email, password })
      useAuthStore.getState().setTokens(tokens.access_token, tokens.refresh_token)
      const me = await authApi.me()
      setSession({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user: me.user,
        memberships: me.memberships,
      })
      if (me.memberships.length > 0) {
        const firstOrg = me.memberships[0]
        const firstProject = firstOrg.org.projects?.[0]
        useAuthStore.getState().setWorkspace(firstOrg.org_id, firstProject?.id ?? null)
      }
      navigate("/app/dashboard")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Login failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-6">
      <GridBackground className="h-[420px]" />
      <div className="relative w-full max-w-sm rounded-[var(--radius)] border border-border bg-surface p-8">

        <Eyebrow>Welcome back</Eyebrow>
        <h1 className="mt-1 text-xl font-semibold text-foreground">Sign in to Pulse</h1>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          <Button type="submit" className="glow-cta w-full" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </form>

        <p className="mt-4 text-xs text-muted-foreground">
          Demo login: <code className="text-foreground">demo@pulse.dev</code> /{" "}
          <code className="text-foreground">demo1234</code>
        </p>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Don't have an account?{" "}
          <Link to="/register" className="text-primary hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
