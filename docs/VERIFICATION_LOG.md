# Verification Log

Commands actually run and their actual results, including failures and fixes. Nothing here is invented.

## Phase 0 (2026-11-09)

Environment: Linux, Python 3.14 system (backend uses 3.12 via uv), Node 24.19.0, pnpm 11.22.0, PostgreSQL 18 on the host. **Docker isn't installed. uv isn't installed** (the agent used a session-only copy of uv 0.13.7 in a temporary venv).

### Automated: backend (`backend/`, clean `.venv`)
| Command | Result |
|---|---|
| `uv sync --frozen` | OK, installed from lockfile |
| `uv run ruff format --check .` | `7 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 6 source files` |
| `uv run pytest -q` | `3 passed` (health OK, health degraded + ready 503, `check_db` unreachable → False) |

Failures fixed along the way:
- First `ruff format --check` and `ruff check` failed: `app/main.py:24` was 101 chars (E501). Fixed by running `ruff format`. Re-run passed.
- pytest printed a `PytestDeprecationWarning` about the asyncio fixture loop scope. Fixed by setting `asyncio_default_fixture_loop_scope = "function"`.

### Automated: frontend (`frontend/`, clean `node_modules`)
| Command | Result |
|---|---|
| `pnpm install --frozen-lockfile` | OK |
| `pnpm lint --deny-warnings` (oxlint) | exit 0, no findings |
| `pnpm typecheck` (`tsc -b`, all configs `noEmit`) | exit 0 |
| `pnpm build` | OK: JS 293.06 kB (94.40 kB gzip), CSS 23.18 kB |

Fix along the way: the first `pnpm lint` reported 2 `react/only-export-components` warnings in generated shadcn files (`badge.tsx`, `button.tsx`). Fixed by turning that rule off for `src/components/ui/**` only.

### Automated: config validation
| Command | Result |
|---|---|
| `actionlint .github/workflows/ci.yml` (actionlint-py) | no errors |
| `check-jsonschema --builtin-schema vendor.github-workflows .github/workflows/ci.yml` | `ok -- validation done` |
| `check-jsonschema --schemafile <compose-spec.json from compose-spec/compose-spec@main> docker-compose.yml` | `ok -- validation done` |

This is **schema validation only**. It doesn't prove the stack runs.

### Runtime: backend against real Postgres (no Docker)
Throwaway cluster: `initdb` in a temp dir, `pg_ctl` on 127.0.0.1:55432, `createdb newsdc`.
- First `pg_ctl start` failed: `could not create Unix-domain socket` (temp path longer than the socket path limit). Fixed with `-c unix_socket_directories=''` (TCP only).

| Check | Result |
|---|---|
| `curl localhost:8765/api/v1/health` (DB up) | `{"status":"ok","db":"ok","version":"0.1.0"}` HTTP 200 |
| `curl localhost:8765/api/v1/ready` (DB up) | same body, HTTP 200 |
| Stop Postgres, then `/health` | `{"status":"degraded","db":"error",...}` HTTP 200 |
| Stop Postgres, then `/ready` | same body, HTTP 503 |
| `curl /api/v1/docs` | HTTP 200 |
| `curl -H 'Origin: http://localhost:5173' /api/v1/health` | `access-control-allow-origin: http://localhost:5173` |
| `timeout 5 uv run python -m app.worker` | JSON logs `worker started` (`jobs: 0`) and `Scheduler started`. Kept running until timeout (exit 124, expected) |
| Server logs | JSON lines (uvicorn messages routed through the JSON formatter) |

### Runtime: frontend + backend + Postgres (no Docker)
Backend on :8000 (pointed at the throwaway DB), `VITE_API_BASE_URL=http://localhost:8000 vite --port 5173`.
- `curl localhost:5173/` serves `<title>NewsDC</title>`.
- Headless Chrome screenshot at 800×500 (light): the page shows "System status" with **API ok · DB ok · v0.1.0**.
- Headless Chrome at 375×500 with the system dark preference: dark theme applied, same status, no horizontal overflow.

These screenshots were checked by the agent. **Human visual check: pending.**

### BLOCKED
| Acceptance check | Status | Reason | Command for the human to run |
|---|---|---|---|
| `docker compose up --build` starts everything; `curl localhost:8000/api/v1/health` reports db ok; `localhost:5173` shows status | **BLOCKED** | Docker isn't installed on the agent's machine | `cp .env.example .env && docker compose up --build`, then `curl localhost:8000/api/v1/health` and open http://localhost:5173 |
| CI runs green on GitHub | **BLOCKED** (not pushed) | The agent doesn't push without approval | `git push origin main`, then check the Actions tab |

