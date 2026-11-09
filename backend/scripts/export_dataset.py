"""Write the committed sample dataset (PLAN Phase 8 step 4): data/sample/newsdc_sample.json and
.md, the newest processed items with the same fields as `GET /api/v1/export`.

    uv run python scripts/export_dataset.py [--limit 1000] [--out ../data/sample]

Exits 1 if fewer than 500 records were written (the required minimum).
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.common import Filters  # noqa: E402
from app.api.export import category_names, export_records, to_markdown  # noqa: E402
from app.db import SessionLocal  # noqa: E402

MIN_RECORDS = 500
REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--out", type=Path, default=REPO / "data" / "sample")
    args = p.parse_args(argv)

    with SessionLocal() as db:
        records = export_records(db, Filters(), args.limit)
        md = to_markdown(records, category_names(db), datetime.now(UTC))
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "newsdc_sample.json"
    json_path.write_text("[\n" + ",\n".join(r.model_dump_json() for r in records) + "\n]\n")
    (args.out / "newsdc_sample.md").write_text(md)
    print(f"wrote {len(records)} records to {json_path} and newsdc_sample.md")
    return 0 if len(records) >= MIN_RECORDS else 1


if __name__ == "__main__":
    sys.exit(main())
