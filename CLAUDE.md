# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

NewsDC: AI-powered discovery platform for Data Center news (ingest HN/RSS/arXiv/GitHub → LangGraph AI pipeline → FastAPI → React UI, with RAG "Ask AI"). Built phase by phase from `plan.md` (the plan calls it `PLAN.md`; same file). Current progress is in `docs/PHASE_STATUS.md`.

## Working rules (from plan.md — read the relevant phase before coding)

- **plan.md §11 overrides earlier sections** where they conflict. Any further deviation goes in `docs/DECISIONS.md` (D-NNN entries).
- **One phase at a time.** Implement only the current phase's scope. Don't create files or modules that belong to later phases (D-006), and stop after the phase for human review.
- At the end of a phase, update `CHANGELOG.md`, `docs/AI_AGENT_LOG.md` (Task | Done by | How verified), `docs/VERIFICATION_LOG.md` (real commands and real output only, never invented), and `docs/PHASE_STATUS.md`. Mark something human-verified only if the human actually confirmed it. Otherwise write `pending human verification`.
- Use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`), and commit only after the checks pass.
- Never hardcode or assume LLM model IDs. `CLASSIFIER_MODEL` and `ASSISTANT_MODEL` come from env and default to empty (D-007). Prompts live in `backend/app/prompts/*.md`, not in Python strings. Mock the LLM in tests; never make a real paid call.
- The frontend talks to the backend only over the HTTP API. All routes go under `/api/v1`.
- Docker isn't available on the agent machine (RISKS R-001). Verify against a local Postgres+pgvector and record anything that's blocked.

## Commands

Backend (run from `backend/`, Python 3.12 via uv):
```bash
uv sync
uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest -q   # same as CI
uv run pytest tests/test_urls.py::test_http_and_https_stay_distinct    # single test
uv run alembic upgrade head          # needs pgvector available in Postgres
uv run uvicorn app.main:app --reload # API on :8000, docs at /api/v1/docs
uv run python -m app.worker          # APScheduler worker process
uv run python -m app.seed            # re-seed categories/sources from config/
```
DB integration tests (`tests/test_db.py`) are skipped unless `TEST_DATABASE_URL` is set. That database is **destroyed**: the tests drop the `public` schema, so point it at a throwaway database only:
```bash
TEST_DATABASE_URL=postgresql+psycopg://newsdc:newsdc@localhost:5433/newsdc_test uv run pytest -q
```

Frontend (run from `frontend/`, Node 24 + pnpm):
```bash
pnpm install
pnpm dev                                                  # :5173
pnpm lint --deny-warnings && pnpm typecheck && pnpm build # same as CI (lint is oxlint, D-002)
```

Full stack: `cp .env.example .env && docker compose up --build`. The compose DB is on host port **5433** (D-004). The backend container runs `alembic upgrade head` before uvicorn.

## Architecture

- **Config:** `app/config.py` is a single pydantic-settings `Settings` loaded from env or `.env` (repo root or `backend/`), accessed via the cached `get_settings()`. `config_dir` resolves to the repo-root `config/` locally and to `/config` in the container.
- **DB:** sync SQLAlchemy 2.0 with psycopg3. `app/db.py` holds the shared `engine` (bounded pool, statement and idle-in-transaction timeouts) and `SessionLocal`. Models are in `app/models.py`. Migrations in `alembic/versions/` are hand-reviewed, numbered `0001`, `0002`, and so on. `alembic/env.py` uses `sqlalchemy.url` if it is set, and falls back to `get_settings().database_url` otherwise.
- **Data model (plan §5 + §11.2):** provenance is many-to-many. One `items` row (deduped by the UNIQUE `url_hash`) can have many `item_sources` rows, each holding one source's external_id, URL, engagement and timestamps. When an exact URL duplicate arrives, attach a new `item_sources` row instead of discarding it. `ai_annotations` is 1:1 with items. `items` carries a pgvector embedding (384-dim, fastembed bge-small) and an FTS `tsvector`, which hybrid search combines.
- **URL dedup:** `app/ingest/common.py` holds `canonicalize_url` and `url_hash`. Every source adapter must use it. It deliberately doesn't rewrite http→https (D-010).
- **Seeding:** `app/seed.py` validates `config/categories.yaml` and `config/sources.yaml` with strict Pydantic models, then upserts them (ON CONFLICT) in one transaction on every API startup. Invalid YAML aborts startup. A DB error only logs. A category's `enabled` flag is owned by Admin after the first insert. A source's `enabled` flag is owned by the YAML, and an enabled source must have a `terms_url`.
- **Processes:** the `backend` (FastAPI, `app/main.py:create_app`) and the `worker` (`app/worker.py`, BlockingScheduler) are separate containers built from the same image. Ingestion and pipeline jobs get registered in the worker. `/api/v1/health` always returns 200 and reports the DB state. `/api/v1/ready` returns 503 when the DB is down (D-001).
- **Frontend:** React 19 + Vite + Tailwind v4 + shadcn/ui (uses the `cn` package, D-009), with TanStack Query. The API base comes from `VITE_API_BASE_URL`: `http://localhost:8000` in dev (the backend allows it through CORS, no Vite proxy), and empty in prod (same origin behind Caddy). No Next.js (§11.1).
- Logging is structured JSON via `app/logging.py:setup_logging`. Pass context through `extra={...}`.
