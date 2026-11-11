# NewsDC

AI-powered discovery platform for Data Center news and research.

NewsDC collects public content from Hacker News, industry RSS feeds, arXiv and GitHub. Claude filters out spam and off-topic items, sorts the rest into 14 categories, and writes a summary and key insights for each item. You can browse the result as Trending, Most relevant, By topic and a personal **For You** feed (kept in your browser, no account). You can also ask questions and get answers that cite the stored articles.

**Live:** https://news-dc.atinus.co · Version 1.0.0 · [Changelog](CHANGELOG.md)

![Home page](docs/img/home.png)

| Dashboard | Phone (Trending) |
|---|---|
| ![Dashboard](docs/img/dashboard.png) | ![Trending at phone width](docs/img/mobile.png) |

## Features

- **Ingestion:** Hacker News (Algolia API), 6 industry RSS feeds, arXiv and GitHub, every hour. Each source was checked for its terms and robots.txt ([SOURCE_REGISTER](docs/SOURCE_REGISTER.md)). URLs are canonicalized and deduplicated by hash, and every source that found an item is kept (many-to-many provenance). One failing source never stops the others.
- **AI filtering and enrichment:** a LangGraph pipeline with a free keyword prefilter, Claude classification with a strict JSON schema (relevance, spam, categories, content type, summary, technical and business insights, entities, tags, relevance and quality scores), a publish gate, local embeddings and near-duplicate detection. Rejected items keep their reason.
- **Feeds:** For You (from your reading, bookmarks and picked topics, with a "why" on each item and 20% discovery), Trending, Most relevant, By topic, Related and "Also covered by".
- **Search:** hybrid full-text and semantic search with filters, sort and highlighted snippets.
- **Ask NewsDC:** retrieval-augmented answers streamed over SSE. Every `[n]` citation links to a real stored item, and unknown citation numbers are removed.
- **Trends and dashboard:** rising tags, companies and technologies (last 7 days vs the 28 before), a weekly AI trend brief with citations, the ingestion funnel, and per-category, per-source and per-day charts with AI cost.
- **Admin:** token login with a signed cookie, CSRF and rate limiting. Trigger ingestion, pipeline runs and briefs, pause sources, edit categories, view rejected items, and retry dead-lettered jobs.
- **Export:** JSON and Markdown (API, dashboard, bookmarks). The sample dataset of 1,000 real records is in [data/sample/](data/sample/).
- **UI:** light and dark themes, responsive down to 375 px, infinite scroll, keyboard shortcuts (`?` lists them), bookmarks and reading history in localStorage.

## Architecture

```mermaid
flowchart LR
  B[Browser] -->|HTTPS| C[Caddy]
  C -->|/api/*| A[FastAPI]
  C --> F[Nginx: React build]
  A --> P[(Postgres + pgvector)]
  A -->|Ask| L[Claude API]
  W[Worker] --> P
  W --> S[HN, RSS, arXiv, GitHub]
  W -->|classify, brief| L
```

The backend and the worker are separate containers built from one image. The worker schedules ingestion and runs durable jobs from a Postgres `jobs` table. The API only reads data and enqueues jobs. Full diagrams (ingestion workflow, RAG sequence), the ranking formulas and the trade-offs are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, LangGraph, Anthropic SDK, fastembed · PostgreSQL 16 + pgvector · React 19, Vite, TypeScript, Tailwind v4, shadcn/ui, TanStack Query, Recharts · Docker Compose, Caddy, GitHub Actions.

## Quick start (Docker)

```bash
cp .env.example .env           # fill in ANTHROPIC_API_KEY, CLASSIFIER_MODEL, ASSISTANT_MODEL; never commit .env
docker compose up --build      # backend runs `alembic upgrade head`, then seeds config/ on startup
curl localhost:8000/api/v1/health
open http://localhost:5173     # UI;  API docs: http://localhost:8000/api/v1/docs

# first data load (paid LLM calls in the second step, about $0.30 per 1,000 items)
docker compose exec backend python -m app.ingest --all --since-days 365
docker compose exec backend python -m app.pipeline
```

The dev database is on host port 5433.

## Quick start (without Docker)

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24 with pnpm, and Postgres with pgvector reachable through `DATABASE_URL`.

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload                # http://localhost:8000
uv run python -m app.ingest --all --since-days 365  # backfill; --source <key> for one source
uv run python -m app.pipeline --limit 100           # classify new items (paid)
uv run python -m app.worker                         # schedule + run jobs
uv run python -m app.jobs list                      # jobs; enqueue <kind> | retry <id> | cancel <id>

