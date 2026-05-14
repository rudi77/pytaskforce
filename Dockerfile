# syntax=docker/dockerfile:1
#
# Taskforce Community — single-image deployment (API + bundled web UI).
# Build:  docker build -t taskforce-community .
# Run:    docker compose up
#
# Two stages: the React UI is compiled with pnpm, then dropped into the
# Python image so one process serves both the REST API and the front-end.

# ---- Stage 1: build the React web UI -------------------------------------
FROM node:20-bookworm-slim AS ui-builder

WORKDIR /build/ui
RUN corepack enable

# Install deps first (cached until the UI manifest/lockfile changes).
COPY ui/package.json ui/pnpm-lock.yaml ui/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# Build the production bundle into /build/ui/dist.
COPY ui/ ./
RUN pnpm run build

# ---- Stage 2: Python runtime ---------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# uv — fast, reproducible Python dependency installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# System libraries: poppler for pdf2image, curl for the healthcheck,
# tini for clean PID-1 signal handling. Chromium's own libs are added by
# `playwright install --with-deps` below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        ca-certificates \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TASKFORCE_WORK_DIR=/data \
    TASKFORCE_LOG_DIR=/data/logs \
    TASKFORCE_UI_DIR=/app/src/taskforce/api/_ui

WORKDIR /app

# Whole project (.dockerignore trims build artifacts / venvs / caches).
COPY . .

# Drop the compiled UI in where the API expects it (TASKFORCE_UI_DIR).
COPY --from=ui-builder /build/ui/dist ./src/taskforce/api/_ui

# Install the framework, unified CLI and bundled agent packages (butler /
# coding-agent / rag-agent) from the uv workspace, exactly as documented
# for local development.
RUN uv sync --frozen

# Chromium for the browser tool — version-matched to the installed
# Playwright so the browser binary never drifts from the SDK.
RUN uv run playwright install --with-deps chromium

# Run as a non-root user that owns the data volume and browser cache.
RUN useradd --create-home --uid 1000 taskforce \
    && mkdir -p /data/logs /ms-playwright \
    && chown -R taskforce:taskforce /data /app /ms-playwright
USER taskforce

VOLUME ["/data"]
EXPOSE 8070

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8070/health || exit 1

# tini reaps zombies (browser/tool subprocesses) and forwards signals.
ENTRYPOINT ["tini", "--"]
CMD ["taskforce", "serve", "--host", "0.0.0.0", "--port", "8070"]
