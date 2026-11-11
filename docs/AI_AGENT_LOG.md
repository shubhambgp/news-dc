# AI Agent Log

Who did what, per phase. "Agent + Human verified" is used only after the human has actually confirmed the item.

## Summary by kind of AI use

| Kind | What the AI did | Where to check | Verified by the human? |
|---|---|---|---|
| AI-assisted development | Claude Code (Claude Opus 5.5) wrote the code, migrations and config for every phase from `plan.md` | Git history, phase sections below | Phase reviews done (2026-11-11, see PHASE_STATUS) |
| Agent-based ingestion and classification | The agent ran the backfills, and the LangGraph pipeline classifies every item with `CLASSIFIER_MODEL` | VERIFICATION_LOG Phases 2–3, `/stats` | Spot check by the agent; human spot check done (2026-11-11) |
| Automated summarization | The classifier writes the summary and insights; Ask NewsDC and the weekly trend brief write cited answers | AI_CONFIG, VERIFICATION_LOG Phases 6–7 | Q&A pairs and the brief judged by the human (2026-11-11) |
| AI code review | A security audit (`security-audit/`, 24 findings) and a review pass of the fixes (Phase 11: 6 low findings, all fixed) | SECURITY.md, D-040, D-041, CHANGELOG 1.0.0 | Reviewed by the human (2026-11-11) |
| Test generation | The agent wrote all tests: 388 backend (pytest), 12 Vitest, 1 Playwright E2E. The LLM is mocked | `backend/tests/`, `frontend/src/**/*.test.*`, `frontend/e2e/` | CI runs them; reviewed by the human (2026-11-11) |
| Documentation | The agent wrote every doc, the CHANGELOG and the logs | `docs/`, README | Reviewed by the human (2026-11-11) |
| Human-only work | Plan, phase approvals, domain and DNS, API keys and credentials, deciding on open questions | n/a | Done by the human |

## Phase 0: Project skeleton & dev environment

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Read the plan and inspect the repo | Agent | n/a |
| Root `.gitignore`, `.env.example` | Agent | Manual review of the diff; `git status` shows `.env` is ignored. Verified by human (2026-11-11) |
| Backend uv project and dependencies | Agent | `uv sync --frozen` from a clean venv. Verified by human (2026-11-11) |
| `app/config.py` (env settings) | Agent | Imported by tests and the running app. Verified by human (2026-11-11) |
| JSON logging | Agent | Observed JSON log lines from uvicorn and the worker. Verified by human (2026-11-11) |
| `GET /api/v1/health`, `GET /api/v1/ready` | Agent | pytest (3 tests) and curl against a real Postgres, up and down. Verified by human (2026-11-11) |
| Worker entrypoint | Agent | Ran `python -m app.worker`, which started and blocked as expected. Verified by human (2026-11-11) |
| Frontend scaffold (Vite, Tailwind, shadcn, TanStack Query, ThemeProvider) and status page | Agent | lint, typecheck, build, and headless Chrome screenshots (light and dark, 375 px). Verified by human (2026-11-11) |
| `docker-compose.yml` and dev Dockerfiles | Agent | Compose-spec schema validation only. **Runtime check BLOCKED** (no Docker). Verified by human (2026-11-11) |
| CI workflow | Agent | actionlint and GitHub workflow schema. Not yet run on GitHub. Verified by human (2026-11-11) |
| Docs and logs (README, CHANGELOG, DECISIONS, RISKS, PHASE_STATUS, SOURCE_REGISTER, AI_EVALUATION, this log) | Agent | Manual review. Verified by human (2026-11-11) |
| Diff review and commit | Agent | `git diff --stat` and `git status` reviewed before commit |

