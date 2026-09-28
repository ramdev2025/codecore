import { lazy, Suspense, useMemo } from 'react'
import { AlertTriangle, ArrowRight, FileCode, Sparkles, Timer, Users } from 'lucide-react'
import type { ActivityOut, LockOut, SemanticOut } from '../api/client'
import { ActivityLog } from '../components/ActivityLog'
import { AdvisorPanel } from '../components/AdvisorPanel'
import { ClaimsTable } from '../components/ClaimsTable'
import { PageHeader } from '../components/PageHeader'
import { StatCard } from '../components/StatCard'
import { hasConflict, secondsRemaining } from '../lib/conflicts'
import { buildLog } from '../lib/log'

// recharts is by far the heaviest dependency here and this donut is the only
// thing that uses it, so it loads on demand instead of blocking first paint.
const DonutChart = lazy(() =>
  import('../components/charts').then(m => ({ default: m.DonutChart })),
)

interface Props {
  activity: ActivityOut | null
  semantic: SemanticOut | null
  nowMs: number
  me?: string | null
  onInspect?: (lock: LockOut) => void
  onSeeLog?: () => void
}

const EXPIRING_SOON_SECONDS = 60

export function OverviewPage({ activity, semantic, nowMs, me, onInspect, onSeeLog }: Props) {
  const locks = activity?.locks ?? []
  const ttl = activity?.lock_ttl_seconds ?? 300

  const conflicts = locks.filter(l => hasConflict(l, locks))
  const expiringSoon = locks.filter(l => {
    const s = secondsRemaining(l.expires_at, nowMs)
    return s !== null && s > 0 && s <= EXPIRING_SOON_SECONDS
  })
  const editing = locks.filter(l => l.intent === 'editing').length
  const reading = locks.length - editing
  const findings = semantic?.status === 'ready' ? semantic.overlaps.length : 0

  // Only the entries worth acting on get the compact panel; the Log page has everything.
  const attention = useMemo(
    () => buildLog(activity, semantic, nowMs, me)
      .filter(e => e.severity === 'conflict' || e.severity === 'advisory' || e.severity === 'expired'),
    [activity, semantic, nowMs, me],
  )

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle={activity ? `Team ${activity.slug} · claims auto-expire ${ttl}s after their last refresh` : 'Connecting…'}
      />
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6 space-y-6">
        <div className="grid gap-3 sm:gap-4 grid-cols-2 xl:grid-cols-4">
          <StatCard label="Active claims" value={locks.length} icon={<FileCode className="w-5 h-5" />} />
          <StatCard label="Live teammates" value={activity?.active_members.length ?? 0} color="emerald" icon={<Users className="w-5 h-5" />} />
          <StatCard
            label="Expiring soon"
            value={expiringSoon.length}
            color="amber"
            hint={`within ${EXPIRING_SOON_SECONDS}s`}
            icon={<Timer className="w-5 h-5" />}
          />
          <StatCard
            label="Advisor findings"
            value={semantic?.status === 'disabled' ? 'off' : findings}
            color="purple"
            hint={semantic?.status === 'disabled' ? 'overlap detection disabled' : 'advisory only'}
            icon={<Sparkles className="w-5 h-5" />}
          />
        </div>

        {conflicts.length > 0 && (
          <button
            type="button"
            onClick={() => onInspect?.(conflicts[0])}
            className="flex w-full items-start gap-3 rounded-xl border border-ui-error/20 bg-ui-error-bg p-4 text-left text-sm text-ui-error hover:bg-ui-error/10 focus-visible:ring-2 focus-visible:ring-ui-error"
          >
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="mb-0.5 block font-semibold">
                {conflicts.length} claim{conflicts.length === 1 ? '' : 's'} in conflict
              </span>
              <span className="block opacity-90">
                The same lines are claimed by two people and at least one is editing. Claims are advisory —
                tap to see the overlap and what you can do.
              </span>
            </span>
            <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
          </button>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-3 lg:col-span-2">
            <h2 className="text-sm font-semibold text-ui-text">Files claimed right now</h2>
            <ClaimsTable locks={locks} ttl={ttl} nowMs={nowMs} onInspect={onInspect} />
          </div>
          <div className="space-y-6">
            <AdvisorPanel semantic={semantic} />
            <section className="rounded-xl border border-ui-border bg-ui-surface p-5 shadow-card" aria-labelledby="attention-heading">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 id="attention-heading" className="text-sm font-semibold text-ui-text">Needs attention</h2>
                {onSeeLog && (
                  <button
                    type="button"
                    onClick={onSeeLog}
                    className="inline-flex min-h-[32px] items-center gap-1 rounded-lg px-2 text-xs font-medium text-ui-accent hover:bg-ui-hover focus-visible:ring-2 focus-visible:ring-ui-accent"
                  >
                    Full log <ArrowRight className="h-3 w-3" aria-hidden="true" />
                  </button>
                )}
              </div>
              <ActivityLog
                entries={attention}
                nowMs={nowMs}
                limit={3}
                onInspect={onInspect}
                emptyMessage="Nothing needs your attention — no conflicts or advisory findings."
              />
            </section>
            <div className="rounded-xl border border-ui-border bg-ui-surface p-5 shadow-card">
              <h2 className="mb-4 text-sm font-semibold text-ui-text">Claim intent</h2>
              {locks.length === 0 ? (
                <p className="text-sm text-ui-text-2">Nothing claimed yet.</p>
              ) : (
                <Suspense fallback={<div className="h-[200px]" aria-label="Loading chart" />}>
                  <DonutChart
                    height={200}
                    centerValue={locks.length}
                    centerLabel="claims"
                    data={[
                      { name: 'editing', value: editing },
                      { name: 'reading', value: reading },
                    ].filter(d => d.value > 0)}
                  />
                </Suspense>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
