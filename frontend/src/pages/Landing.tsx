import { Link } from "react-router-dom"
import { ArrowRight, ExternalLink } from "lucide-react"
import { GridBackground } from "@/components/shared/GridBackground"
import { PlusMarks } from "@/components/shared/PlusMarks"
import { Eyebrow } from "@/components/shared/Eyebrow"
import { Button } from "@/components/ui/button"

const TRUST_STATS = [
  { label: "Jobs claimed atomically", value: "SKIP LOCKED" },
  { label: "Retry strategies", value: "3" },
  { label: "At-least-once delivery", value: "100%" },
  { label: "Live dashboard updates", value: "~2s" },
]

const FEATURES = [
  {
    title: "Atomic claiming",
    body: "FOR UPDATE SKIP LOCKED plus a per-queue advisory lock means two workers never run the same job, and concurrency limits hold under real contention.",
  },
  {
    title: "Built-in retries",
    body: "Fixed, linear, and exponential backoff with jitter, automatic promotion to a dead letter queue, and one-click replay.",
  },
  {
    title: "Full lifecycle visibility",
    body: "Every attempt, log line, and worker heartbeat is recorded — watch a job move from queued to completed in real time.",
  },
]

export function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tracking-tight">Pulse</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" nativeButton={false} render={<Link to="/login" />}>
            Sign in
          </Button>
          <Button size="sm" className="glow-cta" nativeButton={false} render={<Link to="/register" />}>
            Get started <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        </div>
      </header>

      <section className="relative overflow-hidden px-6 pt-20 pb-24 text-center">
        <GridBackground className="h-[520px]" />
        <PlusMarks />
        <div className="relative mx-auto max-w-3xl">
          <Eyebrow className="justify-center">Distributed job scheduling</Eyebrow>
          <h1 className="mt-4 text-5xl font-semibold tracking-tight text-balance sm:text-6xl">
            <span className="text-foreground">Reliable background jobs.</span>{" "}
            <span className="bg-linear-to-r from-primary to-brand-2 bg-clip-text text-transparent">
              From enqueue to done.
            </span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-balance text-muted-foreground">
            Pulse claims jobs atomically across any number of workers, retries what fails,
            quarantines what can't be saved, and shows you exactly what happened — live.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Button size="lg" className="glow-cta" nativeButton={false} render={<Link to="/register" />}>
              Start for free <ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              nativeButton={false}
              render={<a href="https://github.com" target="_blank" rel="noreferrer" />}
            >
              <ExternalLink className="mr-1.5 h-4 w-4" /> View source
            </Button>
          </div>
        </div>

        <div className="relative mx-auto mt-16 grid max-w-4xl grid-cols-2 gap-6 border-t border-border pt-10 sm:grid-cols-4">
          {TRUST_STATS.map((stat) => (
            <div key={stat.label}>
              <p className="stat-number text-2xl">{stat.value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-24">
        <Eyebrow className="text-center">Why Pulse</Eyebrow>
        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="relative rounded-[var(--radius)] border border-border bg-surface p-6">
              <PlusMarks />
              <h3 className="text-sm font-semibold text-foreground">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
