#!/usr/bin/env python3
"""Tray-based background app for Auto Screenshot."""

from __future__ import annotations

import sys
import threading

import pystray
import tkinter as tk
from pystray import MenuItem as Item

import autostart
from assets import ensure_icon_file, tray_icon
from config import AppConfig, config_path, load_config, save_config
from gui import ScreenshotApp


class TrayApplication:
    def __init__(self) -> None:
        ensure_icon_file()
        self.config = load_config()
        self.root = tk.Tk()
        self.root.withdraw()

        self.gui = ScreenshotApp(
            self.root,
            tray_mode=True,
            on_save=self._on_config_saved,
            on_hide=self._refresh_tray_menu,
        )
        self.tray_icon: pystray.Icon | None = None
        self._tray_thread: threading.Thread | None = None

    def run(self) -> None:
        if config_path().exists():
            self._apply_autostart(self.config.autostart)
        self._start_tray()

        if self.config.running:
            self.gui.start_scheduler()
        elif not config_path().exists():
            self.gui.show_window()

        self.root.mainloop()

    def _start_tray(self) -> None:
        self.tray_icon = pystray.Icon(
            "AutoScreenshot",
            tray_icon(),
            "Auto Screenshot",
            menu=self._build_menu(),
        )
        self._tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _build_menu(self) -> pystray.Menu:
        running = self.gui.is_running
        return pystray.Menu(
            Item("Settings", self._show_settings, default=True),
            Item("Capture now", self._capture_now),
            Item(
                "Pause" if running else "Resume",
                self._toggle_running,
            ),
            pystray.Menu.SEPARATOR,
            Item(
                "Run at Windows login",
                self._toggle_autostart,
                checked=lambda _: autostart.is_enabled(),
                enabled=lambda _: sys.platform == "win32",
            ),
            pystray.Menu.SEPARATOR,
            Item("Quit", self._quit),
        )

    def _refresh_tray_menu(self) -> None:
        if self.tray_icon:
            self.tray_icon.menu = self._build_menu()

    def _run_on_ui(self, callback) -> None:
        self.root.after(0, callback)

    def _show_settings(self, _icon=None, _item=None) -> None:
        self._run_on_ui(self.gui.show_window)

    def _capture_now(self, _icon=None, _item=None) -> None:
        self._run_on_ui(self.gui.capture_now)

    def _toggle_running(self, _icon=None, _item=None) -> None:
        def toggle() -> None:
            if self.gui.is_running:
                self.gui.stop_scheduler()
            else:
                self.gui.start_scheduler()
                self.config.running = True
                save_config(self.config)
            self._refresh_tray_menu()

        self._run_on_ui(toggle)

    def _toggle_autostart(self, _icon=None, _item=None) -> None:
        enabled = not autostart.is_enabled()
        self._apply_autostart(enabled)
        self.gui.autostart_var.set(enabled)
        self.config.autostart = enabled
        save_config(self.config)
        self._refresh_tray_menu()

    def _apply_autostart(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return
        if enabled:
            autostart.enable()
        else:
            autostart.disable()

    def _on_config_saved(self, config: AppConfig) -> None:
        self.config = config
        self._apply_autostart(config.autostart)
        if self.gui.scheduler:
            self.gui.scheduler.settings = config.to_settings()
        self._refresh_tray_menu()

    def _quit(self, _icon=None, _item=None) -> None:
        def shutdown() -> None:
            self.gui.stop_scheduler()
            if self.tray_icon:
                self.tray_icon.stop()
            self.root.destroy()

        self._run_on_ui(shutdown)


def main() -> None:
    TrayApplication().run()


if __name__ == "__main__":
    main()
