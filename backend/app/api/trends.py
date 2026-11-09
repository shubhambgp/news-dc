"""Emerging trends and dashboard data (PLAN Phase 7): `GET /trends` and `GET /stats`."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from app.ai import trends
from app.api.common import get_db, public_items
from app.models import (
    ITEM_STATUSES,
    AIAnnotation,
    Category,
    Item,
    ItemSource,
    PipelineRun,
    Source,
    TrendBrief,
)
from app.schemas import (
    AiCost,
    BriefSource,
    CategoryStat,
    Count,
    DayCount,
    Funnel,
    RisingTermOut,
    RunOut,
    SourceStat,
    StatsResponse,
    TrendBriefOut,
    TrendsResponse,
)

router = APIRouter(tags=["trends"])

PER_DAY_DAYS = 60
LAST_RUNS = 10


def latest_brief(db: Session) -> TrendBriefOut | None:
    brief = db.scalars(select(TrendBrief).order_by(TrendBrief.created_at.desc()).limit(1)).first()
    if brief is None:
        return None
    rows = {r[0].id: r[0] for r in db.execute(public_items().where(Item.id.in_(brief.sources)))}
    return TrendBriefOut(
        id=brief.id,
        period_start=brief.period_start,
        period_end=brief.period_end,
        content_md=brief.content_md,
        sources=[
            BriefSource(
                n=n,
                id=it.id,
                title=it.title,
                url=it.original_url,
                publisher=it.publisher,
                published_at=it.published_at,
            )
            for n, item_id in enumerate(brief.sources, 1)
            if (it := rows.get(item_id))
        ],
        model=brief.model,
        created_at=brief.created_at,
    )


@router.get("/trends", response_model=TrendsResponse)
def get_trends(db: Annotated[Session, Depends(get_db)]) -> TrendsResponse:
    """Top rising tags, companies and technologies (last 7 days vs the 28 days before, as shares
    of the items in each window), plus the latest weekly trend brief."""
    now = datetime.now(UTC)
    topics = trends.rising_topics(db, now)
    recent_start = now - timedelta(days=trends.RECENT_DAYS)
    return TrendsResponse(
        recent_start=recent_start,
        baseline_start=recent_start - timedelta(days=trends.BASELINE_DAYS),
        now=now,
        **{k: [RisingTermOut(**vars(t)) for t in v] for k, v in topics.items()},
        brief=latest_brief(db),
    )


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Annotated[Session, Depends(get_db)]) -> StatsResponse:
    """Dashboard data: the ingestion funnel, processed items by category, content type, source and
    day, recent pipeline runs and the estimated AI spend."""
    by_status = dict.fromkeys(ITEM_STATUSES, 0) | dict(
        db.execute(select(Item.status, func.count()).group_by(Item.status)).all()
    )
    processed = Item.status == "processed"

    cats = db.execute(
        select(
            Category.slug,
            Category.name,
            func.count(Item.id),
            func.avg(AIAnnotation.quality_score).filter(Item.id.is_not(None)),
        )
        .select_from(Category)
        .outerjoin(AIAnnotation, AIAnnotation.primary_category == Category.slug)
        .outerjoin(Item, (Item.id == AIAnnotation.item_id) & processed)
        .group_by(Category.slug, Category.name, Category.sort_order)
        .order_by(Category.sort_order, Category.slug)
    ).all()

    types = db.execute(
        select(AIAnnotation.content_type, func.count())
        .join(Item, Item.id == AIAnnotation.item_id)
        .where(processed, AIAnnotation.content_type.is_not(None))
        .group_by(AIAnnotation.content_type)
        .order_by(func.count().desc(), AIAnnotation.content_type)
    ).all()

    sources = db.execute(
        select(
            Source.key,
            Source.name,
            func.count(Item.id),
            func.count(case((processed, 1))),
        )
        .select_from(Source)
        .outerjoin(ItemSource, ItemSource.source_id == Source.id)
        .outerjoin(Item, Item.id == ItemSource.item_id)
        .group_by(Source.key, Source.name)
        .order_by(func.count(Item.id).desc(), Source.key)
    ).all()

    today = datetime.now(UTC).date()
    first = today - timedelta(days=PER_DAY_DAYS - 1)
    day = cast(func.timezone("UTC", Item.published_at), Date)
    counts: dict[date, int] = dict(
        db.execute(select(day, func.count()).where(processed, day >= first).group_by(day)).all()
    )

    runs = db.scalars(
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc(), PipelineRun.id.desc())
        .limit(LAST_RUNS)
    ).all()

    midnight = datetime.combine(today, datetime.min.time(), UTC)
    run_cost = func.coalesce(func.sum(PipelineRun.cost_usd_estimate), 0)
    classifier = float(db.scalar(select(run_cost).where(PipelineRun.kind == "pipeline")) or 0)
    classifier_today = float(
        db.scalar(
            select(run_cost).where(
                PipelineRun.kind == "pipeline", PipelineRun.started_at >= midnight
            )
        )
        or 0
    )
    brief_cost = float(
        db.scalar(select(func.coalesce(func.sum(TrendBrief.cost_usd_estimate), 0))) or 0
    )

    return StatsResponse(
        funnel=Funnel(fetched=sum(by_status.values()), **by_status),
        by_category=[
            CategoryStat(
                slug=slug,
                name=name,
                items=n,
                avg_quality=None if avg is None else round(float(avg), 1),
            )
            for slug, name, n, avg in cats
        ],
        by_content_type=[Count(key=k or "", items=n) for k, n in types],
        by_source=[SourceStat(key=k, name=nm, items=n, processed=p) for k, nm, n, p in sources],
        per_day=[
            DayCount(date=d.isoformat(), items=counts.get(d, 0))
            for d in (first + timedelta(days=i) for i in range(PER_DAY_DAYS))
        ],
        pipeline_runs=[RunOut.model_validate(r, from_attributes=True) for r in runs],
        ai_cost=AiCost(
            classifier_usd=round(classifier, 4),
            classifier_today_usd=round(classifier_today, 4),
            trend_brief_usd=round(brief_cost, 4),
            total_usd=round(classifier + brief_cost, 4),
        ),
    )
