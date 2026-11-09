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
