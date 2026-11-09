"""Seed `categories` and `sources` from config/*.yaml (upsert by slug/key).

Runs on backend startup and as `python -m app.seed`. Idempotent and safe to run concurrently
(INSERT ... ON CONFLICT). YAML is validated with Pydantic before anything is written.
"""

import logging
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from sqlalchemy import Engine, func
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.models import SOURCE_TYPES, Category, Source

log = logging.getLogger(__name__)

SLUG = r"^[a-z0-9][a-z0-9_-]*$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryConfig(_Strict):
    slug: str = Field(pattern=SLUG, max_length=64)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    keywords: list[str] = Field(min_length=1)


class SourceConfig(_Strict):
    key: str = Field(pattern=SLUG, max_length=64)
    name: str = Field(min_length=1)
    type: Literal[SOURCE_TYPES]  # type: ignore[valid-type]
    endpoint_or_feed_url: HttpUrl
    enabled: bool
    terms_url: HttpUrl | None
    robots_policy: str
    allowed_fields: list[str] = Field(min_length=1)
    max_requests_per_minute: int = Field(gt=0, le=600)
    backfill_window_days: int = Field(gt=0, le=3650)
    attribution_label: str = Field(min_length=1)

    @model_validator(mode="after")
    def _enabled_needs_terms(self) -> Self:
        # PLAN §11.6: a source is enabled only after its terms have been checked.
        if self.enabled and self.terms_url is None:
            raise ValueError(f"source {self.key!r} is enabled but has no terms_url")
        return self


def _unique(values: list[str], what: str) -> None:
    dupes = {v for v in values if values.count(v) > 1}
    if dupes:
        raise ValueError(f"duplicate {what}: {sorted(dupes)}")


class CategoriesFile(_Strict):
    categories: list[CategoryConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_slugs(self) -> Self:
        _unique([c.slug for c in self.categories], "category slug")
        return self


class SourcesFile(_Strict):
    sources: list[SourceConfig]

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        _unique([s.key for s in self.sources], "source key")
        return self


def load_categories(path: Path) -> list[CategoryConfig]:
    return CategoriesFile.model_validate(yaml.safe_load(path.read_text())).categories


def load_sources(path: Path) -> list[SourceConfig]:
    return SourcesFile.model_validate(yaml.safe_load(path.read_text())).sources


def seed(engine: Engine, config_dir: Path) -> tuple[int, int]:
    """Upsert both files in one transaction. Returns (categories, sources) counts."""
    categories = load_categories(config_dir / "categories.yaml")
    sources = load_sources(config_dir / "sources.yaml")

    with engine.begin() as conn:
        stmt = insert(Category).values(
            [{**c.model_dump(), "sort_order": i} for i, c in enumerate(categories)]
        )
        # `enabled` is left alone on conflict: Admin owns it once the row exists.
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[Category.slug],
                set_={
                    k: stmt.excluded[k] for k in ("name", "description", "keywords", "sort_order")
                }
                | {"updated_at": func.now()},
            )
        )
        if sources:
            rows = [
                {
                    "key": s.key,
                    "name": s.name,
                    "type": s.type,
                    "url": str(s.endpoint_or_feed_url),
                    "enabled": s.enabled,
                    "settings": s.model_dump(
                        mode="json",
                        exclude={"key", "name", "type", "endpoint_or_feed_url", "enabled"},
                    ),
                }
                for s in sources
            ]
            src = insert(Source).values(rows)
            # The YAML is admin-controlled and authoritative for sources, including `enabled`.
            conn.execute(
                src.on_conflict_do_update(
                    index_elements=[Source.key],
                    set_={
                        k: src.excluded[k] for k in ("name", "type", "url", "enabled", "settings")
                    }
                    | {"updated_at": func.now()},
                )
            )
    log.info("seeded config", extra={"categories": len(categories), "sources": len(sources)})
    return len(categories), len(sources)


if __name__ == "__main__":
    from app import db
    from app.logging import setup_logging

    settings = get_settings()
    setup_logging(settings.log_level)
    seed(db.engine, settings.config_dir)
