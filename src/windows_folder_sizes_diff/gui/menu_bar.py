"""Native Tk menu bar for the CustomTkinter main window."""

from __future__ import annotations

import tkinter as tk

from windows_folder_sizes_diff.gui.actions import ApplicationActions
from windows_folder_sizes_diff.gui.state import ApplicationState, ComparisonViewFilters


class ApplicationMenuBar:
    """Build and update the native application menu bar."""

    def __init__(
        self,
        root: tk.Misc,
        actions: ApplicationActions,
        view_state: ComparisonViewFilters,
    ) -> None:
        self._root = root
        self._actions = actions
        self._view_state = view_state
        self.menu_bar = tk.Menu(root)
        self.menus: dict[str, tk.Menu] = {}
        self._build()
        root.configure(menu=self.menu_bar)
        root.bind("<Control-r>", self._run_scan_shortcut)
        root.bind("<Control-R>", self._run_scan_shortcut)
        root.bind("<F5>", self._refresh_shortcut)

    def update_state(self, state: ApplicationState, *, has_result_view: bool) -> None:
        file_menu = self.menus["File"]
        history_menu = self.menus["History"]
        view_menu = self.menus["View"]

        can_run = not state.scan_active and not state.cancellation_requested and not state.shutting_down
        file_menu.entryconfigure("Run Scan", state="normal" if can_run else "disabled")

        history_state = "normal" if state.has_scans else "disabled"
        history_menu.entryconfigure("Recent Scans…", state=history_state)
        history_menu.entryconfigure("Scan Details…", state=history_state)
        history_menu.entryconfigure(
            "Latest Comparison",
            state="normal" if state.has_completed_comparison else "disabled",
        )
        history_menu.entryconfigure(
            "Scan Warnings…",
            state="normal" if state.current_scan_warning_count > 0 else "disabled",
        )

        filter_state = "normal" if has_result_view else "disabled"
        for label in (
            "Direct Growth View",
            "Folder Tree View",
            "Show Growth",
            "Show Reductions",
            "Show New and Removed Folders",
            "Show Incomplete Comparisons",
        ):
            view_menu.entryconfigure(label, state=filter_state)
        view_menu.entryconfigure("Refresh", state="normal")

    def sync_filter_variables(self) -> None:
        self.view_mode_var.set(self._view_state.view_mode)
        self.show_growth_var.set(self._view_state.show_growth)
        self.show_reductions_var.set(self._view_state.show_reductions)
        self.show_new_removed_var.set(self._view_state.show_new_removed)
        self.show_incomplete_var.set(self._view_state.show_incomplete)

    def _build(self) -> None:
        self._build_file_menu()
        self._build_history_menu()
        self._build_view_menu()
        self._build_help_menu()

    def _build_file_menu(self) -> None:
        menu = tk.Menu(self.menu_bar, tearoff=False)
        menu.add_command(
            label="Run Scan",
            accelerator="Ctrl+R",
            command=self._actions.run_scan,
        )
        menu.add_separator()
        menu.add_command(label="Open Logs Folder", command=self._actions.open_logs_folder)
        menu.add_separator()
        menu.add_command(label="Exit", command=self._actions.exit_application)
        self.menu_bar.add_cascade(label="File", menu=menu)
        self.menus["File"] = menu

    def _build_history_menu(self) -> None:
        menu = tk.Menu(self.menu_bar, tearoff=False)
        menu.add_command(label="Recent Scans…", command=self._actions.show_recent_scans)
        menu.add_command(label="Latest Comparison", command=self._actions.show_latest_comparison)
        menu.add_command(label="Scan Details…", command=self._actions.show_scan_details)
        menu.add_command(label="Scan Warnings…", command=self._actions.show_scan_warnings)
        self.menu_bar.add_cascade(label="History", menu=menu)
        self.menus["History"] = menu

    def _build_view_menu(self) -> None:
        self.view_mode_var = tk.StringVar(master=self._root, value=self._view_state.view_mode)
        self.show_growth_var = tk.BooleanVar(master=self._root, value=self._view_state.show_growth)
        self.show_reductions_var = tk.BooleanVar(
            master=self._root, value=self._view_state.show_reductions
        )
        self.show_new_removed_var = tk.BooleanVar(
            master=self._root, value=self._view_state.show_new_removed
        )
        self.show_incomplete_var = tk.BooleanVar(
            master=self._root, value=self._view_state.show_incomplete
        )

        menu = tk.Menu(self.menu_bar, tearoff=False)
        menu.add_radiobutton(
            label="Direct Growth View",
            variable=self.view_mode_var,
            value="direct",
            command=self._on_view_filters_changed,
        )
        menu.add_radiobutton(
            label="Folder Tree View",
            variable=self.view_mode_var,
            value="tree",
            command=self._on_view_filters_changed,
        )
        menu.add_separator()
        menu.add_checkbutton(
            label="Show Growth",
            variable=self.show_growth_var,
            command=self._on_view_filters_changed,
        )
        menu.add_checkbutton(
            label="Show Reductions",
            variable=self.show_reductions_var,
            command=self._on_view_filters_changed,
        )
        menu.add_checkbutton(
            label="Show New and Removed Folders",
            variable=self.show_new_removed_var,
            command=self._on_view_filters_changed,
        )
        menu.add_checkbutton(
            label="Show Incomplete Comparisons",
            variable=self.show_incomplete_var,
            command=self._on_view_filters_changed,
        )
        menu.add_command(
            label="Refresh",
            accelerator="F5",
            command=self._actions.refresh_current_view,
        )
        self.menu_bar.add_cascade(label="View", menu=menu)
        self.menus["View"] = menu

    def _build_help_menu(self) -> None:
        menu = tk.Menu(self.menu_bar, tearoff=False)
        menu.add_command(
            label="Measurement Explanation",
            command=self._actions.show_measurement_explanation,
        )
        menu.add_command(label="Open Application Log", command=self._actions.open_application_log)
        menu.add_separator()
        menu.add_command(label="About", command=self._actions.show_about)
        self.menu_bar.add_cascade(label="Help", menu=menu)
        self.menus["Help"] = menu

    def _on_view_filters_changed(self) -> None:
        self._actions.update_filters(
            ComparisonViewFilters(
                show_growth=bool(self.show_growth_var.get()),
                show_reductions=bool(self.show_reductions_var.get()),
                show_new_removed=bool(self.show_new_removed_var.get()),
                show_incomplete=bool(self.show_incomplete_var.get()),
                view_mode=str(self.view_mode_var.get()),
            )
        )

    def _run_scan_shortcut(self, _event: object | None = None) -> str:
        self._actions.run_scan()
        return "break"

    def _refresh_shortcut(self, _event: object | None = None) -> str:
        self._actions.refresh_current_view()
        return "break"
