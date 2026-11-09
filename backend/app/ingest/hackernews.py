"""Hacker News via the Algolia HN Search API (https://hn.algolia.com/api).

One title-restricted phrase search per configured query, newest first. Pages walk backwards in
time with a `created_at_i` cursor (avoids Algolia's 1,000-hit pagination cap). The cursor is
kept in the source checkpoint so an interrupted backfill resumes where it stopped.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from app.ingest.common import Http, canonicalize_url, host_of
from app.models import Source

PAGE_SIZE = 100
ITEM_URL = "https://news.ycombinator.com/item?id={}"
SEARCH_URL = "https://hn.algolia.com/api/v1/search"


def fetch(
    http: Http, source: Source, since: datetime, checkpoint: dict[str, Any]
) -> Iterator[list[dict[str, Any]]]:
    since_ts = int(since.timestamp())
    for query in source.settings.get("queries", []):
        state = checkpoint.get(query) or {}
        floor = min(since_ts, state.get("since", since_ts))  # finish an older backfill first
        upper: int | None = state.get("until")
        while True:
            filters = f"created_at_i>{floor}" + (f",created_at_i<={upper}" if upper else "")
            data = http.get(
                source.url,
                params={
                    "query": f'"{query}"',
                    "tags": "story",
                    "restrictSearchableAttributes": "title",
                    "hitsPerPage": PAGE_SIZE,
                    "numericFilters": filters,
                },
            ).json()
            hits = data.get("hits") or []
            if not hits:
                break
            oldest = min(h["created_at_i"] for h in hits)
            # `<=` re-reads stories sharing the boundary second (upserts are idempotent); stop
            # if a full page never moves the cursor.
            done = len(hits) < PAGE_SIZE or oldest == upper
            checkpoint[query] = {"until": oldest, "since": floor}
            yield [_row(h, query) for h in hits]
            if done:
                break
            upper = oldest
        checkpoint.pop(query, None)


def _row(hit: dict[str, Any], query: str) -> dict[str, Any]:
    story_id = str(hit["objectID"])
    discussion = ITEM_URL.format(story_id)
    url = hit.get("url") or discussion  # Ask HN / text posts link to the thread itself
    return {
        "title": hit.get("title") or "",
        "url": url,
        "description": hit.get("story_text"),
        "publisher": host_of(url) or None,
        "author": hit.get("author"),
        "published_at": datetime.fromtimestamp(hit["created_at_i"], UTC),
        "source_tags": [query],
        "points": hit.get("points"),
        "comments_count": hit.get("num_comments"),
        "discussion_url": discussion,
        "external_id": story_id,
    }


def discussions(http: Http, url: str) -> list[dict[str, Any]]:
    """HN threads that link exactly this URL (after canonicalization), most points first."""
    target = canonicalize_url(url)
    data = http.get(
        SEARCH_URL,
        params={
            "query": url,
            "restrictSearchableAttributes": "url",
            "tags": "story",
            "hitsPerPage": 20,
        },
    ).json()
    found = []
    for hit in data.get("hits") or []:
        try:
            same = bool(hit.get("url")) and canonicalize_url(hit["url"]) == target
        except ValueError:
            continue
        if same:
            found.append(
                {
                    "type": "hn_discussion",
                    "url": ITEM_URL.format(hit["objectID"]),
                    "title": hit.get("title"),
                    "points": hit.get("points") or 0,
                    "comments": hit.get("num_comments") or 0,
                }
            )
    return sorted(found, key=lambda d: d["points"], reverse=True)[:5]
