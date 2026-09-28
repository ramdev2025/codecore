"""Everything `jupiter_checkin` / `jupiter_who_is_working` need, in one
transaction. Ported from jupiter-code's lib/activity.ts."""

from __future__ import annotations

from dataclasses import dataclass

from .announcements_repo import ANNOUNCEMENTS_SQL, AnnouncementOut, announcement_cutoff, to_announcements
from .config import ANNOUNCEMENT_LIMIT, lock_ttl
from .locks_repo import ACTIVE_LOCKS_SQL, LockOut, _to_active_lock, lock_out
from .sweep import sweep
from .time_util import isoformat, now as utcnow


@dataclass(frozen=True)
class ActivityOut:
    slug: str
    now: str | None
    lock_ttl_seconds: int
    locks: list[LockOut]
    active_members: list[str]
    announcements: list[AnnouncementOut]


async def activity_for(aconn, org_id: int, org_slug: str) -> ActivityOut:
    ttl = lock_ttl()
    now = utcnow()

    async with aconn.transaction():
        await sweep(aconn, org_id, now, ttl)

        async with aconn.cursor() as cur:
            await cur.execute(ACTIVE_LOCKS_SQL, (org_id,))
            lock_rows = await cur.fetchall()

            await cur.execute(
                """
                SELECT DISTINCT m.display_name
                  FROM sessions s
                  JOIN members m ON m.id = s.member_id
                 WHERE s.org_id = %s AND s.ended_at IS NULL
                 ORDER BY m.display_name
                """,
                (org_id,),
            )
            member_rows = await cur.fetchall()

            await cur.execute(ANNOUNCEMENTS_SQL, (org_id, announcement_cutoff(now), ANNOUNCEMENT_LIMIT))
            announcement_rows = await cur.fetchall()

    return ActivityOut(
        slug=org_slug,
        now=isoformat(now),
        lock_ttl_seconds=ttl,
        locks=[lock_out(_to_active_lock(row), ttl) for row in lock_rows],
        active_members=[row[0] for row in member_rows],
        announcements=to_announcements(announcement_rows),
    )
