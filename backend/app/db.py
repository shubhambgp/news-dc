import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

log = logging.getLogger(__name__)

# create_engine does not connect; the first query does.
# Bounded pool plus server-side timeouts so a stuck query or open transaction can't pin
# connections forever (PLAN §11.10).
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_timeout=10,
    connect_args={
        "connect_timeout": 3,
        # UTC sessions so every timestamp the API returns is serialized as UTC (§11.7).
        "options": "-c timezone=UTC -c statement_timeout=30000 "
        "-c idle_in_transaction_session_timeout=60000",
    },
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def check_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # health must report, never raise
        log.warning("db check failed", extra={"error": type(exc).__name__})
        return False
