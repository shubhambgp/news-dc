"""Scoring formulas (PLAN Phase 5). Each formula is written once and works on plain numbers (unit
tests, For You ranking in Python) and on SQLAlchemy expressions (`ORDER BY` for paginated feeds):
`+ - * /` and `**` (rendered as `power()`) behave the same on both."""

from typing import Any

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import aliased

from app.models import AIAnnotation, Item, ItemSource

RELEVANT_HALF_AFTER_DAYS = 30  # mild decay: a month-old item keeps half its relevant score
FRESHNESS_HALF_LIFE_DAYS = 7
SHARED_CATEGORY_BOOST = 0.1


def trending(points: Any, comments: Any, quality: Any, coverage: Any, age_hours: Any) -> Any:
    """Hacker News gravity: engagement, quality and coverage over (age + 2)^1.5. Items without
    engagement data (non-HN) rank on quality and coverage alone."""
    return (1 + points + 2 * comments + quality / 10 + 5 * coverage) / (age_hours + 2) ** 1.5


def relevant(relevance: Any, quality: Any, age_hours: Any) -> Any:
    """0.6·relevance + 0.4·quality, divided by 1 + age_days/30."""
    return (0.6 * relevance + 0.4 * quality) / (1 + age_hours / 24 / RELEVANT_HALF_AFTER_DAYS)


def related(similarity: float, shared_categories: int) -> float:
    """Cosine similarity + 0.1 per shared category."""
    return similarity + SHARED_CATEGORY_BOOST * shared_categories


def freshness(age_hours: float) -> float:
    """1.0 now, halves every 7 days."""
    return float(0.5 ** (max(age_hours, 0.0) / 24 / FRESHNESS_HALF_LIFE_DAYS))


def personal(
    category: float, similarity: float, tag: float, quality: int, age_hours: float
) -> float:
    """For You: 0.35·category + 0.25·embedding similarity + 0.15·tag + 0.15·quality + 0.10·fresh.
    Affinities are in [-1, 1], similarity in [0, 1], quality 0–100."""
    return (
        0.35 * category
        + 0.25 * similarity
        + 0.15 * tag
        + 0.15 * quality / 100
        + 0.10 * freshness(age_hours)
    )


# --- SQL bindings ------------------------------------------------------------------------------


def _f(col: Any) -> Any:
    return cast(func.coalesce(col, 0), Float)


def age_hours_sql() -> Any:
    """Hours since publication (fetch time when the source gave no date); never negative."""
    ts = func.coalesce(Item.published_at, Item.fetched_at)
    return func.greatest(cast(func.extract("epoch", func.now() - ts), Float) / 3600, 0.0)


def coverage_sql() -> Any:
    """How many other outlets covered the story: near-duplicates pointing at the item plus every
    extra source that found the same URL (D-032)."""
    dup = aliased(Item)
    near = (
        select(func.count())
        .where(dup.duplicate_of == Item.id, dup.status == "duplicate")
        .correlate(Item)
        .scalar_subquery()
    )
    extra = (
        select(func.greatest(func.count() - 1, 0))
        .where(ItemSource.item_id == Item.id)
        .correlate(Item)
        .scalar_subquery()
    )
    return near + extra


def trending_sql() -> Any:
    return trending(
        _f(Item.points),
        _f(Item.comments_count),
        _f(AIAnnotation.quality_score),
        cast(coverage_sql(), Float),
        age_hours_sql(),
    )


def relevant_sql() -> Any:
    return relevant(
        _f(AIAnnotation.relevance_score), _f(AIAnnotation.quality_score), age_hours_sql()
    )
