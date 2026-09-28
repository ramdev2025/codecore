import type { ActivityOut, LockOut, SemanticOut } from '../api/client'
import {
  conflictingHolders,
  formatClock,
  formatPathWithRange,
  formatRange,
  formatRemaining,
  intersectRange,
  remediationSteps,
  secondsRemaining,
} from './conflicts'

export type LogSeverity = 'conflict' | 'advisory' | 'expiring' | 'expired' | 'ok' | 'info'

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
  /** The claim this entry is about, when there is one — lets the row open the modal. */
  lock?: LockOut
}

const EXPIRING_SOON_SECONDS = 60

/**
 * Build the activity log from the state we actually have.
 *
 * Jupiter stores current claims, not an event history, so this is a reading of
 * the present rather than a replay of the past: what each live claim means for
 * you right now, plus announcements and advisor findings. Everything is framed
 * as "what happened / what you can do" because that is what the log is for.
 *
 * `me` is the signed-in member's display name when known, so entries can say
 * "you" instead of naming you in the third person.
 */
export function buildLog(
  activity: ActivityOut | null,
  semantic: SemanticOut | null,
  nowMs: number,
  me?: string | null,
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
    conflict: 0, advisory: 0, expiring: 0, expired: 0, ok: 0, info: 0,
  }
  for (const e of entries) out[e.severity] += 1
  return out
}
