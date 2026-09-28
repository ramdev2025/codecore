import clsx from 'clsx'
import type { ReactNode } from 'react'

type Variant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'purple'
const styles: Record<Variant, string> = {
  success: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  warning: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  error:   'bg-ui-error-bg text-ui-error border-ui-error/20',
  info:    'bg-ui-info-bg text-ui-info border-ui-info/20',
  neutral: 'bg-ui-elevated text-ui-text-2 border-ui-border',
  purple:  'bg-purple-500/10 text-purple-400 border-purple-500/20',
}

/**
 * `icon` is not decoration. Every status in this UI carries an icon AND its
 * text label, so colour is never the only channel communicating state.
 */
export function StatusBadge({ label, variant = 'neutral', icon }: { label: string; variant?: Variant; icon?: ReactNode }) {
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border', styles[variant])}>
      {icon && <span className="flex-shrink-0 w-3 h-3 inline-flex items-center justify-center" aria-hidden="true">{icon}</span>}
      {label}
    </span>
  )
}
