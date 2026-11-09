# NewsDC

AI-powered discovery platform for Data Center news and research.

> Status: **Phase 2 (ingestion)**. See [docs/PHASE_STATUS.md](docs/PHASE_STATUS.md) and [plan.md](plan.md) for the build plan.

## Quick start (Docker)

```bash
cp .env.example .env          # fill in values; never commit .env
docker compose up --build    # backend runs `alembic upgrade head`, then seeds config/ on startup
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
uv run alembic upgrade head                # create/upgrade the schema (needs pgvector in Postgres)
uv run uvicorn app.main:app --reload       # http://localhost:8000
uv run python -m app.ingest --all --since-days 365   # backfill every enabled source
uv run python -m app.ingest --source hn              # one source; default window = since last success
uv run python -m app.worker                # scheduler process (jobs are registered in Phase 3)

# frontend
cd frontend
pnpm install
pnpm dev                                   # http://localhost:5173
```

## Checks (same as CI)

```bash
cd backend  && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest -q
# DB integration tests run only when TEST_DATABASE_URL points at a THROWAWAY pgvector database:
TEST_DATABASE_URL=postgresql+psycopg://newsdc:newsdc@localhost:5433/newsdc_test uv run pytest -q
cd frontend && pnpm lint --deny-warnings && pnpm typecheck && pnpm build
```

## Layout

```
backend/   FastAPI app (app/), Alembic migrations (alembic/), tests, uv project
config/    categories.yaml (14 categories) and sources.yaml (verified sources), seeded into the DB on startup
frontend/  React 19 + Vite + TypeScript + Tailwind + shadcn/ui
docs/      logs, decisions, risks, phase status
```

## Ingestion

Sources live in `config/sources.yaml`; each one was checked for a working endpoint, terms and robots.txt
(see [docs/SOURCE_REGISTER.md](docs/SOURCE_REGISTER.md)). Adapters are in `backend/app/ingest/`
(`hackernews`, `rss`, `arxiv`, `github`). The runner (`runner.py`) dedupes by canonical-URL hash in the
database, records each source's provenance in `item_sources`, writes one `pipeline_runs` row per source,
and checkpoints progress so an interrupted backfill resumes. One failing source never stops the others.
