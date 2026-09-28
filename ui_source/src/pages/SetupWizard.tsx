import { useState } from 'react'
import { ArrowRight, KeyRound, Orbit, ShieldAlert, UserPlus, Users } from 'lucide-react'
import clsx from 'clsx'
import { api, mcpAddCommand, type MemberCreated, type OrgCreated } from '../api/client'
import { CopyField } from '../components/CopyField'
import { Alert, Button, Input, ThemeSwitcher } from '../components/ui'
import { useAppStore } from '../stores/appStore'

type Mode = 'create' | 'join'

interface Minted {
  slug: string
  displayName: string
  memberKey: string
  adminKey?: string
}

export function SetupWizard() {
  const setApiKey = useAppStore(s => s.setApiKey)
  const [mode, setMode] = useState<Mode>('create')
  const [teamName, setTeamName] = useState('')
  const [slug, setSlug] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [minted, setMinted] = useState<Minted | null>(null)

  const submit = async () => {
    setError(null)
    setBusy(true)
    try {
      let org: OrgCreated | null = null
      let targetSlug = slug.trim()

      if (mode === 'create') {
        org = await api.createOrg(teamName.trim(), targetSlug || undefined)
        targetSlug = org.slug
      }

      const member: MemberCreated = await api.joinOrg(targetSlug, displayName.trim())
      setMinted({
        slug: targetSlug,
        displayName: member.display_name,
        memberKey: member.api_key,
        adminKey: org?.admin_key,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const canSubmit = mode === 'create'
    ? teamName.trim().length > 0 && displayName.trim().length > 0
    : slug.trim().length > 0 && displayName.trim().length > 0

  return (
    <div className="h-screen overflow-y-auto bg-ui-bg">
      <div className="mx-auto max-w-2xl px-6 py-12">
        <header className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2.5">
            <Orbit className="w-6 h-6 text-ui-accent" aria-hidden="true" />
            <div>
              <h1 className="text-lg font-semibold text-ui-text leading-tight">Jupiter</h1>
              <p className="text-xs text-ui-text-2">File-claim coordination for Claude Code teams</p>
            </div>
          </div>
          <ThemeSwitcher compact />
        </header>

        {minted ? (
          <KeyHandover minted={minted} onContinue={() => setApiKey(minted.memberKey)} />
        ) : (
          <div className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-6 space-y-5">
            <div>
              <h2 className="text-base font-semibold text-ui-text mb-1">Get started</h2>
              <p className="text-sm text-ui-text-2">
                Create a team, or join one a teammate already made.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2" role="tablist" aria-label="Setup mode">
              <ModeButton
                active={mode === 'create'} onClick={() => setMode('create')}
                icon={<Users className="w-4 h-4" />} label="Create a team"
                hint="You are the first one here"
              />
              <ModeButton
                active={mode === 'join'} onClick={() => setMode('join')}
                icon={<UserPlus className="w-4 h-4" />} label="Join a team"
                hint="You have a team slug"
              />
            </div>

            <div className="space-y-4">
              {mode === 'create' ? (
                <>
                  <Input label="Team name" placeholder="Payments Squad" value={teamName}
                    onChange={e => setTeamName(e.target.value)} />
                  <Input label="Slug (optional)" placeholder="payments-squad" value={slug}
                    onChange={e => setSlug(e.target.value)}
                    hint="Leave blank and Jupiter derives one from the name." />
                </>
              ) : (
                <Input label="Team slug" placeholder="payments-squad" value={slug}
                  onChange={e => setSlug(e.target.value)}
                  hint="Ask a teammate for this — anyone who knows it can join." />
              )}
              <Input label="Your display name" placeholder="alice" value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && canSubmit) void submit() }}
                hint="How teammates will see you in the claims table." />
            </div>

            {error && <Alert variant="error" message={error} />}

            <Button onClick={() => void submit()} loading={busy} disabled={!canSubmit}
              icon={<ArrowRight className="w-3.5 h-3.5" />} size="lg" className="w-full">
              {mode === 'create' ? 'Create team and join' : 'Join team'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function ModeButton({ active, onClick, icon, label, hint }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string; hint: string
}) {
  return (
    <button onClick={onClick} role="tab" aria-selected={active}
      className={clsx('flex flex-col items-start gap-1 p-3 rounded-lg border text-left transition-colors',
        active
          ? 'border-ui-accent bg-ui-accent-muted text-ui-text'
          : 'border-ui-border bg-ui-surface text-ui-text-2 hover:bg-ui-hover hover:text-ui-text')}>
      <span className={clsx('inline-flex items-center gap-2 text-sm font-medium', active && 'text-ui-accent')}>
        {icon}{label}
      </span>
      <span className="text-xs text-ui-text-2">{hint}</span>
    </button>
  )
}

function KeyHandover({ minted, onContinue }: { minted: Minted; onContinue: () => void }) {
  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3 p-4 rounded-xl border border-amber-500/20 bg-ui-warning-bg text-amber-600 text-sm">
        <ShieldAlert className="w-5 h-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <p className="font-semibold mb-0.5">Save these keys now — they are shown once</p>
          <p className="opacity-90">
            Jupiter stores only a hash. There is no key rotation or recovery: if you lose a key, you join again
            under a new name.
          </p>
        </div>
      </div>

      <div className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-6 space-y-5">
        <div className="flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-ui-accent" aria-hidden="true" />
          <h2 className="text-base font-semibold text-ui-text">
            You are <span className="text-ui-accent">{minted.displayName}</span> in <span className="text-ui-accent">{minted.slug}</span>
          </h2>
        </div>

        <CopyField label="Your member key" value={minted.memberKey} />

        {minted.adminKey && (
          <CopyField
            label="Team admin key (you created this team)"
            value={minted.adminKey}
          />
        )}

        <div>
          <CopyField label="Connect Claude Code" value={mcpAddCommand(minted.memberKey)} multiline />
          <p className="text-xs text-ui-text-2 mt-2">
            Run this on every machine that should share this team's view. Each teammate joins separately to get
            their own key — the conflict rule compares people, not sessions.
          </p>
        </div>

        <Button onClick={onContinue} size="lg" className="w-full" icon={<ArrowRight className="w-3.5 h-3.5" />}>
          I've saved my key — open the dashboard
        </Button>
      </div>
    </div>
  )
}
