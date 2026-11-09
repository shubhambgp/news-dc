"""The AI processing pipeline (PLAN Phase 3), one LangGraph run per item:

    normalize -> prefilter -> classify -> gate -> embed -> near_duplicate_check -> store
                    |            |          |        |
                    |            |          |        +-> store (embedding failed: stays processed,
                    |            |          |            embedding NULL = pending, retried later)
                    |            |          +-> store (rejected_ai)
                    |            +-> store (failed / retry later / LLM budget used up)
                    +-> store (rejected_prefilter)

`run_pipeline` processes `status = new` items in id order, up to `llm_concurrency` items in
parallel, and never overlaps with another run (Postgres advisory lock). Every outcome, including
rejections, is written by `store` in one transaction together with the item's status. An item is
only updated while it is still `new`, so a retried run cannot write twice.
"""

import logging
import threading
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypedDict

import numpy as np
from langgraph.graph import END, START, StateGraph
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import db
from app.ai.classify import (
    PROMPT_VERSION,
    CategoryRef,
    ClassifyResult,
    InvalidOutput,
    Prices,
    build_system_prompt,
    build_user_message,
    classify,
    prompt_hash,
)
from app.ai.embeddings import Embedder, FastEmbedder
from app.ai.llm import AnthropicLLM, LLMClient, LLMError
from app.config import get_settings
from app.models import AIAnnotation, Category, Item, PipelineRun, Source
from app.pipeline.nodes import GENERAL_DC_VOCAB, gate, keyword_pattern, normalize_text, prefilter

log = logging.getLogger(__name__)

PIPELINE_LOCK_KEY = 7_303_001  # pg advisory lock: one pipeline run at a time
PAGE_SIZE = 50
MAX_AI_ATTEMPTS = 3  # transient LLM failures per item before it is marked failed
PROVIDER_DOWN_AFTER = 5  # consecutive transient failures that abort the run
DUPLICATE_WINDOW = timedelta(days=14)
EMBED_BACKLOG_BATCH = 200


@dataclass(frozen=True)
class ItemInput:
    id: int
    title: str
    description: str | None
    content_text: str | None
    publisher: str | None
    source_key: str
    dc_specific: bool
    url: str
    published_at: datetime | None
    fetched_at: datetime
    source_tags: list[str]
    ai_attempts: int

    @property
    def when(self) -> datetime:
        return self.published_at or self.fetched_at


class ItemState(TypedDict, total=False):
    item: ItemInput
    title: str
    text: str
    status: str  # outcome; "new" means: leave it for a later run
    reason: str | None
    skipped: bool  # LLM budget used up: nothing is written
    result: ClassifyResult
    error: str | None
    ai_attempts: int
    embedding: list[float] | None
    duplicate_of: int
    similarity: float


class Budget:
    """LLM spend control shared by the worker threads (§11.5)."""

    def __init__(self, max_items: int, usd_left: float) -> None:
        self.items_left = max_items
        self.usd_left = usd_left
        self.spent = Decimal(0)
        self.stop_reason: str | None = None
        self._lock = threading.Lock()

    def take(self) -> str | None:
        with self._lock:
            if self.items_left <= 0:
                self.stop_reason = self.stop_reason or "MAX_LLM_ITEMS_PER_RUN reached"
            elif self.usd_left <= 0:
                self.stop_reason = self.stop_reason or "DAILY_LLM_BUDGET_USD reached"
            else:
                self.items_left -= 1
                return None
            return self.stop_reason

    def spend(self, usd: Decimal) -> None:
        with self._lock:
            self.spent += usd
            self.usd_left -= float(usd)