## Phase 1: Database schema & config

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 1, §5, §6, §11.2, §11.3, §11.6, §11.10 | Agent | n/a |
| SQLAlchemy models for all §5 tables + `item_sources` | Agent | `alembic check` reports no drift; DB integration tests. Verified by human (2026-11-11) |
| Alembic setup and migration `0001` (vector extension, generated `tsv` + GIN, HNSW, indexes) | Agent | `alembic upgrade head` on a fresh DB; downgrade/upgrade roundtrip test; index definitions asserted in tests. Verified by human (2026-11-11) |
| CHECK constraints, FK delete rules, timezone-aware timestamps | Agent | One integration test per constraint group, plus a query asserting no `timestamp without time zone` columns. Verified by human (2026-11-11) |
| `config/categories.yaml` (14 categories, keywords) | Agent | Loader test asserts 14 valid entries. Category wording reviewed by the human (2026-11-11) |
| `config/sources.yaml` (3 API sources, disabled) | Agent | Loader test. Endpoints/terms **not yet verified** (Phase 2) |
| Seeding (`app/seed.py`), startup hook, `python -m app.seed` | Agent | Integration test (14 categories, idempotent, Admin toggle survives); manual uvicorn run on an unmigrated DB (logs error, stays up) and on a migrated DB (seeds 14). Verified by human (2026-11-11) |
| `canonicalize_url()` / `url_hash()` | Agent | 31 unit tests. Verified by human (2026-11-11) |
| DB pool limits and statement timeouts | Agent | Code review only; exercised by the running app. Verified by human (2026-11-11) |
| Compose (migrate on start, config mount) and CI Postgres service | Agent | compose-spec and GitHub workflow schema validation, actionlint. **Runtime BLOCKED** (no Docker; not pushed). Verified by human (2026-11-11) |
| Docs and logs | Agent | Manual review. Verified by human (2026-11-11) |


## Phase 2: Ingestion

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 2, §11.2, §11.3, §11.4, §11.6, §11.12, §13 | Agent | n/a |
| Checked every source URL (plan list plus replacements), robots.txt and terms page | Agent | `curl` status codes, `urllib.robotparser` evaluation, feed parsing (VERIFICATION_LOG). Terms reviewed by the human (2026-11-11), incl. NYT's non-commercial clause |
| `config/sources.yaml` (9 enabled, 2 disabled by robots.txt) and `docs/SOURCE_REGISTER.md` | Agent | Config tests; live runs of every enabled source. Verified by human (2026-11-11) |
| `common.py`: `RawItem`, guarded `Http` (SSRF, redirects, size cap, throttle, retries), `Robots`, `extract_article` | Agent | 31 unit tests (`test_ingest_common.py`); live runs. Verified by human (2026-11-11) |
| Adapters: `hackernews`, `rss`, `arxiv`, `github` | Agent | 9 fixture tests (`test_ingest_adapters.py`); live 365-day backfill. Verified by human (2026-11-11) |
| Runner: dedupe, enrichment, upsert, provenance, per-source isolation, checkpoints, run records | Agent | 9 DB integration tests (`test_ingest_db.py`); two live full runs with counts compared. Verified by human (2026-11-11) |
| CLI `python -m app.ingest` | Agent | Used for every live run; exit code 1 when a source failed (observed). Verified by human (2026-11-11) |
| Bug found in live run: `304` treated as redirect (`KeyError: 'location'`) | Agent | Seen on the second DCD run. Fixed; regression test |
| Bug found in live backfill: transaction held open during enrichment → `IdleInTransactionSessionTimeout` on arXiv and GitHub | Agent | Seen in backfill run 1. Fixed; regression test confirmed failing before the fix and passing after; arXiv and GitHub re-run successfully |
| Docs: CHANGELOG, DECISIONS D-016 to D-023, RISKS R-009 to R-012, README, CLAUDE.md, this log, VERIFICATION_LOG, PHASE_STATUS | Agent | Manual review. Verified by human (2026-11-11) |
| Diff review and commit | Agent | `git diff --stat`, `git status`, secret grep before commit |

