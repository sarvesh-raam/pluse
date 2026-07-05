import { driver, type DriveStep } from "driver.js"
import "driver.js/dist/driver.css"

type TourStep = DriveStep & { data: { path: string } }

const DASHBOARD = "/app/dashboard"
const QUEUES = "/app/queues"
const JOBS = "/app/jobs"
const WORKERS = "/app/workers"
const DLQ = "/app/dlq"
const SETTINGS = "/app/settings"

/** Waits for an element to exist in the DOM, e.g. after a client-side route change. */
function waitForElement(selector: string, timeoutMs = 4000): Promise<void> {
  return new Promise((resolve) => {
    if (document.querySelector(selector)) return resolve()

    const observer = new MutationObserver(() => {
      if (document.querySelector(selector)) {
        observer.disconnect()
        clearTimeout(timer)
        resolve()
      }
    })
    observer.observe(document.body, { childList: true, subtree: true })

    const timer = setTimeout(() => {
      observer.disconnect()
      resolve()
    }, timeoutMs)
  })
}

const steps: TourStep[] = [
  {
    data: { path: DASHBOARD },
    element: '[data-tour="stat-cards"]',
    popover: {
      title: "Welcome to Pulse 👋",
      description:
        "This is your control tower. These four numbers, updated live, tell you everything at a glance: how many tasks are finishing per minute, what share of them are succeeding, how many worker computers are online, and how many tasks are still waiting in line.",
      side: "bottom",
      align: "start",
    },
  },
  {
    data: { path: DASHBOARD },
    element: '[data-tour="throughput-chart"]',
    popover: {
      title: "Watching work happen",
      description:
        "This chart shows tasks completing (green) and failing (red) over time. You never need to refresh the page — it updates itself as work happens.",
      side: "top",
      align: "start",
    },
  },
  {
    data: { path: DASHBOARD },
    element: '[data-tour="telemetry-chart"]',
    popover: {
      title: "How hard your workers are working",
      description:
        "Every worker computer reports its own CPU and memory usage a few times a second. If a worker ever looks overloaded, this is the first place you'd notice it.",
      side: "top",
      align: "start",
    },
  },
  {
    data: { path: DASHBOARD },
    element: '[data-tour="load-generator"]',
    popover: {
      title: "Try it yourself",
      description:
        'Click "Blast Jobs" any time to send a batch of test tasks through the system and watch every chart on this page react in real time. It\'s the fastest way to see Pulse actually working.',
      side: "top",
      align: "start",
    },
  },
  {
    data: { path: QUEUES },
    element: '[data-tour="new-queue-btn"]',
    popover: {
      title: "What's a queue?",
      description:
        "Think of a queue as a line at a checkout counter. Every task you send to Pulse waits in a specific queue until a worker is free to pick it up. Click here to create your own — you decide how many tasks it can run at once, and how failures get retried.",
      side: "bottom",
      align: "start",
    },
  },
  {
    data: { path: QUEUES },
    element: '[data-tour="queues-table"]',
    popover: {
      title: "Watching queues live",
      description:
        'Each row is one queue. "Depth" is how many tasks are currently waiting. Flip the switch on the right to pause a queue instantly — nothing already running gets interrupted, but no new tasks start until you flip it back on.',
      side: "top",
      align: "start",
    },
  },
  {
    data: { path: JOBS },
    element: '[data-tour="enqueue-job-btn"]',
    popover: {
      title: "What's a job?",
      description:
        'A job is one single task — like "send this email" or "generate this report." Click here to add one to any queue and watch it move through its lifecycle in real time.',
      side: "bottom",
      align: "start",
    },
  },
  {
    data: { path: JOBS },
    element: '[data-tour="jobs-table"]',
    popover: {
      title: "Reading the status colors",
      description:
        "Grey means waiting its turn, blue means in line, a pulsing purple means actively running right now, green means finished successfully, and orange/red means it failed or is being retried. Click any row for its full history, logs, and — if it failed — an AI-written explanation of what went wrong.",
      side: "top",
      align: "start",
    },
  },
  {
    data: { path: WORKERS },
    element: '[data-tour="worker-cards"]',
    popover: {
      title: "Meet your workers",
      description:
        "These are the actual computer processes doing the work. A pulsing green dot means a worker is alive and healthy. If a worker ever goes quiet — crashes, loses its network — Pulse notices within seconds and automatically hands its unfinished tasks to another worker. Nothing gets lost.",
      side: "bottom",
      align: "start",
    },
  },
  {
    data: { path: DLQ },
    element: '[data-tour="dlq-table"]',
    popover: {
      title: "When things go wrong",
      description:
        'If a task fails too many times in a row, Pulse stops retrying automatically and moves it here instead of trying forever. Nothing is lost — you can see exactly why it failed and click "Replay" to give it another shot once the underlying issue is fixed.',
      side: "top",
      align: "start",
    },
  },
  {
    data: { path: SETTINGS },
    element: '[data-tour="invite-member-btn"]',
    popover: {
      title: "Working with a team",
      description:
        "Invite teammates here and control what they're allowed to do: Viewers can only look around, Members can add and manage tasks, Admins can also configure queues and settings, and Owners have full control over everything.",
      side: "bottom",
      align: "start",
    },
  },
  {
    data: { path: SETTINGS },
    popover: {
      title: "You're ready 🎉",
      description:
        'That\'s everything — queues, jobs, workers, and the dead letter queue. You can restart this tour any time from the "Take a tour" button in the top bar.',
    },
  },
]

export function startTour(navigate: (path: string) => void) {
  const driverObj = driver({
    showProgress: true,
    allowClose: true,
    smoothScroll: true,
    overlayOpacity: 0.65,
    steps,
    onNextClick: async (_el, _step, opts) => {
      const nextIndex = (opts.driver.getActiveIndex() ?? 0) + 1
      const next = steps[nextIndex] as TourStep | undefined
      if (next && next.data.path !== window.location.pathname) {
        navigate(next.data.path)
        if (typeof next.element === "string") await waitForElement(next.element)
      }
      opts.driver.moveNext()
    },
    onPrevClick: async (_el, _step, opts) => {
      const prevIndex = (opts.driver.getActiveIndex() ?? 0) - 1
      const prev = steps[prevIndex] as TourStep | undefined
      if (prev && prev.data.path !== window.location.pathname) {
        navigate(prev.data.path)
        if (typeof prev.element === "string") await waitForElement(prev.element)
      }
      opts.driver.movePrevious()
    },
  })

  const start = () => driverObj.drive()

  if (window.location.pathname !== DASHBOARD) {
    navigate(DASHBOARD)
    waitForElement('[data-tour="stat-cards"]').then(start)
  } else {
    start()
  }
}
