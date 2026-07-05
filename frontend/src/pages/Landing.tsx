import { useState, useRef, useEffect } from "react"
import { Link } from "react-router-dom"
import {
  ArrowUpRight,
  Zap,
  Shield,
  BarChart3,
  RefreshCcw,
  Activity,
  Clock,
  Users,
  Server,
  Layers,
  GitBranch,
  Database,
  Cpu,
  CheckCircle,
} from "lucide-react"
import { ThemeToggle } from "@/components/shared/ThemeToggle"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/* ─── Nav ─── */
const NAV_LINKS = [
  { label: "Home", href: "#hero" },
  { label: "Features", href: "#features" },
  { label: "Architecture", href: "#architecture" },
  { label: "How It Works", href: "#how-it-works" },
]

/* ─── Capabilities strip words ─── */
const CAP_WORDS = ["Scheduling", "Analytics", "Retry Engine", "Monitoring"]

/* ─── Integration partners ─── */
const INTEGRATIONS = [
  { name: "PostgreSQL", icon: Database },
  { name: "Docker", icon: Server },
  { name: "REST API", icon: GitBranch },
  { name: "WebSocket", icon: Layers },
  { name: "Redis", icon: Cpu },
]

/* ─── Features for bento ─── */
const BENTO_FEATURES = [
  {
    title: "Knows your queues like your SRE.",
    body: "It understands your queue topology and gives real-time visibility into depth, throughput, and health — with full lifecycle tracking.",
    orbitIcons: [BarChart3, Layers, Shield],
    wide: true,
  },
  {
    title: "Turns chaotic retries into precise recovery.",
    body: "Pulse prioritizes high-impact failures so operators can quickly act on what matters most. Dead letter quarantine included.",
    stackLabels: ["Retry with backoff", "Promote to DLQ"],
    wide: false,
  },
  {
    title: "Planning Sync",
    body: "Link worker pools to queue groups so capacity planning and execution stay in sync across your infrastructure.",
    wide: false,
  },
  {
    title: "Risk Prevention",
    body: "Detect stalled workers and zombie jobs during execution before they cause cascading failures in production environments.",
    wide: false,
  },
]

/* ─── Why Pulse cards ─── */
const WHY_CARDS = [
  {
    eyebrow: "Stop Babysitting Workers",
    title: "Let Your Jobs Run Themselves",
    desc: "Most tools poll blindly. Pulse uses atomic claiming with FOR UPDATE SKIP LOCKED so no two workers ever run the same job — even under extreme contention.",
    bullets: ["Heartbeat-based liveness detection", "Graceful shutdown with job re-queuing"],
  },
  {
    eyebrow: "Static Dashboards Are Tired",
    title: "This Dashboard Actually Thinks",
    desc: "Basic dashboards show counts. Pulse shows throughput trends, P95 latencies, success rates, and worker fleet utilization — all updating live via WebSockets.",
    bullets: ["Real-time metrics, not stale snapshots", "Adapts to your queue topology automatically"],
  },
  {
    eyebrow: "No More Tool Chaos",
    title: "Scheduling, Monitoring & Recovery. All in one place.",
    desc: "Why does scheduling live in cron, monitoring in Grafana, and DLQ in a spreadsheet? Pulse unifies immediate, delayed, cron, and batch jobs under one roof.",
    bullets: ["One API for all job types", "Built-in dead letter queue with one-click replay"],
  },
]

/* ─── Stats ─── */
const STATS = [
  { value: "99.9%", label: "At-least-once delivery", sub: "guarantee" },
  { value: "< 50ms", label: "Claim latency", sub: "P95 under load" },
  { value: "∞", label: "Horizontal scaling", sub: "Add workers, not complexity" },
]

/* ─── How it works ─── */
const STEPS = [
  { step: "01", title: "Create a Queue", desc: "Define queues with priority, concurrency limits, and retry policies." },
  { step: "02", title: "Enqueue Jobs", desc: "Submit immediate, delayed, scheduled, or recurring jobs via REST API." },
  { step: "03", title: "Workers Execute", desc: "Workers poll, atomically claim, execute concurrently, and heartbeat." },
  { step: "04", title: "Monitor & Retry", desc: "Watch jobs live. Failed jobs retry automatically or land in the DLQ." },
]

