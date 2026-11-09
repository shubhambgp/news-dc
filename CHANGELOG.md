# Changelog

All notable changes, grouped by build phase. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Phase 3: AI processing pipeline (2026-11-09)

#### Added
- **LangGraph pipeline** `backend/app/pipeline/graph.py`: `normalize -> prefilter -> classify -> gate -> embed -> near_duplicate_check -> store`, one graph run per `new` item, up to `LLM_CONCURRENCY` (5) in parallel, in pages of 50. A Postgres advisory lock prevents overlapping runs. `store` writes the annotation and the item status in one transaction, only while the item is still `new` (idempotent re-runs). Rejected items keep their annotation and reason. Pure decision logic (HTML/whitespace normalization, English heuristic, keyword pre-filter, gate) is in `pipeline/nodes.py`.
- **Classifier** `backend/app/ai/classify.py` + `backend/app/prompts/classify.md` (`classify-v2`): category list rendered from the DB into a cached system prompt; structured outputs with a strict JSON schema (category slugs and content types as enums); Pydantic validation with one repair call; tokens, latency, attempts, model, prompt version, prompt hash and estimated cost stored on `ai_annotations`. A test pins the prompt file's hash to `PROMPT_VERSION`.
- **Provider interface** `backend/app/ai/llm.py`: `LLMClient` / `LLMError(retryable, fatal)` with the Anthropic implementation (explicit connect/read timeouts, SDK retries with Retry-After, error classification, no prompt text in errors).
- **Embeddings** `backend/app/ai/embeddings.py`: fastembed `BAAI/bge-small-en-v1.5` (384-dim), lazy and thread-safe. Near-duplicates: cosine > 0.92 within ±14 days, with similarity and reason stored. Failed embeddings stay pending and are filled by the next run.
- **Spend controls**: `MAX_LLM_ITEMS_PER_RUN`, `DAILY_LLM_BUDGET_USD` (from per-page `pipeline_runs.cost_usd_estimate`), `pipeline_runs.stop_reason`; per-item retry limit (3) and run abort after 5 consecutive provider failures.
- **Durable jobs** `backend/app/jobs.py` + migration `0002`: `jobs` table (pending, running, succeeded, retry_wait, dead_letter, cancelled), `FOR UPDATE SKIP LOCKED` claims, heartbeat leases with reclaim, full-jitter backoff, dead letters, manual retry/cancel CLI, one active job per kind (partial unique index).
- **Worker** `backend/app/worker.py`: APScheduler enqueues `ingest_all` every `INGEST_INTERVAL_MINUTES`; the main loop claims and runs jobs; a finished ingest queues `pipeline`. Graceful SIGTERM: stop claiming, stop at the next safe point, release the job. Compose: `stop_grace_period: 60s` and a `models` volume for the embedding cache.
- CLIs: `python -m app.pipeline [--limit N] [--max-llm-items N] [--reprocess-outdated]`, `python -m app.jobs list|enqueue|retry|cancel`.
- **Evaluation**: `backend/scripts/eval_classifier.py` and `backend/tests/fixtures/eval_set.json` (40 real items, agent-labelled, human review pending). Results in `docs/AI_EVALUATION.md`; configuration and costs in `docs/AI_CONFIG.md`.
- Migration `0002`: `jobs`; `items.ai_attempts`, `items.status_reason`; `ai_annotations.attempts`; `pipeline_runs.kind`, `pipeline_runs.stop_reason`.
- `config/sources.yaml`: optional `dc_specific` (true for `dcd`, `dck`), so the pre-filter always passes them.
- Settings / `.env.example`: `CLASSIFIER_EFFORT`, `CLASSIFIER_INPUT_USD_PER_MTOK`, `CLASSIFIER_OUTPUT_USD_PER_MTOK`, `DAILY_LLM_BUDGET_USD`, `LLM_CONCURRENCY`, `LLM_TIMEOUT_SECONDS`, `NEAR_DUPLICATE_THRESHOLD`, `JOB_LEASE_SECONDS`, `FASTEMBED_CACHE_PATH`.
- Tests: pipeline unit tests (normalize, language, pre-filter, gate, validation and repair, refusal, cost, prompt pinning, injection escaping, provider error mapping, backoff), pipeline DB tests (every outcome, idempotent re-run, near-duplicates in one run and across runs, transient failures, provider outage, bad credentials, invalid output, item cap, daily limit, cost, embedding failure and backlog, overlapping runs, reprocess, shutdown), job and worker DB tests (dedupe, concurrent claims, backoff to dead letter, permanent failure, lease reclaim, release/cancel, worker outcomes, scheduler tick). An autouse fixture fails any real Anthropic call.

#### Changed vs. plan (see docs/DECISIONS.md D-024 to D-028)
- Structured outputs (`output_config.format`) instead of forced tool use, which current Opus/Sonnet/Fable models reject.
- Single-scheduler guard is a unique index on active jobs instead of an advisory scheduler lock; the pipeline run still takes an advisory lock.
- Near-duplicate canonical item = the item processed first.
- The reprocess-old-prompt action is a CLI flag now; the Admin button is Phase 8.
- Prompt `classify-v1` -> `classify-v2` after evaluation run 1 showed title-only HN items being cut by the quality gate.

#### Fixed
- `logging.py`: the Anthropic SDK's `httpx2` per-request INFO lines are silenced like `httpx`.
- Language heuristic (found in the live run): the first version judged text by its share of English function words, so terse English GitHub descriptions plus an `owner/repo` title looked non-English. 283 repos were rejected without reaching the classifier. It now requires positive evidence of another language. The 289 affected items were re-queued and re-run (192 processed). Regression tests use the real descriptions and fail on the old heuristic.
- Pre-filter rejection reasons were not stored. `items.processing_error` became `items.status_reason` (migration 0002 not yet released) and records the pre-filter or gate reason as well as errors.

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
