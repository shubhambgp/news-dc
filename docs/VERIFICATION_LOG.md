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

## Phase 3 (2026-11-09)

Environment: same machine and same throwaway PostgreSQL 18.6 + pgvector 0.8.1 cluster as Phase 2 (port 55433; `newsdc` holds the live Phase 2 data, `newsdc_test` is for pytest). No Docker. `.env` (gitignored, mode 600) holds the human-supplied `ANTHROPIC_API_KEY`, `CLASSIFIER_MODEL=claude-haiku-5-5` and the Haiku 5.5 prices.

### Provider checks (live)
| Check | Result |
|---|---|
| `client.models.retrieve("claude-haiku-5-5")`, `("claude-sonnet-5-5")` | both `OK` ("Claude Haiku 5.5", "Claude Sonnet 5.5"), `max_tokens` 128000 |
| Pricing page (platform.claude.com/docs/en/about-claude/pricing) | Haiku 5.5, prompts ≤ 100k tokens: $0.10 input, $0.125 5-min cache write, $0.01 cache read, $0.50 output per MTok |
| Two classify calls on one hand-written item, then a third raw call | `tokens_in 3672, tokens_out 386, cost 0.000649` then `0.000237`; third call `cache read 3536 write 0 in 136`: **prompt caching works**. Output was valid and on-topic (relevance 95, `power-energy`, `investment`) |
| fastembed `BAAI/bge-small-en-v1.5` | downloaded (about 17 s), 384 dims, unit norm; cosine 0.80 for two cooling sentences, 0.43 vs an unrelated sentence |

### Automated checks (final state)
| Command | Result |
|---|---|
| `uv lock --check` | `Resolved 112 packages` (no dependency changes) |
| `uv run ruff format --check .` | `42 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 25 source files` |
| `TEST_DATABASE_URL=...newsdc_test uv run pytest -q` | `188 passed` (new: 50 pipeline unit, 14 pipeline DB, 18 jobs/worker DB, 1 ingest shutdown) |
| `uv run pytest -q` (no DB) | `134 passed, 54 skipped` |
| No paid calls in tests | autouse fixture replaces `Messages.create` with an AssertionError; tests inject `FakeLLM` |

Failures along the way (all fixed): migration downgrade used the full constraint name, which the naming convention prefixed again (`ck_pipeline_runs_ck_pipeline_runs_kind_valid`); mypy on the SDK's typed params (`httpx2.Timeout`, TypedDict request params); ruff B008 in a test; the first English heuristic flagged a German test sentence because it contains "in".

### Migration on the live DB
`uv run alembic upgrade head`: `Running upgrade 0001 -> 0002`. `python -m app.seed`: 14 categories, 11 sources; `dc_specific` true for `dcd`, `dck`. After the column rename (below), the live DB was aligned by hand with `ALTER TABLE items RENAME COLUMN processing_error TO status_reason`, which is what the final 0002 creates (the test DB is rebuilt from the migration on every run).

### Evaluation
Two runs of `uv run python scripts/eval_classifier.py` (full output summarised in AI_EVALUATION.md):
- `classify-v1`: TP 15, FN 5, FP 0, TN 20 → precision 15/15, recall 15/20; category strict 16/20, lenient 18/20; $0.0110.
- `classify-v2`: TP 20, FN 0, FP 2, TN 18 → precision 20/22, recall 20/20; category strict 16/20, lenient 18/20; $0.0116.

### Acceptance 1: ≥ 500 items with `status = processed`
Run 29: `python -m app.pipeline --max-llm-items 4000` on the full backlog (3,895 items, all `new`), exit code 0:
```
"run_id": 29, "status": "succeeded",
"counts": {"processed": 2415, "rejected_ai": 1093, "rejected_prefilter": 310, "duplicate": 77},
"cost_usd": 1.063929, "stop_reason": null, "error": null
```
34 min 42 s, no ERROR or WARNING log lines.

