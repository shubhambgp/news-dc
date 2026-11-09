"""LLM classification of one item (PLAN Phase 3 node 3, §11.5).

The system prompt is `prompts/classify.md` with the enabled categories filled in. It is identical
for every item, so it is sent as a cached prefix. The answer is constrained by a JSON schema
(structured outputs) and then validated again with Pydantic. Invalid output gets exactly one
repair attempt.
"""

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.ai.llm import LLMClient, LLMError, LLMResponse
from app.models import CONTENT_TYPES

# Bump whenever prompts/classify.md or the output schema changes. A test pins the file hash to
# this version so a prompt edit without a bump fails CI. Old annotations can then be reprocessed.
PROMPT_VERSION = "classify-v2"
PROMPT_PATH = Path(__file__).parents[1] / "prompts" / "classify.md"
MAX_TOKENS = 4000  # bounded response (thinking + JSON); a cut-off answer counts as invalid
ITEM_TEXT_MAX_CHARS = 4000  # article excerpt sent to the model


@dataclass(frozen=True)
class CategoryRef:
    slug: str
    name: str
    description: str


def build_system_prompt(categories: list[CategoryRef]) -> str:
    lines = "\n".join(f"- `{c.slug}`: {c.name}. {c.description}" for c in categories)
    return PROMPT_PATH.read_text().replace("{{CATEGORIES}}", lines)


def prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode()).hexdigest()


def output_schema(slugs: list[str]) -> dict[str, Any]:
    """JSON schema for structured outputs. Every field is required and no nulls are used."""
    slug = {"type": "string", "enum": slugs}
    return {
        "type": "object",
        "properties": {
            "is_relevant": {"type": "boolean"},
            "is_spam": {"type": "boolean"},
            "relevance_score": {"type": "integer"},
            "quality_score": {"type": "integer"},
            "primary_category": slug,
            "categories": {"type": "array", "items": slug},
            "content_type": {"type": "string", "enum": list(CONTENT_TYPES)},
            "summary": {"type": "string"},
            "key_insights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["technical", "business"]},
                        "text": {"type": "string"},
                    },
                    "required": ["type", "text"],
                    "additionalProperties": False,
                },
            },
            "entities": {
                "type": "object",
                "properties": {
                    "companies": {"type": "array", "items": {"type": "string"}},
                    "technologies": {"type": "array", "items": {"type": "string"}},
                    "locations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["companies", "technologies", "locations"],
                "additionalProperties": False,
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "reject_reason": {"type": "string"},
        },
        "required": [
            "is_relevant",
            "is_spam",
            "relevance_score",
            "quality_score",
            "primary_category",
            "categories",
            "content_type",
            "summary",
            "key_insights",
            "entities",
            "tags",
            "reject_reason",
        ],
        "additionalProperties": False,
    }


class Insight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["technical", "business"]
    text: str = Field(min_length=1, max_length=500)


def _clean_names(v: list[str]) -> list[str]:
    out: list[str] = []
    for s in v:
        s = s.strip()[:120]
        if s and s not in out:
            out.append(s)
    return out[:20]


class Entities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    companies: list[str]
    technologies: list[str]
    locations: list[str]

    _clean = field_validator("companies", "technologies", "locations")(_clean_names)


