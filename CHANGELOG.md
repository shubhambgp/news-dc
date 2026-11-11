# Changelog

All notable changes, grouped by build phase. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] - 2026-11-11

### Phase 11: Polish, docs & presentation (2026-11-11)

#### Added
- `README.md` rewritten: features, screenshots (`docs/img/`), architecture, quick start, environment variable table, tests, deployment, project structure, how AI agents were used, limitations and future work.
- `docs/ARCHITECTURE.md`: Mermaid diagrams for the system, the ingestion and processing workflow with status transitions, and the Ask NewsDC (RAG) sequence, plus a table of key design decisions and trade-offs.
- `docs/AI_CONFIG.md`: summary table (prompts with versions, models, cost per 1,000 articles), the classifier output schema, and how to switch LLM providers.
- `docs/PRESENTATION.md`: Marp deck (15 slides) with a 5-minute demo script in the speaker notes.
- Frontend test `src/components/Markdown.test.tsx`; Vitest now also runs `.tsx` tests.

#### Fixed (code review of the security audit fixes, D-041)
- `/ask` answers without evidence (no LLM call) no longer count against the global Ask budget.
- Rate-limit keys: an IPv4-mapped IPv6 client (`::ffff:a.b.c.d`) is keyed by its IPv4 address instead of sharing one /64 with every IPv4 client.
- Fetcher: `trust_env=False`, so a `HTTP(S)_PROXY` in the environment can't bypass connection pinning. `Authorization` is also dropped on an https → http redirect to the same host.
- Test: the disconnect test checks that the stream slot is released.

#### Changed
- Version 1.0.0 (`backend/pyproject.toml`, `app.__version__`, `frontend/package.json`).

### Fix: concurrent ingest deadlock (2026-11-11)
- Two runs of the same source writing one page could deadlock on the unique indexes of `items` and `item_sources`, failing a run (seen in CI run 42956055213). Page writes of one source are now serialized with a transaction-level advisory lock, taken after enrichment, so no network I/O happens under it. `test_concurrent_runs_do_not_duplicate` now starts 8 runs instead of 3.

### Security audit fixes (2026-11-11)

Fixes for the audit in `security-audit/` (audited `8b4c0f0`). Decisions in D-040, triage in `docs/SECURITY.md#audit-2026-11-10`.

#### Security
- `/ask` has a limit for all clients together (`RATE_LIMIT_ASK_GLOBAL`, default `30/minute;500/day`), so the Anthropic spend has a ceiling however many IPs send requests (NDC-01).
- At most 8 Ask answers stream at once. Past that, the stream ends with an `error` event, code `busy`, and no LLM call is made, which keeps worker threads free for the rest of the API (NDC-05).
- The fetcher connects only to the address it has just checked, which closes the DNS-rebinding window (NDC-02). NAT64 addresses are refused (NDC-19). Each request must finish within 60 s (NDC-13). `Authorization` is dropped when a redirect goes to another host (NDC-17).
- URLs containing control characters are rejected at ingestion, and the Markdown export percent-encodes them (NDC-16).
- Rate limits key IPv6 clients by /64 (NDC-06). Admin sessions end when the backend restarts, so a logout can't be undone by a restart (NDC-08).
- Links written by the model (Ask answers, trend brief) render as plain text. Only `[n]` citations stay links (NDC-07).
- `API_DOCS=false` in production turns off Swagger UI and `openapi.json` (NDC-15).
- Production: `cap_drop: [ALL]` on backend, worker and frontend (NDC-10). Caddy is 2.11 and Nginx 1.30. `deploy.sh` pulls `db`/`caddy` and rebuilds with `--pull`, so security rebuilds of the same tags reach the server (NDC-24).
- The restore command reads the backup passphrase from a file descriptor, not the command line (NDC-22).

### Phase 10: Production Docker & deployment (2026-11-10)