@dataclass
class Deps:
    llm: LLMClient
    embedder: Embedder
    engine: Engine
    system: str
    slugs: list[str]
    prompt_hash: str
    prices: Prices
    relevance_threshold: int
    quality_threshold: int
    near_duplicate_threshold: float
    keywords: Any  # compiled keyword pattern
    budget: Budget
    counts: Counter[str] = field(default_factory=Counter)
    accepted: list[tuple[int, Any, datetime]] = field(default_factory=list)  # this run's items
    lock: threading.Lock = field(default_factory=threading.Lock)
    dup_lock: threading.Lock = field(default_factory=threading.Lock)
    transient_failures: int = 0

    def count(self, key: str) -> None:
        with self.lock:
            self.counts[key] += 1

    def llm_outcome(self, ok: bool) -> None:
        with self.lock:
            self.transient_failures = 0 if ok else self.transient_failures + 1
            down = self.transient_failures >= PROVIDER_DOWN_AFTER
        if down:
            raise LLMError(
                f"LLM provider unavailable ({PROVIDER_DOWN_AFTER} consecutive failures)",
                retryable=True,
                fatal=True,
            )


# --- nodes -------------------------------------------------------------------------------------


def build_graph(deps: Deps) -> Any:
    def normalize_node(state: ItemState) -> ItemState:
        it = state["item"]
        text_ = " ".join(
            filter(None, [normalize_text(it.description), normalize_text(it.content_text)])
        )
        return {"title": normalize_text(it.title), "text": text_}

    def prefilter_node(state: ItemState) -> ItemState:
        it = state["item"]
        _, reason = prefilter(
            deps.keywords,
            title=state["title"],
            text=state["text"],
            source_tags=it.source_tags,
            dc_specific=it.dc_specific,
        )
        return {"status": "rejected_prefilter", "reason": reason} if reason else {}

    def classify_node(state: ItemState) -> ItemState:
        it = state["item"]
        stop = deps.budget.take()
        if stop:
            return {"status": "new", "skipped": True}
        user = build_user_message(
            title=state["title"],
            text=state["text"],
            publisher=it.publisher,
            source=it.source_key,
            url=it.url,
            published_at=it.published_at.isoformat() if it.published_at else None,
            source_tags=it.source_tags,
        )
        try:
            result = classify(
                deps.llm, system=deps.system, user=user, slugs=deps.slugs, prices=deps.prices
            )
        except InvalidOutput as exc:
            deps.budget.spend(exc.cost_usd)
            deps.llm_outcome(ok=True)  # the provider answered
            return {"status": "failed", "error": str(exc)}
        except LLMError as exc:
            if exc.fatal:
                raise
            attempts = it.ai_attempts + 1
            if exc.retryable:
                deps.llm_outcome(ok=False)
                if attempts < MAX_AI_ATTEMPTS:
                    return {"status": "new", "error": str(exc), "ai_attempts": attempts}
            return {"status": "failed", "error": str(exc), "ai_attempts": attempts}
        deps.budget.spend(result.cost_usd)
        deps.llm_outcome(ok=True)
        return {"result": result}

    def gate_node(state: ItemState) -> ItemState:
        c = state["result"].classification
        status, reason = gate(c, deps.relevance_threshold, deps.quality_threshold)
        return {"status": status, "reason": reason}

    def embed_node(state: ItemState) -> ItemState:
        c = state["result"].classification
        try:
            return {"embedding": deps.embedder.embed(f"{state['title']}\n{c.summary}")}
        except Exception as exc:  # keep the annotation; embedding stays pending (§11.5)
            log.warning(
                "embedding failed", extra={"item_id": state["item"].id, "error": str(exc)[:200]}
            )
            return {"embedding": None, "error": f"embedding failed: {type(exc).__name__}"}

    def near_duplicate_node(state: ItemState) -> ItemState:
        it = state["item"]
        vec = np.asarray(state["embedding"], dtype=np.float32)
        # Serialized so two similar items processed in parallel still see each other.
        with deps.dup_lock:
            best_id, best_sim = _nearest_stored(deps.engine, it, vec)
            for other_id, other_vec, other_when in deps.accepted:
                if abs(other_when - it.when) <= DUPLICATE_WINDOW:
                    sim = float(vec @ other_vec)
                    if sim > best_sim:
                        best_id, best_sim = other_id, sim
            if best_id is not None and best_sim > deps.near_duplicate_threshold:
                return {"status": "duplicate", "duplicate_of": best_id, "similarity": best_sim}
            deps.accepted.append((it.id, vec, it.when))
        return {}

    def store_node(state: ItemState) -> ItemState:
        _store(deps, state)
        return {}

    g = StateGraph(ItemState)
    g.add_node("normalize", normalize_node)
    g.add_node("prefilter", prefilter_node)
    g.add_node("classify", classify_node)
    g.add_node("gate", gate_node)
    g.add_node("embed", embed_node)
    g.add_node("near_duplicate_check", near_duplicate_node)
    g.add_node("store", store_node)
    g.add_edge(START, "normalize")
    g.add_edge("normalize", "prefilter")
    g.add_conditional_edges("prefilter", lambda s: "store" if s.get("status") else "classify")
    g.add_conditional_edges("classify", lambda s: "store" if s.get("status") else "gate")
    g.add_conditional_edges("gate", lambda s: "embed" if s["status"] == "processed" else "store")
    g.add_conditional_edges(
        "embed", lambda s: "near_duplicate_check" if s.get("embedding") else "store"
    )
    g.add_edge("near_duplicate_check", "store")
    g.add_edge("store", END)
    return g.compile()


