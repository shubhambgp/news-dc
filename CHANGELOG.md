# Changelog

All notable changes, grouped by build phase. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Phase 2: Ingestion (2026-11-09)

#### Added
- Source adapters in `backend/app/ingest/`: `hackernews.py` (Algolia, title-phrase queries, backwards `created_at_i` cursor), `rss.py` (feedparser, conditional GET with ETag/Last-Modified), `arxiv.py` (API, newest first, versionless `https://arxiv.org/abs/<id>` URLs, PDF in `related_links`), `github.py` (repo search, stars as engagement, optional `GITHUB_TOKEN`).
- `common.py`: `RawItem` (Pydantic; HTML stripped from titles and descriptions, URLs must canonicalize, timestamps converted to UTC) and `Http`, a guarded httpx client. It checks for SSRF on every redirect hop (http/https only, every resolved address must be public, IPv4-mapped IPv6 included), caps response size (5 MB by default), throttles per source (`max_requests_per_minute`), and retries 429/5xx/rate-limit 403 with jittered backoff that honours Retry-After (bounded attempts; 4xx are not retried). Also `Robots` (per-origin robots.txt cache, RFC 9309 semantics), `extract_article` (trafilatura, 6,000 chars, 10 s, 2 MB, failures ignored; returns the resolved URL and a same-host `rel=canonical`), `content_hash`, and `html_to_text`.
- `runner.py`: `ingest_source(key)` and `ingest_all()`. Validates rows, dedupes by this source's external_id and then by `url_hash`, enriches only new items (full text, resolved URL, related HN threads via Algolia `search?restrictSearchableAttributes=url`), upserts with `INSERT ... ON CONFLICT (url_hash)` to refresh engagement, and attaches cross-source provenance in `item_sources`. Each page commits with its checkpoint. One `pipeline_runs` row per source. A failing source records its error on `sources.last_error` and the run row, and the other sources continue.
- CLI: `python -m app.ingest --source <key> [--since-days N]` and `--all`. Seeds config first, prints a JSON summary, and exits 1 if any source failed.
- `config/sources.yaml`: 11 verified sources (9 enabled: hn, arxiv, github, dcd, dck, sth, semianalysis, nyt_tech, ft_tech; 2 disabled by robots.txt: register_dc, nextplatform). New optional fields `queries` and `max_items_per_run`.
- `docs/SOURCE_REGISTER.md` filled in for every source.
- Tests (51 new): HTTP guard, SSRF, redirects, 304, size caps, retries and Retry-After, throttling, robots, extraction, RawItem (`test_ingest_common.py`); adapters against fixtures (`test_ingest_adapters.py`); DB integration: re-run creates no duplicates, engagement refresh, cross-source attach, redirect resolution before dedupe, broken source isolation, capped run plus checkpoint resume, three concurrent runs, a mid-run failure keeps committed pages and the resume cursor, no transaction held during enrichment, disabled source refused (`test_ingest_db.py`). Shared DB fixture and a fake-DNS fixture in `tests/conftest.py`.

#### Changed vs. plan (see docs/DECISIONS.md D-016 to D-023)
- The Register and The Next Platform are **disabled**: robots.txt is default-deny, and the Register `data_centre` feed is 404. SemiAnalysis uses the newsletter feed.
- RSS publishers that block Anthropic crawlers (DCD, DCK, NYT, FT) and SemiAnalysis are **metadata only**. Full text is fetched only for HN-linked pages and ServeTheHome, and only when robots.txt allows NewsDC, ClaudeBot and anthropic-ai.
- HN queries are quoted title phrases. `PUE` was dropped (prefix and typo matching hit about 33k unrelated stories).
- Adapters yield RawItem-shaped dicts, which the runner validates, so bad rows are counted rather than fatal.
- No scheduled ingestion job yet. The durable job lifecycle is Phase 3 (§11.4).

#### Fixed
- `Http` treated `304 Not Modified` as a redirect (httpx 0.28 `is_redirect` is true for every 3xx) and crashed with `KeyError: 'location'` on the second RSS run. It now uses `has_redirect_location`. Regression test added.
- Holding the page transaction open while new items were enriched: the throttled HN lookups for a 100-item arXiv page took about 100 s, past the 60 s `idle_in_transaction_session_timeout`, and the live backfill failed. The runner now commits the read before enrichment. Regression test checks `pg_stat_activity` during enrichment.
- If a run fails mid-way, the run record now reports only the committed pages.
- `logging.py`: the `httpx` logger is set to WARNING, so per-request INFO lines no longer drown the ingest logs.

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
