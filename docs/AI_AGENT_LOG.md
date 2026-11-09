# AI Agent Log

Who did what, per phase. "Agent + Human verified" is used only after the human has actually confirmed the item.

## Phase 0: Project skeleton & dev environment

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Read the plan and inspect the repo | Agent | n/a |
| Root `.gitignore`, `.env.example` | Agent | Manual review of the diff; `git status` shows `.env` is ignored. Pending human verification |
| Backend uv project and dependencies | Agent | `uv sync --frozen` from a clean venv. Pending human verification |
| `app/config.py` (env settings) | Agent | Imported by tests and the running app. Pending human verification |
| JSON logging | Agent | Observed JSON log lines from uvicorn and the worker. Pending human verification |
| `GET /api/v1/health`, `GET /api/v1/ready` | Agent | pytest (3 tests) and curl against a real Postgres, up and down. Pending human verification |
| Worker entrypoint | Agent | Ran `python -m app.worker`, which started and blocked as expected. Pending human verification |
| Frontend scaffold (Vite, Tailwind, shadcn, TanStack Query, ThemeProvider) and status page | Agent | lint, typecheck, build, and headless Chrome screenshots (light and dark, 375 px). Pending human verification |
| `docker-compose.yml` and dev Dockerfiles | Agent | Compose-spec schema validation only. **Runtime check BLOCKED** (no Docker). Pending human verification |
| CI workflow | Agent | actionlint and GitHub workflow schema. Not yet run on GitHub. Pending human verification |
| Docs and logs (README, CHANGELOG, DECISIONS, RISKS, PHASE_STATUS, SOURCE_REGISTER, AI_EVALUATION, this log) | Agent | Manual review. Pending human verification |
| Diff review and commit | Agent | `git diff --stat` and `git status` reviewed before commit |

## Phase 1: Database schema & config

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 1, §5, §6, §11.2, §11.3, §11.6, §11.10 | Agent | n/a |
| SQLAlchemy models for all §5 tables + `item_sources` | Agent | `alembic check` reports no drift; DB integration tests. Pending human verification |
| Alembic setup and migration `0001` (vector extension, generated `tsv` + GIN, HNSW, indexes) | Agent | `alembic upgrade head` on a fresh DB; downgrade/upgrade roundtrip test; index definitions asserted in tests. Pending human verification |
| CHECK constraints, FK delete rules, timezone-aware timestamps | Agent | One integration test per constraint group, plus a query asserting no `timestamp without time zone` columns. Pending human verification |
| `config/categories.yaml` (14 categories, keywords) | Agent | Loader test asserts 14 valid entries. Category wording pending human review |
| `config/sources.yaml` (3 API sources, disabled) | Agent | Loader test. Endpoints/terms **not yet verified** (Phase 2) |
| Seeding (`app/seed.py`), startup hook, `python -m app.seed` | Agent | Integration test (14 categories, idempotent, Admin toggle survives); manual uvicorn run on an unmigrated DB (logs error, stays up) and on a migrated DB (seeds 14). Pending human verification |
| `canonicalize_url()` / `url_hash()` | Agent | 31 unit tests. Pending human verification |
| DB pool limits and statement timeouts | Agent | Code review only; exercised by the running app. Pending human verification |
| Compose (migrate on start, config mount) and CI Postgres service | Agent | compose-spec and GitHub workflow schema validation, actionlint. **Runtime BLOCKED** (no Docker; not pushed). Pending human verification |
| Docs and logs | Agent | Manual review. Pending human verification |


## Phase 2: Ingestion

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 2, §11.2, §11.3, §11.4, §11.6, §11.12, §13 | Agent | n/a |
| Checked every source URL (plan list plus replacements), robots.txt and terms page | Agent | `curl` status codes, `urllib.robotparser` evaluation, feed parsing (VERIFICATION_LOG). **Human review of terms pending**, especially NYT's non-commercial clause |
| `config/sources.yaml` (9 enabled, 2 disabled by robots.txt) and `docs/SOURCE_REGISTER.md` | Agent | Config tests; live runs of every enabled source. Pending human verification |
| `common.py`: `RawItem`, guarded `Http` (SSRF, redirects, size cap, throttle, retries), `Robots`, `extract_article` | Agent | 31 unit tests (`test_ingest_common.py`); live runs. Pending human verification |
| Adapters: `hackernews`, `rss`, `arxiv`, `github` | Agent | 9 fixture tests (`test_ingest_adapters.py`); live 365-day backfill. Pending human verification |
| Runner: dedupe, enrichment, upsert, provenance, per-source isolation, checkpoints, run records | Agent | 9 DB integration tests (`test_ingest_db.py`); two live full runs with counts compared. Pending human verification |
| CLI `python -m app.ingest` | Agent | Used for every live run; exit code 1 when a source failed (observed). Pending human verification |
| Bug found in live run: `304` treated as redirect (`KeyError: 'location'`) | Agent | Seen on the second DCD run. Fixed; regression test |
| Bug found in live backfill: transaction held open during enrichment → `IdleInTransactionSessionTimeout` on arXiv and GitHub | Agent | Seen in backfill run 1. Fixed; regression test confirmed failing before the fix and passing after; arXiv and GitHub re-run successfully |
| Docs: CHANGELOG, DECISIONS D-016 to D-023, RISKS R-009 to R-012, README, CLAUDE.md, this log, VERIFICATION_LOG, PHASE_STATUS | Agent | Manual review. Pending human verification |
| Diff review and commit | Agent | `git diff --stat`, `git status`, secret grep before commit |

