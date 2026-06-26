#!/usr/bin/env python3
"""Simple GUI for periodic screenshots."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from screenshot import ScreenshotScheduler, ScreenshotSettings, list_monitors


class ScreenshotApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Auto Screenshot")
        self.root.minsize(420, 480)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.scheduler: ScreenshotScheduler | None = None
        self.monitor_options: list[tuple[int, str]] = []

        self._build_ui()
        self._load_monitors()
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

        default_output = Path(__file__).resolve().parent / "screenshots"
        self.output_var = tk.StringVar(value=str(default_output))
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

        button_row = ttk.Frame(frame)
        button_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        button_row.columnconfigure((0, 1, 2), weight=1)

        self.start_button = ttk.Button(button_row, text="Start", command=self._start)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.stop_button = ttk.Button(button_row, text="Stop", command=self._stop)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=6)

        self.capture_button = ttk.Button(
            button_row, text="Capture now", command=self._capture_now
        )
        self.capture_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Label(frame, text="Log").grid(row=6, column=0, columnspan=2, sticky="w")
        log_frame = ttk.Frame(frame)
        log_frame.grid(row=7, column=0, columnspan=2, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        frame.rowconfigure(7, weight=1)

        self.log_text = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

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
            if labels:
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
        return 0

    def _read_settings(self) -> ScreenshotSettings | None:
        try:
            interval = float(self.interval_var.get())
        except ValueError:
            messagebox.showerror("Invalid interval", "Enter a valid number of minutes.")
            return None

        if interval <= 0:
            messagebox.showerror("Invalid interval", "Interval must be greater than 0.")
            return None

        output = self.output_var.get().strip()
        if not output:
            messagebox.showerror("Missing folder", "Choose a folder to save screenshots.")
            return None

        return ScreenshotSettings(
            interval_minutes=interval,
            output_dir=Path(output),
            quality=int(self.quality_var.get()),
            monitor_index=self._selected_monitor_index(),
        )

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

    def _start(self) -> None:
        if self.scheduler and self.scheduler.running:
            return

        settings = self._read_settings()
        if settings is None:
            return

        self.scheduler = ScreenshotScheduler(
            settings,
            on_capture=self._on_capture,
            on_error=self._on_error,
            on_status=self._on_status,
        )
        self.scheduler.start()
        self._set_running(True)
        self._log(f"Started: every {settings.interval_minutes:g} min -> {settings.output_dir}")

    def _stop(self) -> None:
        if self.scheduler:
            self.scheduler.stop()
        self._set_running(False)

    def _capture_now(self) -> None:
        settings = self._read_settings()
        if settings is None:
            return

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
        if self.scheduler:
            self.scheduler.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ScreenshotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
