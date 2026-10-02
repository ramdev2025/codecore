import type { ActivityOut, HistoryLockOut, LockOut, SemanticOut } from '../api/client'
import {
  conflictingHolders,
  formatClock,
  formatPathWithRange,
  formatRange,
  formatRemaining,
  intersectRange,
  pastConflictingHolders,
  remediationSteps,
  secondsRemaining,
} from './conflicts'

export type LogSeverity = 'conflict' | 'advisory' | 'expiring' | 'expired' | 'ok' | 'info' | 'closed'

export interface LogEntry {
  id: string
  /** Sort key — ms since epoch. */
  at: number
  atIso: string | null
  severity: LogSeverity
  /** Short headline, e.g. "Conflict on src/auth/session.ts". */
  title: string
  /** Plain-language account of what happened. */
  what: string
  /** Concrete things the reader may choose to do. Empty when nothing is needed. */
  todo: string[]
  /** True for anything the model suggested, so it never reads as a hard fact. */
  aiSuggested?: boolean
  /** True for something that already finished — the claims behind it are gone. */
  past?: boolean
  /** The claim this entry is about, when there is one — lets the row open the modal. */
  lock?: LockOut
}

const EXPIRING_SOON_SECONDS = 60

/**
 * Build the activity log from the state we actually have.
 *
 * Two sources, deliberately: `activity` is a snapshot of the present — what
 * each live claim means for you right now — and `history` is the closed
 * claims behind it, fetched from `/api/history`. Without the second the log
 * empties itself as claims lapse, because a claim leaving `/api/activity` is
 * the only trace expiry leaves. Everything is framed as "what happened / what
 * you can do" because that is what the log is for.
 *
 * `me` is the signed-in member's display name when known, so entries can say
 * "you" instead of naming you in the third person.
 */
