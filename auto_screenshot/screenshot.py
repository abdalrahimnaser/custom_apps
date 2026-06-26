#!/usr/bin/env python3
"""Periodically capture screenshots and save them as JPEG files."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import mss
from PIL import Image

CaptureCallback = Callable[[Path, float], None]
ErrorCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]


@dataclass
class ScreenshotSettings:
    interval_minutes: float = 5.0
    output_dir: Path = Path("screenshots")
    quality: int = 75
    monitor_index: int = 0


def list_monitors() -> list[tuple[int, str]]:
    with mss.MSS() as sct:
        monitors: list[tuple[int, str]] = []
        for index, monitor in enumerate(sct.monitors):
            if index == 0:
                label = "All monitors"
            else:
                label = f"Monitor {index} ({monitor['width']}x{monitor['height']})"
            monitors.append((index, label))
        return monitors


def capture_screenshot(monitor_index: int) -> Image.Image:
    with mss.MSS() as sct:
        monitor = sct.monitors[monitor_index]
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def save_screenshot(image: Image.Image, output_dir: Path, quality: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.jpg")
    path = output_dir / filename
    image.save(path, format="JPEG", quality=quality, optimize=True)
    return path


def take_screenshot(settings: ScreenshotSettings) -> tuple[Path, float]:
    image = capture_screenshot(settings.monitor_index)
    path = save_screenshot(image, settings.output_dir, settings.quality)
    size_kb = path.stat().st_size / 1024
    return path, size_kb


class ScreenshotScheduler:
    def __init__(
        self,
        settings: ScreenshotSettings,
        on_capture: CaptureCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_status: StatusCallback | None = None,
    ) -> None:
        self.settings = settings
        self.on_capture = on_capture
        self.on_error = on_error
        self.on_status = on_status
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def capture_once(self) -> None:
        threading.Thread(target=self._capture, daemon=True).start()

    def _emit_status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def _capture(self) -> None:
        try:
            path, size_kb = take_screenshot(self.settings)
            if self.on_capture:
                self.on_capture(path, size_kb)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))

    def _run_loop(self) -> None:
        interval_seconds = self.settings.interval_minutes * 60
        self._emit_status(
            f"Running every {self.settings.interval_minutes:g} minute(s)"
        )

        while not self._stop_event.is_set():
            self._capture()

            deadline = time.monotonic() + interval_seconds
            while not self._stop_event.is_set() and time.monotonic() < deadline:
                time.sleep(0.25)

        self._emit_status("Stopped")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Take screenshots every N minutes and save them locally."
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=5.0,
        help="Minutes between screenshots (default: 5)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("screenshots"),
        help="Directory to save screenshots (default: ./screenshots)",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=75,
        choices=range(1, 101),
        metavar="1-100",
        help="JPEG quality; lower = smaller files (default: 75)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=0,
        help="Monitor index to capture; 0 = all monitors combined (default: 0)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Take a single screenshot and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.interval <= 0:
        print("Interval must be greater than 0.", file=sys.stderr)
        return 1

    settings = ScreenshotSettings(
        interval_minutes=args.interval,
        output_dir=args.output,
        quality=args.quality,
        monitor_index=args.monitor,
    )

    def on_capture(path: Path, size_kb: float) -> None:
        print(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Saved {path.name} ({size_kb:.0f} KB)"
        )

    def on_error(message: str) -> None:
        print(f"Screenshot failed: {message}", file=sys.stderr)

    scheduler = ScreenshotScheduler(
        settings,
        on_capture=on_capture,
        on_error=on_error,
    )

    running = True

    def handle_stop(signum, frame):
        nonlocal running
        running = False
        scheduler.stop()
        print("\nStopping...")

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    print(f"Saving screenshots to: {settings.output_dir.resolve()}")
    print(f"Interval: {settings.interval_minutes:g} minute(s), JPEG quality: {settings.quality}")
    if not args.once:
        print("Press Ctrl+C to stop.\n")

    if args.once:
        try:
            path, size_kb = take_screenshot(settings)
            on_capture(path, size_kb)
        except Exception as exc:
            on_error(str(exc))
            return 1
        return 0

    scheduler.start()
    while running and scheduler.running:
        time.sleep(0.5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
