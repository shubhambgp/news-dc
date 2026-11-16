# 4. Examples of the AI going off course, and how it was corrected

Each example gives what happened, how it was noticed, the prompt that corrected it, and the result. Timestamps are IST from the session transcripts; the prompts are quoted as typed. The examples are in order of impact.

| # | Deviation | Noticed by | Correction |
|---|---|---|---|
| 1 | Committed security-audit reports and a demo recorder to a public repo | Human, reviewing the commit | Revert, move to gitignored `temp/` |
| 2 | Reported the deliverables as done when GitHub still had old docs and the deck was not exported | Human, pushing back | "Really each point is done properly? Please verify it" |
| 3 | Marked phases 1–9 as passing while CI had never run and was in fact red | Human question about CD | First push, CI fixed |
| 4 | AI-written code had 24 security findings, one high (unlimited Ask spend) | Human, using a second model as auditor | Audit, triage of false positives, fixes on a separate branch |
| 5 | A CI failure dismissed as flaky was a real deadlock | Human: "Fix this failed CI" | Reproduced, fixed with an advisory lock |
| 6 | Justified the LLM choice with "the brief mentions it" | Human challenge | Cost/quality comparison; Haiku for volume, Opus for answers |
| 7 | Classifier prompt v1 rejected most real HN news | Agent's own evaluation | Prompt v2, recall 15/20 → 20/20 |
| 8 | Left local servers in a broken state | Human bug report | Diagnosed stale container and CORS ports |
| 9 | Security fixes mixed into the UI branch | Agent flagged; human decided | Separate branch and PR |
| 10 | Plain default UI | Human, with reference designs | Two redesign rounds on a feature branch |
| 11 | Deployment steps: SSH key blocked, wrong DNS assumption | Human | Explicit permission; human corrected the record name |
| 12 | Agent kept re-checking "pending" items during submission | Human | "do not check if anything is pending" |
| 13 | Topic pages rank by date by default, not by engagement | Found while writing this document | Documented with a fix plan (see section 3.4) |

---

### 1. Private audit files committed to a public repository

- **When:** Wed 11 Nov, 12:14–12:22, session `83c44478`.
- **What happened:** asked which uncommitted files to leave out, the agent listed them. After "create a temp folder gitignore it and commit rest of it", it committed `security-audit/` (reports naming the server and its weak spots) and the demo-recording script into the public repo. Removing a `.gitignore` line also briefly pulled a 21 MB demo video into the commit.
- **How it was noticed:** reviewing the commit before pushing.
- **Correction prompt:** *"revert the last commit, remove from locally i haven't pushed it yet, then move security audit, record demo and other non related stuff into temp and commit the rest"*
- **Result:** commit reverted before any push; audit, recorder, video, assignment PDF and generated deck moved to a gitignored `temp/`. Lesson kept: "commit the rest" is not permission to publish sensitive files. The agent had said in an earlier session that the audit should stay out of git, and did not apply that here.

### 2. "Done" that wasn't done on GitHub

- **When:** Wed 11 Nov, 10:38, session `6a56bd02` (Claude Fable 5.1).
- **What happened:** a gap analysis said every deliverable was built.
- **Correction prompt:** the human pasted the deliverables list from the assignment and asked *"Realy each point is done properly? Please verify it"*.
- **Result:** checked against the live site and the GitHub repo instead of the status docs, the agent found the README on GitHub was the old 77-line version, the presentation was only a Markdown file never exported, and the Phase 11 branch was not pushed or deployed. All three were fixed: branch merged and deployed, deck themed and exported to PDF/PPTX. Lesson: verify against what a reviewer will see, not against the agent's own logs.

### 3. CI marked "blocked", but actually red

- **When:** Tue 10 Nov, 09:46–09:53, session `c345c4da`.
- **What happened:** from Phase 1 to Phase 9 the status file said "CI on GitHub: BLOCKED (not pushed)". That was true, but it meant nine phases were marked passing without the database tests ever running in CI.
- **How it was noticed:** the human asked *"is CI/CD fixed, if i push will it deploy on the vps ?"*. The agent answered that CI had never run and there was no CD, then set up push-to-deploy.
- **Correction prompt:** *"done, push it and watch the run"*
- **Result:** the first GitHub run failed: a database test needed `DATABASE_URL` in CI, and earlier runs were red too. Fixed in `fb897a2`; the next run was green (375 tests) and deployed by itself. Since then a red check blocks deploys.

### 4. Security issues in AI-written code, found by a second model

