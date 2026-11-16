# 3. Article selection, ranking and topic identification

Everything below is taken from the code on `main` and from the live site's API on 2026-11-16 (2,182 published items). File references point at the code that does it.

## 3.0 Short answer

| Question | Answer |
|---|---|
| **a. How articles get under a topic** | An item is shown under a topic when it passed the AI filter (relevant, not spam, relevance ≥ 55, quality ≥ 40, not a near-duplicate) and the classifier put that topic among its 1–3 categories. |
| **b. How they are ranked inside a topic** | Four sorts: **Latest** (the default), **Trending** (Hacker News-style gravity on points, comments, coverage and age), **Relevant** (AI relevance + quality with a slow age decay) and **Quality**. Only Trending uses reader engagement. |
| **c. How the topics were chosen** | The 14 topics are the 14 categories the assignment lists, written into `config/categories.yaml` with a description and keywords each. Inside those topics, *rising* tags, companies and technologies are found automatically every week. |
| **Engagement, honestly** | Trending ranks by engagement the way HN does. But only Hacker News exposes engagement (72% of published items). Topic pages open on **Latest**, so the first ranking a reader sees is by date, not engagement. Section 3.4 lists these gaps and the fix. |

## 3.1 a. How articles are selected under each topic

Every item goes through the same funnel. Only items that reach `processed` are visible anywhere in the product (`base()` in `backend/app/api/common.py` filters on `status = 'processed'`).

```
Ingest (7 active sources, hourly)
  → canonical URL + hash: one item per story, every source kept as provenance
  → keyword prefilter (free, no LLM)          rejected_prefilter: 76
  → Claude Haiku 5.5 classifier (JSON schema) 
  → gate: relevant AND not spam AND relevance ≥ 55 AND quality ≥ 40
                                               rejected_ai: 1,097 (each with a reason)
  → local embedding (bge-small) → near-duplicate check (cosine ≥ 0.92)
                                               duplicate: 90
  → processed: 2,182 of 3,445 collected (63%)
```

1. **Collection.** Hacker News through the Algolia API with quoted title-only queries ("data center", "liquid cooling", "hyperscaler", "SMR", …, D-018); arXiv API; RSS from Data Center Knowledge, ServeTheHome, SemiAnalysis, NYT Technology and FT Technology. Each source is in `config/sources.yaml` with its terms URL and allowed fields.
2. **Prefilter** (`pipeline/nodes.py:prefilter`). Items from general sources (HN, NYT, FT) need at least one data center keyword from `categories.yaml` in the title, text or tags, and must look like English. Data center sources skip this step. This removes obvious noise for free.
3. **Classification** (`backend/app/prompts/classify.md`, prompt `classify-v2`). For each item the model returns `is_relevant`, `is_spam`, `relevance_score` (0–100), `quality_score` (0–100), `primary_category`, `categories` (1–3 slugs from the fixed list, enforced as an enum in the JSON schema), content type, summary, insights, entities and a `reject_reason`.
4. **Gate** (`pipeline/nodes.py`, thresholds in `config.py`: `relevance_threshold = 55`, `quality_threshold = 40`). Failing items are stored as `rejected_ai` with the reason (for example `relevance 42 < 55`), visible in Admin.
5. **Near-duplicates.** When two outlets cover the same story under different URLs, the later item is marked `duplicate` of the earlier one and raises the earlier item's *coverage* count instead of appearing twice.
6. **Topic membership.** `GET /topics/{slug}` returns processed items whose `categories` array contains the slug (`api/topics.py`). An item can appear under up to three topics.

**What the screens show**

| Screen | What it lists | Source |
|---|---|---|
| Topics page | 14 cards: item count per topic and the 3 **newest** items | `GET /topics` (`api/topics.py:_topics`) |
| Topic page | All items in the topic, paginated, sortable, filterable by source, type, quality, date | `GET /topics/{slug}?sort=…` |
| Dashboard | Items per *primary* category with average quality, funnel, per source/day, rising topics, weekly AI brief | `GET /stats`, `GET /trends` |

