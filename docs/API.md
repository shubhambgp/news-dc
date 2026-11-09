# NewsDC API

Base path: `/api/v1`. The interactive OpenAPI docs are at `/api/v1/docs` and the schema is at `/api/v1/openapi.json`. Request and response models live in `backend/app/schemas.py`.

Every endpoint is **rate limited** to `RATE_LIMIT_DEFAULT` (60/minute) per client IP, except `/health` and `/ready`. Everything outside `/admin` is **public** and read-only. `POST /ask` has an extra limit, `RATE_LIMIT_ASK` (10/minute). `/admin/*` is **admin-only** (see [Admin](#admin)). Request bodies are at most 64 KiB.

## Conventions

| Topic | Rule |
|---|---|
| Timestamps | ISO 8601 in UTC with a `Z` suffix (`2026-11-09T14:02:28Z`). In query parameters, a timestamp without an offset is read as UTC. |
| Pagination | `page` (1–1000, default 1) and `page_size` (1–50, default 20). The response is `{items, page, page_size, total, has_more}`. |
| Ordering | Deterministic. Every sort ends with `published_at DESC, id DESC`, so pages never skip or repeat rows while the data is unchanged. |
| Visibility | Only items with status `processed` are returned. Rejected, failed and duplicate items stay in the DB for audit (a near-duplicate appears in its canonical item's `also_covered_by`). |
| Content | Full article text is never returned. Items carry the original link, the publisher, source attribution and NewsDC's AI summary. |
| Request ID | Send `X-Request-ID` (`[A-Za-z0-9._-]{1,64}`) or the server generates one. It is returned in the `X-Request-ID` header and in error bodies, and it appears in every log line for the request. |

### Shared item filters

`/items`, `/feeds/trending`, `/feeds/relevant`, `/topics/{slug}` and `/search` accept these filters:

| Param | Type | Meaning |
|---|---|---|
| `category` | slug | Matches any of the item's categories. `/topics/{slug}` ignores it, because the path decides. |
| `content_type` | `news` \| `research` \| `investment` \| `engineering` | |
| `source` | source key (e.g. `hn`, `dcd`, `arxiv`) | Any source that found the item, not only the primary one |
| `min_quality` | 0–100 | `quality_score >= min_quality` |
| `from` | timestamp | `published_at >= from` |
| `to` | timestamp | `published_at < to` (exclusive). Must be later than `from`. |

A well-formed slug or key that doesn't exist returns an empty list. A malformed one returns `422`.

## Endpoints

| Endpoint | Purpose | Sort / ranking | Errors |
|---|---|---|---|
| `GET /health` | Liveness. Always 200 and reports the DB state. | | |
| `GET /ready` | Readiness. Returns 503 while the DB is down. | | |
| `GET /items` | Processed items with filters | `sort=latest` (default) \| `relevance` \| `quality` \| `trending` \| `relevant` (see below) | 422 |
| `GET /items/{id}` | Detail: the annotation (`key_insights`, `entities`), `related_links`, `coverage` (every source that found the item, with its URL, engagement and timestamps) and `also_covered_by` (near-duplicates with their similarity) | | 404, 422 |
| `GET /items/{id}/related` | Up to 6 items: cosine similarity of the embeddings + 0.1 per shared category. Each has `similarity` and `score`. Returns `[]` when the item has no embedding yet. | `score DESC` | 404, 422 |
| `GET /feeds/trending` | Trending items | `sort=trending` | 422 |
| `GET /feeds/relevant` | Most relevant items | `sort=relevant` | 422 |
| `POST /feeds/foryou` | Personalised feed from the anonymous localStorage profile (see below). Takes `page`/`page_size`. | profile score, every 5th item `discover` | 411, 413, 422 |
| `GET /topics` | Enabled categories in display order, each with `item_count` and its 3 newest items (`latest`) | `sort_order` | |
| `GET /topics/{slug}` | `{slug, name, description, items: Page}` for one enabled category | same `sort` as `/items` | 404 (unknown or disabled), 422 |
| `GET /search?q=` | Hybrid search (see below). The response adds `mode` (`hybrid` or `keyword`) and, per hit, `snippet` and `score`. | RRF score DESC | 422 |
| `POST /ask` | Ask NewsDC: a cited answer from collected items, streamed as Server-Sent Events (see below) | | 411, 413, 422, 429, 503 |
| `GET /ask/suggestions` | The 5 example questions for the empty Ask screen (`string[]`) | | |
| `GET /trends` | Rising tags, companies and technologies (up to 10 each) plus the latest trend brief (see below) | `change_pct DESC, recent DESC` | |
| `GET /stats` | Dashboard data (see below) | | |

### Sorts and feeds (Phase 5)

The formulas are explained in `docs/ARCHITECTURE.md`. Ties are broken by `published_at DESC, id DESC`.

| `sort` | Score |
|---|---|
| `latest` | `published_at DESC` |
| `relevance` | `relevance_score DESC` |
| `quality` | `quality_score DESC` |
| `trending` | `(1 + points + 2·comments + quality/10 + 5·coverage) / (age_hours + 2)^1.5`, where coverage is near-duplicates plus extra sources |
| `relevant` | `(0.6·relevance + 0.4·quality) / (1 + age_days/30)` |

### For You

`POST /feeds/foryou?page=1&page_size=20` with `Content-Type: application/json`:

```json
{"categoryWeights": {"cooling": 7.5}, "tagWeights": {"immersion": 3},
 "readIds": [12, 40], "bookmarkIds": [7], "dismissedIds": [99], "explicitTopics": ["cooling"]}
```

| Field | Limit |
|---|---|
| `categoryWeights` | ≤ 64 entries. Keys must be existing category slugs. Values are finite, −1000 to 1000. |
| `tagWeights` | ≤ 100 entries. Tags are 1–64 characters and are compared case-insensitively. |
| `readIds` | ≤ 200 item IDs, oldest first |
| `bookmarkIds`, `dismissedIds` | ≤ 500 item IDs each |
| `explicitTopics` | ≤ 64 category slugs (picked at onboarding) |

Every field is optional, and an unknown field returns 422. The body must have a `Content-Length` (otherwise 411) and be at most 64 KiB (otherwise 413).

The response is a page (`items`, `page`, `page_size`, `total`, `has_more`) plus `cold_start`. Each item adds:
- `kind`: `personal`, `discover`, `trending` or `relevant`
- `reason`: the "Why am I seeing this?" text, e.g. `Because you read 4 Cooling articles` or `Discover: Networking`
- `score`

Read, bookmarked and dismissed items are never returned. The feed ranks the newest 1,000 public items, so `total` is at most 1,000. A profile with no positive signal returns Trending + Most relevant with `cold_start: true`.

### Search

- `q`: 1–200 characters in web-search syntax (`"exact phrase"`, `-exclude`, `OR`). A blank `q` returns 422.
- **Keyword retriever:** `websearch_to_tsquery('english', q)` against the title (weight A), description (B), article text (C) and AI summary (B), ranked by `ts_rank_cd`. Returns up to 100 candidates.
- **Semantic retriever:** cosine distance between the query embedding (bge-small-en-v1.5) and the item embeddings. Hits below `SEARCH_MIN_SIMILARITY` (0.6) are dropped. Returns up to 100 candidates.
- The two lists are fused with Reciprocal Rank Fusion: `score = Σ 1/(60 + rank)`, ties broken by id DESC. `total` is the size of the fused list.
- `snippet` comes from `ts_headline` over the summary (or the description, or the title). It is **HTML-escaped**, and matched terms are wrapped in `<mark>…</mark>`. It contains no other markup.
- If the embedding model is unavailable, search runs keyword-only and returns `mode: "keyword"`.

## Ask NewsDC (Phase 6)

`POST /api/v1/ask` with a JSON body. Use `fetch()` and read `response.body` with a `ReadableStream` reader; browser `EventSource` can't send a POST body.

```json
{
  "question": "Which of those are in Europe?",
  "history": [
    {"role": "user", "content": "Which hyperscalers are investing in new data centers?"},
    {"role": "assistant", "content": "Meta is building Hyperion in Louisiana [6] …"}
  ]
}
```

| Field | Rule |
|---|---|
| `question` | 3–500 characters after trimming |
| `history` | Optional. At most 4 messages: complete `user`, `assistant` pairs, oldest first. Each `content` is 1–4,000 characters. Unknown fields or roles are a 422 |

Validation, rate-limit and configuration errors (`503 assistant_unavailable` when `ASSISTANT_MODEL` or the API key is unset) are normal JSON error envelopes, sent before the stream starts. After that the response is `200 text/event-stream` (`Cache-Control: no-cache`, `X-Accel-Buffering: no`). Each event is `event: <name>\ndata: <json>\n\n`:

| Event | When | `data` |
|---|---|---|
| `sources` | Always first | `{"sources": [{n, id, title, url, publisher, published_at, source: {key, name}, primary_category, content_type}]}`. Up to 8. `[n]` in the answer refers to `n`. Links come from the database, never from the model. Empty when nothing matched |
| `status` | Before generation starts | `{"stage": "generating"}` |
| `token` | Many times | `{"text": "…"}`. Markdown text. Citation numbers that don't match a source have already been removed |
| `done` | Success, last event | `{"cited": [1, 3], "removed_citations": 0, "truncated": false}`. `truncated` means the answer hit `ASSISTANT_MAX_TOKENS` |
| `error` | Failure, last event | `{"code": "llm_unavailable" \| "llm_error" \| "no_answer", "message": "…"}`. Discard any tokens already shown. `done` never follows an `error` |

When nothing matches, the stream is `sources` (empty), one `token` saying the collected sources don't cover the question, then `done`. No LLM call is made. There is no resume and no event IDs: if the connection drops, send the question again. When the client disconnects, the server closes the upstream LLM stream.

Retrieval: hybrid search (keywords OR-ed, plus the embedding) over the question and the previous user question in `history` gives 25 candidates. They are re-ranked by retrieval rank, relevance, quality and freshness down to 8. Questions about recent news ("latest", "this month", "emerging") weigh freshness more. Formula in `docs/ARCHITECTURE.md`.

## Trends and dashboard (Phase 7)

`GET /trends` returns `{recent_start, baseline_start, now, tags, companies, technologies, brief}`.

- Each rising term is `{term, recent, baseline, change_pct, new}`. `recent` and `baseline` are item counts in the last 7 days and the 28 days before. `change_pct` is the change of the *share* of items that mention the term (formula in `docs/ARCHITECTURE.md`). Only rising terms with at least 3 items this week are listed. A company is not counted on items its own outlet published.
- `brief` is `null` until the first brief exists. Otherwise `{id, period_start, period_end, content_md, sources, model, created_at}`. `content_md` is untrusted Markdown with `[n]` citations; `sources[]` is `{n, id, title, url, publisher, published_at}` and every `[n]` in the text has a matching `n` (items no longer public are left out).

`GET /stats` returns:

| Field | Content |
|---|---|
| `funnel` | `{fetched, new, rejected_prefilter, rejected_ai, duplicate, failed, processed}`: every item and its status; `fetched` is the sum |
| `by_category` | `[{slug, name, items, avg_quality}]` for every category in display order; processed items by primary category, `avg_quality` is `null` with no items |
| `by_content_type` | `[{key, items}]`, processed items, largest first |
| `by_source` | `[{key, name, items, processed}]`; every item a source found (any status, via `item_sources`) and how many are processed |
| `per_day` | `[{date, items}]`, 60 UTC days ending today, processed items by publication date, zero-filled |
| `pipeline_runs` | The 10 most recent ingest and pipeline runs with their counts, status, cost, `stop_reason` and `error` |
| `ai_cost` | `{classifier_usd, classifier_today_usd, trend_brief_usd, total_usd}`. Estimates from token counts and the configured prices. Ask NewsDC answers are logged, not stored, so they are not included |

## Export

`GET /export?format=json|md&limit=&category=&content_type=&source=&min_quality=&from=&to=`: public, rate limited. Downloads the newest `limit` (1–1000, default 500) processed items matching the shared filters, ordered `published_at DESC, id DESC`, as an attachment (`Content-Disposition: attachment; filename="newsdc_export.json|md"`).

- `format=json` (default): `application/json`, an array of records. A record is an `ItemSummary` plus `key_insights`, `entities` and `sources` (`[{key, name, url}]`, every source that found the item, primary first).
- `format=md`: `text/markdown; charset=utf-8`, one document grouped by primary category (display order, then "Uncategorized"). Each item has a title link, publisher · date · content type, the summary, insights and source links. Titles, summaries and insights are escaped (no raw HTML or Markdown from sources or the model), and only `http(s)` links are emitted.

Exports never contain the extracted article text or the source's description: only metadata, original links, attribution and NewsDC's own summaries and insights (§11.13). `backend/scripts/export_dataset.py` writes the same format to `data/sample/`.

## Admin

Admin is disabled (every `/admin/*` route returns `503 admin_disabled`) unless `ADMIN_TOKEN` (≥ 16 chars) and `SESSION_SECRET` (≥ 32 chars, a different random value) are set.

**Session.** `POST /admin/login` with `{"token": "<ADMIN_TOKEN>"}` returns `{csrf_token, expires_at}` and sets the `newsdc_admin` cookie: `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/admin; Max-Age=ADMIN_SESSION_MINUTES*60` (default 30 minutes). Every login issues a new session ID and CSRF token. Login is limited to `RATE_LIMIT_ADMIN_LOGIN` (5/minute) per IP and `RATE_LIMIT_ADMIN_LOGIN_GLOBAL` (30/minute) for all clients together; a wrong token is `401 unauthorized` with no detail.

Every other admin route needs the cookie (`401 unauthorized` without a valid, unexpired, not-logged-out session). `POST` and `PATCH` also need the `X-CSRF-Token` header (`403 csrf_failed`), and a browser request's `Origin` (or `Referer`) must be the API's own origin or one of `CORS_ORIGINS` (`403 forbidden_origin`). The frontend sends `credentials: "include"`; CORS allows credentials for `CORS_ORIGINS` only.

| Endpoint | Does |
|---|---|
| `POST /admin/login` | See above |
| `GET /admin/session` | `{csrf_token, expires_at}` of the current session (the cookie is httpOnly, so the UI reads the token here after a reload) |
| `POST /admin/logout` | `204`. Revokes the session and clears the cookie |
| `POST /admin/ingest` | Body `{"source": "<key>"}` or `{}` for every active source. `202 {job_id}`. Queues an `ingest_all` job; the worker queues a pipeline run when it finishes. `404` unknown source, `409 source_inactive` if disabled in YAML or paused |
| `POST /admin/pipeline` | `202 {job_id}`. Queues a pipeline run over `new` items (paid; spend limits apply) |
| `POST /admin/trend-brief` | `202 {job_id}`. Queues a new trend brief. `409 assistant_unavailable` without `ASSISTANT_MODEL` |
| `POST /admin/reprocess-outdated` | `202 {items, job_id}`. Items classified with another prompt version or prompt hash (e.g. after a category edit) go back to `new`, and a pipeline run is queued (paid) |
| `POST /admin/items/{id}/reprocess` | `202 {items: 1, job_id}`. One item back to `new`, any status. `404` unknown item |
| `POST /admin/jobs/{id}/retry` | `200 {job_id}`. A dead-lettered job gets fresh attempts. `409 not_dead_letter` otherwise |
| `GET /admin/runs` | The last 50 ingest and pipeline runs: counts, status, cost, `error`, `stop_reason` (e.g. a spend limit) |
| `GET /admin/jobs` | The last 50 jobs with status, attempts, `last_error` |
| `GET /admin/sources` | Every source: `enabled` (YAML, terms reviewed), `admin_disabled`, `active`, `terms_url`, last fetch/success/status/error |
| `PATCH /admin/sources/{key}` | `{"active": bool}`. Pauses or resumes a source. Turning on a source that YAML disables is `409 disabled_in_config` |
| `GET /admin/categories` | Every category with `admin_edited_at` |
| `PATCH /admin/categories/{slug}` | Any of `name` (1–80), `description` (1–500), `keywords` (≤ 50, each 1–64), `enabled`. The next classification run uses the new text; existing annotations become outdated. Seeding no longer overwrites an edited category's text. Disabling the last enabled category is `409 last_category` |
| `GET /admin/rejected?status=&page=&page_size=` | Paginated items kept out of the feed (`rejected_prefilter`, `rejected_ai`, `duplicate`), newest decision first, with `reason`, scores and `duplicate_of`/`duplicate_similarity` |

`job_id` is `null` when a job of that kind is already queued or running (one active job per kind); that job picks up the change.

## Errors

Every non-2xx response has the same shape:

```json
{"error": {"code": "not_found", "message": "item 42 not found", "request_id": "5f0c2e1d9a8b4c7e"}}
```

| Status | `code` | When |
|---|---|---|
| 401 | `unauthorized` | Admin route without a valid session, or a wrong admin token |
| 403 | `csrf_failed`, `forbidden_origin` | Admin `POST`/`PATCH` without the CSRF token, or from a foreign origin |
| 404 | `not_found` | Unknown route, item or topic |
| 409 | see [Admin](#admin) | An admin action that conflicts with the current state |
| 411 | `length_required` | A request body without `Content-Length` |
| 413 | `payload_too_large` | A request body over 64 KiB |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 422 | `validation_error` | Invalid parameters. The message names the field (up to 3 errors), e.g. `query.page_size: Input should be less than or equal to 50` |
| 429 | `rate_limited` | Over the per-IP limit |
| 500 | `internal_error` | Unexpected error. No internals are exposed. |
| 503 | `db_unavailable` | The database is unreachable |
| 503 | `admin_disabled` | Admin route while `ADMIN_TOKEN`/`SESSION_SECRET` are unset |

## Response headers

Every response carries `X-Request-ID`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`. API responses also carry `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. The docs page doesn't, because Swagger UI loads a CDN script. CORS allows only `CORS_ORIGINS` (with credentials, for the admin cookie), the methods `GET`, `POST`, `PATCH` and the request headers `Content-Type`, `X-Request-ID`, `X-CSRF-Token`, and exposes `X-Request-ID`.
