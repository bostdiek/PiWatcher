"""CLI entry point for one-shot pending inference backfill."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .db import close_db, init_db
from .inference import backfill_pending_inference

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_ERROR = 2


logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for pending inference backfill."""

    parser = argparse.ArgumentParser(description="Backfill pending PiWatcher inference events")
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of pending events to attempt in one run (default: 25)",
    )
    return parser


async def run_async(limit: int) -> int:
    """Run pending inference backfill against the configured database."""

    await init_db()
    try:
        return await backfill_pending_inference(limit=limit)
    finally:
        await close_db()


def main() -> int:
    """Run the backfill CLI."""

    parser = create_parser()
    args = parser.parse_args()

    if args.limit < 1:
        parser.print_usage(sys.stderr)
        print("error: --limit must be >= 1", file=sys.stderr)
        return EXIT_ERROR

    try:
        processed = asyncio.run(run_async(args.limit))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logger.exception("Backfill failed")
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    print(f"Backfill processed {processed} event(s).")
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
