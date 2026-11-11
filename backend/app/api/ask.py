"""Ask NewsDC (PLAN Phase 6, §11.7, §11.8): hybrid retrieval of the top 25 items, re-ranked to 8,
then a streamed, cited answer over Server-Sent Events.

Events, in order: `sources` (the numbered evidence, so the UI can show cards at once), `status`,
`token`* (answer text; unknown citation numbers already removed), then exactly one of `done` or
`error`. An `error` after tokens means the partial answer must be discarded. There is no resume:
after a dropped connection the client sends the question again.
"""

import json
import logging
import threading
from collections.abc import AsyncIterator, Generator
from contextlib import suppress
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from limits import parse, parse_many
from sqlalchemy import Text, cast, func
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.ai import assistant
from app.ai.assistant import CitationFilter, Evidence
from app.ai.classify import Prices
from app.ai.embeddings import Embedder
from app.ai.llm import AnthropicLLM, ChatLLM, LLMError, LLMResponse
from app.api.common import ApiError, Filters, get_db, get_embedder, public_items
from app.api.search import hybrid
from app.config import get_settings
from app.models import AIAnnotation, Item
from app.recommend.scoring import age_hours_sql, ask_rank
from app.schemas import AskRequest, AskSource, ErrorResponse, SourceRef
from app.security import allow, client_key

log = logging.getLogger(__name__)
router = APIRouter(tags=["ask"])

RETRIEVE = 25  # hybrid-search candidates
TOP = 8  # sources given to the model
ASK_LIMIT = parse(get_settings().rate_limit_ask)
ASK_GLOBAL_LIMITS = parse_many(get_settings().rate_limit_ask_global)
# A stream holds a worker thread for the whole answer; Starlette has 40 for every route.
MAX_STREAMS = 8
_streams = threading.BoundedSemaphore(MAX_STREAMS)
BUSY = {"code": "busy", "message": "The assistant is busy right now. Try again in a minute."}

SUGGESTED_QUESTIONS = [
    "What are the latest developments in AI data center infrastructure?",
    "Which hyperscalers are investing in new data centers?",
    "What is emerging in liquid cooling and power availability?",
    "Which articles discuss GPU utilization optimization?",
    "What technologies could improve PUE and WUE?",
]


@lru_cache
def _anthropic() -> AnthropicLLM:
    s = get_settings()
    return AnthropicLLM(
        api_key=s.anthropic_api_key,
        model=s.assistant_model,
        effort=s.assistant_effort,
        timeout_s=s.llm_timeout_seconds,
    )


def get_llm() -> ChatLLM:
    s = get_settings()
    if not (s.anthropic_api_key and s.assistant_model):
        raise ApiError(503, "assistant_unavailable", "Ask NewsDC is not configured")
    return _anthropic()


def retrieval_query(req: AskRequest) -> str:
    """The latest question plus the previous one, so follow-ups like "and in Europe?" still
    retrieve on the topic (Phase 6 step 5)."""
    prev = next((m.content for m in reversed(req.history) if m.role == "user"), "")
    return f"{prev[:500]} {req.question}".strip()


def retrieve(db: Session, embedder: Embedder, query: str, recent: bool) -> list[Any]:
    """Top RETRIEVE hybrid hits, re-ranked by retrieval + relevance + quality + freshness down to
    TOP rows of (Item, AIAnnotation, source key, source name, age_hours). Keywords are OR-ed (a
    question has many words; `ts_rank_cd` still ranks items matching more of them first)."""
    any_word = func.replace(cast(func.plainto_tsquery("english", query), Text), "&", "|")
    fused, _ = hybrid(db, embedder, func.to_tsquery("simple", any_word), query, Filters())
    # Retrieval strength by position: 1.0 for the best hit down to 1/RETRIEVE for the last. Raw RRF
    # scores are too close together (rank 2 has 98% of rank 1's) to weigh against freshness.
    candidates = {item_id: 1 - i / RETRIEVE for i, (item_id, _) in enumerate(fused[:RETRIEVE])}
    if not candidates:
        return []
    rows = db.execute(
        public_items().add_columns(age_hours_sql()).where(Item.id.in_(candidates))
    ).all()

    def score(r: Any) -> float:
        ann: AIAnnotation = r[1]
        return ask_rank(
            candidates[r[0].id],
            ann.relevance_score or 0,
            ann.quality_score or 0,
            r[4],
            recent,
        )

    return sorted(rows, key=lambda r: (-score(r), -r[0].id))[:TOP]


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def answer_events(
    llm: ChatLLM,
    req: AskRequest,
    evidence: list[Evidence],
    sources: list[AskSource],
    request_id: str,
) -> Generator[str, None, None]:
    """The SSE body. Never emits `done` after a failed generation (§11.7)."""
    yield sse("sources", {"sources": [s.model_dump(mode="json") for s in sources]})
    if not evidence:  # nothing to ground an answer on: no LLM call (§11.8)
        yield sse("token", {"text": assistant.NO_EVIDENCE_ANSWER})
        yield sse("done", {"cited": [], "removed_citations": 0, "truncated": False})
        return
    # Taken inside the generator, so a response that never starts streaming holds no slot.
    if not _streams.acquire(blocking=False):
        yield sse("error", BUSY)
        return
    try:
        yield from _generate(llm, req, evidence, request_id)
    finally:
        _streams.release()


