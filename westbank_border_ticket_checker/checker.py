#!/usr/bin/env python3
"""CLI entry point for the JETT VIP border ticket checker."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime

from checker_service import (
    DEFAULT_END,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_START,
    date_range,
    notify_findings,
    run_scan,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Continuously check JETT VIP for available King Hussein Bridge tickets."
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START.isoformat(),
        help="First travel date to check (YYYY-MM-DD). Default: 2026-07-11",
    )
    parser.add_argument(
        "--end",
        default=DEFAULT_END.isoformat(),
        help="Last travel date to check (YYYY-MM-DD). Default: 2026-07-18",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Seconds between full scans. Default: 300 (5 minutes)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and exit.",
    )
    return parser.parse_args()


def notify_cli(findings) -> None:
    lines = notify_findings(findings)
    if not lines:
        return
    print(f"\n{'=' * 72}")
    print(f"TICKETS FOUND ({len(lines)})")
    print("\n\n".join(lines))
    print(f"{'=' * 72}\n")
    sys.stdout.write("\a")
    sys.stdout.flush()


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    dates = date_range(start, end)

    print(f"Monitoring JETT VIP {start.isoformat()} to {end.isoformat()} every {args.interval}s")

    while True:
        started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{started}] Starting scan...")
        findings = run_scan(
            dates,
            log=lambda msg: print(f"  {msg}" if not msg.startswith("  ") else msg),
        )

        if findings:
            notify_cli(findings)
        else:
            print("No tickets found this scan.")

        if args.once:
            break

        print(f"Sleeping {args.interval}s...")
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
