# Phase 2 GUI Menu Bar Technical Specification

Implement Phase 2.1 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 2.1. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## Application Navigation, Scan History, Result Filters, and Help

**Project:** `windows-folder-sizes-diff`
**Implementation point:** After Phase 2
**Language:** Python 3.12+
**GUI:** CustomTkinter with native Tkinter menu support
**Prerequisites:** Phases 0–2 completed

---

# 1. Objective

Add a conventional desktop application menu bar to the Phase 2 GUI.

The menu bar must expose only functionality already supported by the application after Phase 2:

* starting a scan;
* opening application logs;
* viewing persisted scan history;
* opening the latest comparison;
* inspecting scan details;
* reviewing scan warnings;
* filtering the current comparison results;
* refreshing the displayed data;
* viewing measurement documentation;
* viewing application information;
* exiting the application.

The menu bar must not introduce placeholder commands for capabilities planned for Phases 3–8.

The existing **Show Logs** button should be removed from the main interface. Its position should become a contextual **Cancel Scan** button that is visible only while a scan is active.

---

# 2. Final Menu Structure

Implement exactly this initial structure:

```text
File
├── Run Scan
├── Open Logs Folder
└── Exit

History
├── Recent Scans…
├── Latest Comparison
├── Scan Details…
└── Scan Warnings…

View
├── Show Growth
├── Show Reductions
├── Show New and Removed Folders
├── Show Incomplete Comparisons
└── Refresh

Help
├── Measurement Explanation
├── Open Application Log
└── About
```

Do not add:

* Cancel Scan;
* Compare Scans;
* Settings;
* hierarchy or tree views;
* reparse-point reports;
* volume reconciliation;
* allocated-size controls;
* file-level forensic reports;
* backup or maintenance functions;
* scheduling;
* retention;
* trend reports.

These capabilities are not part of the Phase 2 GUI.

---

# 3. Design Principles

## 3.1 Menus invoke application actions

Menu callbacks must not contain substantial business logic.

The main scan button, menu commands, keyboard shortcuts, dialogs, and contextual controls should call shared application actions.

Example:

```python
class ApplicationActions:
    def run_scan(self) -> None:
        ...

    def open_logs_folder(self) -> None:
        ...

    def show_recent_scans(self) -> None:
        ...

    def show_latest_comparison(self) -> None:
        ...

    def show_scan_details(self) -> None:
        ...

    def show_scan_warnings(self) -> None:
        ...

    def refresh_current_view(self) -> None:
        ...

    def show_measurement_explanation(self) -> None:
        ...

    def open_application_log(self) -> None:
        ...

    def show_about(self) -> None:
        ...

    def exit_application(self) -> None:
        ...
```

A different class name is acceptable if the existing application architecture already has a controller or command layer.

## 3.2 No duplicated implementations

The following must use the same underlying action:

* main **Run Scan** button;
* **File → Run Scan**;
* the `Ctrl+R` shortcut.

The same principle applies to refresh, exit, and other duplicated entry points.

## 3.3 State-aware commands

Menu command state must reflect current application state.

Examples:

* **Run Scan** disabled while scanning;
* history commands disabled when no persisted scans exist;
* **Latest Comparison** disabled when no completed comparison exists;
* **Scan Warnings** disabled when the selected or current scan has no warnings.

## 3.4 No disabled future placeholders

Do not add visible menu items for unimplemented phases, even in a disabled state.

---

# 4. Menu Technology

CustomTkinter does not provide a replacement for every native desktop menu capability.

Use the native Tkinter `Menu` class attached to the CustomTkinter root window.

Example architecture:

```python
import tkinter as tk
import customtkinter as ctk


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.menu_bar = tk.Menu(self)
        self.configure(menu=self.menu_bar)
```

The menu should follow the operating system’s native menu appearance.

Do not attempt to reproduce the menu bar using a row of CustomTkinter buttons.

---

# 5. File Menu

Implement:

```text
File
├── Run Scan
├── Open Logs Folder
└── Exit
```

Recommended separators:

```text
File
├── Run Scan
├──────────────
├── Open Logs Folder
├──────────────
└── Exit
```

---

# 6. File → Run Scan

## Purpose

Start a new scan using the same configuration and validation path as the primary GUI scan button.

## Behavior

When selected:

