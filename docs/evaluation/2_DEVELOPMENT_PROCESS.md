# 2. Development process and AI usage

How NewsDC was built, from the assignment PDF to the live site, with the prompts, the time each step took and what it cost. Sources: the 30 Claude Code session transcripts (`~/.claude/projects/…/*.jsonl`), `git log` (62 commits), and the project logs in `docs/`. All times are IST (UTC+5:30).

> Items marked **[TO CONFIRM]** happened outside Claude Code, so no transcript or file records them. They are the only parts of this document not backed by a log.

## 2.0 Summary

| | |
|---|---|
| Calendar time | Mon 9 Nov 17:18 (first commit) → Wed 11 Nov 13:15 (final deck), about **44 hours elapsed**, plus planning before 9 Nov 17:18 |
| Time with the agent working | **≈ 13.5 hours** of active session time across 30 Claude Code sessions (gaps over 30 min excluded) |
| Human prompts | **87** (counting interruptions) |
| Coding agent | Claude Code CLI, mostly Claude Opus 5.5 (1,329 of 1,446 model calls) |
| Cost of the AI coding agent | **$118.80** at Anthropic API list prices (token counts from the transcripts); what was actually billed depends on the plan, **[TO CONFIRM]** |
| Cost of AI inside the product | **≈ $2.60** recorded so far (classification of ~7,300 item runs locally and on the VPS, evaluation, test questions, two weekly briefs) |
| Result | Live at https://news-dc.atinus.co, code at https://github.com/shubhambgp/news-dc, 388 backend tests, 12 Vitest, 1 Playwright E2E |

## 2.1 a. Initial research and planning

**1. The brief.** The assignment PDF (`NewsDC_Recruitment_Assignment v1.0.pdf`, 2 pages) asks for an HackerTube-style discovery platform for data center news, with a fixed list of 14 categories, an AI filter, recommendations without accounts, a RAG assistant, a deployed URL, and 9 deliverables in 3–4 working days. It names two references: HackerTube, and https://hn.algolia.com/?q=llmwiki for the assistant.

**2. The plan.** Before any code, a 972-line build plan was written: `plan.md` (committed at 17:30 on 9 Nov, 12 minutes after `git init`). It fixes the stack with a reason per choice, the data model, the 14 categories, 12 build phases (0–11) with acceptance checks, the human's manual tasks, standard prompts for the agent (§14), required control files (§15) and release gates (§16). After a review, §11 "Mandatory corrections" was added and overrides earlier sections: Vite instead of Next.js, a many-to-many source-to-item model, URL rules, durable jobs, provider cost controls, source compliance, RAG citation rules, security additions, and dataset integrity.
- How plan.md was produced: **[TO CONFIRM: e.g. drafted in a claude.ai / ChatGPT conversation from the PDF, then reviewed and corrected by hand; name the tool and the prompt]**.
- Websites and repositories the human looked at while planning: **[TO CONFIRM: e.g. HackerTube, hn.algolia.com, the Algolia HN API docs, DatacenterDynamics, Data Center Knowledge, arXiv API docs, LangGraph, pgvector, fastembed, Anthropic pricing]**.

**3. Research the agent did during the build** (from the transcripts: every URL in a tool call). Each source was checked live before it was enabled, including its robots.txt and terms:

| Purpose | Sites and APIs visited by the agent |
|---|---|
| Hacker News | `hn.algolia.com` (Algolia HN Search API: query behaviour, 1,000-hit cap, D-018), `news.ycombinator.com`, `www.ycombinator.com` (terms) |
| Research | `export.arxiv.org` (arXiv API), `info.arxiv.org` (API terms of use, 3 s rule), `arxiv.org` |
| Trade press | `www.datacenterknowledge.com`, `www.datacenterdynamics.com`, `www.servethehome.com`, `www.theregister.com` (feed 404, robots.txt denies, disabled), `www.nextplatform.com` (robots.txt denies, disabled), `semianalysis.com` and `newsletter.semianalysis.com`, Informa/TechTarget terms pages |
| Mainstream | `rss.nytimes.com`, `help.nytimes.com` (RSS terms), `www.ft.com`, `aboutus.ft.com`, `help.ft.com` (terms) |
| Code | `api.github.com`, `docs.github.com` (search API, rate limits) |
| AI | `platform.claude.com` (model IDs, pricing, structured outputs, prompt caching); web searches for OpenAI, Gemini and DeepSeek prices for the model comparison |
| Deploy | `hub.docker.com` (pgvector, Caddy images), `pypi.org` |

