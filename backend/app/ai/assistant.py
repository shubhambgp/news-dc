"""Ask NewsDC (PLAN Phase 6, §11.8): the prompt, the numbered evidence block and citation checks.
Pure functions only; retrieval and streaming live in `app/api/ask.py`."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from anthropic.types import AssistantMessageParam, MessageParam, UserMessageParam

# Bump whenever prompts/assistant.md changes; a test pins the file hash to this version.
PROMPT_VERSION = "assistant-v1"
PROMPT_PATH = Path(__file__).parents[1] / "prompts" / "assistant.md"
SUMMARY_MAX_CHARS = 1200
INSIGHTS_MAX = 5
INSIGHT_MAX_CHARS = 300
NO_EVIDENCE_ANSWER = (
    "NewsDC's collected sources don't cover this question. Try different words, or a broader "
    "topic such as cooling, power or hyperscaler investment."
)

_RECENT = re.compile(
    r"\b(latest|newest|recent(ly)?|current(ly)?|today|emerging|upcoming|"
    r"this (week|month|year|quarter)|past (few )?(days|weeks|months)|last (week|month))\b",
    re.IGNORECASE,
)


def system_prompt() -> str:
    return PROMPT_PATH.read_text()


def prompt_hash() -> str:
    return hashlib.sha256(system_prompt().encode()).hexdigest()


def is_time_sensitive(question: str) -> bool:
    """The question asks for recent news, so retrieval prefers recent items (Phase 6 step 1)."""
    return bool(_RECENT.search(question))


@dataclass(frozen=True)
class Evidence:
    """One retrieved item as the model sees it. `n` is its citation number (1-based)."""

    n: int
    title: str
    publisher: str | None
    published_at: datetime | None
    url: str
    summary: str | None
    key_insights: list[dict[str, Any]]


def _q(s: str) -> str:
    """Quoted data: angle brackets are escaped so source text cannot close or open a tag."""
    return s.replace("<", "&lt;").replace(">", "&gt;")


def render_sources(evidence: list[Evidence]) -> str:
    """`[n] title, publisher, date, url, summary, key insights` as tagged, escaped data.
    Lengths are capped, so the context is bounded (8 sources ≈ 3–4k tokens)."""
    parts = []
    for e in evidence:
        insights = [
            f"- {_q(str(i.get('text', ''))[:INSIGHT_MAX_CHARS])}"
            for i in e.key_insights[:INSIGHTS_MAX]
            if i.get("text")
        ]
        parts.append(
            f'<source n="{e.n}">\n'
            f"title: {_q(e.title)}\n"
            f"publisher: {_q(e.publisher or 'unknown')}\n"
            f"published: {e.published_at.date().isoformat() if e.published_at else 'unknown'}\n"
            f"url: {_q(e.url)}\n"
            f"summary: {_q((e.summary or '')[:SUMMARY_MAX_CHARS]) or '(none)'}\n"
            + ("key insights:\n" + "\n".join(insights) + "\n" if insights else "")
            + "</source>"
        )
    return "<sources>\n" + "\n".join(parts) + "\n</sources>"


def build_messages(
    question: str, history: list[dict[str, str]], evidence: list[Evidence], today: date
) -> list[MessageParam]:
    """Earlier turns verbatim, then the evidence and the question. The latest question comes last
    and is the one to answer; the system prompt keeps the rules (§11.8)."""
    msgs: list[MessageParam] = [
        UserMessageParam(role="user", content=m["content"])
        if m["role"] == "user"
        else AssistantMessageParam(role="assistant", content=m["content"])
        for m in history
    ]
    msgs.append(
        UserMessageParam(
            role="user",
            content=f"{render_sources(evidence)}\n\nToday's date: {today.isoformat()}\n\n"
            f"Question: {_q(question)}",
        )
    )
    return msgs


_CITE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
_HOLD_MAX = 16  # an unfinished "[12, 3" longer than this is not a citation


class CitationFilter:
    """Streams the answer through while dropping citation numbers that don't map to a supplied
    source (§11.8). A trailing "[" that may still become a citation is held back until it closes,
    so a marker split across chunks ("[1" + "2]") is checked whole."""

    def __init__(self, n_sources: int) -> None:
        self.n_sources = n_sources
        self.cited: set[int] = set()
        self.removed = 0
        self._buf = ""

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        cut = self._buf.rfind("[")
        if cut != -1 and "]" not in self._buf[cut:] and len(self._buf) - cut <= _HOLD_MAX:
            out, self._buf = self._buf[:cut], self._buf[cut:]
        else:
            out, self._buf = self._buf, ""
        return _CITE.sub(self._check, out)

    def flush(self) -> str:
        out, self._buf = self._buf, ""
        return _CITE.sub(self._check, out)

    def _check(self, m: re.Match[str]) -> str:
        nums = [int(x) for x in re.split(r"\s*,\s*", m.group(1))]
        ok = [x for x in dict.fromkeys(nums) if 1 <= x <= self.n_sources]
        self.removed += sum(1 for x in nums if not 1 <= x <= self.n_sources)
        self.cited.update(ok)
        return f"[{', '.join(map(str, ok))}]" if ok else ""
