# Phase Status

Status values: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `PASS`, `PASS WITH DEFERRED ITEMS`, `FAIL`.

| Phase | Status | Started | Completed | Commit | Acceptance checks | Human verification |
|---|---|---|---|---|---|---|
| 0 | BLOCKED | 2026-11-09 | n/a | Phase 0 commits on `main` (see `git log`) | Tests, lint, typecheck, build, and config validation: PASS. Health against real Postgres: PASS. `docker compose up --build`: **BLOCKED** (no Docker on the agent machine). CI on GitHub: **BLOCKED** (not pushed) | Pending |
| 1 | PASS WITH DEFERRED ITEMS | 2026-11-09 | 2026-11-09 | Phase 1 commits on `main` (see `git log`) | `alembic upgrade head` on a fresh DB: PASS. Seeds load 14 categories: PASS. `pytest`: PASS (54 incl. 12 DB integration tests). Ruff, mypy: PASS. Under `docker compose`: **BLOCKED** (no Docker). CI on GitHub: **BLOCKED** (not pushed). Deferred: redirect-resolution tests (Phase 2) | Pending |
| 2 | PASS WITH DEFERRED ITEMS | 2026-11-09 | 2026-11-09 | Phase 2 commit on `main` (see `git log`) | ≥1,500 raw items: PASS (3,887 unique after a 365-day backfill; per-source counts in VERIFICATION_LOG). Second run creates no duplicate rows: PASS (0 duplicate canonical URLs or source IDs; the 8 new rows were published between runs). Broken source isolated, error stored on the source row: PASS (live and tested). `pytest`: PASS (105). Ruff, mypy: PASS. Under `docker compose`: **BLOCKED** (no Docker). CI on GitHub: **BLOCKED** (not pushed). Deferred: "500+ after AI filtering" is measured in Phase 3; scheduled ingestion moves to Phase 3 (D-022) | Pending (incl. review of source terms, esp. NYT/FT) |
| 3 | PASS WITH DEFERRED ITEMS | 2026-11-09 | 2026-11-09 | Phase 3 commit on `main` (see `git log`) | ≥500 processed: PASS (**2,609** processed of 3,898 real items; counts per status, source, category and content type in VERIFICATION_LOG). Spot check of 20 processed + 20 rejected: PASS by the agent (20/20 processed correct; 17/20 rejections correct, 3 borderline). Eval results recorded: PASS (classify-v2: precision 20/22, recall 20/20, category 16/20; AI_EVALUATION.md). `pytest`: PASS (188). Ruff, mypy: PASS. Live worker run (scheduled ingest → pipeline job → SIGTERM): PASS. Under `docker compose`: **BLOCKED** (no Docker). CI on GitHub: **BLOCKED** (not pushed). Deferred: Admin endpoint for reprocess/dead-letter retry (Phase 8; CLI exists) | Pending: review of the 40 eval labels, own spot check, rotate the API key pasted in chat |
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
