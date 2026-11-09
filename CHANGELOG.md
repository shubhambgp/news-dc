# Changelog

All notable changes, grouped by build phase. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Phase 0: Project skeleton & dev environment (2026-11-09)

#### Added
- `backend/`: uv project (Python 3.12) with the Phase 0 dependency set (FastAPI, SQLAlchemy, Alembic, psycopg, pgvector, pydantic-settings, httpx, feedparser, trafilatura, tenacity, anthropic, fastembed, langgraph, APScheduler 3.x, slowapi, python-json-logger, PyYAML; dev: pytest, pytest-asyncio, respx, ruff, mypy). `uv.lock` committed.
- `app/config.py`: settings from env/`.env` for every Phase 0 variable.
- `app/logging.py`: JSON logging for the app and uvicorn.
- `GET /api/v1/health` (liveness, always 200, returns `{status, db, version}`) and `GET /api/v1/ready` (503 when DB is unreachable). OpenAPI at `/api/v1/docs`.
- `app/worker.py`: APScheduler process entrypoint (`python -m app.worker`), no jobs yet.
- Health tests (`backend/tests/test_health.py`).
- `frontend/`: React 19 + Vite 8 + TypeScript + Tailwind v4 + shadcn/ui (button, card, badge) + TanStack Query + custom ThemeProvider (system / light / dark, persisted to localStorage). A single status page calls `/api/v1/health`.
- `docker-compose.yml`: `db` (pgvector/pgvector:pg16, named volume, healthcheck), `backend` (hot reload), `worker`, `frontend` (Vite dev server). Dev Dockerfiles for backend and frontend.
- `.env.example`, `.gitignore`, `.github/workflows/ci.yml` (backend: ruff format/lint, mypy, pytest; frontend: lint, typecheck, build).
- Project control docs: `docs/AI_AGENT_LOG.md`, `VERIFICATION_LOG.md`, `PHASE_STATUS.md`, `DECISIONS.md`, `RISKS.md`, `SOURCE_REGISTER.md`, `AI_EVALUATION.md`.

#### Changed vs. plan (see docs/DECISIONS.md)
- Routes are under `/api/v1` (PLAN §11.7 overrides the `/api/health` in Phase 0).
- Frontend linter is **oxlint** (current `create-vite` default) instead of ESLint.
- Dev DB is published on host port **5433** to avoid clashing with a local Postgres.
- Frontend production (Nginx) stage deferred to Phase 10, which owns production Dockerfiles.
