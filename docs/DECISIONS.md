# Decisions

Each entry: context, options, decision, why, trade-offs, and whether it changes the plan.

## D-001 (2026-11-09): Health route path and liveness vs readiness
- **Context:** Phase 0 says `GET /api/health`. §11.7 says all routes go under `/api/v1`, and §11.11 asks for a separate `/ready`.
- **Options:** (a) `/api/health` as written; (b) `/api/v1/health` plus `/api/v1/ready`.
- **Decision:** (b). `/health` always returns 200 and reports `db: ok|error` (`status: degraded` on DB failure). `/ready` returns 503 when the DB is down.
- **Why:** §11 explicitly overrides earlier wording. Keeping liveness separate stops an orchestrator from restarting a healthy API because of a DB outage.
- **Trade-offs:** none significant.
- **Changes plan:** no (it follows §11).

## D-002 (2026-11-09): Frontend linter is oxlint, not ESLint
- **Context:** The plan's tooling table names ESLint. The current `create-vite` `react-ts` template ships oxlint with React-hooks rules preconfigured.
- **Options:** (a) swap to ESLint plus plugins; (b) keep oxlint.
- **Decision:** (b). CI runs `pnpm lint --deny-warnings`.
- **Why:** It is the template default, has fewer dependencies, and covers the hook rules the plan cares about.
- **Trade-offs:** A smaller plugin ecosystem than ESLint. If a needed rule is missing, switch then.
- **Changes plan:** yes, minor tooling change (recorded in CHANGELOG).

## D-003 (2026-11-09): Dev API access via CORS, not a Vite proxy
- **Context:** In dev, the browser on :5173 must reach the API on :8000.
- **Decision:** The browser calls `VITE_API_BASE_URL` (default `http://localhost:8000`). The backend allows `CORS_ORIGINS`. In production `VITE_API_BASE_URL` is empty (same origin behind Caddy).
- **Why:** It uses only variables the plan already defines (§11.1 `VITE_API_BASE_URL`, `CORS_ORIGINS`) and adds no proxy config.
- **Changes plan:** no.

## D-004 (2026-11-09): Dev DB host port 5433
- **Context:** The development machine already runs Postgres on 5432.
- **Decision:** Compose publishes the DB at `127.0.0.1:${POSTGRES_PORT:-5433}`. Containers still reach it as `db:5432`.
- **Changes plan:** no (new optional env var `POSTGRES_PORT`).

