"""The hand-rolled Jupiter MCP server.

AgentFlow can only act as an MCP *client* (see `workflows/docs/MCP.md`), so
teammates who point Claude Code at Jupiter as an MCP *server* need this
separate, small component. It shares `jupiter_core.logic` with the Jupiter
AgentFlow app - one implementation, two front doors.

Built on the official `mcp` SDK's low-level `Server` (not `FastMCP`), because
per-request bearer auth needs raw access to the ASGI request, which FastMCP's
single-session model does not expose cleanly.

## Auth, before any MCP machinery runs

Matches jupiter-code's `lib/mcp/handler.ts` / `app/api/mcp/route.ts`:
authentication happens in a plain ASGI wrapper around the whole
streamable-HTTP session manager, so an unauthenticated caller gets a real
HTTP 401/403 *before* the JSON-RPC dispatcher ever sees the request - not an
error embedded in a tool result or a protocol-level MCP error.

The resolved `Principal` is stashed on `scope["state"]["principal"]`. The
transport constructs its own `starlette.requests.Request(scope, receive)`
downstream from the very same `scope` object (see
`mcp.server.streamable_http.StreamableHTTPServerTransport._handle_request`),
and that `Request` becomes `RequestContext.request` inside `call_tool`
handlers (`server.request_context.request`) - so reading
`.state.principal` there sees exactly what this wrapper set, no contextvars
needed for that hop. (`request_context` itself *is* a contextvar
(`mcp.server.lowlevel.server.request_ctx`), owned entirely by the SDK; we
only ride the `Request` object it threads through.)

`/api/mcp/{key}` is a labelled fallback for Claude Code's `--header`
forwarding bugs (anthropics/claude-code#29562, #50464): the key rides in the
path, gets authenticated exactly the same way, and the request is rewritten
to look like a plain `/api/mcp` call before reaching the session manager.
"""

from __future__ import annotations

from urllib.parse import unquote

import mcp.types as types
from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.requests import Request
from starlette.responses import JSONResponse

from jupiter_core import logic
from jupiter_core.auth import Principal, extract_key, principal_from_key_async, require_member
from jupiter_core.config import VERSION
from jupiter_core.db import get_pool
from jupiter_core.errors import JupiterError

MCP_ROUTE = "/api/mcp"

INSTRUCTIONS = """Jupiter shows what other developers on this team have their Claude Code
instances working on right now, so two people don't edit the same file at once.

Suggested habits:
  - call jupiter_checkin once at the start of a coding session;
  - call jupiter_lock_file before editing a file, and heed a 'blocked' result;
  - call jupiter_unlock_file when done with that file;
  - call jupiter_who_is_working before picking up a new area of the codebase.
Claims are advisory and expire on their own, so they never wedge the team."""

_TOOLS: list[types.Tool] = [
    types.Tool(
        name="jupiter_checkin",
        description=(
            "Register this Claude Code session with the team's Jupiter server and "
            "return a snapshot of what teammates are working on. Call once at the start "
            "of a coding session, before touching files."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "working_dir": {
                    "type": "string",
                    "description": "Absolute path of the repo/working directory for this session.",
                },
            },
        },
    ),
    types.Tool(
        name="jupiter_lock_file",
        description=(
            'Declare an intent to edit (or read) a file so teammates\' Claude Code '
            'instances can see it. Returns "clear" if nobody else holds the file, or a '
            "blocked warning naming the teammate who does. Call before editing a file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file, ideally relative to the repo root.",
                },
                "intent": {
                    "type": "string",
                    "enum": ["editing", "reading"],
                    "default": "editing",
                    "description": (
                        '"editing" conflicts with any other claim; "reading" only '
                        "conflicts with editors."
                    ),
                },
                "note": {
                    "type": "string",
                    "description": "Optional one-line note about what you are changing.",
                },
                "line_start": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional first line you are editing. Narrows the claim to a range, so "
                        "teammates editing far-apart regions of the same file no longer block "
                        "each other. Omit to claim the whole file."
                    ),
                },
                "line_end": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional last line you are editing (inclusive). Defaults to line_start."
                    ),
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Optional source of the claimed lines, so a teammate hitting a conflict "
                        "can see what you are changing. IGNORED unless the deployment sets "
                        "JUPITER_STORE_SNIPPETS - it is off by default, and it is never sent to "
                        "any LLM."
                    ),
                },
            },
            "required": ["file_path"],
        },
    ),
    types.Tool(
        name="jupiter_unlock_file",
        description="Release your claim on a file once you are done editing it.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The same path you passed to jupiter_lock_file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    types.Tool(
        name="jupiter_who_is_working",
        description=(
            "List every file currently claimed across the team, who holds it, and when "
            "the claim expires. Use before starting work in a new area of the codebase."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="jupiter_announce",
        description=(
            'Broadcast a short status message to teammates, e.g. "refactoring the auth '
            'module for the next hour".'
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The status message (truncated to 280 characters).",
                },
            },
            "required": ["message"],
        },
    ),
]