## Phase 3: AI processing pipeline

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 3, §11.4, §11.5, §11.10–§11.13, §13; inspected Phase 2 code and the live DB | Agent | n/a |
| Supplied `ANTHROPIC_API_KEY` | Human | Pasted into the chat; the agent wrote it to the gitignored `.env` (mode 600). The key was in the chat transcript; **rotated by the human (2026-11-11)** |
| Verified model IDs and prices (`claude-haiku-5-5`) | Agent | Models API call with the key; pricing page fetched 2026-11-09 (D-024). Verified by human (2026-11-11) |
| Migration 0002 (`jobs`, pipeline columns) and models | Agent | `test_models_match_migrations`, downgrade/upgrade round trip, applied to the live DB. Verified by human (2026-11-11) |
| Provider interface + Anthropic client (`app/ai/llm.py`) | Agent | Unit tests for error classification; 3 live calls (cache hit confirmed). Verified by human (2026-11-11) |
| Classifier, schema, validation, repair retry, prompt `classify.md` | Agent | 41 unit tests; live eval runs. Verified by human (2026-11-11) |
| Prompt v1 → v2 after eval run 1 | Agent | Eval run 2 (D-028). Verified by human (2026-11-11) |
| LangGraph pipeline, near-duplicates, spend limits, CLI | Agent | 14 DB integration tests with fake LLM/embedder; live runs 29 and 30 (2,609 processed). Verified by human (2026-11-11) |
| Bug found in the live run: English heuristic rejected 283 terse English GitHub descriptions; pre-filter reasons not stored | Agent | Seen in run 29's rejection reasons. Fixed; regression test fails 2/2 on the old heuristic; 289 items re-run (run 30) |
| Durable jobs + worker (leases, backoff, dead letter, shutdown) | Agent | 18 DB tests (incl. concurrent claims, lease reclaim); live worker run: scheduled ingest → pipeline job → SIGTERM (VERIFICATION_LOG). Shutdown during a running job only tested in pytest. Verified by human (2026-11-11) |
| Evaluation set (40 real items, labels) | Agent | Labelled blind before classification. Every label reviewed by the human (2026-11-11) |
| Eval script and results | Agent | Two live runs recorded in AI_EVALUATION.md |
| Spot check of 20 processed + 20 rejected items | Agent | Agent's own judgement recorded in VERIFICATION_LOG. Human spot check done (2026-11-11) |
| Docs: CHANGELOG, DECISIONS D-024–D-028, RISKS, AI_CONFIG, AI_EVALUATION, README, CLAUDE.md, .env.example, this log, VERIFICATION_LOG, PHASE_STATUS | Agent | Manual review. Verified by human (2026-11-11) |
| Diff review and commit | Agent | `git diff --stat`, `git status`, secret grep before commit |

## Phase 4: Backend API

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 4, §11.7, §11.9, §11.10, §11.12, §13; inspected the Phase 1–3 code and the live DB | Agent | n/a |
| Response schemas, shared filters/pagination/base query (`app/schemas.py`, `app/api/common.py`) | Agent | `test_api_db.py` filter, sort and pagination tests. Verified by human (2026-11-11) |
| `/items`, `/items/{id}`, `/items/{id}/related`, `/feeds/relevant`, `/topics`, `/topics/{slug}` | Agent | DB API tests plus the live smoke test on 2,609 real items. Verified by human (2026-11-11) |
| Hybrid search (FTS + pgvector + RRF, snippets, keyword fallback), migration 0003 | Agent | DB API tests; similarity floor measured on 10 live queries (VERIFICATION_LOG). Verified by human (2026-11-11) |
| Error envelope, request ID, access log, security headers, CORS | Agent | `test_api.py`; live curl. Verified by human (2026-11-11) |
| Rate limiting: found slowapi exempting every route under FastAPI 0.162; replaced with `limits` | Agent | 62 live requests before (62 × 200) and after (60 × 200, then 429s); `test_rate_limit_returns_429_envelope_and_spares_health`. Verified by human (2026-11-11) |
| Found the API depending on the session timezone (`Asia/Kolkata` locally) and `/feeds/relevant` ignoring `category` | Agent | Found by failing DB tests; fixed; the tests now pass |
| Docs: API.md, DECISIONS D-029 to D-031, RISKS R-017, CHANGELOG, CLAUDE.md | Agent | Reviewed by the human (2026-11-11) |
| Try the API (e.g. `/api/v1/docs`, a search, an article detail) | Human | **Verified by human (2026-11-11)** |

## Phase 5: Recommendation engine

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 5, §11.7, §11.12, §12, §13; inspected the Phase 4 API code and the live DB | Agent | n/a |
| Scoring formulas (`app/recommend/scoring.py`): trending, relevant, related, freshness, For You | Agent | 15 unit tests (`test_recommend.py`); SQL-vs-Python ordering test against Postgres. Verified by human (2026-11-11) |
| `/feeds/trending`, `sort=trending|relevant` on `/items` and `/topics/{slug}`, new `/feeds/relevant` formula | Agent | `test_recommend_db.py` (ordering, coverage, pagination without repeats); live smoke test on 2,609 items. Verified by human (2026-11-11) |
| `POST /feeds/foryou`: profile validation, discovery, reasons, cold start, exclusions | Agent | **Acceptance test** `test_cooling_heavy_profile_returns_mostly_cooling_plus_discovery_and_excludes_read` (8/10 cooling, 2 discovery, read/dismissed absent) plus a pure-ranking version; live request on real data. Verified by human (2026-11-11) |
| Request body limits (411/413) | Agent | `test_request_body_size_limits`; live 413 check |
| Found and fixed: pgvector `avg()` returned a string (no result type) | Agent | Found by a failing DB test; fixed by typing `func.avg` as `Vector` |
| Docs: ARCHITECTURE.md, API.md, DECISIONS D-032, CHANGELOG, CLAUDE.md | Agent | Reviewed by the human (2026-11-11) |
| Try the feeds (e.g. POST a profile to `/api/v1/feeds/foryou` in `/api/v1/docs`) and check the reasons make sense | Human | **Verified by human (2026-11-11)** |

