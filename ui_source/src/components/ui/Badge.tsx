import clsx from 'clsx'

type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'purple'
const styles: Record<BadgeVariant, string> = {
  default: 'bg-ui-elevated text-ui-text-2 border-ui-border',
  success: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  warning: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  error:   'bg-ui-error-bg text-ui-error border-ui-error/20',
  info:    'bg-ui-info-bg text-ui-info border-ui-info/20',
  purple:  'bg-purple-500/10 text-purple-400 border-purple-500/20',
}
const dotColors: Record<BadgeVariant, string> = {
  default: 'bg-ui-text-2', success: 'bg-emerald-500', warning: 'bg-amber-500',
  error: 'bg-ui-error', info: 'bg-ui-info', purple: 'bg-purple-400',
}

export function Badge({ label, variant = 'default', dot }: { label: string; variant?: BadgeVariant; dot?: boolean }) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border', styles[variant])}>
      {dot && <span className={clsx('w-1.5 h-1.5 rounded-full', dotColors[variant])} />}
      {label}
    </span>
  )
}
