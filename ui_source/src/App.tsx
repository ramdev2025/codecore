import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, FileCode, LayoutDashboard, Orbit, Radio, RefreshCw, ScrollText, Settings, Users, WifiOff,
} from 'lucide-react'
import type { LockOut } from './api/client'
import { ConflictModal } from './components/ConflictModal'
import { DashShell } from './components/DashShell'
import { StatusBadge } from './components/StatusBadge'
import { useJupiterData } from './hooks/useJupiterData'
import { useServerClock } from './hooks/useServerClock'
import { useTheme } from './hooks/useTheme'
import { hasConflict } from './lib/conflicts'
import { ActivityPage } from './pages/ActivityPage'
import { FilesPage } from './pages/FilesPage'
import { LogPage } from './pages/LogPage'
import { OverviewPage } from './pages/OverviewPage'
import { SettingsPage } from './pages/SettingsPage'
import { SetupWizard } from './pages/SetupWizard'
import { TeamPage } from './pages/TeamPage'
import { useAppStore, type PageId } from './stores/appStore'

const NAV = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard className="w-4 h-4" /> },
  { id: 'files',    label: 'Files',    icon: <FileCode className="w-4 h-4" /> },
  { id: 'log',      label: 'Log',      icon: <ScrollText className="w-4 h-4" /> },
  { id: 'team',     label: 'Team',     icon: <Users className="w-4 h-4" /> },
  { id: 'activity', label: 'Activity', icon: <Activity className="w-4 h-4" /> },
  { id: 'settings', label: 'Settings', icon: <Settings className="w-4 h-4" /> },
]

const TITLES: Record<PageId, string> = {
  overview: 'Overview',
  files: 'Files',
  log: 'Log',
  team: 'Team',
  activity: 'Activity',
  settings: 'Settings',
}

export default function App() {
  useTheme()
  const apiKey = useAppStore(s => s.apiKey)
  const page = useAppStore(s => s.page)
  const setPage = useAppStore(s => s.setPage)

  const { syncFrom, correctedNow } = useServerClock()
  const { activity, semantic, connection, error, refresh } = useJupiterData(apiKey, syncFrom)
  const [inspecting, setInspecting] = useState<LockOut | null>(null)

  const locks = activity?.locks ?? []
  const ttl = activity?.lock_ttl_seconds ?? 300
  // Supplied by the API per request, so the log can say "you hold" rather
  // than naming you in the third person.
  const me = activity?.me?.display_name ?? null
  const conflicted = useMemo(() => locks.filter(l => hasConflict(l, locks)), [locks])

  // Pop the modal the first time a given conflict appears, so a collision is
  // surfaced rather than waiting to be noticed. The `announced` set is what
  // stops a dismissed conflict from re-opening on the next poll, while a
  // genuinely new one still does.
  const announced = useRef<Set<number>>(new Set())
  useEffect(() => {
    const fresh = conflicted.find(l => !announced.current.has(l.lock_id))
    conflicted.forEach(l => announced.current.add(l.lock_id))
    if (fresh) setInspecting(prev => prev ?? fresh)
  }, [conflicted])

  // Keep the open modal's data fresh as claims refresh underneath it.
  useEffect(() => {
    if (!inspecting) return
    const next = locks.find(l => l.lock_id === inspecting.lock_id)
    if (!next) setInspecting(null)
    else if (next !== inspecting) setInspecting(next)
  }, [locks, inspecting])

  if (!apiKey) return <SetupWizard />

  const nowMs = correctedNow()

  return (
    <>
      <DashShell
        navItems={NAV}
        activePage={page}
        onNavigate={id => setPage(id as PageId)}
        appName="Jupiter"
        appIcon={<Orbit className="w-5 h-5" />}
        userDisplayName={activity?.slug}
        breadcrumbs={[{ label: activity?.slug ?? 'Jupiter' }, { label: TITLES[page] }]}
        headerAccessory={<ConnectionPill connection={connection} error={error} />}
        badges={{ log: conflicted.length, files: conflicted.length }}
      >
        {page === 'overview' && (
          <OverviewPage
            activity={activity} semantic={semantic} nowMs={nowMs} me={me}
            onInspect={setInspecting} onSeeLog={() => setPage('log')}
          />
        )}
        {page === 'files' && <FilesPage activity={activity} nowMs={nowMs} onInspect={setInspecting} />}
        {page === 'log' && (
          <LogPage activity={activity} semantic={semantic} nowMs={nowMs} me={me} onInspect={setInspecting} />
        )}
        {page === 'team' && <TeamPage activity={activity} nowMs={nowMs} />}
        {page === 'activity' && <ActivityPage activity={activity} nowMs={nowMs} onPosted={() => void refresh()} />}
        {page === 'settings' && <SettingsPage activity={activity} semantic={semantic} />}
      </DashShell>

      <ConflictModal
        lock={inspecting}
        allLocks={locks}
        ttl={ttl}
        nowMs={nowMs}
        onClose={() => setInspecting(null)}
      />
    </>
  )
}

function ConnectionPill({ connection, error }: { connection: string; error: string | null }) {
  if (connection === 'live') {
    return <StatusBadge label="live" variant="success" icon={<Radio className="w-3 h-3" />} />
  }
  if (connection === 'polling') {
    return <StatusBadge label="polling" variant="warning" icon={<RefreshCw className="w-3 h-3" />} />
  }
  if (connection === 'error') {
    return <StatusBadge label={error ? 'disconnected' : 'error'} variant="error" icon={<WifiOff className="w-3 h-3" />} />
  }
  return <StatusBadge label="connecting" variant="neutral" icon={<RefreshCw className="w-3 h-3" />} />
}