1. validate the current target and scan inputs;
2. prevent a second concurrent scan;
3. begin the existing Phase 2 scan workflow;
4. update GUI state;
5. disable scan-start controls;
6. reveal the contextual **Cancel Scan** button.

## State

Enabled when:

* no scan is active;
* the application is not shutting down;
* no conflicting operation is active.

Disabled when:

* scanning;
* cancellation is in progress;
* application shutdown is in progress.

## Keyboard shortcut

Recommended:

```text
Ctrl+R
```

The shortcut must use the same action.

Do not use `F5` unless the application already uses that convention.

---

# 7. File → Open Logs Folder

## Purpose

Open the application’s log directory in Windows File Explorer.

## Behavior

Use the configured or resolved log directory.

Recommended Windows implementation:

```python
os.startfile(log_directory)
```

Validate that the directory exists.

If it does not exist:

* create it when appropriate; or
* display an informative error dialog.

Do not hard-code a user-specific path.

## Error handling

Display a GUI error if Windows cannot open the directory.

Also write the failure to the application log.

---

# 8. File → Exit

## Purpose

Close the application safely.

## Behavior with no active scan

Close normally.

## Behavior during an active scan

Do not terminate the process immediately.

Display a confirmation dialog:

```text
A scan is currently running.

Cancel the scan and exit?
```

Options:

```text
Cancel Scan and Exit
Keep Running
```

If the user chooses to exit:

1. request cancellation;
2. wait for the worker to reach a safe terminal state;
3. flush pending persistence or event processing;
4. close database resources;
5. destroy the GUI.

Do not forcibly terminate the worker thread unless the existing architecture explicitly supports safe termination.

## Window-close integration

The window close button must invoke the same exit action:

```python
root.protocol("WM_DELETE_WINDOW", actions.exit_application)
```

## Keyboard shortcut

Recommended:

```text
Alt+F4
```

This normally arrives through the operating system and should use the same close handler.

---

# 9. History Menu

Implement:

```text
History
├── Recent Scans…
├── Latest Comparison
├── Scan Details…
└── Scan Warnings…
```

The History menu is justified by Phase 2 persistence and comparison capabilities.

---

# 10. History → Recent Scans

## Purpose

Display persisted scan history from the SQLite database.

## Dialog type

Open a modal or modeless scan-history window.

A modeless window is preferred if the current GUI architecture supports multiple application windows safely.

## Required columns

Display:

```text
Scan ID
Started
Completed
Status
Target
Baseline Scan
Comparison Status
Folders Analyzed
Warnings
```

The exact visual labels may be shortened where necessary.

## Default ordering

Newest scan first.

## Required behavior

The user must be able to:

* select a scan;
* inspect its details;
* view its warnings;
* open its comparison when available;
* close the history window.

Double-clicking a scan may open **Scan Details**.

## Data source

Query persisted Phase 2 scan records.

Do not reconstruct history from log files.

## Empty state

Display:

```text
No scans have been recorded yet.
```

Do not open an empty table without explanation.

---

# 11. History → Latest Comparison

## Purpose

Display the latest successfully completed Phase 2 comparison.

## Selection rule

Use the most recent scan whose comparison status is:

```text
completed
```

or:

```text
completed_with_warnings
```

Do not select:

* baseline-only scans;
* comparisons still running;
* incompatible scans;
* failed comparisons;
* interrupted comparisons.

## Behavior

When selected:

1. load the persisted latest comparison;
2. make it the active comparison in the main results view;
3. apply the current View-menu filters;
4. update the status and summary areas.

## No-comparison state

Disable the command when possible.

If invoked without a comparison, display:

```text
No completed comparison is available.

The first compatible scan creates a baseline. Run another scan to calculate changes.
```

---

# 12. History → Scan Details

## Purpose

Display metadata for a selected scan.

## Scan selection

Selection priority:

1. scan selected in the Recent Scans window;
2. scan currently displayed in the main view;
3. latest persisted scan.

If none exists, disable the command or display an empty-state message.

## Required fields

Display:

```text
Scan ID
Scan UUID
Target path
Normalized target path
Started
Completed
Status

Baseline scan ID
Comparison status
Measurement algorithm version
Configuration compatibility or hash

Folders discovered
Folders analyzed
Folders compared
Folders matched or shown
Files examined
Warning count

Cancellation requested
Failure message
```

Only show fields that exist in the Phase 2 schema.

Do not fabricate unavailable metadata.

## Presentation