**Bug found in the live data:** 289 of the 310 pre-filter rejections said "non-English". 283 of those were GitHub repos with terse English descriptions (e.g. `xukelvin24665-glitch/gridweave` "Deadline-safe co-scheduling of AI compute, renewable power, and battery storage"). The `owner/repo` title plus few English function words fell under the 15% ratio. Fix: non-English now needs positive evidence (mostly non-Latin letters, or ≥ 2 function words of another Latin-script language outnumbering English ones). Regression test `test_prefilter_passes_terse_english_repo_descriptions` uses the real strings; replayed against the old function it **fails 2 of 2**, and passes with the fix. The pre-filter reasons had also not been stored; that was fixed (`status_reason`) and backfilled for run 29 (deterministic recomputation; AI reasons copied from `ai_annotations.reject_reason`).

The 289 items were reset to `new` and run 30 processed them, exit code 0:
```
"run_id": 30, "status": "succeeded",
"counts": {"rejected_prefilter": 31, "rejected_ai": 65, "processed": 192, "duplicate": 1},
"cost_usd": 0.064484
```
The 27 items still rejected as non-English were checked one by one: all are Chinese, Korean, Japanese, Russian, Spanish, French or Portuguese descriptions.

**Final counts by status (3,895 unique items):**

| Status | Items |
|---|---|
| processed | **2,607** |
| rejected_ai | 1,158 |
| duplicate | 78 |
| rejected_prefilter | 52 (27 non-English, 25 no DC keywords) |
| failed | 0 |
| new | 0 |

**By source (primary source):**

| Source | Total | processed | rejected_ai | rejected_prefilter | duplicate |
|---|---|---|---|---|---|
| hn | 2,482 | 1,502 | 906 | 0 | 74 |
| github | 760 | 545 | 185 | 27 | 3 |
| arxiv | 499 | 462 | 36 | 0 | 1 |
| dck | 50 | 48 | 2 | 0 | 0 |
| nyt_tech | 26 | 7 | 14 | 5 | 0 |
| dcd | 26 | 19 | 7 | 0 | 0 |
| ft_tech | 26 | 6 | 6 | 14 | 0 |
| semianalysis | 20 | 13 | 1 | 6 | 0 |
| sth | 6 | 5 | 1 | 0 | 0 |

**Processed by primary category:** ai-compute-gpus 640, optimization 306, power-energy 273, site-selection 217, networking 200, economics-finance 187, regulation 186, dc-infrastructure 153, sustainability 98, hyperscaler-investments 98, emerging-tech 86, cooling 63, ai-agentic 55, security 45 (all 14 used).
**Processed by content type:** news 1,032, engineering 709, research 572, investment 294.
**Annotations:** 3,843, all `classify-v2`; $1.128 total; 15.70M input / 1.62M output tokens; mean latency 2,712 ms; 0 repair retries. Every processed item has an embedding (0 pending).

- **2,607 ≥ 500: PASS.** All records are real ingested items; nothing synthetic.

### Acceptance 2: spot check, 20 random processed and 20 random rejected
`setseed(0.7)`, `ORDER BY random() LIMIT 20` per group. Verdicts are the **agent's**; human spot check pending.

Processed (20/20 judged correct to publish):

