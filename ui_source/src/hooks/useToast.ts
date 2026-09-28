import { create } from 'zustand'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'
export interface Toast { id: string; message: string; variant: ToastVariant; duration?: number }

interface ToastState {
  toasts: Toast[]
  show: (message: string, variant?: ToastVariant, duration?: number) => void
  dismiss: (id: string) => void
}

export const useToast = create<ToastState>((set, get) => ({
  toasts: [],
  show: (message, variant = 'info', duration = 4000) => {
    const id = crypto.randomUUID()
    set(s => ({ toasts: [...s.toasts, { id, message, variant, duration }] }))
    if (duration > 0) setTimeout(() => get().dismiss(id), duration)
  },
  dismiss: (id) => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
}))