def build_server() -> Server:
    server: Server = Server("jupiter", version=VERSION, instructions=INSTRUCTIONS)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return _TOOLS

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        request = server.request_context.request
        principal = getattr(getattr(request, "state", None), "principal", None)
        if principal is None:
            # Unreachable: the ASGI auth wrapper rejects anything that would
            # reach here without one.
            return [types.TextContent(type="text", text="Jupiter error: missing authenticated principal")]

        pool = await get_pool()
        async with pool.connection() as aconn:
            if name == "jupiter_checkin":
                text = await logic.jupiter_checkin(aconn, principal, arguments.get("working_dir"))
            elif name == "jupiter_lock_file":
                text = await logic.jupiter_lock_file(
                    aconn, principal, arguments.get("file_path", ""),
                    arguments.get("intent", "editing"), arguments.get("note"),
                    arguments.get("line_start"), arguments.get("line_end"),
                    arguments.get("code"),
                )
            elif name == "jupiter_unlock_file":
                text = await logic.jupiter_unlock_file(aconn, principal, arguments.get("file_path", ""))
            elif name == "jupiter_who_is_working":
                text = await logic.jupiter_who_is_working(aconn, principal)
            elif name == "jupiter_announce":
                text = await logic.jupiter_announce(aconn, principal, arguments.get("message", ""))
            else:
                return [types.TextContent(type="text", text=f"unknown tool: {name}")]

        return [types.TextContent(type="text", text=text)]

    return server


_server = build_server()

session_manager = StreamableHTTPSessionManager(
    app=_server,
    stateless=True,
    json_response=False,
    # Auth is a bearer key checked by our own wrapper below, not Host/Origin
    # matching; explicit `None` keeps DNS-rebinding protection off regardless
    # of the deployment's Host header (its default is already off, but this
    # is the security-relevant choice, so it is spelled out here rather than
    # left implicit).
    security_settings=None,
)


def _method_not_allowed() -> JSONResponse:
    return JSONResponse(
        {"detail": "this MCP endpoint is stateless; POST JSON-RPC to it"},
        status_code=405,
        headers={"allow": "POST"},
    )


async def _authenticate(scope, receive) -> tuple[Principal | None, JSONResponse | None, str | None]:
    """Resolve the caller's Principal, or the JSONResponse to send instead.

    Returns `(principal, error_response, path_key)`. `path_key` is set when
    the request came in via the `/api/mcp/{key}` fallback, so the caller can
    rewrite `scope["path"]` before dispatching to the session manager.
    """
    request = Request(scope, receive)
    path = scope["path"]

    path_key: str | None = None
    if path != MCP_ROUTE and path.startswith(MCP_ROUTE + "/"):
        path_key = unquote(path[len(MCP_ROUTE) + 1 :])

    try:
        pool = await get_pool()
        async with pool.connection() as aconn:
            if path_key is not None:
                principal = await principal_from_key_async(path_key, aconn)
            else:
                key = extract_key(request.headers)
                principal = await principal_from_key_async(key, aconn)
            principal = require_member(principal)
    except JupiterError as error:
        return None, JSONResponse({"detail": error.message}, status_code=error.status_code), path_key

    return principal, None, path_key


class JupiterMCPApp:
    """Pure ASGI app: authenticates, then delegates to the MCP session manager."""

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return

        path = scope["path"]
        method = scope["method"]
        if method in ("GET", "DELETE") and path == MCP_ROUTE:
            await _method_not_allowed()(scope, receive, send)
            return
        if method != "POST":
            await _method_not_allowed()(scope, receive, send)
            return

        principal, error_response, path_key = await _authenticate(scope, receive)
        if error_response is not None:
            await error_response(scope, receive, send)
            return

        scope = dict(scope)
        scope["state"] = {**scope.get("state", {}), "principal": principal}
        if path_key is not None:
            scope["path"] = MCP_ROUTE
            scope["raw_path"] = MCP_ROUTE.encode("utf-8")

        await session_manager.handle_request(scope, receive, send)


app = JupiterMCPApp()
