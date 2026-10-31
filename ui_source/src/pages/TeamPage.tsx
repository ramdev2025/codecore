import { useCallback, useEffect, useState } from 'react'
import { CircleDot, Moon, Plus, RefreshCw, Trash2, Users, X } from 'lucide-react'
import { api, type ActivityOut, type MemberOut, type TeamOut } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { Button, Spinner } from '../components/ui'
import { useBilling } from '../hooks/useBilling'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useToast } from '../hooks/useToast'
import { formatAgo } from '../lib/conflicts'

interface Props {
  activity: ActivityOut | null
  nowMs: number
  active: boolean
}

export function TeamPage({ activity, nowMs, active }: Props) {
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
        <div className="space-y-6">
          <DeveloperTeams active={active} members={members ?? []} />
          {error && <p className="text-sm text-ui-error">{error}</p>}
          {members === null ? (
            <Spinner label="Loading members…" />
          ) : isMobile ? (
            <ul className="space-y-2">
              {members.length === 0 ? (
                <li className="rounded-xl border border-ui-border bg-ui-surface p-10 text-center text-ui-text-2 shadow-card">
                  No members yet.
                </li>
              ) : members.map(m => {
                const live = m.active_sessions > 0 || liveNames(activity, m.display_name)
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
                    const live = m.active_sessions > 0 || liveNames(activity, m.display_name)
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
      </div>
    </>
  )
}

function liveNames(activity: ActivityOut | null, display_name: string): boolean {
  return (activity?.active_members ?? []).includes(display_name)
}

// ---------------------------------------------------------------------------
// Developer teams — the plan-capped grouping this page exists to manage
// ---------------------------------------------------------------------------

function DeveloperTeams({ active, members }: { active: boolean; members: MemberOut[] }) {
  const { billing, refresh: refreshBilling } = useBilling(active)
  const toast = useToast(s => s.show)
  const [teams, setTeams] = useState<TeamOut[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  const loadTeams = useCallback(async () => {
    try {
      const out = await api.teams()
      setTeams(Array.isArray(out.teams) ? out.teams : [])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    if (active) void loadTeams()
  }, [active, loadTeams])

  const create = async () => {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try {
      await api.createTeam(name)
      toast(`Team '${name}' created`, 'success')
      setNewName('')
      await loadTeams()
      void refreshBilling()
    } catch (e) {
      // 402 carries the upgrade prompt from the server.
      toast(e instanceof Error ? e.message : String(e), 'error')
      await loadTeams()
    } finally {
      setCreating(false)
    }
  }

  const remove = async (teamId: number, name: string) => {
    try {
      await api.deleteTeam(teamId)
      toast(`Team '${name}' deleted`, 'success')
      await loadTeams()
      void refreshBilling()
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'error')
    }
  }

  const toggleMember = async (teamId: number, memberId: number, currentlyIn: boolean) => {
    try {
      if (currentlyIn) {
        await api.removeTeamMember(teamId, memberId)
      } else {
        await api.addTeamMember(teamId, memberId)
      }
      await loadTeams()
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'error')
    }
  }

  const maxTeams = billing?.max_teams ?? 1
  const count = teams?.length ?? 0

  return (
    <section className="rounded-xl border border-ui-border bg-ui-surface p-5 shadow-card" aria-labelledby="teams-heading">
      <div className="flex items-center justify-between gap-2 mb-3">
        <h2 id="teams-heading" className="text-sm font-semibold text-ui-text flex items-center gap-2">
          <Users className="w-4 h-4 text-ui-accent" aria-hidden="true" />
          Developer teams
          {billing && <span className="text-ui-text-2 font-normal">— {count} / {maxTeams} allowed</span>}
        </h2>
      </div>

      {error && <p className="text-sm text-ui-error mb-3">{error}</p>}

      <div className="flex flex-wrap items-start gap-2 mb-4">
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') void create() }}
          placeholder="New team name"
          aria-label="New team name"
          className="flex-1 min-w-[180px] max-w-xs rounded-lg border border-ui-border bg-ui-surface px-3 py-2 text-sm text-ui-text placeholder:text-ui-muted hover:border-ui-border-strong focus:outline-none focus:ring-2 focus:ring-ui-accent focus:border-ui-accent"
        />
        <Button size="md" icon={<Plus className="w-4 h-4" />} loading={creating} disabled={!newName.trim()} onClick={() => void create()}>
          Create team
        </Button>
      </div>

      {teams === null ? (
        <Spinner label="Loading teams…" />
      ) : teams.length === 0 ? (
        <p className="text-sm text-ui-text-2">
          No developer teams yet. Group members into teams to organize who works on what —
          your plan allows {maxTeams}.
        </p>
      ) : (
        <ul className="space-y-3">
          {teams.map(team => (
            <li key={team.team_id} className="rounded-lg border border-ui-border p-3">
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-sm font-medium text-ui-text">{team.name}</span>
                <Button variant="ghost" size="sm" icon={<Trash2 className="w-3.5 h-3.5" />}
                  onClick={() => void remove(team.team_id, team.name)}>
                  Delete
                </Button>
              </div>
              {team.members.length === 0 ? (
                <p className="text-xs text-ui-text-2 mb-2">No members assigned.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {team.members.map(m => (
                    <span key={m.member_id} className="inline-flex items-center gap-1 rounded-full border border-ui-border bg-ui-elevated px-2 py-0.5 text-xs text-ui-text">
                      {m.display_name}
                      <button
                        aria-label={`Remove ${m.display_name} from ${team.name}`}
                        onClick={() => void toggleMember(team.team_id, m.member_id, true)}
                        className="text-ui-text-2 hover:text-ui-error transition-colors"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <details className="text-xs">
                <summary className="text-ui-accent cursor-pointer select-none">Add member</summary>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {members
                    .filter(m => !team.members.some(tm => tm.member_id === m.member_id))
                    .map(m => (
                      <button
                        key={m.member_id}
                        onClick={() => void toggleMember(team.team_id, m.member_id, false)}
                        className="rounded-full border border-dashed border-ui-border-strong px-2 py-0.5 text-ui-text-2 hover:border-ui-accent hover:text-ui-accent transition-colors"
                      >
                        + {m.display_name}
                      </button>
                    ))}
                  {members.filter(m => !team.members.some(tm => tm.member_id === m.member_id)).length === 0 && (
                    <span className="text-ui-text-2">Every member is already in this team.</span>
                  )}
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
