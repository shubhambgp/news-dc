# NewsDC: documents for the second evaluation round

| # | Requested | Document |
|---|---|---|
| 1 | Project presentation: raw data sources, GitHub links, AI models (open-weight or proprietary), local or cloud | [NewsDC_Presentation.pdf](../NewsDC_Presentation.pdf) · [.pptx](../NewsDC_Presentation.pptx) · source [PRESENTATION.md](../PRESENTATION.md). New slides: 6 *Raw data*, 7 *Code, links and where it runs*, 12 *Selecting and ranking by engagement*, 15 *AI models used*, 19 *Build process, time and cost* |
| 2 | Development process and AI usage: research, prompts, files, guardrails, transcripts, time per step, total cost | [2_DEVELOPMENT_PROCESS.md](2_DEVELOPMENT_PROCESS.md) and [PROMPT_LOG.md](PROMPT_LOG.md) (all 87 prompts, 30 sessions, with summaries) |
| 3 | Article selection, ranking and topic identification | [3_ARTICLE_SELECTION_AND_RANKING.md](3_ARTICLE_SELECTION_AND_RANKING.md) |
| 4 | Examples of the AI deviating and how it was corrected | [4_AI_DEVIATIONS.md](4_AI_DEVIATIONS.md) (13 examples) |

## Quick answers

| Question | Answer |
|---|---|
| Raw data | Hacker News (Algolia API), arXiv API, RSS from FT, NYT, Data Center Knowledge, SemiAnalysis, ServeTheHome; DCD and GitHub configured. 3,445 items collected, 2,182 published (live, 16 Nov 2026) |
| Repository | https://github.com/shubhambgp/news-dc (single public monorepo). Live app: https://news-dc.atinus.co |
| AI models | **Proprietary:** Claude Haiku 5.5 (classifier), Claude Opus 5.5 (Ask answers, weekly brief, main coding agent), Claude Fable 5.1 / 5.2 and Sonnet 5.5 (coding-agent sessions). **Open-weight:** BAAI/bge-small-en-v1.5 embeddings (MIT), run locally |
| Local or cloud | Built on a local Linux machine with Claude Code. Deployed on a cloud VPS: OVHcloud, Singapore, 2 vCPU / 4 GB, Docker Compose. LLMs via the Anthropic API |
| Time | ~44 h elapsed (9 Nov 17:18 → 11 Nov 13:15 IST), 13.4 h of active agent-session time |
| Cost | Claude Code: $118.80 at API list prices. Product AI calls: ≈ $2.60. Hosting: see section 2.5 |

## Sources and method

Every number comes from a log, not from memory: the Claude Code session transcripts (timestamps, prompts, token usage), `git log`, the project's `docs/VERIFICATION_LOG.md`, and the live API (`/api/v1/stats`, `/api/v1/items`, 16 Nov 2026). Secrets that appeared in prompts (an API key, a password) are redacted; they were rotated on 11 Nov.