The outcome of that research is in `docs/SOURCE_REGISTER.md` (source, method, terms, allowed fields) and decisions D-016 to D-023.

**Open-source projects the solution is built on** (from `backend/pyproject.toml`, `frontend/package.json`): [FastAPI](https://github.com/fastapi/fastapi), [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy), [Alembic](https://github.com/sqlalchemy/alembic), [pgvector](https://github.com/pgvector/pgvector), [LangGraph](https://github.com/langchain-ai/langgraph), [anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python), [fastembed](https://github.com/qdrant/fastembed) with [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5), [feedparser](https://github.com/kurtmckee/feedparser), [trafilatura](https://github.com/adbar/trafilatura), [httpx](https://github.com/encode/httpx), [APScheduler](https://github.com/agronholm/apscheduler), [limits](https://github.com/alisaifee/limits), [React](https://github.com/facebook/react), [Vite](https://github.com/vitejs/vite), [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss), [shadcn/ui](https://github.com/shadcn-ui/ui), [TanStack Query](https://github.com/TanStack/query), [Recharts](https://github.com/recharts/recharts), [Caddy](https://github.com/caddyserver/caddy), [Marp CLI](https://github.com/marp-team/marp-cli) (deck), [Playwright](https://github.com/microsoft/playwright). Agent skills came from [affaan-m/ecc](https://github.com/affaan-m/ecc) (pinned by hash in `skills-lock.json`).

## 2.2 b. How AI was employed

### The harness

- **Tool:** Claude Code CLI, running on the developer's Linux machine, in a terminal next to VS Code (the transcripts show the IDE's "file opened" events).
- **Repository files given to the agent as context**
  - `plan.md`: the source of truth. Every phase prompt starts with "Read plan.md".
  - `CLAUDE.md`: generated with `/init` after Phase 1 (commit `f8dc1ea`), then kept up to date. It holds the working rules, the commands and an architecture map, and is loaded into every session automatically.
  - Four project skills in `.claude/skills/` (`python-patterns`, `frontend-patterns`, `backend-patterns`, `coding-standards`), pinned in `skills-lock.json`. CLAUDE.md says which one to load for which code.
  - Built-in Claude Code skills the agent loaded when needed: `claude-api` (current model IDs and API features, so nothing was guessed), `dataviz` (dashboard charts).
  - The assignment PDF (attached in sessions `6a56bd02` and `22e3f21e`), and two reference screenshots for the UI redesign.
- **Persistent memory:** one note (`local-env-quirks.md`) so new sessions didn't rediscover machine quirks (uv path, test DB port, snap Docker).
- **Data:** the agent ran ingestion against the real sources and the pipeline against the real Anthropic API, but only from the CLI. Tests never touch the network or a paid API.

### The first prompt

Session `20d11b08`, Mon 9 Nov 17:21, Claude Opus 5.5:

> Read plan.md completely.
> Execute Phase 0 only.
> Follow the Universal Definition of Done.
> Implement all Phase 0 tasks.
> Run all acceptance checks.
> Update all required documentation and logs.
> Review your changes and commit if checks pass.
> Do not start Phase 1.
> Stop and provide the complete Phase 0 report.

Each later phase was one short prompt, because the detail lives in plan.md: *"Complete Phase 4. Done means acceptance checks fullfilles"*. One session per phase kept each context small.

### Guardrails

| Guardrail | Where it is | What it prevents |
|---|---|---|
| One phase at a time, stop for review | plan.md §2, §14.2; CLAUDE.md | Scope creep; unreviewed work piling up |
| Definition of Done per phase: tests, lint, types, acceptance checks, logs, Conventional Commit only if checks pass | plan.md §13 | "Done" without evidence |
| `VERIFICATION_LOG.md`: real commands and real output only | plan.md §2 | Invented test results |
| "pending human verification" until the human confirms | plan.md §2, CLAUDE.md | The agent claiming human sign-off |
| Every deviation recorded as a decision (D-001 … D-041) | `docs/DECISIONS.md` | Silent changes to the plan |
| Model IDs never hardcoded, prompts in versioned files with a pinned hash | CLAUDE.md, D-007, tests | Guessed model names, untracked prompt edits |
| Tests mock the LLM; an autouse fixture makes any real Anthropic call fail | `backend/tests/conftest.py`, `tests/fakes.py` | Paid calls and flaky tests |
| Spend caps per pipeline run and per day; a global Ask budget | `config.py`, D-040 | A runaway bill |
| Claude Code's permission system | harness | Blocked some risky actions (installing an SSH key, a force push) until the human allowed them |
| A second model as auditor | sessions `78640d66`, `6a56bd02` | The authoring model grading its own work |
| CI on every push, deploy only after all checks pass | `.github/workflows/ci.yml`, D-038 | Shipping red builds |

