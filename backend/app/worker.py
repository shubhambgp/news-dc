"""Worker entrypoint: `python -m app.worker`.

Phase 0 only starts the scheduler process so the container lifecycle can be exercised.
Ingestion and pipeline jobs are registered in Phase 2/3.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_settings
from app.logging import setup_logging

log = logging.getLogger("app.worker")


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    scheduler = BlockingScheduler(timezone="UTC")
    log.info("worker started", extra={"jobs": len(scheduler.get_jobs())})
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("worker stopped")


if __name__ == "__main__":
    main()