## Phase 6: Ask NewsDC (RAG with citations)

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-09.

| Task | Done by | How it was verified |
|---|---|---|
| Re-read Phase 6, §11.5, §11.7, §11.8, §12, §13; inspected the Phase 3–5 LLM, search and API code | Agent | n/a |
| Verified `claude-opus-5-5` with the Models API; set `ASSISTANT_MODEL` in the local `.env` only | Agent | `models.retrieve` output in VERIFICATION_LOG |
| Streaming `ChatLLM.stream_text` and shared error mapping | Agent | `FakeChat` tests for success, mid-stream errors and disconnect; live streaming with 7 answers. Verified by human (2026-11-11) |
| Retrieval (hybrid top 25 → re-rank to 8, recency for "latest" questions, history-aware query) | Agent | `test_ask_db.py` (5 tests against real Postgres); live answers on 2,609 items. Verified by human (2026-11-11) |
| Prompt `assistant-v1`, evidence block, injection guard, citation filter, no-evidence path | Agent | `test_assistant.py` (31 tests). Verified by human (2026-11-11) |
| SSE endpoint, validation, rate limit, 503 when unconfigured, `/ask/suggestions` | Agent | API tests; live 422 check |
| Found and fixed: raw RRF normalization made retrieval barely count against freshness | Agent | Found by a failing DB test; rank-position normalization (D-033) |
| **Acceptance:** five example questions return cited answers, and every `[n]` maps to a real source link | Agent | Live run, verbatim Q&A in VERIFICATION_LOG: ALL OK. Verified by human (2026-11-11) |
| Docs: API.md, ARCHITECTURE.md, AI_CONFIG.md, DECISIONS D-033, RISKS R-005, CHANGELOG, CLAUDE.md, `.env.example` | Agent | Reviewed by the human (2026-11-11) |
| Read the Q&A pairs in VERIFICATION_LOG and judge answer quality and faithfulness to the cited sources | Human | **Verified by human (2026-11-11)** |



## Phase 7: Emerging trends and dashboard data

| Task | Done by | How verified |
|---|---|---|
| Re-read Phase 7, §5 (`trend_briefs`, `pipeline_runs`), §11.5, §11.8, §12, §13; inspected the jobs, worker, LLM, assistant and API code | Agent | n/a |
| Rising topics (share-based change, ≥3 items, publisher filter) | Agent | `test_trends.py`; live `/trends` on 2,609 items. Verified by human (2026-11-11) |
| Prompt `trend-brief-v1`, `generate_brief`, citation filtering, storage with model/tokens/cost | Agent | `test_trends.py`, `test_trends_db.py`; one live brief (30 sources, 20 cited, 0 removed). Verified by human (2026-11-11) |
| Migration 0004 (job kind, brief columns, index) | Agent | Fresh-migration and model/migration match tests; downgrade/upgrade round trip |
| Weekly schedule + `trend_brief` job handler | Agent | Cron next-run check; live run through `jobs.enqueue` → `claim` → `run_job` |
| `GET /trends`, `GET /stats` | Agent | `test_trends_db.py`; live responses cross-checked against SQL counts |
| Found and fixed: publishers listed as rising companies | Agent | Live `/trends`; unit test; D-034 |
| Docs: API.md, ARCHITECTURE.md, AI_CONFIG.md, DECISIONS D-034, CHANGELOG, CLAUDE.md | Agent | Reviewed by the human (2026-11-11) |
| Read the live brief in VERIFICATION_LOG and judge whether it is faithful to its cited sources and useful | Human | **Verified by human (2026-11-11)** |


## Phase 8: Admin, security & export

