# NewsDC

AI-powered discovery platform for Data Center news and research.

> Status: **Phase 3 (AI pipeline)**. See [docs/PHASE_STATUS.md](docs/PHASE_STATUS.md) and [plan.md](plan.md) for the build plan.

## Quick start (Docker)

```bash
cp .env.example .env          # fill in values; never commit .env
docker compose up --build    # backend runs `alembic upgrade head`, then seeds config/ on startup
curl localhost:8000/api/v1/health   # {"status":"ok","db":"ok","version":"0.1.0"}
open http://localhost:5173          # status page
```

API docs (OpenAPI): http://localhost:8000/api/v1/docs

## Quick start (without Docker)

Requires Python 3.12 via [uv](https://docs.astral.sh/uv/), Node 24 + pnpm, and a Postgres you can reach through `DATABASE_URL`.

```bash
# backend
cd backend
uv sync
uv run alembic upgrade head                # create/upgrade the schema (needs pgvector in Postgres)
uv run uvicorn app.main:app --reload       # http://localhost:8000
uv run python -m app.ingest --all --since-days 365   # backfill every enabled source
uv run python -m app.ingest --source hn              # one source; default window = since last success
uv run python -m app.pipeline --limit 100  # classify new items (needs ANTHROPIC_API_KEY + CLASSIFIER_MODEL)
uv run python -m app.worker                # scheduled ingest -> pipeline via the durable jobs table
uv run python -m app.jobs list             # jobs; also: enqueue <kind> | retry <id> | cancel <id>
uv run python scripts/eval_classifier.py   # classifier evaluation (about 40 paid LLM calls)

# frontend
cd frontend
pnpm install
pnpm dev                                   # http://localhost:5173
```

## Checks (same as CI)

```bash
cd backend  && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest -q
# DB integration tests run only when TEST_DATABASE_URL points at a THROWAWAY pgvector database:
TEST_DATABASE_URL=postgresql+psycopg://newsdc:newsdc@localhost:5433/newsdc_test uv run pytest -q
cd frontend && pnpm lint --deny-warnings && pnpm typecheck && pnpm build
```

## Layout

```
backend/   FastAPI app (app/), Alembic migrations (alembic/), tests, uv project
config/    categories.yaml (14 categories) and sources.yaml (verified sources), seeded into the DB on startup
frontend/  React 19 + Vite + TypeScript + Tailwind + shadcn/ui
docs/      logs, decisions, risks, phase status
```

## Ingestion

Sources live in `config/sources.yaml`; each one was checked for a working endpoint, terms and robots.txt
(see [docs/SOURCE_REGISTER.md](docs/SOURCE_REGISTER.md)). Adapters are in `backend/app/ingest/`
(`hackernews`, `rss`, `arxiv`, `github`). The runner (`runner.py`) dedupes by canonical-URL hash in the
database, records each source's provenance in `item_sources`, writes one `pipeline_runs` row per source,
and checkpoints progress so an interrupted backfill resumes. One failing source never stops the others.

## AI pipeline

`backend/app/pipeline/graph.py` is a LangGraph graph run once per new item:
`normalize -> prefilter -> classify (LLM) -> gate -> embed -> near_duplicate_check -> store`.
The keyword pre-filter costs nothing; the classifier uses the prompt in `backend/app/prompts/classify.md`
with structured JSON output, validated by Pydantic. Rejected items keep their annotation and reason.
Spend is capped per run (`MAX_LLM_ITEMS_PER_RUN`) and per day (`DAILY_LLM_BUDGET_USD`).
The worker enqueues jobs into a Postgres `jobs` table (claims with `SKIP LOCKED`, leases, retries,
dead letters). Details: [docs/AI_CONFIG.md](docs/AI_CONFIG.md), evaluation: [docs/AI_EVALUATION.md](docs/AI_EVALUATION.md).