- **When:** Tue 10 Nov 23:04 (audit) → Wed 11 Nov 09:44 (fixes), sessions `424e8ba8`, `78640d66`, `5c57f1a1`.
- **What happened:** the code passed its own tests and reviews, but an independent audit run on a **different model** (Claude Fable 5.2, with a detailed red-team prompt written by the human) found 24 issues: 0 critical, 1 high. The high one: Ask NewsDC calls a paid model and had only per-IP limits, so anyone rotating IPs could run up the bill.
- **Correction prompt:** *"These are security audits please look for false positive and fix actual problem in the codebase"*
- **Result:** each finding triaged in `docs/SECURITY.md` (D-040): a global Ask cap (30/min, 500/day) and 8 concurrent streams, pinned connections against DNS rebinding, `cap_drop: ALL`, API docs off in production, and more. False positives and accepted risks are recorded with reasons. A follow-up code review of the fix commit found 6 more low issues, fixed with tests (`66b71d2`). Lesson: use a second, independent model as the reviewer, and make it argue rather than confirm.

### 5. A "flaky test" that was a real bug

- **When:** Wed 11 Nov, 09:34, session `5c57f1a1`.
- **What happened:** the PR for the security fixes failed CI on `test_concurrent_runs_do_not_duplicate`, while the same code had passed on the branch push and on `main`. The easy answer was "flaky, re-run".
- **Correction prompt:** *"Fix this faild CI"* (with a screenshot of the failed run).
- **Result:** the agent reproduced it: 0 failures in 40 runs as written, but 11 of 25 with 8 concurrent runs, all Postgres deadlocks. Concurrent ingests of the same source could deadlock in production (CLI ingest alongside the worker). Fixed with a per-source transaction advisory lock: 0 of 25 failures, and the test now runs 8 concurrent ingests so it would catch a regression (`a5254a2`).

### 6. "Why Anthropic?" answered with "the brief said so"

- **When:** Mon 9 Nov, 18:51–18:55, session `83e535a5`.
- **What happened:** asked *"why we choose antrophic model for this project instead of other model like openAI, Gemini, deepseek etc?"*, the agent's main reason was that the brief names Anthropic. The brief actually lists "Claude, Qwen, Ollama or another suitable LLM", so that is an option, not a requirement, and the plan had never compared providers.
- **Correction prompt:** *"Compare all the model and tell me which is most suitable for this project. Cost and performance is the major factor"*
- **Result:** a price table across Anthropic, OpenAI, Google and DeepSeek with a per-1,000-article cost estimate. The cheap Claude Haiku 5.5 tier tied for the lowest price, and the code already relied on structured outputs and prompt caching. Final split: Haiku 5.5 for the high-volume classifier (about $0.29 per 1,000 articles, measured), Opus 5.5 only for user-facing answers and the weekly brief. The agent also noted that its non-Anthropic prices came from aggregator sites and should be checked.

### 7. Classifier prompt v1 rejected most real Hacker News stories

- **When:** Mon 9 Nov, Phase 3, session `bafb9ee1`.
- **What happened:** prompt v1 said "a title-only item cannot score above 60". The model read it as "score title-only items low", so real HN headlines (relevance 85–92) got quality 30–35 and were cut by the quality gate. Recall was 15/20 on the evaluation set.
- **How it was noticed:** the evaluation script required by the plan (`scripts/eval_classifier.py`, 40 labelled items).
- **Result:** prompt v2 rates a title-only item by how specific the headline is (concrete headline 45–60, vague or clickbait below 40). Precision 20/22, recall 20/20 (D-028). The caveat is written down: the agent labelled the 40 items and the same items informed v2, so the numbers are optimistic. Phase 3 was marked human-verified only on 11 Nov, after the human's review.

### 8. Local app broken by leftover servers

- **When:** Wed 11 Nov, 02:33–02:42, session `a6159733`.
- **What happened:** after the UI redesign session, Admin and Ask failed locally. The agent had left Vite servers on ports 5199 and 4173, which the backend's CORS list doesn't allow, and the Docker frontend container still held a 33-hour-old `node_modules` that no longer matched the new dependencies.
- **Correction prompts:** *"Admin and Ask is not working, fix it"*, *"kindly run it"*, *"I want both runinf"*.
- **Result:** frontend image rebuilt with a fresh volume (`up -d --build -V frontend`), both features checked with curl through the right port, and the agent explained why the other ports fail. No code change was needed.

### 9. Security fixes mixed into the UI branch