cd ../frontend
pnpm install
pnpm dev                                            # http://localhost:5173
```

## Environment variables

All settings come from `.env` ([.env.example](.env.example) lists every one with a comment). The main ones:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local dev DB | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `ANTHROPIC_API_KEY` | empty | Needed for the pipeline, Ask and the trend brief |
| `CLASSIFIER_MODEL`, `ASSISTANT_MODEL` | empty (no default on purpose) | e.g. `claude-haiku-5-5`, `claude-opus-5-5`. Empty `ASSISTANT_MODEL` makes `/ask` return 503 |
| `CLASSIFIER_*_USD_PER_MTOK`, `ASSISTANT_*_USD_PER_MTOK` | 0 | Prices for cost tracking and the daily budget |
| `DAILY_LLM_BUDGET_USD`, `MAX_LLM_ITEMS_PER_RUN` | 5, 300 | Pipeline spend caps |
| `RELEVANCE_THRESHOLD`, `QUALITY_THRESHOLD` | 55, 40 | Publish gate |
| `ADMIN_TOKEN`, `SESSION_SECRET` | empty | Admin is disabled until both are set (≥ 16 and ≥ 32 chars) |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed browser origins |
| `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_ASK`, `RATE_LIMIT_ASK_GLOBAL` | 60/min, 10/min, 30/min;500/day | Per-IP and all-client limits |
| `INGEST_INTERVAL_MINUTES` | 60 | Worker schedule |
| `GITHUB_TOKEN` | empty | Optional, read-only, for higher GitHub API limits |
| `DOMAIN`, `BACKUP_PASSPHRASE`, `POSTGRES_PASSWORD` | | Production only |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Empty in production (same origin) |

## Tests and checks

The same checks run in CI (`.github/workflows/ci.yml`):

```bash
cd backend && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest -q
# DB integration tests: point at a THROWAWAY database (the tests drop its schema)
TEST_DATABASE_URL=postgresql+psycopg://newsdc:newsdc@localhost:5433/newsdc_test uv run pytest -q
cd frontend && pnpm lint --deny-warnings && pnpm typecheck && pnpm test && pnpm build
pnpm e2e        # Playwright smoke test, API mocked
```

The LLM is always mocked in tests. An autouse fixture fails any real Anthropic call. The classifier evaluation (`uv run python scripts/eval_classifier.py`, about $0.01) is run by hand. The results are in [docs/AI_EVALUATION.md](docs/AI_EVALUATION.md).

## Deployment

Production runs on one VPS with `docker-compose.prod.yml` (Caddy with automatic HTTPS, unprivileged containers, no public DB port). A push to `main` deploys after CI passes. Setup, backups and restore, and the smoke test are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Project structure

```
backend/
  app/            FastAPI app: api/ (routers), ingest/ (adapters, runner), pipeline/ (LangGraph),
                  ai/ (LLM client, classifier, assistant, trends, embeddings), recommend/ (ranking),
                  prompts/ (*.md prompts), models.py, schemas.py, jobs.py, worker.py
  alembic/        hand-reviewed migrations 0001…
  scripts/        eval_classifier.py, export_dataset.py
  tests/          pytest (unit, API, DB integration with a throwaway database)
frontend/src/     React app: pages/, components/, lib/api.ts (the only API client), lib/profile.ts
config/           categories.yaml (14 categories), sources.yaml (verified sources)
data/sample/      1,000-record sample dataset (JSON + Markdown)
scripts/          backup_db.sh, deploy.sh, smoke_test.sh
docs/             architecture, API, AI config and evaluation, security, deployment, decisions, logs
```

## Documentation

| | |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Diagrams, workflow, RAG, ranking formulas, trade-offs |
| [API](docs/API.md) | `/api/v1` contract |
| [AI_CONFIG](docs/AI_CONFIG.md) · [AI_EVALUATION](docs/AI_EVALUATION.md) | Models, prompts, schema, thresholds, costs, evaluation |
| [SECURITY](docs/SECURITY.md) · [DEPLOYMENT](docs/DEPLOYMENT.md) | Controls, audit triage, production setup |
| [DECISIONS](docs/DECISIONS.md) · [RISKS](docs/RISKS.md) · [SOURCE_REGISTER](docs/SOURCE_REGISTER.md) | Deviations from the plan, risks, source terms |
| [AI_AGENT_LOG](docs/AI_AGENT_LOG.md) · [VERIFICATION_LOG](docs/VERIFICATION_LOG.md) · [PHASE_STATUS](docs/PHASE_STATUS.md) | Who did what, real command output, phase status |
| [PRESENTATION](docs/PRESENTATION.md) | Marp slide deck with a 5-minute demo script |

## How AI coding agents were used

The code, tests and docs were written by Claude Code (Claude Opus 5.5), one phase at a time from [plan.md](plan.md). The human reviewed each phase, made the decisions the plan left open, set up the domain, and supplied the credentials. The agent also ran the backfills, the evaluation, live checks and a code review pass whose findings were fixed. Every task is listed with who did it and how it was verified in [docs/AI_AGENT_LOG.md](docs/AI_AGENT_LOG.md). Items still marked "pending human verification" there have not been confirmed by the human yet.

## Limitations and future work

- **Data:** 2 of the 9 enabled sources produce nothing in production: DatacenterDynamics returns 403 to the VPS, and the GitHub token there returns 401 and needs replacing. Two more feeds (The Register, The Next Platform) are disabled because their robots.txt denies crawlers. Most items come from Hacker News and arXiv. The classifier evaluation set has 40 items, was labelled by the agent, and is still awaiting human review.
- **Product:** no accounts, so the For You profile doesn't sync across devices. No email or RSS digest, and no Ollama/local model provider (optional plan items, not built). Server-side rendering and a sitemap aren't done.
- **Ops:** one VPS with no high availability. Backups are local to the server unless copied off.
- **Next:** optional accounts with sync; more sources (SEC 8-K filings, interconnection queues, conference talks); a learned ranking model from click data; an entity graph of companies, sites and power deals; alerts; a map of announced sites; multilingual ingestion.
