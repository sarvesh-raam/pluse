import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useAuthStore } from "@/lib/auth-store"
import { Play, Loader2, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { jobsApi, queuesApi } from "@/lib/api"
import { cn } from "@/lib/utils"

interface LoadGeneratorProps {
  queueId: string
  className?: string
}

export function LoadGenerator({ className }: Omit<LoadGeneratorProps, 'queueId'>) {
  const projectId = useAuthStore((s) => s.currentProjectId)!
  const { data: queues } = useQuery({
    queryKey: ["queues", projectId],
    queryFn: () => queuesApi.list(projectId),
  })
  
  const queueId = queues?.items?.[0]?.id

  const [jobCount, setJobCount] = useState(100)
  const [isFiring, setIsFiring] = useState(false)
  const [progress, setProgress] = useState(0)

  const handleFire = async () => {
    if (!queueId) return
    setIsFiring(true)
    setProgress(0)
    
    const BATCH_SIZE = 50
    let completed = 0

    try {
      for (let i = 0; i < jobCount; i += BATCH_SIZE) {
        const chunk = Math.min(BATCH_SIZE, jobCount - i)
        const promises = Array.from({ length: chunk }).map(() =>
          jobsApi.create({
            queue_id: queueId,
            type: "immediate",
            handler: "sleep",
            payload: { seconds: 1 }, // Short sleep to burn through them fast
          })
        )
        await Promise.all(promises)
        completed += chunk
        setProgress(Math.round((completed / jobCount) * 100))
      }
    } catch (err) {
      console.error("Failed to blast jobs", err)
    } finally {
      setIsFiring(false)
      setTimeout(() => setProgress(0), 2000)
    }
  }

  return (
    <div className={cn("relative overflow-hidden rounded-2xl border border-border bg-surface p-6", className)}>
      <div className="absolute inset-0 bg-gradient-to-br from-brand/5 to-transparent pointer-events-none" />
      
      <div className="relative flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-brand" />
            <h3 className="font-semibold text-foreground">Load Generator</h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Stress test event-driven dispatch (LISTEN/NOTIFY) on queue: <strong className="text-foreground">{queues?.items?.[0]?.name || "Loading..."}</strong>
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 rounded-full border border-border bg-background px-4 py-1.5">
            <Input 
              type="number" 
              min={1} 
              max={1000} 
              value={jobCount} 
              onChange={(e) => setJobCount(Math.min(1000, Math.max(1, parseInt(e.target.value) || 1)))}
              className="w-16 h-8 text-center"
              disabled={isFiring || !queueId}
            />
            <input
              type="range"
              min="1"
              max="1000"
              value={jobCount}
              onChange={(e) => setJobCount(parseInt(e.target.value))}
              disabled={isFiring || !queueId}
              className="w-24 accent-brand"
            />
          </div>

          <Button 
            size="sm" 
            disabled={isFiring || !queueId} 
            onClick={handleFire}
            className="rounded-full bg-brand px-6 text-brand-foreground hover:bg-brand/90 min-w-[120px]"
            nativeButton
          >
            {isFiring ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {progress}%
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4 fill-current" />
                Blast Jobs
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
