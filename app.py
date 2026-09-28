"""Jupiter — one process serving four things on one origin.

  /static/…          the dashboard
  /api/…             the REST surface and the SSE activity stream
  /api/mcp           the MCP server teammates' Claude Code instances connect to
  /ws/{session_id}   the coordination advisor agent, streaming

Same-origin throughout, so there is no CORS to configure between the parts.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from agentflow import AsyncWorkflowOrchestrator  # noqa: E402

import advisor  # noqa: E402
from api import rest_router, stream_router  # noqa: E402
from jupiter_core.db import close_pool, get_pool  # noqa: E402
from jupiter_core.errors import JupiterError  # noqa: E402
from mcp_app.server import MCP_ROUTE, session_manager  # noqa: E402
from mcp_app.server import app as mcp_asgi_app  # noqa: E402

ORCHESTRATOR: AsyncWorkflowOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ORCHESTRATOR
    # The MCP session manager's task group has to be live before it will serve
    # a single request (`StreamableHTTPSessionManager._handle_request` raises
    # otherwise), so entering run() here is required, not optional.
    async with session_manager.run():
        ORCHESTRATOR = await AsyncWorkflowOrchestrator.create(
            config_path="workflow.yaml",
            tools_module="tools",
        )
        # Hand the agent to the semantic layer, so overlap analysis is done by
        # the advisor agent rather than a direct gateway call. jupiter_core
        # stays AgentFlow-free; the dependency is injected, not imported.
        advisor.set_orchestrator(ORCHESTRATOR)
        await get_pool()
        try:
            yield
        finally:
            await ORCHESTRATOR.cleanup()
            await close_pool()


fastapi_app = FastAPI(title="Jupiter", lifespan=lifespan)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.exception_handler(JupiterError)
async def jupiter_error_handler(request: Request, error: JupiterError) -> JSONResponse:
    return JSONResponse({"detail": error.message}, status_code=error.status_code)


@fastapi_app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    """Render FastAPI's own validation failures in Jupiter's error shape.

    FastAPI defaults to `{"detail": [ {...}, … ]}`; every other error here is
    `{"detail": "<message>"}`, and clients parse one shape.
    """
    first = (error.errors() or [{}])[0]
    location = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path"))
    message = first.get("msg", "invalid request")
    return JSONResponse({"detail": f"{location}: {message}" if location else message}, status_code=422)


fastapi_app.include_router(rest_router)
fastapi_app.include_router(stream_router)


def _normalize_content(content):
    """Ensure event content is always a plain string.

    AgentFlow 'agent' events may carry AIMessage.content as a list of content
    blocks instead of a plain string; sending a non-string to the frontend
    renders as '[object Object]'.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


@fastapi_app.get("/")
async def root():
    return RedirectResponse(url="/static/")


@fastapi_app.websocket("/ws/{session_id}")
async def websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("message", "")
            state = {"messages": [{"role": "user", "content": query}]}
            config = {"thread_id": session_id}
            async for event in ORCHESTRATOR.run(state, config=config, stream_tokens=True):
                if "content" in event:
                    event = {**event, "content": _normalize_content(event["content"])}
                await websocket.send_json(event)
    except WebSocketDisconnect:
        pass


# The compiled dashboard lands here via `npm run build`. Tolerate its absence
# so the API and MCP server still start in a fresh checkout before the first
# UI build — StaticFiles refuses to mount a directory that does not exist.
os.makedirs("static", exist_ok=True)
fastapi_app.mount("/static", StaticFiles(directory="static", html=True), name="static")


class ASGIRouter:
    """Sends `/api/mcp` (and its `/api/mcp/{key}` fallback) to the MCP app with
    the path left intact; everything else — including lifespan — goes to FastAPI.

    Deliberately not `Mount(...)`: Starlette strips the prefix from
    `scope["path"]` for a mounted sub-app, but the MCP app's own routing and
    its `/api/mcp/{key}` -> `/api/mcp` rewrite both need the full path.
    """

    def __init__(self, mcp_app, http_app) -> None:
        self._mcp_app = mcp_app
        self._http_app = http_app

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == MCP_ROUTE or path.startswith(MCP_ROUTE + "/")):
            await self._mcp_app(scope, receive, send)
        else:
            await self._http_app(scope, receive, send)


app = ASGIRouter(mcp_asgi_app, fastapi_app)


if __name__ == "__main__":
    import asyncio
    import sys

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        # uvicorn.run()'s loop_factory hardcodes ProactorEventLoop on Windows
        # regardless of the ambient asyncio policy, and psycopg's async mode
        # needs a selector loop — so drive the server manually with one.
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())
