"""The REST surface, ported from jupiter-code's app/api/.

Route handlers stay thin — parse, authenticate, call `jupiter_core`, serialize.
Every error surfaces as ``{"detail": "<message>"}`` with the status code
`jupiter_core` chose; none of them are invented here.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from jupiter_core.activity import activity_for
from jupiter_core.announcements_repo import announce, recent_announcements
from jupiter_core.auth import Principal, require_org_access
from jupiter_core.config import (
    ANNOUNCEMENT_LIMIT,
    ANNOUNCEMENT_MAX_LIMIT,
    VERSION,
    lock_ttl,
)
from jupiter_core.errors import unprocessable
from jupiter_core.locks_repo import (
    acquire_lock,
    active_locks_for,
    release_lock,
    snippet_for,
)
from jupiter_core.orgs_repo import create_org, get_org_by_slug, join_org, list_members
from advisor import analyze_with_agent
from jupiter_core.semantic import claims_for_analysis, get_semantic
from jupiter_core.sessions_repo import create_session, end_session, ensure_session_id, heartbeat
from jupiter_core.sweep import sweep
from jupiter_core.time_util import now as utcnow

from .deps import current_member, current_principal, db_conn, run_sync

router = APIRouter(prefix="/api")

VALID_INTENTS = ("editing", "reading")


def _dump(value: Any) -> Any:
    return asdict(value) if hasattr(value, "__dataclass_fields__") else value


def _dump_list(values: list[Any]) -> list[Any]:
    return [_dump(v) for v in values]


def _require_str(body: dict, field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise unprocessable(f"{field} must not be empty")
    return value.strip()


def _optional_session_id(body: dict) -> int | None:
    raw = body.get("session_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise unprocessable("session_id must be an integer") from None


async def _session_for(aconn, principal: Principal, body: dict) -> int:
    """The session this write belongs to — the one supplied, or the caller's
    current live session (opened on demand)."""
    supplied = _optional_session_id(body)
    if supplied is not None:
        return supplied
    return await ensure_session_id(aconn, principal)


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": VERSION, "lock_ttl_seconds": lock_ttl()}


@router.post("/orgs", status_code=201)
async def post_orgs(body: dict = Body(default_factory=dict)) -> dict:
    name = _require_str(body, "name")
    raw_slug = body.get("slug")
    slug = raw_slug.strip() if isinstance(raw_slug, str) and raw_slug.strip() else None
    created = await run_sync(create_org, name, slug)
    return _dump(created)


@router.post("/orgs/{slug}/join", status_code=201)
async def post_join(slug: str, body: dict = Body(default_factory=dict)) -> dict:
    display_name = _require_str(body, "display_name")
    created = await run_sync(join_org, slug, display_name)
    return _dump(created)


# --------------------------------------------------------------------------
# Member or admin
# --------------------------------------------------------------------------


@router.get("/orgs/{slug}/members")
async def get_members(slug: str, principal: Principal = Depends(current_principal)) -> list:
    """A bare array, matching jupiter-code's `json(await listMembers(org.id))`.

    It was briefly wrapped in a {slug, members} envelope, which both broke
    parity with the original and made the dashboard's Team page throw
    "i.map is not a function".
    """
    org = await run_sync(get_org_by_slug, slug)
    require_org_access(principal, org.id)
    return _dump_list(await run_sync(list_members, org.id))


def with_caller(payload: dict, principal: Principal) -> dict:
    """Tag an activity payload with who asked for it.

    Added at the HTTP layer rather than inside `ActivityOut`, because "who is
    this request from" is a property of the request, not of the org's state -
    and ActivityOut also feeds the MCP text renderer, which must not change.

    The dashboard needs this to tell "Alice holds this" from "you hold this",
    so the activity log can say what *you* did and what *you* can do about it.
    """
    return {
        **payload,
        "me": {
            "kind": principal.kind,
            "member_id": principal.member_id,
            "display_name": principal.display_name,
        },
    }


@router.get("/orgs/{slug}/activity")
async def get_org_activity(
    slug: str,
    principal: Principal = Depends(current_principal),
    aconn=Depends(db_conn),
) -> dict:
    org = await run_sync(get_org_by_slug, slug)
    require_org_access(principal, org.id)
    return with_caller(_dump(await activity_for(aconn, org.id, org.slug)), principal)


@router.get("/activity")
async def get_activity(
    principal: Principal = Depends(current_principal),
    aconn=Depends(db_conn),
) -> dict:
    return with_caller(
        _dump(await activity_for(aconn, principal.org_id, principal.slug)), principal
    )


@router.get("/announcements")
async def get_announcements(
    request: Request,
    principal: Principal = Depends(current_principal),
    aconn=Depends(db_conn),
) -> dict:
    # Parsed by hand rather than via a typed query param so a bad value is a
    # 422 with our {"detail": "..."} shape, and so the value actually reaches
    # the query — jupiter-code's bug #5 was a limit that was silently ignored.
    raw = request.query_params.get("limit")
    if raw is None or raw == "":
        limit = ANNOUNCEMENT_LIMIT
    else:
        try:
            limit = int(raw)
        except ValueError:
            raise unprocessable("limit must be an integer") from None
        if limit < 1:
            raise unprocessable("limit must be at least 1")
        limit = min(limit, ANNOUNCEMENT_MAX_LIMIT)

    announcements = await recent_announcements(aconn, principal.org_id, limit)
    return {"limit": limit, "announcements": _dump_list(announcements)}


@router.get("/semantic")
async def get_semantic_route(
    principal: Principal = Depends(current_principal),
    aconn=Depends(db_conn),
) -> dict:
    async with aconn.transaction():
        await sweep(aconn, principal.org_id, utcnow(), lock_ttl())
        locks = await active_locks_for(aconn, principal.org_id)
    result = await get_semantic(
        aconn,
        principal.org_id,
        claims_for_analysis(locks),
        analyze=analyze_with_agent,
    )
    return _dump(result)


# --------------------------------------------------------------------------
# Member only
# --------------------------------------------------------------------------


@router.post("/sessions", status_code=201)
async def post_sessions(
    body: dict = Body(default_factory=dict),
    principal: Principal = Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    working_dir = body.get("working_dir")
    if working_dir is not None and not isinstance(working_dir, str):
        raise unprocessable("working_dir must be a string")
    return _dump(await create_session(aconn, principal, working_dir))


@router.post("/sessions/{session_id}/heartbeat")
async def post_heartbeat(
    session_id: int,
    principal: Principal = Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    return _dump(await heartbeat(aconn, principal, session_id))


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    principal: Principal = Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    return _dump(await end_session(aconn, principal, session_id))


@router.post("/locks")
async def post_locks(
    body: dict = Body(default_factory=dict),
    principal: Principal = Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    file_path = _require_str(body, "file_path")

    raw_intent = body.get("intent")
    intent = raw_intent.strip() if isinstance(raw_intent, str) and raw_intent.strip() else "editing"
    if intent not in VALID_INTENTS:
        raise unprocessable("intent must be 'editing' or 'reading'")

    note = body.get("note")
    if note is not None and not isinstance(note, str):
        raise unprocessable("note must be a string")

    code = body.get("code")
    if code is not None and not isinstance(code, str):
        raise unprocessable("code must be a string")

    # normalize_lines (inside acquire_lock) does the real validation and
    # raises 422 with a precise message.
    session_id = await _session_for(aconn, principal, body)
    result = await acquire_lock(
        aconn,
        principal,
        session_id,
        file_path,
        intent,
        note,
        body.get("line_start"),
        body.get("line_end"),
        code,
    )
    return _dump(result)


@router.get("/locks/{lock_id}/snippet")
async def get_lock_snippet(
    lock_id: int,
    principal: Principal = Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    """The stored source for one claim.

    Deliberately a separate request: snippets stay out of the bulk activity
    payload and the SSE frames, so code is only ever fetched when someone
    actually opens a conflict.
    """
    return _dump(await snippet_for(aconn, principal.org_id, lock_id))


@router.post("/locks/release")
async def post_locks_release(
    body: dict = Body(default_factory=dict),
    principal: Principal = Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    file_path = _require_str(body, "file_path")
    session_id = await _session_for(aconn, principal, body)
    return _dump(await release_lock(aconn, principal, session_id, file_path))


@router.post("/announcements", status_code=201)
async def post_announcements(
    body: dict = Body(default_factory=dict),
    principal: Principal = Depends(current_member),
    aconn=Depends(db_conn),
) -> dict:
    message = _require_str(body, "message")
    session_id = await _session_for(aconn, principal, body)
    return _dump(await announce(aconn, principal, session_id, message))
