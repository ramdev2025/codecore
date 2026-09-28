import { useMemo, useState } from 'react'
import type { ActivityOut, LockOut, SemanticOut } from '../api/client'
import { ActivityLog } from '../components/ActivityLog'
import { PageHeader } from '../components/PageHeader'
import { Select } from '../components/ui'
import { buildLog, countBySeverity, type LogSeverity } from '../lib/log'

interface Props {
  activity: ActivityOut | null
  semantic: SemanticOut | null
  nowMs: number
  me?: string | null
  onInspect: (lock: LockOut) => void
}

type Filter = 'all' | 'attention' | LogSeverity

export function LogPage({ activity, semantic, nowMs, me, onInspect }: Props) {
  const [filter, setFilter] = useState<Filter>('all')

  const entries = useMemo(
    () => buildLog(activity, semantic, nowMs, me),
    [activity, semantic, nowMs, me],
  )
  const counts = useMemo(() => countBySeverity(entries), [entries])

  const filtered = useMemo(() => {
    if (filter === 'all') return entries
    if (filter === 'attention') {
      return entries.filter(e => e.severity === 'conflict' || e.severity === 'expiring' || e.severity === 'expired')
    }
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
              { label: `Needs attention (${counts.conflict + counts.expiring + counts.expired})`, value: 'attention' },
              { label: `Conflicts (${counts.conflict})`, value: 'conflict' },
              { label: `AI-suggested (${counts.advisory})`, value: 'advisory' },
              { label: `Clear (${counts.ok})`, value: 'ok' },
              { label: `Announcements (${counts.info})`, value: 'info' },
            ]}
          />
        </div>

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
