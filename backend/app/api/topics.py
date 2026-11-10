from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy import any_, func, select
from sqlalchemy.orm import Session

from app.api.common import (
    ORDER,
    SLUG,
    ApiError,
    Filters,
    Pagination,
    Sort,
    apply_filters,
    cached,
    get_db,
    item_filters,
    paginate,
    pagination,
    public_items,
    summary_fields,
)
from app.models import AIAnnotation, Category, Item
from app.schemas import ItemSummary, TopicPage, TopicSummary

router = APIRouter(prefix="/topics", tags=["topics"])

LATEST_PER_TOPIC = 3


@router.get("", response_model=list[TopicSummary])
def list_topics(db: Annotated[Session, Depends(get_db)]) -> list[TopicSummary]:
    """Enabled categories in display order, each with its processed-item count and newest 3
    items. An item counts under every category it has, not only its primary one. Cached 60 s."""
    return cached("topics", lambda: _topics(db))


def _topics(db: Session) -> list[TopicSummary]:
    cats = db.scalars(
        select(Category).where(Category.enabled).order_by(Category.sort_order, Category.slug)
    ).all()
    ranked = (
        select(
            AIAnnotation.item_id,
            Category.slug,
            func.row_number()
            .over(partition_by=Category.slug, order_by=ORDER["latest"])
            .label("rn"),
            func.count().over(partition_by=Category.slug).label("n"),
        )
        .select_from(Category)
        .join(AIAnnotation, Category.slug == any_(AIAnnotation.categories))
        .join(Item, Item.id == AIAnnotation.item_id)
        .where(Item.status == "processed", Category.enabled)
        .subquery()
    )
    top = db.execute(select(ranked).where(ranked.c.rn <= LATEST_PER_TOPIC)).all()
    counts = {t.slug: t.n for t in top}
    rows = db.execute(public_items().where(Item.id.in_({t.item_id for t in top}))).all()
    by_id = {r[0].id: ItemSummary(**summary_fields(r)) for r in rows}
    latest: dict[str, list[ItemSummary]] = {}
    for t in sorted(top, key=lambda t: t.rn):
        latest.setdefault(t.slug, []).append(by_id[t.item_id])
    return [
        TopicSummary(
            slug=c.slug,
            name=c.name,
            description=c.description,
            item_count=counts.get(c.slug, 0),
            latest=latest.get(c.slug, []),
        )
        for c in cats
    ]


@router.get("/{slug}", response_model=TopicPage)
def get_topic(
    slug: Annotated[str, Path(max_length=64, pattern=SLUG)],
    filters: Annotated[Filters, Depends(item_filters)],
    pg: Annotated[Pagination, Depends(pagination)],
    db: Annotated[Session, Depends(get_db)],
    sort: Sort = "latest",
) -> TopicPage:
    """Processed items in one enabled category, with the same filters and sorts as `/items`
    (a `category` parameter is ignored: the path decides)."""
    cat = db.get(Category, slug)
    if cat is None or not cat.enabled:
        raise ApiError(404, "not_found", f"topic {slug!r} not found")
    stmt = apply_filters(public_items(), replace(filters, category=slug))
    return TopicPage(
        slug=cat.slug,
        name=cat.name,
        description=cat.description,
        items=paginate(db, stmt, sort, pg),
    )
