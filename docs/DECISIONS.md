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
