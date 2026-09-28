"""Team announcements. Ported from jupiter-code's lib/announcements.ts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .auth import Principal
from .config import ANNOUNCEMENT_MAX_LENGTH, ANNOUNCEMENT_WINDOW
from .errors import unprocessable
from .sessions_repo import _SELECT_SESSION_SQL, _to_session_row, assert_owned
from .time_util import isoformat, now as utcnow


def announcement_cutoff(now: datetime) -> datetime:
    from datetime import timedelta

    return now - timedelta(seconds=ANNOUNCEMENT_WINDOW)


ANNOUNCEMENTS_SQL = """
    SELECT a.message, a.created_at, m.display_name
      FROM announcements a
      LEFT JOIN members m ON m.id = a.member_id
     WHERE a.org_id = %s
       AND a.created_at >= %s
     ORDER BY a.created_at DESC, a.id DESC
     LIMIT %s
"""


@dataclass(frozen=True)
class AnnouncementOut:
    member: str
    message: str
    at: str | None


def to_announcements(rows) -> list[AnnouncementOut]:
    """Rows come back newest-first; the published order is oldest-first."""
    out = [
        AnnouncementOut(
            member="unknown" if row[2] is None else row[2],
            message=row[0],
            at=isoformat(row[1]),
        )
        for row in rows
    ]
    return list(reversed(out))


async def recent_announcements(aconn, org_id: int, limit: int) -> list[AnnouncementOut]:
    now = utcnow()
    async with aconn.cursor() as cur:
        await cur.execute(ANNOUNCEMENTS_SQL, (org_id, announcement_cutoff(now), limit))
        rows = await cur.fetchall()
    return to_announcements(rows)


@dataclass(frozen=True)
class AnnouncedOut:
    announced: bool
    member: str | None
    message: str
    at: str | None


async def announce(aconn, principal: Principal, session_id: int | None, raw_message: str) -> AnnouncedOut:
    message = (raw_message or "").strip()
    if not message:
        raise unprocessable("message must not be empty")
    if len(message) > ANNOUNCEMENT_MAX_LENGTH:
        raise unprocessable(f"message must be at most {ANNOUNCEMENT_MAX_LENGTH} characters")

    now = utcnow()

    if session_id is not None:
        async with aconn.transaction():
            async with aconn.cursor() as cur:
                await cur.execute(_SELECT_SESSION_SQL, (session_id,))
                session_row = await cur.fetchone()
                await cur.execute(
                    """
                    UPDATE sessions SET last_seen = %s
                     WHERE id = %s AND member_id = %s AND ended_at IS NULL
                    """,
                    (now, session_id, principal.member_id),
                )
        assert_owned(_to_session_row(session_row), session_id, principal)

    async with aconn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO announcements (org_id, member_id, message, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (principal.org_id, principal.member_id, message, now),
        )
        row = await cur.fetchone()

    return AnnouncedOut(
        announced=True,
        member=principal.display_name,
        message=message,
        at=isoformat(row[1] if row and row[1] else now),
    )
