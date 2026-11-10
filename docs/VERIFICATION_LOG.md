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

## Phase 6 (2026-11-09)

Environment: same machine and the same PostgreSQL 18.6 + pgvector 0.8.1 cluster (port 55433). `newsdc` holds the live data (2,609 processed items), and `newsdc_test` is the throwaway pytest database. No Docker. No migration. The live checks made real, paid calls to `claude-opus-5-5` (7 answered questions logged at $0.193 in total, plus one interrupted request that was not logged). Tests never call the API (`FakeChat`, plus the autouse `no_real_llm` fixture).

### Automated checks (final state)
| Command | Result |
|---|---|
| `uv lock --check` | `Resolved 111 packages in 1ms` (no dependency changes) |
| `uv run ruff format --check .` | `63 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 38 source files` |
| `TEST_DATABASE_URL=...newsdc_test uv run pytest -q` | `324 passed` (new: 31 in `test_assistant.py`, 5 in `test_ask_db.py`) |
| `uv run pytest -q` (no DB) | `227 passed, 97 skipped` |

What the new tests cover (§11.8): seeded retrieval returns the right items (rejected items never appear); "latest" questions prefer fresh evidence over a better but 120-day-old match (stale evidence); keyword-only fallback; no results means no LLM call; prompt builder formats `[n]` sources (title, publisher, date, URL, summary, insights) and bounds the context; prompt injection in source text stays escaped inside `<source>`; conflicting sources are both passed; fabricated citation numbers are removed, including markers split across chunks; malformed output (empty answer, refusal) ends in `error`, never `done`; `max_tokens` is marked `truncated`; client disconnect closes the LLM stream; SSE order `sources → status → token* → done`; 422 for bad questions or history; the separate rate limit; 503 when unconfigured; the prompt file hash is pinned to `assistant-v1`.