export function buildLog(
  activity: ActivityOut | null,
  semantic: SemanticOut | null,
  nowMs: number,
  me?: string | null,
  history: HistoryLockOut[] = [],
): LogEntry[] {
  if (!activity) return []
  const locks = activity.locks
  const entries: LogEntry[] = []
  const isMine = (l: LockOut) => !!me && l.member === me

  for (const lock of locks) {
    const at = Date.parse(lock.locked_at ?? '') || nowMs
    const label = formatPathWithRange(lock.file_path, lock.line_start, lock.line_end)
    const who = isMine(lock) ? 'You' : lock.member
    const holds = isMine(lock) ? 'hold' : 'holds'
    const clashes = conflictingHolders(lock, locks)
    const remaining = secondsRemaining(lock.expires_at, nowMs)

    if (clashes.length > 0) {
      const other = clashes[0]
      const shared = intersectRange(lock, other)
      const overlap = shared
        ? `lines ${shared.start}–${shared.end} overlap`
        : 'the claims overlap'
      entries.push({
        id: `conflict-${lock.lock_id}`,
        at,
        atIso: lock.locked_at,
        severity: 'conflict',
        title: `Conflict on ${lock.file_path}`,
        what:
          `${who} ${holds} ${formatRange(lock.line_start, lock.line_end)} of ${lock.file_path} (${lock.intent}), ` +
          `while ${clashes.map(c => `${c.member} holds ${formatRange(c.line_start, c.line_end)} (${c.intent})`).join(' and ')} — ${overlap}. ` +
          `The claim was still recorded: Jupiter reports, it never blocks.`,
        todo: isMine(lock) ? remediationSteps(lock, clashes, nowMs) : [],
        lock,
      })
      continue
    }

    if (remaining !== null && remaining <= 0) {
      entries.push({
        id: `expired-${lock.lock_id}`,
        at,
        atIso: lock.expires_at,
        severity: 'expired',
        title: `Claim lapsed on ${lock.file_path}`,
        what: `${who} ${holds} ${label}, but the claim lapsed at ${formatClock(lock.expires_at)}.`,
        todo: isMine(lock) ? ['Re-claim the file if you are still editing it.'] : [],
        lock,
      })
      continue
    }

    if (remaining !== null && remaining <= EXPIRING_SOON_SECONDS) {
      entries.push({
        id: `expiring-${lock.lock_id}`,
        at,
        atIso: lock.expires_at,
        severity: 'expiring',
        title: `Claim expiring on ${lock.file_path}`,
        what: `${who} ${holds} ${label}, expiring in ${formatRemaining(remaining)}.`,
        todo: isMine(lock)
          ? ['Claims refresh themselves while your agent is working — re-claim if it has stopped.']
          : [],
        lock,
      })
      continue
    }

    entries.push({
      id: `clear-${lock.lock_id}`,
      at,
      atIso: lock.locked_at,
      severity: 'ok',
      title: `Clear on ${lock.file_path}`,
      what: `${who} ${holds} ${label} until ${formatClock(lock.expires_at)}. Nobody else is on it.`,
      todo: [],
      lock,
    })
  }

  // Claims that have already closed. A row that is still live is skipped —
  // the loop above already spoke for it, against fresher data than a history
  // fetch has, and two rows for one claim would read as two events.
  const live = new Set(locks.map(l => l.lock_id))
  for (const claim of history) {
    if (claim.state === 'active' || live.has(claim.lock_id)) continue

    const at = Date.parse(claim.locked_at ?? '') || nowMs
    const who = isMine(claim) ? 'You' : claim.member
    const ran = `from ${formatClock(claim.locked_at)} to ${formatClock(claim.released_at)}`
    const ending = claim.state === 'expired'
      ? 'it lapsed without being refreshed'
      : 'it was released'
    const clashes = pastConflictingHolders(claim, history)

    if (clashes.length > 0) {
      const shared = intersectRange(claim, clashes[0])
      const overlap = shared
        ? `lines ${shared.start}–${shared.end} overlapped`
        : 'the claims overlapped'
      entries.push({
        id: `past-conflict-${claim.lock_id}`,
        at,
        atIso: claim.locked_at,
        severity: 'conflict',
        past: true,
        title: `Conflict on ${claim.file_path}`,
        what:
          `${who} held ${formatRange(claim.line_start, claim.line_end)} of ${claim.file_path} (${claim.intent}) ${ran}, ` +
          `while ${clashes.map(c => `${c.member} held ${formatRange(c.line_start, c.line_end)} (${c.intent})`).join(' and ')} — ${overlap}. ` +
          `Both claims were recorded — Jupiter reports, it never blocks — and ${ending}.`,
        todo: [],
      })
      continue
    }

    const label = formatPathWithRange(claim.file_path, claim.line_start, claim.line_end)
    entries.push({
      id: `closed-${claim.lock_id}`,
      at,
      atIso: claim.locked_at,
      severity: 'closed',
      past: true,
      title: claim.state === 'expired'
        ? `Claim lapsed on ${claim.file_path}`
        : `Claim released on ${claim.file_path}`,
      what:
        `${who} held ${label} (${claim.intent}) ${ran}` +
        `${claim.note ? ` — ${claim.note}` : ''}. Nobody else was on it.`,
      todo: [],
    })
  }

  if (semantic?.status === 'ready') {
    for (const [i, o] of semantic.overlaps.entries()) {
      entries.push({
        id: `advisory-${i}-${o.paths.join('|')}`,
        at: Date.parse(semantic.analyzed_at ?? '') || nowMs,
        atIso: semantic.analyzed_at,
        severity: 'advisory',
        title: 'Possibly related work on different files',
        what: `${o.paths.join(' + ')} — held by ${o.members.join(', ')}. ${o.reason}`,
        todo: [
          'Nothing is blocked. Check in with each other if both changes are still in flight.',
        ],
        aiSuggested: true,
      })
    }
  }

  for (const [i, a] of activity.announcements.entries()) {
    entries.push({
      id: `announcement-${i}-${a.at ?? ''}`,
      at: Date.parse(a.at ?? '') || nowMs,
      atIso: a.at,
      severity: 'info',
      title: `${a.member} announced`,
      what: a.message,
      todo: [],
    })
  }

  return entries.sort((x, y) => y.at - x.at)
}

export function countBySeverity(entries: LogEntry[]): Record<LogSeverity, number> {
  const out: Record<LogSeverity, number> = {
    conflict: 0, advisory: 0, expiring: 0, expired: 0, ok: 0, info: 0, closed: 0,
  }
  for (const e of entries) out[e.severity] += 1
  return out
}
