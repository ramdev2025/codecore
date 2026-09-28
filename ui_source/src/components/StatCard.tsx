import clsx from 'clsx'
interface Props { label: string; value: string | number; delta?: string; deltaPositive?: boolean; icon?: React.ReactNode; color?: string; hint?: string }
export function StatCard({ label, value, delta, deltaPositive, icon, color = 'brand', hint }: Props) {
  const iconClass = color === 'red'     ? 'bg-red-500/10 text-red-500'
    : color === 'emerald'               ? 'bg-emerald-500/10 text-emerald-500'
    : color === 'amber'                 ? 'bg-amber-500/10 text-amber-500'
    : color === 'orange'                ? 'bg-orange-500/10 text-orange-500'
    : color === 'purple'                ? 'bg-purple-500/10 text-purple-400'
    :                                     'bg-ui-accent-muted text-ui-accent'
  return (
    <div className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-5 flex items-start justify-between">
      <div>
        <p className="text-xs font-medium text-ui-text-2 uppercase tracking-wide mb-1">{label}</p>
        <p className="text-2xl font-bold text-ui-text">{value}</p>
        {delta && (
          <p className={clsx('text-xs mt-1 font-medium', deltaPositive ? 'text-emerald-500' : 'text-ui-error')}>
            {deltaPositive ? '↑' : '↓'} {delta}
          </p>
        )}
        {hint && !delta && <p className="text-xs mt-1 text-ui-text-2">{hint}</p>}
      </div>
      {icon && <div className={clsx('p-2.5 rounded-lg', iconClass)}>{icon}</div>}
    </div>
  )
}