#### Added
- `docker-compose.prod.yml`: Postgres+pgvector with no public port, backend (migrates on start, trusts proxy headers from Caddy), worker, Nginx frontend and Caddy on 80/443 with automatic HTTPS; `restart: unless-stopped` and log rotation on all services.
- `Caddyfile`: `/api/*` to the backend, everything else to the frontend; zstd/gzip (not on the `/ask` stream); HSTS and security headers; a CSP for the frontend.
- Production frontend stage (`nginx-unprivileged`, port 8080, immutable hashed assets, SPA fallback) and `frontend/nginx.conf`.
- `scripts/backup_db.sh` (AES-256 encrypted `pg_dump`, keeps 14), `scripts/smoke_test.sh` (production smoke test), `docs/DEPLOYMENT.md`.
- `Cache-Control: public, max-age=30` on public API `GET`s (`no-store` on admin and probes); `/topics` and `/stats` cached for 60 s.
- CI: `pip-audit`, `pnpm audit --prod`, and a job that builds both production images.
- `.env.example`: `DOMAIN`, `BACKUP_PASSPHRASE`.

#### Changed
- The backend Dockerfile is multi-stage (no uv in the runtime image) with a healthcheck. The frontend Dockerfile has a `dev` target, used by `docker-compose.yml`.

### Phase 9: Frontend UI, 9A–9E (2026-11-10)

#### Added
- **9A foundation:** React Router 8 with route-level code splitting (`frontend/src/App.tsx`), the layout (top bar with search, Ask AI, theme toggle and shortcuts help; desktop sidebar with navigation and categories; mobile bottom nav and drawer), a blue primary design token for both themes, and a typed API client for every public and admin endpoint (`src/lib/api.ts`) with the error envelope as `ApiError`. TanStack Query retries only network and 5xx errors.
- **9B feeds:** For You (onboarding topic picker on first visit, "why" reasons, marked Discover rows, Trending strip, "Your interests" panel with weights and a reset button), Trending (24h / 7d / 30d tabs), Most relevant, Topics grid (counts and latest headlines) and topic pages with a sort. Every feed has filters in the URL (category, content type, source, min quality) and infinite scroll (IntersectionObserver + "Load more"). Read items are dimmed, "Not interested" hides an item.
- **9C article, bookmarks, reading history:** article page (summary, technical/business insights, type, scores, entities, tags, "Read original", HN and related discussions, "Also covered by", related articles, bookmark, not interested). The localStorage profile (`src/lib/profile.ts`): open +1, 30 s visible reading +2, bookmark +3, not interested −3 on the item's categories and tags, ×0.95 daily decay, the server's limits, malformed storage tolerated, sync across tabs. Bookmarks page with client-side JSON/Markdown export.
- **9D:** Search (filters, date range, sort, highlighted snippets rendered without `innerHTML`, all state in the URL); Ask NewsDC (suggested questions, streamed answer over `fetch` + `ReadableStream`, `[n]` citations linking to source cards, stop button, 2 exchanges of history, errors discard partial answers); Dashboard (Recharts: per-day, funnel, category, content type, source; rising topics; the trend brief with citations; AI cost; last runs; export buttons; a table view under every chart); Admin (login, session after reload, all Phase 8 actions with the CSRF header, paid actions confirm first, sources pause/resume/ingest, category edit/enable, jobs with dead-letter retry, runs, rejected items with reprocess, logout).
- **9E:** keyboard shortcuts (`j/k`, `o`/`Enter`, `Shift+O`, `b`, `x`, `/`, `a`, `t`, `g h/t/p/b/d`, `?`, `Esc`) with a help dialog; skip link, labelled controls, focus rings; page titles and meta description; `robots.txt`.
- `GET /api/v1/search` takes `sort=relevance|latest` (latest = the same hits, newest first). Test: `test_search_sort_latest_keeps_hits_newest_first`.
- Tests: `src/lib/profile.test.ts` (Vitest, 10: weights, decay, limits, parsing, request body, SSE parsing) and `e2e/smoke.spec.ts` (Playwright: home → pick topics → article → bookmark → bookmarks → search → ask, plus theme persistence and the shortcuts dialog; API mocked). CI runs both.
- Dependencies: `react-router`, `recharts`, `react-markdown`; dev: `vitest`, `jsdom`, `@playwright/test`.