| Item | Source | Title | Rel/Qual | Category | Agent verdict |
|---|---|---|---|---|---|
| 654 | hn | xAI built an illegal power plant to power its data center | 92/85 | power-energy | correct; summary facts (Earthjustice, NAACP) are in the extracted text |
| 642 | hn | Data center drains 30M gals of water — until residents complained | 85/45 | sustainability | correct |
| 3294 | arxiv | A Network Arena for Benchmarking AI Agents on Network Troubleshooting | 72/78 | ai-agentic | correct (networking also fits) |
| 3009 | arxiv | Space AI Infrastructure: Where the Edge Meets the Orbital Cloud | 70/70 | emerging-tech | correct |
| 179 | hn | HSBC Seeks to Hedge Data Center Debt with Credit Risk Insurance | 85/50 | economics-finance | correct; title-only, summary says no further text |
| 3014 | arxiv | Capturing Electrical Windows Through Reconfigurable Optical Networks | 88/78 | optimization | correct |
| 3960 | github | Physics-Informed-Cooling-for-Computing-Charging-Hubs | 88/50 | cooling | correct |
| 2870 | hn | Nvidia says its GPUs are a 'generation ahead' of Google's AI chips | 75/50 | ai-compute-gpus | acceptable (indirect) |
| 2812 | hn | Nvidia can sell H200 AI chips to China, Donald Trump says | 75/50 | ai-compute-gpus | acceptable (export policy; regulation also fits) |
| 364 | hn | Data Center Foes' Newest Tack: Sue Locals over Approval Process | 85/50 | site-selection | correct |
| 818 | hn | CoreWeave Hid Data Center Delays, Investors Say | 72/55 | hyperscaler-investments | correct; "class action" is in the extracted text |
| 2594 | hn | Nvidia's Moat Is Leaking: The Rise of High-Bandwidth CPUs | 72/40 | ai-compute-gpus | acceptable, borderline quality |
| 2794 | hn | China government-approved AI hw suppliers: Cambricon and Huawei in | 72/50 | ai-compute-gpus | correct |
| 3342 | arxiv | A Survey on AI Datacenter Hardware Architecture | 88/78 | ai-compute-gpus | correct |
| 220 | hn | Drones Hit Third Yandex Data Center Disrupting over 80 Services | 85/70 | security | correct; "Vladimir" is in the extracted text |
| 3187 | arxiv | The Anatomy of Silent Data Corruption: GPU Error Pattern Study | 78/82 | ai-compute-gpus | correct |
| 3771 | github | ndom91/ai-infra-monitoring | 62/45 | economics-finance | correct |
| 658 | hn | OpenAI-Oracle data center construction proceeds despite Michigan vote | 95/82 | site-selection | correct; "$16 billion", "21 million", "Saline" are in the extracted text |
| 2815 | hn | Trump Clears Sale of More Powerful Nvidia A.I. Chips to China | 65/50 | regulation | correct |
| 41 | dck | Rethinking the Blind-Mate Connection | 85/50 | cooling | correct |

Rejected (17/20 judged correct; 3 borderline):

| Item | Source | Title | Rel/Qual | Reason stored | Agent verdict |
|---|---|---|---|---|---|
| 939 | hn | John Carmack on why he would push back against anti-datacenter efforts | 55/25 | quality 25 < 40 | **borderline**: on topic, thin title |
| 2415 | hn | NVIDIA Nemotron 3 Super | 55/30 | quality 30 < 40 | correct |
| 1722 | hn | Nvidia DLSS 5 Neural Rendering Now Works on AMD Radeon GPUs | 10/35 | consumer gaming graphics mod | correct |
| 2844 | hn | Nvidia announces new open AI models for autonomous driving research | 25/40 | autonomous driving tooling | correct |
| 2727 | hn | Nvidia Bought the Bouncer | 40/25 | vague headline | correct |
| 2107 | hn | Nvidia and Microsoft Reinvent Windows PCs for the Age of Personal AI | 18/55 | consumer PCs | correct |
| 2647 | hn | Building voice agents with Nvidia open models | 35/62 | application tutorial | correct |
| 964 | hn | Is It Impossible to Cool a Datacenter in Space? (Scott Manley) [video] | 72/35 | quality 35 < 40 | **borderline**: relevant topic, video with title only |
| 2666 | hn | GPU Memory Allocation Bugs with Nvidia on Linux and Wayland | 10/45 | consumer desktop Linux | correct |
| 1668 | hn | Run QWEN3.8 27B on 16gb Nvidia GPUs | 30/25 | consumer local model | correct |
| 2636 | hn | Jensen Huang says robots could be 'AI immigrants' | 20/35 | robotics commentary | correct |
| 3785 | github | akirakubota-dev/akirakubota.com | 25/25 | personal portfolio | correct |
| 2393 | hn | Hands-On with DLSS 5 [video] | 15/15 | consumer gaming | correct |
| 3385 | arxiv | When Is Availability-Aware Training Worth It? | 40/68 | satellite training, indirect | correct |
| 4203 | github | aorus-waterforce-linux | 30/40 | consumer AIO cooler tool | correct |
| 1261 | hn | You Had Me at "Hello": A Chinese-Language Framework Targeting AI Infrastructure | 45/62 | relevance 45 < 55 | **borderline**: security research on AI infrastructure |
| 2378 | hn | New Nvidia DLSS Tech Gives Characters AI Slop Faces | 35/55 | consumer gaming | correct |
| 4209 | github | omarchy-aeolus | 15/35 | consumer fan control | correct |
| 2258 | hn | Nvidia Ising – Open AI Models for Quantum Computing | 45/62 | no facility angle | correct |
| 1646 | hn | Owed a billion dollars in Nvidia stock | 20/40 | personal essay | correct |

