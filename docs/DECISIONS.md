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
