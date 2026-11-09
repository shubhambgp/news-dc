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
