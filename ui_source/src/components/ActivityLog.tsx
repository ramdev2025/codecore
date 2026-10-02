import {
  AlertTriangle, Archive, CheckCircle2, Clock, Megaphone, Sparkles, TimerOff,
} from 'lucide-react'
import type { ReactNode } from 'react'
import clsx from 'clsx'
import type { LockOut } from '../api/client'
import { formatAgo } from '../lib/conflicts'
import type { LogEntry, LogSeverity } from '../lib/log'
import { StatusBadge } from './StatusBadge'

interface Props {
  entries: LogEntry[]
  nowMs: number
  /** Cap the list, for the compact panel on Overview. */
  limit?: number
  onInspect?: (lock: LockOut) => void
  emptyMessage?: string
}

/**
 * Severity carries an icon AND a text label in every row — colour is never
 * the only thing distinguishing a conflict from an announcement.
 */
const SEVERITY: Record<LogSeverity, { label: string; icon: ReactNode; badge: 'error' | 'warning' | 'success' | 'info' | 'neutral' | 'purple'; rail: string }> = {
  conflict:  { label: 'conflict',  icon: <AlertTriangle className="h-3 w-3" />, badge: 'error',   rail: 'bg-ui-error' },
  expiring:  { label: 'expiring',  icon: <Clock className="h-3 w-3" />,         badge: 'warning', rail: 'bg-amber-500' },
  expired:   { label: 'lapsed',    icon: <TimerOff className="h-3 w-3" />,      badge: 'warning', rail: 'bg-amber-500' },
  advisory:  { label: 'AI-suggested · advisory', icon: <Sparkles className="h-3 w-3" />, badge: 'purple', rail: 'bg-purple-400' },
  ok:        { label: 'clear',     icon: <CheckCircle2 className="h-3 w-3" />,  badge: 'success', rail: 'bg-emerald-500' },
  info:      { label: 'announcement', icon: <Megaphone className="h-3 w-3" />,  badge: 'neutral', rail: 'bg-ui-border-strong' },
  closed:    { label: 'closed',    icon: <Archive className="h-3 w-3" />,       badge: 'neutral', rail: 'bg-ui-border-strong' },
}

export function ActivityLog({ entries, nowMs, limit, onInspect, emptyMessage = 'Nothing has happened yet.' }: Props) {
  const shown = limit ? entries.slice(0, limit) : entries

  if (shown.length === 0) {
    return <p className="text-sm text-ui-text-2">{emptyMessage}</p>
  }

  return (
    <ol className="space-y-2">
      {shown.map(entry => {
        const meta = SEVERITY[entry.severity]
        const inspectable = !!entry.lock && !!onInspect
        return (
          <li
            key={entry.id}
            className="relative overflow-hidden rounded-xl border border-ui-border bg-ui-surface shadow-card"
          >
            <span className={clsx('absolute inset-y-0 left-0 w-1', meta.rail)} aria-hidden="true" />
            <div className="pl-4">
              <div className="flex flex-wrap items-start justify-between gap-2 px-4 pt-3.5">
                <p className="min-w-0 break-words text-sm font-semibold text-ui-text">{entry.title}</p>
                <div className="flex flex-shrink-0 items-center gap-2">
                  <StatusBadge label={meta.label} variant={meta.badge} icon={meta.icon} />
                  {/* A past conflict keeps its red rail so it stays findable,
                      which makes saying it is over non-optional. */}
                  {entry.past && entry.severity === 'conflict' && (
                    <StatusBadge label="ended" variant="neutral" />
                  )}
                  <span className="whitespace-nowrap text-xs text-ui-text-2">{formatAgo(entry.atIso, nowMs)}</span>
                </div>
              </div>

              <p className="px-4 pt-1.5 text-sm text-ui-text-2">{entry.what}</p>

              {entry.todo.length > 0 && (
                <div className="mx-4 mt-3 rounded-lg border border-ui-border bg-ui-elevated p-3">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ui-text-2">
                    What you can do
                  </p>
                  <ul className="space-y-1">
                    {entry.todo.map((step, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-ui-text">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-ui-accent" aria-hidden="true" />
                        <span>{step}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="px-4 pb-3.5 pt-3">
                {inspectable ? (
                  <button
                    type="button"
                    onClick={() => onInspect?.(entry.lock!)}
                    className="inline-flex min-h-[36px] items-center rounded-lg border border-ui-border px-3 text-xs font-medium text-ui-text hover:bg-ui-hover focus-visible:ring-2 focus-visible:ring-ui-accent"
                  >
                    Inspect claim
                  </button>
                ) : null}
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