export function Landing() {
  const [activeNav, setActiveNav] = useState(0)
  const [hoveredNav, setHoveredNav] = useState<number | null>(null)
  const navRefs = useRef<(HTMLAnchorElement | null)[]>([])
  const [indicatorStyle, setIndicatorStyle] = useState({ left: 0, width: 0, opacity: 0 })

  useEffect(() => {
    const idx = hoveredNav ?? activeNav
    const el = navRefs.current[idx]
    if (el) {
      setIndicatorStyle({
        left: el.offsetLeft,
        width: el.offsetWidth,
        opacity: 1,
      })
    }
  }, [hoveredNav, activeNav])

  return (
    <div className="min-h-screen bg-background text-foreground overflow-x-hidden">
      {/* ─── Navbar ─── */}
      <header className="sticky top-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          {/* Logo */}
          <a href="#hero" className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            <span className="text-sm font-bold tracking-tight">Pulse</span>
          </a>

          {/* Nav with sliding indicator */}
          <nav className="relative hidden items-center gap-0.5 md:flex">
            {/* Sliding pill indicator */}
            <div
              className="absolute top-1/2 -translate-y-1/2 h-[34px] rounded-full bg-muted transition-all duration-300 ease-out"
              style={{
                left: indicatorStyle.left,
                width: indicatorStyle.width,
                opacity: indicatorStyle.opacity,
              }}
              aria-hidden="true"
            />
            {NAV_LINKS.map((link, i) => (
              <a
                key={link.label}
                ref={(el) => { navRefs.current[i] = el }}
                href={link.href}
                onClick={() => setActiveNav(i)}
                onMouseEnter={() => setHoveredNav(i)}
                onMouseLeave={() => setHoveredNav(null)}
                className={cn(
                  "relative z-10 rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-200",
                  i === activeNav ? "text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {i === activeNav && (
                  <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-primary" />
                )}
                {link.label}
              </a>
            ))}
          </nav>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Button
              size="sm"
              className="rounded-full px-6 font-medium"
              nativeButton={false}
              render={<Link to="/login" />}
            >
              Login
            </Button>
          </div>
        </div>
      </header>

      {/* ─── Hero ─── */}
      <section id="hero" className="relative px-6 pt-16 pb-8 sm:pt-24 sm:pb-12">
        <div className="mx-auto max-w-4xl text-center">
          <h1 className="text-5xl font-semibold leading-[1.1] tracking-tight sm:text-6xl lg:text-7xl">
            Distributed Job{" "}
            <br className="hidden sm:block" />
            Scheduling System.
            <br />
            <span className="text-muted-foreground/50">
              From enqueue to done.
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-lg text-base text-muted-foreground">
            The all-in-one platform for background job execution, atomic claiming, and real-time observability.
          </p>

          <div className="mt-8 flex items-center justify-center gap-2">
            <Button
              size="lg"
              variant="outline"
              className="rounded-full border-2 px-8 font-medium"
              nativeButton={false}
              render={<Link to="/register" />}
            >
              Get Started
            </Button>
            <Button
              size="lg"
              className="h-12 w-12 rounded-full p-0"
              nativeButton={false}
              render={<Link to="/register" />}
            >
              <ArrowUpRight className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {/* Wireframe illustration */}
        <div className="mx-auto mt-12 flex justify-center">
          <div className="relative h-64 w-64 sm:h-80 sm:w-80">
            <svg viewBox="0 0 400 400" className="h-full w-full text-foreground/70" fill="none" stroke="currentColor" strokeWidth="0.7">
              {Array.from({ length: 10 }).map((_, i) => {
                const r = 50 + i * 16
                const rot = i * 18
                const pts = Array.from({ length: 6 })
                  .map((_, j) => {
                    const a = (Math.PI / 3) * j + (rot * Math.PI) / 180
                    return `${200 + r * Math.cos(a)},${200 + r * Math.sin(a)}`
                  })
                  .join(" ")
                return <polygon key={i} points={pts} opacity={0.2 + (i / 10) * 0.6} />
              })}
              {Array.from({ length: 6 }).map((_, j) => {
                const a = (Math.PI / 3) * j
                return (
                  <line
                    key={j}
                    x1={200 + 50 * Math.cos(a)}
                    y1={200 + 50 * Math.sin(a)}
                    x2={200 + 210 * Math.cos(a + (18 * 9 * Math.PI) / 180)}
                    y2={200 + 210 * Math.sin(a + (18 * 9 * Math.PI) / 180)}
                    opacity="0.15"
                  />
                )
              })}
              <circle cx="200" cy="200" r="4" fill="currentColor" opacity="0.5" />
              {[0, 60, 120, 180, 240, 300].map((deg, i) => (
                <circle
                  key={i}
                  cx={200 + 130 * Math.cos((deg * Math.PI) / 180)}
                  cy={200 + 130 * Math.sin((deg * Math.PI) / 180)}
                  r="3"
                  fill="currentColor"
                  opacity="0.35"
                />
              ))}
            </svg>
          </div>
        </div>

        {/* Side content — visible at larger sizes */}
        <div className="mx-auto mt-8 flex max-w-7xl flex-wrap items-start justify-between gap-8 px-4">
          {/* Left — plus & description */}
          <div className="max-w-xs">
            <svg viewBox="0 0 14 14" fill="none" className="mb-3 h-5 w-5 text-border" aria-hidden="true">
              <path d="M7 1V13M1 7H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Find and fix reliability issues before they reach production. One platform for scheduling, monitoring, and recovery.
            </p>
          </div>
          {/* Right — stats */}
          <div className="flex items-center gap-3">
            <div className="flex -space-x-2">
              {["#2563eb", "#6c5ce7", "#10b981"].map((c, i) => (
                <div key={i} className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-background text-xs font-bold text-white" style={{ backgroundColor: c }}>
                  {["P", "S", "R"][i]}
                </div>
              ))}
            </div>
            <div>
              <span className="text-xl font-bold tracking-tight">99.9%</span>
              <p className="text-xs text-muted-foreground">Trusted delivery guarantee</p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Capabilities strip ─── */}
      <section className="py-10">
        <div className="flex items-center justify-center gap-6 sm:gap-12">
          {CAP_WORDS.map((word, i) => (
            <span key={i} className="flex items-center gap-6 text-4xl font-semibold tracking-tight text-foreground/[0.07] sm:gap-12 sm:text-6xl lg:text-7xl">
              {i > 0 && <span className="text-foreground/[0.12]">+</span>}
              {word}
            </span>
          ))}
        </div>
      </section>

      {/* ─── Blue Banner ─── */}
      <section className="mx-6 overflow-hidden rounded-3xl bg-primary px-8 py-16 text-center lg:mx-auto lg:max-w-7xl">
        <h2 className="text-4xl font-bold tracking-tight text-white sm:text-5xl lg:text-6xl">
          END TO END JOB
          <br />
          LIFECYCLE MANAGEMENT
        </h2>
        <div className="mx-auto my-8 h-px w-40 bg-white/20" />
        <p className="mx-auto max-w-xl text-base text-white/70">
          Built on PostgreSQL for reliability, powered by WebSockets for real-time updates.
        </p>
        {/* Integration logos row */}
        <div className="mx-auto mt-10 flex flex-wrap items-center justify-center gap-8">
          {INTEGRATIONS.map(({ name, icon: Icon }) => (
            <div key={name} className="flex items-center gap-2 text-white/80">
              <Icon className="h-6 w-6" />
              <span className="text-sm font-medium">{name}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ─── Bento Features Grid ─── */}
      <section id="features" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-4 py-1.5 text-xs font-medium text-primary">
              <Activity className="h-3.5 w-3.5" />
              Key Features
            </div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
              Explore Our{" "}
              <br />
              <span className="bg-gradient-to-r from-primary to-brand-2 bg-clip-text text-transparent">
                Standout Features
              </span>
            </h2>
          </div>

          {/* Bento grid */}
          <div className="mt-16 grid gap-5 lg:grid-cols-12">
            {/* Card 1 — wide */}
            <div className="group relative overflow-hidden rounded-2xl border border-border bg-muted p-8 transition-shadow duration-300 hover:shadow-xl hover:shadow-primary/5 lg:col-span-7">
              {/* Grid pattern overlay */}
              <div className="pointer-events-none absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 0h40v40H0z' fill='none' stroke='%23000' stroke-width='.5'/%3E%3C/svg%3E\")" }} />

              {/* Orbit SVG */}
              <div className="relative mb-6 flex justify-center">
                <svg viewBox="0 0 420 200" className="h-40 w-full max-w-sm text-primary/40" fill="none" stroke="currentColor" strokeWidth="1">
                  <path d="M210 100 C162 55 110 35 66 28" strokeDasharray="4 4" />
                  <path d="M210 95 C212 55 222 40 232 25" strokeDasharray="4 4" />
                  <path d="M210 100 C260 55 308 35 353 28" strokeDasharray="4 4" />
                  <path d="M208 130 C154 155 110 170 66 180" strokeDasharray="4 4" />
                  <path d="M212 130 C214 160 216 175 216 190" strokeDasharray="4 4" />
                  <path d="M214 128 C272 155 308 170 353 180" strokeDasharray="4 4" />
                </svg>
                {/* Orbit icon pills */}
                {[
                  { Icon: BarChart3, x: "12%", y: "10%" },
                  { Icon: Layers, x: "50%", y: "5%" },
                  { Icon: Shield, x: "85%", y: "10%" },
                  { Icon: Clock, x: "12%", y: "78%" },
                  { Icon: Database, x: "50%", y: "85%" },
                  { Icon: RefreshCcw, x: "85%", y: "78%" },
                ].map(({ Icon, x, y }, i) => (
                  <span
                    key={i}
                    className="absolute flex h-9 w-9 items-center justify-center rounded-full border border-primary/20 bg-background text-primary shadow-sm"
                    style={{ left: x, top: y, transform: "translate(-50%,-50%)" }}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                ))}
              </div>

              <h3 className="text-lg font-semibold">{BENTO_FEATURES[0].title}</h3>
              <p className="mt-2 max-w-md text-sm text-muted-foreground">{BENTO_FEATURES[0].body}</p>
            </div>

            {/* Card 2 — narrow */}
            <div className="group relative overflow-hidden rounded-2xl border border-border bg-muted p-8 transition-shadow duration-300 hover:shadow-xl hover:shadow-primary/5 lg:col-span-5">
              <div className="pointer-events-none absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 0h40v40H0z' fill='none' stroke='%23000' stroke-width='.5'/%3E%3C/svg%3E\")" }} />

              {/* Stacked review-like cards */}
              <div className="mb-6 space-y-3">
                {["Retry with exponential backoff", "Promote to dead letter queue"].map((label, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex items-center gap-3 rounded-xl border p-4 transition-transform duration-300 group-hover:translate-x-1",
                      i === 0
                        ? "border-primary/30 bg-primary/5"
                        : "border-border bg-background"
                    )}
                  >
                    <RefreshCcw className={cn("h-5 w-5 shrink-0", i === 0 ? "text-primary" : "text-muted-foreground")} />
                    <span className={cn("text-sm font-medium", i === 0 ? "text-primary" : "text-muted-foreground")}>{label}</span>
                  </div>
                ))}
              </div>

              <h3 className="text-lg font-semibold">{BENTO_FEATURES[1].title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{BENTO_FEATURES[1].body}</p>
            </div>

            {/* Card 3 — narrow */}
            <div className="group relative overflow-hidden rounded-2xl border border-border bg-muted p-8 transition-shadow duration-300 hover:shadow-xl hover:shadow-primary/5 lg:col-span-5">
              <div className="pointer-events-none absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 0h40v40H0z' fill='none' stroke='%23000' stroke-width='.5'/%3E%3C/svg%3E\")" }} />
              <h3 className="text-lg font-semibold">{BENTO_FEATURES[2].title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{BENTO_FEATURES[2].body}</p>
            </div>

            {/* Card 4 — narrow */}
            <div className="group relative overflow-hidden rounded-2xl border border-border bg-muted p-8 transition-shadow duration-300 hover:shadow-xl hover:shadow-primary/5 lg:col-span-4">
              <div className="pointer-events-none absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 0h40v40H0z' fill='none' stroke='%23000' stroke-width='.5'/%3E%3C/svg%3E\")" }} />
              <h3 className="text-lg font-semibold">{BENTO_FEATURES[3].title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{BENTO_FEATURES[3].body}</p>
            </div>

            {/* Card 5 — CTA card (dark bg like Codity) */}
            <div className="group relative flex flex-col items-center justify-center overflow-hidden rounded-2xl bg-primary p-8 text-center text-white lg:col-span-3">
              <Activity className="mb-4 h-12 w-12 opacity-80" />
              <h3 className="text-lg font-semibold">Get started</h3>
              <Button
                className="mt-4 rounded-full border-2 border-white/30 bg-transparent px-6 font-medium text-white hover:bg-white/10"
                nativeButton={false}
                render={<Link to="/register" />}
              >
                Get Started Now
                <ArrowUpRight className="ml-1.5 h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Why Pulse ─── */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-4 py-1.5 text-xs font-medium text-primary">
              <Activity className="h-3.5 w-3.5" />
              Why ?
            </div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
              Why <span className="bg-gradient-to-r from-primary to-brand-2 bg-clip-text text-transparent">Pulse ?</span>
            </h2>
          </div>

          <div className="mt-16 space-y-16">
            {WHY_CARDS.map((card, i) => (
              <article key={i} className="grid items-center gap-8 lg:grid-cols-2">
                {/* Text */}
                <div className={cn(i % 2 === 1 && "lg:order-2")}>
                  <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-primary">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                    {card.eyebrow}
                  </p>
                  <h3 className="mt-3 text-2xl font-semibold tracking-tight">{card.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{card.desc}</p>
                  <ul className="mt-4 space-y-2">
                    {card.bullets.map((b, j) => (
                      <li key={j} className="flex items-start gap-2 text-sm text-muted-foreground">
                        <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
                {/* Illustration placeholder */}
                <div className={cn("flex items-center justify-center rounded-2xl bg-muted p-12", i % 2 === 1 && "lg:order-1")}>
                  <div className="flex h-40 w-full max-w-xs items-center justify-center rounded-xl border border-border bg-background p-6">
                    <div className="grid grid-cols-3 gap-3">
                      {[Zap, RefreshCcw, BarChart3, Shield, Clock, Users].slice(i * 2, i * 2 + 6).map((Icon, k) => (
                        <div key={k} className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <Icon className="h-4 w-4" />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Stats ─── */}
      <section id="architecture" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-4 py-1.5 text-xs font-medium text-primary">
              <Activity className="h-3.5 w-3.5" />
              Statistics
            </div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
              See Your{" "}
              <br />
              <span className="bg-gradient-to-r from-primary to-brand-2 bg-clip-text text-transparent">Smart Job Analysis</span>
            </h2>
          </div>
          <div className="mx-auto mt-16 grid max-w-3xl gap-8 sm:grid-cols-3">
            {STATS.map((s) => (
              <div key={s.label} className="rounded-2xl border border-border bg-muted p-8 text-center">
                <p className="text-4xl font-bold tracking-tight text-primary">{s.value}</p>
                <p className="mt-2 text-sm font-medium text-foreground">{s.label}</p>
                <p className="mt-1 text-xs text-muted-foreground">{s.sub}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── How it works ─── */}
      <section id="how-it-works" className="border-t border-border/40 px-6 py-24">
        <div className="mx-auto max-w-7xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Four steps to reliable job execution
          </h2>
          <div className="mt-16 grid gap-8 text-left sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <div key={s.step}>
                <span className="text-5xl font-bold tracking-tight text-foreground/[0.06]">{s.step}</span>
                <h3 className="mt-2 text-base font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Bottom CTA Banner ─── */}
      <section className="mx-6 mb-16 overflow-hidden rounded-3xl bg-primary px-8 py-16 text-center lg:mx-auto lg:max-w-7xl">
        <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
          All plans include a 7 day
          <br />
          free trial
        </h2>
        <p className="mx-auto mt-3 text-sm text-white/60">No credit card required</p>
        <div className="mt-8 flex justify-center gap-2">
          <Button
            size="lg"
            className="rounded-full bg-white px-8 font-medium text-primary hover:bg-white/90"
            nativeButton={false}
            render={<Link to="/register" />}
          >
            Get Started
          </Button>
          <Button
            size="lg"
            className="h-12 w-12 rounded-full bg-white p-0 text-primary hover:bg-white/90"
            nativeButton={false}
            render={<Link to="/register" />}
          >
            <ArrowUpRight className="h-5 w-5" />
          </Button>
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="border-t border-border/40 px-6 py-16">
        <div className="mx-auto grid max-w-7xl gap-12 sm:grid-cols-2 lg:grid-cols-5">
          {/* Brand */}
          <div className="lg:col-span-1">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              <span className="text-sm font-bold tracking-tight">Pulse</span>
            </div>
            <p className="mt-4 text-xs text-muted-foreground">Distributed Job Scheduler</p>
          </div>
          {/* Links */}
          {[
            { title: "Product", links: ["Dashboard", "Queues", "Workers", "Dead Letter Queue"] },
            { title: "Developers", links: ["REST API", "WebSocket", "Documentation"] },
            { title: "Architecture", links: ["PostgreSQL", "SKIP LOCKED", "Advisory Locks", "Retry Engine"] },
            { title: "Project", links: ["GitHub", "License", "Contributing"] },
          ].map((col) => (
            <div key={col.title}>
              <p className="text-xs font-semibold uppercase tracking-wider text-foreground">{col.title}</p>
              <ul className="mt-3 space-y-2">
                {col.links.map((link) => (
                  <li key={link}>
                    <span className="cursor-default text-sm text-muted-foreground transition-colors hover:text-foreground">
                      {link}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mx-auto mt-12 max-w-7xl border-t border-border/40 pt-6">
          <p className="text-xs text-muted-foreground">© 2024 Pulse. Built as an engineering showcase.</p>
        </div>
      </footer>
    </div>
  )
}
