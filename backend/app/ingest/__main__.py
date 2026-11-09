"""CLI: `python -m app.ingest --source hn --since-days 365` or `python -m app.ingest --all`."""

import argparse
import json
import sys
from dataclasses import asdict

from app import db
from app.config import get_settings
from app.ingest.runner import ingest_all, ingest_source
from app.logging import setup_logging
from app.seed import seed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest", description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--source", help="source key from config/sources.yaml")
    target.add_argument("--all", action="store_true", help="every enabled source")
    parser.add_argument(
        "--since-days",
        type=int,
        help="look back this many days (default: since last success, else the backfill window)",
    )
    args = parser.parse_args(argv)
    if args.since_days is not None and not 0 < args.since_days <= 3650:
        parser.error("--since-days must be between 1 and 3650")

    settings = get_settings()
    setup_logging(settings.log_level)
    seed(db.engine, settings.config_dir)  # make sure sources.yaml changes are in the DB
    if args.all:
        results = ingest_all(since_days=args.since_days, trigger="cli")
    else:
        results = [ingest_source(args.source, since_days=args.since_days, trigger="cli")]
    print(json.dumps([asdict(r) for r in results], indent=2))
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