Observations: title-only HN summaries state that no further text was available instead of guessing (R-014). The borderline rejections sit just under the relevance or quality thresholds, which are configurable. The pre-filter's earlier sample showed two SemiAnalysis posts (Huawei-DeepSeek, DRAM/SSD offloading) rejected for having no keyword; arguably relevant, noted as a pre-filter trade-off.

- **PASS (agent spot check recorded); human spot check pending.**

### Acceptance 3: evaluation results recorded
- AI_EVALUATION.md and AI_CONFIG.md hold both runs with denominators and limitations. **PASS**; the human review of the 40 labels is pending.

### Worker end to end (live DB, real sources and LLM)
`uv run python -m app.worker`, started 20:32:46 IST:
- APScheduler enqueued job 1 `ingest_all` at start ("scheduled ingest"). The worker claimed it and ran all 9 enabled sources (pipeline_runs 31–39, all `succeeded`: hn 34 fetched / 2 new, github 94 / 0, dcd 18 / 1, ft_tech 21 / 0, and so on; arXiv 0). The job finished `succeeded` and queued job 2 `pipeline` with the same trigger.
- Job 2 ran the pipeline (run 40, `succeeded`): 3 new items → 2 processed, 1 duplicate. Job 2 `succeeded`, attempt 1.
- SIGTERM to the idle worker at 20:47:40: log shows `worker stopped` and `Scheduler has been shut down` in the same second; exit without error. 0 ERROR lines in the worker log (one INFO `extraction fetch failed`, an ignored full-text fetch).
- My watcher script meant to send SIGTERM automatically had a shell quoting bug (`-c: command not found`), so the worker idled about 14 minutes after its jobs and **SIGTERM was sent by hand**. Shutdown **during** a running job (release to `pending`) was not exercised live; it is covered by `test_shutdown_during_ingest_releases_the_job` and `test_shutdown_stops_between_pages`.

**Final counts after the worker run:** processed **2,609**, rejected_ai 1,158, duplicate 79, rejected_prefilter 52 (3,898 unique items).

### Not verified (BLOCKED / pending)
- Worker and pipeline inside `docker compose` (incl. the `models` volume, `stop_grace_period`): no Docker on this machine (R-001).
- CI on GitHub: not pushed.
- Human review of the 40 eval labels and a human spot check of processed and rejected items: pending.

## Phase 4 (2026-11-09)

Environment: same machine and the same throwaway PostgreSQL 18.6 + pgvector 0.8.1 cluster as Phase 3 (port 55433). `newsdc` holds the live data (2,609 processed of 3,898 items, all embedded); `newsdc_test` is for pytest. No Docker. No LLM calls in this phase.