Use a read-only dialog.

Long values such as paths, UUIDs, hashes, and failure messages must be selectable for copying.

---

# 13. History → Scan Warnings

## Purpose

Display structured warnings associated with a scan.

## Scan selection

Use the same selection priority as **Scan Details**.

## Required columns

Display:

```text
Time
Path
Operation
Error Type
Error Code
Message
```

Directory identity may be included internally but does not need to be shown by default.

## Filters

At minimum, allow filtering by:

```text
All
Permission errors
Disappeared paths
Filesystem errors
Other
```

Filtering may be implemented through a simple selector in the warning dialog.

## Empty state

Display:

```text
No warnings were recorded for this scan.
```

## Data source

Use persisted `scan_warnings` or the corresponding Phase 2 repository.

Do not parse warning text from the application log.

---

# 14. View Menu

Implement:

```text
View
├── Show Growth
├── Show Reductions
├── Show New and Removed Folders
├── Show Incomplete Comparisons
└── Refresh
```

The first four items must be checkable menu commands.

---

# 15. View State Model

Create a dedicated view-filter state.

Recommended model:

```python
@dataclass
class ComparisonViewFilters:
    show_growth: bool = True
    show_reductions: bool = False
    show_new_removed: bool = True
    show_incomplete: bool = True
```

Equivalent Pydantic or existing state models are acceptable.

Do not use menu variables as the only source of truth.

The filter model should drive:

* menu checkmarks;
* main result filtering;
* refresh behavior;
* future toolbar or dialog controls.

---

# 16. View → Show Growth

## Default

Checked.

## Includes

Display comparison rows with states such as:

```text
grown
```

A new directory may also have a positive delta, but it belongs to the dedicated new/removed category rather than ordinary growth filtering.

## Behavior

Toggling the item immediately refreshes the visible result set.

Do not rerun the filesystem scan or database comparison.

---

# 17. View → Show Reductions

## Default

Unchecked.

## Includes

Display rows with state:

```text
reduced
```

The result table must preserve the negative sign.

Do not display reductions as positive “space recovered” values unless that is an additional presentation field.

---

# 18. View → Show New and Removed Folders

## Default

Checked.

## Includes

Display:

```text
new
removed
```

These should remain visibly distinguished from ordinary growth and reduction.

Recommended state labels:

```text
New
Removed
```

Do not convert them silently into generic grown or reduced rows.

---

# 19. View → Show Incomplete Comparisons

## Default

Checked.

## Includes

Display rows with states such as:

```text
incomplete
not_comparable
```

and observations where the delta is unavailable.

These rows must not display an invented zero delta.

Recommended display:

```text
—
```

or:

```text
Unavailable
```

## Rationale

Incomplete results are important diagnostic information and should remain visible by default.

---

# 20. View → Refresh

## Purpose

Reload the currently displayed persisted data and reapply the active filters.

## Behavior

Refresh must:

1. retain the currently selected scan or comparison where possible;
2. reload current scan metadata;
3. reload comparison rows;
4. reapply View menu filters;
5. update summaries and warning counts;
6. preserve table selection where practical.

Refresh must not:

* start a new scan;
* create a new comparison;
* change the selected baseline;
* reset filters.

## Keyboard shortcut

Recommended:

```text
F5
```

---

# 21. View Menu Checkbutton Implementation

Use Tkinter checkbutton menu items with Tk variables.

Example:

```python
self.show_growth_var = tk.BooleanVar(value=True)

view_menu.add_checkbutton(
    label="Show Growth",
    variable=self.show_growth_var,
    command=self._on_view_filters_changed,
)
```

Synchronize the variables with the application’s view-state model.

Do not scatter filtering logic across individual callback functions.

Use one shared refresh path.

---

# 22. Help Menu

Implement:

```text
Help
├── Measurement Explanation
├── Open Application Log
└── About
```

Recommended separators:

```text
Help
├── Measurement Explanation
├── Open Application Log
├────────────────────────
└── About
```

---

# 23. Help → Measurement Explanation

## Purpose

Explain the meaning and limitations of Phase 2 results.

## Required content

The dialog must explain:

### Baselines

```text
The first compatible scan creates a baseline.
A later compatible scan is required to calculate changes.
```

### Direct logical size

```text
Phase 2 measures the logical size of files directly contained in each folder.
It does not yet include descendant folders in parent totals.
```

### True differences