## Phase 3: AI processing pipeline

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 3, §11.4, §11.5, §11.10–§11.13, §13; inspected Phase 2 code and the live DB | Agent | n/a |
| Supplied `ANTHROPIC_API_KEY` | Human | Pasted into the chat; the agent wrote it to the gitignored `.env` (mode 600). **The human should rotate this key**, since it is in the chat transcript |
| Verified model IDs and prices (`claude-haiku-5-5`) | Agent | Models API call with the key; pricing page fetched 2026-11-09 (D-024). Pending human verification |
| Migration 0002 (`jobs`, pipeline columns) and models | Agent | `test_models_match_migrations`, downgrade/upgrade round trip, applied to the live DB. Pending human verification |
| Provider interface + Anthropic client (`app/ai/llm.py`) | Agent | Unit tests for error classification; 3 live calls (cache hit confirmed). Pending human verification |
| Classifier, schema, validation, repair retry, prompt `classify.md` | Agent | 41 unit tests; live eval runs. Pending human verification |
| Prompt v1 → v2 after eval run 1 | Agent | Eval run 2 (D-028). Pending human verification |
| LangGraph pipeline, near-duplicates, spend limits, CLI | Agent | 14 DB integration tests with fake LLM/embedder; live runs 29 and 30 (2,609 processed). Pending human verification |
| Bug found in the live run: English heuristic rejected 283 terse English GitHub descriptions; pre-filter reasons not stored | Agent | Seen in run 29's rejection reasons. Fixed; regression test fails 2/2 on the old heuristic; 289 items re-run (run 30) |
| Durable jobs + worker (leases, backoff, dead letter, shutdown) | Agent | 18 DB tests (incl. concurrent claims, lease reclaim); live worker run: scheduled ingest → pipeline job → SIGTERM (VERIFICATION_LOG). Shutdown during a running job only tested in pytest. Pending human verification |
| Evaluation set (40 real items, labels) | Agent | Labelled blind before classification. **Human review of every label: pending** |
| Eval script and results | Agent | Two live runs recorded in AI_EVALUATION.md |
| Spot check of 20 processed + 20 rejected items | Agent | Agent's own judgement recorded in VERIFICATION_LOG. **Human spot check pending** |
| Docs: CHANGELOG, DECISIONS D-024–D-028, RISKS, AI_CONFIG, AI_EVALUATION, README, CLAUDE.md, .env.example, this log, VERIFICATION_LOG, PHASE_STATUS | Agent | Manual review. Pending human verification |
| Diff review and commit | Agent | `git diff --stat`, `git status`, secret grep before commit |

## Phase 4: Backend API

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 4, §11.7, §11.9, §11.10, §11.12, §13; inspected the Phase 1–3 code and the live DB | Agent | n/a |
| Response schemas, shared filters/pagination/base query (`app/schemas.py`, `app/api/common.py`) | Agent | `test_api_db.py` filter, sort and pagination tests. Pending human verification |
| `/items`, `/items/{id}`, `/items/{id}/related`, `/feeds/relevant`, `/topics`, `/topics/{slug}` | Agent | DB API tests plus the live smoke test on 2,609 real items. Pending human verification |
| Hybrid search (FTS + pgvector + RRF, snippets, keyword fallback), migration 0003 | Agent | DB API tests; similarity floor measured on 10 live queries (VERIFICATION_LOG). Pending human verification |
| Error envelope, request ID, access log, security headers, CORS | Agent | `test_api.py`; live curl. Pending human verification |
| Rate limiting: found slowapi exempting every route under FastAPI 0.162; replaced with `limits` | Agent | 62 live requests before (62 × 200) and after (60 × 200, then 429s); `test_rate_limit_returns_429_envelope_and_spares_health`. Pending human verification |
| Found the API depending on the session timezone (`Asia/Kolkata` locally) and `/feeds/relevant` ignoring `category` | Agent | Found by failing DB tests; fixed; the tests now pass |
| Docs: API.md, DECISIONS D-029 to D-031, RISKS R-017, CHANGELOG, CLAUDE.md | Agent | Pending human review |
| Try the API (e.g. `/api/v1/docs`, a search, an article detail) | Human | **Pending human verification** |