Failures along the way (all fixed):
- `test_api.py::test_openapi_lists_every_phase4_endpoint_and_error_shape`: the new `/ask` paths weren't in the pinned list. Updated (renamed `..._every_endpoint_...`).
- mypy: `ChatLLM` not found (an edit script didn't apply), the `MessageParam` TypedDict was ambiguous for history messages (now built with `UserMessageParam`/`AssistantMessageParam`), and `content_type` was `str` vs `Literal`.
- `test_ask_db.py::test_latest_questions_prefer_recent_evidence`: in normal mode the fresh rank-2 item beat the rank-1 match. Cause: raw RRF scores normalized by the best one were 1.0 vs 0.984, so retrieval barely counted. **Fix:** retrieval strength = `1 − position/25` (D-033, ARCHITECTURE.md). The test now checks the hybrid order and the recent-mode re-rank separately.

### Model check
`client.models.retrieve("claude-opus-5-5")` returned `Claude Opus 5.5`, `max_input_tokens=1000000`, `max_tokens=128000`, and effort `low…max` supported. (`claude-sonnet-5-5` was also listed.)

### Phase 6 acceptance: the five example questions (live, uvicorn on :8011 against the live DB, final code)

Run with `python ask_examples.py` (a scratch script: it gets `/ask/suggestions`, POSTs each question, parses the SSE stream and checks that every `[n]` in the answer is a returned source with an http(s) link). The output below is verbatim. Every question ended with `done`, and every citation maps to a real source link. Result: **ALL OK**.

#### Q: What are the latest developments in AI data center infrastructure?

events: ['sources', 'status', 'token']... -> ('done', {'cited': [1, 2, 3, 4, 5, 6, 7], 'removed_citations': 0, 'truncated': False})  (10.1s)

Recent coverage points to AI data center work expanding from chips and racks to power grids and networking, alongside rising equipment costs; the newest source is from mid-October 2026, about three weeks old.

- **Industry standards (OCP 2026):** The Open Compute Project is extending its specifications from servers and racks to silicon, cooling, power distribution, facilities and grid integration, which it calls "chip-to-grid" infrastructure [3]. **Meta** detailed its **Prometheus** AI cluster in New Albany, Ohio, including new optical networking, open-source transport software and AI-optimized concrete [3]. **Broadcom** and **NVIDIA** presented Ethernet and optical interconnect advances, and **AMD** and **Arm** also made announcements [3].
- **Equipment costs:** Stockatomics' AI Infrastructure Index, which tracks monthly prices for GPUs, servers, memory, optics, power and cooling components, is reported at 600.14, up 500.1% from its January 2023 base [6]. The source labels this a November 2026 reading even though it was published October 17. The index measures price per unit of equipment, not cost per unit of compute, which can fall while the index rises [6].
- **Grid interconnection:** An October arXiv paper finds that coordinating grid-side flexibility with data center workload shifting and UPS storage could raise feasible IT capacity at a constrained connection point from about 10.5–10.6 MW to 15.3–16.0 MW [5]. Most of that gain comes from network reconfiguration on the grid side [5].
- **Onsite power:** A July paper proposes phased deployment using on-site natural gas generation with grid-forming energy storage to work around multi-year interconnection and equipment lead times [7].
- **Scale of the largest sites:** Epoch AI finds the record for the largest AI data center has doubled roughly every seven months since **Colossus 1** (August 2024) [1]. It expects no facility to meaningfully exceed **Colossus 2** until the second half of 2027, with **QTS Cedar Rapids** and **Meta Hyperion** due in late 2027 or early 2028 [1].
- **Multi-site training:** Research explores EVPN-VXLAN for connecting data centers for geo-distributed AI training, motivated partly by data sovereignty requirements [4].
- **Security:** West Point's Modern War Institute cites Iranian strikes on **AWS** and **Oracle** data centers in the UAE and Bahrain as evidence that AI data centers are becoming strategic targets [2]. 

[1] Largest AI Data Center: Doubling every 7 months | epoch.ai | 2026-06-12 | https://epoch.ai/data-insights/largest-data-center-compute
[2] Data Center Warfare: Defending AI Infrastructure | mwi.westpoint.edu | 2026-06-20 | https://mwi.westpoint.edu/data-center-warfare-defending-the-key-terrain-of-ai-infrastructure/
[3] OCP 2026: Agentic AI Pushes the Data Center from Chip to Grid | datacenterfrontier.com | 2026-10-14 | https://www.datacenterfrontier.com/hyperscale/article/55411534/ocp-2026-agentic-ai-pushes-the-data-center-from-chip-to-grid
[4] ScaleAcross: Designing Multi-Data-Center Infrastructure for Geo-Distributed AI Training | arXiv | 2026-06-11 | https://arxiv.org/abs/2606.12963
[5] Unlocking AI Data Center Interconnection Capacity Through Coordinated Grid and Data Center Flexibility | arXiv | 2026-10-04 | https://arxiv.org/abs/2610.05502
[6] AI Infrastructure Index | stockatomics.com | 2026-10-17 | https://www.stockatomics.com/ai-infrastructure-index
[7] A Phased Development Framework Enabling Islanded Operation of Sustainable AI Data Centers With Onsite Grid-Following and Grid-Forming Energy Architectures | arXiv | 2026-07-19 | https://arxiv.org/abs/2607.17391

citations in answer: [1, 2, 3, 4, 5, 6, 7]; sources returned: 8; all map to a source link: True

#### Q: Which hyperscalers are investing in new data centers?

events: ['sources', 'status', 'token']... -> ('done', {'cited': [1, 4, 5, 6, 7], 'removed_citations': 0, 'truncated': False})  (7.5s)

NewsDC's collected sources name only a few large tech companies investing in new data centers, and they don't provide a full picture of hyperscaler spending.

- **Meta** is building its **Hyperion** data center in Richland Parish, Louisiana, with a planned investment of more than $10 billion and a first phase expected to open in 2028 [6]. Local officials approved the project under the code name Project Sucre through a subsidiary, Laidley LLC, before Meta was publicly identified [6]. Louisiana tax incentives, including an estimated $3.3 billion in sales tax relief on GPUs and networking gear, are worth billions to the company [6]. This source dates from December 2025, nearly 11 months ago.
- **Alibaba**, **ByteDance** and **Tencent** are investing billions in new data centers across Southeast Asia, where American firms are also seeking capacity [4]. The source does not name the American firms.
- **Google** has proposed orbital data centres through **Project Suncatcher**, alongside proposals from SpaceX and Blue Origin [7]. These are proposals, not facilities under construction [7].

Related developments:

- **Hyperscale Data**, despite its name, is not described as a hyperscaler. It is converting its former Bitcoin mining site in Dowagiac, Michigan, to AI computing for an unnamed California neocloud customer under a 20 MW contract [5].
- Several Bitcoin miners, including **Core Scientific**, **Galaxy Digital**, **TeraWulf** and **IREN**, are redirecting mining sites toward AI and HPC workloads [5].
- Northern Virginia's hyperscale cluster keeps expanding despite resident concern, but the source doesn't say which companies operate the facilities [1]. 

[1] What's It Like Inside a Data Center? | thenation.com | 2026-10-24 | https://www.thenation.com/article/society/inside-a-data-center-hyperscale/
[4] The Global Data Center Boom Is a Gift to Spies | lawfaremedia.org | 2026-09-10 | https://www.lawfaremedia.org/article/the-global-data-center-boom-is-a-gift-to-spies
[5] Goodbye Bitcoin, Hello AI Data Center | americanbuildout.com | 2026-09-02 | https://americanbuildout.com/goodbye-bitcoin-hello-ai-data-center/
[6] The Power Play Behind Hyperion, Meta's Big Data Center Being Built in Louisiana | sherwood.news | 2025-12-19 | https://sherwood.news/tech/hyperion/
[7] The earthly limits of data centre resistance | policyreview.info | 2026-06-10 | https://policyreview.info/articles/news/data-centre-resistance/2102

citations in answer: [1, 4, 5, 6, 7]; sources returned: 8; all map to a source link: True

#### Q: What is emerging in liquid cooling and power availability?

events: ['sources', 'status', 'token']... -> ('done', {'cited': [1, 2, 3, 4, 5, 6, 7, 8], 'removed_citations': 0, 'truncated': False})  (8.4s)

The sources show liquid cooling moving toward warm-water designs, retrofits for existing air-cooled halls and optimized cold plates; NewsDC's collected sources don't cover power availability (grid supply or securing power for sites).

**Liquid cooling**
- **Higher-temperature designs:** **NVIDIA** describes liquid cooling for its Rubin-generation AI infrastructure that runs at up to 45°C with closed-loop dry coolers, allowing chiller-less operation in favorable climates [3].
  - NVIDIA says this cuts facility water use from about 2.6 million gallons per megawatt per year to near zero [3].
  - It describes Rubin-generation systems as 100% liquid cooled, with no fans [3].
- **Retrofitting air-cooled sites:** **Google**'s **Brazos** is a rack-mounted, closed-loop liquid-to-air system for running high-density liquid-cooled equipment in existing air-cooled data centers [5].
  - It supports 60 kW nominal thermal load per rack and can be installed one rack at a time, avoiding chilled-water retrofits [5].
  - It is described as generally available, with open-sourcing planned through the Open Compute Project [5].
- **Cold plate innovation:**
  - **University of Illinois Urbana-Champaign** researchers developed 3D-printed, topology-optimized pure copper cold plates [8]. They estimate cooling's share of data center electricity could fall from about 30% to about 1.1% [8].
  - A generative design method for **NVIDIA GB200** cold plates reports more than 5°C lower average and over 35°C lower maximum temperatures than a baseline parallel-channel design [6].
- **Modeling and optimization:**
  - A new EnergyPlus model of direct-to-chip cooling reports, in a case study, that warm-water liquid cooling lowers annual PUE from 1.43 to 1.25 and cuts facility energy by 37.9% compared with air cooling [2].
  - A machine-learning study on the **Frontier** supercomputer finds up to 96% of about 85 MWh of annual excess cooling energy could be recovered through small setpoint changes [7].
- **Operations and adoption:**
  - Liquid cooling makes precise, real-time measurement across both liquid and air environments essential [1].
  - Single-phase cooling currently predominates, while two-phase and immersion cooling are growing [4].

**Power availability**
- The sources only touch on power indirectly:
  - Cooling is cited as up to 40% of data center electricity use [3], or about 30% [8].
  - Brazos requires legacy facilities to have sufficient power [5]. 

[1] Liquid Cooling Is Changing What Data Centers Need to Measure | Data Center Knowledge | 2026-11-04 | https://www.datacenterknowledge.com/cooling/liquid-cooling-is-changing-what-data-centers-need-to-measure
[2] Modeling Liquid-Cooled Data Centers in EnergyPlus | arXiv | 2026-10-23 | https://arxiv.org/abs/2610.33148
[3] 45°C cooling design cuts data center water use to near zero | blogs.nvidia.com | 2026-06-24 | https://blogs.nvidia.com/blog/liquid-cooling-ai-factories/
[4] Liquid Cooling Gains Traction in Data Centers | semiengineering.com | 2026-01-22 | https://semiengineering.com/liquid-cooling-gains-traction-in-data-centers/
[5] Brazos: Liquid cooling system for air-cooled data centers | cloud.google.com | 2026-06-16 | https://cloud.google.com/blog/topics/systems/brazos-liquid-cooling-system-for-air-cooled-data-centers/
[6] Generative Design for Direct-to-Chip Liquid Cooling for Data Centers | arXiv | 2026-04-13 | https://arxiv.org/abs/2604.10941
[7] Machine Learning Guided Cooling System Optimization for Data Center | arXiv | 2026-01-05 | https://arxiv.org/abs/2601.02275
[8] Cooling copper plates could slash data center energy use by 90% | newatlas.com | 2026-05-20 | https://newatlas.com/energy/cooling-copper-plates-data-center-energy-use/

citations in answer: [1, 2, 3, 4, 5, 6, 7, 8]; sources returned: 8; all map to a source link: True

#### Q: Which articles discuss GPU utilization optimization?

events: ['sources', 'status', 'token']... -> ('done', {'cited': [1, 2, 3, 4, 5, 6, 7, 8], 'removed_citations': 0, 'truncated': False})  (8.4s)

Several of NewsDC's collected sources address GPU utilization optimization, from power- and thermal-aware control to scheduling, virtualization, profiling and kernel-level tuning.

**Power, thermal and grid-aware control**
- **GPU-to-Grid** (arXiv): Uses LLM inference batch size as a control knob that trades off GPU power, latency and token throughput, so data centers can help regulate grid voltage [1].
- **Coordinated Cooling and Compute Management** (arXiv): Jointly tunes GPU parallelism, DVFS frequency and cooling controls, evaluated with Azure inference traces, to balance serving latency against thermal limits [6].
- **Lit Silicon** (arXiv): Finds that thermal imbalance creates straggler GPUs in multi-GPU LLM training. It reports up to 6% performance and 4% power improvements on AMD MI300X systems through power management strategies [4].

**Prediction and scheduling**
- **Two-Stage GPU Resource and Power Prediction** (arXiv): Predicts maximum GPU utilization with up to 97% accuracy and runtime power with up to 92% accuracy on NERSC's Perlmutter system, to support more efficient, power-aware scheduling [2].

**Sharing and profiling**
- **GPU-Virt-Bench** (arXiv): Benchmarks software-based GPU virtualization (HAMi-core, BUD-FCSP) against simulated NVIDIA MIG baselines for multi-tenant GPU sharing, including fragmentation and scheduling metrics [3].
- **Zymtrace vs. Nsight** (zymtrace.com): Argues that continuous, eBPF-based cluster profiling helps maximize throughput per GPU, per watt and per dollar [7].

**Software performance tuning**
- **GPT-OSS Optimizations on Nvidia Blackwell** (blog.vllm.ai): Reports +38% maximum throughput and +13% best interactivity for gpt-oss-120b on B200/GB200, using FlashInfer kernels and torch.compile fusions [5].

**More tangential**
- **NVIDIA GQE**: Covers GPU-accelerated SQL execution and identifies memory and I/O bandwidth as the main constraints, rather than utilization tuning as such [8]. 

[1] GPU-to-Grid: Voltage Regulation via GPU Utilization Control | arXiv | 2026-02-04 | https://arxiv.org/abs/2602.05116
[2] A Practical Two-Stage Framework for GPU Resource and Power Prediction in Heterogeneous HPC Systems | arXiv | 2026-04-02 | https://arxiv.org/abs/2604.02158
[3] GPU-Virt-Bench: A Comprehensive Benchmarking Framework for Software-Based GPU Virtualization Systems | arXiv | 2025-11-26 | https://arxiv.org/abs/2512.22125
[4] Lit Silicon: A Case Where Thermal Imbalance Couples Concurrent Execution in Multiple GPUs | arXiv | 2025-11-13 | https://arxiv.org/abs/2511.09861
[5] GPT-OSS Optimizations on Nvidia Blackwell: Pushing the Pareto Frontier | blog.vllm.ai | 2026-02-25 | https://blog.vllm.ai/2026/02/01/gpt-oss-optimizations.html
[6] Coordinated Cooling and Compute Management for AI Datacenters | arXiv | 2026-01-13 | https://arxiv.org/abs/2601.08113
[7] Zymtrace vs. Nsight: Profiling Nvidia GPU Clusters at Scale | zymtrace.com | 2026-01-09 | https://zymtrace.com/article/zymtrace-nsight/
[8] Designing GPU-Accelerated Query Engines with NVIDIA GQE | developer.nvidia.com | 2026-07-06 | https://developer.nvidia.com/blog/designing-gpu-accelerated-query-engines-with-nvidia-gqe/

citations in answer: [1, 2, 3, 4, 5, 6, 7, 8]; sources returned: 8; all map to a source link: True

#### Q: What technologies could improve PUE and WUE?

events: ['sources', 'status', 'token']... -> ('done', {'cited': [1, 3, 4, 6, 7], 'removed_citations': 0, 'truncated': False})  (6.8s)

The only technology NewsDC's sources directly link to better PUE is a **digital twin** framework for energy optimization, and none of them describe a technology that improves WUE.

**Directly tied to PUE**
- **Digital twin with IoT and machine learning:** A scalable framework monitors power, temperature and workload in real time and uses LSTM models to forecast energy demand [3]. The authors report lower power consumption and improved PUE, but only in a small-scale controlled data center, not in production facilities [3].

**Related efficiency technologies (sources don't report PUE or WUE effects)**
- **Diamond-copper thermal interface coating:** The Chinese Academy of Sciences' Ningbo Institute says it improved cooling efficiency by 80% and chip performance by 10% at an AI computing node in Zhengzhou [6]. The composite reportedly exceeds 1,000 W/mK thermal conductivity [6].
- **Server configuration adjustments:** A measurement-based study in an operational data center found that these change the energy consumption of processing jobs [7]. It recommends ways to cut server energy use while weighing performance and carbon emissions [7].
- **Waste heat recovery:** Reusing data center heat to supply buildings in an integrated energy system cut total energy costs by about 10% in case studies [4].

**Measurement**
- **deoks-pue-wue-validator:** This zero-dependency Python tool validates CSV data and calculates PUE and WUE [1]. It measures the metrics but does not improve them.

NewsDC's collected sources don't cover water-saving technologies or anything else specifically aimed at WUE. 

[1] indeokman/deoks-pue-wue-validator | GitHub | 2026-11-09 | https://github.com/indeokman/deoks-pue-wue-validator
[3] A Scalable Digital Twin Framework for Energy Optimization in Data Centers | arXiv | 2026-05-07 | https://arxiv.org/abs/2605.05581
[4] End-to-End Learning-based Operation of Integrated Energy Systems for Buildings and Data Centers | arXiv | 2026-03-31 | https://arxiv.org/abs/2604.14184
[6] Chinese diamond-based coating boosts data center cooling efficiency by 80% | thecoolingreport.com | 2026-04-21 | https://thecoolingreport.com/intel/diamond-copper-composite-coating-chinese-academy-sciences-cooling-efficiency.html
[7] Improving the Energy Efficiency of High Throughput Computing: A Measurement-Based Case Study | arXiv | 2026-08-06 | https://arxiv.org/abs/2608.06622

citations in answer: [1, 3, 4, 6, 7]; sources returned: 8; all map to a source link: True

ALL OK

Logged per answer (`ask answered` lines in the uvicorn log, in order: the five above, the follow-up, the off-topic question):

| # | tokens in | tokens out | latency ms | cited/sources | removed | cost |
|---|---|---|---|---|---|---|
| 1 | 4016 | 954 | 9496 | 7/8 | 0 | $0.035888 |
| 2 | 4074 | 759 | 7441 | 5/8 | 0 | $0.028798 |
| 3 | 3805 | 961 | 8390 | 8/8 | 0 | $0.031762 |
| 4 | 3814 | 889 | 8309 | 8/8 | 0 | $0.030358 |
| 5 | 3375 | 675 | 6766 | 5/8 | 0 | $0.024322 |
| 6 | 4151 | 571 | 5748 | 4/8 | 0 | $0.025346 |
| 7 | 3662 | 222 | 2870 | 2/8 | 0 | $0.01641 |

#### Follow-up (multi-turn)
`{"question":"Which of those are in Europe?","history":[user: "Which hyperscalers are investing in new data centers?", assistant: "Meta is building Hyperion in Louisiana [6]; Alibaba, ByteDance and Tencent invest in Southeast Asia [4]."]}`. Retrieval used both questions and returned Europe-related sources (Ireland/Dublin grid, EU plans, Gulf vs Europe).

> **None of the hyperscaler investments named in NewsDC's current sources are in Europe.** The sources don't name any specific hyperscaler building new data centers there.
> 
> - **Alibaba, ByteDance and Tencent** are investing billions in new data centers across Southeast Asia, not Europe [4].
> - **Meta's** Hyperion project in Louisiana isn't covered in the current sources.
> 
> What the sources do say about Europe:
> 
> - **Ireland:** Hyperscale data center growth around Dublin is diverting grid capacity and driving transmission upgrades. The state is funding emergency fossil-fuel generators to keep supply stable [5]. The sources don't name the hyperscalers involved.
> - **Local opposition:** Communities near Dublin, including Rochfortbridge and Naas, are opposing new developments [5]. Local, legal and political resistance to data centres is also growing elsewhere in Europe [7].
> - **EU plans:** The EU plans to triple its data center capacity under the AI Continent Action Plan [5].
> - **Permitting hurdles:** Grid, permitting and opposition problems in parts of Europe contrast with the Gulf, where governments can coordinate energy, land and capital [2].

`data: {"cited":[2,4,5,7],"removed_citations":0,"truncated":false}`

#### Off-topic
`{"question":"What is the best sourdough bread recipe?"}`. The OR-ed keywords still matched 8 items (on "best" and "recipe"), so the model was called, and it declined correctly from the evidence:

> NewsDC's collected sources don't cover sourdough bread or any baking recipes. They focus on data center topics such as GPU cluster configuration, grid interconnection and AI model training.
> 
> The only "recipes" in these sources are technical ones:
> 
> - **AICR v1.0** from NVIDIA provides version-locked, validated recipes for configuring GPU-accelerated Kubernetes clusters [1].
> - A paper on the **SuperMUC-NG Phase 2** system describes a "scalable recipe" for training language models of up to 175 billion parameters [5].
> 
> For a sourdough recipe, you'll need a cooking or baking resource. I can help with any data center questions.

`data: {"cited":[1,5],"removed_citations":0,"truncated":false}`

#### Other live checks
- `POST /ask {"question":"hi"}` → `{"error":{"code":"validation_error","message":"body.question: String should have at least 3 characters","request_id":"7c90b57e100145549234cbbc31af88c0"}}`.
- The first off-topic attempt was piped through `head -c`, which closed the connection after `sources`/`status`. No `ask answered` line was logged for it: the server stopped streaming when the client went away.

### Observations (not failures)
- The follow-up answer says Meta's Hyperion "isn't covered in the current sources". That's true, because the second turn retrieved a new source list. The rule of citing only the current list works as designed, but it can read oddly.
- "What is emerging in liquid cooling and power availability?" retrieved 8 cooling items, and the answer says power availability isn't covered, although the corpus has power items. Retrieval favours the dominant topic of a two-topic question. A possible fix (split retrieval per topic) is noted for later; no change was made.
- An off-topic question still costs one LLM call (about $0.025) because OR-ed keywords match common words. A minimum-evidence threshold would save it.

Not run: `docker compose` (no Docker, R-001). CI on GitHub (not pushed). Pricing for Opus 5.5 ($4/$20 per MTok) was **not** re-checked on the live pricing page.


## Phase 7 (2026-11-09)

Environment: same machine and PostgreSQL 18.6 + pgvector 0.8.1 cluster (port 55433). `newsdc` holds the live data (3,898 items, 2,609 processed); `newsdc_test` is the throwaway pytest database. No Docker. **uv is not on PATH in this session**, so the commands below ran with the project's existing `backend/.venv` binaries (`.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/pytest`, `.venv/bin/alembic`), which is what `uv run` would execute; no dependency changes. One real, paid call to `claude-opus-5-5` (the live brief, $0.063). Tests never call the API (`FakeChat`, autouse `no_real_llm`).

Plan Phase 7 lists no separate acceptance block. The checks used are its three scope items: (1) rising topics with % change, (2) a scheduled weekly brief with citations stored in `trend_briefs`, (3) `/stats` with every listed field.

### Automated checks (final state)
| Command | Result |
|---|---|
| `ruff format --check .` | `69 files already formatted` |
| `ruff check .` | `All checks passed!` |
| `mypy app` | `Success: no issues found in 40 source files` |
| `TEST_DATABASE_URL=...newsdc_test pytest -q` | `344 passed` (new: 12 in `test_trends.py`, 8 in `test_trends_db.py`) |
| `pytest -q` (no DB) | `239 passed, 105 skipped` |
| `alembic downgrade 0003` then `upgrade head` on `newsdc_test` | `Running downgrade 0004 -> 0003`, `Running upgrade 0003 -> 0004` |
| `alembic upgrade head` on `newsdc` | `Running upgrade 0003 -> 0004` |

What the new tests cover: share-based change (more items overall is not a rise), new terms, the ≥3 minimum, window bounds, case-insensitive counting once per item, ordering and limit, no baseline; publishers dropped from their own items' companies; untrusted terms escaped in the prompt; prompt hash pinned to `trend-brief-v1`; brief stored with only valid citations, this week's processed items only, cost computed; no LLM call with <5 items; no-citation and `max_tokens` answers rejected and not stored; `trend_brief` job kind accepted by the DB; `/trends` numbers (6/10 vs 2/20 = +500%, falling terms absent, brief sources numbered 1–10); `/stats` funnel, category counts and average quality, content types, sources, 60 zero-filled days, runs, cost.

Failures along the way (all fixed):
- `test_openapi_lists_every_endpoint_and_error_shape`: `/trends` and `/stats` added to the pinned path list.
- Two of my own unit-test expectations were wrong (a spelling tie, and a window test with no baseline items); the tests were corrected, not the code.
- SQLAlchemy 2.1 deprecation warning for `Result.tuples()`; removed.
- **Live finding:** the first `/trends` on real data listed publishers as rising companies (DatacenterDynamics +4,113%, The New York Times, Financial Times, ServeTheHome) because the classifier lists the outlet as an entity. Fixed by ignoring a company equal to the item's own publisher (D-034); covered by a unit test.

### Live checks (uvicorn on :8012 against `newsdc`, final code)

**1. Rising topics** (`GET /trends` at 2026-11-09T16:28Z; term (recent/baseline items, change)):
- tags: export-controls (7/1, +1447%), data-center-protest (4/0, +784%), data-center-monitoring (3/0, +563%), optical-networking (3/1, +563%), ups-monitoring (3/0, +563%), ai-agents (3/2, +232%), ai-data-center-power (3/2, +232%), battery-energy-storage (3/2, +232%), predictive-maintenance (3/2, +232%), nvidia (17/14, +168%)
- companies: Megaspeed International Pte Ltd (3/0, +563%), OpenAI (4/2, +342%), Intel (3/2, +232%), Microsoft (12/9, +195%), Anthropic (7/6, +158%), AMD (5/7, +58%), Nvidia (32/66, +7%)
- technologies: battery energy storage system (3/1, +563%), AI (5/2, +453%), AI agents (5/3, +268%), Three.js (3/2, +232%), liquid cooling (4/5, +77%), AI accelerators (3/4, +66%), UPS (3/4, +66%), vLLM (3/4, +66%)

**2. Weekly brief.** Scheduler: `add_job(schedule_brief, "cron", day_of_week="mon", hour=6)` → `next brief run 2026-11-16 06:00:00+00:00`. On-demand run through the real job path: `python -m app.jobs enqueue trend_brief` → `{"queued": 3}`, then `jobs.claim` + `worker.run_job`:

```
"message": "trend brief stored", "brief_id": 1, "model": "claude-opus-5-5", "prompt_version": "trend-brief-v1", "sources": 30, "cited": 20, "removed_citations": 0, "tokens_in": 10152, "tokens_out": 1069, "cost_usd": "0.062733"
"message": "job finished", "job_id": 3, "kind": "trend_brief", "attempt": 1, "outcome": "succeeded"
```

The brief as served by `GET /trends` (period 2026-11-02T16:28:10.784951Z to 2026-11-09T16:28:10.784951Z):

> Power is this week's dominant theme: AI developers are securing their own on-site generation, and grid researchers are focusing on how large data centers behave on the network. Community opposition and new chip specifications also stand out.
>
> **AI labs securing their own power**
> - Anthropic signed a $3.4bn deal to support 1.7 GW of data center power by taking over an existing OnePWR order of Caterpillar gas generator sets [1]. The FT describes this as bypassing traditional suppliers to secure scarce equipment [5].
> - Google acquired Crusoe's southeast Wyoming site. Its hybrid power strategy combines fuel cells, grid power and natural gas turbines, with a planned carbon capture roadmap [4].
> - SpaceXAI claims its planned Arizona data center will reach 6 GW, with construction possibly starting in March 2027 [24].
>
> **Grid integration and battery storage research**
> - Several arXiv papers address how data centers behave on the grid. Topics include battery storage sizing to meet interconnection requirements [10], ride-through-aware voltage control that cut mean disconnection rates by 44.8% in one test system [12], and transmission planning under uncertainty about which projects get built [29].
> - Battery dispatch using price and load forecasts reported 2.63 times the cost savings of a rule-based strategy [18].
> - A county-level US study finds that growth in data center floor area drives nearby generation capacity, with the strongest effects in the West [13].
>
> **Community pushback and new commitments**
> - Power shortages and local opposition are delaying projects [16]. A small Spanish town is contesting a macro data center [23].
> - OpenAI published a National Community Compact. It commits to paying full electricity and infrastructure costs, writing a water plan for each campus that prioritizes closed-loop or low-water cooling, and limiting NDAs with public officials [11, 30].
>
> **Chips and server hardware**
> - NVIDIA revised Rubin specifications as production ramps. HBM4 bandwidth drops from 22TB/s to 19.2TB/s and NVLink bandwidth from 3.6TB/s to 3.0TB/s, while scale-out bandwidth rises to 450GB/s [17].
> - Google added TPU 8tx for confidential computing and TPU 8i Max for context scaling [22].
> - An ASRock Rack Diamond Rapids board routes all PCIe Gen6/CXL 3.0 I/O through cables [20].
>
> **New designs and markets abroad**
> - The Inner Mongolia campus SemiAnalysis calls "Stargate" is planned at 800MW, with 120MW built within a year. It pilots 800V DC power with solid-state transformers and uses cooling without central chillers [2].
> - Argentina's Milei envisions an unregulated AI hub in Patagonia [28].
>
> **Governance and financial signals**
> - Nvidia opened an investigation into Jensen Huang's relationship with an executive that U.S. officials linked to Chinese intelligence; the item connects the matter to Megaspeed International [26].
> - ING Bank is reportedly seeking to sell about $500m in data center loans, including loans tied to a Stargate site, amid investor concern [25].

Every cited number maps to a real source link (20 of 30 sources cited, check: `all map: True`):

| n | Title | URL |
|---|---|---|
| [1] | Anthropic signs $3.4bn gas generator deal to support 1.7GW of data center power | https://www.datacenterdynamics.com/en/news/anthropic-signs-34bn-gas-generator-deal-to-support-17gw-of-data-center-power/ |
| [2] | We Visited China’s Stargate in Inner Mongolia | https://newsletter.semianalysis.com/p/we-visited-chinas-stargate-in-inner |
| [4] | Google has acquired Crusoe's data center site in southeast Wyoming | https://www.crusoe.ai/resources/newsroom/crusoe-wyoming-data-center-campus-update |
| [5] | Anthropic strikes $3.4bn deal to generate gas-fired power for data centres | https://www.ft.com/content/41bf5c6a-9735-4f1a-a8e3-2bcccad58ba0?syn-25a6b1a6=1 |
| [10] | Supporting Data Center Grid Integration via Co-Optimized Battery Energy Storage Sizing and Capacity Allocation | https://arxiv.org/abs/2611.09001 |
| [11] | Setting a new standard for responsible AI infrastructure | https://openai.com/index/setting-new-standard-responsible-ai-infrastructure/ |
| [12] | Reducing Data-Center Load Transfers with Ride-Through-Aware Voltage Control | https://arxiv.org/abs/2611.08777 |
| [13] | Data Center Agglomeration and Power Infrastructure Capacity in the United States | https://arxiv.org/abs/2611.06737 |
| [16] | AI’s Expansion Hits the Limits of Local Power | https://www.datacenterknowledge.com/energy-power-supply/ai-s-expansion-hits-the-limits-of-local-power |
| [17] | Nvidia Updates Rubin GPU Specs as First Production Hardware Arrives | https://www.servethehome.com/nvidia-updates-rubin-gpu-specs-as-first-production-hardware-arrives/ |
| [18] | Joint Electricity Price and Load Forecasting for Data Center Battery Dispatch Using Polynomial Diffusion Models | https://arxiv.org/abs/2611.08470 |
| [20] | ASRock Rack DMRD16-2L+ Spotted with 16 DDR5 Slots for Diamond Rapids | https://www.servethehome.com/asrock-rack-dmrd16-2l-plus-diamond-rapids-ocp-summit-2026/ |
| [22] | Google expands eighth-generation TPU portfolio with two new “TPU systems” | https://www.datacenterdynamics.com/en/news/google-expands-eighth-generation-tpu-portfolio-with-two-new-tpu-systems/ |
| [23] | A small town in Spain battles again construction of a macro data center | https://english.elpais.com/spain/2026-11-07/a-small-town-in-spain-battles-again-construction-of-a-macro-data-center-its-a-way-of-kicking-us-out.html |
| [24] | SpaceXAI plans data center in Arizona, Musk's firm claims it will have 6GW capacity | https://www.datacenterdynamics.com/en/news/spacexai-data-center-arizona-cochise-county-elon-musk/ |
| [25] | ING Bank looks to sell $500m in data center loans at once, including at Stargate site | https://www.datacenterdynamics.com/en/news/ing-bank-looks-to-sell-500m-in-data-center-loans-at-once-including-at-stargate-site/ |
| [26] | Nvidia Opens Investigation Into Jensen Huang’s Relationship With Chinese Spy | https://www.nytimes.com/2026/11/08/technology/nvidia-investigation-jensen-huang-china.html |
| [28] | Argentina’s Milei dreams of data centres on the Patagonian steppe | https://www.ft.com/content/d432ae29-6454-4916-98c7-afb6993cfb67?syn-25a6b1a6=1 |
| [29] | Transmission Expansion with Large, Discrete Data Center Realization Uncertainty | https://arxiv.org/abs/2611.05958 |
| [30] | OpenAI Pledges to Give Locals More Say in Data Center Projects | https://www.nytimes.com/2026/11/05/technology/openai-data-centers-midterms.html |

**3. `GET /stats`**: `HTTP 200 0.080s`.
- funnel `{fetched: 3898, new: 0, rejected_prefilter: 52, rejected_ai: 1158, duplicate: 79, failed: 0, processed: 2609}`; matches `SELECT status, count(*) FROM items GROUP BY 1`.
- by_category sums to 2,609 (ai-compute-gpus 640 at avg quality 56.3 … security 45 at 56.1; power-energy has the highest average, 68.7).
- by_content_type: news 1,033, engineering 709, research 573, investment 294 (sum 2,609).
- by_source: hn 2,487 found / 1,506 processed, github 760/545, arxiv 502/464, dck 50/48, dcd 27/20, ft_tech 26/6, nyt_tech 26/7, semianalysis 20/13, sth 6/5, nextplatform 0/0, register_dc 0/0.
- per_day: 60 days, 644 processed items, last three days 11, 12, 22.
- pipeline_runs: the 10 latest (run 40 pipeline, runs 39–31 ingest).
- ai_cost after the brief: `{classifier_usd: 1.1292, classifier_today_usd: 1.1292, trend_brief_usd: 0.0627, total_usd: 1.1919}`.

Not run: `docker compose` (no Docker, R-001). CI on GitHub (not pushed).

## Phase 8 (2026-11-09)

Environment: same machine and PostgreSQL 18.6 + pgvector 0.8.1 cluster (port 55433). `newsdc` holds the live data (3,898 items, 2,609 processed); `newsdc_test` is the throwaway pytest database. No Docker. uv is not on PATH, so commands ran with the existing `backend/.venv` binaries (what `uv run` executes); no dependency changes. No LLM calls in this phase.

Acceptance checks (plan Phase 8): admin routes return 401 without the cookie; login is rate limited; exports download and open correctly; tests cover auth and export.

### Automated checks (final state)
| Command | Result |
|---|---|
| `ruff format --check .` | `75 files already formatted` |
| `ruff check .` | `All checks passed!` |
| `mypy app` | `Success: no issues found in 42 source files` |
| `TEST_DATABASE_URL=...newsdc_test pytest -q` | `372 passed` (new: 16 in `test_admin.py`, 12 in `test_admin_db.py`) |
| `pytest -q` (no DB) | `255 passed, 117 skipped` |
| `pytest -q tests/test_admin.py tests/test_admin_db.py` (with DB) | `28 passed` |
| `alembic downgrade 0004` then `upgrade head` on `newsdc_test` | `Running downgrade 0005 -> 0004`, `Running upgrade 0004 -> 0005` |
| `alembic upgrade head` on `newsdc` | `Running upgrade 0004 -> 0005` |

What the new tests cover:
- **Auth:** all 15 protected routes return 401 without a cookie. Admin is disabled (503) without `SESSION_SECRET` or with a short token. The cookie carries `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/v1/admin` and `Max-Age=1800`, and never the token or the secret. A wrong token is 401 with no detail. Login is limited per IP (5 → 429, and the correct token is refused too while the limit holds) and globally (30). The login body is validated. `POST` without or with a wrong `X-CSRF-Token` is 403. A foreign `Origin` or `Referer` is 403, while an allowed `CORS_ORIGINS` origin passes. Logout revokes the session, and a copied cookie works before logout but not after. Each login rotates the session. Forged, tampered, unsigned, empty and expired cookies are refused, and a cookie signed with the admin token is refused.
- **Export:** JSON has processed items only, sources primary first, insights, no `content_text` or `description`, and the download headers. Filters, `limit` bounds and format validation work. Markdown has the download headers and is grouped by category. A `<script>` / `javascript:` title stays escaped text. The escaping and link helpers are unit-tested.
- **Actions:** ingest all / one source / unknown (404) / YAML-disabled (409). Pipeline queueing with one active job per kind (`job_id: null`). The trend brief needs the assistant (409). The runs list shows `stop_reason`. Jobs list, dead-letter retry, then 409. Reprocess one item, and unknown is 404. Rejected items with reasons and a status filter. Pausing a source survives a re-seed, enabling a YAML-disabled source is 409. A category edit survives a re-seed and makes every classified item outdated (4 reset). Category validation, and the last enabled category can't be disabled (409).

Failures along the way (all fixed):
- `scripts/export_dataset.py`: `ModuleNotFoundError: No module named 'app'`. Fixed with the same `sys.path` line `eval_classifier.py` uses.
- `tests/test_admin_db.py`: `import app.db` was shadowed by the FastAPI `app`, so it is now `from app import db as app_db`. Two test expectations were wrong: YAML lists Power before Cooling, and a substring check matched the *escaped* `\<script\>`. Both were fixed in the tests, not the code.
- `SADeprecationWarning: Result.tuples()` in `export.category_names` turned into a 500 under `-W error`. Removed.
- `test_openapi_lists_every_endpoint_and_error_shape`: the 17 new paths were added to the pinned list.
- `markdown-it-py` isn't installed, and adding a dev dependency needs uv, which isn't on PATH here. The Markdown test asserts the escaped output directly instead of rendering it.

### Live checks (uvicorn on :8765 against `newsdc`, final code)
Throwaway `ADMIN_TOKEN`/`SESSION_SECRET` from `secrets.token_urlsafe`, set in the environment only (not in `.env`). Output verbatim:
```
--- no cookie
runs 401
jobs 401
sources 401
categories 401
rejected 401
session 401
POST pipeline 401
--- login
csrf len 43
cookie path=/api/v1/admin secure=TRUE
runs 40 pipeline succeeded
rejected 1289
  duplicate | title+summary embedding cosine similarity 0.932 > 0.92 with item 163, published within 14 
  rejected_ai | Personal and espionage story about an Nvidia executive with no data center infrastructure,
  rejected_prefilter | no data center keywords
sources [('hn', True), ('arxiv', True), ('github', True), ('dcd', True), ('dck', True), ('sth', True), ('semianalysis', True), ('nyt_tech', True), ('ft_tech', True), ('register_dc', False), ('nextplatform', False)]
POST without csrf: {"error":{"code":"csrf_failed","message":"missing or invalid X-CSRF-Token","request_id":"3acfad044d2c48728d5df5cf1e464f51"}}
--- login rate limit (bad token x6)
401 401 401 401 429 429 
--- logout 204; after: 401
```
The 5th bad attempt already got 429 because the successful login before it counts toward the 5/minute per-IP limit (D-035). `rejected` 1,289 = 52 prefilter + 1,158 AI + 79 duplicates, which matches the Phase 7 funnel.

Export:
```
content-disposition: attachment; filename="newsdc_export.json"
content-type: application/json
json records 1000 | cats 14 | with sources 1000
content-disposition: attachment; filename="newsdc_export.md"
content-type: text/markdown; charset=utf-8
50                      # "### " item headings for ?format=md&category=cooling&limit=50
## Data Center Infrastructure … ## Emerging Technologies   # 7 groups (by primary category)
real 0m0.312s           # ?format=md&limit=1000
```
The JSON parsed with `json.load`. No actions that queue paid jobs were run on the live DB.

### Sample dataset
`python scripts/export_dataset.py` → `wrote 1000 records to /home/shubham/Documents/news-dc/data/sample/newsdc_sample.json and newsdc_sample.md` (exit 0). The JSON is 1,481,854 bytes and the Markdown 828,277 bytes. A `json.load` check found 1000 records, the fields listed in API.md, and no `content_text` key.

Not run: `docker compose` (no Docker, R-001), so the non-root frontend Dockerfile change hasn't been built. CI on GitHub (not pushed). Rendering the Markdown in a browser or editor: pending human verification.

## Phase 9 (2026-11-10)

Environment: same machine and PostgreSQL 18.6 + pgvector 0.8.1 cluster (port 55433, `newsdc` with 3,898 items / 2,609 processed; `newsdc_test` for pytest). No Docker. Backend run with `backend/.venv/bin/uvicorn app.main:app --port 8000` and `CORS_ORIGINS=http://localhost:5173,http://localhost:4173`. Frontend: Node 24.19.0, pnpm 11.22.0, production build served by `vite preview` on :4173 (built with `VITE_API_BASE_URL=http://localhost:8000`). Browser: the installed Google Chrome (Playwright `channel: 'chrome'`, Lighthouse `CHROME_PATH=/usr/bin/google-chrome`). One real, paid `claude-opus-5-5` call (the live Ask check, logged at $0.03024).

Acceptance checks (plan Phase 9): Lighthouse on the home page Performance ≥ 85 and Accessibility ≥ 95; works at 375 px and on desktop; both themes look right.

### Automated checks (final state)
| Command | Result |
|---|---|
| `pnpm lint --deny-warnings` (oxlint) | no warnings |
| `pnpm typecheck` | no errors |
| `pnpm test` (Vitest) | `Tests 10 passed (10)` |
| `pnpm build` | `✓ built`; main chunk 352.5 kB (110.9 kB gzip), Dashboard chunk 397.2 kB (113.3 kB gzip, Recharts) |
| `pnpm e2e` (Playwright, API mocked) | `1 passed (7.9s)` |
| `ruff format --check .` / `ruff check .` / `mypy app` | `75 files already formatted` / `All checks passed!` / `Success: no issues found in 42 source files` |
| `TEST_DATABASE_URL=...newsdc_test pytest -q` | `373 passed` (new: `test_search_sort_latest_keeps_hits_newest_first`) |

Failures on the way, and fixes:
- `tsc`: `Property 'error' does not exist on type 'never'` in `Feed.tsx` after the early `isError` return. Fixed by destructuring `error` before the returns.
- oxlint: `only-export-components` (hooks exported from component files), `refs` (ref read during render), `set-state-in-effect` (search box synced from the URL). Fixed: hooks moved to `src/lib/filters.ts`, `useCallback` for the help dialog opener, the search box is re-keyed on the URL query.
- pytest collection: `SyntaxError: parameter without a default follows parameter with a default` after adding `sort` to `/search`. Moved the parameter last.
- E2E: two "Read original" links matched (a hidden per-card link for `Shift+O`). That link was also redundant for screen readers; the card now carries the URL in `data-original`. Second failure: pressing `t` after clicking the page body didn't toggle the theme (the click landed on an element in the page); the test now presses `Esc` to leave the question box.
- Lighthouse a11y on `/dashboard`: 97, `aria-hidden-focus` (Recharts 3 makes charts focusable inside the `aria-hidden` wrapper that is backed by a table view). Fixed with `accessibilityLayer={false}`; rerun 100.
- First screenshot of `/dashboard` showed the per-day line stopping at 11-01: the screenshot was taken during Recharts' animation (the API returns all 60 days). Chart animation turned off.

### Lighthouse 13.6.0 (`pnpm dlx lighthouse@13.6.0 http://localhost:4173/ --chrome-flags="--headless=new"`)
| Page | Mode | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|---|
| `/` (home) | mobile (default), run 1 | **88** | **100** | 100 | 100 |
| `/` (home) | mobile, run 2 | **90** | **100** | | |
| `/` (home) | `--preset=desktop` | **94** | **100** | | |

Run 1 details: TBT 310 ms, CLS 0.139, unused JS ~56 KiB. Run 2: LCP 0.8 s, CLS 0. Desktop: LCP 0.7 s, CLS 0.151. Accessibility only (mobile): `/article/4561` 100, `/dashboard` 100 (after the fix above), `/ask` 100, `/search?q=cooling` 100, `/topics` 100, `/trending` 100, `/admin` 100. The scores were taken against a local API, so they leave out network latency to a real server.

### Responsive and themes (agent check, not human)
A Playwright script opened 10 routes (`/`, `/trending`, `/topics`, `/topics/cooling`, `/article/4561`, `/search?q=liquid cooling`, `/dashboard`, `/ask`, `/admin`, `/bookmarks`) at 1366×900 in light mode and 375×812 in dark mode on live data, took screenshots and checked `scrollWidth > innerWidth`. Result: no horizontal overflow on any route, no page errors; the only console errors were the expected `401` from `GET /admin/session` before login. From the screenshots, two mobile fixes: filters now wrap two per row, and "Your interests" moved into a collapsible section under the topic picker.

### Live checks on real data
- **Admin** (token read from `.env` by the script, never printed): wrong token shows "Wrong token."; correct token shows the dashboard (11 sources, 3 jobs); `Pause hn` then `Resume hn` (CSRF-protected `PATCH`) both answered "done"; the session survived a reload (`GET /admin/session`); logout returned to the login form. No paid actions were triggered.
- **Ask NewsDC** through the UI: "Which hyperscalers are investing in new data centers?" streamed an answer with 8 citation links and 8 source cards; every `#src-0-n` link target exists. Server log: `sources 8, cited 5, removed_citations 0, tokens_in 4074, tokens_out 660, latency_ms 6979, cost_usd 0.03024`.

### Not checked
- Human review of the UI in both themes and at phone width (pending).
- Safari/Firefox (only Chrome was used).
- CI on GitHub (not pushed); the new CI steps (`pnpm test`, Playwright install, `pnpm e2e`) ran only locally.

## Phase 10 (2026-11-10)

### Local checks
| Command | Result |
|---|---|
| `ruff format --check . && ruff check . && mypy app` (backend `.venv`; `uv` isn't installed, R-002) | `75 files already formatted`, `All checks passed!`, `Success: no issues found in 42 source files` |
| `pytest -q` | `257 passed, 118 skipped` (2 new: `test_cache_control`, `test_cached_reuses_value_until_expiry`). DB tests **not run locally**: the local test Postgres on port 55433 was down (`Connection refused`); CI runs them |
| `pnpm lint --deny-warnings && pnpm typecheck && pnpm test && pnpm build` | all pass |
| `pnpm audit --prod --audit-level high` | `No known vulnerabilities found` |
| `pip-audit@2.10.1 -r <uv export --no-dev>` (run on the VPS in the `uv:0.13.7-python3.12` image) | `No known vulnerabilities found` |

Bundle (`vite build`, gzip): main `index` 110.95 kB, `Dashboard` (Recharts) 113.36 kB, `Markdown` 35.85 kB, `format` 27.65 kB, CSS 8.25 kB; every other route chunk < 5 kB.

### Production deploy on the VPS (`15.235.142.100`, Ubuntu 26.04 LTS, 2 vCPU, 3.7 GiB RAM)
Docker isn't available on the agent machine (R-001), so the acceptance run was done on the real server instead of locally with `DOMAIN=localhost`.
- `apt-get install docker.io docker-compose-v2`: `Docker version 29.1.3`, `Docker Compose version 2.40.3`. `ufw`: OpenSSH, 80/tcp, 443 allowed, enabled.
- Code copied with `rsync` (commit `c3a1bb3` working tree), `.env` created on the server (mode 600) with new random `POSTGRES_PASSWORD`, `ADMIN_TOKEN`, `SESSION_SECRET`, `BACKUP_PASSPHRASE` (`openssl rand -hex 32`); the Anthropic key and model settings copied from the local `.env` without printing them.
- `docker compose -f docker-compose.prod.yml up -d --build`: `exit=0`. After 50 s `ps`: `backend Up (healthy)`, `db Up (healthy)`, `frontend Up (healthy)`, `worker Up`, `caddy Up`. Image sizes: backend 784 MB, frontend 83 MB.
- From the Caddy container: `wget http://backend:8000/api/v1/ready` → `{"status":"ok","db":"ok","version":"0.1.0"}`; `wget http://frontend:8080/` → the built `index.html`; `/api/v1/topics` → `200`, `cache-control: public, max-age=30`.
- `curl -sI http://127.0.0.1/ -H "Host: news-dc.atinus.co"` → `308 Permanent Redirect`, `Location: https://news-dc.atinus.co/`.
- Caddy's certificate request failed as expected before DNS existed: `DNS problem: NXDOMAIN looking up A for news-dc.atinus.co` (it retries on its own).
- The worker's first scheduled `ingest_all` started on boot (items `new|274` → `new|904` within minutes). A one-off `~/first_load.sh` then runs `app.ingest --all --since-days 365` and `app.pipeline --max-llm-items 5000` once the queue is idle.

### Backup and restore test (§11.10)
`./scripts/backup_db.sh` → `wrote backups/newsdc-20261110T032314Z.dump.gpg (948K)`, file mode `-rw-------`. Decrypted and restored into a scratch database `newsdc_restore_test`: `items 1120 | item_sources 1120 | categories 14 | alembic 0005`, then dropped. Daily cron installed: `0 3 * * * cd /home/ubuntu/newsdc && ./scripts/backup_db.sh >> backups/backup.log 2>&1`.

### HTTPS and smoke test on the live domain
The DNS record the human created is `news-dc` (not `new-dc` as first configured), so `DOMAIN` and `CORS_ORIGINS` were switched to `news-dc.atinus.co`. Caddy log: `certificate obtained successfully`, `identifier: news-dc.atinus.co`, issuer Let's Encrypt.

`curl -sI https://news-dc.atinus.co/` → `HTTP/2 200`, `strict-transport-security: max-age=31536000; includeSubDomains`, the frontend CSP, `cache-control: no-cache`. A hashed asset → `cache-control: public, max-age=31536000, immutable`, `content-encoding: zstd`. Backend access log shows the real client IP (`122.183.45.144`, the agent's public IP), not Caddy's.

`./scripts/smoke_test.sh https://news-dc.atinus.co`:
```
ok   ready
ok   frontend
ok   feed (item 1257)
ok   article
ok   search
ok   ask
ok   admin protected
ok   export
all checks passed
```

### First data load
- 365-day backfill (`app.ingest --all --since-days 365`) after the worker's first scheduled ingest. Two sources failed and were isolated: `github` `HTTP 401` (the token from the local `.env` is rejected by `api.github.com/rate_limit` too; removed on the server, GitHub now runs unauthenticated), `dcd` `HTTP 403` (cause not confirmed; likely the site blocks the datacenter IP).
- **Incident:** `docker compose up -d caddy` (after the domain change) also recreated `backend`, because its `CORS_ORIGINS` had changed, and that killed the CLI pipeline running in it via `exec` at 04:04:31 UTC. Items are stored one transaction each, so nothing was half-written; run 20 (`processed 1557, rejected_ai 874, $0.75`) was left `running` and was closed by hand as `partial`, `stop_reason=interrupted`. The remaining 291 items went through a worker `pipeline` job (job 3, `succeeded`). DEPLOYMENT.md now warns about this.
- Final: `processed 2064`, `rejected_ai 946`, `rejected_prefilter 22`, `duplicate 82`, `new 0`. Classifier spend for all pipeline runs: `$0.91` (estimate).

### Not checked
- Local `docker compose -f docker-compose.prod.yml up` with `DOMAIN=localhost` (no Docker on the agent machine; the VPS run covers the same files).
- Human click-through of the live site and Admin login.

### CI/CD on GitHub
- First push of Phases 0–10. The previous run (42677836217, Phase 9) had failed: `tests/test_api_db.py::test_utc_sessions` opens the app's own engine, and CI didn't set `DATABASE_URL` (default port 5433, `Connection refused`). Fixed by setting it to the CI Postgres.
- Push needed the `workflow` scope on the human's `gh` token (`refusing to allow an OAuth App to create or update workflow`); the human ran `gh auth refresh -s workflow`.
- Run 42755588479 (`fb897a2`): `backend: success` (`375 passed`, `pip-audit`: `No known vulnerabilities found`), `frontend: success`, `images: success`, `deploy: success` (`deployed fb897a2`, backend healthy). Live `/api/v1/ready` → `{"status":"ok","db":"ok"}` afterwards.
- Deploy key: forced command checked by connecting with the key and sending `echo should-not-run; id`; the server ran `deploy.sh` instead.
