import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import type { ActivityOut, LockOut } from '../api/client'
import { ClaimsTable } from '../components/ClaimsTable'
import { PageHeader } from '../components/PageHeader'
import { Input, Select } from '../components/ui'
import { useDebounce } from '../hooks/useDebounce'

interface Props {
  activity: ActivityOut | null
  nowMs: number
  onInspect?: (lock: LockOut) => void
}

export function FilesPage({ activity, nowMs, onInspect }: Props) {
  const [query, setQuery] = useState('')
  const [intent, setIntent] = useState('all')
  const [holder, setHolder] = useState('all')
  const debounced = useDebounce(query, 200)

  const locks = activity?.locks ?? []
  const ttl = activity?.lock_ttl_seconds ?? 300

  const holders = useMemo(
    () => Array.from(new Set(locks.map(l => l.member))).sort(),
    [locks],
  )

  const filtered = useMemo(() => {
    const q = debounced.trim().toLowerCase()
    return locks.filter(l => {
      if (intent !== 'all' && l.intent !== intent) return false
      if (holder !== 'all' && l.member !== holder) return false
      if (!q) return true
      return (
        l.file_path.toLowerCase().includes(q) ||
        l.member.toLowerCase().includes(q) ||
        (l.note ?? '').toLowerCase().includes(q)
      )
    })
  }, [locks, debounced, intent, holder])

  return (
    <>
      <PageHeader
        title="Files"
        subtitle={`${filtered.length} of ${locks.length} claim${locks.length === 1 ? '' : 's'} shown`}
      />
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6 space-y-4">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem_12rem]">
          <Input
            label="Search"
            placeholder="path, holder or note…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            icon={<Search className="w-4 h-4" />}
          />
          <Select
            label="Intent"
            value={intent}
            onChange={e => setIntent(e.target.value)}
            options={[
              { label: 'All intents', value: 'all' },
              { label: 'Editing', value: 'editing' },
              { label: 'Reading', value: 'reading' },
            ]}
          />
          <Select
            label="Held by"
            value={holder}
            onChange={e => setHolder(e.target.value)}
            options={[{ label: 'Everyone', value: 'all' }, ...holders.map(h => ({ label: h, value: h }))]}
          />
        </div>

        <ClaimsTable
          locks={filtered}
          ttl={ttl}
          nowMs={nowMs}
          onInspect={onInspect}
          emptyMessage={locks.length === 0 ? 'No files are currently claimed by anyone.' : 'No claims match these filters.'}
        />
      </div>
    </>
  )
}