Live counts per topic (an item counts in every topic it has; 2026-11-16):

| Topic | Items | With HN engagement |
|---|---|---|
| AI Compute & GPUs | 1,024 | 79% |
| Regulation | 543 | 87% |
| Economics & Financial Models | 496 | 83% |
| Power & Energy | 490 | 48% |
| Optimization | 462 | 26% |
| Hyperscaler Investments | 408 | 93% |
| Site Selection | 407 | 90% |
| Data Center Infrastructure | 346 | 77% |
| AI / Agentic AI | 229 | 59% |
| Emerging Technologies | 227 | 44% |
| Networking | 222 | 39% |
| Sustainability | 211 | 64% |
| Security | 80 | 86% |
| Cooling | 77 | 53% |

Topics with many arXiv papers (Optimization, Networking, Power) have the least engagement data, because arXiv has no public reader signal.

## 3.2 b. How articles are ranked within a topic

The topic page has a segmented control: Latest · Trending · Relevant · Quality. The choice is kept in the URL (`?sort=trending`). Every sort ends with `published_at DESC, id DESC` so pagination never repeats or skips items (`ORDER` in `api/common.py`). The formulas live once in `backend/app/recommend/scoring.py` and run both in Python and as SQL.

| Sort | Formula | Uses engagement |
|---|---|---|
| **Latest** (default) | `published_at DESC` | No |
| **Trending** | `(1 + points + 2·comments + quality/10 + 5·coverage) / (age_hours + 2)^1.5` | **Yes**: points, comments, coverage |
| **Relevant** | `(0.6·relevance + 0.4·quality) / (1 + age_days/30)` | No (AI scores) |
| **Quality** | `quality_score DESC` | No (AI score) |

**Trending is Hacker News's ranking idea**, extended:
- `points` and `comments_count` come from the HN Algolia API and are refreshed on every hourly run for items from the last 2 days (`REFRESH_OVERLAP` in `ingest/runner.py`), always keeping the higher number.
- Comments count **twice** as much as points. A story people argue about is a stronger signal than one people only upvote, which matches the brief's "engagement and comments".
- `coverage` = other outlets that carried the same story (exact-URL duplicates from other sources + near-duplicates), worth 5 points each. This is the stand-in for engagement on sources that publish no counters: if FT, NYT and DCK all run it, it matters.
- `quality/10` adds at most 10 points, so the AI score breaks ties but never beats real reader activity.
- `(age + 2)^1.5` is HN's gravity: a story must keep earning engagement to stay on top.

Worked example: an HN story 10 hours old with 120 points, 45 comments, quality 70 and one other outlet scores `(1 + 120 + 90 + 7 + 5) / 12^1.5 = 223 / 41.6 = 5.4`. A 10-hour-old FT article with no counters, quality 80 and two other outlets scores `(1 + 0 + 0 + 8 + 10) / 41.6 = 0.46`. Engagement dominates, as intended.

**Elsewhere in the product:**
- **Trending page** (`/feeds/trending`) uses the same formula over all topics, with 24 h / 7 d / 30 d windows.
- **For You** ranks with `0.35·category affinity + 0.25·embedding similarity + 0.15·tag affinity + 0.15·quality + 0.10·freshness`, from the reader's own activity in localStorage (open +1, read 30 s +2, bookmark +3, dismiss −3, ×0.95 daily decay). Every 5th slot is a "Discover" pick from a topic the reader has not read. The empty-profile feed alternates Trending and Relevant.
- **Related** articles: embedding cosine similarity + 0.1 per shared category.

## 3.3 c. How the topics were identified

**The 14 topics are fixed by the assignment.** Section 3B of the brief lists them: Data Center Infrastructure; AI Compute and GPUs; Power and Energy; Cooling; Sustainability (PUE/WUE/carbon); Hyperscaler Investments; Economics and Financial Models; Site Selection; Networking; Optimization; AI/Agentic AI; Security; Regulation; Emerging Technologies. `plan.md` §6 copied that list, and Phase 1 turned it into `config/categories.yaml`:

