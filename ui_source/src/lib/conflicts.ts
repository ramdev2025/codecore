import type { HistoryLockOut, LockOut } from '../api/client'

/**
 * The conflict rule, mirrored client-side for display only.
 *
 * A claim conflicts when a DIFFERENT member holds the SAME normalized path,
 * at least one side is editing, AND their line ranges overlap. Two readers
 * coexist, and a member's own second session never conflicts with their
 * first — the rule compares people, not sessions.
 *
 * The server is authoritative; this only decides which badge to render and
 * which rows open the conflict modal.
 */

/** A null range means the whole file, which overlaps every range on that path. */
export function rangesOverlap(
  aStart: number | null, aEnd: number | null,
  bStart: number | null, bEnd: number | null,
): boolean {
  if (aStart === null || bStart === null) return true
  const aTop = aEnd ?? aStart
  const bTop = bEnd ?? bStart
  return aStart <= bTop && bStart <= aTop
}

export function conflictingHolders(lock: LockOut, all: LockOut[]): LockOut[] {
  return all.filter(other =>
    other.file_path === lock.file_path &&
    other.member_id !== lock.member_id &&
    (other.intent === 'editing' || lock.intent === 'editing') &&
    rangesOverlap(lock.line_start, lock.line_end, other.line_start, other.line_end)
  )
}

export function hasConflict(lock: LockOut, all: LockOut[]): boolean {
  return conflictingHolders(lock, all).length > 0
}

/**
 * Did two claims' lifetimes actually overlap?
 *
 * `conflictingHolders` can skip this because everything in the activity
 * payload is live simultaneously by construction. History is not: two people
 * claiming the same lines an hour apart never collided, and saying they did
 * would be worse than showing nothing. An unreleased claim runs to now, so
 * its end is open.
 */
export function livesOverlapped(a: HistoryLockOut, b: HistoryLockOut): boolean {
  const aStart = Date.parse(a.locked_at ?? '')
  const bStart = Date.parse(b.locked_at ?? '')
  if (Number.isNaN(aStart) || Number.isNaN(bStart)) return false
  const aEnd = a.released_at ? Date.parse(a.released_at) : Infinity
  const bEnd = b.released_at ? Date.parse(b.released_at) : Infinity
  return aStart <= bEnd && bStart <= aEnd
}

/** The same rule as `conflictingHolders`, plus the claims having coexisted. */
export function pastConflictingHolders(
  lock: HistoryLockOut, all: HistoryLockOut[],
): HistoryLockOut[] {
  return all.filter(other =>
    other.file_path === lock.file_path &&
    other.member_id !== lock.member_id &&
    (other.intent === 'editing' || lock.intent === 'editing') &&
    rangesOverlap(lock.line_start, lock.line_end, other.line_start, other.line_end) &&
    livesOverlapped(lock, other)
  )
}

/** "lines 40–80", "line 40", or "whole file". */
export function formatRange(start: number | null, end: number | null): string {
  if (start === null) return 'whole file'
  const top = end ?? start
  return top === start ? `line ${start}` : `lines ${start}–${top}`
}

/** `path:40-80`, or just `path` for a whole-file claim. */
export function formatPathWithRange(path: string, start: number | null, end: number | null): string {
  if (start === null) return path
  const top = end ?? start
  return top === start ? `${path}:${start}` : `${path}:${start}-${top}`
}

/**
 * The lines two claims actually share, or null when either is a whole-file
 * claim (in which case the overlap is "everything", not a range worth naming).
 */
export function intersectRange(a: LockOut, b: LockOut): { start: number; end: number } | null {
  if (a.line_start === null || b.line_start === null) return null
  const start = Math.max(a.line_start, b.line_start)
  const end = Math.min(a.line_end ?? a.line_start, b.line_end ?? b.line_start)
  return start <= end ? { start, end } : null
}

/** Seconds until a claim lapses, against server-corrected time. Null if unknown. */
export function secondsRemaining(expiresAt: string | null, nowMs: number): number | null {
  if (!expiresAt) return null
  const t = Date.parse(expiresAt)
  if (Number.isNaN(t)) return null
  return Math.round((t - nowMs) / 1000)
}

export function formatRemaining(seconds: number | null): string {
  if (seconds === null) return 'unknown'
  if (seconds <= 0) return 'expired'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

/** Short relative age, e.g. "3m ago". */
export function formatAgo(iso: string | null, nowMs: number): string {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return '—'
  const secs = Math.max(0, Math.round((nowMs - t) / 1000))
  if (secs < 60) return `${secs}s ago`
  const m = Math.floor(secs / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

/** Wall-clock time of day, for "until 14:32". */
export function formatClock(iso: string | null): string {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return '—'
  return new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * Concrete next steps for a conflict. Jupiter is advisory — every line here
 * is something the reader may choose to do, never a prohibition.
 */
export function remediationSteps(mine: LockOut, others: LockOut[], nowMs: number): string[] {
  const steps: string[] = []
  const names = Array.from(new Set(others.map(o => o.member)))
  steps.push(
    names.length === 1
      ? `Talk to ${names[0]} before editing — they may already be mid-change.`
      : `Talk to ${names.join(' and ')} before editing — they may already be mid-change.`,
  )

  const soonest = others
    .map(o => secondsRemaining(o.expires_at, nowMs))
    .filter((s): s is number => s !== null && s > 0)
    .sort((a, b) => a - b)[0]
  if (soonest !== undefined) {
    steps.push(`Or wait ~${formatRemaining(soonest)} for their claim to lapse, then re-claim.`)
  }

  const ranged = others.filter(o => o.line_start !== null)
  if (mine.line_start !== null && ranged.length > 0) {
    steps.push('Or claim a line range that does not overlap theirs.')
  } else if (mine.line_start === null && ranged.length > 0) {
    steps.push('Or claim just the lines you need instead of the whole file — a narrower range may not overlap.')
  }

  steps.push('Or pick a different file and come back to this one later.')
  return steps
}
