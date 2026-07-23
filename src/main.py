import customtkinter as ctk
from scanner import FolderScanner, load_settings, save_settings

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Folder Growth Scanner")
        self.geometry("860x620")
        self.minsize(640, 480)
        self._scanner = None
        self._log_lines = []
        self._last_log_path = None
        self._settings = load_settings()
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Settings bar ---
        settings_frame = ctk.CTkFrame(self)
        settings_frame.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        settings_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(settings_frame, text="Directory:").grid(row=0, column=0, padx=(10, 4), pady=8, sticky="w")
        self._dir_entry = ctk.CTkEntry(settings_frame)
        self._dir_entry.insert(0, self._settings["TargetDirectory"])
        self._dir_entry.grid(row=0, column=1, padx=4, pady=8, sticky="ew")
        ctk.CTkButton(settings_frame, text="Browse", width=70, command=self._browse).grid(row=0, column=2, padx=(0, 8), pady=8)

        ctk.CTkLabel(settings_frame, text="Threshold (MB):").grid(row=0, column=3, padx=(12, 4), pady=8)
        self._mb_entry = ctk.CTkEntry(settings_frame, width=80)
        self._mb_entry.insert(0, str(self._settings["GrowthThresholdMB"]))
        self._mb_entry.grid(row=0, column=4, padx=4, pady=8)

        ctk.CTkLabel(settings_frame, text="Days:").grid(row=0, column=5, padx=(12, 4), pady=8)
        self._days_entry = ctk.CTkEntry(settings_frame, width=60)
        self._days_entry.insert(0, str(self._settings["HistoryDays"]))
        self._days_entry.grid(row=0, column=6, padx=4, pady=8)

        self._start_btn = ctk.CTkButton(settings_frame, text="Start", width=80, command=self._on_start)
        self._start_btn.grid(row=0, column=7, padx=(12, 4), pady=8)

        self._log_btn = ctk.CTkButton(settings_frame, text="Show Log", width=90, state="disabled", command=self._show_log)
        self._log_btn.grid(row=0, column=8, padx=(4, 10), pady=8)

        # --- Results ---
        self._results = ctk.CTkTextbox(self, font=("Consolas", 12), wrap="none")
        self._results.grid(row=1, column=0, padx=12, pady=6, sticky="nsew")
        self._results.configure(state="disabled")

        # --- Status bar ---
        self._status_var = ctk.StringVar(value="Ready.")
        ctk.CTkLabel(self, textvariable=self._status_var, anchor="w",
                     font=("Consolas", 11)).grid(row=2, column=0, padx=14, pady=(0, 8), sticky="ew")

    def _browse(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=self._dir_entry.get().strip() or "C:\\", title="Select folder")
        if path:
            self._dir_entry.delete(0, "end")
            self._dir_entry.insert(0, path.replace("/", "\\"))

    def _on_start(self):
        if self._scanner is not None:
            self._scanner.stop()
            self._start_btn.configure(text="Start")
            self._scanner = None
            return

        target = self._dir_entry.get().strip()
        try:
            threshold = int(self._mb_entry.get().strip())
            days = int(self._days_entry.get().strip())
        except ValueError:
            self._set_status("Invalid threshold or days value.")
            return

        save_settings(target, threshold, days)
        self._clear_results()
        self._log_lines = []
        self._last_log_path = None
        self._log_btn.configure(state="disabled")
        self._start_btn.configure(text="Stop")

        self._scanner = FolderScanner(
            target_dir=target,
            threshold_mb=threshold,
            history_days=days,
            on_status=lambda msg: self.after(0, self._set_status, msg),
            on_result=lambda folder, mb: self.after(0, self._append_result, folder, mb, days),
            on_complete=lambda lines, **kw: self.after(0, lambda: self._on_complete(lines, **kw)),
        )
        self._scanner.start()

    def _append_result(self, folder: str, mb: float, days: int):
        self._results.configure(state="normal")
        self._results.insert("end", f"⚠  {folder}\n    → {mb} MB in last {days} day(s)\n\n")
        self._results.see("end")
        self._results.configure(state="disabled")

    def _clear_results(self):
        self._results.configure(state="normal")
        self._results.delete("1.0", "end")
        self._results.configure(state="disabled")

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _on_complete(self, log_lines: list, cancelled=False, flagged=0, total=0):
        self._scanner = None
        self._start_btn.configure(text="Start")
        if log_lines:
            self._last_log_path = FolderScanner.write_log(
                log_lines,
                self._dir_entry.get().strip(),
                int(self._mb_entry.get().strip()),
                int(self._days_entry.get().strip()),
            )
            self._log_btn.configure(state="normal")
            suffix = f"  Log: {self._last_log_path.name}"
        else:
            self._last_log_path = None
            suffix = ""
        if cancelled:
            self._set_status(f"Scan stopped.{suffix}")
        else:
            self._set_status(f"Done. {flagged} folder(s) found out of {total} scanned.{suffix}")

    def _show_log(self):
        if self._last_log_path and self._last_log_path.exists():
            import subprocess
            subprocess.Popen(["notepad.exe", str(self._last_log_path)])


if __name__ == "__main__":
    App().mainloop()