def _nearest_stored(engine: Engine, it: ItemInput, vec: Any) -> tuple[int | None, float]:
    """Most similar processed item published within ±14 days (HNSW, cosine)."""
    distance = Item.embedding.cosine_distance(vec.tolist())
    when = func.coalesce(Item.published_at, Item.fetched_at)
    with Session(engine) as s, s.begin():
        # Filtered HNSW scans can return too few rows without iterative scans (pgvector >= 0.8).
        s.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        row = s.execute(
            select(Item.id, distance)
            .where(
                Item.status == "processed",
                Item.embedding.is_not(None),
                Item.id != it.id,
                when.between(it.when - DUPLICATE_WINDOW, it.when + DUPLICATE_WINDOW),
            )
            .order_by(distance)
            .limit(1)
        ).first()
    return (row[0], 1.0 - float(row[1])) if row else (None, -1.0)


def _store(deps: Deps, state: ItemState) -> None:
    """Annotation + item status in one transaction, only while the item is still `new`."""
    if state.get("skipped"):
        deps.count("skipped_budget")
        return
    it = state["item"]
    status = state["status"]
    values: dict[str, Any] = {
        "status": status,
        "status_reason": state.get("error"),
        "ai_attempts": state.get("ai_attempts", it.ai_attempts),
        "duplicate_of": None,
        "duplicate_similarity": None,
        "duplicate_reason": None,
        "updated_at": func.now(),
    }
    if status == "duplicate":
        values |= {
            "duplicate_of": state["duplicate_of"],
            "duplicate_similarity": round(state["similarity"], 4),
            "duplicate_reason": (
                f"title+summary embedding cosine similarity {state['similarity']:.3f} > "
                f"{deps.near_duplicate_threshold} with item {state['duplicate_of']}, "
                f"published within {DUPLICATE_WINDOW.days} days"
            ),
        }
    if state.get("embedding"):
        values["embedding"] = state["embedding"]
    if status in ("rejected_prefilter", "rejected_ai"):
        values["status_reason"] = state.get("reason")

    with Session(deps.engine) as s, s.begin():
        updated = s.execute(
            update(Item).where(Item.id == it.id, Item.status == "new").values(**values)
        ).rowcount  # type: ignore[attr-defined]
        if not updated:
            log.info("item no longer new; result discarded", extra={"item_id": it.id})
            deps.count("skipped_changed")
            return
        result = state.get("result")
        if result is not None:
            c = result.classification
            row = {
                "item_id": it.id,
                "is_relevant": c.is_relevant,
                "is_spam": c.is_spam,
                "relevance_score": c.relevance_score,
                "quality_score": c.quality_score,
                "primary_category": c.primary_category,
                "categories": c.categories,
                "content_type": c.content_type,
                "summary": c.summary,
                "key_insights": [i.model_dump() for i in c.key_insights],
                "entities": c.entities.model_dump(),
                "tags": c.tags,
                "reject_reason": state.get("reason") if status == "rejected_ai" else None,
                "model": result.model,
                "prompt_version": PROMPT_VERSION,
                "prompt_hash": deps.prompt_hash,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "latency_ms": result.latency_ms,
                "attempts": result.attempts,
                "cost_usd_estimate": result.cost_usd,
            }
            ins = insert(AIAnnotation).values(row)
            s.execute(
                ins.on_conflict_do_update(
                    index_elements=[AIAnnotation.item_id],
                    set_={k: ins.excluded[k] for k in row if k != "item_id"}
                    | {"updated_at": func.now()},
                )
            )
    deps.count("retry_later" if status == "new" else status)
    log.info(
        "item stored",
        extra={
            "item_id": it.id,
            "status": status,
            "reason": state.get("reason") or state.get("error"),
        },
    )


