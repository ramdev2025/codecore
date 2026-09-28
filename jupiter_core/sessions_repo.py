"""Sessions: one running Claude Code instance (or one AgentFlow chat turn).

Ported from jupiter-code's lib/sessions.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .auth import Principal
from .config import lock_ttl
from .errors import conflict, not_found
from .sweep import sweep
from .time_util import isoformat, now as utcnow

_SELECT_SESSION_SQL = """
    SELECT id, member_id, org_id, working_dir, started_at, last_seen, ended_at
      FROM sessions
     WHERE id = %s
"""


@dataclass(frozen=True)
class SessionRow:
    id: int
    member_id: int
    org_id: int
    working_dir: str | None
    started_at: datetime | None
    last_seen: datetime | None
    ended_at: datetime | None


def _to_session_row(row) -> SessionRow | None:
    if row is None:
        return None
    return SessionRow(
        id=int(row[0]),
        member_id=int(row[1]),
        org_id=int(row[2]),
        working_dir=row[3],
        started_at=row[4],
        last_seen=row[5],
        ended_at=row[6],
    )


def assert_owned(session: SessionRow | None, session_id: int, principal: Principal) -> SessionRow:
    """The ownership check.

    Someone else's session is a 404, not a 403 - deliberately, so the API
    never confirms a session id exists to a caller who does not own it. An
    already-ended session is a 409 telling the client to check in again.
    """
    if session is None or session.member_id != principal.member_id:
        raise not_found(f"no such session: {session_id}")
    if session.ended_at is not None:
        raise conflict(f"session {session_id} has ended; check in again to get a new one")
    return session


@dataclass(frozen=True)
class SessionOut:
    session_id: int
    member_id: int
    display_name: str
    slug: str
    working_dir: str | None
    started_at: str | None
    last_seen: str | None


def _session_out(session: SessionRow, principal: Principal, last_seen: datetime) -> SessionOut:
    return SessionOut(
        session_id=session.id,
        member_id=session.member_id,
        display_name=principal.display_name or "",
        slug=principal.slug,
        working_dir=session.working_dir,
        started_at=isoformat(session.started_at),
        last_seen=isoformat(last_seen),
    )


async def create_session(aconn, principal: Principal, working_dir: str | None) -> SessionOut:
    now = utcnow()
    directory = (working_dir or "").strip() or None

    async with aconn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO sessions (member_id, org_id, working_dir, started_at, last_seen)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, member_id, org_id, working_dir, started_at, last_seen, ended_at
            """,
            (principal.member_id, principal.org_id, directory, now, now),
        )
        row = await cur.fetchone()

    session = _to_session_row(row)
    if session is None:
        raise RuntimeError("failed to create session")
    return _session_out(session, principal, now)


async def heartbeat(aconn, principal: Principal, session_id: int) -> SessionOut:
    """Refresh `last_seen`, plus every active claim this session holds.

    Ordering is load-bearing: the session is read first, touched next, and
    only then swept - otherwise a session could be killed by its own
    heartbeat.
    """
    now = utcnow()
    ttl = lock_ttl()
    member_id = principal.member_id

    async with aconn.transaction():
        async with aconn.cursor() as cur:
            await cur.execute(_SELECT_SESSION_SQL, (session_id,))
            session_row = await cur.fetchone()

            await cur.execute(
                """
                UPDATE sessions
                   SET last_seen = %s
                 WHERE id = %s AND member_id = %s AND ended_at IS NULL
                """,
                (now, session_id, member_id),
            )
            await cur.execute(
                """
                UPDATE file_locks
                   SET refreshed_at = %s
                 WHERE session_id = %s
                   AND released_at IS NULL
                   AND EXISTS (
                     SELECT 1 FROM sessions s
                      WHERE s.id = file_locks.session_id
                        AND s.member_id = %s
                        AND s.ended_at IS NULL
                   )
                """,
                (now, session_id, member_id),
            )

        await sweep(aconn, principal.org_id, now, ttl)

    session = assert_owned(_to_session_row(session_row), session_id, principal)
    return _session_out(session, principal, now)


@dataclass(frozen=True)
class SessionEnded:
    session_id: int
    ended: bool
    locks_released: int


async def end_session(aconn, principal: Principal, session_id: int) -> SessionEnded:
    now = utcnow()

    async with aconn.transaction():
        async with aconn.cursor() as cur:
            await cur.execute(_SELECT_SESSION_SQL, (session_id,))
            session_row = await cur.fetchone()

            await cur.execute(
                """
                UPDATE file_locks
                   SET released_at = %s
                 WHERE session_id = %s
                   AND released_at IS NULL
                   AND EXISTS (
                     SELECT 1 FROM sessions s
                      WHERE s.id = file_locks.session_id AND s.member_id = %s
                   )
                RETURNING id
                """,
                (now, session_id, principal.member_id),
            )
            released_rows = await cur.fetchall()

            await cur.execute(
                """
                UPDATE sessions
                   SET ended_at = %s
                 WHERE id = %s AND member_id = %s AND ended_at IS NULL
                """,
                (now, session_id, principal.member_id),
            )

    session = _to_session_row(session_row)
    if session is None or session.member_id != principal.member_id:
        raise not_found(f"no such session: {session_id}")

    return SessionEnded(session_id=session_id, ended=True, locks_released=len(released_rows))


async def latest_live_session(aconn, principal: Principal) -> SessionRow | None:
    """The caller's most recent live session, or None.

    Tools other than `jupiter_checkin` reuse the most recent live session
    instead of opening a new one per call.
    """
    now = utcnow()
    async with aconn.transaction():
        await sweep(aconn, principal.org_id, now, lock_ttl())

        async with aconn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, member_id, org_id, working_dir, started_at, last_seen, ended_at
                  FROM sessions
                 WHERE member_id = %s AND ended_at IS NULL
                 ORDER BY last_seen DESC, id DESC
                 LIMIT 1
                """,
                (principal.member_id,),
            )
            row = await cur.fetchone()

    return _to_session_row(row)


async def ensure_session_id(aconn, principal: Principal) -> int:
    """The caller's live session id, opening one if they have none."""
    existing = await latest_live_session(aconn, principal)
    if existing is not None:
        return existing.id
    created = await create_session(aconn, principal, None)
    return created.session_id