### Migration on the live DB
`uv run alembic upgrade head`: `Running upgrade 0002 -> 0003, full-text index over the AI summary for hybrid search`. The pytest `engine` fixture builds the test DB from an empty schema, and `test_downgrade_and_upgrade_roundtrip` covers 0003 down and up.

### Automated checks (final state)
| Command | Result |
|---|---|
| `uv lock --check` | `Resolved 111 packages` (`slowapi` and `wrapt` removed, `limits` 5.8.0 now direct) |
| `uv run ruff format --check .` | `53 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 33 source files` |
| `TEST_DATABASE_URL=...newsdc_test uv run pytest -q` | `251 passed` (new: 33 in `test_api.py`, 30 in `test_api_db.py`) |
| `uv run pytest -q` (no DB) | `167 passed, 84 skipped` |

Failures along the way (all fixed):
- mypy: `ARRAY.any()` typing (switched to `literal(x) == any_(col)`), `Row` tuple indexing, and the `responses=` dict type.
- `test_api_db`: (1) `published_at` came back as `2026-10-05T17:30:00+05:30`. The test engine has no `timezone=UTC`, so the API was relying on the session timezone. **Fix:** the schemas now convert every timestamp to UTC `Z` themselves. (2) `/feeds/relevant?category=cooling` returned every item: `category` existed only on `/items`. **Fix:** `category` moved into the shared filters. (3) The similarity-floor test's query vector shared an axis with a fixture vector (a test bug).

### Bug found in the live check: rate limiting did nothing
The first live check sent 62 requests to `GET /api/v1/feeds/relevant?page_size=1` and got `62 200`. Cause: with FastAPI 0.162, `app.routes` holds `_IncludedRouter` objects that have no `endpoint`, so `slowapi.middleware._find_route_handler` returned `None` and `_should_exempt` exempted every request (seen by matching routes against a scope by hand). **Fix:** D-030, `limits` in our own middleware. After the fix, against the live server:
```
     60 200
      2 429
{"error":{"code":"rate_limited","message":"rate limit exceeded: 60 per 1 minute","request_id":"fd013534b1654aa986fc0ebf6b389c0d"}}
health 200
```

### Semantic similarity floor (measured on the live corpus)
Cosine similarity of the query embedding to the nearest processed items (bge-small-en-v1.5, HNSW with `iterative_scan = relaxed_order`). Without iterative scan, the filtered HNSW query returned fewer than 100 rows (an IndexError in the probe script), so the API sets it.

| Query | top | 10th | 50th | 100th |
|---|---|---|---|---|
| xqzv flurble banana | 0.619 | 0.587 | 0.564 | 0.554 |
| chocolate cake recipe | 0.484 | 0.467 | 0.445 | 0.436 |
| football world cup results | 0.560 | 0.535 | 0.514 | 0.499 |
| taylor swift concert | 0.521 | 0.457 | 0.412 | 0.400 |
| liquid cooling | 0.804 | 0.727 | 0.642 | 0.613 |
| GPU utilization optimization | 0.804 | 0.760 | 0.720 | 0.698 |
| nuclear power for data centers | 0.818 | 0.769 | 0.745 | 0.730 |
| PUE WUE | 0.692 | 0.529 | 0.498 | 0.490 |
| hyperscaler capex | 0.717 | 0.671 | 0.644 | 0.631 |
| submarine cables | 0.676 | 0.616 | 0.576 | 0.561 |

Before the floor, `search?q=xqzv flurble banana` returned `total 100`. With `SEARCH_MIN_SIMILARITY=0.6`: `xqzv flurble banana` 2, `chocolate cake recipe` 0, `liquid cooling` 133, `PUE WUE` 3, `submarine cables` 16.

