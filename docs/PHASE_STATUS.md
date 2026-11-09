# Phase Status

Status values: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `PASS`, `PASS WITH DEFERRED ITEMS`, `FAIL`.

| Phase | Status | Started | Completed | Commit | Acceptance checks | Human verification |
|---|---|---|---|---|---|---|
| 0 | BLOCKED | 2026-11-09 | n/a | Phase 0 commits on `main` (see `git log`) | Tests, lint, typecheck, build, and config validation: PASS. Health against real Postgres: PASS. `docker compose up --build`: **BLOCKED** (no Docker on the agent machine). CI on GitHub: **BLOCKED** (not pushed) | Pending |
| 1 | PASS WITH DEFERRED ITEMS | 2026-11-09 | 2026-11-09 | Phase 1 commits on `main` (see `git log`) | `alembic upgrade head` on a fresh DB: PASS. Seeds load 14 categories: PASS. `pytest`: PASS (54 incl. 12 DB integration tests). Ruff, mypy: PASS. Under `docker compose`: **BLOCKED** (no Docker). CI on GitHub: **BLOCKED** (not pushed). Deferred: redirect-resolution tests (Phase 2) | Pending |
| 2 | PASS WITH DEFERRED ITEMS | 2026-11-09 | 2026-11-09 | Phase 2 commit on `main` (see `git log`) | ≥1,500 raw items: PASS (3,887 unique after a 365-day backfill; per-source counts in VERIFICATION_LOG). Second run creates no duplicate rows: PASS (0 duplicate canonical URLs or source IDs; the 8 new rows were published between runs). Broken source isolated, error stored on the source row: PASS (live and tested). `pytest`: PASS (105). Ruff, mypy: PASS. Under `docker compose`: **BLOCKED** (no Docker). CI on GitHub: **BLOCKED** (not pushed). Deferred: "500+ after AI filtering" is measured in Phase 3; scheduled ingestion moves to Phase 3 (D-022) | Pending (incl. review of source terms, esp. NYT/FT) |
| 3 | NOT STARTED | | | | | |
| 4 | NOT STARTED | | | | | |
| 5 | NOT STARTED | | | | | |
| 6 | NOT STARTED | | | | | |
| 7 | NOT STARTED | | | | | |
| 8 | NOT STARTED | | | | | |
| 9A | NOT STARTED | | | | | |
| 9B | NOT STARTED | | | | | |
| 9C | NOT STARTED | | | | | |
| 9D | NOT STARTED | | | | | |
| 9E | NOT STARTED | | | | | |
| 10 | NOT STARTED | | | | | |
| 11 | NOT STARTED | | | | | |

Phase 1 and 2 local verification used PostgreSQL 18.6 + pgvector 0.8.1 (Ubuntu packages), not the `pgvector/pgvector:pg16` image. CI runs the same tests on the pg16 image.

Phase 0 becomes `PASS` once the human runs `docker compose up --build` successfully and CI is green. Record the result in `VERIFICATION_LOG.md`.
