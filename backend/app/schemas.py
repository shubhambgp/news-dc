"""Pydantic API schemas (PLAN Phase 4, §11.7). Timestamps are UTC and serialized with `Z`."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    model_validator,
)
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
    tag_weights: dict[Tag, Weight] = Field(default_factory=dict, max_length=100)
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


# --- Ask NewsDC (PLAN Phase 6) -------------------------------------------------------------------


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class AskRequest(BaseModel):
    """`history` is up to two earlier exchanges, oldest first (user, assistant, user, assistant).
    It may clarify the question; it never overrides the assistant's rules (§11.8)."""

    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
    history: list[ChatMessage] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _alternating(self) -> "AskRequest":
        roles = [m.role for m in self.history]
        if roles != ["user", "assistant"] * (len(roles) // 2) or len(roles) % 2:
            raise ValueError("history must be user/assistant pairs, oldest first")
        return self


class AskSource(BaseModel):
    """A numbered source of an answer. `[n]` in the answer refers to `n`. The link comes from the
    database, never from the model (§11.8)."""

    n: int
    id: int
    title: str
    url: str
    publisher: str | None
    published_at: UtcDatetime | None
    source: SourceRef | None
    primary_category: str | None
    content_type: ContentType | None


# --- Trends and dashboard (PLAN Phase 7) --------------------------------------------------------


class RisingTermOut(BaseModel):
    term: str
    recent: int = Field(description="Items mentioning it in the last 7 days.")
    baseline: int = Field(description="Items mentioning it in the 28 days before.")
    change_pct: int = Field(
        description="Change of the share of items mentioning it, last 7 days vs the 28 before. "
        "A term absent from the baseline is counted as 1 baseline item."
    )
    new: bool = Field(description="Not mentioned in the baseline window.")


class BriefSource(BaseModel):
    """`[n]` in the brief refers to `n`. Items no longer public are left out."""

    n: int
    id: int
    title: str
    url: str
    publisher: str | None
    published_at: UtcDatetime | None


class TrendBriefOut(BaseModel):
    id: int
    period_start: UtcDatetime
    period_end: UtcDatetime
    content_md: str = Field(description="Untrusted Markdown with `[n]` citations.")
    sources: list[BriefSource]
    model: str | None
    created_at: UtcDatetime


class TrendsResponse(BaseModel):
    recent_start: UtcDatetime
    baseline_start: UtcDatetime
    now: UtcDatetime
    tags: list[RisingTermOut]
    companies: list[RisingTermOut]
    technologies: list[RisingTermOut]
    brief: TrendBriefOut | None = Field(description="The latest trend brief, if any.")


class Funnel(BaseModel):
    """Every item ingested, and where it ended up."""

    fetched: int
    new: int
    rejected_prefilter: int
    rejected_ai: int
    duplicate: int
    failed: int
    processed: int


class CategoryStat(BaseModel):
    slug: str
    name: str
    items: int = Field(description="Processed items with this primary category.")
    avg_quality: float | None


class Count(BaseModel):
    key: str
    items: int


class SourceStat(BaseModel):
    key: str
    name: str
    items: int = Field(description="Items this source found, any status.")
    processed: int


class DayCount(BaseModel):
    date: str = Field(description="UTC date, YYYY-MM-DD.")
    items: int


class RunOut(BaseModel):
    id: int
    kind: str
    trigger: str
    source_key: str | None
    status: str
    started_at: UtcDatetime
    finished_at: UtcDatetime | None
    fetched: int
    new: int
    duplicates: int
    rejected_prefilter: int
    rejected_ai: int
    processed: int
    failed: int
    cost_usd_estimate: float
    stop_reason: str | None
    error: str | None


class AiCost(BaseModel):
    """Estimates from token counts and the configured prices. Ask NewsDC answers are logged, not
    stored, so they are not included."""

    classifier_usd: float
    classifier_today_usd: float
    trend_brief_usd: float
    total_usd: float


class StatsResponse(BaseModel):
    funnel: Funnel
    by_category: list[CategoryStat]
    by_content_type: list[Count]
    by_source: list[SourceStat]
    per_day: list[DayCount] = Field(description="Processed items by publication date, 60 days.")
    pipeline_runs: list[RunOut] = Field(description="The 10 most recent runs.")
    ai_cost: AiCost


# --- Export (Phase 8) ---------------------------------------------------------------------------


class ExportSource(BaseModel):
    """Attribution: one source that found the item, with its own link."""

    key: str
    name: str
    url: str


class ExportRecord(ItemSummary):
    """One processed item for export: permitted metadata, original link, NewsDC-generated
    summary/insights. Never the extracted article text (§11.6, §11.13)."""

    key_insights: list[KeyInsight]
    entities: Entities
    sources: list[ExportSource]


# --- Admin (Phase 8) ----------------------------------------------------------------------------


class AdminLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)


class AdminSessionInfo(BaseModel):
    csrf_token: str = Field(description="Send it as `X-CSRF-Token` on every admin POST/PATCH.")
    expires_at: UtcDatetime


class JobQueued(BaseModel):
    job_id: int | None = Field(
        description="The new job, or null when a job of this kind is already queued or running "
        "(it will pick up the change)."
    )


class Reprocessed(BaseModel):
    items: int = Field(description="Items sent back to `new`.")
    job_id: int | None


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: (
        Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)] | None
    ) = Field(default=None, description="Source key; omit for every enabled source.")


class AdminSource(BaseModel):
    key: str
    name: str
    type: str
    url: str
    enabled: bool = Field(description="From config/sources.yaml (terms reviewed).")
    admin_disabled: bool = Field(description="Paused in Admin.")
    active: bool = Field(description="Ingested on the next run: enabled and not paused.")
    terms_url: str | None
    last_fetched_at: UtcDatetime | None
    last_success_at: UtcDatetime | None
    last_status: str | None
    last_error: str | None


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


class AdminCategory(BaseModel):
    slug: str
    name: str
    description: str
    keywords: list[str]
    enabled: bool
    sort_order: int
    admin_edited_at: UtcDatetime | None


Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class CategoryPatch(BaseModel):
    """Only the fields sent are changed. The next classification run uses them; existing
    annotations become outdated (POST /admin/reprocess-outdated reclassifies them, paid)."""

    model_config = ConfigDict(extra="forbid")

    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None
    ) = None
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = None
    keywords: list[Keyword] | None = Field(default=None, max_length=50)
    enabled: bool | None = None


class AdminRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    trigger: str
    source_key: str | None
    status: str
    started_at: UtcDatetime
    finished_at: UtcDatetime | None
    fetched: int
    new: int
    duplicates: int
    rejected_prefilter: int
    rejected_ai: int
    processed: int
    failed: int
    cost_usd_estimate: float
    error: str | None
    stop_reason: str | None


class AdminJob(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    payload: dict[str, Any]
    status: str
    attempt_count: int
    max_attempts: int
    next_retry_at: UtcDatetime | None
    locked_by: str | None
    last_error: str | None
    created_at: UtcDatetime
    finished_at: UtcDatetime | None


class RejectedItem(BaseModel):
    id: int
    title: str
    url: str
    publisher: str | None
    published_at: UtcDatetime | None
    status: str
    reason: str | None = Field(description="Why it was rejected (prefilter, AI or duplicate).")
    relevance_score: int | None
    quality_score: int | None
    duplicate_of: int | None
    duplicate_similarity: float | None
    updated_at: UtcDatetime