def _record_crash(engine: Engine, it: ItemInput, exc: Exception) -> str:
    """A bug or DB error on one item: count the attempt so it cannot loop forever."""
    attempts = it.ai_attempts + 1
    status = "failed" if attempts >= MAX_AI_ATTEMPTS else "new"
    with Session(engine) as s, s.begin():
        s.execute(
            update(Item)
            .where(Item.id == it.id, Item.status == "new")
            .values(
                status=status,
                ai_attempts=attempts,
                status_reason=f"{type(exc).__name__}: {exc}"[:500],
                updated_at=func.now(),
            )
        )
    return "failed" if status == "failed" else "retry_later"


# --- run ---------------------------------------------------------------------------------------


@dataclass
class PipelineResult:
    run_id: int | None
    status: str  # succeeded | partial | failed | skipped
    counts: dict[str, int]
    cost_usd: float = 0.0
    stop_reason: str | None = None
    error: str | None = None
    retryable: bool = True  # for the job layer: is a failed run worth retrying?


def run_pipeline(
    *,
    limit: int | None = None,
    max_llm_items: int | None = None,
    trigger: str = "cli",
    engine: Engine | None = None,
    llm: LLMClient | None = None,
    embedder: Embedder | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> PipelineResult:
    """Process up to `limit` new items (default: all), spending at most `max_llm_items` LLM calls
    (default MAX_LLM_ITEMS_PER_RUN). Returns `skipped` if another run holds the lock."""
    eng = engine or db.engine
    with eng.connect() as lock_conn:
        got = lock_conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": PIPELINE_LOCK_KEY})
        lock_conn.commit()  # the session lock outlives the transaction; don't sit idle in one
        if not got:
            log.info("pipeline already running; skipped")
            return PipelineResult(None, "skipped", {}, stop_reason="another pipeline run is active")
        try:
            return _run(eng, limit, max_llm_items, trigger, llm, embedder, should_stop)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PIPELINE_LOCK_KEY})
            lock_conn.commit()


def _deps(
    eng: Engine, llm: LLMClient, embedder: Embedder, max_llm_items: int | None
) -> tuple[Deps, dict[int, tuple[str, bool]]]:
    settings = get_settings()
    with Session(eng) as s:
        cats = s.execute(
            select(Category.slug, Category.name, Category.description, Category.keywords)
            .where(Category.enabled)
            .order_by(Category.sort_order, Category.slug)
        ).all()
        sources = {
            sid: (key, bool(cfg.get("dc_specific", False)))
            for sid, key, cfg in s.execute(select(Source.id, Source.key, Source.settings))
        }
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent_today = float(
            s.scalar(
                select(func.coalesce(func.sum(PipelineRun.cost_usd_estimate), 0)).where(
                    PipelineRun.kind == "pipeline", PipelineRun.started_at >= midnight
                )
            )
            or 0
        )
    if not cats:
        raise RuntimeError("no enabled categories; run `python -m app.seed`")
    system = build_system_prompt([CategoryRef(c.slug, c.name, c.description) for c in cats])
    prices = Prices(settings.classifier_input_usd_per_mtok, settings.classifier_output_usd_per_mtok)
    usd_left = settings.daily_llm_budget_usd - spent_today if prices.input else float("inf")
    if not prices.input:
        log.warning("classifier prices not configured; daily USD limit is not enforced")
    deps = Deps(
        llm=llm,
        embedder=embedder,
        engine=eng,
        system=system,
        slugs=[c.slug for c in cats],
        prompt_hash=prompt_hash(system),
        prices=prices,
        relevance_threshold=settings.relevance_threshold,
        quality_threshold=settings.quality_threshold,
        near_duplicate_threshold=settings.near_duplicate_threshold,
        keywords=keyword_pattern([k for c in cats for k in c.keywords] + list(GENERAL_DC_VOCAB)),
        budget=Budget(max_llm_items or settings.max_llm_items_per_run, usd_left),
    )
    return deps, sources


