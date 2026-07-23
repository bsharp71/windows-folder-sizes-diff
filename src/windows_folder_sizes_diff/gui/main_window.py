"""CustomTkinter main window."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.config import AppSettings
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.gui.scan_controller import ScanController

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MainWindow(ctk.CTk):
    """Application window for configuring and running scans."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        session_factory: sessionmaker[Session] | None = None,
        lifecycle_service: ScanLifecycleService | None = None,
    ) -> None:
        super().__init__()
        self.title("Folder Growth Scanner")
        self.geometry("860x620")
        self.minsize(640, 480)
        self._settings = settings
        self._last_log_path: Path | None = None
        self._controller = ScanController(
            self,
            session_factory=session_factory,
            lifecycle_service=lifecycle_service,
            database_path=settings.database_path,
        )
        self._build_ui()

    def run(self) -> None:
        self.mainloop()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        settings_frame = ctk.CTkFrame(self)
        settings_frame.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(settings_frame, text="Directory:").grid(
            row=0, column=0, padx=(10, 4), pady=8, sticky="w"
        )
        self._dir_entry = ctk.CTkEntry(settings_frame)
        self._dir_entry.insert(0, str(self._settings.target_directory))
        self._dir_entry.grid(row=0, column=1, padx=4, pady=8, sticky="ew")
        ctk.CTkButton(settings_frame, text="Browse", width=70, command=self._browse).grid(
            row=0, column=2, padx=(0, 8), pady=8
        )

        ctk.CTkLabel(settings_frame, text="Threshold (MB):").grid(
            row=0, column=3, padx=(12, 4), pady=8
        )
        self._mb_entry = ctk.CTkEntry(settings_frame, width=80)
        self._mb_entry.insert(0, str(self._settings.growth_threshold_mb))
        self._mb_entry.grid(row=0, column=4, padx=4, pady=8)

        ctk.CTkLabel(settings_frame, text="Days:").grid(row=0, column=5, padx=(12, 4), pady=8)
        self._days_entry = ctk.CTkEntry(settings_frame, width=60)
        self._days_entry.insert(0, str(self._settings.history_days))
        self._days_entry.grid(row=0, column=6, padx=4, pady=8)

        self._start_btn = ctk.CTkButton(
            settings_frame,
            text="Start",
            width=80,
            command=self._controller.start_or_stop,
        )
        self._start_btn.grid(row=0, column=7, padx=(12, 4), pady=8)

        self._log_btn = ctk.CTkButton(
            settings_frame,
            text="Show Log",
            width=90,
            state="disabled",
            command=lambda: self._controller.show_log(self._last_log_path),
        )
        self._log_btn.grid(row=0, column=8, padx=(4, 10), pady=8)

        self._results = ctk.CTkTextbox(self, font=("Consolas", 12), wrap="none")
        self._results.grid(row=1, column=0, padx=12, pady=6, sticky="nsew")
        self._results.configure(state="disabled")

        self._status_var = ctk.StringVar(value="Ready.")
        ctk.CTkLabel(
            self,
            textvariable=self._status_var,
            anchor="w",
            font=("Consolas", 11),
        ).grid(row=2, column=0, padx=14, pady=(0, 8), sticky="ew")

    def _browse(self) -> None:
        from tkinter import filedialog

        path = filedialog.askdirectory(
            initialdir=self._dir_entry.get().strip() or "C:\\",
            title="Select folder",
        )
        if path:
            self._dir_entry.delete(0, "end")
            self._dir_entry.insert(0, path.replace("/", "\\"))

    def get_target_directory(self) -> str:
        return self._dir_entry.get()

    def get_threshold_mb(self) -> str:
        return self._mb_entry.get()

    def get_history_days(self) -> str:
        return self._days_entry.get()

    def clear_results(self) -> None:
        self._results.configure(state="normal")
        self._results.delete("1.0", "end")
        self._results.configure(state="disabled")

    def append_result(self, folder: Path, megabytes: float, history_days: int) -> None:
        self._results.configure(state="normal")
        self._results.insert(
            "end",
            f"⚠  {folder}\n    → {megabytes} MB in last {history_days} day(s)\n\n",
        )
        self._results.see("end")
        self._results.configure(state="disabled")

    def set_status(self, message: str) -> None:
        self._status_var.set(message)

    def set_running(self, running: bool) -> None:
        self._start_btn.configure(text="Stop" if running else "Start")

    def set_log_path(self, path: Path | None) -> None:
        self._last_log_path = path
        self._log_btn.configure(state="normal" if path is not None else "disabled")

    def schedule_after(self, milliseconds: int, callback) -> None:
        self.after(milliseconds, callback)
