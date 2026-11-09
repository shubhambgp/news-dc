"""CLI: `python -m app.pipeline --limit 100` (process new items) or `--reprocess-outdated`."""

import argparse
import json
import sys
from dataclasses import asdict

from app.config import get_settings
from app.logging import setup_logging
from app.pipeline.graph import reprocess_outdated, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.pipeline", description=__doc__)
    parser.add_argument("--limit", type=int, help="max new items to examine (default: all)")
    parser.add_argument(
        "--max-llm-items", type=int, help="max LLM calls this run (default MAX_LLM_ITEMS_PER_RUN)"
    )
    parser.add_argument(
        "--reprocess-outdated",
        action="store_true",
        help="reset items classified with an older prompt version to `new`, then exit",
    )
    args = parser.parse_args(argv)
    for name in ("limit", "max_llm_items"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")

    setup_logging(get_settings().log_level)
    if args.reprocess_outdated:
        print(json.dumps({"reset_to_new": reprocess_outdated()}))
        return 0
    result = run_pipeline(limit=args.limit, max_llm_items=args.max_llm_items, trigger="cli")
    print(json.dumps(asdict(result), indent=2))
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