#### Changed
- Markdown from the model (answers, trend brief) is rendered by `react-markdown` with raw HTML skipped, images dropped and only `http(s)` links.

### Phase 8: Admin, security & export (2026-11-09)

#### Added
- Admin auth (`backend/app/api/admin.py`, `backend/app/security.py`): `POST /api/v1/admin/login` checks `ADMIN_TOKEN` in constant time and sets an HMAC-signed `HttpOnly; Secure; SameSite=Strict` session cookie (signed with a separate `SESSION_SECRET`, 30-minute expiry, new session and CSRF token on every login). `GET /admin/session` and `POST /admin/logout` (revokes the session) are added too. Every other admin route returns 401 without a session. `POST`/`PATCH` need `X-CSRF-Token` and an allowed Origin/Referer. Login is rate limited to 5/minute per IP and 30/minute globally. Admin is disabled (503) without a ≥ 16-char token and a ≥ 32-char secret.
- Admin actions: queue ingestion (all sources or one), a pipeline run or a trend brief; reprocess outdated items or one item; retry a dead-lettered job. Admin views: the last 50 runs and jobs, sources (pause/resume), categories (edit name/description/keywords/enabled), rejected items with reasons (paginated, filter by status).
- `GET /api/v1/export?format=json|md` with the shared item filters and `limit` ≤ 1000, served as an attachment. Markdown is grouped by category and escaped, with http(s) links only. The export never includes article text.
- `backend/scripts/export_dataset.py` and the committed sample `data/sample/newsdc_sample.json` / `.md` (1,000 records).
- Migration `0005`: `sources.admin_disabled`, `categories.admin_edited_at`.
- Settings / `.env.example`: `SESSION_SECRET`, `ADMIN_SESSION_MINUTES`, `RATE_LIMIT_ADMIN_LOGIN`, `RATE_LIMIT_ADMIN_LOGIN_GLOBAL`.
- `docs/SECURITY.md` (controls, tests, secret rotation, what Phases 9/10 add).
- Tests: `tests/test_admin.py` (16, no DB) and `tests/test_admin_db.py` (12, real Postgres).

#### Changed
- Seeding no longer overwrites the text of a category edited in Admin. It never touches the Admin pause on sources (D-035).
- "Outdated" annotations (reprocess) now also include a different prompt hash, so a category edit marks existing classifications outdated (D-035).
- The `ingest_all` job takes an optional `source` key.
- CORS allows credentials, `PATCH` and `X-CSRF-Token` (origins are still the `CORS_ORIGINS` allow-list).
- The For You profile allows ≤ 100 `tagWeights` (was 200), as Phase 8 specifies.
- The frontend dev image runs as the `node` user.

### Phase 7: Emerging trends and dashboard data (2026-11-09)

#### Added
- `backend/app/ai/trends.py`: rising topics (tags, companies, technologies; last 7 days vs the 28 before, as shares of the items in each window, ≥3 items this week) and the weekly trend brief (top 30 items of the week by relevant score, rising topics as a hint, `ASSISTANT_MODEL`, citations validated with `CitationFilter`, stored in `trend_briefs` with model, prompt version, tokens and cost).
- `backend/app/prompts/trend_brief.md` (`trend-brief-v1`, hash pinned by a test).
- `GET /api/v1/trends` (rising tags/companies/technologies + the latest brief with its numbered sources) and `GET /api/v1/stats` (funnel, items per category with average quality, per content type, per source, per day for 60 days, the last 10 pipeline runs, estimated AI cost) in `backend/app/api/trends.py`.
- Job kind `trend_brief`: the worker enqueues it every Monday 06:00 UTC when the assistant model is configured; `python -m app.jobs enqueue trend_brief` runs it on demand (the Admin button comes with Phase 8).
- Migration `0004`: `trend_brief` job kind; `trend_briefs.model`, `prompt_version`, `tokens_in`, `tokens_out`, `cost_usd_estimate`; index on `created_at DESC`.
- Tests: `tests/test_trends.py` (12, no DB) and `tests/test_trends_db.py` (8, real Postgres).
- Docs: API.md, ARCHITECTURE.md (rising formula), AI_CONFIG.md (trend brief), D-034.

