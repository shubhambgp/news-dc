"""Database integration tests: migrations, seeds and constraints against real Postgres + pgvector.

Set TEST_DATABASE_URL to a THROWAWAY database (its public schema is dropped). Skipped otherwise.
"""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.exc import DataError, IntegrityError

from alembic import command
from app.config import get_settings
from app.ingest.common import canonicalize_url, url_hash
from app.seed import seed

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

TABLES = {
    "sources",
    "categories",
    "items",
    "item_sources",
    "ai_annotations",
    "pipeline_runs",
    "trend_briefs",
}


def _alembic() -> Config:
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", URL or "")
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(URL or "")
    with eng.begin() as conn:  # truly empty database
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(_alembic(), "head")
    seed(eng, get_settings().config_dir)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine):
    """A connection whose work is always rolled back."""
    with engine.connect() as c:
        tx = c.begin()
        yield c
        tx.rollback()


def test_fresh_migration_creates_schema(engine):
    insp = inspect(engine)
    assert TABLES <= set(insp.get_table_names())
    indexes = {i["name"] for i in insp.get_indexes("items")}
    assert {
        "ix_items_tsv",
        "ix_items_embedding_hnsw",
        "ix_items_published_at_id",
        "ix_items_status",
    } <= indexes
    assert "ix_ai_annotations_primary_category" in {
        i["name"] for i in insp.get_indexes("ai_annotations")
    }
    with engine.connect() as c:
        assert c.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        hnsw = c.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_items_embedding_hnsw'")
        )
        assert "hnsw" in hnsw and "vector_cosine_ops" in hnsw


def test_models_match_migrations(engine):
    command.check(_alembic())  # raises if models and migrations drift apart


def test_downgrade_and_upgrade_roundtrip(engine):
    cfg = _alembic()
    command.downgrade(cfg, "base")
    assert not TABLES & set(inspect(engine).get_table_names())
    command.upgrade(cfg, "head")
    seed(engine, get_settings().config_dir)
    assert TABLES <= set(inspect(engine).get_table_names())


def test_seed_loads_14_categories_and_is_idempotent(engine):
    config_dir = get_settings().config_dir
    with engine.begin() as c:
        c.execute(text("UPDATE categories SET enabled = false WHERE slug = 'cooling'"))
    seed(engine, config_dir)
    seed(engine, config_dir)
    with engine.begin() as c:
        assert c.scalar(text("SELECT count(*) FROM categories")) == 14
        assert c.scalar(text("SELECT count(*) FROM sources")) == 3
        # Admin's toggle survives a re-seed; YAML-owned fields are refreshed.
        assert c.scalar(text("SELECT enabled FROM categories WHERE slug = 'cooling'")) is False
        c.execute(text("UPDATE categories SET enabled = true WHERE slug = 'cooling'"))
        order = c.scalars(text("SELECT slug FROM categories ORDER BY sort_order")).all()
    assert order[0] == "dc-infrastructure" and order[-1] == "emerging-tech"


# --- constraints -----------------------------------------------------------------------------


def _source_id(c: Connection, key: str = "hn") -> int:
    return c.scalar(text("SELECT id FROM sources WHERE key = :k"), {"k": key})


def _item(c: Connection, url: str, title: str = "Liquid cooling for GPU clusters", **cols) -> int:
    canonical = canonicalize_url(url)
    values = {
        "original_url": url,
        "canonical_url": canonical,
        "url_hash": url_hash(canonical),
        "title": title,
        **cols,
    }
    names = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    return c.scalar(text(f"INSERT INTO items ({names}) VALUES ({params}) RETURNING id"), values)


def _fails(c: Connection, sql: str, params=None, exc=IntegrityError):
    sp = c.begin_nested()
    with pytest.raises(exc):
        c.execute(text(sql), params or {})
    sp.rollback()


def test_url_hash_is_unique(conn):
    _item(conn, "https://www.example.com/a/?utm_source=x")
    sp = conn.begin_nested()
    with pytest.raises(IntegrityError):
        _item(conn, "https://example.com/a")  # same canonical URL
    sp.rollback()
    # The ingestion path: ON CONFLICT keeps one row.
    canonical = canonicalize_url("https://example.com/a")
    conn.execute(
        text(
            "INSERT INTO items (original_url, canonical_url, url_hash, title) "
            "VALUES (:u, :u, :h, 't') ON CONFLICT (url_hash) DO NOTHING"
        ),
        {"u": canonical, "h": url_hash(canonical)},
    )
    assert conn.scalar(text("SELECT count(*) FROM items")) == 1


