"""The live activity stream.

SSE replaced the original's 3-second dashboard poll. Expiry is still lazy, so
each tick runs the same batched `activity_for` any REST reader would, and a
frame only goes out when the payload actually changed.

Authentication accepts `?key=` in the query string because `EventSource`
cannot set headers. That is a deliberate, documented trade-off (a URL is more
likely than a header to land in a log or shell history) and nothing else in
the API accepts a key this way. A header still wins when one is present.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.routes import with_caller
from jupiter_core.activity import activity_for
from jupiter_core.auth import extract_key, principal_from_key_async, require_org_access
from jupiter_core.db import get_pool
from jupiter_core.errors import JupiterError
from jupiter_core.orgs_repo import get_org_by_slug

from .deps import run_sync

router = APIRouter(prefix="/api")

POLL_SECONDS = 2.0
KEEPALIVE_SECONDS = 15.0


def _stream_key(request: Request) -> str:
    """A header key if there is one, else `?key=`, else the canonical 401."""
    try:
        return extract_key(request.headers)
    except JupiterError:
        supplied = request.query_params.get("key")
        if supplied and supplied.strip():
            return supplied.strip()
        raise


@router.get("/orgs/{slug}/stream")
async def stream_activity(slug: str, request: Request) -> StreamingResponse:
    key = _stream_key(request)

    pool = await get_pool()
    async with pool.connection() as aconn:
        principal = await principal_from_key_async(key, aconn)

    org = await run_sync(get_org_by_slug, slug)
    require_org_access(principal, org.id)

    async def events():
        previous: str | None = None
        since_keepalive = 0.0

        while True:
            if await request.is_disconnected():
                return

            try:
                pool_ = await get_pool()
                async with pool_.connection() as conn:
                    activity = await activity_for(conn, org.id, org.slug)
                payload = with_caller(asdict(activity), principal)
                # `now` ticks every poll; excluding it keeps a quiet team quiet.
                # `me` is constant for the life of the stream, so it cannot
                # trigger a frame either.
                comparable = json.dumps(
                    {k: v for k, v in payload.items() if k not in ("now", "me")},
                    sort_keys=True,
                    default=str,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - a stream must not 500 mid-flight
                yield f"event: error\ndata: {json.dumps({'detail': str(error)})}\n\n"
                await asyncio.sleep(POLL_SECONDS)
                continue

            if comparable != previous:
                previous = comparable
                since_keepalive = 0.0
                yield f"data: {json.dumps(payload, default=str)}\n\n"
            else:
                since_keepalive += POLL_SECONDS
                if since_keepalive >= KEEPALIVE_SECONDS:
                    since_keepalive = 0.0
                    yield ": keepalive\n\n"

            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