### Live smoke test (uvicorn on :8011 against the live DB, final code)
| Request | Status | Time | Result |
|---|---|---|---|
| `GET /api/v1/health` | 200 | 0.023066s | {"status": "ok", "db": "ok", "version": "0.1.0"} |
| `GET /api/v1/items?page_size=1` | 200 | 0.061639s | total=2609 has_more=True mode=- first='Data Center Energy Use and Grid Impacts (Nove' published_at=2026-11-09T14:02:28Z |
| `GET /api/v1/items?category=cooling&sort=quality&page_size=1` | 200 | 0.010828s | total=132 has_more=True mode=- first='Modeling Liquid-Cooled Data Centers in Energy' published_at=2026-10-23T17:24:37Z |
| `GET /api/v1/items?source=arxiv&page_size=1` | 200 | 0.012034s | total=464 has_more=True mode=- first='An Optimal Power-Flow Grouping Topology for S' published_at=2026-11-06T10:56:19Z |
| `GET /api/v1/items/471` | 200 | 0.009549s | 'The Americans Striking It Rich in the Data-Ce' coverage=1 also_covered_by=[474] |
| `GET /api/v1/items/471/related` | 200 | 0.011037s | list of 6; first: 'Blue-Collar Jobs Are the New Flashpoint in Da' |
| `GET /api/v1/feeds/relevant?page_size=1` | 200 | 0.017706s | total=2609 has_more=True mode=- first='The Datacenter as a Computer (2013)' published_at=2026-02-10T17:06:51Z |
| `GET /api/v1/feeds/relevant?category=power-energy&page_size=1` | 200 | 0.011980s | total=531 has_more=True mode=- first='The Datacenter as a Computer (2013)' published_at=2026-02-10T17:06:51Z |
| `GET /api/v1/topics` | 200 | 0.024763s | list of 14; first: 'dc-infrastructure' |
| `GET /api/v1/topics/cooling?page_size=1` | 200 | 0.009937s | topic cooling total=132 |
| `GET /api/v1/search?q=liquid+cooling&page_size=1` | 200 | 0.463423s | total=133 has_more=True mode=hybrid first='45°C cooling design cuts data center water us' published_at=2026-06-24T14:10:11Z |
| `GET /api/v1/search?q=chocolate+cake+recipe` | 200 | 0.026753s | total=0 items=[] mode=hybrid |
| `GET /api/v1/items/999999999` | 404 | 0.003605s | {"code": "not_found", "message": "item 999999999 not found", "request_id": "e59dda8225744c5d9ad6103301180920"} |
| `GET /api/v1/items?page_size=51` | 422 | 0.002062s | {"code": "validation_error", "message": "query.page_size: Input should be less than or equal to 50", "request_id": "a97b4cac3a0a49b1a68484ca698602a1"} |
| `GET /api/v1/docs (html)` | 200 | 0.001148s |  |

Notes: the first search call (0.46 s) includes loading the embedding model. Later searches took about 25 ms. Item 471 is a canonical item with one near-duplicate (474, similarity 0.935). Its six related items were jobs/construction stories with similarity 0.73–0.79 (0.10 category boost included in the score). The first `/search?q=liquid cooling` hits were the NVIDIA 45 °C cooling design, an arXiv EnergyPlus liquid-cooling model, and a liquid-cooling overview, each with `<mark>liquid</mark> <mark>cooling</mark>` in the snippet. Response headers on a 404: `x-request-id`, `x-content-type-options: nosniff`, `content-security-policy: default-src 'none'; frame-ancestors 'none'`. Access-log line (real): `{"name": "app.access", "message": "request", "request_id": "6468e335…", "method": "GET", "path": "/api/v1/health", "status": 200, "duration_ms": 1.5, "client": "127.0.0.1", …}`.

### Not run
- `docker compose up --build` (no Docker, RISKS R-001). Compose now mounts the `models` volume on the backend too. This is untested under Docker.
- CI on GitHub (not pushed).

## Phase 5 (2026-11-09)

