# NewsDC

AI-powered discovery platform for Data Center news and research.

> Status: **Phase 0 (project skeleton)**. See [docs/PHASE_STATUS.md](docs/PHASE_STATUS.md) and [plan.md](plan.md) for the build plan.

## Quick start (Docker)

```bash
cp .env.example .env          # fill in values; never commit .env
docker compose up --build
curl localhost:8000/api/v1/health   # {"status":"ok","db":"ok","version":"0.1.0"}
open http://localhost:5173          # status page
```

API docs (OpenAPI): http://localhost:8000/api/v1/docs

## Quick start (without Docker)

Requires Python 3.12 via [uv](https://docs.astral.sh/uv/), Node 24 + pnpm, and a Postgres you can reach through `DATABASE_URL`.

```bash
# backend
cd backend
uv sync
uv run uvicorn app.main:app --reload       # http://localhost:8000
uv run python -m app.worker                # scheduler process (no jobs until Phase 2/3)

# frontend
cd frontend
pnpm install
pnpm dev                                   # http://localhost:5173
```

## Checks (same as CI)

```bash
cd backend  && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest -q
cd frontend && pnpm lint --deny-warnings && pnpm typecheck && pnpm build
```

## Layout

```
backend/   FastAPI app (app/), tests, uv project
frontend/  React 19 + Vite + TypeScript + Tailwind + shadcn/ui
docs/      logs, decisions, risks, phase status
```