### Who did what

| Done by the agent | Done by the human |
|---|---|
| All code, migrations, tests, Dockerfiles, CI/CD, docs, diagrams, the deck | Wrote and corrected the plan; chose to use Claude Code |
| Ran backfills, the AI pipeline, the classifier evaluation, live smoke tests | Supplied the API key, the VPS, the domain and DNS record, GitHub auth |
| SSH setup of the VPS and push-to-deploy, with permission | Reviewed every phase, tested the app, decided on branches and merges |
| Security audit (second model), triage and fixes | Wrote the audit prompt and the UI redesign brief; asked for verification when claims looked too good |
| Logged every step and its evidence | Rotated leaked credentials; confirmed human verification on 11 Nov |

The per-phase table of tasks, who did them and how they were verified is in `docs/AI_AGENT_LOG.md`.

## 2.3 c. All prompts and session summaries

Every session, with its model, the step it covered and the number of human prompts:

| # | When (IST) | Session | Model | Step | Prompts |
|---|---|---|---|---|---|
| 1 | Mon 9 Nov 17:20 | `20d11b08` | Opus 5.5 | Phase 0: skeleton, CI, control docs | 1 |
| 2 | 17:38 | `261b91e8` | Opus 5.5 | Phase 1: schema, migrations, URL dedup, seeding | 1 |
| 3 | 17:58–18:24 | 4 short | Sonnet/Opus | Docker permissions, skills in CLAUDE.md, commit and push | 5 |
| 4 | 18:24 | `fe5abcdf` | Opus 5.5 | Phase 2: ingestion, 365-day backfill (3,887 items) | 1 |
| 5 | 18:48–18:58 | `a6a609e1`, `83e535a5` | Opus 5.5 | VPS sizing; LLM provider comparison | 3 |
| 6 | 19:33 | `bafb9ee1` | Opus 5.5 | Phase 3: LangGraph pipeline, eval, 2,609 items processed | 7 |
| 7 | 21:04–22:00 | 4 sessions | Opus 5.5 | Phases 4–7: API, recommendations, Ask (RAG), trends | 4 |
| 8 | 22:02 | `730c469a` | Opus 5.5 | Phase 8: admin, security, export | 2 |
| 9 | 23:57 | `47cdb9d4` | Opus 5.5 | Phase 9: the React UI, run locally for testing | 3 |
| 10 | Tue 10 Nov 07:53 | `c503d295`, `b2f30819` | Opus 5.5 | Status, VPS choice, Docker access | 4 |
| 11 | 08:37 | `c345c4da` | Opus 5.5 | Phase 10: VPS deploy, HTTPS, CI/CD | 10 |
| 12 | 23:04–23:45 | `424e8ba8`, `78640d66` | Opus 5.5, **Fable 5.2** | Independent security audit | 2 |
| 13 | 23:50 → Wed 02:32 | `01282cc5` | Opus 5.5 | UI redesign (2 rounds, 9 phases) | 8 |
| 14 | Wed 11 Nov 02:33 | `a6159733` | Opus 5.5 | Fix local Admin/Ask | 3 |
| 15 | 08:47 | `5c57f1a1` | Opus 5.5 | Audit triage and fixes, PR, deadlock fix | 5 |
| 16 | 09:32 | `2c93fe67` | Opus 5.5 | Phase 11: docs, diagrams, deck, code review | 5 |
| 17 | 10:21 | `6a56bd02` | **Fable 5.1** | Assignment gap analysis, demo video, re-verification, deck theme | 5 |
| 18 | 12:14–13:15 | 4 sessions | Opus 5.5 | Repo hygiene, verification status, logo, submission email, PDF/PPTX | 18 |

## 2.4 Time taken per step

Active time is the time a session was in use: agent working or human typing, with idle gaps over 30 minutes removed. It does not include the human's own testing and review between sessions, or the planning before the first commit.

