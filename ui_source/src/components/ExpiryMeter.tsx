import clsx from 'clsx'
import { formatRemaining } from '../lib/conflicts'

/**
 * Time-remaining meter for a claim.
 *
 * This encodes ONE thing: how much of the claim's TTL is left. Conflict lives
 * in a separate badge, deliberately — if the meter also carried conflict
 * state, the two channels could be confused for one another.
 *
 * The numeric label is always rendered, so the bar is never the only way to
 * read the value.
 */
export function ExpiryMeter({ seconds, ttl }: { seconds: number | null; ttl: number }) {
  const label = formatRemaining(seconds)
  const expired = seconds !== null && seconds <= 0
  const pct = seconds === null || ttl <= 0 ? 0 : Math.min(100, Math.max(0, (seconds / ttl) * 100))

  // Thresholds describe time only — never conflict.
  const tone = expired || pct <= 10 ? 'bg-ui-error'
    : pct <= 33 ? 'bg-amber-500'
    : 'bg-emerald-500'

  return (
    <div className="flex items-center gap-2 min-w-[7.5rem]">
      <div className="flex-1 h-1.5 rounded-full bg-ui-elevated overflow-hidden" role="presentation">
        <div className={clsx('h-full rounded-full transition-[width] duration-500', tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className={clsx('text-xs tabular-nums whitespace-nowrap', expired ? 'text-ui-error' : 'text-ui-text-2')}>
        {label}
      </span>
    </div>
  )
}
