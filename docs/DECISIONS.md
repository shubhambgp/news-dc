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