## Phase 1 (2026-11-09)

Environment: same machine as Phase 0. **No Docker, no sudo.** For a real pgvector database the agent ran `apt-get download postgresql-18-pgvector`, extracted it with `dpkg -x` into a session scratch directory (pgvector 0.8.1), and started a throwaway PostgreSQL 18.6 cluster (`initdb`, port 55433, TCP only) using PG18's `extension_control_path` and `dynamic_library_path` to load it. In the copied `vector.control`, `module_pathname` was changed from `$libdir/vector` to `vector` so `dynamic_library_path` applies. Check: `CREATE EXTENSION vector; SELECT '[1,2]'::vector` returned `[1,2]`.

### Acceptance: migrations and seeds
| Command | Result |
|---|---|
| `alembic upgrade head` (fresh `newsdc` DB) | `Running upgrade -> 0001, initial schema ...` |
| `alembic check` | `No new upgrade operations detected.` |
| `python -m app.seed` | JSON log `seeded config`, `categories: 14`, `sources: 3` |
| `psql -c "select count(*) from categories"` | `14` |
| Same, repeated after dropping/recreating the DB with the clean-venv toolchain | `upgrade -> 0001`, then `"categories": 14, "sources": 3` |

### Automated: backend (clean `.venv`, `uv sync --frozen`)
| Command | Result |
|---|---|
| `uv lock --check` | `Resolved 112 packages` (lockfile unchanged) |
| `uv run ruff format --check .` | `16 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 10 source files` |
| `TEST_DATABASE_URL=... uv run pytest -q` | `54 passed` (31 URL, 8 config, 12 DB integration, 3 health) |
| `pytest -q -rs` without `TEST_DATABASE_URL` | `42 passed, 12 skipped` (DB tests skip with a reason) |

Failures fixed along the way:
- First `ruff check` after generating migration 0001: 4× E501 in autogenerated DDL strings. Fixed with a per-file ignore for `alembic/versions/*`. Same for long inline SQL in `tests/test_db.py` (5× E501, plus 1 import-order fix by `ruff --fix`).
- First draft of `canonicalize_url()` used `parse_qsl`/`urlencode`, which re-encodes values (`%20` → `+`, `?a` → `?a=`). Replaced with sorting raw `k=v` segments before the tests were run. The test `q=liquid%20cooling` pins this.

### Runtime: startup seeding
| Check | Result |
|---|---|
| `uvicorn app.main:app` against an **unmigrated** DB | JSON log `seeding skipped: database error` (`ProgrammingError`), then `Application startup complete` |
| `alembic upgrade head`, then `uvicorn` again | JSON log `seeded config` (`categories: 14`, `sources: 3`); `curl /api/v1/ready` → `{"status":"ok","db":"ok","version":"0.1.0"}` |

### Config validation
| Command | Result |
|---|---|
| `actionlint .github/workflows/ci.yml` | no errors |
| `check-jsonschema --builtin-schema vendor.github-workflows .github/workflows/ci.yml` | `ok -- validation done` |
| `check-jsonschema --schemafile compose-spec.json docker-compose.yml` (schema from compose-spec `main`) | `ok -- validation done` |

### Not verified (BLOCKED)
- `docker compose up --build` with the new migrate-then-serve command and the `./config` mount: no Docker on this machine. Manual command: `docker compose up --build`, then `docker compose exec db psql -U newsdc -c "select count(*) from categories"` should print 14.
- CI on GitHub, including the integration tests on `pgvector/pgvector:pg16`: not pushed.

## Phase 2 (2026-11-09)

Environment: same machine, no Docker, no sudo. A fresh throwaway PostgreSQL 18.6 + pgvector 0.8.1 cluster was started in the session scratch directory, the same way as in Phase 1 (`initdb`, port 55433, TCP only, `unix_socket_directories=''` because the scratch path exceeds the 107-byte socket limit). `CREATE EXTENSION vector; SELECT '[1,2]'::vector` returned `[1,2]`. Databases: `newsdc` (live ingestion) and `newsdc_test` (pytest; its schema gets dropped). The backend venv was the existing `backend/.venv`; uv 0.13.7 came from the Phase 0 session copy.

