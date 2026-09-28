"""The 5 tool orchestration functions.

Used by the AgentFlow tools (`tools/__init__.py`), which read and write this
deployment's own local database.

Ported from jupiter-code's lib/mcp/server.ts (`buildJupiterServer`).
"""

from __future__ import annotations

from .activity import activity_for
from .announcements_repo import announce as announce_repo
from .auth import Principal
from .errors import JupiterError
from .locks_repo import acquire_lock, active_locks_for, release_lock
from .render import render_activity, render_checkin, render_lock, render_overlaps
from .semantic import claims_for_analysis, get_semantic
from .sessions_repo import create_session, ensure_session_id, latest_live_session


async def _guard(body) -> str:
    """A tool must never throw at the caller."""
    try:
        return await body()
    except JupiterError as error:
        return f"Jupiter error: {error.message}"
    except Exception as error:  # noqa: BLE001 - deliberately catch-all, see module docstring
        return f"Jupiter error: {error}"


async def _with_session(aconn, principal: Principal, operation):
    """Run an operation against the caller's session, checking in again if
    that session turns out to be gone.

    The race this covers: a session can be swept between the lookup and the
    write.
    """
    session_id = await ensure_session_id(aconn, principal)
    try:
        return await operation(session_id)
    except JupiterError as error:
        if error.status_code not in (404, 409):
            raise
        from .sessions_repo import create_session as _create_session

        fresh = await _create_session(aconn, principal, None)
        return await operation(fresh.session_id)


async def jupiter_checkin(aconn, principal: Principal, working_dir: str | None = None) -> str:
    async def body() -> str:
        session = await create_session(aconn, principal, working_dir)
        activity = await activity_for(aconn, principal.org_id, principal.slug)
        return render_checkin(session, activity)

    return await _guard(body)


async def jupiter_lock_file(
    aconn,
    principal: Principal,
    file_path: str,
    intent: str = "editing",
    note: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    code: str | None = None,
) -> str:
    async def body() -> str:
        path = (file_path or "").strip()
        if not path:
            return "Jupiter error: file_path is required"
        chosen = intent or "editing"
        if chosen not in ("editing", "reading"):
            return "Jupiter error: intent must be 'editing' or 'reading'"

        async def operation(session_id: int):
            return await acquire_lock(
                aconn, principal, session_id, path, chosen, note, line_start, line_end, code
            )

        result = await _with_session(aconn, principal, operation)
        return render_lock(result)

    return await _guard(body)


async def jupiter_unlock_file(aconn, principal: Principal, file_path: str) -> str:
    async def body() -> str:
        path = (file_path or "").strip()
        if not path:
            return "Jupiter error: file_path is required"

        async def operation(session_id: int):
            return await release_lock(aconn, principal, session_id, path)

        result = await _with_session(aconn, principal, operation)
        return result.message

    return await _guard(body)


async def jupiter_who_is_working(aconn, principal: Principal) -> str:
    async def body() -> str:
        # Deliberately does not open a session: asking who is working should
        # not itself make you present.
        own = await latest_live_session(aconn, principal)
        activity = await activity_for(aconn, principal.org_id, principal.slug)
        rendered = render_activity(activity, own.id if own else None)

        extra: list[str] = []
        try:
            locks = await active_locks_for(aconn, principal.org_id)
            semantic = await get_semantic(aconn, principal.org_id, claims_for_analysis(locks))
            extra = render_overlaps(semantic.overlaps)
        except Exception:
            extra = []

        return f"{rendered}\n{chr(10).join(extra)}" if extra else rendered

    return await _guard(body)


async def jupiter_announce(aconn, principal: Principal, message: str) -> str:
    async def body() -> str:
        trimmed = (message or "").strip()
        if not trimmed:
            return "Jupiter error: message is required"

        async def operation(session_id: int):
            return await announce_repo(aconn, principal, session_id, trimmed[:280])

        result = await _with_session(aconn, principal, operation)
        return f"Announced to the team: {result.message}"

    return await _guard(body)