### Phase 6: Ask NewsDC, RAG with citations (2026-11-09)

#### Added
- `POST /api/v1/ask` (`backend/app/api/ask.py`): Server-Sent Events with `sources`, `status`, `token`*, then `done` or `error`. Hybrid retrieval gets 25 candidates (keywords OR-ed plus the embedding of the question and the previous question), which are re-ranked by retrieval rank, relevance, quality and freshness to 8. Freshness weighs more for "latest"-type questions. Retrieval runs before the stream, and the DB session is closed while the answer streams. A client disconnect closes the LLM stream.
- `GET /api/v1/ask/suggestions`: the five example questions from the brief.
- `backend/app/ai/assistant.py`: the numbered, escaped evidence block (`[n]` title, publisher, date, URL, summary, insights; bounded), message builder with history, `CitationFilter` (removes citation numbers that don't map to a source, also when split across chunks), time-sensitivity detection, and the fixed no-evidence answer (no LLM call).
- `backend/app/prompts/assistant.md` (`assistant-v1`, hash pinned by a test): grounding, "say when not covered", conflicts, dates, prompt-injection guard, citation and style rules.
- `ChatLLM.stream_text` in `backend/app/ai/llm.py` (Anthropic `messages.stream`, effort, cached system prompt). Errors map to `LLMError` through the same function as `complete_json`.
- `scoring.ask_rank` (re-rank formula, documented in `docs/ARCHITECTURE.md`).
- `AskRequest` (question 3–500 chars; history ≤ 4 messages as user/assistant pairs) and `AskSource` schemas.
- Settings / `.env.example`: `ASSISTANT_EFFORT`, `ASSISTANT_MAX_TOKENS`, `ASSISTANT_INPUT_USD_PER_MTOK`, `ASSISTANT_OUTPUT_USD_PER_MTOK`, `RATE_LIMIT_ASK` (10/minute per IP). Each answer logs model, prompt version, tokens, latency, estimated cost and citation counts (never the question).
- Tests: `tests/test_assistant.py` (31, no DB) and `tests/test_ask_db.py` (5, real Postgres). `FakeChat` in `tests/fakes.py`.
- Docs: `/ask` contract in `docs/API.md`, retrieval in `docs/ARCHITECTURE.md`, assistant section in `docs/AI_CONFIG.md`, D-033.

#### Changed
- `search.hybrid()` was extracted from `GET /search` (same behaviour) so `/ask` reuses it.
- `AnthropicLLM` error mapping moved into `_llm_error()`, shared by both methods.

### Phase 5: Recommendation engine (2026-11-09)

#### Added
- `backend/app/recommend/scoring.py`: the trending, most relevant, related, freshness and For You formulas. Each is written once and used both in Python and as SQL expressions.
- `backend/app/recommend/foryou.py`: the For You ranking. It takes the anonymous profile, scores items on category, tag and embedding affinity plus quality and freshness, and excludes read, bookmarked and dismissed items. About 20% of slots are "Discover: <category>" items. Every item has a "why am I seeing this" `reason`. An empty profile gets a cold-start fallback (Trending + Most relevant).
- Endpoints: `GET /feeds/trending`, `POST /feeds/foryou` (`Profile` request schema with size limits and known slugs only; the response adds `kind`, `reason`, `score` and `cold_start`).
- `sort=trending` and `sort=relevant` on `/items` and `/topics/{slug}`.
- Request-body middleware: `Content-Length` is required (411) and bodies over 64 KiB are refused (413).
- `docs/ARCHITECTURE.md` with every formula. `docs/API.md` covers the new feeds, sorts and the profile contract.
- Tests: `tests/test_recommend.py` (15 unit tests: each formula, ordering, normalisation, discovery interleave, reasons, cold start), `tests/test_recommend_db.py` (9 tests against real Postgres, including the Phase 5 acceptance check), and 14 new `tests/test_api.py` cases (profile validation, body limits, new paths).

#### Changed
- `/feeds/relevant` now ranks by `(0.6·relevance + 0.4·quality) / (1 + age_days/30)` instead of `relevance × quality`.
- `/items/{id}/related` uses `scoring.related` (same formula as before).

#### Changed vs. plan (see docs/DECISIONS.md D-032)
- Trending `coverage_count` also counts extra sources that found the same URL (§11.2 provenance), not only near-duplicates.
- Client-side profile updates (event weights, daily decay, onboarding picker, reset) are frontend work in Phase 9B. Phase 5 delivers the server contract.

### Phase 4: Backend API (2026-11-09)

#### Added
- **Endpoints** under `/api/v1` (`backend/app/api/`): `GET /items` (filters `category`, `content_type`, `source`, `min_quality`, `from`, `to`; `sort=latest|relevance|quality`), `GET /items/{id}` (annotation, related links, `coverage` from every `item_sources` row, `also_covered_by` near-duplicates), `GET /items/{id}/related` (top 6 by cosine similarity + 0.1 per shared category), `GET /feeds/relevant` (relevance × quality), `GET /topics` (enabled categories with counts and their 3 newest items), `GET /topics/{slug}`, `GET /search` (hybrid: `websearch_to_tsquery` + `ts_rank_cd` and pgvector, merged with Reciprocal Rank Fusion; `ts_headline` snippets, HTML-escaped with `<mark>` highlights; keyword-only fallback when embeddings fail).
- `backend/app/schemas.py`: Pydantic response models. Timestamps are always serialized as UTC with `Z`.
- `backend/app/api/common.py`: shared session dependency, filters, `page`/`page_size` pagination (max 50) with deterministic `…, id DESC` ordering, and the processed-items query (rejected and duplicate items never appear).
- Middleware (`backend/app/main.py`, `backend/app/security.py`): request ID (`X-Request-ID`, echoed or generated, added to every log line of the request), one JSON access-log line per request, the error envelope `{error: {code, message, request_id}}` for 404/405/422/429/500/503, security headers and an API CSP, per-IP rate limit `RATE_LIMIT_DEFAULT` (60/minute; health and ready exempt), and CORS that exposes `X-Request-ID`.
- Migration `0003`: generated `ai_annotations.summary_tsv` with a GIN index, so search also matches the AI summary (D-029).
- Settings / `.env.example`: `RATE_LIMIT_DEFAULT`, `SEARCH_MIN_SIMILARITY`.
- `docs/API.md`: the endpoint contract (parameters, pagination, ordering, errors, headers).
- Tests: `tests/test_api.py` (33, no DB: validation for every endpoint, error envelope, request ID, headers, CORS, rate limit, 500/503, OpenAPI paths, RRF, snippet escaping) and `tests/test_api_db.py` (30, real Postgres: every endpoint, every filter, sorts, pagination without skips or repeats, provenance, duplicates hidden, related ranking, topics, hybrid/semantic/keyword-fallback search, similarity floor, UTC sessions).

#### Changed
- DB sessions run with `timezone=UTC` (the local cluster defaulted to `Asia/Kolkata`).
- `uvicorn.access` is silenced; `app.access` logs each request with its request ID.
- Compose: the `backend` container now also mounts the `models` volume, because search embeds the query.
- Dependencies: `slowapi` replaced by `limits` (D-030).

#### Changed vs. plan (see docs/DECISIONS.md D-029 to D-031)
- Rate limiting uses `limits` directly. With FastAPI 0.162, slowapi's middleware cannot find routes and exempted every request.
- `sort=trending` and `/feeds/trending`, `/feeds/foryou` come in Phase 5. `/ask`, `/stats`, `/trends`, `/export` and `/admin/*` come in their own phases and are not stubbed.
- Semantic search drops hits below cosine 0.6 (`SEARCH_MIN_SIMILARITY`). Without the floor, any query returned 100 "semantic" hits.

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
