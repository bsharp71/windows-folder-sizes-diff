Implemented the Phase 3 review fixes and added the missing GUI view-mode behavior.

Key corrections:
- Preserved Phase 2 direct-scan compatibility by keeping hierarchy version out of the scan configuration hash.
- Fixed parent/depth metadata persistence across directory batches and migrated Phase 2 rows.
- Marked upgraded Phase 2 hierarchy data as `unavailable`.
- Made hierarchy cycle detection iterative and persisted hierarchy warnings.
- Removed invalid summed inclusive totals from models/reports.
- Added GUI `Direct Growth View` vs `Folder Tree View` radio controls, with direct mode unindented and tree mode parent-first.

Touched areas include [configuration.py](</G:/My Drive/Programming/windows-folder-sizes-diff/src/windows_folder_sizes_diff/db/configuration.py>), [repositories.py](</G:/My Drive/Programming/windows-folder-sizes-diff/src/windows_folder_sizes_diff/db/repositories.py>), [hierarchy.py](</G:/My Drive/Programming/windows-folder-sizes-diff/src/windows_folder_sizes_diff/analysis/hierarchy.py>), [actions.py](</G:/My Drive/Programming/windows-folder-sizes-diff/src/windows_folder_sizes_diff/gui/actions.py>), and the Phase 3 Alembic migration.

Verification:
- `uv run pytest` passed: `70 passed in 41.89s`
- `git diff --check -- README.md alembic/versions/0003_phase_3_hierarchical_sizing.py src tests` passed

Note: `config.yaml` is still modified in the worktree and has whitespace noise; I left it alone because it looks like local/runtime config rather than part of the Phase 3 implementation.