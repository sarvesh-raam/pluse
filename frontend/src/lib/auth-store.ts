import { create } from "zustand"
import { persist } from "zustand/middleware"
import type { OrgMembership, User } from "@/types/api"

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
  memberships: OrgMembership[]
  currentOrgId: string | null
  currentProjectId: string | null

  setSession: (data: {
    accessToken: string
    refreshToken: string
    user: User
    memberships: OrgMembership[]
  }) => void
  setTokens: (accessToken: string, refreshToken: string) => void
  setWorkspace: (orgId: string | null, projectId: string | null) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      memberships: [],
      currentOrgId: null,
      currentProjectId: null,

      setSession: ({ accessToken, refreshToken, user, memberships }) =>
        set({ accessToken, refreshToken, user, memberships }),
      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setWorkspace: (orgId, projectId) =>
        set({ currentOrgId: orgId, currentProjectId: projectId }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          memberships: [],
          currentOrgId: null,
          currentProjectId: null,
        }),
    }),
    { name: "pulse-auth" }
  )
)