### Source verification (all on 2026-11-09)
| Check | Result |
|---|---|
| `curl -L` each candidate feed/API with a `NewsDC/1.0` UA | 200: DCD `/en/rss/`, DCK `/rss.xml`, STH `/feed/`, `newsletter.semianalysis.com/feed`, `semianalysis.com/feed/`, NYT Technology, FT `technology?format=rss`, HN Algolia, arXiv, GitHub. **404: `theregister.com/data_centre/headlines.atom`** (and `.rss`). 200: `theregister.com/on_prem/headlines.atom` |
| feedparser entry counts | DCD 20, DCK 50, STH 6, SemiAnalysis newsletter 20, semianalysis.com 10 (newest 2025-09-16, a stale archive), NYT 26, FT 25 |
| `urllib.robotparser`, UA `NewsDC`, feed and article paths | DCD ✓, DCK ✓, SemiAnalysis ✓, NYT ✓, FT ✓ (crawl-delay 1). **Register ✗, Next Platform ✗** (`User-agent: *` / `Disallow: /`). `export.arxiv.org` ✗ (`Disallow: /`; API use is governed by the API ToU instead) |
| robots.txt AI-crawler entries | DCD, DCK, NYT and FT disallow `ClaudeBot`/`anthropic-ai` (with GPTBot, CCBot etc.) |
| Terms pages (HTTP 200) | hn.algolia.com/api, info.arxiv.org/help/api/tou.html, GitHub ToS, DCD terms, informatechtarget.com terms (DCK), STH data/privacy policy (no ToS page found), substack.com/tos, nytimes.com/rss, help.ft.com terms. NYT RSS text: "personal use in a news reader or as part of a non-commercial blog" |
| arXiv ToU text | "no more than one request every three seconds, and limit requests to a single connection" |
| GitHub search docs | "For unauthenticated requests, the rate limit allows you to make up to 10 requests per minute"; 30 with auth |
| HN query sizing (365 days, `nbHits`) | unquoted `PUE` 32,975; quoted+title `"PUE"` 0. `data center` 2,489 unquoted vs 753 quoted+title. `"nvidia"` title 1,590. `"datacenter"` 137, `"AI infrastructure"` 127, `"liquid cooling"` 5 |
| arXiv query sizing | `abs:"data center" AND (cat:cs.DC OR cat:cs.AR OR cat:cs.NI OR cat:eess.SY)`: 1,615 total, 100 papers between 2026-08-31 and 2026-11-06. One probe was answered `429 Rate exceeded` after a quick burst, so retries are needed |

### Automated checks (final state)
| Command | Result |
|---|---|
| `uv lock --check` | `Resolved 112 packages` (no dependency changes) |
| `uv run ruff format --check .` | `26 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 16 source files` |
| `TEST_DATABASE_URL=...newsdc_test uv run pytest -q` | `105 passed` (31 URL, 31 ingest common, 9 adapters, 9 ingest DB integration, 12 DB, 10 config, 3 health) |
| `uv run pytest -q -rs` (no DB) | `84 passed, 21 skipped` |
| Secret grep over `backend/app`, `backend/tests`, `config` | no matches (only the fake `test-token` in a test) |

Failures along the way (all fixed):
- `mypy`: `RobotFileParser` has no `allow_all`/`disallow_all` attributes (undocumented). Replaced with `parse([])` / `parse(["User-agent: *", "Disallow: /"])`. Two typing fixes in the runner.
- `test_ingest_common`: three failures because the test's `Sleeps` helper is a `list`. An empty one is falsy, so `sleep or time.sleep` silently used real sleep (the run took 15.9 s). Changed to `time.sleep if sleep is None else sleep` (0.37 s afterwards).
- `test_ingest_db`: two wrong expectations in my own tests (the invalid fixture row is counted as failed on every run; a URL-encoded query string). Tests fixed, no code change.

### Live ingestion: bugs found and fixed
| Run | What happened | Fix |
|---|---|---|
| `python -m app.ingest --source dcd`, twice | 1st: `fetched 20, new 20`. 2nd: `status failed`, `last_error = KeyError: 'location'` | The feed answered `304`. httpx 0.28's `is_redirect` is true for every 3xx. Switched to `has_redirect_location`; regression test `test_not_modified_is_returned_not_followed`. Re-run: `succeeded`, `fetched 0` (304) |
| Backfill run 1 (`--all --since-days 365`, 18:47–19:00 IST) | hn `succeeded` (2,869 fetched / 2,481 new). **arxiv and github `failed`**: `psycopg.errors.IdleInTransactionSessionTimeout ... [SQL: SAVEPOINT sa_savepoint_1]`. The RSS sources after them still ran and succeeded. CLI exit code `1` | The page's read transaction stayed open while about 100 new items were enriched (HN lookups throttled to 60/min, so about 100 s, past the 60 s idle-in-transaction limit). The runner now commits before enrichment. Regression test `test_no_transaction_is_held_open_during_enrichment` (checks `pg_stat_activity`): **fails without the fix (`[1] == [0]`), passes with it**. Run 1 also showed the failed run reporting `fetched: 100` for a rolled-back page, so failed runs now report only committed pages (test `test_failure_mid_run_keeps_committed_pages_and_cursor`) |