## D-005 (2026-11-09): Phase 0 Dockerfiles are dev-only
- **Context:** Phase 0 task 6 mentions "production static build served by Nginx". Phase 10 owns multi-stage, hardened production Dockerfiles and `docker-compose.prod.yml`.
- **Decision:** Phase 0 ships dev Dockerfiles only. The backend already runs as a non-root user. The Nginx stage is built in Phase 10.
- **Why:** This avoids unverifiable production config before Phase 10, and Docker isn't available on the build machine (see RISKS R-001).
- **Changes plan:** no (deferral within the plan's own phases).

## D-006 (2026-11-09): Only Phase 0 paths are created now
- **Context:** Task 1 says "create the repo structure from Section 4". Many of those paths (`config/`, `ingest/`, `pipeline/`, `prompts/`, `docs/ARCHITECTURE.md`, …) belong to later phases.
- **Decision:** Create the files Phase 0 owns. Each later path is created by the phase that fills it.
- **Why:** The Definition of Done forbids presenting placeholders as complete. Empty modules would be placeholders.
- **Changes plan:** no.

## D-007 (2026-11-09): No default LLM model IDs
- **Decision:** `CLASSIFIER_MODEL` and `ASSISTANT_MODEL` default to empty. Phase 3 and 6 set them after checking the Anthropic docs.
- **Why:** §3 and §11.5 forbid assuming model IDs.

## D-008 (2026-11-09): Plan file kept as `plan.md` at repo root
- **Context:** The plan calls itself `PLAN.md` inside a `newsdc/` folder. The repository is `news-dc/` and the file is `plan.md`.
- **Decision:** Keep both names as they are. The repo root is the project root.
- **Changes plan:** no functional change.

## D-009 (2026-11-09): shadcn uses the `cn` package
- **Context:** The current shadcn CLI installs `cn` (from the shadcn-ui GitHub org) instead of `clsx` plus `tailwind-merge`.
- **Decision:** Accept the CLI default.

## D-010 (2026-11-09): Don't rewrite http to https during canonicalization
- **Context:** The Phase 1 task list mentions an "http→https" test. §11.3 says not to blindly rewrite `http` to `https`.
- **Decision:** `canonicalize_url()` keeps the scheme (lowercased). The test asserts `http://x/a` and `https://x/a` stay distinct. Redirect-following to a verified canonical URL happens at fetch time (Phase 2).
- **Why:** §11 overrides earlier wording. Some origins serve different resources over http.
- **Changes plan:** no (follows §11).

## D-011 (2026-11-09): Canonicalization details
- **Decision:** lowercase scheme and host; drop `www.`, userinfo, a trailing dot on the host, the default port, the fragment, tracking params (`utm_*`, `fbclid`, `gclid`, `ref`, ... case-insensitive); sort the remaining params as raw `k=v` strings (original encoding preserved); drop a trailing slash (root path stays `/`). Path case and meaningful params are preserved. Non-http(s) or host-less URLs raise `ValueError`.
- **Why:** sorting raw segments keeps values byte-identical while making parameter order irrelevant. Dropping userinfo keeps credentials out of the DB.
- **Trade-offs:** `ref` is removed as the plan asks, though a few sites use it meaningfully. A wrong merge costs one lost item; the original URL is stored anyway.
- **Changes plan:** no.

## D-012 (2026-11-09): Provenance via `item_sources`; `items` keeps `primary_source_id`
- **Context:** §5 puts `source_id` and `external_id` on `items`. §11.2 adds `item_sources` and says `items.source_id` can't be the only provenance.
- **Decision:** `items.primary_source_id` (nullable, display only); `external_id` lives only on `item_sources`. FK deletes on provenance are `RESTRICT`.
- **Changes plan:** no (follows §11.2).

## D-013 (2026-11-09): `tsv` excludes the AI summary
- **Context:** §5 asks for `tsv` = title A, summary B, content C as a generated column. The summary is in `ai_annotations`, and a Postgres generated column can only read its own row.
- **Options:** (a) trigger that copies the summary; (b) denormalize a summary column onto `items`; (c) generated column over title A, description B, content_text C, and let Phase 4 search also match annotations.
- **Decision:** (c) for now. Phase 4 revisits this when it builds hybrid search.
- **Why:** no trigger machinery before there is a search endpoint to justify it.
- **Changes plan:** yes, minor (recorded in CHANGELOG).

## D-014 (2026-11-09): Seed ownership rules
- **Decision:** categories: YAML owns `name`, `description`, `keywords`, `sort_order`; `enabled` is set only on insert and then owned by Admin. Sources: YAML owns every field including `enabled`, because §11.6 makes source config administrator-controlled and compliance-gated. YAML is validated with Pydantic (`extra="forbid"`); an enabled source without `terms_url` is rejected. Invalid YAML stops startup; a DB error during startup seeding is logged and the API stays up.
- **Changes plan:** no.

## D-015 (2026-11-09): Scope boundaries for Phase 1
- **Decision:** the §11.4 jobs table is created in Phase 3 (durable worker). Redirect-resolution tests (§11.3) belong to Phase 2, where URLs are fetched. RSS sources are added to `sources.yaml` in Phase 2 after each feed URL is verified, so no unverified URL is committed.
- **HNSW:** created in migration 0001. The table is empty at that point, so the build is instant and pgvector maintains it incrementally.
- **Changes plan:** no (sequencing within the plan's phases).

## D-016 (2026-11-09): When we fetch full article text
- **Context:** Phase 2 task 2 says to extract full text "for non-paywalled article URLs". §11.6 says to respect robots.txt and terms. The extracted text is sent to Claude in Phase 3.
- **Options:** (a) extract every linked page; (b) check robots.txt for our own user agent only; (c) per-source opt-in, plus robots.txt checks for our agent *and* Anthropic's crawler names, plus a hard-paywall host list.
- **Decision:** (c). A source opts in by listing `content_text` in `allowed_fields` (only `hn` and `sth` do). Each page is fetched only if its robots.txt allows `NewsDC`, `ClaudeBot` and `anthropic-ai` (RFC 9309: 4xx means no rules, 5xx or unreachable means disallow) and the host is not in `PAYWALLED_HOSTS`. Everything else is metadata only.
- **Why:** DCD, DCK, NYT and FT all disallow Anthropic's crawlers in robots.txt. Feeding their article bodies to Claude would ignore a stated opt-out even though our own user agent is technically allowed.
- **Trade-offs:** fewer items have full text, so classification relies on title plus summary for those items. Costs one robots.txt request per origin per run (cached).
- **Changes plan:** no (it is a stricter reading of §11.6).

## D-017 (2026-11-09): Source list changes after verification
- **The Register:** the plan's `data_centre` feed returns 404. The current section feed (`/on_prem/headlines.atom`) works, but robots.txt is `User-agent: *` / `Disallow: /`. Kept in YAML, **disabled**.
- **The Next Platform:** feed works, robots.txt is default-deny for unlisted agents. **Disabled**.
- **SemiAnalysis:** `semianalysis.com/feed/` is a stale archive (newest entry 2025-09). Use the newsletter feed `newsletter.semianalysis.com/feed` (Substack). Metadata only, because the newsletter is partly paywalled.
- **NYT, FT:** enabled with headline and description only. NYT's RSS terms allow "personal use in a news reader or as part of a non-commercial blog"; **the human must confirm that this assignment qualifies** (see SOURCE_REGISTER).
- **arXiv:** `export.arxiv.org/robots.txt` disallows all crawling, but the arXiv API Terms of Use explicitly permit API access at no more than one request every 3 s. We only call the API and never crawl abstract pages.
- **Changes plan:** yes, source list (recorded in CHANGELOG).

## D-018 (2026-11-09): Hacker News query strategy
- **Context:** Algolia does prefix and typo matching on unquoted terms, across title, URL and story text. A 365-day probe showed `PUE` matching 32,975 stories and `data center` 2,489, mostly noise.
- **Decision:** quoted phrase queries restricted to titles (`restrictSearchableAttributes=title`). `PUE` was dropped (0 title matches when quoted). Added `immersion cooling` and `power grid`, and shortened `SMR nuclear` to `SMR`. Pagination walks backwards with a `created_at_i <= cursor` filter instead of `page=`, which avoids Algolia's 1,000-hit cap. The cursor is the checkpoint.
- **Trade-offs:** misses stories that mention a term only in the URL or body. `nvidia` stays as the plan lists it, which brings consumer-GPU noise that the Phase 3 pre-filter must drop.
- **Changes plan:** minor (query list).

## D-019 (2026-11-09): Dedupe order, URL resolution and engagement ownership
- **Lookup order:** first this source's `external_id` in `item_sources`, then `url_hash` of the canonical original URL. Known items skip enrichment, so a re-run costs no extra fetches.
- **Resolution:** a new item whose source allows full text is fetched (redirects followed, with an SSRF check on every hop) before insert. Its canonical URL is the page's `rel=canonical` if that is on the same host, else the canonicalized resolved URL, else the canonicalized original. `original_url`, `resolved_url` and `canonical_url` are stored separately (§11.3). Metadata-only sources keep `resolved_url = NULL` and are not fetched just to resolve.
- **Engagement:** `items.points` and `items.comments_count` belong to the item's primary (first) source and only grow (`GREATEST`). Every source keeps its own numbers in `item_sources.source_engagement`. When one source reports the same URL twice (HN reposts), the observation with more points is kept.
- **Concurrency:** uniqueness is enforced by `UNIQUE(url_hash)` and `UNIQUE(source_id, item_id)` through `INSERT ... ON CONFLICT`, with one savepoint per item. Tested with three concurrent runs.
- **Changes plan:** no.

## D-020 (2026-11-09): Adapters yield dicts; the runner validates them as RawItem
- **Context:** Phase 2 says each source module "returns a list of RawItem".
- **Decision:** adapters are generators that yield pages of RawItem-shaped dicts. The runner validates each with `RawItem.model_validate`, so one malformed row is counted in `pipeline_runs.failed` and logged instead of aborting the page.
- **Changes plan:** minor (shape of the adapter return value).

## D-021 (2026-11-09): Run records, time window, caps and checkpoints
- One `pipeline_runs` row per source per run (`source_key` set): `succeeded`, `partial` (some rows rejected) or `failed` (the source raised; its error is stored on the run and on `sources.last_error`).
- Window: `--since-days` if given; else `last_success_at - 2 days` (re-reads recent items to refresh engagement); else the source's `backfill_window_days`.
- `sources.yaml` gained two optional fields: `queries` (required when an API source is enabled) and `max_items_per_run` (default 1000). A run stops at its cap and the next run resumes from the checkpoint. Each page commits together with its checkpoint.
- RSS uses conditional GET (`ETag` / `Last-Modified` in the checkpoint).
- **Changes plan:** no.

## D-022 (2026-11-09): No scheduled ingestion job yet
- **Context:** the worker could register `ingest_all` on an APScheduler interval now.
- **Decision:** not in Phase 2. §11.4 requires a database-backed job lifecycle (claims, leases, retries, single-scheduler guard), which Phase 3 builds. A bare APScheduler job now would be thrown away. Phase 2 ingestion runs through the CLI.
- **Changes plan:** no (sequencing).

## D-023 (2026-11-09): GitHub `published_at` is the repository creation date
- Stars are stored as `points`, `pushed_at` limits the search to active repos, and `created_at` is the publication date. "Published" should not move every time someone pushes.

## D-024 (2026-11-09): Classifier model, structured output and effort
- **Context:** Phase 3 asks for "tool use / structured output" with a strict schema, a model ID from env, and model IDs verified against official docs (§11.5).
- **Verified:** the Models API returned `claude-haiku-5-5` ("Claude Haiku 5.5") and `claude-sonnet-5-5` for this key. The pricing page (checked 2026-11-09) lists Haiku 5.5 at $0.10/MTok input, $0.125 cache write, $0.01 cache read and $0.50 output for prompts up to 100k tokens. The minimum cacheable prefix for Haiku 5.5 is 512 tokens; the classify prompt is about 3,500 tokens and was confirmed to cache (`cache_read_input_tokens = 3536` on the second call).
- **Options:** (a) forced `tool_choice` with a tool schema; (b) structured outputs (`output_config.format` with a JSON schema). Forced `tool_choice` returns a 400 on several current models (Opus 5.5, Sonnet 5.5, Fable 5.1), so (a) would tie the code to a model family.
- **Decision:** (b), with the category slugs and content types as enums in the schema, then Pydantic validation and one repair call. `CLASSIFIER_MODEL=claude-haiku-5-5` is set in the local `.env` only. Code and `.env.example` still default to empty (D-007). `CLASSIFIER_EFFORT=low` (classification does not benefit from deep reasoning; it is configurable and can be emptied for models without `effort`).
- **Trade-offs:** structured outputs guarantee parseable JSON but not every rule (score ranges, unknown categories are still checked by Pydantic). A Haiku-class model is cheaper but less nuanced than Sonnet; the eval (AI_EVALUATION.md) is the evidence it is good enough.
- **Changes plan:** minor (structured outputs instead of forced tool use; both are allowed by the plan's wording).

## D-025 (2026-11-09): Provider interface, retries and failure classes
- `app/ai/llm.py` defines `LLMClient` (one method, `complete_json`) and `LLMError(retryable, fatal)`. Pipeline code never sees vendor types.
- Transient errors (429, 5xx including 529, timeouts, connection errors) are retried by the Anthropic SDK (`max_retries=3`, exponential backoff, honours Retry-After). We don't add a second retry layer.
- What still fails is classified: auth/permission/unknown model = **fatal** (abort the run, the job goes to dead_letter); 400 or refusal = **permanent for that item** (status `failed`); transient = **retry later** (item stays `new`, `ai_attempts` + 1, `failed` after 3). Five transient failures in a row abort the run as "provider unavailable" (job retried with backoff). Invalid output twice = `failed`.
- Logged errors carry the exception type, status and the SDK's message only, never the prompt or article text.

## D-026 (2026-11-09): Durable jobs without an advisory scheduler lock
- **Context:** §11.4 asks for an atomic claim, leases, backoff, dead letters, manual retry, idempotent handlers, a single-scheduler guard and defined shutdown.
- **Decision:** a `jobs` table (migration 0002) with kinds `ingest_all` and `pipeline`. The single-scheduler guard is a **partial unique index** (`one active job per kind`), plus a "not enqueued within 0.9 × interval" check, so replicas' ticks no-op in the database. This is the "or equivalent" in §11.4 and needs no long-held lock connection. The pipeline itself additionally holds `pg_try_advisory_lock` so a CLI run and a worker run never overlap.
- Leases: 600 s, renewed by a heartbeat thread every 60 s. A lease that expires on the last attempt goes to dead_letter. Backoff: full jitter, 60 s base, 1 h cap, `max_attempts` 3.
- Shutdown: SIGTERM stops claiming; ingestion stops between sources and the pipeline between pages of 50 items; the job is released to `pending` without spending an attempt. Compose gives the worker `stop_grace_period: 60s`; past that, lease expiry recovers the job.
- Manual actions are CLI for now (`python -m app.jobs list|enqueue|retry|cancel`). Admin endpoints are Phase 8.
- **Changes plan:** no.

## D-027 (2026-11-09): Pipeline details
- **Prefilter:** word-bounded, case-insensitive match of category keywords plus a small general DC vocabulary (`app/pipeline/nodes.py`); score 0 rejects unless the source is DC-specific. DC-specific is a new optional `dc_specific: true` field in `sources.yaml` (set for `dcd` and `dck`).
- **Language:** no new dependency. Text is non-English only on positive evidence: more than 30% non-ASCII letters, or at least two function words of another Latin-script language (German, Spanish, French, Portuguese, Dutch) that outnumber the English ones. Such items are rejected unless the title has a DC keyword (plan: "skip non-English unless the title is clearly relevant"). The first version (English function-word ratio) wrongly rejected 283 terse English GitHub descriptions in the live run and was replaced (VERIFICATION_LOG, Phase 3).
- **Near-duplicates:** `title + summary` embedding, cosine > 0.92 with a `processed` item published within ±14 days (HNSW with `hnsw.iterative_scan = relaxed_order`, pgvector ≥ 0.8). The **already-processed item stays canonical**; the new one becomes `duplicate` with `duplicate_of`, the similarity and a reason string. Items running in parallel in the same run are also compared against each other in memory under a lock, so concurrent duplicates are caught. The plan allows "earlier or higher-quality"; we pick "first processed" and do not flip published items.
- **Embedding failures:** the item stays `processed` with `embedding` NULL and a `status_reason`; each run first embeds that backlog.
- **Audit trail:** `items.status_reason` says why an item has its status: the pre-filter or gate reason, the last LLM error (items left `new` or `failed`), or a pending embedding. AI rejections also keep the full annotation.
- **Idempotency:** `store` updates an item only `WHERE status = 'new'`, in the same transaction as the annotation upsert. A retried or overlapping run cannot write twice.
- **Spend limits:** `MAX_LLM_ITEMS_PER_RUN` and `DAILY_LLM_BUDGET_USD` (sum of today's `pipeline_runs.cost_usd_estimate`, persisted after every page). When either triggers, unclassified items stay `new` and `pipeline_runs.stop_reason` says why (for Admin in Phase 8).
- **Reprocess:** `python -m app.pipeline --reprocess-outdated` resets items whose annotation has another `prompt_version` to `new`. The Admin button that calls it is Phase 8.
- **Changes plan:** minor (`dc_specific` field in sources.yaml).

## D-028 (2026-11-09): Prompt v2 after the first evaluation
- **Context:** eval run 1 (`classify-v1`) had precision 15/15 and recall 15/20. All five misses were Hacker News title-only items with relevance 85–92 and quality 30–35, cut by the quality gate (40). The v1 prompt said only "a title-only item cannot score above 60", which the model read as "score title-only items low". Most HN items are title-only, so v1 would have rejected most real HN news.
- **Decision:** `classify-v2` rates title-only items by how specific the headline is (concrete factual headline 45–60, vague or clickbait below 40, never above 60). Run 2: precision 20/22, recall 20/20.
- **Caveat:** the same 40 items informed the change and measured it. There is no held-out set, so run 2 is optimistic. Both runs are recorded in AI_EVALUATION.md.
- **Changes plan:** no.

## D-029 (2026-11-09): Hybrid search details
- **Summary in full-text search (resolves D-013):** migration `0003` adds a generated `ai_annotations.summary_tsv` (summary, weight B) with a GIN index. Search matches `items.tsv @@ q OR ai_annotations.summary_tsv @@ q` and ranks by `ts_rank_cd(items.tsv || summary_tsv, q)`. Most Hacker News items are title-only, so without the summary their only searchable text is the headline. Tags are not indexed, because `array_to_string` is not IMMUTABLE and so can't go in a generated column.
- **Fusion:** keyword and semantic retrievers each return up to 100 candidates (same filters), merged with Reciprocal Rank Fusion (`Σ 1/(60 + rank)`; ties broken by id DESC). `total` is the size of the fused list, so pagination beyond about 200 hits isn't possible. That is enough for a discovery UI.
- **Similarity floor:** nearest-neighbour search always returns something, so a nonsense query got 100 "semantic" hits. Measured on the live corpus (VERIFICATION_LOG Phase 4): off-topic queries top out at 0.48–0.62 cosine, and on-topic queries keep dozens of hits above 0.6. `SEARCH_MIN_SIMILARITY=0.6` (env) drops the rest. It is specific to bge-small and this corpus, so re-measure if either changes.
- **Snippets:** `ts_headline` over summary → description → title, using private-use characters as match markers. The API HTML-escapes the text and then turns the markers into `<mark>`, so `snippet` contains no markup except `<mark>`.
- **Degraded mode:** if the query embedding fails, search runs keyword-only and the response says `mode: "keyword"` (§11.5).
- **Changes plan:** no (D-013 said Phase 4 would revisit this).

## D-030 (2026-11-09): Rate limiting with `limits`, not slowapi's middleware
- **Context:** the plan names `slowapi`. With FastAPI 0.162, `SlowAPIMiddleware` looks for the route by scanning `app.routes` for an `endpoint` attribute. Included routers are now wrapped in `_IncludedRouter` objects that have none, so slowapi found no handler and **exempted every request**: 62 requests in a row returned 200 in the live check.
- **Decision:** drop `slowapi` and use `limits` (the library slowapi is built on) in a small middleware: moving window, in-memory, keyed by client IP, `RATE_LIMIT_DEFAULT=60/minute`, health/ready exempt. It runs inside CORS so the browser can read a 429. `app.security.allow(client, limit, scope)` takes a per-route limit for `/ask` (Phase 6) and admin login (Phase 8).
- **Trade-offs:** counts are per process (a single uvicorn process in this deployment). Behind Caddy, uvicorn needs `--proxy-headers` so the key is the client IP and not the proxy's (Phase 10; RISKS R-017).
- **Changes plan:** minor (library choice, recorded in CHANGELOG).

## D-031 (2026-11-09): Phase 4 API contract choices
- **Scope:** Phase 4 creates `/items`, `/items/{id}`, `/items/{id}/related`, `/feeds/relevant`, `/topics`, `/topics/{slug}` and `/search`. Endpoints whose logic belongs to later phases are not stubbed: `/feeds/trending` and `/feeds/foryou` (Phase 5), `/ask` (6), `/stats` and `/trends` (7), `/export` and `/admin/*` (8). `sort=trending` on `/items` returns 422 until Phase 5 adds the trending score.
- **Pagination:** `page` (1–1000) and `page_size` (1–50, default 20) with `total` and `has_more`. Every ordering ends with `id DESC` (latest: `published_at DESC NULLS LAST, id DESC`), so pages don't skip or repeat while the data is unchanged. Offset pagination was chosen over cursors because the plan allows either and the UI needs page numbers and totals.
- **`/feeds/relevant`:** `relevance_score × quality_score DESC`, then newest first, as the Phase 4 table says. Phase 5 replaces it with `0.6·relevance + 0.4·quality` plus recency decay.
- **Filters:** `category` matches any of an item's categories, not only the primary one. `source` matches any source that found the item (`item_sources`). `from` is inclusive and `to` exclusive. A timestamp without an offset is taken as UTC. Slugs and keys are validated by format, so a well-formed unknown slug returns an empty list (`/topics/{slug}` returns 404).
- **Detail:** only `processed` items have a public detail page. Rejected, failed and duplicate items return 404 (§11.13). A near-duplicate appears under its canonical item's `also_covered_by`. `coverage` lists every `item_sources` row (§11.2). `url` is the original URL. `content_text` (full article text) is never returned (§11.6).
- **Related:** cosine similarity over the 50 nearest processed items, plus 0.1 per shared category, top 6. An item without an embedding gets `[]`.
- **Timestamps:** serialized as UTC with a `Z` suffix by the response schemas, whatever the session timezone. DB sessions also run with `timezone=UTC`. The local cluster defaulted to `Asia/Kolkata`, which is how this was found.
- **Errors:** every non-2xx response is `{"error": {"code", "message", "request_id"}}`. Codes: `validation_error` 422, `not_found` 404, `method_not_allowed` 405, `rate_limited` 429, `db_unavailable` 503 (SQLAlchemy `OperationalError`), `internal_error` 500 (no details leak). `X-Request-ID` is echoed if it is safe (`[A-Za-z0-9._-]{1,64}`) or generated, and is in every log line of the request.
- **Request bodies:** no Phase 4 endpoint accepts one. The body-size limit is added with the first POST endpoint (`/feeds/foryou`, Phase 5).
- **Headers:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `CSP default-src 'none'; frame-ancestors 'none'` on API responses. The Swagger UI page is exempt from the CSP, because it loads a CDN script. The frontend's CSP belongs to Caddy (Phase 10).
- **Changes plan:** no.