| Step | Sessions | Active time | Elapsed (first → last activity) |
|---|---|---|---|
| Planning (`plan.md`) | outside Claude Code | **[TO CONFIRM]** | before 9 Nov 17:18 |
| Phase 0 — skeleton, CI | 1 | 10 min | 17:20–17:31 |
| Phase 1 — schema, config | 1 | 26 min | 17:38–18:04 |
| Tooling (Docker, CLAUDE.md, skills) | 4 | 4 min | 17:58–18:24 |
| Phase 2 — ingestion and backfill | 1 | 66 min | 18:24–19:31 |
| Model choice, VPS sizing | 2 | 9 min | 18:48–18:58 |
| Phase 3 — AI pipeline, evaluation, full run | 1 | 91 min | 19:33–21:04 |
| Phase 4 — API | 1 | 15 min | 21:04–21:19 |
| Phase 5 — recommendations | 1 | 10 min | 21:20–21:30 |
| Phase 6 — Ask NewsDC (RAG) | 1 | 13 min | 21:33–21:45 |
| Phase 7 — trends, dashboard data | 1 | 10 min | 21:50–22:00 |
| Phase 8 — admin, security, export | 1 | 15 min | 22:02–22:16 (commit), session open until 23:52 |
| Phase 9 — frontend | 1 | 27 min + manual testing | 23:57–00:17 (commit) |
| Status and Docker questions | 2 | 17 min | Tue 07:53–08:11 |
| Phase 10 — deploy, HTTPS, CI/CD | 1 | 90 min | 08:37–09:56 (last commit), session to 14:53 |
| Security audit (second model) | 2 | 30 min | 23:04–23:45 |
| UI redesign | 1 | 166 min | Tue 23:50 → Wed 02:32 |
| Local Admin/Ask fix | 1 | 9 min | 02:33–02:42 |
| Audit triage, fixes, CI deadlock | 1 | 57 min | 08:47–09:44 |
| Phase 11 — docs, diagrams, deck | 1 | 46 min | 09:32–10:19 |
| Gap analysis, demo video, deck theme | 1 | 48 min | 10:21–11:09 |
| Repo hygiene, submission, final deck | 4 | 48 min | 12:14–13:15 |
| **Total** | **30** | **≈ 806 min (13.4 h)** | 9 Nov 17:18 → 11 Nov 13:15 |

The backend (phases 0–8) took about 4.3 hours of agent time, because each phase was already specified in detail. The longest steps were the ones that touched the outside world (the real data backfill, the full AI run, the VPS deployment) and the UI redesign.

## 2.5 Total cost

| Item | Cost | Basis |
|---|---|---|
| **Claude Code (building)** | **$118.80** API-equivalent | Token counts from all transcripts × Anthropic list prices (below) |
| ↳ billed | **[TO CONFIRM: subscription plan (e.g. Claude Max, flat monthly) or API pay-per-use]** | |
| **Anthropic API (the product's own AI)** | **≈ $2.60** recorded | Local full run $1.13 (3,843 annotations); VPS classifier $1.10 and two weekly briefs $0.075 (`/stats`, 16 Nov); local brief $0.063; test questions to Ask ≈ $0.22; evaluation runs ≈ $0.02. Ask questions from site visitors are not in `/stats`; the Anthropic console has the exact total **[TO CONFIRM]** |
| Embeddings | $0 | bge-small runs locally on CPU |
| VPS (OVHcloud, Singapore, 2 vCPU / 4 GB) | **[TO CONFIRM]** | |
| Domain (`atinus.co`, subdomain `news-dc`) | **[TO CONFIRM]** (already owned?) | |
| GitHub repo, GitHub Actions CI | $0 | Public repo, free tier |

**Claude Code token usage by model** (main sessions and their sub-agents, de-duplicated by message ID):

| Model | Calls | Output tokens | Cache writes | Cache reads | Cost at list price |
|---|---|---|---|---|---|
| Claude Opus 5.5 ($4 / $20 per MTok, cache read $0.20) | 1,329 | 1.41 M | 4.66 M | 245.2 M | $100.50 |
| Claude Fable 5.2 (priced as Fable 5.1: $10 / $50, cache read $0.25) | 43 | 0.09 M | 0.29 M | 9.2 M | $10.54 |
| Claude Fable 5.1 ($10 / $50, cache read $0.25) | 58 | 0.06 M | 0.17 M | 8.2 M | $7.24 |
| Claude Sonnet 5.5 ($2 / $10, cache read $0.20) | 16 | 0.005 M | 0.12 M | 0.8 M | $0.52 |
| **Total** | **1,446** | **1.57 M** | **5.24 M** | **263.4 M** | **$118.80** |

Cache writes are priced at the 5-minute rate (1.25× input). If they were 1-hour writes (2× input), the total is $136.40. Uncached input was only ~4,600 tokens: almost everything the agent read came from the prompt cache, which is why 263 M tokens of context cost about $54.

**Product cost at steady state:** about $0.29 per 1,000 articles classified (Haiku 5.5), $0.02–$0.04 per Ask answer and $0.06 per weekly brief (Opus 5.5), with hard caps on all three (`docs/AI_CONFIG.md`).
