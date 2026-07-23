"""Scan warnings dialog."""

from __future__ import annotations

import customtkinter as ctk

from windows_folder_sizes_diff.db.models import ScanWarningRecord

WARNING_FILTERS = (
    "All",
    "Permission errors",
    "Disappeared paths",
    "Filesystem errors",
    "Other",
)


HEADINGS = (
    ("time", "Time", 155),
    ("path", "Path", 280),
    ("operation", "Operation", 115),
    ("error_type", "Error Type", 145),
    ("error_code", "Error Code", 95),
    ("message", "Message", 290),
)


class ScanWarningsDialog(ctk.CTkToplevel):
    """Display structured persisted warnings for a scan."""

    def __init__(self, master, *, scan_id: int, warnings: list[ScanWarningRecord]) -> None:
        super().__init__(master)
        self.title(f"Scan Warnings {scan_id}")
        self.geometry("1040x500")
        self.minsize(760, 320)
        self.transient(master)
        self._warnings = warnings

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.filter_var = ctk.StringVar(value="All")
        filter_box = ctk.CTkOptionMenu(
            self,
            values=WARNING_FILTERS,
            variable=self.filter_var,
            command=lambda _value: self._populate(),
            width=220,
        )
        filter_box.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="w")

        self.table = ctk.CTkScrollableFrame(self)
        self.table.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="nsew")
        self.table.grid_columnconfigure(1, weight=1)
        self.table.grid_columnconfigure(5, weight=1)

        self.empty_label = ctk.CTkLabel(self, text="", anchor="w")
        self.empty_label.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="w")
        ctk.CTkButton(self, text="Close", width=90, command=self.destroy).grid(
            row=3, column=0, padx=10, pady=(0, 10), sticky="e"
        )
        self._populate()

    def _populate(self) -> None:
        for child in self.table.winfo_children():
            child.destroy()
        self._build_header()
        rows = [warning for warning in self._warnings if _matches_filter(warning, self.filter_var.get())]
        for row_index, warning in enumerate(rows, start=1):
            self._build_row(row_index, warning)
        if not self._warnings:
            self.empty_label.configure(text="No warnings were recorded for this scan.")
        elif not rows:
            self.empty_label.configure(text="No warnings match the selected filter.")
        else:
            self.empty_label.configure(text="")

    def _build_header(self) -> None:
        for column_index, (_key, label, width) in enumerate(HEADINGS):
            ctk.CTkLabel(
                self.table,
                text=label,
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                width=width,
            ).grid(row=0, column=column_index, padx=4, pady=(4, 8), sticky="ew")

    def _build_row(self, row_index: int, warning: ScanWarningRecord) -> None:
        frame = ctk.CTkFrame(self.table, fg_color=("gray90", "gray20"), corner_radius=4)
        frame.grid(row=row_index, column=0, columnspan=len(HEADINGS), pady=2, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(5, weight=1)
        values = {
            "time": warning.occurred_at,
            "path": warning.path,
            "operation": warning.operation,
            "error_type": warning.error_type,
            "error_code": warning.error_code or "",
            "message": warning.message,
        }
        for column_index, (key, _label, width) in enumerate(HEADINGS):
            ctk.CTkLabel(
                frame,
                text=str(values[key]),
                anchor="w",
                width=width,
                wraplength=width,
            ).grid(row=0, column=column_index, padx=4, pady=6, sticky="ew")


def _matches_filter(warning: ScanWarningRecord, filter_name: str) -> bool:
    if filter_name == "All":
        return True
    haystack = f"{warning.operation} {warning.error_type} {warning.message}".lower()
    if filter_name == "Permission errors":
        return "permission" in haystack or "access denied" in haystack
    if filter_name == "Disappeared paths":
        return "disappear" in haystack or "not found" in haystack or "missing" in haystack
    if filter_name == "Filesystem errors":
        return "oserror" in haystack or "filesystem" in haystack or "file" in haystack
    return not any(
        _matches_filter(warning, name)
        for name in ("Permission errors", "Disappeared paths", "Filesystem errors")
    )