| Task | Done by | How verified |
|---|---|---|
| Re-read Phase 8, §11.5, §11.6, §11.7, §11.9, §11.11, §11.13 and D-027/D-033/D-034 deferrals; inspected security, main, jobs, worker, seed, pipeline and API code | Agent | n/a |
| Admin session (stdlib HMAC cookie, `SESSION_SECRET`, rotation, logout revocation, expiry), CSRF token + origin check, login rate limits per IP and global | Agent | `test_admin.py` (16); live curl run. Verified by human (2026-11-11) |
| Admin actions: ingest all/one, pipeline, trend brief, reprocess outdated/one item, dead-letter retry, runs, jobs, sources pause/resume, category edit, rejected items | Agent | `test_admin_db.py` (12); live read-only calls on real data |
| Migration 0005 (`sources.admin_disabled`, `categories.admin_edited_at`); seed keeps admin edits; worker one-source ingest | Agent | Migration round trip; re-seed tests |
| Outdated = other prompt version or prompt hash (category edits) | Agent | `test_edit_category_survives_seed_and_outdates_annotations` |
| `GET /export` (JSON/Markdown, escaped, http(s) links only, no article text) and `scripts/export_dataset.py`; committed `data/sample/` (1,000 records) | Agent | `test_admin.py`, `test_admin_db.py`; live downloads; script output. Verified by human (2026-11-11) of the Markdown rendering |
| Hardening: profile tags ≤ 100, CORS credentials/PATCH/CSRF header, non-root frontend dev image, `.env.example`, `docs/SECURITY.md` | Agent | Tests; frontend image **not built** (no Docker) |
| Docs: API.md, SECURITY.md, DECISIONS D-035, RISKS R-018, CHANGELOG, CLAUDE.md | Agent | Reviewed by the human (2026-11-11) |
| Try admin login and the actions with a real `ADMIN_TOKEN`/`SESSION_SECRET`; open the exported Markdown and JSON | Human | **Verified by human (2026-11-11)** |

## Phase 9: Frontend UI (9A–9E)

| Task | Done by | How verified |
|---|---|---|
| Re-read Phase 9, §11.7, §11.8, §11.12, §12, D-032/D-033/D-035; inspected the Phase 0 frontend, `docs/API.md` and `schemas.py` | Agent | n/a |
| 9A: router, layout (top bar, sidebar, mobile nav/drawer), theme tokens, API client with error envelope | Agent | typecheck, lint, build; screenshots at 1366 px (light) and 375 px (dark) on live data |
| 9B: For You (picker, reasons, Discover, Trending strip, interests + reset), Trending tabs, Most relevant, Topics, topic pages, URL filters, infinite scroll | Agent | Screenshots on live data; E2E (picker → feed, request body has `explicitTopics`) |
| 9C: article page, localStorage profile (weights, decay, limits), reading tracking, bookmarks + JSON/Markdown export | Agent | `profile.test.ts` (10); E2E (article → bookmark → bookmarks) |
| 9D: Search (filters, dates, sort, snippets), Ask streaming UI with citations, Dashboard charts and brief, Admin UI; backend `sort=latest` on `/search` | Agent | E2E (search, mocked ask); live Ask (8/8 citations map to source cards); live Admin login/pause/resume/logout; pytest test for the sort |
| 9E: keyboard shortcuts and help, a11y (skip link, labels, focus), titles/meta, Playwright smoke test, CI steps | Agent | E2E (`g b`, `/`, `a`, `t` persisted over reload, `?`); Lighthouse |
| Lighthouse home page: Performance ≥ 85, Accessibility ≥ 95 | Agent | Lighthouse 13.6.0 run by the agent (numbers in VERIFICATION_LOG). Verified by human (2026-11-11) |
| Both themes look right; works at 375 px and desktop | Agent | Agent screenshots and an overflow check on 10 routes. **Verified by human (2026-11-11)** |
| Docs: CHANGELOG, API.md (search sort), DECISIONS D-036, logs, status | Agent | Reviewed by the human (2026-11-11) |
| Click through the UI in a browser (both themes, phone width), try the shortcuts, bookmark export and Admin | Human | **Verified by human (2026-11-11)** |

## Phase 10: Production Docker & deployment

