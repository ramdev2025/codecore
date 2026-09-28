# syntax=docker/dockerfile:1

# ---- stage 1: the dashboard -------------------------------------------------
# vite.config.ts writes to `../static`, so the source has to sit at the same
# relative depth here as it does in the repo for that path to land anywhere
# predictable.
FROM node:22-slim AS ui
WORKDIR /build/ui_source

COPY ui_source/package.json ui_source/package-lock.json ./
RUN npm ci

COPY ui_source/ ./
RUN npm run build
# -> /build/static

# ---- stage 2: the app -------------------------------------------------------
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# requirements.txt points at the AgentFlow wheel by relative path, so the wheel
# has to be in the context before pip runs. Both are copied ahead of the source
# so the dependency layer caches independently of code changes.
COPY requirements.txt agentflow-0.28.0-py3-none-any.whl ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py advisor.py workflow.yaml ./
COPY api/ api/
COPY jupiter_core/ jupiter_core/
COPY jupiter_admin/ jupiter_admin/
COPY mcp_app/ mcp_app/
COPY tools/ tools/
COPY --from=ui /build/static ./static

EXPOSE 8000

# One process, deliberately. The MCP StreamableHTTPSessionManager keeps session
# state in memory, so a second worker would strand half the sessions on the
# wrong process. Scale by making the machine bigger, never by adding workers.
CMD ["python", "app.py"]
