---
marp: true
theme: default
paginate: true
title: NewsDC
---

<!--
Export: npx @marp-team/marp-cli docs/PRESENTATION.md --pdf   (or the Marp VS Code extension)
Numbers are from the live site on 2026-11-11 and from docs/AI_EVALUATION.md. Refresh them from the Dashboard before presenting.
-->

# NewsDC

### AI-powered discovery for Data Center news and research

https://news-dc.atinus.co

<!--
Speaker: one sentence: "NewsDC is like Hacker News for the data center industry. It collects content, has AI filter and explain it, and gives every reader a personal feed without an account."
-->

---

## The problem

- Data center news is spread over HN, trade press, arXiv, GitHub and financial outlets
- Most of HN is off-topic, and trade press repeats the same announcement many times
- Engineers, investors and researchers want *different* slices: power deals, cooling, GPUs, regulation
- Reading everything to find the 5% that matters doesn't scale

---

## The solution

1. **Collect** from 9 public sources every hour, with no duplicates
2. **Filter and explain** with AI: relevance, spam, 14 categories, content type, summary, insights, scores
3. **Recommend:** Trending, Most relevant, By topic, Related, and **For You** from localStorage (no accounts)
4. **Ask:** questions answered only from stored articles, with real citations
5. **Watch trends:** rising topics and a weekly AI brief

---

## Live demo flow

Home (For You) → article (summary, insights, discussions, related) → bookmark → Topics → Search → **Ask AI** (2 questions) → Dashboard (funnel) → Admin (rejected items, trigger ingestion) → export → theme + `?` shortcuts

<!--
5-MINUTE DEMO SCRIPT
0:00 Home. "First visit: I pick Cooling and Power. The feed adapts. Every item says why it is here, and every 5th item is Discover from a topic I haven't read."
0:40 Open the top article. "Summary, technical and business insights, entities, quality score, the original link, the HN discussion, and 'Also covered by' when several outlets carried it." Press b to bookmark.
1:20 Topics → Cooling. "14 categories, configurable in YAML and in Admin." Then press / and search "liquid cooling". "Hybrid search: full text plus vectors, fused with RRF."
2:00 Ask AI: "What are the latest developments in liquid cooling?" Point at a [n] and click it: it jumps to the source card. "Each number maps to a stored article. Numbers the model invents are removed before they reach the browser."
2:45 Second question: "Which companies are investing in nuclear power for data centers?"
3:15 Dashboard. "3,158 collected, 2,081 published. 30 removed by the free keyword filter, 965 by the AI, 82 near-duplicates. Total AI cost so far is under one dollar."
3:50 Admin: log in, open Rejected items. "Every rejection keeps its reason." Queue an ingestion and show it under jobs.
4:30 Export Markdown, toggle the theme, press ? for the shortcuts.
4:50 "All of it runs on one 4 GB VPS with Docker Compose."
Backup: if the network fails, play the recorded demo video.
-->

---

## Architecture

```
Browser ──HTTPS──> Caddy ──/api/*──> FastAPI ──> Postgres + pgvector
                     └──────────> Nginx (React build)     ▲
Worker (scheduler + durable jobs) ──> sources, Claude API ┘
```

- Backend and worker: one image, two containers. The API never ingests; it enqueues jobs
- Postgres does everything: data, vectors (HNSW), full text, job queue (`SKIP LOCKED`)
- Frontend talks to the backend only through `/api/v1`

<!--
Speaker: the diagrams with more detail are in docs/ARCHITECTURE.md (Mermaid). Why one database: one thing to back up and secure on a small VPS.
-->

---

## Ingestion and the AI pipeline

- Adapters: HN (Algolia), RSS/Atom, arXiv, GitHub. Terms and robots.txt checked per source
- Canonical URL → hash → **one item, many sources** (`item_sources`)
- Every request: SSRF check on each redirect hop, pinned connections, size caps, throttling, retries
- LangGraph per item:
  `normalize → prefilter → classify (Haiku, JSON schema) → gate → embed (local) → near-duplicate → store`
- Spend caps per run and per day. Failed items retry, then are marked `failed`. Jobs dead-letter

---

## AI filtering results

| Funnel (live) | Items |
|---|---|
| Collected | 3,158 |
| Rejected by keyword prefilter (free) | 30 |
| Rejected by AI (with reason) | 965 |
| Near-duplicates | 82 |
| **Published** | **2,081** (66%) |

Evaluation (40 hand-labelled items, `classify-v2`): precision **20/22**, recall **20/20**, primary category **16/20** (18/20 lenient).
Cost: **$0.29 per 1,000 articles** with Claude Haiku 5.5.

