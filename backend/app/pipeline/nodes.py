"""Pure decision logic for the pipeline nodes (no DB, no network), unit tested on its own."""

import re
from collections.abc import Iterable

from app.ai.classify import Classification
from app.ingest.common import html_to_text

TEXT_MAX_CHARS = 6000

# Words that signal data center content beyond the category keywords in categories.yaml.
GENERAL_DC_VOCAB = (
    "data center",
    "data centre",
    "datacenter",
    "datacentre",
    "server",
    "cloud infrastructure",
    "ai infrastructure",
    "compute capacity",
    "hpc",
    "high performance computing",
    "edge computing",
    "uptime",
    "megawatts",
)

_ENGLISH_STOPWORDS = frozenset(
    "the and of to in for is on with a an as by at from that this are be it its how why what "
    "new will has have was were or not but".split()
)
# Function words of the other common Latin-script languages (German, Spanish, French,
# Portuguese, Dutch) that are not also English words.
_OTHER_STOPWORDS = frozenset(
    "der das und mit für ist nicht ein eine auf von zu den dem des im sich auch wird werden "
    "el la los las del y en por para con una que es se como más "
    "le les et du une est pour dans sur avec qui pas au aux "
    "os do da em uma não são mais "
    "het een van voor met niet ook zijn".split()
)


def normalize_text(value: str | None) -> str:
    """Strip any HTML, collapse whitespace, cap the length."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", html_to_text(value)).strip()[:TEXT_MAX_CHARS]


def looks_english(text: str) -> bool:
    """Cheap heuristic, no extra dependency. Non-English only on positive evidence: mostly
    non-Latin letters, or at least two function words of another Latin-script language that
    outnumber the English ones. Terse English (headlines, repo descriptions) stays English."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    if sum(not c.isascii() for c in letters) / len(letters) > 0.3:
        return False
    words = re.findall(r"[^\W\d_]+", text.lower())
    english = sum(w in _ENGLISH_STOPWORDS for w in words)
    other = sum(w in _OTHER_STOPWORDS for w in words)
    return not (other >= 2 and other > english)


def keyword_pattern(keywords: Iterable[str]) -> re.Pattern[str]:
    """One case-insensitive, word-bounded alternation; a trailing plural `s` also matches."""
    terms = sorted({k.strip().lower() for k in keywords if k.strip()}, key=len, reverse=True)
    alternation = "|".join(re.escape(t).replace(r"\ ", r"[\s-]+") for t in terms)
    return re.compile(rf"\b(?:{alternation})s?\b", re.IGNORECASE)


def keyword_hits(pattern: re.Pattern[str], text: str) -> set[str]:
    return {m.group(0).lower() for m in pattern.finditer(text)}


def prefilter(
    pattern: re.Pattern[str],
    *,
    title: str,
    text: str,
    source_tags: list[str],
    dc_specific: bool,
) -> tuple[int, str | None]:
    """Returns (keyword score, reject reason or None). No LLM is spent on rejected items."""
    title_hits = keyword_hits(pattern, title)
    score = len(title_hits | keyword_hits(pattern, f"{text} {' '.join(source_tags)}"))
    if dc_specific:
        return score, None
    if not looks_english(f"{title} {text[:1000]}") and not title_hits:
        return score, "non-English text and no data center keyword in the title"
    if score == 0:
        return score, "no data center keywords"
    return score, None


def gate(
    c: Classification, relevance_threshold: int, quality_threshold: int
) -> tuple[str, str | None]:
    """`processed` only if relevant, not spam, and above both thresholds; else `rejected_ai`."""
    if c.is_spam:
        return "rejected_ai", f"spam: {c.reject_reason or 'flagged by classifier'}"
    if not c.is_relevant:
        return "rejected_ai", c.reject_reason or "not relevant"
    if c.relevance_score < relevance_threshold:
        return "rejected_ai", f"relevance {c.relevance_score} < {relevance_threshold}"
    if c.quality_score < quality_threshold:
        return "rejected_ai", f"quality {c.quality_score} < {quality_threshold}"
    return "processed", None
