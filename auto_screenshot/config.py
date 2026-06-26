"""Persisted application settings."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from screenshot import ScreenshotSettings

APP_NAME = "AutoScreenshot"


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_dir() -> Path:
    if sys.platform == "win32":
        pictures = Path(os.environ.get("USERPROFILE", Path.home())) / "Pictures"
        return pictures / APP_NAME
    return Path.home() / "Pictures" / APP_NAME


def config_path() -> Path:
    return app_data_dir() / "config.json"


@dataclass
class AppConfig:
    interval_minutes: float = 5.0
    output_dir: str = ""
    quality: int = 75
    monitor_index: int = 0
    monitor_label: str = "All monitors"
    autostart: bool = True
    running: bool = True

    def __post_init__(self) -> None:
        if not self.output_dir:
            self.output_dir = str(default_output_dir())

    def to_settings(self) -> ScreenshotSettings:
        return ScreenshotSettings(
            interval_minutes=self.interval_minutes,
            output_dir=Path(self.output_dir),
            quality=self.quality,
            monitor_index=self.monitor_index,
        )

    @classmethod
    def from_settings(
        cls,
        settings: ScreenshotSettings,
        monitor_label: str,
        *,
        autostart: bool,
        running: bool,
    ) -> AppConfig:
        return cls(
            interval_minutes=settings.interval_minutes,
            output_dir=str(settings.output_dir),
            quality=settings.quality,
            monitor_index=settings.monitor_index,
            monitor_label=monitor_label,
            autostart=autostart,
            running=running,
        )


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        return AppConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__dataclass_fields__})
    except (json.JSONDecodeError, OSError, TypeError):
        return AppConfig()


def save_config(config: AppConfig) -> None:
    path = config_path()
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
