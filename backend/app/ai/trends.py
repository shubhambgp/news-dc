"""Emerging trends (PLAN Phase 7): rising topics and the weekly AI-written trend brief.

Rising topics compare how often a tag, company or technology appears in the last 7 days with
the 28 days before. Frequencies are shares of the items published in each window, so a week in
which more items were collected does not make every term look like it is rising.

The brief sends the week's top items (relevant score) to ASSISTANT_MODEL with
`prompts/trend_brief.md`. `[n]` in the stored Markdown refers to `trend_briefs.sources[n-1]`;
numbers outside the evidence are removed before storing (§11.8).
"""

import hashlib
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from anthropic.types import MessageParam
from sqlalchemy import Engine, func
from sqlalchemy.orm import Session

from app.ai.assistant import CitationFilter, Evidence, _q, render_sources
from app.ai.classify import Prices
from app.ai.llm import ChatLLM, LLMError, LLMResponse
from app.api.common import ORDER, base, public_items
from app.models import AIAnnotation, Item, TrendBrief

log = logging.getLogger(__name__)

# Bump whenever prompts/trend_brief.md changes; a test pins the file hash to this version.
PROMPT_VERSION = "trend-brief-v1"
PROMPT_PATH = Path(__file__).parents[1] / "prompts" / "trend_brief.md"
RECENT_DAYS = 7
BASELINE_DAYS = 28
MIN_RECENT = 3  # a term needs this many items this week to count as rising
TOP_TERMS = 10
BRIEF_ITEMS = 30
BRIEF_MIN_ITEMS = 5  # fewer items in the week: no brief
KINDS = ("tags", "companies", "technologies")


def system_prompt() -> str:
    return PROMPT_PATH.read_text()


def prompt_hash() -> str:
    return hashlib.sha256(system_prompt().encode()).hexdigest()


@dataclass(frozen=True)
class RisingTerm:
    term: str
    recent: int  # items in the last 7 days
    baseline: int  # items in the 28 days before
    change_pct: int  # change of the share of items mentioning the term
    new: bool  # not seen in the baseline window


def rising(
    rows: Iterable[tuple[datetime, Iterable[str]]],
    now: datetime,
    *,
    min_recent: int = MIN_RECENT,
    limit: int = TOP_TERMS,
) -> list[RisingTerm]:
    """`rows` are (published_at, terms) per item. Terms are matched case-insensitively and counted
    once per item. A term absent from the baseline is counted as 1 baseline item, so it gets a
    finite change and is ranked with the rest. Only terms that rose are returned, biggest first."""
    recent_start = now - timedelta(days=RECENT_DAYS)
    base_start = recent_start - timedelta(days=BASELINE_DAYS)
    n_recent = n_base = 0
    recent: Counter[str] = Counter()
    baseline: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    for ts, terms in rows:
        if recent_start <= ts < now:
            n_recent += 1
            counter = recent
        elif base_start <= ts < recent_start:
            n_base += 1
            counter = baseline
        else:
            continue
        keys: dict[str, str] = {}
        for t in terms:
            if t := t.strip():
                keys.setdefault(t.casefold(), t)
        for key, t in keys.items():
            counter[key] += 1
            spellings[key][t] += 1
    out = []
    for key, r in recent.items():
        if r < min_recent:
            continue
        b = baseline[key]
        share_recent = r / n_recent
        share_base = max(b, 1) / max(n_base, 1)
        change = round((share_recent / share_base - 1) * 100)
        if change > 0:
            name = min(spellings[key].items(), key=lambda kv: (-kv[1], kv[0]))[0]
            out.append(RisingTerm(name, r, b, change, b == 0))
    out.sort(key=lambda t: (-t.change_pct, -t.recent, t.term.casefold()))
    return out[:limit]


def _outlet(name: str) -> str:
    """ "nytimes.com", "The New York Times" -> comparable keys ("nytimes", "thenewyorktimes")."""
    s = name.casefold().strip()
    if " " not in s and "." in s:  # a domain
        s = s.removeprefix("www.").rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9]", "", s)


def _companies(entities: dict[str, Any] | None, publisher: str | None) -> list[str]:
    """Companies of one item, minus the outlet that published it (the classifier often lists the
    publisher itself, which would make every busy outlet look like a rising company)."""
    names = (entities or {}).get("companies", [])
    if not publisher:
        return list(names)
    # ponytail: exact key match, so "nytimes.com" != "The New York Times"; alias table if it matters
    own = _outlet(publisher)
    return [n for n in names if _outlet(n) != own]


