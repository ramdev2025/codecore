import { create } from 'zustand'
import { useMediaQuery } from './useMediaQuery'
import { useEffect } from 'react'

export type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  setTheme: (t: Theme) => void
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: (localStorage.getItem('ui-theme') as Theme) ?? 'system',
  resolvedTheme: 'light',
  setTheme: (theme) => {
    localStorage.setItem('ui-theme', theme)
    set({ theme })
  },
}))

export function useTheme() {
  const { theme, resolvedTheme, setTheme } = useThemeStore()
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  useEffect(() => {
    const resolved = theme === 'system' ? (prefersDark ? 'dark' : 'light') : theme
    useThemeStore.setState({ resolvedTheme: resolved })
    document.documentElement.setAttribute('data-theme', resolved)
  }, [theme, prefersDark])
  return { theme, resolvedTheme, setTheme, isDark: resolvedTheme !== 'light' }
}
