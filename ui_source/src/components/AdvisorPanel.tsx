import { Lightbulb, Loader2, PowerOff, Sparkles, TriangleAlert } from 'lucide-react'
import type { SemanticOut } from '../api/client'
import { StatusBadge } from './StatusBadge'

const confidenceVariant = { high: 'purple', medium: 'info', low: 'neutral' } as const

/**
 * The advisor's findings: DIFFERENT files, held by DIFFERENT people, whose work
 * is likely to collide even though the paths differ.
 *
 * These are advisory and AI-suggested, and are styled to read that way — they
 * must never be mistaken for the deterministic same-path conflicts shown in
 * the claims table.
 */
export function AdvisorPanel({ semantic }: { semantic: SemanticOut | null }) {
  return (
    <section className="bg-ui-surface rounded-xl border border-ui-border shadow-card p-5" aria-labelledby="advisor-heading">
      <div className="flex items-start justify-between gap-3 mb-1">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-purple-400 flex-shrink-0" aria-hidden="true" />
          <h2 id="advisor-heading" className="text-sm font-semibold text-ui-text">Advisor</h2>
        </div>
        <StatusBadge label="AI-suggested · advisory" variant="purple" icon={<Lightbulb className="w-3 h-3" />} />
      </div>
      <p className="text-xs text-ui-text-2 mb-4">
        Possibly-related work on <em>different</em> files. Never changes a claim's clear/blocked status.
      </p>
      <AdvisorBody semantic={semantic} />
    </section>
  )
}

function AdvisorBody({ semantic }: { semantic: SemanticOut | null }) {
  if (!semantic) {
    return (
      <p className="text-sm text-ui-text-2 flex items-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin text-ui-accent" aria-hidden="true" />
        Loading advisor findings…
      </p>
    )
  }

  if (semantic.status === 'disabled') {
    return (
      <p className="text-sm text-ui-text-2 flex items-start gap-2">
        <PowerOff className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
        <span>
          Overlap detection is off.
          {semantic.llm?.reason ? ` ${semantic.llm.reason}` : ' Set JUPITER_LLM_API_KEY to enable it.'}
        </span>
      </p>
    )
  }

  if (semantic.status === 'pending') {
    return (
      <p className="text-sm text-ui-text-2 flex items-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin text-ui-accent" aria-hidden="true" />
        Analysing the current claim set…
      </p>
    )
  }

  if (semantic.status === 'error') {
    return (
      <p className="text-sm text-ui-error flex items-start gap-2">
        <TriangleAlert className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
        <span>Advisor unavailable{semantic.error ? `: ${semantic.error}` : ''}. Hard conflicts are unaffected.</span>
      </p>
    )
  }

  if (semantic.overlaps.length === 0) {
    return (
      <p className="text-sm text-ui-text-2">
        No related work detected. An empty result is the expected answer most of the time.
      </p>
    )
  }

  return (
    <ul className="space-y-3">
      {semantic.overlaps.map((o, i) => (
        <li key={i} className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3">
          <div className="flex items-start justify-between gap-3 mb-1.5">
            <div className="flex flex-wrap gap-1.5 min-w-0">
              {o.paths.map(p => (
                <code key={p} className="font-mono text-xs text-ui-text bg-ui-elevated border border-ui-border rounded px-1.5 py-0.5 break-all">{p}</code>
              ))}
            </div>
            <StatusBadge
              label={`${o.confidence} confidence`}
              variant={confidenceVariant[o.confidence] ?? 'neutral'}
              icon={<Sparkles className="w-3 h-3" />}
            />
          </div>
          <p className="text-xs text-ui-text-2">
            <span className="font-medium text-ui-text">{o.members.join(', ')}</span> — {o.reason}
          </p>
        </li>
      ))}
    </ul>
  )
}