```text
Growth is calculated by subtracting the previous direct logical size from the current direct logical size.
```

### Same-size rewrites

```text
Rewriting a file without changing its size produces a zero-byte size difference.
```

### New and removed folders

```text
New folders are compared against zero.
Removed folders are reported as negative changes.
```

### Incomplete comparisons

```text
Folders that could not be measured reliably are shown as incomplete.
The application does not treat inaccessible folders as empty folders.
```

### Current limitations

```text
Phase 2 does not yet provide:
- inclusive parent-folder totals;
- reparse-point deduplication;
- physical allocated size;
- whole-volume reconciliation;
- file-level attribution.
```

## Presentation

Use a scrollable, read-only dialog.

Do not send the user to external documentation for these core explanations.

---

# 24. Help → Open Application Log

## Purpose

Open the current application log file in the operating system’s associated text editor.

## File selection

Use the currently active log file.

If rotating logs are used, open the active log rather than the oldest or largest log.

## Missing log

If no log file exists:

```text
No application log has been created yet.
```

Do not fail silently.

## Distinction from Open Logs Folder

* **Open Logs Folder** opens the directory.
* **Open Application Log** opens the active log file.

---

# 25. Help → About

## Purpose

Display application identity and current measurement capability.

## Required fields

Display:

```text
Application name
Application version
Python requirement
Database schema revision
Measurement mode
```

Recommended Phase 2 measurement description:

```text
Direct logical folder-size snapshots with scan-to-scan comparison
```

Optional:

```text
Database path
Project repository path
License
```

Only display optional fields if already known and useful.

## Version source

Read the application version from project metadata where practical.

Do not maintain a second manually duplicated version string.

---

# 26. Contextual Cancel Scan Button

The menu bar must not include **Cancel Scan**.

Replace the current **Show Logs** button with a contextual **Cancel Scan** button.

---

# 27. Cancel Button State Machine

## Idle

```text
Run Scan: enabled
Cancel Scan: hidden
```

## Scan starting

```text
Run Scan: disabled
Cancel Scan: visible and enabled
```

## Scanning

```text
Run Scan: disabled
Cancel Scan: visible and enabled
```

## Cancellation requested

```text
Run Scan: disabled
Cancel Scan: visible and disabled
Status: Cancelling…
```

## Completed

```text
Run Scan: enabled
Cancel Scan: hidden
```

## Completed with warnings

```text
Run Scan: enabled
Cancel Scan: hidden
```

## Cancelled

```text
Run Scan: enabled
Cancel Scan: hidden
```

## Failed

```text
Run Scan: enabled
Cancel Scan: hidden
```

The button must return to its idle state after every terminal scan event.

---

# 28. Cancel Button Behavior

When selected:

1. request cooperative cancellation through the existing cancellation mechanism;
2. disable the button to prevent repeated requests;
3. update the status text to `Cancelling…`;
4. allow the worker thread to terminate safely;
5. process the single terminal event;
6. restore idle controls.

Do not:

* terminate the thread forcibly;
* destroy the window;
* issue cancellation multiple times;
* mark a scan cancelled before the worker reaches the terminal state.

---

# 29. Main-Window Button Layout

The replacement should preserve the existing layout as much as possible.

If the current layout is:

```text
[Run Scan] [Show Logs]
```

change it to:

```text
Idle:
[Run Scan]

Scanning:
[Run Scan disabled] [Cancel Scan]
```

A stable layout that reserves the button space is acceptable, but the user requested that the button be visible only during active scanning.

Therefore, prefer `grid_remove()` or the equivalent over merely disabling it.

Example:

```python
cancel_button.grid_remove()
```

When scanning:

```python
cancel_button.grid()
```

---

# 30. Menu State Controller

Create a central state-update method.

Example:

```python
def update_command_states(self, state: ApplicationState) -> None:
    ...
```

It should update:

* File → Run Scan;
* History menu commands;
* View menu availability;
* contextual Cancel Scan button;
* main Run Scan button;
* status labels.

Recommended state fields:

```python
@dataclass
class ApplicationState:
    scan_active: bool
    cancellation_requested: bool
    has_scans: bool
    has_completed_comparison: bool
    current_scan_id: int | None
    current_scan_warning_count: int
    shutting_down: bool
```

Do not independently toggle each control from many event handlers.

---

# 31. Recommended Command States

## Initial application with no history