def _generate(
    llm: ChatLLM, req: AskRequest, evidence: list[Evidence], request_id: str
) -> Generator[str, None, None]:
    yield sse("status", {"stage": "generating"})
    settings = get_settings()
    cites = CitationFilter(len(evidence))
    final: LLMResponse | None = None
    stream = llm.stream_text(
        system=assistant.system_prompt(),
        messages=assistant.build_messages(
            req.question,
            [m.model_dump() for m in req.history],
            evidence,
            datetime.now(UTC).date(),
        ),
        max_tokens=settings.assistant_max_tokens,
    )
    try:
        for part in stream:
            if isinstance(part, LLMResponse):
                final = part
            elif text := cites.feed(part):
                yield sse("token", {"text": text})
    except LLMError as exc:
        log.warning("ask failed", extra={"request_id": request_id, "error": str(exc)})
        code = "llm_unavailable" if exc.retryable else "llm_error"
        yield sse("error", {"code": code, "message": "The assistant is unavailable right now."})
        return
    finally:
        stream.close()  # also closes the upstream HTTP stream when the client went away
    if tail := cites.flush():
        yield sse("token", {"text": tail})
    if final is None or final.stop_reason == "refusal" or not final.text.strip():
        log.warning(
            "ask produced no answer",
            extra={"request_id": request_id, "stop_reason": final and final.stop_reason},
        )
        msg = "The assistant could not answer this question."
        yield sse("error", {"code": "no_answer", "message": msg})
        return
    prices = Prices(settings.assistant_input_usd_per_mtok, settings.assistant_output_usd_per_mtok)
    log.info(
        "ask answered",
        extra={
            "request_id": request_id,
            "model": final.model,
            "prompt_version": assistant.PROMPT_VERSION,
            "sources": len(evidence),
            "cited": len(cites.cited),
            "removed_citations": cites.removed,
            "stop_reason": final.stop_reason,
            "tokens_in": final.input_tokens + final.cache_read_tokens + final.cache_write_tokens,
            "tokens_out": final.output_tokens,
            "latency_ms": final.latency_ms,
            "cost_usd": str(prices.cost(final)),
        },
    )
    yield sse(
        "done",
        {
            "cited": sorted(cites.cited),
            "removed_citations": cites.removed,
            "truncated": final.stop_reason == "max_tokens",
        },
    )


async def stream_body(events: Generator[str, None, None]) -> AsyncIterator[str]:
    """Runs the blocking generator in a worker thread. When the client disconnects, Starlette
    cancels this coroutine and `finally` closes the generator, which closes the LLM stream."""
    try:
        async for chunk in iterate_in_threadpool(events):
            yield chunk
    finally:
        # A cancel can land while the thread is inside next(); then the generator is closed
        # by the garbage collector right after that call returns.
        with suppress(ValueError):
            events.close()


@router.get("/ask/suggestions", response_model=list[str])
def suggestions() -> list[str]:
    """Example questions for the empty Ask screen."""
    return SUGGESTED_QUESTIONS


@router.post(
    "/ask",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events: `sources`, `status`, `token`*, then `done` or "
            "`error` (see docs/API.md).",
            "content": {"text/event-stream": {"example": 'event: token\ndata: {"text":"…"}\n\n'}},
        },
        503: {"model": ErrorResponse, "description": "Assistant not configured"},
    },
)
def ask(
    req: AskRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    llm: Annotated[ChatLLM, Depends(get_llm)],
) -> StreamingResponse:
    """Answers from NewsDC's collected items only, citing them as `[n]`. Rate limited per IP
    (`RATE_LIMIT_ASK`, default 10/minute) on top of the default limit, and for all clients
    together (`RATE_LIMIT_ASK_GLOBAL`, default 30/minute and 500/day)."""
    if not allow(client_key(request), ASK_LIMIT, "ask"):
        raise ApiError(429, "rate_limited", f"rate limit exceeded: {ASK_LIMIT}")
    rows = retrieve(db, embedder, retrieval_query(req), assistant.is_time_sensitive(req.question))
    # Only answers that will call the LLM use the shared budget; the no-evidence reply is free.
    if rows and not all(allow("all", limit, "ask_global") for limit in ASK_GLOBAL_LIMITS):
        raise ApiError(429, "rate_limited", "Ask NewsDC is busy, try again later")
    evidence, sources = [], []
    for n, r in enumerate(rows, start=1):
        item: Item = r[0]
        ann: AIAnnotation = r[1]
        evidence.append(
            Evidence(
                n,
                item.title,
                item.publisher,
                item.published_at,
                item.original_url,
                ann.summary,
                ann.key_insights,
            )
        )
        sources.append(
            AskSource(
                n=n,
                id=item.id,
                title=item.title,
                url=item.original_url,
                publisher=item.publisher,
                published_at=item.published_at,
                source=SourceRef(key=r[2], name=r[3]) if r[2] else None,
                primary_category=ann.primary_category,
                content_type=ann.content_type,  # type: ignore[arg-type]  # DB CHECK
            )
        )
    db.close()  # retrieval is done; don't hold a connection while the answer streams
    rid = getattr(request.state, "request_id", "")
    return StreamingResponse(
        stream_body(answer_events(llm, req, evidence, sources, rid)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
