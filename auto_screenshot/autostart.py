"""Windows login autostart via registry."""

from __future__ import annotations

import sys
from pathlib import Path

APP_REGISTRY_NAME = "AutoScreenshot"

if sys.platform == "win32":
    import winreg

    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def executable_path() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    return f'"{Path(sys.executable).resolve()}" "{Path(__file__).resolve().parent / "app.py"}"'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, APP_REGISTRY_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> None:
    if sys.platform != "win32":
        return

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, APP_REGISTRY_NAME, 0, winreg.REG_SZ, executable_path())


def disable() -> None:
    if sys.platform != "win32":
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_REGISTRY_NAME)
    except FileNotFoundError:
        pass
