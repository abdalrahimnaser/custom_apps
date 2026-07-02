# Westbank Border Ticket Checker

Continuously checks both JETT booking sites for available King Hussein Bridge tickets.

## Setup

```bash
cd westbank_border_ticket_checker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run

Default: July 11–25, 2026, every 5 minutes.

```bash
python checker.py
```

Single scan:

```bash
python checker.py --once
```

Custom date range / interval:

```bash
python checker.py --start 2026-07-11 --end 2026-07-25 --interval 180
```

## KHB / Cloudflare / Brave

The normal booking site uses Cloudflare. Automated browsers get stuck in robot-check loops.

**Recommended setup** (uses your real Brave browser):

```bash
python checker.py --setup-khb
```

This will:
1. Quit Brave
2. Re-open Brave normally with the booking page
3. Let you pass Cloudflare in a real browser window
4. Save the session for later scans

Then run the monitor as usual:

```bash
python checker.py
```

Automated KHB checks default to Brave (`--browser brave`).

## Notifications

- macOS desktop notification (always, on macOS)
- Terminal bell + printed alert
- Optional Telegram: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

## Sites checked

| Site | URL | Service |
|------|-----|---------|
| JETT VIP | https://www.jett.com.jo/ar/book?from=16&to=41 | VIP / Service B |
| KHB normal | https://jett-khb.com.jo/booking | Regular + Tourist |

You are notified on **every scan** when tickets are found (no deduplication).

KHB login cookies are saved locally as `khb_session.json` next to `checker.py` after running `--setup-khb`.
