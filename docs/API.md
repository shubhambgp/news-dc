# NewsDC API

Base path: `/api/v1`. The interactive OpenAPI docs are at `/api/v1/docs` and the schema is at `/api/v1/openapi.json`. Request and response models live in `backend/app/schemas.py`.

Every endpoint below is **public**, read-only (`GET`), takes no request body, and is **rate limited** to `RATE_LIMIT_DEFAULT` (60/minute) per client IP. `/health` and `/ready` are the exceptions: they aren't rate limited. Admin endpoints arrive in Phase 8.

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

`/items`, `/feeds/relevant`, `/topics/{slug}` and `/search` accept these filters:

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
| `GET /items` | Processed items with filters | `sort=latest` (default) \| `relevance` \| `quality` (`trending` arrives in Phase 5) | 422 |
| `GET /items/{id}` | Detail: the annotation (`key_insights`, `entities`), `related_links`, `coverage` (every source that found the item, with its URL, engagement and timestamps) and `also_covered_by` (near-duplicates with their similarity) | | 404, 422 |
| `GET /items/{id}/related` | Up to 6 items: cosine similarity of the embeddings + 0.1 per shared category. Each has `similarity` and `score`. Returns `[]` when the item has no embedding yet. | `score DESC` | 404, 422 |
| `GET /feeds/relevant` | Most relevant items | `relevance_score × quality_score DESC` (Phase 5 refines this) | 422 |
| `GET /topics` | Enabled categories in display order, each with `item_count` and its 3 newest items (`latest`) | `sort_order` | |
| `GET /topics/{slug}` | `{slug, name, description, items: Page}` for one enabled category | same `sort` as `/items` | 404 (unknown or disabled), 422 |
| `GET /search?q=` | Hybrid search (see below). The response adds `mode` (`hybrid` or `keyword`) and, per hit, `snippet` and `score`. | RRF score DESC | 422 |

### Search

- `q`: 1–200 characters in web-search syntax (`"exact phrase"`, `-exclude`, `OR`). A blank `q` returns 422.
- **Keyword retriever:** `websearch_to_tsquery('english', q)` against the title (weight A), description (B), article text (C) and AI summary (B), ranked by `ts_rank_cd`. Returns up to 100 candidates.
- **Semantic retriever:** cosine distance between the query embedding (bge-small-en-v1.5) and the item embeddings. Hits below `SEARCH_MIN_SIMILARITY` (0.6) are dropped. Returns up to 100 candidates.
- The two lists are fused with Reciprocal Rank Fusion: `score = Σ 1/(60 + rank)`, ties broken by id DESC. `total` is the size of the fused list.
- `snippet` comes from `ts_headline` over the summary (or the description, or the title). It is **HTML-escaped**, and matched terms are wrapped in `<mark>…</mark>`. It contains no other markup.
- If the embedding model is unavailable, search runs keyword-only and returns `mode: "keyword"`.

## Errors

Every non-2xx response has the same shape:

```json
{"error": {"code": "not_found", "message": "item 42 not found", "request_id": "5f0c2e1d9a8b4c7e"}}
```

| Status | `code` | When |
|---|---|---|
| 404 | `not_found` | Unknown route, item or topic |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 422 | `validation_error` | Invalid parameters. The message names the field (up to 3 errors), e.g. `query.page_size: Input should be less than or equal to 50` |
| 429 | `rate_limited` | Over the per-IP limit |
| 500 | `internal_error` | Unexpected error. No internals are exposed. |
| 503 | `db_unavailable` | The database is unreachable |

## Response headers

Every response carries `X-Request-ID`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`. API responses also carry `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. The docs page doesn't, because Swagger UI loads a CDN script. CORS allows only `CORS_ORIGINS` and exposes `X-Request-ID`.
