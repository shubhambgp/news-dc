from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.common import (
    Filters,
    Pagination,
    apply_filters,
    get_db,
    item_filters,
    paginate,
    pagination,
    public_items,
)
from app.schemas import ItemSummary, Page

router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("/relevant", response_model=Page[ItemSummary])
def relevant(
    filters: Annotated[Filters, Depends(item_filters)],
    pg: Annotated[Pagination, Depends(pagination)],
    db: Annotated[Session, Depends(get_db)],
) -> Page[ItemSummary]:
    """Processed items sorted by `relevance_score × quality_score`, then newest first."""
    return paginate(db, apply_filters(public_items(), filters), "relevant_feed", pg)