Environment: same machine and the same throwaway PostgreSQL 18.6 + pgvector 0.8.1 cluster as Phase 4 (port 55433). `newsdc` holds the live data (2,609 processed items), and `newsdc_test` is for pytest. No Docker. No LLM calls in this phase. No migration.

### Automated checks (final state)
| Command | Result |
|---|---|
| `uv lock --check` | `Resolved 111 packages` (no dependency changes) |
| `uv run ruff format --check .` | `58 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 36 source files` |
| `TEST_DATABASE_URL=...newsdc_test uv run pytest -q` | `288 passed` (new: 15 in `test_recommend.py`, 9 in `test_recommend_db.py`, 14 in `test_api.py`; the Phase 4 relevant-feed test moved to `test_recommend_db.py`) |
| `uv run pytest -q` (no DB) | `196 passed, 92 skipped` |

**Phase 5 acceptance check:** `test_recommend_db.py::test_cooling_heavy_profile_returns_mostly_cooling_plus_discovery_and_excludes_read` passed. It sends a profile heavy in cooling (3 read, 1 dismissed). The first 10 items are 8 cooling and 2 discovery (slots 5 and 10, from networking and regulation). No read or dismissed ID appears anywhere in the full feed. The pure-ranking version, `test_recommend.py::test_cooling_heavy_profile_gets_mostly_cooling_plus_discovery`, also passed.

Failures along the way (all fixed):
- `test_api.py`: `/items?sort=trending` expected 422. That was correct for Phase 4 and is now a valid sort, so the case became `sort=hot`.
- mypy: `dict[str | None, int]` from the read-count query. Fixed by dropping `NULL` categories.
- `test_recommend.py`: a negative-weight test assumed a quality-70 networking item would rank in the main feed. It qualifies for discovery (a test bug), so it was lowered to quality 50.
- `test_recommend_db.py`: `ValueError: expected list or ndarray`. pgvector's `avg(embedding)` came back as a string because `func.avg` had no result type, and binding it to `<=>` failed. **Fix:** `func.avg(..., type_=Vector(384))`.
- `test_recommend_db.py`: expected security as the second discovery category, but the regulation fixture (quality 85) correctly outranks it (a test bug).
- `SADeprecationWarning` for `Result.tuples()` (SQLAlchemy 2.1). Replaced it.

### Live smoke test (uvicorn on :8011 against the live DB, final code)
- `GET /feeds/trending?page_size=5`: total 2609. Top: `Nvidia's China Problem [pdf]` (HN, 16 points, 3 comments), then fresh items from today (`Data Center Energy Use and Grid Impacts`, FT, DCD).
- `GET /feeds/relevant?page_size=5`: `Anthropic signs $3.4bn gas generator deal…` (r92 q68, today), `We Visited China's Stargate in Inner Mongolia` (r95 q70, 2 days), `Your data center may be halfway to waterless` (r92 q62), `Google has acquired Crusoe's data center site…` (r95 q72, 3 days).
- `GET /topics/cooling?sort=trending&page_size=3`: 200.
- `POST /feeds/foryou?page_size=10` with `{"categoryWeights":{"cooling":12,"sustainability":2},"readIds":[6,3752,32,3760]}` (the 4 newest cooling items): `200 0.051848s`, `cold=false total=1000`. 8 personal items, all with cooling among their categories and the reason `Because you read 4 Cooling articles`. Slots 5 and 10 are `Discover: Power & Energy` and `Discover: AI / Agentic AI`.
- Same profile with `page_size=50`: the intersection of returned IDs with `readIds` is `[]`.
- `POST /feeds/foryou` with `{}`: `0.025159s`, `cold=true`, alternating `Trending now` / `Highly relevant`.
- Unknown slug: `{"error":{"code":"validation_error","message":"body: unknown category nope",...}}`.
- 70,000-byte body: `{"error":{"code":"payload_too_large","message":"request body over 65536 bytes",...}}`.

Not run: `docker compose` (no Docker, R-001). CI on GitHub (not pushed).

