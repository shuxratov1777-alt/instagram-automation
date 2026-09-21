from __future__ import annotations

import argparse
from pathlib import Path

from .database import init_db
from .pipeline import ingest, process


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    init_db()
    job_id, created = ingest(args.video, dry_run=not args.live)
    print({"job_id": job_id, "created": created, "state": process(job_id) if created else "duplicate"})


if __name__ == "__main__":
    main()

