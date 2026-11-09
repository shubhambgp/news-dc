import logging

from sqlalchemy import create_engine, text

from app.config import get_settings

log = logging.getLogger(__name__)

# create_engine does not connect; the first query does.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3},
)


def check_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # health must report, never raise
        log.warning("db check failed", extra={"error": type(exc).__name__})
        return False
