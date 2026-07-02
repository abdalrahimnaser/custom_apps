"""Core JETT VIP ticket-checking logic for the CLI and Flask web app."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import requests

JETT_RESERVATIONS_URL = "https://jett.com.jo/ar/reservations"
JETT_BOOK_URL = "https://www.jett.com.jo/ar/book?from=16&to=41"

DEFAULT_START = date(2026, 7, 11)
DEFAULT_END = date(2026, 7, 18)
DEFAULT_INTERVAL_SECONDS = 300

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_DIR / "web_config.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def is_cloud_environment() -> bool:
    return bool(os.environ.get("RENDER") or os.environ.get("CLOUD_DEPLOY"))


@dataclass(frozen=True)
class TicketFinding:
    provider: str
    service: str
    travel_date: str
    details: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class MonitorConfig:
    start_date: str = DEFAULT_START.isoformat()
    end_date: str = DEFAULT_END.isoformat()
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    notify_sound: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MonitorConfig:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def load_config() -> MonitorConfig:
    if not CONFIG_FILE.exists():
        return MonitorConfig()
    try:
        return MonitorConfig.from_dict(json.loads(CONFIG_FILE.read_text()))
    except (json.JSONDecodeError, TypeError):
        return MonitorConfig()


def save_config(config: MonitorConfig) -> None:
    CONFIG_FILE.write_text(json.dumps(config.to_dict(), indent=2))


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
    response = session.get(JETT_RESERVATIONS_URL, params=params, timeout=45)
    response.raise_for_status()
    trips = parse_jett_trips(response.text)
    findings: list[TicketFinding] = []
    for trip in trips:
        details = (
            f"{trip['time']} | نقطة الانطلاق: {trip['pickup']} | "
            f"السعر: {trip['price']} | المقاعد: {trip['seats']}"
        )
        findings.append(
            TicketFinding(
                provider="JETT",
                service="VIP (الخدمة B)",
                travel_date=travel_date.isoformat(),
                details=details,
                url=JETT_BOOK_URL,
            )
        )
    return findings


def notify_telegram(message: str, *, token: str | None = None, chat_id: str | None = None) -> None:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=20,
    ).raise_for_status()


def notify_findings(
    findings: list[TicketFinding],
    *,
    telegram_token: str = "",
    telegram_chat_id: str = "",
) -> list[str]:
    lines = [
        (
            f"[{finding.provider} {finding.service}] {finding.travel_date}\n"
            f"  {finding.details}\n"
            f"  {finding.url}"
        )
        for finding in findings
    ]
    if not lines:
        return []
    notify_telegram("\n\n".join(lines), token=telegram_token or None, chat_id=telegram_chat_id or None)
    return lines


def run_scan(
    dates: list[date],
    *,
    log: Callable[[str], None] | None = None,
) -> list[TicketFinding]:
    findings: list[TicketFinding] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    if log:
        log(f"جاري فحص JETT VIP لـ {len(dates)} تاريخ...")
    for travel_date in dates:
        try:
            day_findings = check_jett_vip(session, travel_date)
            if day_findings and log:
                log(f"  {travel_date.isoformat()}: {len(day_findings)} رحلة متاحة")
            findings.extend(day_findings)
        except requests.RequestException as error:
            if log:
                log(f"  {travel_date.isoformat()}: خطأ — {error}")

    return findings


@dataclass
class LogEntry:
    id: str
    timestamp: str
    level: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ScanResult:
    id: str
    started_at: str
    finished_at: str
    findings: list[dict[str, str]]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TicketMonitor:
    """Thread-safe monitor with live logs and scan history for the web UI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._scan_thread: threading.Thread | None = None
        self._config = load_config()
        self._monitoring = False
        self._scanning = False
        self._logs: list[LogEntry] = []
        self._findings_history: list[dict[str, Any]] = []
        self._scan_history: list[ScanResult] = []
        self._last_scan_at: str | None = None
        self._next_scan_at: str | None = None
        self._listeners: list[threading.Event] = []
        self._max_logs = 500
        self._max_history = 100

    def _emit(self) -> None:
        for event in self._listeners:
            event.set()

    def subscribe(self) -> threading.Event:
        event = threading.Event()
        with self._lock:
            self._listeners.append(event)
        return event

    def unsubscribe(self, event: threading.Event) -> None:
        with self._lock:
            if event in self._listeners:
                self._listeners.remove(event)

    def add_log(self, message: str, *, level: str = "info") -> None:
        entry = LogEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            level=level,
            message=message,
        )
        with self._lock:
            self._logs.append(entry)
            if len(self._logs) > self._max_logs:
                self._logs = self._logs[-self._max_logs :]
        self._emit()

    def get_config(self) -> MonitorConfig:
        with self._lock:
            return MonitorConfig.from_dict(self._config.to_dict())

    def update_config(self, updates: dict[str, Any]) -> MonitorConfig:
        with self._lock:
            current = self._config.to_dict()
            current.update(updates)
            self._config = MonitorConfig.from_dict(current)
            save_config(self._config)
            config = MonitorConfig.from_dict(self._config.to_dict())
        self.add_log("تم حفظ الإعدادات")
        return config

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "monitoring": self._monitoring,
                "scanning": self._scanning,
                "cloud_mode": is_cloud_environment(),
                "last_scan_at": self._last_scan_at,
                "next_scan_at": self._next_scan_at,
                "config": self._config.to_dict(),
                "recent_findings_count": len(self._findings_history),
            }

    def get_logs(self, since_id: str | None = None) -> list[dict[str, str]]:
        with self._lock:
            if since_id is None:
                return [entry.to_dict() for entry in self._logs[-100:]]
            found = False
            result: list[dict[str, str]] = []
            for entry in self._logs:
                if found:
                    result.append(entry.to_dict())
                elif entry.id == since_id:
                    found = True
            return result

    def get_findings(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._findings_history[-limit:]))

    def clear_findings(self) -> None:
        with self._lock:
            self._findings_history.clear()
        self.add_log("تم مسح قائمة التذاكر المتاحة")
        self._emit()

    def get_scan_history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [scan.to_dict() for scan in reversed(self._scan_history[-limit:])]

    def _record_scan(
        self,
        *,
        scan_id: str,
        started_at: str,
        findings: list[TicketFinding],
        error: str | None = None,
    ) -> None:
        finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        finding_dicts = [f.to_dict() for f in findings]
        scan = ScanResult(
            id=scan_id,
            started_at=started_at,
            finished_at=finished_at,
            findings=finding_dicts,
            error=error,
        )
        with self._lock:
            self._last_scan_at = finished_at
            self._scan_history.append(scan)
            if len(self._scan_history) > self._max_history:
                self._scan_history = self._scan_history[-self._max_history :]
            for finding in finding_dicts:
                self._findings_history.append(
                    {
                        "id": str(uuid.uuid4()),
                        "found_at": finished_at,
                        **finding,
                    }
                )
            if len(self._findings_history) > self._max_history:
                self._findings_history = self._findings_history[-self._max_history :]
        self._emit()

    def _perform_scan(self) -> list[TicketFinding]:
        config = self.get_config()
        start = date.fromisoformat(config.start_date)
        end = date.fromisoformat(config.end_date)
        dates = date_range(start, end)
        scan_id = str(uuid.uuid4())
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.add_log(f"بدء الفحص ({start.isoformat()} إلى {end.isoformat()})...")

        try:
            findings = run_scan(dates, log=lambda msg: self.add_log(msg))
            if findings:
                self.add_log(
                    f"تم العثور على {len(findings)} تذكرة متاحة!",
                    level="success",
                )
                notify_findings(
                    findings,
                    telegram_token=config.telegram_bot_token,
                    telegram_chat_id=config.telegram_chat_id,
                )
            else:
                self.add_log("لا توجد تذاكر متاحة في هذا الفحص.")
            self._record_scan(scan_id=scan_id, started_at=started_at, findings=findings)
            return findings
        except Exception as error:  # noqa: BLE001
            self.add_log(f"فشل الفحص: {error}", level="error")
            self._record_scan(
                scan_id=scan_id,
                started_at=started_at,
                findings=[],
                error=str(error),
            )
            return []

    def scan_once(self) -> None:
        with self._lock:
            if self._scanning:
                raise RuntimeError("يوجد فحص قيد التشغيل بالفعل.")
            self._scanning = True

        def worker() -> None:
            try:
                self._perform_scan()
            finally:
                with self._lock:
                    self._scanning = False
                self._emit()

        self._scan_thread = threading.Thread(target=worker, daemon=True)
        self._scan_thread.start()

    def start_monitoring(self) -> None:
        with self._lock:
            if self._monitoring:
                return
            self._monitoring = True
            self._stop_event.clear()

        config = self.get_config()
        self.add_log(
            f"بدأت المراقبة — فحص كل {config.interval_seconds} ثانية",
            level="success",
        )

        def loop() -> None:
            while not self._stop_event.is_set():
                self._perform_scan()
                if self._stop_event.is_set():
                    break
                config = self.get_config()
                interval = max(10, config.interval_seconds)
                next_at = datetime.now() + timedelta(seconds=interval)
                with self._lock:
                    self._next_scan_at = next_at.strftime("%Y-%m-%d %H:%M:%S")
                self._emit()
                if self._stop_event.wait(interval):
                    break
            with self._lock:
                self._monitoring = False
                self._next_scan_at = None
            self.add_log("توقفت المراقبة")
            self._emit()

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop_monitoring(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._monitoring = False
            self._next_scan_at = None
        self._emit()


monitor = TicketMonitor()
