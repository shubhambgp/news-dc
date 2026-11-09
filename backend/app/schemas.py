"""Pydantic API schemas (PLAN Phase 4, §11.7). Timestamps are UTC and serialized with `Z`."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints
from pydantic.alias_generators import to_camel


def _utc_iso(dt: datetime) -> str:
    """Always UTC with a Z suffix, whatever the DB session's timezone was."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str)]
ContentType = Literal["news", "research", "investment", "engineering"]


class ErrorBody(BaseModel):
    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["item 42 not found"])
    request_id: str = Field(examples=["5f0c2e1d9a8b4c7e"])


class ErrorResponse(BaseModel):
    """Every non-2xx response has this shape."""

    error: ErrorBody


class SourceRef(BaseModel):
    key: str
    name: str


class KeyInsight(BaseModel):
    type: Literal["technical", "business"]
    text: str


class Entities(BaseModel):
    companies: list[str] = []
    technologies: list[str] = []
    locations: list[str] = []


class ItemSummary(BaseModel):
    """One processed item as shown on a feed card."""

    id: int
    title: str
    url: str = Field(description="Original link to the publisher's page.")
    publisher: str | None
    author: str | None
    published_at: UtcDatetime | None
    source: SourceRef | None = Field(description="The item's primary (first) source.")
    primary_category: str | None
    categories: list[str]
    content_type: ContentType | None
    summary: str | None
    tags: list[str]
    relevance_score: int | None
    quality_score: int | None
    points: int | None
    comments_count: int | None
    discussion_url: str | None


class SearchHit(ItemSummary):
    snippet: str = Field(
        description="HTML-escaped text; matched terms are wrapped in <mark>…</mark> and no "
        "other markup is present."
    )
    score: float = Field(description="Reciprocal Rank Fusion score (higher is better).")


class RelatedItem(ItemSummary):
    similarity: float = Field(description="Cosine similarity of the embeddings.")
    score: float = Field(description="similarity + 0.1 per shared category.")


class Coverage(BaseModel):
    """One source that found this item (item_sources row)."""

    source: SourceRef
    url: str
    title: str | None
    published_at: UtcDatetime | None
    first_seen_at: UtcDatetime
    engagement: dict[str, Any]
    is_primary: bool


class DuplicateRef(BaseModel):
    """A near-duplicate that points at this item ("also covered by")."""

    id: int
    title: str
    url: str
    publisher: str | None
    published_at: UtcDatetime | None
    similarity: float | None


class ItemDetail(ItemSummary):
    description: str | None
    key_insights: list[KeyInsight]
    entities: Entities
    related_links: list[Any]
    coverage: list[Coverage]
    also_covered_by: list[DuplicateRef]


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    has_more: bool


class TopicSummary(BaseModel):
    slug: str
    name: str
    description: str
    item_count: int
    latest: list[ItemSummary]


class TopicPage(BaseModel):
    slug: str
    name: str
    description: str
    items: Page[ItemSummary]


# --- For You (PLAN Phase 5) ---------------------------------------------------------------------

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Weight = Annotated[float, Field(ge=-1000, le=1000, allow_inf_nan=False)]
ItemRef = Annotated[int, Field(ge=1, le=2**63 - 1)]


class Profile(BaseModel):
    """The anonymous profile the browser keeps in localStorage. Lists are oldest first, so the
    last entries are the most recent. Category slugs must exist; unknown fields are rejected."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    category_weights: dict[Slug, Weight] = Field(default_factory=dict, max_length=64)
    tag_weights: dict[Tag, Weight] = Field(default_factory=dict, max_length=200)
    read_ids: list[ItemRef] = Field(default_factory=list, max_length=200)
    bookmark_ids: list[ItemRef] = Field(default_factory=list, max_length=500)
    dismissed_ids: list[ItemRef] = Field(default_factory=list, max_length=500)
    explicit_topics: list[Slug] = Field(default_factory=list, max_length=64)

    def is_empty(self) -> bool:
        """No signal to personalize on (dismissals alone don't say what the user likes)."""
        return not (
            any(self.category_weights.values())
            or any(self.tag_weights.values())
            or self.read_ids
            or self.bookmark_ids
            or self.explicit_topics
        )


FeedKind = Literal["personal", "discover", "trending", "relevant"]


class ForYouItem(ItemSummary):
    kind: FeedKind = Field(
        description="`personal` (scored on the profile), `discover` (a category the user has not "
        "engaged with), or `trending` / `relevant` (cold-start fallback)."
    )
    reason: str = Field(examples=["Because you read 4 Cooling articles"])
    score: float


class ForYouPage(Page[ForYouItem]):
    cold_start: bool = Field(
        description="True when the profile was empty and the feed fell back to Trending + Most "
        "relevant. The UI shows the topic picker."
    )
