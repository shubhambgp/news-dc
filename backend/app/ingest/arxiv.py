"""arXiv API (https://info.arxiv.org/help/api/). Terms: at most one request every 3 s, which the
source's `max_requests_per_minute: 20` enforces through the Http throttle.

Results are sorted newest first and paged until entries are older than `since`. The page offset
is checkpointed so an interrupted backfill resumes.
"""

import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from app.ingest.common import Http, TransientFetchError
from app.ingest.rss import entry_time, parse_feed
from app.models import Source

PAGE_SIZE = 100
_VERSION = re.compile(r"v\d+$")


def fetch(
    http: Http, source: Source, since: datetime, checkpoint: dict[str, Any]
) -> Iterator[list[dict[str, Any]]]:
    since_ts = int(since.timestamp())
    for query in source.settings.get("queries", []):
        state = checkpoint.get(query) or {}
        floor = min(since_ts, state.get("since", since_ts))
        start: int = state.get("start", 0)
        while True:
            fetched = http.get(
                source.url,
                params={
                    "search_query": query,
                    "start": start,
                    "max_results": PAGE_SIZE,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
            )
            feed = parse_feed(fetched.content, source.url)
            total = int(feed.feed.get("opensearch_totalresults", 0) or 0)
            if not feed.entries:
                if start < total:  # the arXiv API sometimes returns an empty page; resume later
                    checkpoint[query] = {"start": start, "since": floor}
                    raise TransientFetchError(f"arXiv returned an empty page at start={start}")
                break
            rows = [_row(e) for e in feed.entries]
            fresh = [r for r in rows if r["published_at"] and r["published_at"].timestamp() > floor]
            start += len(feed.entries)
            done = len(fresh) < len(rows) or start >= total
            checkpoint[query] = {"start": start, "since": floor}
            yield fresh
            if done:
                break
        checkpoint.pop(query, None)


def _row(e: Any) -> dict[str, Any]:
    arxiv_id = _VERSION.sub("", e.get("id", "").rsplit("/abs/", 1)[-1])
    pdf = next(
        (link.get("href") for link in e.get("links", []) if link.get("type") == "application/pdf"),
        None,
    )
    authors = [a.get("name") for a in e.get("authors", []) if a.get("name")]
    author = ", ".join(authors[:10]) + (" et al." if len(authors) > 10 else "")
    return {
        "title": e.get("title") or "",
        "url": f"https://arxiv.org/abs/{arxiv_id}",  # versionless, so v1/v2 dedupe together
        "description": e.get("summary"),
        "publisher": "arXiv",
        "author": author or None,
        "published_at": entry_time(e),
        "source_tags": [t.get("term") for t in e.get("tags", []) if t.get("term")],
        "related_links": [{"type": "pdf", "url": pdf}] if pdf else [],
        "external_id": arxiv_id,
    }