class Classification(BaseModel):
    """Validated classifier output. Validate with context={"slugs": {...}}."""

    model_config = ConfigDict(extra="forbid")

    is_relevant: bool
    is_spam: bool
    relevance_score: int = Field(ge=0, le=100)
    quality_score: int = Field(ge=0, le=100)
    primary_category: str
    categories: list[str] = Field(max_length=6)
    content_type: Literal[CONTENT_TYPES]  # type: ignore[valid-type]
    summary: str = Field(min_length=1, max_length=1500)
    key_insights: list[Insight] = Field(max_length=6)
    entities: Entities
    tags: list[str] = Field(max_length=12)
    reject_reason: str | None = Field(max_length=500)

    @field_validator("summary")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        tags = [re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60] for t in v]
        return list(dict.fromkeys(t for t in tags if t))

    @field_validator("reject_reason")
    @classmethod
    def _empty_is_none(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @model_validator(mode="after")
    def _known_categories(self, info: ValidationInfo) -> Self:
        slugs = (info.context or {}).get("slugs")
        if slugs is None:
            raise ValueError("validation context needs 'slugs'")
        unknown = {self.primary_category, *self.categories} - set(slugs)
        if unknown:
            raise ValueError(f"unknown category slugs: {sorted(unknown)}")
        # Primary first, no repeats.
        self.categories = list(dict.fromkeys([self.primary_category, *self.categories]))[:3]
        return self


@dataclass
class ClassifyResult:
    classification: Classification
    model: str
    tokens_in: int  # all input tokens, cached or not
    tokens_out: int
    latency_ms: int
    attempts: int
    cost_usd: Decimal


@dataclass(frozen=True)
class Prices:
    """USD per million tokens. Cache writes cost 1.25x input and cache reads 0.1x input
    (5-minute cache, Anthropic pricing page)."""

    input: float = 0.0
    output: float = 0.0

    def cost(self, r: LLMResponse) -> Decimal:
        usd = (
            r.input_tokens * self.input
            + r.cache_write_tokens * self.input * 1.25
            + r.cache_read_tokens * self.input * 0.1
            + r.output_tokens * self.output
        ) / 1_000_000
        return Decimal(str(round(usd, 6)))


class InvalidOutput(Exception):
    """The model's answer failed validation twice. Carries the tokens spent on it."""

    def __init__(self, message: str, cost_usd: Decimal) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd


def build_user_message(
    *,
    title: str,
    text: str,
    publisher: str | None,
    source: str,
    url: str,
    published_at: str | None,
    source_tags: list[str],
) -> str:
    """The item as quoted data. Angle brackets are escaped so the text cannot close the tag."""

    def q(s: str) -> str:
        return s.replace("<", "&lt;").replace(">", "&gt;")

    fields = [
        f"title: {q(title)}",
        f"source: {q(source)}",
        f"publisher: {q(publisher or 'unknown')}",
        f"url: {q(url)}",
        f"published: {published_at or 'unknown'}",
    ]
    if source_tags:
        fields.append(f"source tags: {q(', '.join(source_tags[:15]))}")
    body = q(text[:ITEM_TEXT_MAX_CHARS]) if text else "(no description or text available)"
    return "Classify this item.\n\n<item>\n" + "\n".join(fields) + f"\n\n{body}\n</item>"


def classify(
    llm: LLMClient,
    *,
    system: str,
    user: str,
    slugs: list[str],
    prices: Prices,
) -> ClassifyResult:
    """One LLM call, plus at most one repair call if the answer is invalid.

    Raises LLMError (provider problems) or InvalidOutput (two invalid answers)."""
    schema = output_schema(slugs)
    total = LLMResponse("", llm.model, None, 0, 0, 0, 0, 0)
    message = user
    error = ""
    for attempt in (1, 2):
        r = llm.complete_json(system=system, user=message, schema=schema, max_tokens=MAX_TOKENS)
        for f in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "latency_ms",
        ):
            setattr(total, f, getattr(total, f) + getattr(r, f))
        total.model = r.model
        if r.stop_reason == "refusal":
            raise LLMError("model refused to classify the item", retryable=False)
        try:
            if r.stop_reason == "max_tokens":
                raise ValueError(f"answer cut off at max_tokens={MAX_TOKENS}")
            parsed = Classification.model_validate_json(r.text, context={"slugs": set(slugs)})
        except (ValidationError, ValueError) as exc:
            error = str(exc)[:600]
            message = (
                f"{user}\n\nYour previous answer was rejected by validation: {error}\n"
                "Return a corrected JSON object."
            )
            continue
        return ClassifyResult(
            classification=parsed,
            model=total.model,
            tokens_in=total.input_tokens + total.cache_read_tokens + total.cache_write_tokens,
            tokens_out=total.output_tokens,
            latency_ms=total.latency_ms,
            attempts=attempt,
            cost_usd=prices.cost(total),
        )
    raise InvalidOutput(f"invalid classifier output after 2 attempts: {error}", prices.cost(total))
