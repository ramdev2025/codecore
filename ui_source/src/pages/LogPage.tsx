import { useMemo, useState } from 'react'
import type { ActivityOut, LockOut, SemanticOut } from '../api/client'
import { ActivityLog } from '../components/ActivityLog'
import { PageHeader } from '../components/PageHeader'
import { Select } from '../components/ui'
import { useClaimHistory } from '../hooks/useClaimHistory'
import { buildLog, countBySeverity, type LogEntry, type LogSeverity } from '../lib/log'

interface Props {
  activity: ActivityOut | null
  semantic: SemanticOut | null
  nowMs: number
  me?: string | null
  onInspect: (lock: LockOut) => void
}

type Filter = 'all' | 'attention' | LogSeverity

/**
 * `past` is excluded on purpose: a conflict that already ended keeps its red
 * rail so it stays findable, but there is nothing left to act on.
 */
const needsAttention = (e: LogEntry) =>
  !e.past && (e.severity === 'conflict' || e.severity === 'expiring' || e.severity === 'expired')

export function LogPage({ activity, semantic, nowMs, me, onInspect }: Props) {
  const [filter, setFilter] = useState<Filter>('all')

  // Refetch history whenever a claim appears or disappears, which is exactly
  // when a row is added to it. Sorted so a reordered payload is not mistaken
  // for a change.
  const liveKey = useMemo(
    () => (activity?.locks ?? []).map(l => l.lock_id).sort((a, b) => a - b).join(','),
    [activity],
  )
  const { claims: history, error: historyError } = useClaimHistory(liveKey)

  const entries = useMemo(
    () => buildLog(activity, semantic, nowMs, me, history),
    [activity, semantic, nowMs, me, history],
  )
  const counts = useMemo(() => countBySeverity(entries), [entries])
  const attention = useMemo(() => entries.filter(needsAttention).length, [entries])

  const filtered = useMemo(() => {
    if (filter === 'all') return entries
    if (filter === 'attention') return entries.filter(needsAttention)
    return entries.filter(e => e.severity === filter)
  }, [entries, filter])

  return (
    <>
      <PageHeader
        title="Log"
        subtitle="What happened, what it means, and what you can do about it"
      />
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        <div className="max-w-xs">
          <Select
            label="Show"
            value={filter}
            onChange={e => setFilter(e.target.value as Filter)}
            options={[
              { label: `Everything (${entries.length})`, value: 'all' },
              { label: `Needs attention (${attention})`, value: 'attention' },
              { label: `Conflicts (${counts.conflict})`, value: 'conflict' },
              { label: `AI-suggested (${counts.advisory})`, value: 'advisory' },
              { label: `Clear (${counts.ok})`, value: 'ok' },
              { label: `Closed claims (${counts.closed})`, value: 'closed' },
              { label: `Announcements (${counts.info})`, value: 'info' },
            ]}
          />
        </div>

        {historyError && (
          <p className="text-sm text-ui-text-2">
            Showing live claims only — past claims could not be loaded ({historyError}).
          </p>
        )}

        <ActivityLog
          entries={filtered}
          nowMs={nowMs}
          onInspect={onInspect}
          emptyMessage={
            entries.length === 0
              ? 'Nothing to report — no claims, findings or announcements yet.'
              : 'No entries match this filter.'
          }
        />
      </div>
    </>
  )
}