```text
File → Run Scan: enabled
File → Open Logs Folder: enabled
File → Exit: enabled

History → Recent Scans: disabled
History → Latest Comparison: disabled
History → Scan Details: disabled
History → Scan Warnings: disabled

View filters: enabled only if a result view exists
View → Refresh: enabled

Help commands: enabled
```

## After first baseline scan

```text
Recent Scans: enabled
Latest Comparison: disabled
Scan Details: enabled
Scan Warnings: enabled only if warnings exist
```

## After completed comparison

```text
Recent Scans: enabled
Latest Comparison: enabled
Scan Details: enabled
Scan Warnings: based on selected scan
View filters: enabled
```

## During scan

```text
Run Scan: disabled
Cancel Scan button: visible
History commands: remain available only if database reads are safe
View commands: remain available only if they do not interfere with scan updates
```

It is acceptable to leave history viewing enabled during scans if repository access and GUI state are thread-safe.

---

# 32. Dialog Architecture

Create reusable dialog classes or functions.

Recommended components:

```text
RecentScansDialog
ScanDetailsDialog
ScanWarningsDialog
MeasurementExplanationDialog
AboutDialog
```

Dialogs should not directly construct SQLAlchemy sessions unless the existing GUI architecture already uses a safe repository pattern.

Prefer:

```text
dialog
→ controller/action
→ service/repository
→ database
```

---

# 33. Threading Requirements

All GUI creation and modification must occur on the Tk main thread.

Menu callbacks execute on the GUI thread and may invoke quick repository reads.

Long-running database or filesystem operations must not block the GUI.

The following should be fast enough for the main thread if properly indexed:

* loading recent scan summaries;
* loading one scan’s metadata;
* loading a bounded warning list;
* loading the latest comparison page.

If full comparison loading is large, use:

* pagination;
* lazy loading;
* a background loader that returns through the existing event queue.

Do not manipulate menus from the scan worker thread.

---

# 34. Result Filtering Requirements

Filtering should operate on persisted or currently loaded comparison state.

For small-to-moderate result sets, filtering in memory is acceptable.

For large comparisons, prefer repository filtering with state parameters.

Recommended repository method:

```python
def list_directory_diffs(
    current_scan_id: int,
    *,
    include_growth: bool,
    include_reductions: bool,
    include_new_removed: bool,
    include_incomplete: bool,
    limit: int | None = None,
    offset: int = 0,
) -> list[DirectoryDiff]:
    ...
```

Do not load hundreds of thousands of unchanged rows when they are not displayed.

Phase 2 does not require a menu item for unchanged rows.

---

# 35. Accessibility and Usability

Requirements:

* keyboard navigation must work through native menu behavior;
* menu labels must use clear sentence-style naming;
* ellipses indicate that a dialog or additional selection will open;
* immediate commands should not use ellipses;
* disabled items must reflect unavailable actions;
* dialogs must have a clear Close button;
* long paths and messages must be selectable;
* destructive exit-during-scan action requires confirmation.

Use ellipses for:

```text
Recent Scans…
Scan Details…
Scan Warnings…
```

Do not use an ellipsis for:

```text
Run Scan
Latest Comparison
Refresh
About
```

---

# 36. Error Handling

Menu actions must handle:

```text
database unavailable
repository query failure
missing log directory
missing log file
Explorer launch failure
invalid current scan selection
comparison no longer available
application shutdown race
```

For each failure:

1. log the detailed technical error;
2. display a concise user-facing dialog;
3. keep the application running when safe.

Do not show raw stack traces in GUI dialogs.

---

# 37. Logging Requirements

Log:

```text
menu command invoked
scan started from menu
log folder opened
application log opened
history dialog opened
scan details opened
scan warnings opened
latest comparison loaded
view filter changed
refresh requested
exit requested
exit cancelled by user
```

Use debug or info level appropriately.

Do not log every mouse movement or menu hover.

---

# 38. Suggested File Structure

Adapt to the existing Phase 2 architecture.

Recommended structure:

```text
gui/
├── main_window.py
├── menu_bar.py
├── actions.py
├── state.py
└── dialogs/
    ├── recent_scans.py
    ├── scan_details.py
    ├── scan_warnings.py
    ├── measurement_explanation.py
    └── about.py
```

A smaller implementation is acceptable if the project remains modular.

Do not put all menu creation, dialog code, filtering, repository access, and scan control into one oversized main-window module.

