# NewsDC Architecture

Phase 11 adds the full system diagrams. This file documents the recommendation engine (Phase 5) for now.

## Recommendation engine

Code: `backend/app/recommend/` (`scoring.py` holds the formulas, `foryou.py` the For You ranking). Each formula is written once as a Python function. The same function runs on plain numbers (unit tests, For You) and on SQLAlchemy columns (the `ORDER BY` of the paginated feeds), so the SQL can't drift away from the documented formula. `test_relevant_feed_matches_the_python_formula` checks this against Postgres.

Ages are measured from `published_at`, or from `fetched_at` when the source gave no date, and are never negative. A missing score or engagement count counts as 0. Every ordering ends with `published_at DESC, id DESC`, so pagination is deterministic.

### Trending (`/feeds/trending`, `sort=trending`)

```
score = (1 + points + 2·comments + quality/10 + 5·coverage) / (age_hours + 2)^1.5
```

This is Hacker News gravity. `points` and `comments` are Hacker News points and comments (GitHub stars count as points). Items from RSS and arXiv have no engagement data, so they rank on quality and coverage alone. `coverage` counts the other outlets that carried the story: near-duplicates whose `duplicate_of` points at the item, plus every extra source in `item_sources` that found the same URL (D-032). Because of gravity, an item loses about 65% of its score between 2 h and 6 h old, so a fresh RSS item soon outranks a three-day-old HN item with 100 points. That is the intended behaviour for a "what's happening now" feed.

### Most relevant (`/feeds/relevant`, `sort=relevant`)

```
score = (0.6·relevance + 0.4·quality) / (1 + age_days/30)
```

The decay is mild. A month-old item keeps half its score, so a strong item from a few days ago still beats a weak one from today. `sort=relevance` (plain `relevance_score`) is unchanged from Phase 4.

### By topic (`/topics/{slug}`)

A category filter, plus any sort: `latest`, `relevance`, `quality`, `trending` or `relevant`.

### Related (`/items/{id}/related`)

```
score = cosine_similarity(embeddings) + 0.1 · shared_categories
```

It takes the 50 nearest processed items by HNSW and returns the top 6. Near-duplicates have the status `duplicate`, so they are never candidates, and the same story isn't shown twice.

### For You (`POST /feeds/foryou`)

The browser keeps an anonymous profile in `localStorage` and sends it with each request. There are no accounts and nothing is stored on the server.

```json
{"categoryWeights": {"cooling": 7.5}, "tagWeights": {"immersion": 3},
 "readIds": [12, 40], "bookmarkIds": [7], "dismissedIds": [99], "explicitTopics": ["cooling"]}
```

**Client side (Phase 9B):** opening an article adds +1, reading for more than 30 s +2, a bookmark +3, "not interested" −3. The +1, +2 and +3 apply to the item's categories and tags. Weights decay ×0.95 per day. `readIds` keeps the last 200 items. A "Reset my preferences" button clears the profile.

**Server side:**
1. **Validation.** The limits are 64 category weights, 200 tag weights, 200 read IDs, 500 bookmark IDs, 500 dismissed IDs and 64 explicit topics. Weights must be finite and within ±1000. Category slugs must exist. Unknown fields are rejected. The body is at most 64 KiB.
2. **Candidates.** These are the newest 1,000 public items, minus read, bookmarked and dismissed items.
3. **Taste.** Category weights, with +5 for each topic picked at onboarding, are divided by the largest absolute weight. The result is in [−1, 1]. Tag weights are normalised the same way and lower-cased. The taste embedding is the average embedding of the 50 most recent reads and the 50 most recent bookmarks.
4. **Score.**
   ```
   0.35·category_affinity + 0.25·embedding_similarity + 0.15·tag_affinity + 0.15·quality/100 + 0.10·freshness
   ```
   An affinity is the strongest weight among the item's categories (or tags). Similarity is the cosine to the taste embedding, clipped to ≥ 0. Freshness is `0.5^(age_days/7)`.
5. **Discovery.** A category is *engaged* if it has a weight (liked or disliked), was picked at onboarding, or is the primary category of a read or bookmarked item. Items with quality ≥ 60 and no engaged category form the discovery pool. They are ordered by quality and rotate through categories. Every 5th slot (20%) is filled from this pool, and the item is labelled `Discover: <Category>`. A disliked category never appears as discovery.
6. **Reason.** Each item gets a reason from the largest positive part of its score. Examples: "Because you read 4 Cooling articles", "Because you picked Cooling", "Because you're interested in “immersion”", "Similar to articles you read or saved". When no part is positive, the reason is "High quality and recent".
7. **Cold start.** If the profile has no positive signal (dismissals alone don't count), the feed alternates Trending and Most relevant without repeats, and the response has `cold_start: true`. The UI then shows the topic picker (Phase 9B).

The ranking runs in Python over at most 1,000 candidates. Measured on 2,609 live items it took 52 ms. If the pool ever needs to grow much larger, the scoring should move into SQL.
