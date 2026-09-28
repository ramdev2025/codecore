"""Request-scoped dependencies: a pooled connection, and the caller's Principal.

Auth lives entirely in `jupiter_core.auth` — `extract_key` already implements
the header precedence (`X-API-Key` wins over `Authorization`, bare
`Authorization: <key>` with no scheme accepted), so nothing here reimplements it.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import Depends, Request

from jupiter_core.auth import Principal, extract_key, principal_from_key_async, require_member
from jupiter_core.db import get_pool, sync_connection


async def db_conn():
    """One pooled async connection for the life of the request."""
    pool = await get_pool()
    async with pool.connection() as aconn:
        yield aconn


async def current_principal(request: Request, aconn=Depends(db_conn)) -> Principal:
    """Any valid key — member or admin. 401 if absent or bad."""
    key = extract_key(request.headers)
    return await principal_from_key_async(key, aconn)


async def current_member(principal: Principal = Depends(current_principal)) -> Principal:
    """A member key specifically. An admin key here is a 403."""
    return require_member(principal)


async def run_sync(fn: Callable[..., Any], *args: Any) -> Any:
    """Run one of the sync (psycopg.Connection) repo functions off the loop.

    `jupiter_core.orgs_repo` is sync because only the CLI used to call it;
    the API reaches it through here rather than duplicating the logic.
    """

    def call() -> Any:
        conn = sync_connection()
        try:
            return fn(conn, *args)
        finally:
            conn.close()

    return await asyncio.to_thread(call)
