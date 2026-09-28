"""File claims: acquire, release, and the pure conflict rule.

Ported from jupiter-code's lib/locks.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .auth import Principal
from .config import ANNOUNCEMENT_MAX_LENGTH, SNIPPET_MAX_LENGTH, lock_ttl, store_snippets
from .errors import not_found, unprocessable
from .paths import normalize_path
from .sessions_repo import _to_session_row, assert_owned, _SELECT_SESSION_SQL
from .sweep import sweep
from .time_util import expires_at, isoformat, now as utcnow

MAX_LINE = 2_000_000

ACTIVE_LOCKS_SQL = """
    SELECT l.id,
           l.file_path,
           l.intent,
           l.session_id,
           l.locked_at,
           l.refreshed_at,
           l.note,
           s.member_id,
           s.working_dir,
           m.display_name,
           l.line_start,
           l.line_end,
           EXISTS (SELECT 1 FROM claim_snippets cs WHERE cs.lock_id = l.id)
      FROM file_locks l
      JOIN sessions s ON s.id = l.session_id
      JOIN members  m ON m.id = s.member_id
     WHERE l.org_id = %s
       AND l.released_at IS NULL
     ORDER BY l.locked_at, l.id
"""


@dataclass(frozen=True)
class ActiveLock:
    id: int
    file_path: str
    intent: str
    session_id: int
    member_id: int
    member: str
    working_dir: str | None
    locked_at: datetime | None
    refreshed_at: datetime | None
    note: str | None
    line_start: int | None = None
    line_end: int | None = None
    has_snippet: bool = False


def _to_active_lock(row) -> ActiveLock:
    return ActiveLock(
        id=int(row[0]),
        file_path=row[1],
        intent=row[2] if row[2] == "reading" else "editing",
        session_id=int(row[3]),
        locked_at=row[4],
        refreshed_at=row[5],
        note=row[6],
        member_id=int(row[7]),
        working_dir=row[8],
        member=row[9] or "",
        line_start=int(row[10]) if len(row) > 10 and row[10] is not None else None,
        line_end=int(row[11]) if len(row) > 11 and row[11] is not None else None,
        has_snippet=bool(row[12]) if len(row) > 12 else False,
    )


async def active_locks_for(aconn, org_id: int) -> list[ActiveLock]:
    """Every claim currently held across an org, swept first."""
    now = utcnow()
    async with aconn.transaction():
        await sweep(aconn, org_id, now, lock_ttl())
        async with aconn.cursor() as cur:
            await cur.execute(ACTIVE_LOCKS_SQL, (org_id,))
            rows = await cur.fetchall()
    return [_to_active_lock(row) for row in rows]


@dataclass(frozen=True)
class LockOut:
    lock_id: int
    file_path: str
    intent: str
    member: str
    member_id: int
    session_id: int
    working_dir: str | None
    locked_at: str | None
    expires_at: str | None
    note: str | None
    line_start: int | None
    line_end: int | None
    has_snippet: bool


def lock_out(lock: ActiveLock, ttl: int) -> LockOut:
    return LockOut(
        lock_id=lock.id,
        file_path=lock.file_path,
        intent=lock.intent,
        member=lock.member,
        member_id=lock.member_id,
        session_id=lock.session_id,
        working_dir=lock.working_dir,
        locked_at=isoformat(lock.locked_at),
        expires_at=isoformat(expires_at(lock.refreshed_at, ttl)) if lock.refreshed_at else None,
        note=lock.note,
        line_start=lock.line_start,
        line_end=lock.line_end,
        has_snippet=lock.has_snippet,
    )


def describe_range(line_start: int | None, line_end: int | None) -> str:
    """`:40-80`, `:40`, or empty for a whole-file claim.

    Empty for whole-file is deliberate: a claim with no range renders exactly
    as it did before ranges existed, so the strings teammates already read
    stay byte-identical in the common case.
    """
    if line_start is None:
        return ""
    if line_end is None or line_end == line_start:
        return f":{line_start}"
    return f":{line_start}-{line_end}"


def describe_claim(file_path: str, line_start: int | None, line_end: int | None) -> str:
    return f"{file_path}{describe_range(line_start, line_end)}"


def normalize_lines(line_start, line_end) -> tuple[int | None, int | None]:
    """Validate a claimed line range.

    Both absent means a whole-file claim, which is what every claim was before
    ranges existed. A start on its own claims that single line.
    """
    if line_start is None and line_end is None:
        return None, None

    def as_line(value, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            try:
                value = int(str(value).strip())
            except (TypeError, ValueError):
                raise unprocessable(f"{field} must be an integer") from None
        if value < 1:
            raise unprocessable(f"{field} must be 1 or greater")
        if value > MAX_LINE:
            raise unprocessable(f"{field} must be {MAX_LINE} or less")
        return value

    if line_start is None:
        raise unprocessable("line_start is required when line_end is given")
    start = as_line(line_start, "line_start")
    end = start if line_end is None else as_line(line_end, "line_end")
    if end < start:
        raise unprocessable("line_end must be greater than or equal to line_start")
    return start, end


def ranges_overlap(
    a_start: int | None, a_end: int | None, b_start: int | None, b_end: int | None
) -> bool:
    """Do two claimed ranges touch?

    A whole-file claim (NULL/NULL) covers the file, so it overlaps every range
    on that path - which is what keeps the pre-range behaviour intact: when
    neither side names a range this is always True and the rule reduces to the
    original same-path test.
    """
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return True
    return a_start <= b_end and b_start <= a_end


def conflicts_for(
    active: list[ActiveLock],
    file_path: str,
    member_id: int,
    intent: str,
    line_start: int | None = None,
    line_end: int | None = None,
) -> list[ActiveLock]:
    """Who else is on this file, and does it matter?

    * compares members, not sessions - your own second Claude Code instance
      never blocks your first;
    * at least one side must be 'editing' - two readers coexist happily;
    * the claimed line ranges must overlap - two people editing far-apart
      regions of one file no longer block each other. A claim with no range
      covers the whole file, so omitting one restores the original behaviour;
    * paths are compared after normalisation by the caller.
    """
    return [
        lock
        for lock in active
        if lock.file_path == file_path
        and lock.member_id != member_id
        and (lock.intent == "editing" or intent == "editing")
        and ranges_overlap(line_start, line_end, lock.line_start, lock.line_end)
    ]


def own_claim(active: list[ActiveLock], file_path: str, session_id: int) -> ActiveLock | None:
    for lock in active:
        if lock.file_path == file_path and lock.session_id == session_id:
            return lock
    return None


def clear_message(
    file_path: str,
    intent: str,
    expires: str | None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    return f"clear - you hold {describe_claim(file_path, line_start, line_end)} ({intent}) until {expires}"


def blocked_message(
    conflicts: list[ActiveLock],
    file_path: str,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    holders = ", ".join(
        f"{c.member} ({c.intent}{describe_range(c.line_start, c.line_end)})" for c in conflicts
    )
    target = describe_claim(file_path, line_start, line_end)
    return f"⚠ blocked by {holders} on {target} - coordinate before editing, or pick another file"


def released_message(file_path: str) -> str:
    return f"released {file_path}"


def not_held_message(file_path: str) -> str:
    return f"no active lock held on {file_path} (already released or expired)"


@dataclass(frozen=True)
class ResolvedNote:
    provided: bool
    value: str | None


def resolve_note(note: str | None) -> ResolvedNote:
    """An omitted (or None) note keeps whatever is there; an explicitly empty
    one clears it."""
    if note is None:
        return ResolvedNote(provided=False, value=None)
    trimmed = note.strip()[:ANNOUNCEMENT_MAX_LENGTH]
    return ResolvedNote(provided=True, value=trimmed or None)


@dataclass(frozen=True)
class RelatedOut:
    paths: list[str]
    members: list[str]
    reason: str
    confidence: str


@dataclass(frozen=True)
class LockResponse:
    status: str  # "clear" | "blocked"
    file_path: str
    intent: str
    expires_at: str | None
    conflicts: list[LockOut]
    message: str
    related: list[RelatedOut]
    line_start: int | None = None
    line_end: int | None = None


def resolve_snippet(code: str | None) -> str | None:
    """The snippet to persist, or None.

    Returns None unless storage is explicitly enabled, so a caller sending
    `code` to a deployment that has not opted in has it dropped rather than
    silently stored.
    """
    if code is None or not store_snippets():
        return None
    trimmed = code[:SNIPPET_MAX_LENGTH]
    return trimmed or None


async def acquire_lock(
    aconn,
    principal: Principal,
    session_id: int,
    file_path: str,
    intent: str,
    note: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    code: str | None = None,
) -> LockResponse:
    """Claim a file, or a range of lines within it.

    Claims are advisory: the claim is always recorded, even when blocked.
    """
    from .semantic import claims_for_analysis, peek_cached_overlaps, related_for

    ttl = lock_ttl()
    now = utcnow()
    file_path = normalize_path(file_path)
    line_start, line_end = normalize_lines(line_start, line_end)
    snippet = resolve_snippet(code)

    async with aconn.transaction():
        async with aconn.cursor() as cur:
            await cur.execute(
                """
                UPDATE sessions
                   SET last_seen = %s
                 WHERE id = %s AND member_id = %s AND ended_at IS NULL
                """,
                (now, session_id, principal.member_id),
            )
            await cur.execute(_SELECT_SESSION_SQL, (session_id,))
            session_row = await cur.fetchone()

        await sweep(aconn, principal.org_id, now, ttl)

        async with aconn.cursor() as cur:
            await cur.execute(ACTIVE_LOCKS_SQL, (principal.org_id,))
            active_rows = await cur.fetchall()

        session = assert_owned(_to_session_row(session_row), session_id, principal)
        active = [_to_active_lock(row) for row in active_rows]

        mine = own_claim(active, file_path, session.id)
        conflicts = conflicts_for(
            active, file_path, principal.member_id, intent, line_start, line_end
        )
        resolved_note = resolve_note(note)

        async with aconn.cursor() as cur:
            if mine is not None:
                # An omitted range keeps whatever is there, mirroring how an
                # omitted note behaves - re-claiming to refresh a TTL must not
                # silently widen a narrow claim to the whole file.
                await cur.execute(
                    """
                    UPDATE file_locks
                       SET intent = %s,
                           refreshed_at = %s,
                           note = CASE WHEN %s THEN %s ELSE note END,
                           line_start = CASE WHEN %s THEN %s ELSE line_start END,
                           line_end   = CASE WHEN %s THEN %s ELSE line_end   END
                     WHERE id = %s
                    RETURNING id, refreshed_at
                    """,
                    (
                        intent,
                        now,
                        resolved_note.provided,
                        resolved_note.value,
                        line_start is not None,
                        line_start,
                        line_start is not None,
                        line_end,
                        mine.id,
                    ),
                )
            else:
                await cur.execute(
                    """
                    INSERT INTO file_locks
                        (session_id, org_id, file_path, intent, locked_at, refreshed_at,
                         note, line_start, line_end)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, refreshed_at
                    """,
                    (
                        session.id,
                        principal.org_id,
                        file_path,
                        intent,
                        now,
                        now,
                        resolved_note.value,
                        line_start,
                        line_end,
                    ),
                )
            refreshed_row = await cur.fetchone()
            lock_id = int(refreshed_row[0]) if refreshed_row else None

            if snippet is not None and lock_id is not None:
                await cur.execute(
                    """
                    INSERT INTO claim_snippets (lock_id, org_id, code, captured_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (lock_id) DO UPDATE
                       SET code = EXCLUDED.code, captured_at = EXCLUDED.captured_at
                    """,
                    (lock_id, principal.org_id, snippet, now),
                )

    refreshed_at_value = refreshed_row[1] if refreshed_row and refreshed_row[1] else now
    expires = isoformat(expires_at(refreshed_at_value, ttl))

    related: list[RelatedOut] = []
    try:
        cached = await peek_cached_overlaps(aconn, principal.org_id, claims_for_analysis(active))
        related = related_for(cached, file_path, principal.display_name)
    except Exception:
        related = []

    if conflicts:
        return LockResponse(
            status="blocked",
            file_path=file_path,
            intent=intent,
            expires_at=expires,
            conflicts=[lock_out(c, ttl) for c in conflicts],
            message=blocked_message(conflicts, file_path, line_start, line_end),
            related=related,
            line_start=line_start,
            line_end=line_end,
        )

    return LockResponse(
        status="clear",
        file_path=file_path,
        intent=intent,
        expires_at=expires,
        conflicts=[],
        message=clear_message(file_path, intent, expires, line_start, line_end),
        related=related,
        line_start=line_start,
        line_end=line_end,
    )


@dataclass(frozen=True)
class SnippetOut:
    lock_id: int
    file_path: str
    line_start: int | None
    line_end: int | None
    code: str
    captured_at: str | None


async def snippet_for(aconn, org_id: int, lock_id: int) -> SnippetOut:
    """The stored source for one claim, scoped to the caller's own org.

    404s rather than 403s when the claim belongs to another org, so the API
    never confirms that someone else's claim id exists.
    """
    async with aconn.cursor() as cur:
        await cur.execute(
            """
            SELECT l.id, l.file_path, l.line_start, l.line_end, cs.code, cs.captured_at
              FROM claim_snippets cs
              JOIN file_locks l ON l.id = cs.lock_id
             WHERE cs.lock_id = %s AND cs.org_id = %s
            """,
            (lock_id, org_id),
        )
        row = await cur.fetchone()

    if row is None:
        raise not_found("no snippet stored for this claim")

    return SnippetOut(
        lock_id=int(row[0]),
        file_path=row[1],
        line_start=int(row[2]) if row[2] is not None else None,
        line_end=int(row[3]) if row[3] is not None else None,
        code=row[4],
        captured_at=isoformat(row[5]),
    )


@dataclass(frozen=True)
class UnlockResponse:
    file_path: str
    released: int
    message: str


async def release_lock(aconn, principal: Principal, session_id: int, file_path: str) -> UnlockResponse:
    """Release a claim. Scoped to the caller's own session."""
    now = utcnow()
    file_path = normalize_path(file_path)

    async with aconn.transaction():
        async with aconn.cursor() as cur:
            await cur.execute(_SELECT_SESSION_SQL, (session_id,))
            session_row = await cur.fetchone()

            await cur.execute(
                """
                UPDATE file_locks
                   SET released_at = %s
                 WHERE session_id = %s
                   AND file_path = %s
                   AND released_at IS NULL
                   AND EXISTS (
                     SELECT 1 FROM sessions s
                      WHERE s.id = file_locks.session_id AND s.member_id = %s
                   )
                RETURNING id
                """,
                (now, session_id, file_path, principal.member_id),
            )
            released_rows = await cur.fetchall()

            await cur.execute(
                """
                UPDATE sessions
                   SET last_seen = %s
                 WHERE id = %s AND member_id = %s AND ended_at IS NULL
                """,
                (now, session_id, principal.member_id),
            )

    assert_owned(_to_session_row(session_row), session_id, principal)

    released = len(released_rows)
    return UnlockResponse(
        file_path=file_path,
        released=released,
        message=not_held_message(file_path) if released == 0 else released_message(file_path),
    )
