"""Hybrid search (PLAN Phase 4): Postgres full-text search and pgvector similarity, each ranked
separately and merged with Reciprocal Rank Fusion. Falls back to keyword-only when the embedding
model is unavailable (§11.5)."""

import html
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder
from app.api.common import (
    ApiError,
    Filters,
    Pagination,
    apply_filters,
    base,
    get_db,
    get_embedder,
    item_filters,
    pagination,
    public_items,
    summary_fields,
)
from app.config import get_settings
from app.models import AIAnnotation, Item
from app.schemas import Page, SearchHit

log = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

CANDIDATES = 100  # per retriever; the fused list is at most 2 × this
RRF_K = 60  # the usual RRF constant: score = Σ 1 / (k + rank)
# Private-use characters mark matches; the snippet is HTML-escaped and they become <mark>.
_START, _STOP = "", ""
_HEADLINE_OPTS = (
    f"StartSel={_START}, StopSel={_STOP}, MaxWords=35, MinWords=12, MaxFragments=2, "
    'FragmentDelimiter=" … "'
)


class SearchPage(Page[SearchHit]):
    mode: Literal["hybrid", "keyword"] = "hybrid"


def rrf(*rankings: list[int]) -> list[tuple[int, float]]:
    """Fuse ranked id lists; ties are broken by id DESC so the order is deterministic."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], -kv[0]))


def render_snippet(headline: str) -> str:
    return html.escape(headline).replace(_START, "<mark>").replace(_STOP, "</mark>")


@router.get("/search", response_model=SearchPage)
def search(
    q: Annotated[str, Query(min_length=1, max_length=200, description="Web-search syntax.")],
    filters: Annotated[Filters, Depends(item_filters)],
    pg: Annotated[Pagination, Depends(pagination)],
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> SearchPage:
    """Keyword ranking uses `websearch_to_tsquery` and `ts_rank_cd` over the title, description,
    article text and AI summary; semantic ranking uses cosine distance of the query embedding,
    keeping hits with similarity ≥ `SEARCH_MIN_SIMILARITY`.
    `snippet` comes from `ts_headline`."""
    q = q.strip()
    if not q:
        raise ApiError(422, "validation_error", "query.q must not be blank")
    tsq = func.websearch_to_tsquery("english", q)
    doc = Item.tsv.op("||")(AIAnnotation.summary_tsv)
    keyword_ids = list(
        db.scalars(
            apply_filters(base(Item.id), filters)
            .where(or_(Item.tsv.op("@@")(tsq), AIAnnotation.summary_tsv.op("@@")(tsq)))
            .order_by(func.ts_rank_cd(doc, tsq).desc(), Item.id.desc())
            .limit(CANDIDATES)
        )
    )
    mode: Literal["hybrid", "keyword"] = "hybrid"
    semantic_ids: list[int] = []
    try:
        vec = embedder.embed(q)
    except Exception as exc:  # degrade to keyword search, never fail the request
        log.warning("search embedding failed; keyword only", extra={"error": type(exc).__name__})
        mode = "keyword"
    else:
        distance = Item.embedding.cosine_distance(vec)
        db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        semantic_ids = list(
            db.scalars(
                apply_filters(base(Item.id), filters)
                .where(
                    Item.embedding.is_not(None),
                    distance < 1.0 - get_settings().search_min_similarity,
                )
                .order_by(distance, Item.id.desc())
                .limit(CANDIDATES)
            )
        )

    fused = rrf(keyword_ids, semantic_ids)
    page = fused[pg.offset : pg.offset + pg.page_size]
    snippet = func.ts_headline(
        "english",
        func.coalesce(AIAnnotation.summary, Item.description, Item.title),
        tsq,
        _HEADLINE_OPTS,
    )
    rows = db.execute(
        public_items().add_columns(snippet).where(Item.id.in_([i for i, _ in page]))
    ).all()
    by_id = {r[0].id: r for r in rows}
    hits = [
        SearchHit(**summary_fields(by_id[i]), snippet=render_snippet(by_id[i][4]), score=s)
        for i, s in page
        if i in by_id
    ]
    return SearchPage(
        items=hits,
        page=pg.page,
        page_size=pg.page_size,
        total=len(fused),
        has_more=pg.offset + len(page) < len(fused),
        mode=mode,
    )
