#!/usr/bin/env python3
"""Settings window for Auto Screenshot."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from config import AppConfig, load_config, save_config
from screenshot import ScreenshotScheduler, ScreenshotSettings, list_monitors

SaveCallback = Callable[[AppConfig], None]


class ScreenshotApp:
    def __init__(
        self,
        root: tk.Tk,
        *,
        tray_mode: bool = False,
        on_save: SaveCallback | None = None,
        on_hide: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.tray_mode = tray_mode
        self.on_save = on_save
        self.on_hide = on_hide
        self.root.title("Auto Screenshot")
        self.root.minsize(420, 520)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.scheduler: ScreenshotScheduler | None = None
        self.monitor_options: list[tuple[int, str]] = []
        self.config = load_config()

        self._build_ui()
        self._load_monitors()
        self._apply_config(self.config)
        self._set_running(False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Interval (minutes)").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.interval_var = tk.StringVar(value="5")
        self.interval_spinbox = ttk.Spinbox(
            frame,
            from_=0.5,
            to=1440,
            increment=0.5,
            textvariable=self.interval_var,
            width=10,
        )
        self.interval_spinbox.grid(row=0, column=1, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="Save to").grid(row=1, column=0, sticky="w", pady=(0, 8))
        output_row = ttk.Frame(frame)
        output_row.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        output_row.columnconfigure(0, weight=1)

        self.output_var = tk.StringVar()
        self.output_entry = ttk.Entry(output_row, textvariable=self.output_var)
        self.output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.browse_button = ttk.Button(
            output_row, text="Browse...", command=self._browse_output
        )
        self.browse_button.grid(row=0, column=1)

        ttk.Label(frame, text="JPEG quality").grid(row=2, column=0, sticky="w", pady=(0, 8))
        quality_row = ttk.Frame(frame)
        quality_row.grid(row=2, column=1, sticky="ew", pady=(0, 8))
        quality_row.columnconfigure(0, weight=1)

        self.quality_var = tk.IntVar(value=75)
        self.quality_scale = ttk.Scale(
            quality_row,
            from_=1,
            to=100,
            orient="horizontal",
            variable=self.quality_var,
            command=self._update_quality_label,
        )
        self.quality_scale.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.quality_label = ttk.Label(quality_row, text="75")
        self.quality_label.grid(row=0, column=1)

        ttk.Label(frame, text="Monitor").grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(
            frame,
            textvariable=self.monitor_var,
            state="readonly",
        )
        self.monitor_combo.grid(row=3, column=1, sticky="ew", pady=(0, 8))

        self.autostart_var = tk.BooleanVar(value=True)
        self.autostart_check = ttk.Checkbutton(
            frame,
            text="Run at Windows login",
            variable=self.autostart_var,
        )
        self.autostart_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 8))
        if not _is_windows():
            self.autostart_check.state(["disabled"])

        button_row = ttk.Frame(frame)
        button_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        button_row.columnconfigure((0, 1, 2), weight=1)

        self.start_button = ttk.Button(button_row, text="Start", command=self._start)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.stop_button = ttk.Button(button_row, text="Stop", command=self._stop)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=6)

        self.capture_button = ttk.Button(
            button_row, text="Capture now", command=self._capture_now
        )
        self.capture_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        save_row = ttk.Frame(frame)
        save_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        save_row.columnconfigure(0, weight=1)
        ttk.Button(save_row, text="Save settings", command=self._save_settings).grid(
            row=0, column=0, sticky="ew"
        )

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Label(frame, text="Log").grid(row=8, column=0, columnspan=2, sticky="w")
        log_frame = ttk.Frame(frame)
        log_frame.grid(row=9, column=0, columnspan=2, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        frame.rowconfigure(9, weight=1)

        self.log_text = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.interval_var.set(str(config.interval_minutes))
        self.output_var.set(config.output_dir)
        self.quality_var.set(config.quality)
        self.autostart_var.set(config.autostart)
        self._update_quality_label()
        if config.monitor_label:
            self.monitor_var.set(config.monitor_label)

    def _update_quality_label(self, _value: str = "") -> None:
        self.quality_label.configure(text=str(self.quality_var.get()))

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_var.get() or ".")
        if path:
            self.output_var.set(path)

    def _load_monitors(self) -> None:
        try:
            self.monitor_options = list_monitors()
            labels = [label for _, label in self.monitor_options]
            self.monitor_combo["values"] = labels
            if labels and not self.monitor_var.get():
                self.monitor_var.set(labels[0])
        except Exception as exc:
            self._log(f"Could not list monitors: {exc}")
            self.monitor_combo["values"] = ["All monitors"]
            self.monitor_var.set("All monitors")
            self.monitor_options = [(0, "All monitors")]

    def _selected_monitor_index(self) -> int:
        label = self.monitor_var.get()
        for index, option_label in self.monitor_options:
            if option_label == label:
                return index
        return self.config.monitor_index

    def _read_settings(self, *, show_errors: bool = True) -> ScreenshotSettings | None:
        try:
            interval = float(self.interval_var.get())
        except ValueError:
            if show_errors:
                messagebox.showerror("Invalid interval", "Enter a valid number of minutes.")
            return None

        if interval <= 0:
            if show_errors:
                messagebox.showerror("Invalid interval", "Interval must be greater than 0.")
            return None

        output = self.output_var.get().strip()
        if not output:
            if show_errors:
                messagebox.showerror("Missing folder", "Choose a folder to save screenshots.")
            return None

        return ScreenshotSettings(
            interval_minutes=interval,
            output_dir=Path(output),
            quality=int(self.quality_var.get()),
            monitor_index=self._selected_monitor_index(),
        )

    def _build_config(self, *, running: bool | None = None) -> AppConfig | None:
        settings = self._read_settings()
        if settings is None:
            return None

        if running is not None:
            running_value = running
        elif self.scheduler:
            running_value = self.scheduler.running
        else:
            running_value = self.config.running

        return AppConfig.from_settings(
            settings,
            self.monitor_var.get(),
            autostart=self.autostart_var.get(),
            running=running_value,
        )

    def _save_settings(self) -> bool:
        config = self._build_config()
        if config is None:
            return False

        save_config(config)
        self.config = config
        if self.on_save:
            self.on_save(config)
        self._log("Settings saved")
        self.status_var.set("Settings saved")
        return True

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_window(self) -> None:
        self.root.withdraw()

    @property
    def is_running(self) -> bool:
        return self.scheduler is not None and self.scheduler.running

    def start_scheduler(self) -> bool:
        if self.is_running:
            return True

        settings = self._read_settings(show_errors=False)
        if settings is None:
            settings = self.config.to_settings()

        self.scheduler = ScreenshotScheduler(
            settings,
            on_capture=self._on_capture,
            on_error=self._on_error,
            on_status=self._on_status,
        )
        self.scheduler.start()
        self._set_running(True)
        self._log(f"Started: every {settings.interval_minutes:g} min -> {settings.output_dir}")
        return True

    def stop_scheduler(self) -> None:
        if self.scheduler:
            self.scheduler.stop()
        self._set_running(False)
        self._persist_running(False)

    def capture_now(self) -> None:
        settings = self._read_settings(show_errors=False)
        if settings is None:
            settings = self.config.to_settings()

        if self.scheduler is None or not self.scheduler.running:
            self.scheduler = ScreenshotScheduler(
                settings,
                on_capture=self._on_capture,
                on_error=self._on_error,
                on_status=self._on_status,
            )
        else:
            self.scheduler.settings = settings

        self.scheduler.capture_once()

    def _set_running(self, running: bool) -> None:
        start_state = "disabled" if running else "normal"
        self.start_button.configure(state=start_state)
        self.stop_button.configure(state="normal" if running else "disabled")
        self.capture_button.configure(state=start_state)
        self.monitor_combo.configure(state="disabled" if running else "readonly")

        config_state = "disabled" if running else "normal"
        self.interval_spinbox.configure(state=config_state)
        self.output_entry.configure(state=config_state)
        self.browse_button.configure(state=config_state)
        self.quality_scale.configure(state=config_state)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _ui(self, callback) -> None:
        self.root.after(0, callback)

    def _persist_running(self, running: bool) -> None:
        self.config.running = running
        save_config(self.config)

    def _start(self) -> None:
        if self.is_running:
            return
        if not self._save_settings():
            return
        self.start_scheduler()
        self._persist_running(True)

    def _stop(self) -> None:
        self.stop_scheduler()

    def _capture_now(self) -> None:
        self.capture_now()
        self._log("Manual capture requested")

    def _on_capture(self, path: Path, size_kb: float) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"[{timestamp}] Saved {path.name} ({size_kb:.0f} KB)"
        self._ui(lambda: (self._log(message), self.status_var.set("Last capture successful")))

    def _on_error(self, message: str) -> None:
        self._ui(
            lambda: (
                self._log(f"Error: {message}"),
                self.status_var.set("Capture failed"),
            )
        )

    def _on_status(self, message: str) -> None:
        self._ui(lambda: self.status_var.set(message))

    def _on_close(self) -> None:
        if self.tray_mode:
            self.hide_window()
            if self.on_hide:
                self.on_hide()
            return

        if self.scheduler:
            self.scheduler.stop()
        self.root.destroy()


def _is_windows() -> bool:
    import sys

    return sys.platform == "win32"


def main() -> None:
    root = tk.Tk()
    ScreenshotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