def test_item_checks(conn):
    _fails(
        conn,
        "INSERT INTO items (original_url, canonical_url, url_hash, title, status) VALUES ('u','u','h','t','bogus')",
    )
    _fails(
        conn,
        "INSERT INTO items (original_url, canonical_url, url_hash, title, points) VALUES ('u','u','h','t',-1)",
    )
    item = _item(conn, "https://example.com/self")
    _fails(conn, "UPDATE items SET duplicate_of = id WHERE id = :i", {"i": item})
    _fails(conn, "UPDATE items SET duplicate_similarity = 1.5 WHERE id = :i", {"i": item})


def test_tsv_is_generated_and_searchable(conn):
    item = _item(
        conn, "https://example.com/t", title="Immersion cooling arrives", description="A new campus"
    )
    found = conn.scalar(
        text(
            "SELECT id FROM items WHERE tsv @@ websearch_to_tsquery('english', 'immersion cooled')"
        )
    )
    assert found == item


def test_embedding_dimension_enforced(conn):
    item = _item(conn, "https://example.com/e")
    conn.execute(
        text("UPDATE items SET embedding = :v WHERE id = :i"), {"v": str([0.1] * 384), "i": item}
    )
    _fails(
        conn,
        "UPDATE items SET embedding = :v WHERE id = :i",
        {"v": str([0.1] * 3), "i": item},
        exc=DataError,
    )


def test_annotation_checks(conn):
    item = _item(conn, "https://example.com/n")
    base = "INSERT INTO ai_annotations (item_id, is_relevant, relevance_score, quality_score, content_type, primary_category) VALUES (:i, true, :r, :q, :t, :c)"
    good = {"i": item, "r": 80, "q": 60, "t": "news", "c": "cooling"}
    for bad in ({"r": 101}, {"q": -1}, {"t": "opinion"}, {"c": "not-a-category"}):
        _fails(conn, base, good | bad)
    conn.execute(text(base), good)


def test_item_sources_provenance(conn):
    hn, gh = _source_id(conn, "hn"), _source_id(conn, "github")
    item = _item(conn, "https://example.com/p")
    ins = "INSERT INTO item_sources (item_id, source_id, external_id, source_url, is_primary) VALUES (:i, :s, :e, 'u', :p)"
    conn.execute(text(ins), {"i": item, "s": hn, "e": "1", "p": True})
    # A second source for the same item is allowed (multi-source provenance).
    conn.execute(text(ins), {"i": item, "s": gh, "e": "repo/x", "p": False})
    _fails(conn, ins, {"i": item, "s": hn, "e": "2", "p": False})  # same (source, item)
    other = _item(conn, "https://example.com/q")
    _fails(conn, ins, {"i": other, "s": hn, "e": "1", "p": False})  # same (source, external_id)
    _fails(
        conn, "UPDATE item_sources SET is_primary = true WHERE source_id = :s", {"s": gh}
    )  # 2 primaries
    # NULL external_ids never conflict.
    third = _item(conn, "https://example.com/r")
    conn.execute(text(ins), {"i": other, "s": gh, "e": None, "p": False})
    conn.execute(text(ins), {"i": third, "s": gh, "e": None, "p": False})
    # Provenance is never deleted by accident.
    _fails(conn, "DELETE FROM items WHERE id = :i", {"i": item})
    _fails(conn, "DELETE FROM sources WHERE id = :s", {"s": hn})


def test_run_and_brief_checks(conn):
    _fails(conn, "INSERT INTO pipeline_runs (trigger) VALUES ('cron')")
    _fails(conn, "INSERT INTO pipeline_runs (trigger, fetched) VALUES ('cli', -1)")
    conn.execute(text("INSERT INTO pipeline_runs (trigger) VALUES ('cli')"))
    _fails(
        conn,
        "INSERT INTO trend_briefs (period_start, period_end, content_md) VALUES (now(), now() - interval '1 day', 'x')",
    )


def test_timestamps_are_timezone_aware(engine):
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'timestamp without time zone'"
            )
        ).all()
    assert rows == []