def rising_topics(db: Session, now: datetime) -> dict[str, list[RisingTerm]]:
    """Rising tags, companies and technologies over processed items."""
    ts = func.coalesce(Item.published_at, Item.fetched_at)
    since = now - timedelta(days=RECENT_DAYS + BASELINE_DAYS)
    rows = db.execute(
        base(ts, AIAnnotation.tags, AIAnnotation.entities, Item.publisher).where(
            ts >= since, ts < now
        )
    ).all()
    return {
        "tags": rising(((r[0], r[1] or []) for r in rows), now),
        "companies": rising(((r[0], _companies(r[2], r[3])) for r in rows), now),
        "technologies": rising(((r[0], (r[2] or {}).get("technologies", [])) for r in rows), now),
    }


def render_rising(topics: dict[str, list[RisingTerm]]) -> str:
    lines = [
        f"{kind}: "
        + ", ".join(f"{_q(t.term)} ({'new' if t.new else f'+{t.change_pct}%'})" for t in terms)
        for kind, terms in topics.items()
        if terms
    ]
    return "<rising_topics>\n" + "\n".join(lines) + "\n</rising_topics>" if lines else ""


def build_messages(
    evidence: list[Evidence], topics: dict[str, list[RisingTerm]], start: datetime, end: datetime
) -> list[MessageParam]:
    rising_block = render_rising(topics)
    return [
        {
            "role": "user",
            "content": f"{render_sources(evidence)}\n\n"
            + (f"{rising_block}\n\n" if rising_block else "")
            + f"Week: {start.date().isoformat()} to {end.date().isoformat()}\n\n"
            "Write this week's brief.",
        }
    ]


def week_items(db: Session, start: datetime, end: datetime) -> list[Any]:
    """The week's top BRIEF_ITEMS processed items by relevant score (relevance + quality)."""
    return list(
        db.execute(
            public_items()
            .where(Item.published_at >= start, Item.published_at < end)
            .order_by(*ORDER["relevant"])
            .limit(BRIEF_ITEMS)
        ).all()
    )


def generate_brief(
    engine: Engine, llm: ChatLLM, prices: Prices, max_tokens: int, now: datetime | None = None
) -> TrendBrief | None:
    """Write and store the brief for the 7 days before `now`. Returns None (no LLM call) when the
    week has fewer than BRIEF_MIN_ITEMS items. Raises LLMError when no usable brief came back."""
    end = now or datetime.now(UTC)
    start = end - timedelta(days=RECENT_DAYS)
    with Session(engine) as db:
        rows = week_items(db, start, end)
        if len(rows) < BRIEF_MIN_ITEMS:
            log.info("trend brief skipped: too few items", extra={"items": len(rows)})
            return None
        topics = rising_topics(db, end)
    evidence = [
        Evidence(
            n,
            r[0].title,
            r[0].publisher,
            r[0].published_at,
            r[0].original_url,
            r[1].summary,
            r[1].key_insights,
        )
        for n, r in enumerate(rows, 1)
    ]
    final: LLMResponse | None = None
    stream = llm.stream_text(
        system=system_prompt(),
        messages=build_messages(evidence, topics, start, end),
        max_tokens=max_tokens,
    )
    try:
        for part in stream:
            if isinstance(part, LLMResponse):
                final = part
    finally:
        stream.close()
    if final is None or final.stop_reason in ("refusal", "max_tokens"):
        reason = final and final.stop_reason
        raise LLMError(f"no usable brief (stop_reason={reason})", retryable=False)
    cites = CitationFilter(len(evidence))
    content = (cites.feed(final.text) + cites.flush()).strip()
    if not cites.cited:
        raise LLMError("brief has no valid citations", retryable=False)
    cost = prices.cost(final)
    brief = TrendBrief(
        period_start=start,
        period_end=end,
        content_md=content,
        sources=[r[0].id for r in rows],
        model=final.model,
        prompt_version=PROMPT_VERSION,
        tokens_in=final.input_tokens + final.cache_read_tokens + final.cache_write_tokens,
        tokens_out=final.output_tokens,
        cost_usd_estimate=cost,
    )
    with Session(engine, expire_on_commit=False) as db, db.begin():
        db.add(brief)
    log.info(
        "trend brief stored",
        extra={
            "brief_id": brief.id,
            "model": final.model,
            "prompt_version": PROMPT_VERSION,
            "sources": len(evidence),
            "cited": len(cites.cited),
            "removed_citations": cites.removed,
            "tokens_in": brief.tokens_in,
            "tokens_out": brief.tokens_out,
            "cost_usd": str(cost),
        },
    )
    return brief