- **When:** Wed 11 Nov, 09:20–09:24, session `5c57f1a1`.
- **What happened:** the audit fixes were made in the working tree while `feat/ui-redesign` was checked out, so they would have shipped inside the UI PR. The agent flagged it itself.
- **Prompt:** *"what you suggest to push security in new branch or same main branch?"* → *"Make new branch and commit code there"*
- **Result:** moved to `fix/security-audit`, reviewed as PR #2, merged after the UI PR #1. A merge conflict with `main` was resolved by merging instead of rebasing, because the permission system blocked the force push a rebase needs.

### 10. The UI looked like a default template

- **When:** Wed 11 Nov, 00:10–02:32, session `01282cc5`.
- **What happened:** Phase 9 met its acceptance checks (Lighthouse accessibility 100, performance 88–94), but the UI was a plain text list in shadcn's default grey theme.
- **Correction prompts:** *"Before this I want to make UI better. Is it possible to create design like this or give me some suggestion to make beautiful design"* (with two reference screenshots), then *"New branch cut krke switch kro then frontend-only se start kro"* (cut a new branch and start with frontend-only work), then a detailed 9-phase redesign brief that forbade any backend, API or AI change.
- **Result:** the agent said real thumbnails would need backend work and a terms review, and proposed category artwork instead. The redesign ran in 9 committed phases on `feat/ui-redesign`, each with lint, tests, Lighthouse and screenshots at 7 widths in both themes. The agent stopped after each phase as CLAUDE.md requires, until the human said *"Complete each pahse and continue to next one till all the phase completed"*. One change from the brief: the brief put sections below an infinite feed, where nobody could reach them, so Home got a "Show more" button instead.

### 11. Deployment: permissions and DNS

- **When:** Tue 10 Nov, 08:39–09:51, session `c345c4da`.
- **What happened:** installing an SSH key on the VPS was blocked by the agent's permission classifier, so it worked with the password and asked the human to install keys. After the DNS record was added it restarted Caddy for a certificate, while the human was still unsure the record was right (the first prompt also misspelled the domain as `new-dc`).
- **Correction prompts:** *"i added news-dc in name of A record, it might be domain propogation (maybe) but that is our sub domain"* (interrupting the agent), later *"you are allowed to install the keys, just run those commands and set the values into github"*.
- **Result:** HTTPS on `news-dc.atinus.co`, a deploy key and GitHub secrets set by the agent with explicit permission. The agent repeatedly asked for the credentials pasted in chat (Anthropic key, VPS password, admin token) to be rotated; the human rotated them on 11 Nov.

### 12. Over-checking during submission

- **When:** Wed 11 Nov, 12:56, session `bbbad416`.
- **What happened:** every new session re-audited "pending" items from the status docs, even after the human had verified everything.
- **Correction prompt:** *"the project is now complete, do not check if anything is pending. assume everything is complete. now write a mail to HR"*
- **Result:** the agent wrote the email directly. Earlier, after the human confirmed the token rotation and verification (*"Maine token rotate kr diya hai. Human bhi verify ho gya hai."*, "I've rotated the token, and human verification is done too"), the agent updated every status file to "Verified by human" and did not mark anything verified before that confirmation.

### 13. Topic ranking defaults to date, not engagement

- **When:** found on 16 Nov while preparing [3_ARTICLE_SELECTION_AND_RANKING.md](3_ARTICLE_SELECTION_AND_RANKING.md).
- **What happened:** the plan said "topic-based = category filter + one of the sort modes", and the agent picked `latest` as the default for topic pages. The assignment's intent (rank by engagement, like HN, NYT, FT) was met on the Trending page but not on topic pages, and HN points for articles first found via RSS are not counted.
- **Status:** not yet changed, so the live site stays as submitted. The fix is in section 3.4.

## How course correction was built into the process

- **One phase per session**, each ending with acceptance checks, real command output in `VERIFICATION_LOG.md`, and a stop for review (plan.md §2, CLAUDE.md). This is why most corrections happened at phase boundaries.
- **Nothing marked human-verified until the human said so.** The agent kept "pending human verification" in the logs until 11 Nov.
- **Every deviation from the plan is a numbered decision** (D-001 to D-041 in `docs/DECISIONS.md`): 41 times the agent found that the plan, a library or a source behaved differently and wrote down what it did instead (for example D-017: two sources disabled because robots.txt forbids crawling; D-024: forced tool use rejected by current models, structured outputs used instead).
- **A second model as reviewer** (Fable 5.2 for the audit, Fable 5.1 for the assignment gap analysis) rather than the model that wrote the code.
