"""Command line interface: stock-scout run | init-db."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from .config import Settings


def _auto_slot() -> str:
    return "premarket" if datetime.now(timezone.utc).hour < 16 else "postclose"


def _make_repo(settings: Settings, dry_run: bool):
    if dry_run:
        from .db.repo import FakeRepo
        return FakeRepo()
    from .db.repo import Repo
    settings.require("database_url")
    return Repo(settings.database_url)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(prog="stock-scout")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the daily pipeline")
    run_p.add_argument("--dry-run", action="store_true",
                       help="fixture data, in-memory DB, no network, digest to stdout")
    run_p.add_argument("--slot", choices=["auto", "premarket", "postclose"], default="auto")

    sub.add_parser("init-db", help="apply schema.sql to the configured database")

    args = parser.parse_args(argv)
    settings = Settings.load()

    if args.command == "init-db":
        repo = _make_repo(settings, dry_run=False)
        repo.init_db()
        print("schema applied")
        return 0

    if args.command == "run":
        from .pipeline import run_pipeline
        slot = _auto_slot() if args.slot == "auto" else args.slot
        repo = _make_repo(settings, args.dry_run)
        try:
            stats = run_pipeline(settings, repo, dry_run=args.dry_run, slot=slot)
        finally:
            repo.close()
        print(f"run complete: {stats}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
