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

export function Register() {
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await authApi.register({ email, password, full_name: fullName })
      const tokens = await authApi.login({ email, password })
      useAuthStore.getState().setTokens(tokens.access_token, tokens.refresh_token)
      const me = await authApi.me()
      setSession({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user: me.user,
        memberships: me.memberships,
      })
      navigate("/onboarding")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Registration failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-6">
      <GridBackground className="h-[420px]" />
      <div className="relative w-full max-w-sm rounded-[var(--radius)] border border-border bg-surface p-8">

        <Eyebrow>Get started</Eyebrow>
        <h1 className="mt-1 text-xl font-semibold text-foreground">Create your account</h1>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="full_name">Full name</Label>
            <Input
              id="full_name"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ada Lovelace"
            />
          </div>
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
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>
          <Button type="submit" className="glow-cta w-full" disabled={loading}>
            {loading ? "Creating account..." : "Create account"}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