## Phase 5: Recommendation engine

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 5, §11.7, §11.12, §12, §13; inspected the Phase 4 API code and the live DB | Agent | n/a |
| Scoring formulas (`app/recommend/scoring.py`): trending, relevant, related, freshness, For You | Agent | 15 unit tests (`test_recommend.py`); SQL-vs-Python ordering test against Postgres. Pending human verification |
| `/feeds/trending`, `sort=trending|relevant` on `/items` and `/topics/{slug}`, new `/feeds/relevant` formula | Agent | `test_recommend_db.py` (ordering, coverage, pagination without repeats); live smoke test on 2,609 items. Pending human verification |
| `POST /feeds/foryou`: profile validation, discovery, reasons, cold start, exclusions | Agent | **Acceptance test** `test_cooling_heavy_profile_returns_mostly_cooling_plus_discovery_and_excludes_read` (8/10 cooling, 2 discovery, read/dismissed absent) plus a pure-ranking version; live request on real data. Pending human verification |
| Request body limits (411/413) | Agent | `test_request_body_size_limits`; live 413 check |
| Found and fixed: pgvector `avg()` returned a string (no result type) | Agent | Found by a failing DB test; fixed by typing `func.avg` as `Vector` |
| Docs: ARCHITECTURE.md, API.md, DECISIONS D-032, CHANGELOG, CLAUDE.md | Agent | Pending human review |
| Try the feeds (e.g. POST a profile to `/api/v1/feeds/foryou` in `/api/v1/docs`) and check the reasons make sense | Human | **Pending human verification** |

## Phase 6: Ask NewsDC (RAG with citations)

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 6, §11.5, §11.7, §11.8, §12, §13; inspected the Phase 3–5 LLM, search and API code | Agent | n/a |
| Verified `claude-opus-5-5` with the Models API; set `ASSISTANT_MODEL` in the local `.env` only | Agent | `models.retrieve` output in VERIFICATION_LOG |
| Streaming `ChatLLM.stream_text` and shared error mapping | Agent | `FakeChat` tests for success, mid-stream errors and disconnect; live streaming with 7 answers. Pending human verification |
| Retrieval (hybrid top 25 → re-rank to 8, recency for "latest" questions, history-aware query) | Agent | `test_ask_db.py` (5 tests against real Postgres); live answers on 2,609 items. Pending human verification |
| Prompt `assistant-v1`, evidence block, injection guard, citation filter, no-evidence path | Agent | `test_assistant.py` (31 tests). Pending human verification |
| SSE endpoint, validation, rate limit, 503 when unconfigured, `/ask/suggestions` | Agent | API tests; live 422 check |
| Found and fixed: raw RRF normalization made retrieval barely count against freshness | Agent | Found by a failing DB test; rank-position normalization (D-033) |
| **Acceptance:** five example questions return cited answers, and every `[n]` maps to a real source link | Agent | Live run, verbatim Q&A in VERIFICATION_LOG: ALL OK. Pending human verification |
| Docs: API.md, ARCHITECTURE.md, AI_CONFIG.md, DECISIONS D-033, RISKS R-005, CHANGELOG, CLAUDE.md, `.env.example` | Agent | Pending human review |
| Read the Q&A pairs in VERIFICATION_LOG and judge answer quality and faithfulness to the cited sources | Human | **Pending human verification** |



## Phase 7: Emerging trends and dashboard data

| Task | Done by | How verified |
|---|---|---|
| Re-read Phase 7, §5 (`trend_briefs`, `pipeline_runs`), §11.5, §11.8, §12, §13; inspected the jobs, worker, LLM, assistant and API code | Agent | n/a |
| Rising topics (share-based change, ≥3 items, publisher filter) | Agent | `test_trends.py`; live `/trends` on 2,609 items. Pending human verification |
| Prompt `trend-brief-v1`, `generate_brief`, citation filtering, storage with model/tokens/cost | Agent | `test_trends.py`, `test_trends_db.py`; one live brief (30 sources, 20 cited, 0 removed). Pending human verification |
| Migration 0004 (job kind, brief columns, index) | Agent | Fresh-migration and model/migration match tests; downgrade/upgrade round trip |
| Weekly schedule + `trend_brief` job handler | Agent | Cron next-run check; live run through `jobs.enqueue` → `claim` → `run_job` |
| `GET /trends`, `GET /stats` | Agent | `test_trends_db.py`; live responses cross-checked against SQL counts |
| Found and fixed: publishers listed as rising companies | Agent | Live `/trends`; unit test; D-034 |
| Docs: API.md, ARCHITECTURE.md, AI_CONFIG.md, DECISIONS D-034, CHANGELOG, CLAUDE.md | Agent | Pending human review |
| Read the live brief in VERIFICATION_LOG and judge whether it is faithful to its cited sources and useful | Human | **Pending human verification** |
