"""The advisor agent's tools — the live claim set, and acting on it.

These wrap `jupiter_core`, the same business logic the REST API and the MCP
server call. One implementation, three front doors.

The agent acts as one configured member (`JUPITER_AGENT_API_KEY`). Each call
re-resolves the Principal — one cheap DB round trip — so rotating the key
takes effect on the next call rather than needing a restart.
"""

from __future__ import annotations

import json
import os

from langchain_core.tools import tool

from jupiter_core import logic
from jupiter_core.auth import Principal, principal_from_key_async
from jupiter_core.config import lock_ttl
from jupiter_core.db import get_pool
from jupiter_core.locks_repo import active_locks_for
from jupiter_core.semantic import claims_for_analysis
from jupiter_core.sweep import sweep
from jupiter_core.time_util import now as utc_now


async def _principal(aconn) -> Principal:
    key = os.environ.get("JUPITER_AGENT_API_KEY")
    if not key:
        raise RuntimeError(
            "JUPITER_AGENT_API_KEY is not set. Mint one with "
            "`python -m jupiter_admin join --slug <slug> --display-name jupiter-advisor` "
            "and put it in .env."
        )
    return await principal_from_key_async(key, aconn)


@tool
async def jupiter_checkin(working_dir: str | None = None) -> str:
    """Register a working session with the team and return a snapshot of who is
    working on what right now. Call once at the start of a coding session.

    Args:
        working_dir: Absolute path of the repo/working directory for this session.
    """
    pool = await get_pool()
    async with pool.connection() as aconn:
        return await logic.jupiter_checkin(aconn, await _principal(aconn), working_dir)


@tool
async def jupiter_lock_file(
    file_path: str,
    intent: str = "editing",
    note: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    """Declare an intent to edit (or read) a file, or a range of lines in it, so
    teammates can see it. Returns "clear" if nobody else holds an overlapping
    claim, or a blocked warning naming who does.

    Args:
        file_path: Path to the file, ideally relative to the repo root.
        intent: "editing" conflicts with any other claim; "reading" only conflicts with editors.
        note: Optional one-line note about what you are changing.
        line_start: Optional first line being edited. Narrows the claim to a range, so two
            people editing far-apart regions of one file do not block each other. Omit to
            claim the whole file.
        line_end: Optional last line being edited, inclusive. Defaults to line_start.
    """
    pool = await get_pool()
    async with pool.connection() as aconn:
        return await logic.jupiter_lock_file(
            aconn, await _principal(aconn), file_path, intent, note, line_start, line_end
        )


@tool
async def jupiter_unlock_file(file_path: str) -> str:
    """Release a claim on a file once the work on it is done.

    Args:
        file_path: The same path passed to jupiter_lock_file.
    """
    pool = await get_pool()
    async with pool.connection() as aconn:
        return await logic.jupiter_unlock_file(aconn, await _principal(aconn), file_path)


@tool
async def jupiter_who_is_working() -> str:
    """List every file currently claimed across the team, who holds it, and when
    each claim expires. Use before reasoning about whether work is safe to start."""
    pool = await get_pool()
    async with pool.connection() as aconn:
        return await logic.jupiter_who_is_working(aconn, await _principal(aconn))


@tool
async def jupiter_announce(message: str) -> str:
    """Broadcast a short status message to the team.

    Args:
        message: The status message (truncated to 280 characters).
    """
    pool = await get_pool()
    async with pool.connection() as aconn:
        return await logic.jupiter_announce(aconn, await _principal(aconn), message)


@tool
async def jupiter_analyze_overlaps() -> str:
    """Return the raw active claim set as JSON for reasoning about semantic
    overlap — which DIFFERENT files, held by DIFFERENT people, are likely to
    collide even though their paths differ.

    Returns only paths, intents, holder names and notes. Never file contents.
    Use this when asked whether work is safe to start, or what might collide.
    """
    pool = await get_pool()
    async with pool.connection() as aconn:
        principal = await _principal(aconn)
        ttl = lock_ttl()
        async with aconn.transaction():
            await sweep(aconn, principal.org_id, utc_now(), ttl)
            locks = await active_locks_for(aconn, principal.org_id)
    claims = claims_for_analysis(locks)
    if len(claims) < 2:
        return json.dumps({"claims": [], "note": "fewer than two active claims - nothing to compare"})
    return json.dumps(
        {
            "claims": [
                {
                    "file_path": c.file_path,
                    "intent": c.intent,
                    "holder": c.member,
                    "member_id": c.member_id,
                    "note": c.note,
                }
                for c in claims
            ]
        }
    )
