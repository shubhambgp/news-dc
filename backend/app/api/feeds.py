from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import (
    ApiError,
    Filters,
    Pagination,
    apply_filters,
    get_db,
    item_filters,
    paginate,
    pagination,
    public_items,
    summary_fields,
)
from app.models import Category, Item
from app.recommend import foryou
from app.schemas import ForYouItem, ForYouPage, ItemSummary, Page, Profile

router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("/trending", response_model=Page[ItemSummary])
def trending(
    filters: Annotated[Filters, Depends(item_filters)],
    pg: Annotated[Pagination, Depends(pagination)],
    db: Annotated[Session, Depends(get_db)],
) -> Page[ItemSummary]:
    """Hacker News gravity: `(1 + points + 2·comments + quality/10 + 5·coverage) /
    (age_hours + 2)^1.5`, then newest first."""
    return paginate(db, apply_filters(public_items(), filters), "trending", pg)


@router.get("/relevant", response_model=Page[ItemSummary])
def relevant(
    filters: Annotated[Filters, Depends(item_filters)],
    pg: Annotated[Pagination, Depends(pagination)],
    db: Annotated[Session, Depends(get_db)],
) -> Page[ItemSummary]:
    """`(0.6·relevance + 0.4·quality) / (1 + age_days/30)`, then newest first."""
    return paginate(db, apply_filters(public_items(), filters), "relevant", pg)


@router.post("/foryou", response_model=ForYouPage)
def for_you(
    profile: Profile,
    pg: Annotated[Pagination, Depends(pagination)],
    db: Annotated[Session, Depends(get_db)],
) -> ForYouPage:
    """Personalised feed from the anonymous localStorage profile. Read, bookmarked and dismissed
    items are excluded. About every 5th item is `discover`. An empty profile returns Trending +
    Most relevant with `cold_start: true`. Each item has a `reason` ("Why am I seeing this?")."""
    names = {slug: name for slug, name in db.execute(select(Category.slug, Category.name))}
    unknown = sorted(
        (profile.category_weights.keys() | set(profile.explicit_topics)) - names.keys()
    )
    if unknown:
        raise ApiError(422, "validation_error", f"body: unknown category {', '.join(unknown[:5])}")
    picks, cold = foryou.rank(db, profile, names)
    page = picks[pg.offset : pg.offset + pg.page_size]
    rows = db.execute(public_items().where(Item.id.in_([p.id for p in page]))).all()
    by_id = {r[0].id: r for r in rows}
    return ForYouPage(
        items=[
            ForYouItem(
                **summary_fields(by_id[p.id]), kind=p.kind, reason=p.reason, score=round(p.score, 4)
            )
            for p in page
        ],
        page=pg.page,
        page_size=pg.page_size,
        total=len(picks),
        has_more=pg.offset + len(page) < len(picks),
        cold_start=cold,
    )
