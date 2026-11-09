"""GitHub repository search (https://docs.github.com/en/rest/search/search).

Limits: 10 search requests/min unauthenticated, 30 with a token; at most 1,000 results per query.
Each configured query is narrowed to repos pushed since `since`. Stars count as engagement.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.ingest.common import Http
from app.models import Source

PAGE_SIZE = 100
MAX_PAGES = 10  # GitHub search stops at 1,000 results


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch(
    http: Http, source: Source, since: datetime, checkpoint: dict[str, Any]
) -> Iterator[list[dict[str, Any]]]:
    for query in source.settings.get("queries", []):
        page: int = (checkpoint.get(query) or {}).get("page", 1)
        while page <= MAX_PAGES:
            data = http.get(
                source.url,
                params={
                    "q": f"{query} pushed:>={since:%Y-%m-%d}",
                    "sort": "updated",
                    "order": "desc",
                    "per_page": PAGE_SIZE,
                    "page": page,
                },
                headers=_headers(),
            ).json()
            repos = data.get("items") or []
            checkpoint[query] = {"page": page + 1}
            yield [_row(r) for r in repos]
            if len(repos) < PAGE_SIZE:
                break
            page += 1
        checkpoint.pop(query, None)


def _row(repo: dict[str, Any]) -> dict[str, Any]:
    created = repo.get("created_at")
    return {
        "title": repo.get("full_name") or "",
        "url": repo.get("html_url") or "",
        "description": repo.get("description"),
        "publisher": "GitHub",
        "author": (repo.get("owner") or {}).get("login"),
        "published_at": datetime.fromisoformat(created) if created else None,
        "source_tags": repo.get("topics") or [],
        "points": repo.get("stargazers_count"),
        "external_id": str(repo["id"]),
    }
