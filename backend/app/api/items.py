from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.common import (
    ApiError,
    Filters,
    Pagination,
    Sort,
    apply_filters,
    base,
    get_db,
    item_filters,
    paginate,
    pagination,
    public_items,
    summary_fields,
)
from app.models import AIAnnotation, Item, ItemSource, Source
from app.recommend.scoring import related
from app.schemas import (
    Coverage,
    DuplicateRef,
    ItemDetail,
    ItemSummary,
    Page,
    RelatedItem,
    SourceRef,
)

router = APIRouter(tags=["items"])

ItemId = Annotated[int, Path(ge=1, le=2**63 - 1)]
RELATED_LIMIT = 6
RELATED_CANDIDATES = 50


@router.get("/items", response_model=Page[ItemSummary])
def list_items(
    filters: Annotated[Filters, Depends(item_filters)],
    pg: Annotated[Pagination, Depends(pagination)],
    db: Annotated[Session, Depends(get_db)],
    sort: Sort = "latest",
) -> Page[ItemSummary]:
    """Processed items. `category` matches any of an item's categories, `source` any source that
    found it. Ties are broken by `published_at DESC, id DESC`."""
    return paginate(db, apply_filters(public_items(), filters), sort, pg)


def _not_found(item_id: int) -> ApiError:
    return ApiError(404, "not_found", f"item {item_id} not found")


@router.get("/items/{item_id}", response_model=ItemDetail)
def get_item(item_id: ItemId, db: Annotated[Session, Depends(get_db)]) -> ItemDetail:
    """One processed item with its annotation, every source that found it, and near-duplicates
    that point at it ("also covered by")."""
    row = db.execute(public_items().where(Item.id == item_id)).first()
    if row is None:
        raise _not_found(item_id)
    item, ann = row[0], row[1]
    coverage = db.execute(
        select(ItemSource, Source.key, Source.name)
        .join(Source, Source.id == ItemSource.source_id)
        .where(ItemSource.item_id == item_id)
        .order_by(ItemSource.is_primary.desc(), ItemSource.first_seen_at, ItemSource.id)
    ).all()
    dups = db.execute(
        select(Item)
        .where(Item.duplicate_of == item_id, Item.status == "duplicate")
        .order_by(Item.published_at.nulls_last(), Item.id)
    ).scalars()
    return ItemDetail(
        **summary_fields(row),
        description=item.description,
        key_insights=ann.key_insights,
        entities=ann.entities,
        related_links=item.related_links,
        coverage=[
            Coverage(
                source=SourceRef(key=key, name=name),
                url=s.source_url,
                title=s.source_title,
                published_at=s.source_published_at,
                first_seen_at=s.first_seen_at,
                engagement=s.source_engagement,
                is_primary=s.is_primary,
            )
            for s, key, name in coverage
        ],
        also_covered_by=[
            DuplicateRef(
                id=d.id,
                title=d.title,
                url=d.original_url,
                publisher=d.publisher,
                published_at=d.published_at,
                similarity=d.duplicate_similarity,
            )
            for d in dups
        ],
    )


@router.get("/items/{item_id}/related", response_model=list[RelatedItem])
def related_items(item_id: ItemId, db: Annotated[Session, Depends(get_db)]) -> list[RelatedItem]:
    """Top 6 processed items by embedding cosine similarity, + 0.1 per shared category. Items
    marked as duplicates are never processed, so the same story is not repeated. An item that has
    no embedding yet gets an empty list (degraded mode, §11.5)."""
    me = db.execute(base(Item.embedding, AIAnnotation.categories).where(Item.id == item_id)).first()
    if me is None:
        raise _not_found(item_id)
    vec, my_cats = me
    if vec is None:
        return []
    distance = Item.embedding.cosine_distance(vec)
    # Filtered HNSW scans can return too few rows without iterative scans (pgvector >= 0.8).
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = db.execute(
        public_items()
        .add_columns(distance)
        .where(Item.id != item_id, Item.embedding.is_not(None))
        .order_by(distance, Item.id)
        .limit(RELATED_CANDIDATES)
    ).all()
    ranked = []
    for r in rows:
        sim = 1.0 - float(r[4])
        ranked.append((related(sim, len(set(my_cats) & set(r[1].categories))), sim, r))
    ranked.sort(key=lambda t: (-t[0], -t[2][0].id))
    return [
        RelatedItem(**summary_fields(r), similarity=round(sim, 4), score=round(score, 4))
        for score, sim, r in ranked[:RELATED_LIMIT]
    ]
