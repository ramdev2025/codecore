import { create } from 'zustand'
import { readStoredKey, writeStoredKey } from '../api/client'

export type PageId = 'overview' | 'files' | 'log' | 'team' | 'activity' | 'settings'

interface AppState {
  page: PageId
  apiKey: string | null
  setPage: (p: PageId) => void
  setApiKey: (k: string | null) => void
  signOut: () => void
}

export const useAppStore = create<AppState>((set) => ({
  page: 'overview',
  apiKey: readStoredKey(),
  setPage: (page) => set({ page }),
  setApiKey: (apiKey) => {
    writeStoredKey(apiKey)
    set({ apiKey })
  },
  signOut: () => {
    writeStoredKey(null)
    set({ apiKey: null, page: 'overview' })
  },
}))
