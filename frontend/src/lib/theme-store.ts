import { create } from "zustand"
import { persist } from "zustand/middleware"

export type ThemeMode = "light" | "dark" | "system"

interface ThemeState {
  mode: ThemeMode
  setMode: (mode: ThemeMode) => void
}

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "dark"
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

/** Apply or remove the `.dark` class on `<html>`. */
function applyTheme(mode: ThemeMode) {
  const resolved = mode === "system" ? getSystemTheme() : mode
  const root = document.documentElement
  if (resolved === "dark") {
    root.classList.add("dark")
  } else {
    root.classList.remove("dark")
  }
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: "dark",
      setMode: (mode) => {
        applyTheme(mode)
        set({ mode })
      },
    }),
    {
      name: "pulse-theme",
      onRehydrateStorage: () => (state) => {
        // Apply on first load after hydration
        if (state) applyTheme(state.mode)
      },
    }
  )
)

/** Call this once in app init to react to OS theme changes when mode is "system". */
export function initThemeListener() {
  const mql = window.matchMedia("(prefers-color-scheme: dark)")

  // Apply immediately from persisted state
  applyTheme(useThemeStore.getState().mode)

  // Listen for OS changes
  const handler = () => {
    if (useThemeStore.getState().mode === "system") {
      applyTheme("system")
    }
  }
  mql.addEventListener("change", handler)
  return () => mql.removeEventListener("change", handler)
}
