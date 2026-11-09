"""RSS/Atom feeds. Metadata only (title, link, summary, author, date, tags).

Uses conditional GET (ETag / Last-Modified kept in the source checkpoint) so an unchanged feed
costs one 304. Feeds only expose recent entries, so there is nothing to backfill.
"""

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import feedparser

from app.ingest.common import Http, PermanentFetchError
from app.models import Source


def entry_time(entry: Any) -> datetime | None:
    """feedparser normalizes dates to UTC struct_time."""
    for key in ("published_parsed", "updated_parsed"):
        t: time.struct_time | None = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=UTC)
    return None


def parse_feed(content: bytes, url: str) -> Any:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise PermanentFetchError(f"unparseable feed {url}: {feed.get('bozo_exception')}")
    return feed


def fetch(
    http: Http, source: Source, since: datetime, checkpoint: dict[str, Any]
) -> Iterator[list[dict[str, Any]]]:
    headers = {}
    if checkpoint.get("etag"):
        headers["If-None-Match"] = checkpoint["etag"]
    if checkpoint.get("last_modified"):
        headers["If-Modified-Since"] = checkpoint["last_modified"]
    fetched = http.get(source.url, headers=headers)
    if fetched.status == 304:
        return
    feed = parse_feed(fetched.content, source.url)
    checkpoint.clear()
    for key, header in (("etag", "etag"), ("last_modified", "last-modified")):
        if fetched.headers.get(header):
            checkpoint[key] = fetched.headers[header]

    publisher = source.settings.get("attribution_label") or source.name
    rows = []
    for e in feed.entries:
        published = entry_time(e)
        if published and published < since:
            continue
        rows.append(
            {
                "title": e.get("title") or "",
                "url": e.get("link") or "",
                "description": e.get("summary"),
                "publisher": publisher,
                "author": e.get("author"),
                "published_at": published,
                "source_tags": [t.get("term") for t in e.get("tags", []) if t.get("term")],
                "external_id": e.get("id") or e.get("link"),
            }
        )
    yield rows
