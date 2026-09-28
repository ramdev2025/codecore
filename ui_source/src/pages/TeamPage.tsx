import { useEffect, useState } from 'react'
import { CircleDot, Moon, RefreshCw } from 'lucide-react'
import { api, type ActivityOut, type MemberOut } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { Button, Spinner } from '../components/ui'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { formatAgo } from '../lib/conflicts'

interface Props {
  activity: ActivityOut | null
  nowMs: number
}

export function TeamPage({ activity, nowMs }: Props) {
  const isMobile = useMediaQuery('(max-width: 639px)')
  const slug = activity?.slug
  const [members, setMembers] = useState<MemberOut[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async (s: string) => {
    setLoading(true)
    try {
      // Coerced at the boundary: the endpoint returns a bare array, but an
      // unexpected shape must not take the whole page down with a
      // "map is not a function" render crash.
      const rows = await api.members(s)
      if (Array.isArray(rows)) {
        setMembers(rows)
        setError(null)
      } else {
        setMembers([])
        setError('Unexpected response from /api/orgs/{slug}/members — expected a list of members.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (slug) void load(slug) }, [slug])

  const liveNames = new Set(activity?.active_members ?? [])

  return (
    <>
      <PageHeader
        title="Team"
        subtitle={slug ? `Members of ${slug}` : 'Connecting…'}
        actions={
          <Button variant="secondary" size="sm" icon={<RefreshCw className="w-3.5 h-3.5" />}
            onClick={() => slug && void load(slug)} disabled={!slug || loading}>
            Refresh
          </Button>
        }
      />
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        {error && <p className="text-sm text-ui-error mb-4">{error}</p>}
        {members === null ? (
          <Spinner label="Loading members…" />
        ) : isMobile ? (
          <ul className="space-y-2">
            {members.length === 0 ? (
              <li className="rounded-xl border border-ui-border bg-ui-surface p-10 text-center text-ui-text-2 shadow-card">
                No members yet.
              </li>
            ) : members.map(m => {
              const live = m.active_sessions > 0 || liveNames.has(m.display_name)
              return (
                <li key={m.member_id} className="rounded-xl border border-ui-border bg-ui-surface p-4 shadow-card">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ui-text">{m.display_name}</span>
                    {live
                      ? <StatusBadge label="live" variant="success" icon={<CircleDot className="w-3 h-3" />} />
                      : <StatusBadge label="idle" variant="neutral" icon={<Moon className="w-3 h-3" />} />}
                  </div>
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div className="flex gap-1.5">
                      <dt className="text-ui-text-2">Sessions</dt>
                      <dd className="tabular-nums text-ui-text">{m.active_sessions}</dd>
                    </div>
                    <div className="flex gap-1.5">
                      <dt className="text-ui-text-2">Last seen</dt>
                      <dd className="text-ui-text">{formatAgo(m.last_seen, nowMs)}</dd>
                    </div>
                    <div className="flex gap-1.5">
                      <dt className="text-ui-text-2">Joined</dt>
                      <dd className="text-ui-text">
                        {m.joined_at ? new Date(m.joined_at).toLocaleDateString() : '—'}
                      </dd>
                    </div>
                  </dl>
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="w-full overflow-x-auto rounded-xl border border-ui-border bg-ui-surface shadow-card">
            <table className="w-full text-sm">
              <caption className="sr-only">Team members</caption>
              <thead>
                <tr className="border-b border-ui-border bg-ui-elevated">
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-ui-text-2 uppercase tracking-wide">Member</th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-ui-text-2 uppercase tracking-wide">Presence</th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-ui-text-2 uppercase tracking-wide">Sessions</th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-ui-text-2 uppercase tracking-wide">Last seen</th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold text-ui-text-2 uppercase tracking-wide">Joined</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ui-border">
                {members.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-10 text-center text-ui-text-2">No members yet.</td></tr>
                ) : members.map(m => {
                  const live = m.active_sessions > 0 || liveNames.has(m.display_name)
                  return (
                    <tr key={m.member_id} className="hover:bg-ui-hover transition-colors">
                      <td className="px-4 py-3 text-ui-text">{m.display_name}</td>
                      <td className="px-4 py-3">
                        {live
                          ? <StatusBadge label="live" variant="success" icon={<CircleDot className="w-3 h-3" />} />
                          : <StatusBadge label="idle" variant="neutral" icon={<Moon className="w-3 h-3" />} />}
                      </td>
                      <td className="px-4 py-3 text-ui-text tabular-nums">{m.active_sessions}</td>
                      <td className="px-4 py-3 text-ui-text-2 whitespace-nowrap">{formatAgo(m.last_seen, nowMs)}</td>
                      <td className="px-4 py-3 text-ui-text-2 whitespace-nowrap">
                        {m.joined_at ? new Date(m.joined_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
