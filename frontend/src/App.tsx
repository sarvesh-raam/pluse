import { lazy, Suspense, useEffect, type ComponentType, type ReactNode } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useAuthStore } from "@/lib/auth-store"
import { useThemeStore, initThemeListener } from "@/lib/theme-store"
import { AppShell } from "@/components/layout/AppShell"
import { Skeleton } from "@/components/ui/skeleton"

// Route-level code splitting: the landing/login pages no longer pull in
// Recharts and every app page (the single bundle was ~1 MB).
const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })))

const Landing = page(() => import("@/pages/Landing"), "Landing")
const Login = page(() => import("@/pages/Login"), "Login")
const Register = page(() => import("@/pages/Register"), "Register")
const Onboarding = page(() => import("@/pages/Onboarding"), "Onboarding")
const Dashboard = page(() => import("@/pages/Dashboard"), "Dashboard")
const Queues = page(() => import("@/pages/Queues"), "Queues")
const QueueDetail = page(() => import("@/pages/QueueDetail"), "QueueDetail")
const Jobs = page(() => import("@/pages/Jobs"), "Jobs")
const JobDetail = page(() => import("@/pages/JobDetail"), "JobDetail")
const Workers = page(() => import("@/pages/Workers"), "Workers")
const Dlq = page(() => import("@/pages/Dlq"), "Dlq")
const Settings = page(() => import("@/pages/Settings"), "Settings")

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
})

function RequireAuth({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken)
  if (!accessToken) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  const themeMode = useThemeStore((s) => s.mode)

  // Listen for OS theme changes when mode is "system"
  useEffect(() => {
    const cleanup = initThemeListener()
    return cleanup
  }, [])

  // Resolve the actual theme for the Toaster component
  const resolvedTheme: "light" | "dark" =
    themeMode === "system"
      ? (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light")
      : themeMode

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delay={200}>
        <BrowserRouter>
          <Suspense fallback={<Skeleton className="m-6 h-64" />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              path="/onboarding"
              element={
                <RequireAuth>
                  <Onboarding />
                </RequireAuth>
              }
            />
            <Route path="/app" element={<AppShell />}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="queues" element={<Queues />} />
              <Route path="queues/:queueId" element={<QueueDetail />} />
              <Route path="jobs" element={<Jobs />} />
              <Route path="jobs/:jobId" element={<JobDetail />} />
              <Route path="workers" element={<Workers />} />
              <Route path="dlq" element={<Dlq />} />
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </BrowserRouter>
        <Toaster theme={resolvedTheme} position="top-right" />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
