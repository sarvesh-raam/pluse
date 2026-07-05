import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Plus, Trash2 } from "lucide-react"
import { useAuthStore } from "@/lib/auth-store"
import { ApiError, orgsApi } from "@/lib/api"
import type { MemberRole } from "@/types/api"
import { PageHeader } from "@/components/shared/PageHeader"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"

const ROLES: MemberRole[] = ["viewer", "member", "admin", "owner"]

function InviteMemberDialog({ orgId }: { orgId: string }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<MemberRole>("member")

  const inviteMutation = useMutation({
    mutationFn: () => orgsApi.invite(orgId, { email, role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members", orgId] })
      toast.success("Member added")
      setOpen(false)
      setEmail("")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Invite failed"),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button data-tour="invite-member-btn" size="sm" className="glow-cta">
            <Plus className="mr-1.5 h-4 w-4" /> Invite member
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a member</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            inviteMutation.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <p className="text-xs text-muted-foreground">The user must already have a Pulse account.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as MemberRole)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={inviteMutation.isPending}>
              {inviteMutation.isPending ? "Adding..." : "Add member"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Settings() {
  const orgId = useAuthStore((s) => s.currentOrgId)!
  const currentUser = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()

  const { data: members } = useQuery({ queryKey: ["members", orgId], queryFn: () => orgsApi.members(orgId) })

  const roleMutation = useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: MemberRole }) =>
      orgsApi.updateMemberRole(orgId, memberId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members", orgId] })
      toast.success("Role updated")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Update failed"),
  })

  const removeMutation = useMutation({
    mutationFn: (memberId: string) => orgsApi.removeMember(orgId, memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members", orgId] })
      toast.success("Member removed")
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Remove failed"),
  })

  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="Members & roles"
        description="Owners and admins can invite members and manage roles."
        actions={<InviteMemberDialog orgId={orgId} />}
      />

      <div data-tour="members-table" className="overflow-hidden rounded-[var(--radius)] border border-border bg-surface">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {members?.map((member) => (
              <TableRow key={member.id}>
                <TableCell className="font-medium text-foreground">{member.full_name}</TableCell>
                <TableCell className="text-muted-foreground">{member.email}</TableCell>
                <TableCell>
                  <Select
                    value={member.role}
                    onValueChange={(v) => roleMutation.mutate({ memberId: member.id, role: v as MemberRole })}
                  >
                    <SelectTrigger size="sm" className="w-28">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ROLES.map((r) => (
                        <SelectItem key={r} value={r}>
                          {r}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  {member.user_id !== currentUser?.id && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-danger hover:text-danger"
                      onClick={() => removeMutation.mutate(member.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