Backfill run 1 used the code before those two fixes and the httpx log-level change. The adapter, dedupe and upsert logic was otherwise identical.

### Acceptance 1: at least 1,500 raw items (365-day backfill)
Backfill run 1 plus the arXiv and GitHub re-runs with the fixed code (`--source arxiv --since-days 365`: `fetched 510, new 499, duplicates 11`; `--source github --since-days 365`: `fetched 819, new 759, duplicates 60`; both `succeeded`):

| Source | Items first found by this source (`is_primary`) | Items this source observed (incl. shared) |
|---|---|---|
| hn | 2,481 | 2,484 |
| arxiv | 499 | 502 |
| github | 759 | 759 |
| dcd | 21 | 21 |
| dck | 50 | 50 |
| sth | 6 | 6 |
| semianalysis | 20 | 20 |
| nyt_tech | 26 | 26 |
| ft_tech | 25 | 25 |
| **Total unique items** | **3,887** | `item_sources` rows: 3,893 |

- **3,887 unique items ≥ 1,500: PASS.** All have `status = 'new'`; no synthetic records.
- 6 items were found by more than one source (provenance attached, not duplicated). 917 items have extracted full text (HN-linked pages and STH, robots permitting), 939 have a resolved URL, and 42 non-HN items link to a matching HN discussion.
- Whether **500+ remain after AI filtering** can only be measured in Phase 3. HN volume is dominated by `"nvidia"` titles, many of them off-topic (D-018).

### Acceptance 2: running ingestion twice creates zero duplicate rows
Second full run, `python -m app.ingest --all --since-days 365` (same window), exit code `0`:

| Source | fetched | new | duplicates | failed | status |
|---|---|---|---|---|---|
| hn | 2,870 | 1 | 2,869 | 0 | succeeded |
| arxiv | 510 | 0 | 510 | 0 | succeeded |
| github | 820 | 1 | 819 | 0 | succeeded |
| dcd | 20 | 5 | 15 | 0 | succeeded |
| dck | 50 | 0 | 50 | 0 | succeeded |
| sth | 0 (304) | 0 | 0 | 0 | succeeded |
| semianalysis | 0 (304) | 0 | 0 | 0 | succeeded |
| nyt_tech | 26 | 0 | 26 | 0 | succeeded |
| ft_tech | 25 | 1 | 24 | 0 | succeeded |

- Items 3,887 → 3,895 and `item_sources` 3,893 → 3,901. The 8 new rows were all **published after their source's previous run** (DCD's previous run started 13:30 UTC; its 5 new stories are dated 13:33–13:46 UTC; the HN, FT and GitHub items are dated 13:43–13:50 UTC), so they are new content, not duplicates.
- Duplicate checks after the second run: canonical URLs appearing more than once **0**; `(source_id, external_id)` pairs appearing more than once **0**. Engagement on known items was refreshed in place.
- **PASS.** Also covered by `test_running_twice_creates_no_duplicate_rows` and `test_concurrent_runs_do_not_duplicate` (three simultaneous runs).

### Acceptance 3: one broken source doesn't stop the others
- **Live evidence (unplanned):** in backfill run 1, arxiv and github failed. dcd, dck, sth, semianalysis, nyt_tech and ft_tech still ran and succeeded. The error was stored on the source row (`sources.last_status = 'error'`, `last_error = 'InternalError: (psycopg.errors.IdleInTransactionSessionTimeout) ...'`) and on the `pipeline_runs` row (`status failed`). It was logged as JSON `ingest failed` with the traceback and `source_key`.
- **Automated:** `test_one_broken_source_does_not_stop_the_others` (DCD answers 500 after retries; DCK still ingests; DCD's row has `last_status = error` and `HTTP 500` in `last_error`).
- **PASS.**

### Not verified (BLOCKED)
- Ingestion inside `docker compose` (`docker compose run --rm worker python -m app.ingest --all --since-days 365`): no Docker on this machine.
- CI on GitHub: not pushed.