```yaml
- slug: cooling
  name: Cooling
  description: Data center cooling, including liquid, immersion and direct-to-chip cooling, chillers and heat reuse.
  keywords: [cooling, liquid cooling, immersion cooling, direct-to-chip, cold plate, chiller, cdu, heat reuse, rear door heat exchanger]
```

- The **description** goes into the classifier prompt (`{{CATEGORIES}}` in `classify.md`), so the LLM decides membership from meaning, not from keywords.
- The **keywords** drive only the free prefilter.
- The brief says categories must be *configurable*: they are YAML, seeded on startup, and Admin can rename, re-describe or disable a topic (an Admin edit survives re-seeding, D-014).

**Emerging sub-topics are found from the data**, not configured (`backend/app/ai/trends.py`). Every processed item has AI-extracted tags, companies and technologies. "Rising topics" compares each term's *share* of items in the last 7 days with its share in the 28 days before and lists the biggest gains with the % change. A weekly AI brief (Claude Opus 5.5, Mondays 06:00 UTC) writes up the week from the top 30 items, with checked citations. Both are on the Dashboard.

**Not done:** the 14 topics were not derived from the data (for example by clustering embeddings). The assignment fixed them, so clustering would only have produced the same list with less control.

## 3.4 Engagement-based ranking: where it falls short, and the fix

The brief's goal is to select and rank by reader engagement and comments, the way Hacker News, NYT and FT surface "most read / most discussed". Measured against that:

**What works**
- Trending is engagement-first, with comments weighted above points, coverage across outlets, and time decay. It is the ranking on the Trending page and in the Home "Trending" strip.
- Selection is quality-first: 1,173 of 3,445 items (34%) were removed by the prefilter and the AI gate with a stored reason, and 90 duplicates were folded into coverage.

**Gaps (found while preparing this document, not yet fixed)**

1. **Topic pages default to Latest.** A reader who opens "Cooling" sees the newest items first. Trending is one click away, but the default should be the engagement ranking. The Topics overview card also shows the 3 *newest* items, not the 3 most-discussed.
2. **Only Hacker News has engagement data.** 1,577 of 2,182 published items (72%) carry points and comments; arXiv, FT, NYT, DCK, ServeTheHome and SemiAnalysis publish no public counters (NYT and FT do have "most popular" lists, but no per-article numbers in RSS). Those items rank on coverage and quality only.
3. **HN discussion of non-HN articles is not counted.** For every new FT, NYT or trade-press article the ingester looks up HN threads that link the same URL and stores them as "related discussions" on the article page. Their points and comments are not added to the article's score, and when an article is first found by an RSS feed, a later HN copy of the same URL adds only +5 coverage, not its points.
4. **Most HN items have little engagement.** HN median is 3 points; 302 items have ≥ 10 points, 116 have ≥ 50, 148 have ≥ 10 comments. A few 1,000-point stories can dominate a topic for days because the formula is linear in points.

**Fix (small, about half a day including tests)**

| # | Change | Where |
|---|---|---|
| 1 | Default topic sort `trending`; Topics cards show the top 3 by Trending in the last 30 days | `api/topics.py`, `pages/Feeds.tsx` |
| 2 | Item engagement = the best points and comments across **all** its sources and its HN discussion threads, not only the primary source | `ingest/runner.py` upsert, `item_sources.source_engagement` (already stored) |
| 3 | Add a **Most discussed** sort: comments-first, `log(1 + comments)` | `recommend/scoring.py`, `ORDER` |
| 4 | Log-scale points and comments in Trending so one viral story doesn't swamp a topic | `scoring.trending` |
| 5 | For publishers with "most popular" feeds (NYT has a Most Popular API) record the rank as an engagement signal, where the terms allow it | new source adapter |

These are not deployed, so that the live site matches what was submitted. They can be done on request.
