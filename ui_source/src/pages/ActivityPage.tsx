import { useState } from 'react'
import { Megaphone, Send } from 'lucide-react'
import { api, type ActivityOut } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { Alert, Button, Input } from '../components/ui'
import { formatAgo } from '../lib/conflicts'

interface Props {
  activity: ActivityOut | null
  nowMs: number
  onPosted: () => void
}

const MAX_LENGTH = 280

export function ActivityPage({ activity, nowMs, onPosted }: Props) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The API publishes announcements oldest-first; the feed reads newest-first.
  const announcements = [...(activity?.announcements ?? [])].reverse()
  const locks = activity?.locks ?? []

  const post = async () => {
    const trimmed = message.trim()
    if (!trimmed) return
    setSending(true)
    setError(null)
    try {
      await api.postAnnouncement(trimmed)
      setMessage('')
      onPosted()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <PageHeader title="Activity" subtitle="Announcements and what the team is touching right now" />
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6 space-y-6">
        <section className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-5" aria-labelledby="announce-heading">
          <h2 id="announce-heading" className="text-sm font-semibold text-ui-text mb-3">Announce something</h2>
          <div className="flex items-end gap-2">
            <div className="flex-1 min-w-0">
              <Input
                placeholder="refactoring the auth module for the next hour…"
                value={message}
                maxLength={MAX_LENGTH}
                onChange={e => setMessage(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void post() } }}
                hint={`${message.length}/${MAX_LENGTH} — broadcast to everyone on the team`}
              />
            </div>
            <Button onClick={() => void post()} loading={sending} disabled={!message.trim()}
              icon={<Send className="w-3.5 h-3.5" />} className="mb-6">
              Post
            </Button>
          </div>
          {error && <div className="mt-3"><Alert variant="error" message={error} /></div>}
        </section>

        <section aria-labelledby="feed-heading" className="space-y-3">
          <h2 id="feed-heading" className="text-sm font-semibold text-ui-text">Recent announcements</h2>
          {announcements.length === 0 ? (
            <p className="text-sm text-ui-text-2">Nothing announced recently.</p>
          ) : (
            <ul className="space-y-2">
              {announcements.map((a, i) => (
                <li key={i} className="flex items-start gap-3 rounded-xl border border-ui-border bg-ui-surface shadow-card p-4">
                  <Megaphone className="w-4 h-4 text-ui-accent flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-ui-text break-words">{a.message}</p>
                    <p className="text-xs text-ui-text-2 mt-1">
                      <span className="font-medium text-ui-text">{a.member}</span> · {formatAgo(a.at, nowMs)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="claims-heading" className="space-y-3">
          <h2 id="claims-heading" className="text-sm font-semibold text-ui-text">Claim activity</h2>
          {locks.length === 0 ? (
            <p className="text-sm text-ui-text-2">No files are currently claimed by anyone.</p>
          ) : (
            <ul className="space-y-2">
              {[...locks]
                .sort((a, b) => Date.parse(b.locked_at ?? '') - Date.parse(a.locked_at ?? ''))
                .map(l => (
                  <li key={`${l.session_id}-${l.file_path}`}
                    className="flex items-center justify-between gap-3 rounded-xl border border-ui-border bg-ui-surface shadow-card px-4 py-3">
                    <div className="min-w-0">
                      <code className="font-mono text-xs text-ui-text break-all">{l.file_path}</code>
                      <p className="text-xs text-ui-text-2 mt-0.5">
                        <span className="font-medium text-ui-text">{l.member}</span> claimed {formatAgo(l.locked_at, nowMs)}
                      </p>
                    </div>
                    <StatusBadge label={l.intent} variant={l.intent === 'editing' ? 'info' : 'neutral'} />
                  </li>
                ))}
            </ul>
          )}
        </section>
      </div>
    </>
  )
}
