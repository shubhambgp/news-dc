# Changelog

All notable changes, grouped by build phase. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Phase 1: Database schema & config (2026-11-09)

#### Added
- `app/models.py`: SQLAlchemy 2.0 models for `sources`, `categories`, `items`, `item_sources`, `ai_annotations`, `pipeline_runs`, `trend_briefs`. All timestamps `timestamptz`. CHECK constraints for scores (0-100), item status, content type, source type, run trigger/status, non-negative counts, and `period_end > period_start`. Deliberate FK delete rules: provenance and sources are `RESTRICT`, annotations `CASCADE` with their item, `duplicate_of` `SET NULL`. Constraint naming convention.
- Alembic (`backend/alembic/`, `alembic.ini`) with migration `0001`: enables `vector`, creates every table, a generated `tsv` column with a GIN index, an HNSW index (`vector_cosine_ops`) on `embedding vector(384)`, and indexes on `(published_at DESC, id DESC)`, `status`, `primary_category`. The DB URL comes from `DATABASE_URL`.
- `item_sources` provenance table (PLAN §11.2): unique `(source_id, external_id)`, unique `(source_id, item_id)`, at most one primary source per item (partial unique index).
- `items` keeps `original_url`, `resolved_url`, `canonical_url` separately, a UNIQUE `url_hash`, an indexed `content_hash`, and `duplicate_similarity`/`duplicate_reason` for near-duplicates (PLAN §11.3).
- `config/categories.yaml` (the 14 categories with descriptions and pre-filter keywords) and `config/sources.yaml` (hn, arxiv, github with the §11.6 compliance fields, all **disabled** until Phase 2 verifies them).
- `app/seed.py`: Pydantic-validated YAML loaders and an idempotent upsert (`INSERT ... ON CONFLICT`). Runs on backend startup and as `python -m app.seed`. Refuses an enabled source without a `terms_url`.
- `app/ingest/common.py`: `canonicalize_url()` and `url_hash()`.
- DB engine: bounded pool (5 + 5 overflow, 10 s wait), `statement_timeout` 30 s, `idle_in_transaction_session_timeout` 60 s; `SessionLocal`.
- Tests: URL canonicalization (31 cases), config validation (8), DB integration (12: fresh migration, model/migration drift via `alembic check`, downgrade/upgrade roundtrip, seed idempotency, every constraint above, FTS, vector dimension).
- CI: `pgvector/pgvector:pg16` service and `TEST_DATABASE_URL`, so integration tests run in CI.
- Compose: backend runs `alembic upgrade head` before uvicorn; `./config` mounted read-only at `/config`.

#### Changed vs. plan (see docs/DECISIONS.md D-010 to D-015)
- URLs: `http` is **not** rewritten to `https` (PLAN §11.3 overrides the Phase 1 task list).
- `items.source_id`/`external_id` replaced by `primary_source_id` + `item_sources` (PLAN §11.2).
- `tsv` covers title (A), description (B), content_text (C). The AI summary lives in another table, which a generated column can't read.
- `sources` gained `settings` (jsonb: the rest of the YAML entry), `last_success_at`, `checkpoint`, timestamps. `pipeline_runs` gained `status`. `ai_annotations` gained `prompt_hash`, `latency_ms`, `cost_usd_estimate`, `updated_at`.
- The jobs table (§11.4) is deferred to Phase 3, which owns the durable worker.

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
