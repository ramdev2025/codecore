import { useEffect, useState } from 'react'
import { CheckCircle, LogOut, PowerOff, Terminal, XCircle } from 'lucide-react'
import { api, mcpAddCommand, type ActivityOut, type SemanticOut } from '../api/client'
import { CopyField } from '../components/CopyField'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { Button } from '../components/ui'
import { useAppStore } from '../stores/appStore'

interface Props {
  activity: ActivityOut | null
  semantic: SemanticOut | null
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-ui-border last:border-0">
      <span className="text-sm text-ui-text-2">{label}</span>
      <span className="text-sm text-ui-text text-right min-w-0">{children}</span>
    </div>
  )
}

export function SettingsPage({ activity, semantic }: Props) {
  const apiKey = useAppStore(s => s.apiKey)
  const signOut = useAppStore(s => s.signOut)
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    void api.health().then(h => setVersion(h.version ?? null)).catch(() => setVersion(null))
  }, [])

  const llm = semantic?.llm
  const semanticOn = semantic ? semantic.status !== 'disabled' : false

  return (
    <>
      <PageHeader title="Settings" subtitle="Configuration for this deployment" />
      {/* The scroll container stays full width so the scrollbar sits at the
          real right edge; the grid uses the space on large screens instead of
          leaving it empty. */}
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        <div className="grid gap-6 xl:grid-cols-2 items-start">
        <section className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-5" aria-labelledby="deployment-heading">
          <h2 id="deployment-heading" className="text-sm font-semibold text-ui-text mb-2">Deployment</h2>
          <Row label="Team slug">{activity?.slug ?? '—'}</Row>
          <Row label="Claim TTL">
            {activity ? `${activity.lock_ttl_seconds}s from last refresh` : '—'}
          </Row>
          <Row label="Session TTL">
            {activity ? `${Math.max(activity.lock_ttl_seconds * 2, 600)}s` : '—'}
          </Row>
          <Row label="Server version">{version ?? '—'}</Row>
          <Row label="Origin">{window.location.origin}</Row>
        </section>

        <section className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-5" aria-labelledby="semantic-heading">
          <h2 id="semantic-heading" className="text-sm font-semibold text-ui-text mb-2">Overlap detection</h2>
          <Row label="Status">
            {semanticOn
              ? <StatusBadge label="enabled" variant="success" icon={<CheckCircle className="w-3 h-3" />} />
              : <StatusBadge label="disabled" variant="neutral" icon={<PowerOff className="w-3 h-3" />} />}
          </Row>
          <Row label="Model">{semantic?.model ?? llm?.model ?? '—'}</Row>
          <Row label="Gateway">{llm?.base_url ?? '—'}</Row>
          {!semanticOn && llm?.reason && <Row label="Reason">{llm.reason}</Row>}
          {semantic?.status === 'error' && (
            <Row label="Last error">
              <span className="text-ui-error inline-flex items-center gap-1">
                <XCircle className="w-3.5 h-3.5" aria-hidden="true" />{semantic.error}
              </span>
            </Row>
          )}
          <p className="text-xs text-ui-text-2 mt-3">
            Only paths, intents, holder names and notes are ever sent to the gateway. No file contents leave your network.
          </p>
        </section>

        {/* Spans both columns: the connect command is long and reads badly wrapped. */}
        <section className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-5 xl:col-span-2" aria-labelledby="mcp-heading">
          <div className="flex items-center gap-2 mb-1">
            <Terminal className="w-4 h-4 text-ui-accent" aria-hidden="true" />
            <h2 id="mcp-heading" className="text-sm font-semibold text-ui-text">Connect Claude Code</h2>
          </div>
          <p className="text-xs text-ui-text-2 mb-4">
            Run this on any machine to point a Claude Code instance at this Jupiter deployment.
          </p>
          {apiKey
            ? <CopyField value={mcpAddCommand(apiKey)} multiline />
            : <p className="text-sm text-ui-text-2">No API key stored on this browser.</p>}
        </section>

        <section className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-5" aria-labelledby="session-heading">
          <h2 id="session-heading" className="text-sm font-semibold text-ui-text mb-1">This browser</h2>
          <p className="text-xs text-ui-text-2 mb-4">
            Your member key is stored locally. Signing out clears it and returns you to setup — it does not revoke the key.
          </p>
          <Button variant="secondary" icon={<LogOut className="w-3.5 h-3.5" />} onClick={signOut}>
            Sign out of this browser
          </Button>
        </section>
        </div>
      </div>
    </>
  )
}