---

# 39. Suggested Menu Builder

A dedicated builder is recommended.

```python
class ApplicationMenuBar:
    def __init__(
        self,
        root: tk.Misc,
        actions: ApplicationActions,
        view_state: ComparisonViewFilters,
    ) -> None:
        ...

    def update_state(self, state: ApplicationState) -> None:
        ...
```

Responsibilities:

* construct native menus;
* attach callbacks;
* manage checkbutton variables;
* update menu item states.

It must not:

* query the database directly;
* execute scan logic;
* calculate comparisons;
* format reports.

---

# 40. Keyboard Shortcuts

Implement:

```text
Ctrl+R    Run Scan
F5        Refresh
```

Optional:

```text
Ctrl+Q    Exit
```

Use `Ctrl+Q` only if it does not conflict with existing Windows or application conventions.

Shortcut bindings must:

* call the same shared action;
* respect disabled state;
* return `"break"` where appropriate to prevent duplicate propagation.

---

# 41. Persistence of View Filters

Phase 2 does not require persistent GUI preferences.

The filter state may reset on each application launch.

Recommended defaults:

```text
Show Growth: checked
Show Reductions: unchecked
Show New and Removed Folders: checked
Show Incomplete Comparisons: checked
```

Do not add a settings file solely for these menu options unless one already exists.

---

# 42. Testing Requirements

Use unit tests for state and actions, plus focused GUI tests where practical.

## 42.1 Menu construction

Verify top-level menus exist:

```text
File
History
View
Help
```

Verify no Settings menu exists.

## 42.2 File menu contents

Verify:

```text
Run Scan
Open Logs Folder
Exit
```

Verify **Cancel Scan** is not present.

## 42.3 History menu contents

Verify:

```text
Recent Scans…
Latest Comparison
Scan Details…
Scan Warnings…
```

## 42.4 View menu contents

Verify all four checkbuttons and Refresh exist.

## 42.5 Help menu contents

Verify:

```text
Measurement Explanation
Open Application Log
About
```

## 42.6 Run Scan action reuse

Verify the main button, menu command, and shortcut invoke the same action.

## 42.7 Run Scan disabled

While scanning:

* menu item disabled;
* main Run Scan button disabled.

## 42.8 Cancel button idle state

When idle:

```text
Cancel Scan button hidden
```

## 42.9 Cancel button active state

During scan:

```text
Cancel Scan button visible and enabled
```

## 42.10 Cancellation requested state

After click:

* cancellation requested once;
* button disabled;
* status shows Cancelling.

## 42.11 Terminal scan states

After completed, failed, or cancelled:

* Cancel button hidden;
* Run Scan enabled.

## 42.12 No scan history

History commands disabled or display correct empty states.

## 42.13 First baseline

After a baseline-only scan:

* Recent Scans enabled;
* Latest Comparison disabled.

## 42.14 Completed comparison

Latest Comparison becomes enabled and loads the correct scan.

## 42.15 Recent scan ordering

Newest scan appears first.

## 42.16 Scan details

Verify the dialog displays persisted fields accurately.

## 42.17 Warning dialog

Verify warning rows come from structured database records.

## 42.18 Warning empty state

Verify correct message.

## 42.19 Growth filter

Unchecking growth removes grown rows without rescanning.

## 42.20 Reduction filter

Checking reductions reveals negative deltas.

## 42.21 New and removed filter

Verify both states toggle together.

## 42.22 Incomplete filter

Verify unavailable deltas are shown and hidden correctly.

## 42.23 Refresh

Verify refresh:

* retains current scan;
* retains filters;
* reloads persisted data;
* does not start a scan.

## 42.24 Measurement explanation

Verify required Phase 2 concepts and limitations appear.

## 42.25 Open logs folder

Mock operating-system launch and verify correct directory.

## 42.26 Open application log

Mock launch and verify active log path.

## 42.27 Missing log file

Verify user-facing message.

## 42.28 Exit idle

Verify safe shutdown.

## 42.29 Exit during scan

Verify confirmation and cooperative cancellation.

## 42.30 Exit cancellation

Choosing Keep Running must leave the application and scan active.

## 42.31 Worker-thread safety

Verify scan events update menu state only through the GUI thread.

## 42.32 Existing tests

All Phase 0–2 tests must continue to pass.

---

# 43. Acceptance Criteria