def _load_page(
    eng: Engine, sources: dict[int, tuple[str, bool]], after_id: int, n: int
) -> list[ItemInput]:
    with Session(eng) as s:
        rows = s.scalars(
            select(Item).where(Item.status == "new", Item.id > after_id).order_by(Item.id).limit(n)
        ).all()
    out = []
    for r in rows:
        key, dc_specific = sources.get(r.primary_source_id or -1, ("unknown", False))
        out.append(
            ItemInput(
                id=r.id,
                title=r.title,
                description=r.description,
                content_text=r.content_text,
                publisher=r.publisher,
                source_key=key,
                dc_specific=dc_specific,
                url=r.canonical_url,
                published_at=r.published_at,
                fetched_at=r.fetched_at,
                source_tags=list(r.source_tags or []),
                ai_attempts=r.ai_attempts,
            )
        )
    return out


def embed_backlog(eng: Engine, embedder: Embedder, limit: int = EMBED_BACKLOG_BATCH) -> int:
    """Embed processed items whose embedding failed earlier (no near-duplicate check)."""
    with Session(eng) as s:
        rows = s.execute(
            select(Item.id, Item.title, AIAnnotation.summary)
            .join(AIAnnotation, AIAnnotation.item_id == Item.id)
            .where(Item.status == "processed", Item.embedding.is_(None))
            .order_by(Item.id)
            .limit(limit)
        ).all()
    done = 0
    for item_id, title, summary in rows:
        try:
            vec = embedder.embed(f"{normalize_text(title)}\n{summary or ''}")
        except Exception as exc:
            log.warning(
                "embedding retry failed", extra={"item_id": item_id, "error": str(exc)[:200]}
            )
            break  # the embedder is still broken; try next run
        with Session(eng) as s, s.begin():
            s.execute(
                update(Item)
                .where(Item.id == item_id)
                .values(embedding=vec, status_reason=None, updated_at=func.now())
            )
        done += 1
    return done


