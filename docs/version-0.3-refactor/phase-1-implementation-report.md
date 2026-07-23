Implemented Phase 1 only.
Files Added or Changed
Added Alembic:alembic.ini
alembic/env.py
alembic/script.py.mako
alembic/versions/0001_phase_1_database_foundation.py

Added database layer:src/windows_folder_sizes_diff/db/*
Models, engine/session factory, repositories, lifecycle service, schema checks, persistence coordinator, path normalization.

Added CLI:src/windows_folder_sizes_diff/cli.py
folder-diff-cli script in pyproject.toml

Updated app/GUI/scanner/reporting/config:app.py verifies migrated schema and recovers stale scans.
scan_controller.py creates scan rows, persists events, finalizes lifecycle.
Scanner events now carry scan_id.
Reports include scan ID, UUID, DB status, and recent-activity wording.
AppSettings supports optional DatabasePath.

Added/expanded tests:tests/test_database.py
tests/test_scan_lifecycle.py
tests/test_repositories.py
tests/test_persistence.py
tests/test_cli.py
updated existing Phase 0 tests.

Updated:.gitignore
README.md
pyproject.toml
uv.lock

Note: git status also shows pre-existing dirty/untracked docs under docs/version-0.3-refactor/; I left those untouched.
Architectural Decisions
Scanner still has no SQLAlchemy imports and emits typed events only.
Persistence is handled by ScanPersistenceCoordinator consuming scanner events from the GUI/controller path.
Production schema creation is Alembic-only; runtime checks schema currency and does not call Base.metadata.create_all().
Directory identity is Phase 1 path-based, normalized case-insensitively.
All analyzed folders are persisted, including below-threshold folders.
Current timestamp-based matching_bytes semantics are preserved and not labeled as true growth.
Commands You Must Run
uv run alembic upgrade head
uv run folder-diff
Optional inspection:
uv run folder-diff-cli db-info
uv run folder-diff-cli scans
uv run folder-diff-cli scan-show <scan-id>
uv run folder-diff-cli warnings --scan-id <scan-id>
Test Results
uv run pytest
Result: 33 passed in 6.98s
Verified script entry points:folder-diff
folder-diff-cli

Verified Alembic history:<base> -> 0001_phase_1 (head)

Acceptance Criteria Not Fully Satisfied
None known.
Deferred Technical Debt
Persistence currently runs in the GUI event consumer path; acceptable for Phase 1, but can move to a dedicated consumer thread if large scans show UI pauses.
Warning rows currently persist structured warning paths; directory_id is optional and only populated where a directory identity is available.
No 10,000-observation benchmark was added beyond bounded batch design and unit coverage.

Edited 39 files+2,258-83Review changesUndoReview

src/windows_folder_sizes_diff/db/__init__.pysrc/windows_folder_sizes_diff/db/__init__.py+18-0
src/windows_folder_sizes_diff/db/base.pysrc/windows_folder_sizes_diff/db/base.py+7-0
src/windows_folder_sizes_diff/db/configuration.pysrc/windows_folder_sizes_diff/db/configuration.py+23-0
Show 36 more files