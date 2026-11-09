import pytest
import yaml
from pydantic import ValidationError

from app.config import get_settings
from app.seed import load_categories, load_sources

CONFIG = get_settings().config_dir


def test_repo_config_is_valid():
    categories = load_categories(CONFIG / "categories.yaml")
    assert len(categories) == 14
    assert categories[0].slug == "dc-infrastructure"
    sources = load_sources(CONFIG / "sources.yaml")
    # Nothing is enabled until Phase 2 verifies terms/robots (PLAN §11.6).
    assert sources and not any(s.enabled for s in sources)


def _write(tmp_path, data):
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


SOURCE = {
    "key": "x",
    "name": "X",
    "type": "rss",
    "endpoint_or_feed_url": "https://example.com/feed",
    "enabled": False,
    "terms_url": None,
    "robots_policy": "unverified",
    "allowed_fields": ["title"],
    "max_requests_per_minute": 10,
    "backfill_window_days": 30,
    "attribution_label": "X",
}


def test_enabled_source_requires_terms_url(tmp_path):
    with pytest.raises(ValidationError, match="no terms_url"):
        load_sources(_write(tmp_path, {"sources": [SOURCE | {"enabled": True}]}))
    ok = SOURCE | {"enabled": True, "terms_url": "https://example.com/terms"}
    assert load_sources(_write(tmp_path, {"sources": [ok]}))[0].enabled


@pytest.mark.parametrize(
    "change",
    [
        {"type": "scraper"},
        {"endpoint_or_feed_url": "file:///etc/passwd"},
        {"key": "Bad Key"},
        {"max_requests_per_minute": 0},
        {"unexpected": 1},
    ],
)
def test_invalid_source_rejected(tmp_path, change):
    with pytest.raises(ValidationError):
        load_sources(_write(tmp_path, {"sources": [SOURCE | change]}))


def test_duplicate_keys_rejected(tmp_path):
    with pytest.raises(ValidationError, match="duplicate source key"):
        load_sources(_write(tmp_path, {"sources": [SOURCE, SOURCE]}))
    cat = {"slug": "a", "name": "A", "description": "d", "keywords": ["k"]}
    with pytest.raises(ValidationError, match="duplicate category slug"):
        load_categories(_write(tmp_path, {"categories": [cat, cat]}))
