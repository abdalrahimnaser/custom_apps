#!/usr/bin/env python3
"""Monitor JETT VIP and KHB normal booking sites for available tickets."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

JETT_RESERVATIONS_URL = "https://jett.com.jo/ar/reservations"
JETT_BOOK_URL = "https://www.jett.com.jo/ar/book?from=16&to=41"
KHB_BOOKING_URL = "https://jett-khb.com.jo/booking"

DEFAULT_START = date(2026, 7, 11)
DEFAULT_END = date(2026, 7, 18)
DEFAULT_INTERVAL_SECONDS = 20

PROJECT_DIR = Path(__file__).resolve().parent
KHB_SESSION_FILE = PROJECT_DIR / "khb_session.json"
BRAVE_EXECUTABLE = Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
BRAVE_PROFILE_DIR = PROJECT_DIR / ".brave_profile"
KHB_CDP_URL = "http://127.0.0.1:9222"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class TicketFinding:
    provider: str
    service: str
    travel_date: str
    details: str
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Continuously check JETT VIP and KHB normal booking sites "
            "for available King Hussein Bridge tickets."
        )
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START.isoformat(),
        help="First travel date to check (YYYY-MM-DD). Default: 2026-07-11",
    )
    parser.add_argument(
        "--end",
        default=DEFAULT_END.isoformat(),
        help="Last travel date to check (YYYY-MM-DD). Default: 2026-07-25",
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
    parser.add_argument(
        "--no-khb",
        action="store_true",
        help="Skip the KHB normal booking site (Playwright).",
    )
    parser.add_argument(
        "--no-jett",
        action="store_true",
        help="Skip the JETT VIP booking site.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help=(
            "Show a separate automation Brave window for KHB checks. "
            "This is NOT your normal Brave window."
        ),
    )
    parser.add_argument(
        "--khb-use-brave",
        action="store_true",
        help=(
            "Run KHB checks in your real Brave window (visible). "
            "Brave must be open with remote debugging, or the script will open it."
        ),
    )
    parser.add_argument(
        "--setup-khb",
        action="store_true",
        help=(
            "Open KHB in your real Brave browser, let you pass Cloudflare, "
            "then save a session for automated checks."
        ),
    )
    parser.add_argument(
        "--browser",
        choices=("brave", "chrome", "chromium"),
        default="brave",
        help="Browser to use for automated KHB checks. Default: brave",
    )
    return parser.parse_args()


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError(f"end date {end} is before start date {start}")
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(text.split())


def parse_jett_trips(html: str) -> list[dict[str, str]]:
    trips: list[dict[str, str]] = []
    for table_id in ("tab-0", "tab-1"):
        match = re.search(
            rf'<table class="table" id="{table_id}">.*?<tbody>(.*?)</tbody>',
            html,
            re.S,
        )
        if not match:
            continue
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", match.group(1), re.S):
            cells = [
                strip_html(cell)
                for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            # Real trip rows have 5 cells; promo/ad rows are single-cell inserts.
            if len(cells) < 5:
                continue
            seats = cells[3]
            if not seats.isdigit() or int(seats) <= 0:
                continue
            trips.append(
                {
                    "table": table_id,
                    "time": cells[0],
                    "pickup": cells[1],
                    "price": cells[2],
                    "seats": seats,
                }
            )
    return trips


def check_jett_vip(session: requests.Session, travel_date: date) -> list[TicketFinding]:
    params = {
        "source": "16",
        "destination": "41",
        "track_id": "350",
        "from_date": travel_date.strftime("%d-%m-%Y"),
        "trip_path": "oneway",
        "adults_count": "1",
        "childs_count": "0",
        "disabled_count": "0",
    }
    response = session.get(
        JETT_RESERVATIONS_URL,
        params=params,
        timeout=45,
    )
    response.raise_for_status()
    trips = parse_jett_trips(response.text)
    findings: list[TicketFinding] = []
    for trip in trips:
        details = (
            f"{trip['time']} | pickup: {trip['pickup']} | "
            f"price: {trip['price']} | seats: {trip['seats']}"
        )
        findings.append(
            TicketFinding(
                provider="JETT",
                service="VIP (Service B)",
                travel_date=travel_date.isoformat(),
                details=details,
                url=JETT_BOOK_URL,
            )
        )
    return findings


def launch_khb_context(playwright, *, headed: bool, browser: str):
    """Launch a browser context for KHB checks."""
    launch_kwargs = {
        "headless": not headed,
        "locale": "ar-JO",
        "user_agent": USER_AGENT,
    }

    if browser == "brave" and BRAVE_EXECUTABLE.exists():
        BRAVE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        return playwright.chromium.launch_persistent_context(
            str(BRAVE_PROFILE_DIR),
            executable_path=str(BRAVE_EXECUTABLE),
            **launch_kwargs,
        )

    if browser == "chrome":
        try:
            return playwright.chromium.launch_persistent_context(
                str(BRAVE_PROFILE_DIR),
                channel="chrome",
                **launch_kwargs,
            )
        except Exception:
            pass

    return playwright.chromium.launch_persistent_context(
        str(BRAVE_PROFILE_DIR),
        **launch_kwargs,
    )


def quit_brave() -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application "Brave Browser" to quit'],
        check=False,
    )


def start_brave_with_debugging(url: str) -> None:
    if not BRAVE_EXECUTABLE.exists():
        raise FileNotFoundError(
            f"Brave not found at {BRAVE_EXECUTABLE}. "
            "Install Brave or use `python checker.py --no-khb`."
        )
    subprocess.Popen(
        [str(BRAVE_EXECUTABLE), "--remote-debugging-port=9222", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def find_khb_page(browser):
    for context in browser.contexts:
        for page in context.pages:
            if "jett-khb.com.jo" in page.url:
                return context, page
    if browser.contexts:
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        return context, page
    return None, None


def save_khb_session(context) -> None:
    context.storage_state(path=str(KHB_SESSION_FILE))


KHB_FETCH_SLOTS_JS = """
async (dates) => {
    const typeIds = ["0", "1"];
    const results = [];
    for (const travelDate of dates) {
        for (const typeId of typeIds) {
            try {
                const response = await fetch("/api/booking/time-schedule", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    body: JSON.stringify({
                        BookingTypeID: typeId,
                        BookingDate: travelDate,
                    }),
                });
                const payload = await response.json();
                if (payload.Status !== "Success" || !Array.isArray(payload.Data)) {
                    continue;
                }
                for (const slot of payload.Data) {
                    if ((slot.Available ?? 0) > 0) {
                        results.push({
                            travelDate,
                            typeId,
                            fromTime: slot.FromTime,
                            toTime: slot.ToTime,
                            available: slot.Available,
                            travelId: slot.TravelID,
                        });
                    }
                }
            } catch (error) {
                // Ignore per-date API failures and keep scanning.
            }
        }
    }
    return results;
}
"""


def slots_to_findings(slots: list[dict]) -> list[TicketFinding]:
    booking_type_names = {"0": "Regular", "1": "Tourist"}
    findings: list[TicketFinding] = []
    for slot in slots:
        service = booking_type_names.get(slot["typeId"], slot["typeId"])
        details = (
            f"{slot['fromTime']}-{slot['toTime']} | "
            f"type: {service} | seats: {slot['available']}"
        )
        findings.append(
            TicketFinding(
                provider="KHB",
                service=f"Normal ({service})",
                travel_date=slot["travelDate"],
                details=details,
                url=KHB_BOOKING_URL,
            )
        )
    return findings


def connect_brave_cdp(playwright, *, verbose: bool) -> tuple:
    try:
        browser = playwright.chromium.connect_over_cdp(KHB_CDP_URL)
        if verbose:
            print("  KHB: connected to your Brave browser")
        return browser
    except Exception:
        if verbose:
            print("  KHB: opening Brave with the booking page...")
        start_brave_with_debugging(KHB_BOOKING_URL)
        time.sleep(4)
        browser = playwright.chromium.connect_over_cdp(KHB_CDP_URL)
        if verbose:
            print("  KHB: connected to Brave")
        return browser


def wait_for_khb_booking_page(page, *, timeout_seconds: int = 120) -> None:
    marker = "احجز رحلتك"
    for _ in range(timeout_seconds // 2):
        if marker in page.content():
            return
        page.wait_for_timeout(2_000)
    raise TimeoutError(
        "KHB booking page did not load. Cloudflare may be blocking automation. "
        f"Run `python checker.py --setup-khb` once, then retry."
    )


def setup_khb_session() -> None:
    if not BRAVE_EXECUTABLE.exists():
        raise SystemExit(
            f"Brave was not found at:\n  {BRAVE_EXECUTABLE}\n\n"
            "Install Brave, or monitor VIP only with:\n"
            "  python checker.py --no-khb"
        )

    print("Setting up KHB using your real Brave browser.")
    print()
    print("Playwright-controlled browsers get stuck in Cloudflare loops.")
    print("This opens Brave normally, lets you pass the check once, then saves")
    print("the session for later automated scans.")
    print()
    print("Closing any open Brave windows...")
    quit_brave()
    time.sleep(2)
    print("Opening Brave...")
    start_brave_with_debugging(KHB_BOOKING_URL)
    print()
    print("In Brave:")
    print("  1. Pass the Cloudflare check if it appears.")
    print("  2. Wait until you see the booking page (احجز رحلتك).")
    print("  3. Come back here and press Enter.")
    print()
    input("Press Enter after the booking page has fully loaded... ")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(KHB_CDP_URL)
        except Exception as error:
            raise SystemExit(
                "Could not connect to Brave.\n"
                "Make sure Brave is still open, then run setup again.\n"
                f"Details: {error}"
            ) from error

        context, page = find_khb_page(browser)
        if context is None or page is None:
            raise SystemExit("Could not find a Brave tab to save the session from.")

        if "احجز رحلتك" not in page.content():
            raise SystemExit(
                "Booking page not detected yet.\n"
                "If Cloudflare is still looping in Brave, wait a bit and run:\n"
                "  python checker.py --setup-khb"
            )

        save_khb_session(context)

    print(f"Saved KHB session to {KHB_SESSION_FILE}")
    print("You can close Brave now, or leave it open.")


def check_khb_via_brave(
    dates: list[date],
    *,
    verbose: bool,
) -> list[TicketFinding]:
    iso_dates = [d.isoformat() for d in dates]
    if verbose:
        print("  KHB: using your real Brave window (you should see it)")
        print(f"  KHB: checking {len(iso_dates)} date(s) via the site API...")

    with sync_playwright() as playwright:
        browser = connect_brave_cdp(playwright, verbose=verbose)
        context, page = find_khb_page(browser)
        if context is None or page is None:
            raise RuntimeError("Could not find a Brave tab for KHB checks.")

        if "احجز رحلتك" not in page.content():
            if verbose:
                print("  KHB: loading booking page in Brave...")
            page.goto(KHB_BOOKING_URL, wait_until="domcontentloaded", timeout=120_000)
            wait_for_khb_booking_page(page)

        if verbose:
            print("  KHB: querying availability (no page clicks, API calls only)...")
        slots = page.evaluate(KHB_FETCH_SLOTS_JS, iso_dates)
        save_khb_session(context)
        if verbose:
            print(f"  KHB: finished ({len(slots)} available slot(s) found)")

    return slots_to_findings(slots)


def check_khb_normal(
    dates: list[date],
    *,
    headed: bool,
    browser: str,
    verbose: bool,
) -> list[TicketFinding]:
    iso_dates = [d.isoformat() for d in dates]
    if verbose:
        mode = "visible automation window" if headed else "hidden background browser"
        print(f"  KHB: using a separate {mode} (not your normal Brave)")
        print(f"  KHB: profile at {BRAVE_PROFILE_DIR}")
        print(f"  KHB: checking {len(iso_dates)} date(s)...")

    with sync_playwright() as playwright:
        context = launch_khb_context(playwright, headed=headed, browser=browser)
        if KHB_SESSION_FILE.exists():
            # Re-apply cookies from the real Brave setup session.
            state = json.loads(KHB_SESSION_FILE.read_text())
            context.add_cookies(state.get("cookies", []))

        page = context.pages[0] if context.pages else context.new_page()
        if verbose:
            print("  KHB: loading booking page in background browser...")
        page.goto(KHB_BOOKING_URL, wait_until="domcontentloaded", timeout=120_000)
        wait_for_khb_booking_page(page)
        save_khb_session(context)

        if verbose:
            print("  KHB: querying availability via API...")
        slots = page.evaluate(KHB_FETCH_SLOTS_JS, iso_dates)
        context.close()
        if verbose:
            print(f"  KHB: finished ({len(slots)} available slot(s) found)")

    return slots_to_findings(slots)


def check_khb(
    dates: list[date],
    *,
    headed: bool,
    browser: str,
    use_open_brave: bool,
    verbose: bool,
) -> list[TicketFinding]:
    if use_open_brave:
        return check_khb_via_brave(dates, verbose=verbose)
    return check_khb_normal(
        dates,
        headed=headed,
        browser=browser,
        verbose=verbose,
    )


def notify_mac(title: str, message: str) -> None:
    safe_title = title.replace('"', '\\"')
    safe_message = message.replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{safe_message}" with title "{safe_title}" sound name "Glass"',
        ],
        check=False,
    )


def notify_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=20,
    ).raise_for_status()


def notify(findings: list[TicketFinding]) -> None:
    lines = [
        (
            f"[{finding.provider} {finding.service}] {finding.travel_date}\n"
            f"  {finding.details}\n"
            f"  {finding.url}"
        )
        for finding in findings
    ]
    if not lines:
        return

    print(f"\n{'=' * 72}")
    print(f"TICKETS FOUND ({len(lines)})")
    print("\n\n".join(lines))
    print(f"{'=' * 72}\n")
    sys.stdout.write("\a")
    sys.stdout.flush()

    summary = (
        f"{len(findings)} slot(s): "
        + ", ".join(f"{f.provider} {f.travel_date}" for f in findings[:3])
    )
    if len(findings) > 3:
        summary += f", +{len(findings) - 3} more"
    notify_mac("Border tickets available", summary[:180])
    notify_telegram("\n\n".join(lines))


def run_scan(
    dates: list[date],
    *,
    skip_jett: bool,
    skip_khb: bool,
    headed: bool,
    browser: str,
    use_open_brave: bool,
) -> list[TicketFinding]:
    findings: list[TicketFinding] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    if not skip_jett:
        print(f"Checking JETT VIP for {len(dates)} date(s)...")
        for travel_date in dates:
            try:
                day_findings = check_jett_vip(session, travel_date)
                if day_findings:
                    print(
                        f"  {travel_date.isoformat()}: "
                        f"{len(day_findings)} trip(s) available"
                    )
                findings.extend(day_findings)
            except requests.RequestException as error:
                print(f"  {travel_date.isoformat()}: JETT error - {error}")

    if not skip_khb:
        print(f"Checking KHB normal for {len(dates)} date(s)...")
        try:
            khb_findings = check_khb(
                dates,
                headed=headed,
                browser=browser,
                use_open_brave=use_open_brave,
                verbose=True,
            )
            if khb_findings:
                grouped: dict[str, int] = {}
                for finding in khb_findings:
                    grouped[finding.travel_date] = grouped.get(finding.travel_date, 0) + 1
                for travel_date, count in sorted(grouped.items()):
                    print(f"  {travel_date}: {count} slot(s) available")
            findings.extend(khb_findings)
        except Exception as error:  # noqa: BLE001 - surface Playwright failures clearly
            print(f"  KHB error - {error}")

    return findings


def main() -> int:
    args = parse_args()
    if args.setup_khb:
        setup_khb_session()
        return 0

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    dates = date_range(start, end)

    print(
        f"Monitoring {start.isoformat()} to {end.isoformat()} "
        f"every {args.interval}s"
    )
    print(f"JETT VIP: {'off' if args.no_jett else 'on'}")
    print(f"KHB normal: {'off' if args.no_khb else 'on'}")
    if not args.no_khb:
        print(f"KHB browser: {args.browser}")
        if args.khb_use_brave:
            print("KHB mode: your real Brave window (--khb-use-brave)")
        else:
            print(
                "KHB mode: hidden background browser "
                "(use --khb-use-brave to watch checks in Brave)"
            )
    if not args.no_khb:
        if KHB_SESSION_FILE.exists():
            print(f"KHB session: {KHB_SESSION_FILE}")
        else:
            print(
                "KHB session: not set (run `python checker.py --setup-khb` if checks fail)"
            )

    while True:
        started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{started}] Starting scan...")
        findings = run_scan(
            dates,
            skip_jett=args.no_jett,
            skip_khb=args.no_khb,
            headed=args.headed,
            browser=args.browser,
            use_open_brave=args.khb_use_brave,
        )

        if findings:
            notify(findings)
        else:
            print("No tickets found this scan.")

        if args.once:
            break

        print(f"Sleeping {args.interval}s...")
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