def _run(
    eng: Engine,
    limit: int | None,
    max_llm_items: int | None,
    trigger: str,
    llm: LLMClient | None,
    embedder: Embedder | None,
    should_stop: Callable[[], bool],
) -> PipelineResult:
    settings = get_settings()
    if llm is None:
        llm = AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.classifier_model,
            effort=settings.classifier_effort,
            timeout_s=settings.llm_timeout_seconds,
        )
    embedder = embedder or FastEmbedder()
    deps, sources = _deps(eng, llm, embedder, max_llm_items)
    graph = build_graph(deps)

    with Session(eng, expire_on_commit=False) as s:
        run = PipelineRun(kind="pipeline", trigger=trigger)
        s.add(run)
        s.commit()
        ctx = {"run_id": run.id}
        log.info("pipeline started", extra=ctx | {"limit": limit, "model": llm.model})

        embedded = embed_backlog(eng, embedder)
        if embedded:
            log.info("embedded backlog", extra=ctx | {"items": embedded})

        def process(it: ItemInput) -> None:
            try:
                graph.invoke({"item": it})
            except LLMError as exc:
                if exc.fatal:
                    raise
                deps.count(_record_crash(eng, it, exc))
            except Exception as exc:
                log.exception("item crashed", extra=ctx | {"item_id": it.id})
                deps.count(_record_crash(eng, it, exc))

        cursor, examined = 0, 0
        error: str | None = None
        retryable = True
        stop_reason: str | None = None
        with ThreadPoolExecutor(settings.llm_concurrency) as pool:
            while True:
                if should_stop():
                    stop_reason = "shutdown requested"
                    break
                n = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - examined)
                page = _load_page(eng, sources, cursor, n) if n > 0 else []
                if not page:
                    break
                cursor, examined = page[-1].id, examined + len(page)
                futures = [pool.submit(process, it) for it in page]
                for f in futures:
                    try:
                        f.result()
                    except LLMError as exc:  # fatal: bad key/model, or the provider is down
                        error, retryable = (error or str(exc)), exc.retryable
                _progress(s, run, deps, examined)
                if error:
                    break
                if deps.budget.stop_reason:
                    stop_reason = deps.budget.stop_reason
                    break

        status = "failed" if error else ("partial" if deps.counts["failed"] else "succeeded")
        run.status = status
        run.error = error
        run.stop_reason = stop_reason
        run.finished_at = datetime.now(UTC)
        _progress(s, run, deps, examined)
        log.info(
            "pipeline finished",
            extra=ctx | dict(deps.counts) | {"status": status, "stop_reason": stop_reason},
        )
        return PipelineResult(
            run.id,
            status,
            dict(deps.counts),
            float(deps.budget.spent),
            stop_reason,
            error,
            retryable,
        )


def _progress(s: Session, run: PipelineRun, deps: Deps, examined: int) -> None:
    """Persist counts and cost after every page, so the daily spend total survives a crash."""
    c = deps.counts
    run.fetched = examined
    run.rejected_prefilter = c["rejected_prefilter"]
    run.rejected_ai = c["rejected_ai"]
    run.processed = c["processed"]
    run.duplicates = c["duplicate"]
    run.failed = c["failed"]
    run.cost_usd_estimate = deps.budget.spent
    s.commit()


def current_prompt_hash(engine: Engine) -> str:
    """Hash of the system prompt the next run would use (template + enabled categories)."""
    with Session(engine) as s:
        cats = s.execute(
            select(Category.slug, Category.name, Category.description)
            .where(Category.enabled)
            .order_by(Category.sort_order, Category.slug)
        ).all()
    return prompt_hash(build_system_prompt([CategoryRef(*c) for c in cats]))


_RESET = {
    "status": "new",
    "ai_attempts": 0,
    "status_reason": None,
    "duplicate_of": None,
    "duplicate_similarity": None,
    "duplicate_reason": None,
    "updated_at": func.now(),
}


def reprocess_outdated(engine: Engine | None = None) -> int:
    """Admin/CLI action: send items classified with another prompt version, or another prompt
    hash (an Admin category edit changes the hash, D-035), back to `new`. The next run
    classifies them again with the current prompt; their annotation is replaced."""
    eng = engine or db.engine
    outdated = select(AIAnnotation.item_id).where(
        AIAnnotation.prompt_version.is_distinct_from(PROMPT_VERSION)
        | AIAnnotation.prompt_hash.is_distinct_from(current_prompt_hash(eng))
    )
    with Session(eng) as s, s.begin():
        return s.execute(
            update(Item)
            .where(
                Item.id.in_(outdated), Item.status.in_(("processed", "rejected_ai", "duplicate"))
            )
            .values(**_RESET)
        ).rowcount  # type: ignore[attr-defined]


def reprocess_item(engine: Engine, item_id: int) -> bool:
    """Admin action: send one item back to `new`, whatever its status. False if it doesn't exist."""
    with Session(engine) as s, s.begin():
        return bool(
            s.execute(update(Item).where(Item.id == item_id).values(**_RESET)).rowcount  # type: ignore[attr-defined]
        )
