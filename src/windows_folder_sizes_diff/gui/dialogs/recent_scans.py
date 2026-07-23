"""Recent scans history dialog."""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from windows_folder_sizes_diff.db.models import Scan

HEADINGS = (
    ("scan_id", "Scan ID", 70),
    ("started", "Started", 155),
    ("completed", "Completed", 155),
    ("status", "Status", 130),
    ("target", "Target", 280),
    ("baseline", "Baseline", 85),
    ("comparison", "Comparison", 150),
    ("folders", "Folders", 85),
    ("warnings", "Warnings", 85),
)


class RecentScansDialog(ctk.CTkToplevel):
    """Display persisted scan history and scan-level actions."""

    def __init__(
        self,
        master,
        scans: list[Scan],
        *,
        on_select_scan: Callable[[int], None],
        on_open_details: Callable[[int], None],
        on_open_warnings: Callable[[int], None],
        on_open_comparison: Callable[[int], None],
    ) -> None:
        super().__init__(master)
        self.title("Recent Scans")
        self.geometry("1080x500")
        self.minsize(820, 340)
        self.transient(master)
        self._scans = {scan.id: scan for scan in scans}
        self._selected_scan_id: int | None = None
        self._row_frames: dict[int, ctk.CTkFrame] = {}
        self._on_select_scan = on_select_scan
        self._on_open_details = on_open_details
        self._on_open_warnings = on_open_warnings
        self._on_open_comparison = on_open_comparison

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        if not scans:
            self._build_empty_state()
            return

        table = ctk.CTkScrollableFrame(self)
        table.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="nsew")
        table.grid_columnconfigure(4, weight=1)
        self._build_header(table)
        for row_index, scan in enumerate(scans, start=1):
            self._build_row(table, row_index, scan)

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="e")
        ctk.CTkButton(button_frame, text="Details", width=100, command=self._open_details).grid(
            row=0, column=0, padx=(0, 6)
        )
        ctk.CTkButton(button_frame, text="Warnings", width=100, command=self._open_warnings).grid(
            row=0, column=1, padx=(0, 6)
        )
        ctk.CTkButton(
            button_frame,
            text="Open Comparison",
            width=150,
            command=self._open_comparison,
        ).grid(row=0, column=2, padx=(0, 6))
        ctk.CTkButton(button_frame, text="Close", width=90, command=self.destroy).grid(
            row=0, column=3
        )

    def _build_empty_state(self) -> None:
        ctk.CTkLabel(self, text="No scans have been recorded yet.", anchor="center").grid(
            row=0, column=0, padx=12, pady=12, sticky="nsew"
        )
        ctk.CTkButton(self, text="Close", width=90, command=self.destroy).grid(
            row=1, column=0, padx=12, pady=(0, 12), sticky="e"
        )

    def _build_header(self, parent: ctk.CTkScrollableFrame) -> None:
        for column_index, (_key, label, width) in enumerate(HEADINGS):
            ctk.CTkLabel(
                parent,
                text=label,
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                width=width,
            ).grid(row=0, column=column_index, padx=4, pady=(4, 8), sticky="ew")

    def _build_row(self, parent: ctk.CTkScrollableFrame, row_index: int, scan: Scan) -> None:
        frame = ctk.CTkFrame(parent, fg_color=("gray90", "gray20"), corner_radius=4)
        frame.grid(row=row_index, column=0, columnspan=len(HEADINGS), pady=2, sticky="ew")
        frame.grid_columnconfigure(4, weight=1)
        self._row_frames[scan.id] = frame
        values = {
            "scan_id": scan.id,
            "started": scan.started_at,
            "completed": scan.completed_at or "",
            "status": scan.status,
            "target": scan.target_path,
            "baseline": scan.baseline_scan_id or "",
            "comparison": scan.comparison_status,
            "folders": scan.folders_analyzed,
            "warnings": scan.warning_count,
        }
        for column_index, (key, _label, width) in enumerate(HEADINGS):
            label = ctk.CTkLabel(
                frame,
                text=str(values[key]),
                anchor="w",
                width=width,
            )
            label.grid(row=0, column=column_index, padx=4, pady=6, sticky="ew")
            label.bind("<Button-1>", lambda _event, scan_id=scan.id: self._select_scan(scan_id))
            label.bind("<Double-Button-1>", lambda _event, scan_id=scan.id: self._open_details_for(scan_id))
        frame.bind("<Button-1>", lambda _event, scan_id=scan.id: self._select_scan(scan_id))
        frame.bind("<Double-Button-1>", lambda _event, scan_id=scan.id: self._open_details_for(scan_id))

    def _select_scan(self, scan_id: int) -> None:
        self._selected_scan_id = scan_id
        for row_scan_id, frame in self._row_frames.items():
            frame.configure(
                fg_color=("gray75", "gray30")
                if row_scan_id == scan_id
                else ("gray90", "gray20")
            )
        self._on_select_scan(scan_id)

    def _open_details(self) -> None:
        if self._selected_scan_id is not None:
            self._open_details_for(self._selected_scan_id)

    def _open_details_for(self, scan_id: int) -> None:
        self._on_open_details(scan_id)

    def _open_warnings(self) -> None:
        if self._selected_scan_id is not None:
            self._on_open_warnings(self._selected_scan_id)

    def _open_comparison(self) -> None:
        if self._selected_scan_id is not None:
            self._on_open_comparison(self._selected_scan_id)