| Task | Done by | How verified |
|---|---|---|
| Re-read Phase 10, §9 deployment, §11.9–11.11, SECURITY.md and RISKS owed items (R-017, CSP, backups, CI scans) | Agent | n/a |
| Multi-stage backend image with healthcheck; frontend `dev` + unprivileged Nginx prod stage; `nginx.conf` | Agent | Built and healthy on the VPS |
| `docker-compose.prod.yml` (no DB port, `restart: unless-stopped`, log rotation, proxy headers), `Caddyfile` (HTTPS, compression, headers, frontend CSP) | Agent | Running on the VPS; 308 redirect and in-network checks. HTTPS live at `https://news-dc.atinus.co` (Phase 10) |
| `Cache-Control` on public GETs; 60 s cache for `/topics` and `/stats` | Agent | 2 new pytest tests; header seen live |
| `scripts/backup_db.sh` (encrypted), restore procedure, cron | Agent | Backup + restore into a scratch DB on the VPS (1,120 items) |
| `scripts/smoke_test.sh`; CI `pip-audit`, `pnpm audit`, image builds | Agent | Audits run (clean); smoke test 8/8 on `https://news-dc.atinus.co`. CI green (run 42755588479) |
| Domain switch to `news-dc`, certificate, first-load incident (pipeline killed by a container recreate) and recovery | Agent | VERIFICATION_LOG |
| VPS setup: Docker, ufw, `.env` with fresh secrets, stack up, first data load | Agent (on the human's request, with the human's credentials) | VERIFICATION_LOG |
| `docs/DEPLOYMENT.md`, D-037, logs, status | Agent | Reviewed by the human (2026-11-11) |
| DNS A record for `news-dc.atinus.co` | Human | Done by the human; resolves to the VPS |
| Open the site over HTTPS, log in to Admin | Human | **Verified by human (2026-11-11)** |

## Security audit fixes (2026-11-11)

| Task | Done by | How verified |
|---|---|---|
| Triage the 24 findings in `security-audit/` against the code (SECURITY.md#audit-2026-11-10) | Agent | Code read per finding |
| Ask: all-clients limit, 8-stream cap | Agent | pytest (new tests) |
| Fetcher: pinned connections, NAT64, 60 s deadline, no cross-host `Authorization`, control characters in URLs | Agent | pytest (new tests) |
| IPv6 /64 rate-limit key, sessions end on restart, docs off in prod, model links as text | Agent | pytest, frontend checks |
| `cap_drop`, Caddy 2.11, Nginx 1.30, pull on deploy, restore passphrase via fd | Agent | Local Docker run (VERIFICATION_LOG) |
| Rotate the Anthropic key, set a spend limit, branch protection, check sshd | Human | **Verified by human (2026-11-11)** |
| Deploy and check the live site | Human | **Verified by human (2026-11-11)** |

## Phase 11: Polish, docs & presentation

Agent: Claude Code (Claude Opus 5.5). Date: 2026-11-11.

| Task | Done by | How verified |
|---|---|---|
| Re-read Phase 11, §8, §13, §16, §17; inspected the existing docs and the live `/stats` | Agent | n/a |
| Review pass of the security-fix commit `d89ad2b` | Agent (a review subagent; the main agent checked each finding against the code) | 1 finding traced in a scratch script (stream slot released on disconnect: no defect); 6 low findings reported |
| Fix the 6 findings: global Ask budget only for answers that call the LLM, IPv4-mapped rate-limit key, `trust_env=False`, no `Authorization` over http, slot-release assertion, Markdown link test | Agent | A regression test for each; full pytest 388 passed; Vitest 12 passed |
| README (features, screenshots, env table, structure, agent usage, limitations) | Agent | Claims checked against `config/sources.yaml`, `.env.example` and live `/stats`. Reviewed by the human (2026-11-11) |
| ARCHITECTURE Mermaid diagrams + trade-offs; AI_CONFIG summary, schema, provider switch | Agent | Checked against the code. Mermaid rendering checked on GitHub by the human (2026-11-11) |
| PRESENTATION.md (Marp, 15 slides, demo script) | Agent | Numbers from live `/stats` and AI_EVALUATION. Exported to PDF and rehearsed by the human (2026-11-11) |
| Screenshots of the live site | Agent | Headless Chrome; looked at by the agent |
| Final checks: backend, frontend, E2E, local production compose | Agent | VERIFICATION_LOG Phase 11 |
| Version 1.0.0, CHANGELOG, D-041, logs, status | Agent | Reviewed by the human (2026-11-11) |
| Deploy 1.0.0 (merge to `main` → push-to-deploy) and run `scripts/smoke_test.sh` | Human | **Verified by human (2026-11-11)** |
| Rehearse the demo, record the backup video, review the eval labels and the AI summaries | Human | **Verified by human (2026-11-11)** |

