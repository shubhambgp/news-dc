import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.config import get_settings
from app.ingest import common
from app.seed import seed

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Tests never hit real DNS: every host resolves to a public address unless a test says so."""
    monkeypatch.setattr(common, "_resolve", lambda host, port: ["93.184.216.34"])


def _alembic() -> Config:
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL or "")
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="module")
def engine():
    """A freshly migrated and seeded THROWAWAY database (its public schema is dropped)."""
    eng = create_engine(TEST_DATABASE_URL or "")
    with eng.begin() as conn:  # truly empty database
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(_alembic(), "head")
    seed(eng, get_settings().config_dir)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Tests never make a paid call, even with a real ANTHROPIC_API_KEY in .env."""

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to call the real Anthropic API")

    monkeypatch.setattr("anthropic.resources.messages.Messages.create", refuse)
