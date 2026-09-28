import { AlertTriangle, ArrowRight, CheckCircle2, Eye, ListChecks, Pencil, User } from 'lucide-react'
import type { LockOut } from '../api/client'
import {
  conflictingHolders,
  formatClock,
  formatRange,
  formatRemaining,
  intersectRange,
  remediationSteps,
  secondsRemaining,
} from '../lib/conflicts'
import { CodeSnippet } from './CodeSnippet'
import { ExpiryMeter } from './ExpiryMeter'
import { StatusBadge } from './StatusBadge'
import { Dialog } from './ui/Dialog'

interface Props {
  /** The claim being inspected, or null when the modal is closed. */
  lock: LockOut | null
  allLocks: LockOut[]
  ttl: number
  nowMs: number
  onClose: () => void
}

/**
 * What a conflict actually is, and what to do about it.
 *
 * Jupiter is advisory: the claim was recorded regardless, and nothing here
 * tells anyone they may not proceed. The wording throughout offers choices.
 */
export function ConflictModal({ lock, allLocks, ttl, nowMs, onClose }: Props) {
  const clashes = lock ? conflictingHolders(lock, allLocks) : []
  const conflicted = clashes.length > 0

  return (
    <Dialog
      open={lock !== null}
      onOpenChange={open => { if (!open) onClose() }}
      title={
        lock ? (
          <span className="flex flex-wrap items-center gap-2">
            {conflicted
              ? <StatusBadge label="conflict" variant="error" icon={<AlertTriangle className="h-3 w-3" />} />
              : <StatusBadge label="clear" variant="success" icon={<CheckCircle2 className="h-3 w-3" />} />}
            <code className="break-all font-mono text-sm">{lock.file_path}</code>
          </span>
        ) : ''
      }
      description={
        lock
          ? conflicted
            ? describeOverlap(lock, clashes)
            : `${lock.member} holds ${formatRange(lock.line_start, lock.line_end)}. Nobody else is on this file.`
          : undefined
      }
      footer={
        <p className="text-xs text-ui-text-2">
          Claims are advisory and expire on their own. Jupiter reports the situation — you decide what to do.
        </p>
      }
    >
      {lock && (
        <div className="space-y-5">
          <section aria-labelledby="claim-yours">
            <h3 id="claim-yours" className="mb-2 text-xs font-semibold uppercase tracking-wide text-ui-text-2">
              This claim
            </h3>
            <ClaimCard lock={lock} ttl={ttl} nowMs={nowMs} />
          </section>

          {conflicted && (
            <section aria-labelledby="claim-others">
              <h3 id="claim-others" className="mb-2 text-xs font-semibold uppercase tracking-wide text-ui-text-2">
                Overlapping {clashes.length === 1 ? 'claim' : 'claims'}
              </h3>
              <ul className="space-y-2">
                {clashes.map(other => {
                  const shared = intersectRange(lock, other)
                  return (
                    <li key={other.lock_id} className="space-y-2">
                      <ClaimCard lock={other} ttl={ttl} nowMs={nowMs} />
                      <div className="pl-1">
                        <p className="mb-1.5 flex items-center gap-1.5 text-xs text-ui-text-2">
                          <ArrowRight className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
                          {shared
                            ? `Lines ${shared.start}–${shared.end} are claimed by both of you.`
                            : 'One side claims the whole file, so the claims overlap everywhere.'}
                        </p>
                        <CodeSnippet
                          lockId={other.lock_id}
                          hasSnippet={other.has_snippet}
                          highlight={shared}
                        />
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>
          )}

          {conflicted && (
            <section aria-labelledby="what-to-do">
              <h3 id="what-to-do" className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ui-text-2">
                <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
                What you can do
              </h3>
              <ul className="space-y-1.5">
                {remediationSteps(lock, clashes, nowMs).map((step, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-ui-text">
                    <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-ui-accent" aria-hidden="true" />
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {!conflicted && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ui-text-2">Claimed lines</h3>
              <CodeSnippet lockId={lock.lock_id} hasSnippet={lock.has_snippet} highlight={null} />
            </section>
          )}
        </div>
      )}
    </Dialog>
  )
}

function describeOverlap(lock: LockOut, clashes: LockOut[]): string {
  const mine = formatRange(lock.line_start, lock.line_end)
  const first = clashes[0]
  const theirs = formatRange(first.line_start, first.line_end)
  if (clashes.length === 1) {
    return `${mine} overlaps ${first.member}'s ${theirs}. The claim was still recorded — Jupiter never blocks.`
  }
  return `${mine} overlaps claims held by ${clashes.map(c => c.member).join(', ')}. The claim was still recorded — Jupiter never blocks.`
}

function ClaimCard({ lock, ttl, nowMs }: { lock: LockOut; ttl: number; nowMs: number }) {
  return (
    <div className="rounded-lg border border-ui-border bg-ui-elevated p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium text-ui-text">
          <User className="h-3.5 w-3.5 text-ui-text-2" aria-hidden="true" />
          {lock.member}
        </span>
        {lock.intent === 'editing'
          ? <StatusBadge label="editing" variant="info" icon={<Pencil className="h-3 w-3" />} />
          : <StatusBadge label="reading" variant="neutral" icon={<Eye className="h-3 w-3" />} />}
        <span className="font-mono text-xs text-ui-text-2">{formatRange(lock.line_start, lock.line_end)}</span>
      </div>
      {lock.note && <p className="mb-2 text-sm italic text-ui-text-2">“{lock.note}”</p>}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <ExpiryMeter seconds={secondsRemaining(lock.expires_at, nowMs)} ttl={ttl} />
        <span className="text-xs text-ui-text-2">
          expires {formatClock(lock.expires_at)} ({formatRemaining(secondsRemaining(lock.expires_at, nowMs))})
        </span>
      </div>
    </div>
  )
}