The menu implementation is complete when all of the following are true:

1. A native menu bar is attached to the CustomTkinter root.
2. The top-level menus are File, History, View, and Help.
3. No Settings menu is present.
4. File contains Run Scan, Open Logs Folder, and Exit.
5. History contains Recent Scans, Latest Comparison, Scan Details, and Scan Warnings.
6. View contains the four specified result filters and Refresh.
7. Help contains Measurement Explanation, Open Application Log, and About.
8. No later-phase commands or disabled placeholders are present.
9. Cancel Scan is not present in any menu.
10. The existing Show Logs button is removed.
11. A contextual Cancel Scan button replaces it during active scans.
12. The Cancel Scan button is hidden while idle.
13. The Cancel Scan button is visible only while a scan is active or cancelling.
14. Cancellation uses the existing cooperative cancellation mechanism.
15. Run Scan is disabled during scanning.
16. Main buttons, menu items, and shortcuts use shared application actions.
17. Menu callbacks contain no database or scan business logic.
18. Recent Scans loads persisted database history.
19. Latest Comparison loads the newest completed compatible comparison.
20. Scan Details displays persisted Phase 2 metadata.
21. Scan Warnings displays structured warning records.
22. View filters change displayed rows without rescanning.
23. Growth is shown by default.
24. Reductions are hidden by default.
25. New and removed folders are shown by default.
26. Incomplete comparisons are shown by default.
27. Refresh retains the current scan and filter state.
28. Measurement Explanation accurately describes Phase 2 behavior.
29. Open Logs Folder opens the configured log directory.
30. Open Application Log opens the active application log.
31. Exit handles active scans safely.
32. Window-close behavior uses the same exit action.
33. All GUI updates occur on the main thread.
34. Errors are logged and shown through concise dialogs.
35. All existing Phase 0–2 tests continue to pass.
36. All menu-specific tests pass with:

```powershell
uv run pytest
```

---

# 44. Coding-Agent Assignment

Implement the Phase 2 GUI menu bar only.

Add a native Tkinter menu bar to the CustomTkinter root window with exactly this structure:

```text
File
├── Run Scan
├── Open Logs Folder
└── Exit

History
├── Recent Scans…
├── Latest Comparison
├── Scan Details…
└── Scan Warnings…

View
├── Show Growth
├── Show Reductions
├── Show New and Removed Folders
├── Show Incomplete Comparisons
└── Refresh

Help
├── Measurement Explanation
├── Open Application Log
└── About
```

Do not add a Settings menu, manual comparison command, or any Phase 3–8 functionality.

Create shared application actions so the menu, existing buttons, keyboard shortcuts, and window-close handler do not duplicate business logic.

Replace the existing **Show Logs** button with a contextual **Cancel Scan** button.

The Cancel Scan button must:

* remain hidden when no scan is active;
* appear when a scan starts;
* request cooperative cancellation;
* disable itself after cancellation is requested;
* show a `Cancelling…` status;
* hide after completion, cancellation, or failure.

Keep **Cancel Scan** out of the menu bar.

Implement state-aware menu commands:

* disable Run Scan while scanning;
* disable history commands when no applicable history exists;
* disable Latest Comparison when only a baseline exists;
* enable Scan Warnings only when a relevant scan can be selected or inspected.

Implement persisted history dialogs for:

* recent scans;
* scan details;
* scan warnings.

Load history and warnings from the SQLite repositories, not from logs.

Implement checkable View-menu filters with these defaults:

```text
Show Growth: true
Show Reductions: false
Show New and Removed Folders: true
Show Incomplete Comparisons: true
```

Changing a filter must refresh the visible comparison without rerunning the scan.

Implement:

```text
Ctrl+R → Run Scan
F5 → Refresh
```

Add a Measurement Explanation dialog describing:

* baseline creation;
* direct logical-size measurement;
* true scan-to-scan subtraction;
* same-size rewrites producing zero change;
* new and removed folder handling;
* incomplete comparisons;
* Phase 2 limitations.

Add an About dialog showing application version, database schema revision, and the current measurement description.

Use the existing application logging system for menu actions and failures.

Keep all GUI updates on the main Tk thread.

Run the full test suite and report:

* files changed;
* architecture decisions;
* new dialogs and actions;
* keyboard shortcuts;
* menu-state behavior;
* test results;
* unmet acceptance criteria;
* deferred technical debt.
