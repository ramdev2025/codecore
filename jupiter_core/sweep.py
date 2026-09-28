"""The lazy expiry sweep.

Ported from jupiter-code's lib/db.ts `sweepStatements`. Runs at the top of
every read and every write - there is no cron and no background job anywhere
in Jupiter. Both statements are meant to run inside the caller's own
transaction (do not commit here) so the whole operation stays one round trip.

Order matters: sessions are closed first so the claim sweep immediately sees
the ones that just died.
"""

from __future__ import annotations

from datetime import datetime

from .time_util import lock_cutoff, session_cutoff

_SWEEP_SESSIONS_SQL = """
    UPDATE sessions
       SET ended_at = %(now)s
     WHERE org_id = %(org_id)s
       AND ended_at IS NULL
       AND last_seen < %(session_cutoff)s
"""

_SWEEP_LOCKS_SQL = """
    UPDATE file_locks
       SET released_at = %(now)s
     WHERE org_id = %(org_id)s
       AND released_at IS NULL
       AND (
         refreshed_at < %(lock_cutoff)s
         OR EXISTS (
           SELECT 1 FROM sessions s
            WHERE s.id = file_locks.session_id
              AND s.ended_at IS NOT NULL
         )
       )
"""


def _params(org_id: int, now: datetime, ttl: int) -> dict:
    return {
        "now": now,
        "org_id": org_id,
        "session_cutoff": session_cutoff(now, ttl),
        "lock_cutoff": lock_cutoff(now, ttl),
    }


async def sweep(aconn, org_id: int, now: datetime, ttl: int) -> None:
    """Async sweep, run against the caller's own (uncommitted) connection."""
    params = _params(org_id, now, ttl)
    async with aconn.cursor() as cur:
        await cur.execute(_SWEEP_SESSIONS_SQL, params)
        await cur.execute(_SWEEP_LOCKS_SQL, params)


def sweep_sync(conn, org_id: int, now: datetime, ttl: int) -> None:
    """Sync twin, for jupiter_admin."""
    params = _params(org_id, now, ttl)
    with conn.cursor() as cur:
        cur.execute(_SWEEP_SESSIONS_SQL, params)
        cur.execute(_SWEEP_LOCKS_SQL, params)