<!--
Be honest: the 40 labels were made by the agent and I still have to review them. v2 was tuned after run 1 on the same items, so its numbers are optimistic.
-->

---

## Recommendations

- **Trending:** HN-style gravity: `(1 + points + 2·comments + quality/10 + 5·coverage) / (age_h + 2)^1.5`
- **Most relevant:** `(0.6·relevance + 0.4·quality) / (1 + age_days/30)`
- **Related:** embedding cosine + 0.1 × shared categories
- **For You:** a localStorage profile (open +1, read 30 s +2, bookmark +3, dismiss −3, ×0.95 daily decay)
  `0.35 category + 0.25 embedding + 0.15 tag + 0.15 quality + 0.10 freshness`
  20% discovery slots, and a "why" on every item. The server stores nothing

---

## Ask NewsDC (RAG with citations)

1. Hybrid retrieval (full text + pgvector, RRF) → top 25 → re-rank to 8
2. Sources go in as escaped `<source n>` blocks; source text is treated as data, never as instructions
3. Streamed over SSE: `sources` → `token`* → `done`
4. `CitationFilter` removes any `[n]` that isn't a supplied source, even when split across chunks
5. No evidence means a fixed answer and **no LLM call**
6. Per-IP, global (30/min, 500/day) and concurrency limits cap the spend

Live: 5/5 example questions answered with valid citations, $0.02–$0.04 per answer.

---

## Tech choices and trade-offs

| Choice | Why | Cost |
|---|---|---|
| Postgres for everything | One service; hybrid search in one query | Not for millions of items |
| Haiku classifies, Opus answers | Cheap at volume; quality where users see it | Ask needs strict limits |
| Local embeddings (bge-small) | Free, private, no second provider | Lower quality than hosted models |
| localStorage profile | No personal data, works on the first visit | No sync across devices |
| Prefilter before the LLM | Removes obvious noise for free | Can miss items with unusual wording |
| Vite SPA, not Next.js | Static build, no Node server | No SSR |

---

## Security

- Admin: token login → HMAC-signed `HttpOnly` cookie, CSRF token + Origin check, login rate limit, disabled without strong secrets
- SSRF: public-address check on every hop, pinned connections (no DNS rebinding), no env proxies
- XSS: Markdown without raw HTML; model-written links shown as plain text; CSP from Caddy
- Limits: per-IP (IPv6 by /64), a global Ask budget, body size caps, strict schemas
- Deploy: no public DB port, `cap_drop: ALL`, non-root images, encrypted backups, dependency audits in CI
- An external-style audit found 24 issues (0 critical, 1 high: Ask spend). All are triaged and fixed or accepted (D-040)

---

## How AI coding agents were used

- **Claude Code built it phase by phase from `plan.md`:** code, migrations, tests (388 backend, 12 Vitest, Playwright E2E) and docs
- **Agent-run operations:** backfills, the classifier evaluation, live checks, the VPS setup with my credentials
- **AI in the product:** classification, summaries and insights, the RAG assistant, the weekly trend brief
- **AI review:** a security audit (24 findings), then a code-review pass of the fixes: 6 low findings, all fixed with regression tests
- **Guard rails:** a verification log with only real command output, "pending human verification" until I confirm, decisions recorded as D-001…D-040
- **I did:** the review of every phase, the domain and DNS, the API keys, and the product decisions

---

## Challenges and how they were solved

- **Title-only HN items failed the quality gate** (recall 15/20) → prompt v2 rates headline specificity (recall 20/20)
- **RRF scores too close together** (rank 2 = 98% of rank 1) → re-rank on rank position, not raw score
- **A container recreate killed the first production pipeline run** → everything goes through durable jobs with leases
- **Concurrent ingest deadlocked in CI** (8 parallel runs: 11/25 failed) → a per-source transaction advisory lock, then 0/25
- **Forced `tool_choice` was rejected by current models** → structured outputs with a JSON schema
- **Publishers that forbid crawling** → a source register; feeds disabled when robots.txt says no

---

## Future enhancements

- Optional accounts with sync (keeping anonymous mode)
- More sources: SEC 8-K filings, utility interconnection queues, conference talks
- A learned ranking model from click data
- An entity graph (companies ↔ sites ↔ power deals) and a map of announced sites
- Alerts ("a new hyperscaler campus in region X")
- Local models (Ollama) for classification, multilingual ingestion, an RSS digest

---

# Thank you

- Live: https://news-dc.atinus.co
- Code: README.md, docs/ARCHITECTURE.md, docs/AI_CONFIG.md
- Who did what: docs/AI_AGENT_LOG.md · Evidence: docs/VERIFICATION_LOG.md

Questions?
